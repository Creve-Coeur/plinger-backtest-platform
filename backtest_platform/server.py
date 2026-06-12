# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import math
import mimetypes
import os
import sys
import threading
import traceback
import uuid
import warnings
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", message="Workbook contains no default style.*")


APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
STATIC_DIR = APP_DIR / "static"
DATA_DIR = APP_DIR / "data"
STRATEGY_STORE_FILE = DATA_DIR / "saved_strategies.json"

FUND_DIR = ROOT_DIR / "基金"
FUND_MANAGER_DIR = FUND_DIR / "基金经理"
INDEX_DIR = ROOT_DIR / "指数"
ENHANCED_DIR = ROOT_DIR / "增强"
STRATEGY_DIR = ROOT_DIR / "策略代码"
PRING_FILE_NAME = "普林格周期判断表_逐月_补全Stage7Stage8.xlsx"
DEFAULT_BENCHMARK_ID = "index:000300.SH"
APP_VERSION = "2026.06.12.3"

CATEGORY_LABELS = {
    "equity": "股票",
    "commodity": "商品",
    "convertible": "可转债",
    "pure_bond": "纯债",
}
CATEGORY_PRIORITY = ("equity", "commodity", "convertible", "pure_bond")
PRICE_COLUMNS = (
    "收盘价(元)",
    "复权净值(元)",
    "复权净值",
    "累计净值（分红再投资）",
    "累计净值",
    "单位净值",
)

STAGE_DOMINANT = {
    1: "convertible",
    2: "equity",
    3: "equity",
    4: "commodity",
    5: "commodity",
    6: "pure_bond",
    7: "commodity",
    8: "convertible",
}

DEFAULT_STAGE_WEIGHTS = {
    stage: {
        category: 0.70 if category == dominant else 0.10
        for category in CATEGORY_LABELS
    }
    for stage, dominant in STAGE_DOMINANT.items()
}

STAGE_WEIGHT_PROFILE_SPECS = {
    "1": {
        "label": "第一档",
        "shortLabel": "强偏股",
        "description": "优势资产45% + 股票35%，其余资产均分",
        "dominantWeight": 0.45,
        "tiltCategory": "equity",
        "tiltWeight": 0.35,
    },
    "2": {
        "label": "第二档",
        "shortLabel": "偏股",
        "description": "优势资产55% + 股票25%，其余资产均分",
        "dominantWeight": 0.55,
        "tiltCategory": "equity",
        "tiltWeight": 0.25,
    },
    "3": {
        "label": "第三档",
        "shortLabel": "均衡",
        "description": "优势资产70%，其余三类各10%",
        "dominantWeight": 0.70,
        "tiltCategory": None,
        "tiltWeight": 0.0,
    },
    "4": {
        "label": "第四档",
        "shortLabel": "偏债",
        "description": "优势资产55% + 纯债25%，其余资产均分",
        "dominantWeight": 0.55,
        "tiltCategory": "pure_bond",
        "tiltWeight": 0.25,
    },
    "5": {
        "label": "第五档",
        "shortLabel": "强偏债",
        "description": "优势资产45% + 纯债35%，其余资产均分",
        "dominantWeight": 0.45,
        "tiltCategory": "pure_bond",
        "tiltWeight": 0.35,
    },
}

KST_COMPONENTS = (
    (20, 10, 1),
    (60, 20, 2),
    (120, 30, 3),
    (240, 40, 4),
)


@dataclass(frozen=True)
class AssetMeta:
    id: str
    code: str
    name: str
    module: str
    start: str
    end: str
    count: int
    category: str | None = None
    manager: str | None = None
    roleLabel: str | None = None
    fullLabel: str | None = None
    cluster: str | None = None


@dataclass
class PreparedData:
    dates: pd.DatetimeIndex
    asset_returns: pd.DataFrame
    signal_returns: dict[str, pd.Series]
    raw_prices: pd.DataFrame
    splice_summary: list[dict[str, Any]]
    splice_context: dict[str, Any]
    main_selected: dict[str, list[str]]
    splice_selected: dict[str, list[str]] | None = None
    switch_date: pd.Timestamp | None = None

    def active_assets(self, date: pd.Timestamp) -> dict[str, list[str]]:
        if self.splice_selected is not None and self.switch_date is not None and date < self.switch_date:
            return self.splice_selected
        return self.main_selected


class DataStore:
    def __init__(self) -> None:
        self.assets: dict[str, pd.Series] = {}
        self.meta: dict[str, AssetMeta] = {}
        self.pring_df: pd.DataFrame | None = None
        self.pring_source: str | None = None
        self.loaded = False

    def ensure_loaded(self) -> None:
        if self.loaded:
            return
        self.assets.clear()
        self.meta.clear()
        self._load_funds()
        self._load_fund_managers()
        self._load_indexes()
        self._load_enhanced()
        self.pring_df = self._load_pring()
        self.loaded = True

    def _register_asset(
        self,
        module: str,
        code: str,
        name: str,
        series: pd.Series,
        category: str | None = None,
        manager: str | None = None,
        role_label: str | None = None,
        full_label: str | None = None,
        cluster: str | None = None,
    ) -> None:
        series = clean_price_series(series)
        if series.empty:
            return
        asset_id = f"{module}:{code}"
        dedupe = 2
        while asset_id in self.assets:
            asset_id = f"{module}:{code}:{dedupe}"
            dedupe += 1

        self.assets[asset_id] = series
        self.meta[asset_id] = AssetMeta(
            id=asset_id,
            code=code,
            name=name or code,
            module=module,
            start=series.index.min().strftime("%Y-%m-%d"),
            end=series.index.max().strftime("%Y-%m-%d"),
            count=int(series.count()),
            category=category,
            manager=manager,
            roleLabel=role_label,
            fullLabel=full_label,
            cluster=cluster,
        )

    def _load_funds(self) -> None:
        self._load_standard_library(FUND_DIR, "fund")

    def _load_fund_managers(self) -> None:
        if not FUND_MANAGER_DIR.exists():
            return
        csv_files = sorted(FUND_MANAGER_DIR.glob("*.csv"))
        workbook_files = sorted(FUND_MANAGER_DIR.glob("*.xlsx"))
        if not csv_files or not workbook_files:
            raise FileNotFoundError("基金经理目录需要同时包含净值 CSV 和标签配置工作簿")

        workbook = None
        for file in workbook_files:
            with pd.ExcelFile(file) as excel_file:
                if "公募配置池" in excel_file.sheet_names:
                    workbook = file
                    break
        if workbook is None:
            raise ValueError("基金经理标签工作簿缺少 sheet：公募配置池")

        pool = pd.read_excel(workbook, sheet_name="公募配置池", dtype={"基金代码": str})
        required = ["基金代码", "基金经理", "基金简称", "角色标签", "完整标签", "标签聚类"]
        missing = [column for column in required if column not in pool.columns]
        if missing:
            raise ValueError(f"公募配置池缺少字段: {', '.join(missing)}")
        pool = pool.dropna(subset=["基金代码", "基金简称"]).copy()
        pool["基金代码"] = pool["基金代码"].astype(str).str.strip()
        pool["基金简称"] = pool["基金简称"].astype(str).str.strip()
        if pool["基金代码"].duplicated().any():
            duplicates = sorted(pool.loc[pool["基金代码"].duplicated(keep=False), "基金代码"].unique())
            raise ValueError(f"公募配置池存在重复基金代码: {'、'.join(duplicates)}")
        if pool["基金简称"].duplicated().any():
            duplicates = sorted(pool.loc[pool["基金简称"].duplicated(keep=False), "基金简称"].unique())
            raise ValueError(f"公募配置池存在重复基金简称: {'、'.join(duplicates)}")

        nav = pd.read_csv(csv_files[0], encoding="utf-8-sig")
        if nav.shape[1] < 2:
            raise ValueError("基金经理净值 CSV 至少需要日期列和一只基金净值列")
        date_column = nav.columns[0]
        dates = pd.to_datetime(nav[date_column], errors="coerce")
        nav_names = {str(column).strip(): column for column in nav.columns[1:]}
        missing_nav = sorted(set(pool["基金简称"]) - set(nav_names))
        if missing_nav:
            raise ValueError(f"以下公募配置池基金缺少净值序列: {'、'.join(missing_nav)}")

        for row in pool.itertuples(index=False):
            name = str(getattr(row, "基金简称")).strip()
            series = pd.Series(
                pd.to_numeric(nav[nav_names[name]], errors="coerce").values,
                index=dates,
                name=f"manager:{getattr(row, '基金代码')}",
            )
            self._register_asset(
                "manager",
                str(getattr(row, "基金代码")).strip(),
                name,
                series,
                manager=text_or_none(getattr(row, "基金经理")),
                role_label=text_or_none(getattr(row, "角色标签")),
                full_label=text_or_none(getattr(row, "完整标签")),
                cluster=text_or_none(getattr(row, "标签聚类")),
            )

    def _load_indexes(self) -> None:
        self._load_standard_library(INDEX_DIR, "index")

    def _load_enhanced(self) -> None:
        if not ENHANCED_DIR.exists():
            return
        for category in CATEGORY_PRIORITY:
            category_dir = ENHANCED_DIR / CATEGORY_LABELS[category]
            if not category_dir.exists():
                continue
            for file in sorted(category_dir.glob("*.xlsx")):
                try:
                    self._load_enhanced_workbook(file, category)
                except Exception as exc:
                    raise ValueError(f"增强数据读取失败：{file.name}：{exc}") from exc

    def _load_standard_library(self, directory: Path, module: str) -> None:
        if not directory.exists():
            return
        for category in CATEGORY_PRIORITY:
            category_dir = directory / CATEGORY_LABELS[category]
            if not category_dir.exists():
                continue
            for file in sorted(category_dir.glob("*.xlsx")):
                with pd.ExcelFile(file) as workbook:
                    for sheet in workbook.sheet_names:
                        df = pd.read_excel(workbook, sheet_name=sheet)
                        self._register_standard_sheet(module, category, sheet, df)

    def _register_standard_sheet(
        self,
        module: str,
        category: str,
        sheet: str,
        df: pd.DataFrame,
    ) -> bool:
        price_column = next((column for column in PRICE_COLUMNS if column in df.columns), None)
        if price_column is None or not {"代码", "简称", "时间"}.issubset(df.columns):
            return False
        code = first_text(df["代码"], sheet)
        name = first_text(df["简称"], code)
        series = pd.Series(
            pd.to_numeric(df[price_column], errors="coerce").values,
            index=parse_excel_dates(df["时间"]),
            name=f"{module}:{code}",
        )
        self._register_asset(module, code, name, series, category=category)
        return True

    def _load_enhanced_workbook(self, file: Path, category: str) -> None:
        with pd.ExcelFile(file) as workbook:
            if "净值序列" in workbook.sheet_names:
                nav = pd.read_excel(workbook, sheet_name="净值序列")
                if {"基金简称", "净值日期"}.issubset(nav.columns):
                    value_column = next(
                        (column for column in PRICE_COLUMNS if column in nav.columns),
                        None,
                    )
                    if value_column is not None:
                        for name, group in nav.groupby("基金简称", sort=False):
                            product_name = str(name).strip()
                            if not product_name or product_name.lower() == "nan":
                                continue
                            series = pd.Series(
                                pd.to_numeric(group[value_column], errors="coerce").values,
                                index=parse_excel_dates(group["净值日期"]),
                                name=f"enhanced:{product_name}",
                            )
                            self._register_asset(
                                "enhanced",
                                product_name,
                                product_name,
                                series,
                                category=category,
                            )
                        return

            loaded = 0
            for sheet in workbook.sheet_names:
                if sheet in {"合并长表", "汇总说明", "产品清单"}:
                    continue
                df = pd.read_excel(workbook, sheet_name=sheet)
                if self._register_standard_sheet("enhanced", category, sheet, df):
                    loaded += 1
                    continue

                raw = pd.read_excel(workbook, sheet_name=sheet, header=None)
                header = find_nav_header(raw)
                if header is None:
                    continue
                header_row, date_col, value_col = header
                values = raw.iloc[header_row + 1 :]
                series = pd.Series(
                    pd.to_numeric(values.iloc[:, value_col], errors="coerce").values,
                    index=parse_excel_dates(values.iloc[:, date_col]),
                    name=f"enhanced:{sheet}",
                )
                self._register_asset(
                    "enhanced",
                    sheet,
                    sheet,
                    series,
                    category=category,
                )
                loaded += 1
            if loaded == 0:
                raise ValueError("未识别到可用净值序列")

    def _load_pring(self) -> pd.DataFrame:
        candidates = [STRATEGY_DIR / PRING_FILE_NAME]
        candidates.extend(sorted(ROOT_DIR.rglob(PRING_FILE_NAME)))
        file = next((candidate for candidate in candidates if candidate.exists()), None)
        if file is None:
            raise FileNotFoundError(f"未找到普林格周期判断表: {PRING_FILE_NAME}")

        df = pd.read_excel(file, sheet_name="Sheet1")
        required = ["日期", "Pring_State"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(f"普林格周期判断表缺少字段: {', '.join(missing)}")

        parsed = pd.DataFrame(
            {
                "signal_date": pd.to_datetime(df["日期"], errors="coerce"),
                "state": df["Pring_State"].astype(str).str.strip(),
            }
        )
        if parsed["signal_date"].isna().any():
            bad_rows = (parsed.index[parsed["signal_date"].isna()] + 2).tolist()
            raise ValueError(f"普林格周期判断表存在无效日期，Excel 行号: {bad_rows}")
        if parsed["signal_date"].duplicated().any():
            duplicates = parsed.loc[parsed["signal_date"].duplicated(keep=False), "signal_date"]
            duplicate_text = "、".join(sorted({value.strftime("%Y-%m-%d") for value in duplicates}))
            raise ValueError(f"普林格周期判断表存在重复日期: {duplicate_text}")

        parsed["stage"] = pd.to_numeric(
            parsed["state"].str.extract(r"Stage\s*(\d+)", expand=False),
            errors="coerce",
        )
        invalid_stage = parsed["stage"].isna() | ~parsed["stage"].isin(STAGE_DOMINANT)
        if invalid_stage.any():
            bad_rows = (parsed.index[invalid_stage] + 2).tolist()
            raise ValueError(f"普林格周期判断表存在无法解析或超出 1-8 的 Stage，Excel 行号: {bad_rows}")

        parsed["stage"] = parsed["stage"].astype(int)
        parsed = parsed.sort_values("signal_date").reset_index(drop=True)
        self.pring_source = file.name
        return parsed

    def grouped_assets(self) -> dict[str, Any]:
        self.ensure_loaded()
        groups = {"fund": [], "manager": [], "index": [], "enhanced": []}
        category_rank = {category: index for index, category in enumerate(CATEGORY_PRIORITY)}
        for meta in sorted(
            self.meta.values(),
            key=lambda x: (
                x.module,
                category_rank.get(x.category or "", len(category_rank)),
                x.name,
                x.code,
            ),
        ):
            groups.setdefault(meta.module, []).append(meta.__dict__)
        return {
            "apiVersion": APP_VERSION,
            "groups": groups,
            "defaults": self.default_selection(),
            "defaultBenchmarkId": DEFAULT_BENCHMARK_ID,
            "defaultStageWeights": default_stage_weights(),
            "stageWeightProfiles": stage_weight_profiles(),
            "pring": self.pring_summary(),
        }

    def default_selection(self) -> dict[str, list[str]]:
        code_to_id = {(m.module, m.code): m.id for m in self.meta.values()}
        return {
            "equity": [
                code_to_id.get(("index", "000852.SH")),
                code_to_id.get(("index", "932000.CSI")),
                code_to_id.get(("index", "000300.SH")),
                code_to_id.get(("index", "000905.SH")),
                code_to_id.get(("index", "399006.SZ")),
            ],
            "commodity": [
                code_to_id.get(("index", "NHCI.NH")),
            ],
            "convertible": [code_to_id.get(("index", "931078.CSI"))],
            "pure_bond": [code_to_id.get(("index", "H11001.CSI"))],
        }

    def pring_summary(self) -> dict[str, Any]:
        if self.pring_df is None or self.pring_df.empty:
            return {}
        return {
            "start": self.pring_df["signal_date"].min().strftime("%Y-%m-%d"),
            "end": self.pring_df["signal_date"].max().strftime("%Y-%m-%d"),
            "rows": int(len(self.pring_df)),
            "source": self.pring_source,
        }


store = DataStore()


def first_text(series: pd.Series, fallback: str) -> str:
    vals = series.dropna()
    if vals.empty:
        return str(fallback)
    text = str(vals.iloc[0]).strip()
    return text or str(fallback)


def parse_excel_dates(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    numeric = pd.to_numeric(series, errors="coerce")
    excel_serial = numeric.between(20000, 80000)
    if excel_serial.any():
        parsed = pd.Series(parsed, index=series.index)
        parsed.loc[excel_serial] = (
            pd.Timestamp("1899-12-30")
            + pd.to_timedelta(numeric.loc[excel_serial], unit="D")
        )
    return parsed


def find_nav_header(raw: pd.DataFrame) -> tuple[int, int, int] | None:
    for row_index in range(min(12, len(raw))):
        cells = [str(value).strip() if not pd.isna(value) else "" for value in raw.iloc[row_index]]
        if "净值日期" not in cells:
            continue
        value_column = next(
            (
                cells.index(column)
                for column in PRICE_COLUMNS
                if column in cells
            ),
            None,
        )
        if value_column is not None:
            return row_index, cells.index("净值日期"), value_column
    return None


def text_or_none(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def clean_price_series(series: pd.Series) -> pd.Series:
    s = pd.Series(pd.to_numeric(series.values, errors="coerce"), index=pd.to_datetime(series.index, errors="coerce"))
    s = s[~s.index.isna()].dropna()
    if s.empty:
        return s
    s = s.sort_index()
    s = s[~s.index.duplicated(keep="last")]
    s = s[s > 0]
    return s.astype(float)


def as_float(value: Any, digits: int | None = 6) -> float | None:
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, digits) if digits is not None else f
    except Exception:
        return None


def percentage_label(value: float) -> str:
    return f"{value * 100:.2f}".rstrip("0").rstrip(".")


def metric(nav: pd.Series, name: str) -> dict[str, Any]:
    daily = nav.pct_change().fillna(0)
    total = nav.iloc[-1] - 1
    ann = nav.iloc[-1] ** (252 / len(nav)) - 1 if len(nav) else np.nan
    mdd = (nav / nav.cummax() - 1).min()
    vol = daily.std() * np.sqrt(252)
    sharpe = (ann - 0.02) / vol if vol and not np.isnan(vol) else 0.0
    calmar = ann / abs(mdd) if mdd and not np.isnan(mdd) else 0.0
    return {
        "name": name,
        "totalReturn": as_float(total),
        "annualReturn": as_float(ann),
        "maxDrawdown": as_float(mdd),
        "volatility": as_float(vol),
        "sharpe": as_float(sharpe),
        "calmar": as_float(calmar),
    }


def compounded_return(returns: pd.Series) -> float | None:
    valid = returns.dropna()
    if valid.empty:
        return None
    return as_float((1.0 + valid).prod() - 1.0)


def unique_ids(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for asset_id in ids:
        if asset_id and asset_id not in seen:
            seen.add(asset_id)
            out.append(asset_id)
    return out


def build_category_return(returns: pd.DataFrame, ids: list[str]) -> pd.Series:
    return returns[ids].mean(axis=1)


def build_price_frame(ids: list[str]) -> pd.DataFrame:
    frame = pd.concat([store.assets[asset_id].rename(asset_id) for asset_id in ids], axis=1).sort_index()
    return frame.ffill()


def build_category_returns_from_prices(prices: pd.DataFrame, selected: dict[str, list[str]]) -> dict[str, pd.Series]:
    returns = prices.pct_change(fill_method=None).fillna(0.0)
    return {
        "equity": build_category_return(returns, selected["equity"]),
        "commodity": build_category_return(returns, selected["commodity"]),
        "convertible": build_category_return(returns, selected["convertible"]),
        "pure_bond": build_category_return(returns, selected["pure_bond"]),
    }


def validate_asset_modules(
    selected: dict[str, list[str]],
    allowed_modules: set[str],
    source_name: str,
    module_label: str,
) -> None:
    bad = [
        f"{store.meta[asset_id].name}({store.meta[asset_id].code})"
        for ids in selected.values()
        for asset_id in ids
        if store.meta[asset_id].module not in allowed_modules
    ]
    if bad:
        raise ValueError(f"模拟拼接开启时，{source_name}只能使用{module_label}标的: {'、'.join(bad)}")


def prepare_normal_series(
    selected: dict[str, list[str]],
    all_ids: list[str],
    first_signal_date: pd.Timestamp,
) -> PreparedData:
    raw_prices = build_price_frame(all_ids)
    first_dates = [store.assets[asset_id].index.min() for asset_id in all_ids]
    last_dates = [store.assets[asset_id].index.max() for asset_id in all_ids]
    start_date = max(first_dates + [first_signal_date])
    end_date = min(last_dates)
    prices = raw_prices.loc[(raw_prices.index >= start_date) & (raw_prices.index <= end_date)].dropna(how="any")
    if len(prices) < 40:
        raise ValueError("共同净值区间不足 40 个交易日，无法稳定回测")
    asset_returns = prices.pct_change(fill_method=None).fillna(0.0)
    signal_returns = {
        key: build_category_return(asset_returns, ids)
        for key, ids in selected.items()
    }
    return PreparedData(
        dates=pd.DatetimeIndex(prices.index),
        asset_returns=asset_returns,
        signal_returns=signal_returns,
        raw_prices=raw_prices,
        splice_summary=[],
        splice_context={"enabled": False},
        main_selected=selected,
    )


def prepare_spliced_series(
    selected: dict[str, list[str]],
    splice_selected: dict[str, list[str]],
    first_signal_date: pd.Timestamp,
) -> PreparedData:
    validate_asset_modules(selected, {"fund", "manager"}, "主回测篮子", "基金")
    validate_asset_modules(splice_selected, {"index"}, "拼接模拟池", "指数")

    fund_ids = [asset_id for ids in selected.values() for asset_id in ids]
    index_ids = [asset_id for ids in splice_selected.values() for asset_id in ids]

    fund_common_start = max(store.assets[asset_id].index.min() for asset_id in fund_ids)
    fund_end = min(store.assets[asset_id].index.max() for asset_id in fund_ids)

    index_prices_all = build_price_frame(index_ids)
    fund_prices_all = build_price_frame(fund_ids)

    index_start = max([first_signal_date] + [store.assets[asset_id].index.min() for asset_id in index_ids])
    pre_prices = index_prices_all.loc[
        (index_prices_all.index >= index_start) & (index_prices_all.index < fund_common_start)
    ].dropna(how="any")
    post_prices = fund_prices_all.loc[
        (fund_prices_all.index >= fund_common_start) & (fund_prices_all.index <= fund_end)
    ].dropna(how="any")

    if pre_prices.empty:
        raise ValueError("拼接模拟池没有早于基金共同首日的完整指数数据，无法进行模拟拼接")
    if len(post_prices) < 40:
        raise ValueError("基金共同净值区间不足 40 个交易日，无法稳定回测")

    pre_asset_returns = pre_prices.pct_change(fill_method=None).fillna(0.0)
    post_asset_returns = post_prices.pct_change(fill_method=None).fillna(0.0)
    dates = pd.DatetimeIndex(pre_prices.index.append(post_prices.index))
    return_columns = unique_ids(index_ids + fund_ids)
    asset_returns = pd.DataFrame(0.0, index=dates, columns=return_columns)
    asset_returns.loc[pre_asset_returns.index, index_ids] = pre_asset_returns[index_ids]
    asset_returns.loc[post_asset_returns.index, fund_ids] = post_asset_returns[fund_ids]
    signal_returns = {
        key: pd.concat(
            [
                build_category_return(pre_asset_returns, splice_selected[key]),
                build_category_return(post_asset_returns, selected[key]),
            ]
        ).sort_index()
        for key in selected
    }

    splice_summary = [
        {
            "category": key,
            "categoryName": {"equity": "股票", "commodity": "商品", "convertible": "可转债", "pure_bond": "纯债"}[key],
            "proxyAssets": [store.meta[asset_id].__dict__ for asset_id in ids],
            "applied": True,
        }
        for key, ids in splice_selected.items()
    ]
    switch_date = pd.Timestamp(post_prices.index.min())
    splice_context = {
        "enabled": True,
        "fundCommonStart": fund_common_start.strftime("%Y-%m-%d"),
        "indexStart": pre_prices.index.min().strftime("%Y-%m-%d"),
        "indexEnd": pre_prices.index.max().strftime("%Y-%m-%d"),
        "fundStart": switch_date.strftime("%Y-%m-%d"),
        "mode": "index_before_fund_common_start",
    }
    raw_prices = pd.concat([index_prices_all, fund_prices_all], axis=1).sort_index().ffill()
    if len(dates) < 40:
        raise ValueError("拼接后的共同区间不足 40 个交易日，无法稳定回测")
    return PreparedData(
        dates=dates,
        asset_returns=asset_returns,
        signal_returns=signal_returns,
        raw_prices=raw_prices,
        splice_summary=splice_summary,
        splice_context=splice_context,
        main_selected=selected,
        splice_selected=splice_selected,
        switch_date=switch_date,
    )


def default_stage_weights() -> dict[str, dict[str, float]]:
    return {
        str(stage): dict(weights)
        for stage, weights in DEFAULT_STAGE_WEIGHTS.items()
    }


def build_stage_weight_profile(level: str | int) -> dict[str, dict[str, float]]:
    level_key = str(level)
    if level_key not in STAGE_WEIGHT_PROFILE_SPECS:
        raise ValueError(f"未知股债倾向档位: {level}")
    spec = STAGE_WEIGHT_PROFILE_SPECS[level_key]
    dominant_weight = float(spec["dominantWeight"])
    tilt_category = spec["tiltCategory"]
    tilt_weight = float(spec["tiltWeight"])
    residual = 1.0 - dominant_weight - tilt_weight

    profile: dict[str, dict[str, float]] = {}
    for stage, dominant in STAGE_DOMINANT.items():
        weights = {category: 0.0 for category in CATEGORY_PRIORITY}
        weights[dominant] += dominant_weight
        reserved = {dominant}
        if tilt_category is not None:
            weights[str(tilt_category)] += tilt_weight
            reserved.add(str(tilt_category))
        remaining = [category for category in CATEGORY_PRIORITY if category not in reserved]
        equal_weight = round(residual / len(remaining), 12)
        for category in remaining:
            weights[category] = equal_weight
        profile[str(stage)] = weights
    return profile


def stage_weight_profiles() -> dict[str, dict[str, Any]]:
    return {
        level: {
            "label": spec["label"],
            "shortLabel": spec["shortLabel"],
            "description": spec["description"],
            "weights": build_stage_weight_profile(level),
        }
        for level, spec in STAGE_WEIGHT_PROFILE_SPECS.items()
    }


def parse_stage_weights(payload: Any) -> dict[int, dict[str, float]]:
    if payload in (None, {}):
        return {
            stage: dict(weights)
            for stage, weights in DEFAULT_STAGE_WEIGHTS.items()
        }
    if not isinstance(payload, dict):
        raise ValueError("Stage 权重配置必须为对象")

    try:
        supplied_stages = {int(stage) for stage in payload}
    except (TypeError, ValueError):
        raise ValueError("Stage 权重配置只能包含 Stage 1 至 Stage 8") from None
    expected_stages = set(STAGE_DOMINANT)
    if supplied_stages != expected_stages:
        missing = sorted(expected_stages - supplied_stages)
        extra = sorted(supplied_stages - expected_stages)
        detail = []
        if missing:
            detail.append(f"缺少 Stage {', '.join(map(str, missing))}")
        if extra:
            detail.append(f"存在未知 Stage {', '.join(map(str, extra))}")
        raise ValueError(f"Stage 权重配置不完整：{'；'.join(detail)}")

    parsed: dict[int, dict[str, float]] = {}
    expected_categories = set(CATEGORY_LABELS)
    for stage in STAGE_DOMINANT:
        raw = payload.get(str(stage), payload.get(stage))
        if not isinstance(raw, dict):
            raise ValueError(f"Stage {stage} 缺少四类资产权重配置")
        missing = expected_categories - set(raw)
        extra = set(raw) - expected_categories
        if missing or extra:
            detail = []
            if missing:
                detail.append(f"缺少 {'、'.join(CATEGORY_LABELS[key] for key in missing)}")
            if extra:
                detail.append(f"存在未知字段 {'、'.join(sorted(extra))}")
            raise ValueError(f"Stage {stage} 权重字段无效：{'；'.join(detail)}")

        weights: dict[str, float] = {}
        for category in CATEGORY_LABELS:
            try:
                value = float(raw[category])
            except (TypeError, ValueError):
                raise ValueError(
                    f"Stage {stage} 的{CATEGORY_LABELS[category]}权重必须为数字"
                ) from None
            if not math.isfinite(value) or value < 0 or value > 1:
                raise ValueError(
                    f"Stage {stage} 的{CATEGORY_LABELS[category]}权重必须在 0% 至 100% 之间"
                )
            weights[category] = value

        total = sum(weights.values())
        if not math.isclose(total, 1.0, abs_tol=1e-6):
            raise ValueError(f"Stage {stage} 四类资产权重合计必须为 100%，当前为 {total:.2%}")
        parsed[stage] = weights
    return parsed


def serialize_stage_weights(
    stage_weights: dict[int, dict[str, float]],
) -> dict[str, dict[str, float]]:
    return {
        str(stage): {
            category: as_float(weight, 6) or 0.0
            for category, weight in weights.items()
        }
        for stage, weights in stage_weights.items()
    }


def stage_target_weights(
    stage: int,
    stage_weights: dict[int, dict[str, float]] | None = None,
) -> dict[str, float]:
    if stage not in STAGE_DOMINANT:
        raise ValueError(f"不支持的普林格 Stage: {stage}")
    source = stage_weights or DEFAULT_STAGE_WEIGHTS
    return dict(source[stage])


def dominant_asset_for_stage(
    stage: int,
    stage_weights: dict[int, dict[str, float]] | None = None,
) -> str:
    weights = stage_target_weights(stage, stage_weights)
    return max(CATEGORY_PRIORITY, key=lambda category: weights[category])


def stage_for_date(pring_df: pd.DataFrame, date: pd.Timestamp) -> int:
    eligible = pring_df.loc[pring_df["signal_date"] < date, "stage"]
    if eligible.empty:
        raise ValueError(f"{date.strftime('%Y-%m-%d')} 前没有可用的普林格 Stage")
    return int(eligible.iloc[-1])


def next_trading_date(dates: pd.DatetimeIndex, signal_date: pd.Timestamp) -> pd.Timestamp | None:
    position = dates.searchsorted(pd.Timestamp(signal_date), side="right")
    if position >= len(dates):
        return None
    return pd.Timestamp(dates[position])


def build_rebalance_events(
    pring_df: pd.DataFrame,
    dates: pd.DatetimeIndex,
) -> dict[pd.Timestamp, dict[str, Any]]:
    if dates.empty:
        return {}

    events: dict[pd.Timestamp, dict[str, Any]] = {}
    first_date = pd.Timestamp(dates[0])
    events[first_date] = {
        "type": "initial",
        "stage": stage_for_date(pring_df, first_date),
        "signal_date": None,
    }

    stage_changes = pring_df.loc[pring_df["stage"].ne(pring_df["stage"].shift())].iloc[1:]
    pending_stage_events: list[dict[str, Any]] = []
    for row in stage_changes.itertuples(index=False):
        effective_date = next_trading_date(dates, row.signal_date)
        if effective_date is None or effective_date <= first_date:
            continue
        pending_stage_events.append(
            {
                "effective_date": effective_date,
                "signal_period": pd.Timestamp(row.signal_date).to_period("M"),
                "stage": int(row.stage),
                "signal_date": pd.Timestamp(row.signal_date),
            }
        )

    pending_stage_events.sort(key=lambda item: item["signal_date"])
    anchor_period = first_date.to_period("M")
    anchor_date = first_date
    stage_index = 0
    while True:
        while (
            stage_index < len(pending_stage_events)
            and pending_stage_events[stage_index]["signal_date"] <= anchor_date
        ):
            stage_index += 1

        rebalance_period = anchor_period + 3
        next_stage = pending_stage_events[stage_index] if stage_index < len(pending_stage_events) else None
        if next_stage is not None and next_stage["signal_period"] <= rebalance_period:
            effective_date = next_stage["effective_date"]
            events[effective_date] = {
                "type": "stage_change",
                "stage": next_stage["stage"],
                "signal_date": next_stage["signal_date"],
            }
            anchor_period = next_stage["signal_period"]
            anchor_date = next_stage["signal_date"]
            stage_index += 1
            continue

        rebalance_signal_date = rebalance_period.end_time.normalize()
        effective_date = next_trading_date(dates, rebalance_signal_date)
        if effective_date is None:
            break
        events[effective_date] = {
            "type": "three_month",
            "stage": stage_for_date(pring_df, effective_date),
            "signal_date": rebalance_signal_date,
        }
        anchor_period = rebalance_period
        anchor_date = rebalance_signal_date

    return events


def distribute_value(amount: float, ids: list[str]) -> dict[str, float]:
    if not ids:
        raise ValueError("资产类别没有可分配标的")
    each = amount / len(ids)
    return {asset_id: each for asset_id in ids}


def portfolio_total(main_values: dict[str, float], escape_values: dict[str, float]) -> float:
    return float(sum(main_values.values()) + sum(escape_values.values()))


def category_values(
    main_values: dict[str, float],
    escape_values: dict[str, float],
    active: dict[str, list[str]],
) -> dict[str, float]:
    values = {
        key: float(sum(main_values.get(asset_id, 0.0) for asset_id in ids))
        for key, ids in active.items()
    }
    values["pure_bond"] += float(sum(escape_values.values()))
    return values


def category_weights(
    main_values: dict[str, float],
    escape_values: dict[str, float],
    active: dict[str, list[str]],
) -> dict[str, float]:
    values = category_values(main_values, escape_values, active)
    total = sum(values.values())
    return {key: value / total if total else 0.0 for key, value in values.items()}


def rebalance_values(
    total: float,
    target_weights: dict[str, float],
    active: dict[str, list[str]],
    escaped_category: str | None = None,
) -> tuple[dict[str, float], dict[str, float]]:
    main_values: dict[str, float] = {}
    escape_values: dict[str, float] = {}
    for category, weight in target_weights.items():
        amount = total * weight
        if category == escaped_category:
            for asset_id, value in distribute_value(amount, active["pure_bond"]).items():
                escape_values[asset_id] = escape_values.get(asset_id, 0.0) + value
        else:
            main_values.update(distribute_value(amount, active[category]))
    return main_values, escape_values


def transfer_active_assets(
    main_values: dict[str, float],
    escape_values: dict[str, float],
    previous_active: dict[str, list[str]],
    current_active: dict[str, list[str]],
) -> tuple[dict[str, float], dict[str, float]]:
    transferred: dict[str, float] = {}
    for category, previous_ids in previous_active.items():
        amount = float(sum(main_values.get(asset_id, 0.0) for asset_id in previous_ids))
        transferred.update(distribute_value(amount, current_active[category]))
    escape_total = float(sum(escape_values.values()))
    return transferred, distribute_value(escape_total, current_active["pure_bond"])


def build_long_kst(nav: pd.Series) -> pd.DataFrame:
    result = pd.DataFrame(index=nav.index)
    components: list[pd.Series] = []
    for roc_period, smooth_period, weight in KST_COMPONENTS:
        roc = nav / nav.shift(roc_period) - 1.0
        smoothed = roc.rolling(window=smooth_period, min_periods=smooth_period).mean()
        result[f"roc{roc_period}"] = roc
        result[f"roc{roc_period}Smooth"] = smoothed
        components.append(smoothed * weight)

    kst = components[0]
    for component in components[1:]:
        kst = kst + component
    result["kst"] = kst
    result["signal"] = kst.rolling(window=20, min_periods=20).mean()
    result["slope10"] = kst - kst.shift(10)
    return result


def risk_state_for_date(
    category: str,
    enabled: bool,
    nav: pd.Series,
    ma20: pd.Series,
    kst: pd.DataFrame,
    signal_date: pd.Timestamp | None,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "category": category,
        "targetScale": 1.0,
        "targetWeight": None,
        "ma20Above": None,
        "nav": None,
        "ma20": None,
        "kst": None,
        "kstSignal": None,
        "kstSlope10": None,
        "kstReady": False,
        "kstWeak": None,
        "status": "disabled" if not enabled else "waiting",
    }
    if category not in {"equity", "commodity"} or not enabled or signal_date is None:
        return state

    nav_value = nav.get(signal_date)
    ma20_value = ma20.get(signal_date)
    state["nav"] = as_float(nav_value)
    state["ma20"] = as_float(ma20_value)
    if pd.isna(nav_value) or pd.isna(ma20_value):
        return state

    ma20_above = bool(nav_value >= ma20_value)
    state["ma20Above"] = ma20_above

    kst_value = kst.at[signal_date, "kst"] if signal_date in kst.index else np.nan
    signal_value = kst.at[signal_date, "signal"] if signal_date in kst.index else np.nan
    slope_value = kst.at[signal_date, "slope10"] if signal_date in kst.index else np.nan
    ready = bool(pd.notna(kst_value) and pd.notna(signal_value) and pd.notna(slope_value))
    state.update(
        {
            "kst": as_float(kst_value),
            "kstSignal": as_float(signal_value),
            "kstSlope10": as_float(slope_value),
            "kstReady": ready,
        }
    )
    if ready:
        state["kstWeak"] = bool(kst_value < signal_value and slope_value < 0)
    if ma20_above:
        state["status"] = "ma20_above"
        return state
    if not ready:
        state["targetScale"] = 0.0
        state["status"] = "kst_warmup_exit"
        return state

    weak = bool(state["kstWeak"])
    state["targetScale"] = 0.0 if weak else 4.0 / 7.0
    state["status"] = "ma20_below_kst_weak" if weak else "ma20_below_kst_not_weak"
    return state


def risk_adjusted_weights(
    stage: int,
    risk_state: dict[str, Any],
    stage_weights: dict[int, dict[str, float]] | None = None,
) -> dict[str, float]:
    weights = stage_target_weights(stage, stage_weights)
    dominant = dominant_asset_for_stage(stage, stage_weights)
    if dominant not in {"equity", "commodity"}:
        return weights

    base_weight = weights[dominant]
    target = base_weight * float(risk_state.get("targetScale", 1.0))
    weights[dominant] = target
    weights["pure_bond"] += base_weight - target
    return weights


def calibrate_risk_pair(
    values: dict[str, float],
    dominant: str,
    active: dict[str, list[str]],
    target_weight: float,
) -> float:
    if dominant not in {"equity", "commodity"}:
        return category_weights(values, {}, active)[dominant]

    total = float(sum(values.values()))
    dominant_ids = active[dominant]
    pure_bond_ids = active["pure_bond"]
    pair_total = float(
        sum(values.get(asset_id, 0.0) for asset_id in dominant_ids + pure_bond_ids)
    )
    desired_dominant = min(total * target_weight, pair_total)
    desired_pure_bond = pair_total - desired_dominant

    for asset_id in dominant_ids + pure_bond_ids:
        values.pop(asset_id, None)
    values.update(distribute_value(desired_dominant, dominant_ids))
    values.update(distribute_value(desired_pure_bond, pure_bond_ids))
    return desired_dominant / total if total else 0.0


def apply_returns(
    main_values: dict[str, float],
    escape_values: dict[str, float],
    returns: pd.Series,
) -> None:
    for values in (main_values, escape_values):
        for asset_id in list(values):
            daily_return = float(returns.get(asset_id, 0.0))
            values[asset_id] *= 1.0 + daily_return


def select_backtest_dates(
    prepared_dates: pd.DatetimeIndex,
    first_signal_date: pd.Timestamp,
    date_range_payload: Any,
) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex, dict[str, str | None]]:
    available_dates = prepared_dates[prepared_dates > first_signal_date]
    if available_dates.empty:
        raise ValueError("首条普林格信号生效后没有共同净值区间")

    available_start = pd.Timestamp(available_dates[0])
    available_end = pd.Timestamp(available_dates[-1])
    date_range = date_range_payload if isinstance(date_range_payload, dict) else {}

    def parse_date(key: str, label: str) -> pd.Timestamp | None:
        raw = date_range.get(key)
        if raw in (None, ""):
            return None
        parsed = pd.to_datetime(raw, errors="coerce")
        if pd.isna(parsed):
            raise ValueError(f"{label}格式无效，应为 YYYY-MM-DD")
        return pd.Timestamp(parsed).normalize()

    requested_start = parse_date("start", "指定回测开始日期")
    requested_end = parse_date("end", "指定回测结束日期")
    if requested_start is not None and requested_start < available_start:
        raise ValueError(
            f"指定回测开始日期不能早于共同可用起点 {available_start.strftime('%Y-%m-%d')}"
        )
    if requested_start is not None and requested_start > available_end:
        raise ValueError(
            f"指定回测开始日期不能晚于共同可用终点 {available_end.strftime('%Y-%m-%d')}"
        )
    if requested_end is not None and requested_end > available_end:
        raise ValueError(
            f"指定回测结束日期不能晚于共同可用终点 {available_end.strftime('%Y-%m-%d')}"
        )
    if requested_end is not None and requested_end < available_start:
        raise ValueError(
            f"指定回测结束日期不能早于共同可用起点 {available_start.strftime('%Y-%m-%d')}"
        )
    if requested_start is not None and requested_end is not None and requested_start > requested_end:
        raise ValueError("指定回测开始日期不能晚于结束日期")

    selected_dates = available_dates
    if requested_start is not None:
        selected_dates = selected_dates[selected_dates >= requested_start]
    if requested_end is not None:
        selected_dates = selected_dates[selected_dates <= requested_end]
    if len(selected_dates) < 40:
        raise ValueError("指定回测区间不足 40 个交易日，无法稳定回测")

    return (
        pd.DatetimeIndex(available_dates),
        pd.DatetimeIndex(selected_dates),
        {
            "start": available_start.strftime("%Y-%m-%d"),
            "end": available_end.strftime("%Y-%m-%d"),
            "requestedStart": requested_start.strftime("%Y-%m-%d") if requested_start is not None else None,
            "requestedEnd": requested_end.strftime("%Y-%m-%d") if requested_end is not None else None,
        },
    )


def run_backtest(payload: dict[str, Any]) -> dict[str, Any]:
    store.ensure_loaded()
    if store.pring_df is None:
        raise ValueError("普林格周期判断表尚未加载")

    baskets = payload.get("baskets", {})
    splice_payload = payload.get("spliceSimulation", {})
    splice_enabled = bool(splice_payload.get("enabled")) if isinstance(splice_payload, dict) else False
    splice_baskets_payload = splice_payload.get("baskets", {}) if isinstance(splice_payload, dict) else {}
    equity_ids = unique_ids(baskets.get("equity", []))
    commodity_ids = unique_ids(baskets.get("commodity", []))
    convertible_ids = unique_ids(baskets.get("convertible", []))
    pure_bond_ids = unique_ids(baskets.get("pure_bond", []))
    ma20_controls_payload = payload.get("ma20Controls")
    if isinstance(ma20_controls_payload, dict):
        ma20_controls = {
            "equity": bool(ma20_controls_payload.get("equity", False)),
            "commodity": bool(ma20_controls_payload.get("commodity", False)),
        }
    else:
        legacy_enabled = bool(payload.get("ma20Enabled", True))
        ma20_controls = {"equity": legacy_enabled, "commodity": legacy_enabled}
    ma20_enabled = any(ma20_controls.values())
    stage_weights = parse_stage_weights(payload.get("stageWeights"))
    benchmark_id = str(payload.get("benchmarkId") or DEFAULT_BENCHMARK_ID)
    if benchmark_id not in store.assets:
        raise ValueError(f"对照基准不存在或尚未加载: {benchmark_id}")

    selected = {
        "equity": equity_ids,
        "commodity": commodity_ids,
        "convertible": convertible_ids,
        "pure_bond": pure_bond_ids,
    }
    missing_categories = [CATEGORY_LABELS[k] for k, v in selected.items() if not v]
    if missing_categories:
        raise ValueError(f"以下资产类别至少需要一只标的: {'、'.join(missing_categories)}")

    all_ids = equity_ids + commodity_ids + convertible_ids + pure_bond_ids
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("同一标的不能同时放入多个资产类别")
    unknown = [asset_id for asset_id in all_ids if asset_id not in store.assets]
    if unknown:
        raise ValueError(f"资产不存在或尚未加载: {', '.join(unknown)}")

    first_signal_date = store.pring_df["signal_date"].min()
    if splice_enabled:
        splice_selected = {
            "equity": unique_ids(splice_baskets_payload.get("equity", [])),
            "commodity": unique_ids(splice_baskets_payload.get("commodity", [])),
            "convertible": unique_ids(splice_baskets_payload.get("convertible", [])),
            "pure_bond": unique_ids(splice_baskets_payload.get("pure_bond", [])),
        }
        missing_splice = [CATEGORY_LABELS[k] for k, v in splice_selected.items() if not v]
        if missing_splice:
            raise ValueError(f"模拟拼接开启时，拼接模拟池以下类别至少需要一只指数: {'、'.join(missing_splice)}")
        splice_ids = [asset_id for ids in splice_selected.values() for asset_id in ids]
        if len(splice_ids) != len(set(splice_ids)):
            raise ValueError("同一指数不能同时放入多个拼接资产类别")
        unknown_splice = [asset_id for asset_id in splice_ids if asset_id not in store.assets]
        if unknown_splice:
            raise ValueError(f"拼接模拟池资产不存在或尚未加载: {', '.join(unknown_splice)}")
        prepared = prepare_spliced_series(selected, splice_selected, first_signal_date)
    else:
        prepared = prepare_normal_series(selected, all_ids, first_signal_date)

    all_dates, dates, available_window = select_backtest_dates(
        prepared.dates,
        first_signal_date,
        payload.get("dateRange"),
    )
    if len(all_dates) < 40:
        raise ValueError("首条普林格信号生效后的共同区间不足 40 个交易日，无法稳定回测")
    asset_returns = prepared.asset_returns.reindex(dates).fillna(0.0)
    full_signal_returns = {
        key: values.reindex(all_dates).fillna(0.0)
        for key, values in prepared.signal_returns.items()
    }

    signal_nav = {
        key: (1.0 + values).cumprod()
        for key, values in full_signal_returns.items()
    }
    signal_ma20 = {
        key: values.rolling(window=20).mean()
        for key, values in signal_nav.items()
    }
    signal_kst = {
        key: build_long_kst(signal_nav[key])
        for key in ("equity", "commodity")
    }
    events = build_rebalance_events(store.pring_df, dates)

    strategy_main: dict[str, float] = {}
    strategy_escape: dict[str, float] = {}
    theory_main: dict[str, float] = {}
    theory_escape: dict[str, float] = {}
    current_stage: int | None = None
    current_risk_target = 0.70
    previous_active: dict[str, list[str]] | None = None

    strategy_returns: list[float] = []
    theory_returns: list[float] = []
    strategy_nav_values: list[float] = []
    theory_nav_values: list[float] = []
    rows: list[dict[str, Any]] = []
    trade_logs: list[dict[str, Any]] = []
    weights_history = {"equity": [], "commodity": [], "convertible": [], "pure_bond": []}
    contribution_history = {"equity": [], "commodity": [], "convertible": [], "pure_bond": []}

    def append_trade(
        date: pd.Timestamp,
        rebalance_type: str,
        reason: str,
        stage: int,
        active: dict[str, list[str]],
        prev_date: pd.Timestamp | None,
        signal_date: pd.Timestamp | None = None,
        risk_state: dict[str, Any] | None = None,
        risk_transition: str | None = None,
    ) -> None:
        weights = category_weights(strategy_main, strategy_escape, active)
        dominant = dominant_asset_for_stage(stage, stage_weights)
        risk_state = risk_state or {}
        trade_logs.append(
            {
                "start": date.strftime("%Y-%m-%d"),
                "end": date.strftime("%Y-%m-%d"),
                "days": 1,
                "reason": reason,
                "rebalanceType": rebalance_type,
                "stage": stage,
                "dominantAsset": dominant,
                "signalDate": signal_date.strftime("%Y-%m-%d") if signal_date is not None else None,
                "riskSignalDate": prev_date.strftime("%Y-%m-%d") if prev_date is not None else None,
                "riskTier": as_float(risk_state.get("targetWeight", 0.70), 2),
                "riskTransition": risk_transition,
                "ma20Above": risk_state.get("ma20Above"),
                "kst": risk_state.get("kst"),
                "kstSignal": risk_state.get("kstSignal"),
                "kstSlope10": risk_state.get("kstSlope10"),
                "kstReady": bool(risk_state.get("kstReady", False)),
                "kstWeak": risk_state.get("kstWeak"),
                "equityWeight": as_float(weights["equity"], 6),
                "commodityWeight": as_float(weights["commodity"], 6),
                "convertibleWeight": as_float(weights["convertible"], 6),
                "pureBondWeight": as_float(weights["pure_bond"], 6),
                "equityNav": as_float(signal_nav["equity"].loc[prev_date], 4) if prev_date is not None else None,
                "commodityNav": as_float(signal_nav["commodity"].loc[prev_date], 4) if prev_date is not None else None,
                "convertibleNav": as_float(signal_nav["convertible"].loc[prev_date], 4) if prev_date is not None else None,
                "equityMa20": as_float(signal_ma20["equity"].loc[prev_date], 4) if prev_date is not None else None,
                "commodityMa20": as_float(signal_ma20["commodity"].loc[prev_date], 4) if prev_date is not None else None,
                "convertibleMa20": as_float(signal_ma20["convertible"].loc[prev_date], 4) if prev_date is not None else None,
            }
        )

    def current_risk_state(
        dominant: str,
        prev_date: pd.Timestamp | None,
    ) -> dict[str, Any]:
        if dominant not in {"equity", "commodity"}:
            state = risk_state_for_date(
                dominant,
                False,
                signal_nav["equity"],
                signal_ma20["equity"],
                signal_kst["equity"],
                prev_date,
            )
        else:
            state = risk_state_for_date(
                dominant,
                ma20_controls.get(dominant, False),
                signal_nav[dominant],
                signal_ma20[dominant],
                signal_kst[dominant],
                prev_date,
            )
        base_weight = stage_weights[current_stage][dominant] if current_stage is not None else 0.0
        state["baseWeight"] = base_weight
        state["targetWeight"] = base_weight * float(state.get("targetScale", 1.0))
        return state

    def risk_reason(dominant: str, risk_state: dict[str, Any]) -> str:
        label = CATEGORY_LABELS[dominant]
        status = risk_state["status"]
        target_text = f"{float(risk_state.get('targetWeight', 0.0)):.2%}"
        if status == "ma20_above":
            return f"{label}站在MA20上方，优势仓恢复至{target_text}"
        if status == "kst_warmup_exit":
            return f"{label}跌破MA20，KST尚未形成，优势仓直接降至0%"
        if status == "ma20_below_kst_weak":
            return f"{label}跌破MA20且KST低于Signal、10日斜率为负，优势仓降至0%"
        if status == "ma20_below_kst_not_weak":
            return f"{label}跌破MA20但KST未同步转弱，优势仓按基础比例的4/7降至{target_text}"
        return f"{label}分级风控关闭，优势仓维持{target_text}"

    for i, d in enumerate(dates):
        d = pd.Timestamp(d)
        all_date_position = all_dates.searchsorted(d)
        prev_date = pd.Timestamp(all_dates[all_date_position - 1]) if all_date_position > 0 else None
        active = prepared.active_assets(d)
        switched = previous_active is not None and active != previous_active

        if switched and previous_active is not None:
            strategy_main, strategy_escape = transfer_active_assets(
                strategy_main, strategy_escape, previous_active, active
            )
            theory_main, theory_escape = transfer_active_assets(
                theory_main, theory_escape, previous_active, active
            )

        event = events.get(d)
        previous_stage = current_stage
        if event is not None:
            current_stage = int(event["stage"])
            dominant = dominant_asset_for_stage(current_stage, stage_weights)
            risk_state = current_risk_state(dominant, prev_date)
            targets = risk_adjusted_weights(current_stage, risk_state, stage_weights)
            strategy_total = portfolio_total(strategy_main, strategy_escape) or 1.0
            theory_total = portfolio_total(theory_main, theory_escape) or 1.0
            strategy_main, strategy_escape = rebalance_values(
                strategy_total,
                targets,
                active,
            )
            theory_main, theory_escape = rebalance_values(
                theory_total,
                stage_target_weights(current_stage, stage_weights),
                active,
            )
            current_risk_target = float(risk_state["targetWeight"])

            if event["type"] == "initial":
                reason = f"初始建仓：Stage {current_stage}，重仓{CATEGORY_LABELS[dominant]}"
            elif event["type"] == "stage_change":
                reason = (
                    f"月度 Stage 变化：Stage {previous_stage} → Stage {current_stage}，"
                    f"重仓{CATEGORY_LABELS[dominant]}"
                )
            else:
                reason = f"连续3个月未进行策略调仓，执行再平衡：Stage {current_stage}，重仓{CATEGORY_LABELS[dominant]}"
            if switched:
                reason += " + 模拟拼接切换至基金"
            if dominant in {"equity", "commodity"} and ma20_controls.get(dominant, False):
                reason += f" + {risk_reason(dominant, risk_state)}"
            append_trade(
                d,
                event["type"],
                reason,
                current_stage,
                active,
                prev_date,
                event.get("signal_date"),
                risk_state,
            )
        else:
            if current_stage is None:
                current_stage = stage_for_date(store.pring_df, d)
            dominant = dominant_asset_for_stage(current_stage, stage_weights)
            risk_state = current_risk_state(dominant, prev_date)
            if switched:
                append_trade(
                    d,
                    "splice_switch",
                    "模拟拼接切换至基金，保留四类资产市值并恢复类别内等权",
                    current_stage,
                    active,
                    prev_date,
                    risk_state=risk_state,
                )

            next_risk_target = float(risk_state["targetWeight"])
            if (
                dominant in {"equity", "commodity"}
                and ma20_controls.get(dominant, False)
                and not math.isclose(next_risk_target, current_risk_target, abs_tol=1e-12)
            ):
                previous_target = current_risk_target
                applied_target = calibrate_risk_pair(
                    strategy_main,
                    dominant,
                    active,
                    next_risk_target,
                )
                current_risk_target = next_risk_target
                transition = (
                    f"{percentage_label(previous_target)}→"
                    f"{percentage_label(next_risk_target)}"
                )
                reason = risk_reason(dominant, risk_state)
                if not math.isclose(applied_target, next_risk_target, abs_tol=1e-8):
                    reason += f"；受优势资产与纯债可用市值约束，实际校准至{applied_target:.1%}"
                append_trade(
                    d,
                    "risk_tier",
                    reason,
                    current_stage,
                    active,
                    prev_date,
                    risk_state=risk_state,
                    risk_transition=transition,
                )

        strategy_start = portfolio_total(strategy_main, strategy_escape)
        theory_start = portfolio_total(theory_main, theory_escape)
        category_start = category_values(strategy_main, strategy_escape, active)

        returns_today = asset_returns.loc[d]
        apply_returns(strategy_main, strategy_escape, returns_today)
        apply_returns(theory_main, theory_escape, returns_today)

        strategy_end = portfolio_total(strategy_main, strategy_escape)
        theory_end = portfolio_total(theory_main, theory_escape)
        category_end = category_values(strategy_main, strategy_escape, active)
        day_strategy_return = strategy_end / strategy_start - 1.0 if strategy_start else 0.0
        day_theory_return = theory_end / theory_start - 1.0 if theory_start else 0.0
        strategy_returns.append(float(day_strategy_return))
        theory_returns.append(float(day_theory_return))
        strategy_nav_values.append(strategy_end)
        theory_nav_values.append(theory_end)

        for key in contribution_history:
            contribution_history[key].append(
                (category_end[key] - category_start[key]) / strategy_start if strategy_start else 0.0
            )

        weights = category_weights(strategy_main, strategy_escape, active)
        for key in weights_history:
            weights_history[key].append(weights[key])

        rows.append(
            {
                "date": d.strftime("%Y-%m-%d"),
                "equityWeight": as_float(weights["equity"], 6),
                "commodityWeight": as_float(weights["commodity"], 6),
                "convertibleWeight": as_float(weights["convertible"], 6),
                "pureBondWeight": as_float(weights["pure_bond"], 6),
                "riskTier": as_float(current_risk_target, 2),
                "ma20Above": risk_state.get("ma20Above"),
                "kstWeak": risk_state.get("kstWeak"),
                "stage": current_stage,
                "dominantAsset": dominant,
            }
        )
        previous_active = active

    strategy_ret = pd.Series(strategy_returns, index=dates)
    theory_ret = pd.Series(theory_returns, index=dates)
    nav_strategy = pd.Series(strategy_nav_values, index=dates)
    nav_theory = pd.Series(theory_nav_values, index=dates)

    nav_benchmark, benchmark_ret, benchmark_meta = build_benchmark_comparison(
        benchmark_id,
        dates,
    )

    df_daily = pd.DataFrame(
        {
            "Eq": pd.Series(contribution_history["equity"], index=dates),
            "Com": pd.Series(contribution_history["commodity"], index=dates),
            "Cb": pd.Series(contribution_history["convertible"], index=dates),
            "Cdb": pd.Series(contribution_history["pure_bond"], index=dates),
            "Strat": strategy_ret,
            "Benchmark": benchmark_ret,
        }
    )
    df_daily["Prev_NAV"] = nav_strategy.shift(1).fillna(1.0)
    df_daily["Year"] = df_daily.index.year

    annual = build_annual_attribution(df_daily)
    stage_attribution = build_stage_attribution(
        dates=dates,
        stages=pd.Series([row["stage"] for row in rows], index=dates),
        category_returns={
            category: returns.reindex(dates).fillna(0.0)
            for category, returns in full_signal_returns.items()
        },
        df_daily=df_daily,
        trade_logs=trade_logs,
        pring_df=store.pring_df,
        stage_weights=stage_weights,
    )
    year_stage_attribution = build_stage_attribution(
        dates=dates,
        stages=pd.Series([row["stage"] for row in rows], index=dates),
        category_returns={
            category: returns.reindex(dates).fillna(0.0)
            for category, returns in full_signal_returns.items()
        },
        df_daily=df_daily,
        trade_logs=trade_logs,
        pring_df=store.pring_df,
        stage_weights=stage_weights,
        split_by_year=True,
    )
    contribution = build_contribution_summary(df_daily)
    efficiency = build_efficiency(weights_history, contribution, dates)
    risk_diagnostics = [
        {
            "date": log["start"],
            "asset": log["dominantAsset"],
            "transition": log["riskTransition"],
            "riskTier": log["riskTier"],
            "signalDate": log["riskSignalDate"],
            "ma20Above": log["ma20Above"],
            "kst": log["kst"],
            "kstSignal": log["kstSignal"],
            "kstSlope10": log["kstSlope10"],
            "kstReady": log["kstReady"],
            "kstWeak": log["kstWeak"],
            "reason": log["reason"],
        }
        for log in trade_logs
        if log["rebalanceType"] == "risk_tier"
    ]

    drawdown_strategy = nav_strategy / nav_strategy.cummax() - 1
    drawdown_benchmark = nav_benchmark / nav_benchmark.cummax() - 1 if nav_benchmark.notna().any() else nav_benchmark

    for row, d in zip(rows, dates):
        row.update(
            {
                "strategy": as_float(nav_strategy.loc[d]),
                "theory": as_float(nav_theory.loc[d]),
                "benchmark": as_float(nav_benchmark.loc[d]) if d in nav_benchmark.index else None,
                "drawdown": as_float(drawdown_strategy.loc[d]),
                "benchmarkDrawdown": as_float(drawdown_benchmark.loc[d]) if d in drawdown_benchmark.index else None,
            }
        )

    selected_assets = {
        key: [store.meta[asset_id].__dict__ for asset_id in ids]
        for key, ids in selected.items()
    }
    stage_rebalance_count = sum(log["rebalanceType"] == "stage_change" for log in trade_logs)
    three_month_rebalance_count = sum(log["rebalanceType"] == "three_month" for log in trade_logs)
    risk_action_count = sum(log["rebalanceType"] == "risk_tier" for log in trade_logs)

    return {
        "window": {
            "start": dates[0].strftime("%Y-%m-%d"),
            "end": dates[-1].strftime("%Y-%m-%d"),
            "days": int(len(dates)),
            "firstSignalDate": first_signal_date.strftime("%Y-%m-%d"),
        },
        "availableWindow": available_window,
        "ma20Enabled": ma20_enabled,
        "ma20Controls": ma20_controls,
        "stageWeights": serialize_stage_weights(stage_weights),
        "metrics": [
            metric(nav_strategy, "策略实盘版"),
            metric(nav_theory, "理论无风控"),
            metric(nav_benchmark.dropna(), f"{benchmark_meta['name']}基准"),
        ],
        "benchmark": benchmark_meta,
        "series": rows,
        "tradeLogs": trade_logs,
        "rebalanceStats": {
            "strategyTotal": stage_rebalance_count + three_month_rebalance_count,
            "stageChanges": stage_rebalance_count,
            "threeMonth": three_month_rebalance_count,
            "initialBuild": 1 if trade_logs else 0,
            "riskActions": risk_action_count,
            "ma20Actions": risk_action_count,
        },
        "annualAttribution": annual,
        "stageAttribution": stage_attribution,
        "yearStageAttribution": year_stage_attribution,
        "contributionSummary": contribution,
        "efficiency": efficiency,
        "riskDiagnostics": risk_diagnostics,
        "selectedAssets": selected_assets,
        "spliceSummary": prepared.splice_summary,
        "spliceContext": prepared.splice_context,
    }


def build_benchmark_comparison(
    benchmark_id: str,
    dates: pd.DatetimeIndex,
) -> tuple[pd.Series, pd.Series, dict[str, Any]]:
    source = store.assets[benchmark_id]
    meta = store.meta[benchmark_id]
    eligible_dates = dates[
        (dates >= pd.Timestamp(source.index.min()))
        & (dates <= pd.Timestamp(source.index.max()))
    ]
    if eligible_dates.empty:
        raise ValueError(
            f"对照基准“{meta.name}”与当前回测区间没有重叠数据"
        )

    prices = (
        source.reindex(source.index.union(eligible_dates))
        .sort_index()
        .ffill()
        .reindex(eligible_dates)
        .dropna()
    )
    if len(prices) < 2:
        raise ValueError(
            f"对照基准“{meta.name}”与当前回测区间的重叠数据不足 2 个交易日"
        )

    comparison_nav = prices / float(prices.iloc[0])
    nav = pd.Series(np.nan, index=dates, dtype=float)
    nav.loc[comparison_nav.index] = comparison_nav.values
    daily_returns = nav.pct_change(fill_method=None)
    daily_returns.loc[comparison_nav.index[0]] = 0.0

    comparison_start = pd.Timestamp(comparison_nav.index[0])
    comparison_end = pd.Timestamp(comparison_nav.index[-1])
    benchmark_meta = {
        **meta.__dict__,
        "comparisonStart": comparison_start.strftime("%Y-%m-%d"),
        "comparisonEnd": comparison_end.strftime("%Y-%m-%d"),
        "comparisonDays": int(len(comparison_nav)),
        "partial": bool(
            comparison_start > pd.Timestamp(dates[0])
            or comparison_end < pd.Timestamp(dates[-1])
        ),
    }
    return nav, daily_returns, benchmark_meta


def build_annual_attribution(df_daily: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for year, group in df_daily.groupby("Year"):
        start_nav = group["Prev_NAV"].iloc[0]
        rows.append(
            {
                "year": str(year),
                "strategy": as_float((1 + group["Strat"]).prod() - 1),
                "benchmark": compounded_return(group["Benchmark"]),
                "equity": as_float((group["Eq"] * group["Prev_NAV"]).sum() / start_nav),
                "commodity": as_float((group["Com"] * group["Prev_NAV"]).sum() / start_nav),
                "convertible": as_float((group["Cb"] * group["Prev_NAV"]).sum() / start_nav),
                "pureBond": as_float((group["Cdb"] * group["Prev_NAV"]).sum() / start_nav),
            }
        )
    return rows


def build_stage_attribution(
    dates: pd.DatetimeIndex,
    stages: pd.Series,
    category_returns: dict[str, pd.Series],
    df_daily: pd.DataFrame,
    trade_logs: list[dict[str, Any]],
    pring_df: pd.DataFrame,
    stage_weights: dict[int, dict[str, float]],
    split_by_year: bool = False,
) -> list[dict[str, Any]]:
    if dates.empty:
        return []

    pring = pring_df.sort_values("signal_date").reset_index(drop=True).copy()
    pring["runId"] = pring["stage"].ne(pring["stage"].shift()).cumsum()
    log_rows = [
        {**log, "_date": pd.Timestamp(log["start"])}
        for log in trade_logs
    ]
    stage_series = stages.reindex(dates).astype(int)
    segment_breaks = stage_series.ne(stage_series.shift())
    if split_by_year:
        years = pd.Series(stage_series.index.year, index=stage_series.index)
        segment_breaks |= years.ne(years.shift())
    run_ids = segment_breaks.cumsum()
    contribution_columns = {
        "equity": "Eq",
        "commodity": "Com",
        "convertible": "Cb",
        "pure_bond": "Cdb",
    }

    rows: list[dict[str, Any]] = []
    for _, segment_stages in stage_series.groupby(run_ids):
        segment_dates = pd.DatetimeIndex(segment_stages.index)
        start = pd.Timestamp(segment_dates[0])
        end = pd.Timestamp(segment_dates[-1])
        stage = int(segment_stages.iloc[0])
        dominant = dominant_asset_for_stage(stage, stage_weights)
        segment_daily = df_daily.loc[segment_dates]
        segment_start_nav = float(segment_daily["Prev_NAV"].iloc[0])

        eligible_signals = pring.loc[pring["signal_date"] < start]
        if eligible_signals.empty:
            signal_start = None
            signal_end = None
            consecutive_months = 0
        else:
            active_signal = eligible_signals.iloc[-1]
            run = pring.loc[pring["runId"] == active_signal["runId"]]
            if split_by_year:
                observed_run = run.loc[
                    (run["signal_date"] >= active_signal["signal_date"])
                    & (run["signal_date"] <= end)
                ]
                signal_start = pd.Timestamp(active_signal["signal_date"])
            else:
                observed_run = run.loc[run["signal_date"] <= end]
                signal_start = pd.Timestamp(run["signal_date"].iloc[0])
            signal_end = (
                pd.Timestamp(observed_run["signal_date"].iloc[-1])
                if not observed_run.empty
                else signal_start
            )
            consecutive_months = int(len(observed_run))

        segment_logs = [
            log for log in log_rows
            if start <= log["_date"] <= end
        ]
        stage_changes = sum(log["rebalanceType"] == "stage_change" for log in segment_logs)
        three_month = sum(log["rebalanceType"] == "three_month" for log in segment_logs)
        risk_actions = sum(log["rebalanceType"] == "risk_tier" for log in segment_logs)

        row: dict[str, Any] = {
            "period": f"{start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}",
            "start": start.strftime("%Y-%m-%d"),
            "end": end.strftime("%Y-%m-%d"),
            "signalStartDate": signal_start.strftime("%Y-%m-%d") if signal_start is not None else None,
            "signalEndDate": signal_end.strftime("%Y-%m-%d") if signal_end is not None else None,
            "stage": stage,
            "dominantAsset": dominant,
            "dominantWeight": as_float(stage_weights[stage][dominant]),
            "consecutiveMonths": consecutive_months,
            "tradingDays": int(len(segment_dates)),
            "strategyReturn": as_float((1.0 + segment_daily["Strat"]).prod() - 1.0),
            "benchmarkReturn": compounded_return(segment_daily["Benchmark"]),
            "stageChanges": stage_changes,
            "threeMonthRebalances": three_month,
            "strategyRebalances": stage_changes + three_month,
            "riskActions": risk_actions,
        }
        engine_returns: dict[str, float] = {}
        for category in CATEGORY_PRIORITY:
            engine_return = (
                (1.0 + category_returns[category].reindex(segment_dates).fillna(0.0)).prod()
                - 1.0
            )
            engine_returns[category] = float(engine_return)
            contribution = (
                segment_daily[contribution_columns[category]]
                * segment_daily["Prev_NAV"]
            ).sum() / segment_start_nav
            row[f"{category}Return"] = as_float(engine_return)
            row[f"{category}Contribution"] = as_float(contribution)

        ranked_assets = sorted(
            CATEGORY_PRIORITY,
            key=lambda category: (
                -engine_returns[category],
                CATEGORY_PRIORITY.index(category),
            ),
        )
        row["dominantRank"] = ranked_assets.index(dominant) + 1
        rows.append(row)
    return rows


def build_contribution_summary(df_daily: pd.DataFrame) -> dict[str, Any]:
    points = {
        "equity": (df_daily["Eq"] * df_daily["Prev_NAV"]).cumsum(),
        "commodity": (df_daily["Com"] * df_daily["Prev_NAV"]).cumsum(),
        "convertible": (df_daily["Cb"] * df_daily["Prev_NAV"]).cumsum(),
        "pureBond": (df_daily["Cdb"] * df_daily["Prev_NAV"]).cumsum(),
    }
    final = {key: float(value.iloc[-1]) for key, value in points.items()}
    total = sum(final.values())
    return {
        "totalPoints": as_float(total),
        "items": [
            {"key": key, "points": as_float(val), "share": as_float(val / total if total else 0)}
            for key, val in final.items()
        ],
        "series": [
            {
                "date": idx.strftime("%Y-%m-%d"),
                "equity": as_float(points["equity"].loc[idx]),
                "commodity": as_float(points["commodity"].loc[idx]),
                "convertible": as_float(points["convertible"].loc[idx]),
                "pureBond": as_float(points["pureBond"].loc[idx]),
            }
            for idx in df_daily.index
        ],
    }


def build_efficiency(weights_history: dict[str, list[float]], contribution: dict[str, Any], dates: pd.Index) -> list[dict[str, Any]]:
    total_days = len(dates)
    final_points = {item["key"]: item["points"] or 0 for item in contribution["items"]}
    total_profit = sum(final_points.values())
    total_weight_sum = sum(sum(v) for v in weights_history.values()) or 1
    rows: list[dict[str, Any]] = []
    for key, weights in weights_history.items():
        weights_array = np.array(weights, dtype=float)
        capital_share = float(weights_array.sum() / total_weight_sum)
        profit_share = float(final_points.get(key, 0) / total_profit) if total_profit else 0.0
        rows.append(
            {
                "key": key,
                "activeDays": int((weights_array > 0).sum()),
                "timeShare": as_float((weights_array > 0).sum() / total_days),
                "avgWeight": as_float(weights_array.mean()),
                "capitalShare": as_float(capital_share),
                "profitShare": as_float(profit_share),
                "efficiency": as_float(profit_share / capital_share if capital_share else 0),
            }
        )
    return rows


class ApiError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class StrategyStore:
    SCHEMA_VERSION = 1

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()

    def _empty(self) -> dict[str, Any]:
        return {"schemaVersion": self.SCHEMA_VERSION, "strategies": [], "tags": []}

    def _read_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ApiError(
                f"策略数据文件无法读取，已停止写入以保护原文件：{exc}",
                status=500,
            ) from exc
        if (
            not isinstance(data, dict)
            or data.get("schemaVersion") != self.SCHEMA_VERSION
            or not isinstance(data.get("strategies"), list)
            or not isinstance(data.get("tags"), list)
        ):
            raise ApiError("策略数据文件格式或版本无效，已停止写入", status=500)
        return data

    def _write_unlocked(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temp_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            os.replace(temp_path, self.path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _tag_map(self, data: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {tag["id"]: tag for tag in data["tags"]}

    def _strategy_map(self, data: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {strategy["id"]: strategy for strategy in data["strategies"]}

    def _tag_depth(
        self,
        tag_id: str,
        tags: dict[str, dict[str, Any]],
        seen: set[str] | None = None,
    ) -> int:
        seen = set() if seen is None else seen
        if tag_id in seen:
            raise ApiError("标签树存在循环引用")
        seen.add(tag_id)
        tag = tags.get(tag_id)
        if tag is None:
            raise ApiError("标签不存在", status=404)
        parent_id = tag.get("parentId")
        return 1 if not parent_id else 1 + self._tag_depth(parent_id, tags, seen)

    def _tag_path(
        self,
        tag_id: str,
        tags: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        path: list[dict[str, Any]] = []
        current_id: str | None = tag_id
        seen: set[str] = set()
        while current_id:
            if current_id in seen:
                raise ApiError("标签树存在循环引用")
            seen.add(current_id)
            tag = tags.get(current_id)
            if tag is None:
                break
            path.append(tag)
            current_id = tag.get("parentId")
        return list(reversed(path))

    def _descendants(
        self,
        tag_id: str,
        tags: dict[str, dict[str, Any]],
    ) -> set[str]:
        found = {tag_id}
        changed = True
        while changed:
            changed = False
            for candidate in tags.values():
                if candidate.get("parentId") in found and candidate["id"] not in found:
                    found.add(candidate["id"])
                    changed = True
        return found

    def _validate_sibling_name(
        self,
        name: str,
        parent_id: str | None,
        tags: dict[str, dict[str, Any]],
        exclude_id: str | None = None,
    ) -> None:
        folded = name.casefold()
        for tag in tags.values():
            if (
                tag["id"] != exclude_id
                and tag.get("parentId") == parent_id
                and str(tag.get("name", "")).casefold() == folded
            ):
                raise ApiError("同一级标签名称不可重复", status=409)

    def _validate_strategy_name(
        self,
        name: Any,
        strategies: list[dict[str, Any]],
        exclude_id: str | None = None,
    ) -> str:
        clean = str(name or "").strip()
        if not clean:
            raise ApiError("请输入策略名")
        if len(clean) > 120:
            raise ApiError("策略名不能超过 120 个字符")
        folded = clean.casefold()
        if any(
            item["id"] != exclude_id
            and str(item.get("name", "")).casefold() == folded
            for item in strategies
        ):
            raise ApiError("策略名已存在", status=409)
        return clean

    def _normalize_notes(self, value: Any) -> str:
        notes = str(value or "").strip()
        if len(notes) > 2000:
            raise ApiError("备注不能超过 2000 个字符")
        return notes

    def _normalize_tag_ids(
        self,
        tag_ids: Any,
        tags: dict[str, dict[str, Any]],
        require_active: bool,
        allowed_inactive_ids: set[str] | None = None,
    ) -> list[str]:
        if not isinstance(tag_ids, list):
            raise ApiError("标签必须为数组")
        unique: list[str] = []
        for raw_id in tag_ids:
            tag_id = str(raw_id)
            tag = tags.get(tag_id)
            if tag is None:
                raise ApiError(f"标签不存在：{tag_id}")
            if (
                require_active
                and not tag.get("active", True)
                and tag_id not in (allowed_inactive_ids or set())
            ):
                raise ApiError(f"标签已停用：{tag['name']}")
            if tag_id not in unique:
                unique.append(tag_id)
        selected = set(unique)
        return [
            tag_id
            for tag_id in unique
            if not any(
                tag_id in {
                    ancestor["id"]
                    for ancestor in self._tag_path(other_id, tags)[:-1]
                }
                for other_id in selected
                if other_id != tag_id
            )
        ]

    def _normalize_config(self, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise ApiError("策略配置无效")
        baskets_payload = raw.get("baskets", {})
        splice_payload = raw.get("spliceSimulation", {})
        if not isinstance(baskets_payload, dict) or not isinstance(splice_payload, dict):
            raise ApiError("资产篮子配置无效")

        baskets = {
            category: unique_ids(baskets_payload.get(category, []))
            for category in CATEGORY_LABELS
        }
        splice_baskets_payload = splice_payload.get("baskets", {})
        if not isinstance(splice_baskets_payload, dict):
            raise ApiError("拼接模拟资产篮子配置无效")
        splice_baskets = {
            category: unique_ids(splice_baskets_payload.get(category, []))
            for category in CATEGORY_LABELS
        }
        controls = raw.get("ma20Controls", {})
        if not isinstance(controls, dict):
            controls = {}
        date_range = raw.get("dateRange", {})
        if not isinstance(date_range, dict):
            date_range = {}
        parsed_weights = parse_stage_weights(raw.get("stageWeights"))
        serialized_weights = {
            str(stage): {category: float(weight) for category, weight in weights.items()}
            for stage, weights in parsed_weights.items()
        }
        profile = self._detect_stage_profile(serialized_weights)
        requested_profile = str(raw.get("stageWeightProfile") or "")
        if requested_profile in STAGE_WEIGHT_PROFILE_SPECS and profile == requested_profile:
            profile = requested_profile
        return {
            "baskets": baskets,
            "benchmarkId": str(raw.get("benchmarkId") or DEFAULT_BENCHMARK_ID),
            "spliceSimulation": {
                "enabled": bool(splice_payload.get("enabled")),
                "baskets": splice_baskets,
            },
            "ma20Controls": {
                "equity": bool(controls.get("equity")),
                "commodity": bool(controls.get("commodity")),
            },
            "dateRange": {
                "start": str(date_range.get("start") or ""),
                "end": str(date_range.get("end") or ""),
            },
            "stageWeights": serialized_weights,
            "stageWeightProfile": profile or "custom",
        }

    def _detect_stage_profile(self, weights: dict[str, dict[str, float]]) -> str | None:
        for level in STAGE_WEIGHT_PROFILE_SPECS:
            expected = build_stage_weight_profile(level)
            if all(
                abs(weights[str(stage)][category] - expected[str(stage)][category]) < 1e-9
                for stage in STAGE_DOMINANT
                for category in CATEGORY_LABELS
            ):
                return level
        return None

    def _asset_ids(self, config: dict[str, Any]) -> list[str]:
        ids: list[str] = []
        for category in CATEGORY_LABELS:
            ids.extend(config["baskets"].get(category, []))
            if config["spliceSimulation"]["enabled"]:
                ids.extend(config["spliceSimulation"]["baskets"].get(category, []))
        return list(dict.fromkeys(ids))

    def _asset_snapshots(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        store.ensure_loaded()
        snapshots: list[dict[str, Any]] = []
        missing: list[str] = []
        for asset_id in self._asset_ids(config):
            meta = store.meta.get(asset_id)
            if meta is None:
                missing.append(asset_id)
                continue
            snapshots.append(
                {
                    "id": meta.id,
                    "code": meta.code,
                    "name": meta.name,
                    "module": meta.module,
                    "category": meta.category,
                }
            )
        if missing:
            raise ApiError(f"以下资产已失效：{', '.join(missing)}")
        benchmark_id = config.get("benchmarkId") or DEFAULT_BENCHMARK_ID
        if benchmark_id not in store.meta:
            raise ApiError(f"对照基准已失效：{benchmark_id}")
        return snapshots

    def _summary(self, result: dict[str, Any]) -> dict[str, Any]:
        metrics = [metric for metric in result.get("metrics", []) if metric]
        if not metrics:
            raise ApiError("回测结果缺少核心指标")
        metric = metrics[0]
        return {
            "runAt": utc_now(),
            "window": deepcopy(result.get("window", {})),
            "totalReturn": metric.get("totalReturn"),
            "annualReturn": metric.get("annualReturn"),
            "maxDrawdown": metric.get("maxDrawdown"),
            "sharpe": metric.get("sharpe"),
        }

    def _run_and_snapshot(
        self,
        raw_config: Any,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
        config = self._normalize_config(raw_config)
        snapshots = self._asset_snapshots(config)
        try:
            result = run_backtest(config)
        except ApiError:
            raise
        except Exception as exc:
            raise ApiError(str(exc)) from exc
        return config, snapshots, self._summary(result)

    def _serialize(self, data: dict[str, Any]) -> dict[str, Any]:
        tags = self._tag_map(data)
        serialized_tags: list[dict[str, Any]] = []
        for tag in data["tags"]:
            path = self._tag_path(tag["id"], tags)
            serialized_tags.append(
                {
                    **deepcopy(tag),
                    "depth": len(path),
                    "pathIds": [item["id"] for item in path],
                    "pathNames": [item["name"] for item in path],
                    "path": " / ".join(item["name"] for item in path),
                }
            )

        store.ensure_loaded()
        serialized_strategies: list[dict[str, Any]] = []
        for strategy in data["strategies"]:
            serialized_strategy = deepcopy(strategy)
            serialized_strategy.setdefault("config", {})
            benchmark_id = str(
                serialized_strategy["config"].get("benchmarkId")
                or DEFAULT_BENCHMARK_ID
            )
            serialized_strategy["config"]["benchmarkId"] = benchmark_id
            missing_ids = [
                asset_id
                for asset_id in self._asset_ids(serialized_strategy["config"])
                if asset_id not in store.meta
            ]
            snapshot_map = {
                item["id"]: item for item in strategy.get("assetSnapshots", [])
            }
            missing_assets = [
                snapshot_map.get(
                    asset_id,
                    {"id": asset_id, "code": asset_id, "name": asset_id},
                )
                for asset_id in missing_ids
            ]
            tag_paths = []
            for tag_id in strategy.get("tagIds", []):
                if tag_id not in tags:
                    continue
                path = self._tag_path(tag_id, tags)
                tag_paths.append(
                    {
                        "id": tag_id,
                        "pathIds": [item["id"] for item in path],
                        "pathNames": [item["name"] for item in path],
                        "path": " / ".join(item["name"] for item in path),
                        "active": bool(tags[tag_id].get("active", True)),
                    }
                )
            serialized_strategies.append(
                {
                    **serialized_strategy,
                    "tagPaths": tag_paths,
                    "missingAssets": missing_assets,
                    "missingBenchmark": (
                        None
                        if benchmark_id in store.meta
                        else {"id": benchmark_id}
                    ),
                    "assetCount": len(self._asset_ids(serialized_strategy["config"])),
                }
            )
        serialized_strategies.sort(key=lambda item: item["updatedAt"], reverse=True)
        return {
            "schemaVersion": self.SCHEMA_VERSION,
            "strategies": serialized_strategies,
            "tags": serialized_tags,
        }

    def list_all(self) -> dict[str, Any]:
        with self.lock:
            return self._serialize(self._read_unlocked())

    def create_strategy(self, payload: dict[str, Any]) -> dict[str, Any]:
        config, snapshots, summary = self._run_and_snapshot(payload.get("config"))
        with self.lock:
            data = self._read_unlocked()
            tags = self._tag_map(data)
            name = self._validate_strategy_name(payload.get("name"), data["strategies"])
            now = utc_now()
            strategy = {
                "id": uuid.uuid4().hex,
                "name": name,
                "notes": self._normalize_notes(payload.get("notes")),
                "tagIds": self._normalize_tag_ids(payload.get("tagIds", []), tags, True),
                "createdAt": now,
                "updatedAt": now,
                "config": config,
                "assetSnapshots": snapshots,
                "summary": summary,
            }
            data["strategies"].append(strategy)
            self._write_unlocked(data)
            return next(
                item
                for item in self._serialize(data)["strategies"]
                if item["id"] == strategy["id"]
            )

    def update_strategy(self, strategy_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        config, snapshots, summary = self._run_and_snapshot(payload.get("config"))
        with self.lock:
            data = self._read_unlocked()
            strategy = self._strategy_map(data).get(strategy_id)
            if strategy is None:
                raise ApiError("策略不存在", status=404)
            tags = self._tag_map(data)
            requested_tag_ids = payload.get("tagIds", strategy.get("tagIds", []))
            strategy.update(
                {
                    "name": self._validate_strategy_name(
                        payload.get("name"),
                        data["strategies"],
                        exclude_id=strategy_id,
                    ),
                    "notes": self._normalize_notes(payload.get("notes")),
                    "tagIds": self._normalize_tag_ids(
                        requested_tag_ids,
                        tags,
                        requested_tag_ids != strategy.get("tagIds", []),
                        set(strategy.get("tagIds", [])),
                    ),
                    "updatedAt": utc_now(),
                    "config": config,
                    "assetSnapshots": snapshots,
                    "summary": summary,
                }
            )
            self._write_unlocked(data)
            return next(
                item
                for item in self._serialize(data)["strategies"]
                if item["id"] == strategy_id
            )

    def update_metadata(self, strategy_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            data = self._read_unlocked()
            strategy = self._strategy_map(data).get(strategy_id)
            if strategy is None:
                raise ApiError("策略不存在", status=404)
            tags = self._tag_map(data)
            current_tag_ids = strategy.get("tagIds", [])
            requested_tag_ids = payload.get("tagIds", current_tag_ids)
            require_active = requested_tag_ids != current_tag_ids
            strategy.update(
                {
                    "name": self._validate_strategy_name(
                        payload.get("name", strategy["name"]),
                        data["strategies"],
                        exclude_id=strategy_id,
                    ),
                    "notes": self._normalize_notes(
                        payload.get("notes", strategy.get("notes", ""))
                    ),
                    "tagIds": self._normalize_tag_ids(
                        requested_tag_ids,
                        tags,
                        require_active,
                        set(current_tag_ids),
                    ),
                    "updatedAt": utc_now(),
                }
            )
            self._write_unlocked(data)
            return next(
                item
                for item in self._serialize(data)["strategies"]
                if item["id"] == strategy_id
            )

    def duplicate_strategy(self, strategy_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            data = self._read_unlocked()
            source = self._strategy_map(data).get(strategy_id)
            if source is None:
                raise ApiError("策略不存在", status=404)
            requested_name = str(payload.get("name") or "").strip()
            if not requested_name:
                base = f"{source['name']} - 副本"
                requested_name = base
                suffix = 2
                existing = {item["name"].casefold() for item in data["strategies"]}
                while requested_name.casefold() in existing:
                    requested_name = f"{base} {suffix}"
                    suffix += 1
            now = utc_now()
            duplicate = deepcopy(source)
            duplicate.update(
                {
                    "id": uuid.uuid4().hex,
                    "name": self._validate_strategy_name(
                        requested_name,
                        data["strategies"],
                    ),
                    "createdAt": now,
                    "updatedAt": now,
                }
            )
            data["strategies"].append(duplicate)
            self._write_unlocked(data)
            return next(
                item
                for item in self._serialize(data)["strategies"]
                if item["id"] == duplicate["id"]
            )

    def rerun_strategy(self, strategy_id: str) -> dict[str, Any]:
        with self.lock:
            data = self._read_unlocked()
            strategy = self._strategy_map(data).get(strategy_id)
            if strategy is None:
                raise ApiError("策略不存在", status=404)
            raw_config = deepcopy(strategy["config"])

        config = self._normalize_config(raw_config)
        snapshots = self._asset_snapshots(config)
        try:
            result = run_backtest(config)
        except Exception as exc:
            raise ApiError(str(exc)) from exc
        summary = self._summary(result)

        with self.lock:
            data = self._read_unlocked()
            strategy = self._strategy_map(data).get(strategy_id)
            if strategy is None:
                raise ApiError("策略不存在", status=404)
            strategy.update(
                {
                    "config": config,
                    "assetSnapshots": snapshots,
                    "summary": summary,
                    "updatedAt": utc_now(),
                }
            )
            self._write_unlocked(data)
            serialized = next(
                item
                for item in self._serialize(data)["strategies"]
                if item["id"] == strategy_id
            )
        return {"strategy": serialized, "result": result}

    def delete_strategy(self, strategy_id: str) -> None:
        with self.lock:
            data = self._read_unlocked()
            before = len(data["strategies"])
            data["strategies"] = [
                item for item in data["strategies"] if item["id"] != strategy_id
            ]
            if len(data["strategies"]) == before:
                raise ApiError("策略不存在", status=404)
            self._write_unlocked(data)

    def create_tag(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            data = self._read_unlocked()
            tags = self._tag_map(data)
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ApiError("请输入标签名称")
            if len(name) > 60:
                raise ApiError("标签名称不能超过 60 个字符")
            parent_id = payload.get("parentId") or None
            if parent_id is not None:
                parent_id = str(parent_id)
                if parent_id not in tags:
                    raise ApiError("上级标签不存在", status=404)
                if self._tag_depth(parent_id, tags) >= 3:
                    raise ApiError("标签最多支持三级")
            self._validate_sibling_name(name, parent_id, tags)
            now = utc_now()
            tag = {
                "id": uuid.uuid4().hex,
                "name": name,
                "parentId": parent_id,
                "active": True,
                "createdAt": now,
                "updatedAt": now,
            }
            data["tags"].append(tag)
            self._write_unlocked(data)
            return next(
                item
                for item in self._serialize(data)["tags"]
                if item["id"] == tag["id"]
            )

    def update_tag(self, tag_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            data = self._read_unlocked()
            tags = self._tag_map(data)
            tag = tags.get(tag_id)
            if tag is None:
                raise ApiError("标签不存在", status=404)
            name = str(payload.get("name", tag["name"]) or "").strip()
            if not name:
                raise ApiError("请输入标签名称")
            if len(name) > 60:
                raise ApiError("标签名称不能超过 60 个字符")
            parent_id = payload.get("parentId", tag.get("parentId")) or None
            if parent_id is not None:
                parent_id = str(parent_id)
                if parent_id not in tags:
                    raise ApiError("上级标签不存在", status=404)
                if parent_id == tag_id or parent_id in self._descendants(tag_id, tags):
                    raise ApiError("标签不能移动到自身或其下级标签中")

            trial = deepcopy(tags)
            trial[tag_id]["parentId"] = parent_id
            subtree = self._descendants(tag_id, trial)
            max_depth = max(self._tag_depth(item_id, trial) for item_id in subtree)
            if max_depth > 3:
                raise ApiError("移动后将超过三级标签限制")
            self._validate_sibling_name(name, parent_id, tags, exclude_id=tag_id)
            tag.update(
                {
                    "name": name,
                    "parentId": parent_id,
                    "active": bool(payload.get("active", tag.get("active", True))),
                    "updatedAt": utc_now(),
                }
            )
            self._write_unlocked(data)
            return next(
                item
                for item in self._serialize(data)["tags"]
                if item["id"] == tag_id
            )

    def delete_tag(self, tag_id: str) -> None:
        with self.lock:
            data = self._read_unlocked()
            tags = self._tag_map(data)
            if tag_id not in tags:
                raise ApiError("标签不存在", status=404)
            if any(tag.get("parentId") == tag_id for tag in data["tags"]):
                raise ApiError("存在下级标签，不能彻底删除")
            if any(tag_id in strategy.get("tagIds", []) for strategy in data["strategies"]):
                raise ApiError("仍有策略引用该标签，不能彻底删除")
            data["tags"] = [tag for tag in data["tags"] if tag["id"] != tag_id]
            self._write_unlocked(data)


strategy_store = StrategyStore(STRATEGY_STORE_FILE)


class Handler(BaseHTTPRequestHandler):
    server_version = "LocalBacktest/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/assets":
            self.send_json(store.grouped_assets())
            return
        if parsed.path == "/api/health":
            store.ensure_loaded()
            self.send_json(
                {
                    "status": "ok",
                    "apiVersion": APP_VERSION,
                    "assets": len(store.assets),
                    "schemaVersion": strategy_store.SCHEMA_VERSION,
                }
            )
            return
        if parsed.path == "/api/strategies":
            self.handle_api(lambda: strategy_store.list_all())
            return
        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/backtest":
            self.handle_api(lambda: run_backtest(self.read_json()))
            return
        if parsed.path == "/api/strategies":
            self.handle_api(
                lambda: strategy_store.create_strategy(self.read_json()),
                status=201,
            )
            return
        segments = self.api_segments(parsed.path)
        if len(segments) == 3 and segments[:1] == ["strategies"] and segments[2] == "duplicate":
            self.handle_api(
                lambda: strategy_store.duplicate_strategy(
                    segments[1],
                    self.read_json(),
                ),
                status=201,
            )
            return
        if len(segments) == 3 and segments[:1] == ["strategies"] and segments[2] == "rerun":
            self.handle_api(lambda: strategy_store.rerun_strategy(segments[1]))
            return
        if parsed.path == "/api/tags":
            self.handle_api(
                lambda: strategy_store.create_tag(self.read_json()),
                status=201,
            )
            return
        self.send_error(404)

    def do_PUT(self) -> None:
        segments = self.api_segments(urlparse(self.path).path)
        if len(segments) == 2 and segments[0] == "strategies":
            self.handle_api(
                lambda: strategy_store.update_strategy(
                    segments[1],
                    self.read_json(),
                )
            )
            return
        self.send_error(404)

    def do_PATCH(self) -> None:
        segments = self.api_segments(urlparse(self.path).path)
        if len(segments) == 2 and segments[0] == "strategies":
            self.handle_api(
                lambda: strategy_store.update_metadata(
                    segments[1],
                    self.read_json(),
                )
            )
            return
        if len(segments) == 2 and segments[0] == "tags":
            self.handle_api(
                lambda: strategy_store.update_tag(
                    segments[1],
                    self.read_json(),
                )
            )
            return
        self.send_error(404)

    def do_DELETE(self) -> None:
        segments = self.api_segments(urlparse(self.path).path)
        if len(segments) == 2 and segments[0] == "strategies":
            self.handle_api(
                lambda: strategy_store.delete_strategy(segments[1]),
                status=204,
            )
            return
        if len(segments) == 2 and segments[0] == "tags":
            self.handle_api(
                lambda: strategy_store.delete_tag(segments[1]),
                status=204,
            )
            return
        self.send_error(404)

    def api_segments(self, path: str) -> list[str]:
        if not path.startswith("/api/"):
            return []
        return [segment for segment in path[5:].split("/") if segment]

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        payload = json.loads(body or "{}")
        if not isinstance(payload, dict):
            raise ApiError("请求内容必须为对象")
        return payload

    def handle_api(self, action: Any, status: int = 200) -> None:
        try:
            payload = action()
            if status == 204:
                self.send_response(204)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            self.send_json(payload, status=status)
        except ApiError as exc:
            self.send_json({"error": str(exc)}, status=exc.status)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.send_json({"error": f"请求内容不是有效 JSON：{exc}"}, status=400)
        except Exception as exc:
            traceback.print_exc()
            self.send_json({"error": str(exc)}, status=400)

    def serve_static(self, request_path: str) -> None:
        path = unquote(request_path)
        if path == "/":
            path = "/index.html"
        target = (STATIC_DIR / path.lstrip("/")).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.exists() or target.is_dir():
            self.send_error(404)
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8" if content_type.startswith("text/") else content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: Any, status: int = 200) -> None:
        if isinstance(payload, dict) and isinstance(payload.get("metrics"), list):
            payload = {
                **payload,
                "metrics": [metric for metric in payload["metrics"] if metric],
            }
        data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stdout.write("%s - %s\n" % (self.address_string(), fmt % args))


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    store.ensure_loaded()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"本地回测平台已启动: http://127.0.0.1:{port}")
    print(f"已加载资产: {len(store.assets)} 个；普林格信号: {len(store.pring_df) if store.pring_df is not None else 0} 条")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("正在关闭服务...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
