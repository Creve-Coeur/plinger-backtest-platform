# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import math
import mimetypes
import sys
import traceback
import warnings
from dataclasses import dataclass
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

FUND_DIR = ROOT_DIR / "基金"
INDEX_DIR = ROOT_DIR / "指数"
ENHANCED_DIR = ROOT_DIR / "增强"
STRATEGY_DIR = ROOT_DIR / "策略代码"
PRING_FILE_NAME = "普林格周期判断表_逐月_补全Stage7Stage8.xlsx"

CATEGORY_LABELS = {
    "equity": "股票",
    "commodity": "商品",
    "convertible": "可转债",
    "pure_bond": "纯债",
}

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


@dataclass(frozen=True)
class AssetMeta:
    id: str
    code: str
    name: str
    module: str
    start: str
    end: str
    count: int


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
        self._load_indexes()
        self._load_enhanced()
        self.pring_df = self._load_pring()
        self.loaded = True

    def _register_asset(self, module: str, code: str, name: str, series: pd.Series) -> None:
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
        )

    def _load_funds(self) -> None:
        if not FUND_DIR.exists():
            return
        for file in sorted(FUND_DIR.glob("*.xlsx")):
            xl = pd.ExcelFile(file)
            for sheet in xl.sheet_names:
                df = pd.read_excel(file, sheet_name=sheet)
                if not {"代码", "简称", "时间", "收盘价(元)"}.issubset(df.columns):
                    continue
                code = first_text(df["代码"], sheet)
                name = first_text(df["简称"], code)
                series = pd.Series(
                    pd.to_numeric(df["收盘价(元)"], errors="coerce").values,
                    index=pd.to_datetime(df["时间"], errors="coerce"),
                    name=f"fund:{code}",
                )
                self._register_asset("fund", code, name, series)

    def _load_indexes(self) -> None:
        if not INDEX_DIR.exists():
            return
        for file in sorted(INDEX_DIR.glob("*.xlsx")):
            xl = pd.ExcelFile(file)
            for sheet in xl.sheet_names:
                raw = pd.read_excel(file, sheet_name=sheet)
                if raw.shape[0] < 3 or raw.shape[1] < 2:
                    continue
                date_col = raw.columns[0]
                dates = pd.to_datetime(raw.iloc[2:][date_col], errors="coerce")
                if dates.notna().sum() < 3:
                    continue
                names = raw.iloc[0]
                data = raw.iloc[2:].copy()
                for code in raw.columns[1:]:
                    values = (
                        data[code]
                        .replace(["空", "--", "-", ""], pd.NA)
                        .pipe(pd.to_numeric, errors="coerce")
                    )
                    series = pd.Series(values.values, index=dates, name=f"index:{code}")
                    name = str(names.get(code, code)).strip()
                    if name.lower() == "nan" or not name:
                        name = str(code)
                    self._register_asset("index", str(code), name, series)

    def _load_enhanced(self) -> None:
        # The enhanced library is intentionally optional. Future files can use
        # either the fund-like multi-sheet shape or the index-like wide shape.
        if not ENHANCED_DIR.exists():
            return
        for file in sorted(ENHANCED_DIR.glob("*.xlsx")):
            try:
                xl = pd.ExcelFile(file)
                if len(xl.sheet_names) > 1:
                    for sheet in xl.sheet_names:
                        df = pd.read_excel(file, sheet_name=sheet)
                        if {"代码", "简称", "时间", "收盘价(元)"}.issubset(df.columns):
                            code = first_text(df["代码"], sheet)
                            name = first_text(df["简称"], code)
                            series = pd.Series(
                                pd.to_numeric(df["收盘价(元)"], errors="coerce").values,
                                index=pd.to_datetime(df["时间"], errors="coerce"),
                                name=f"enhanced:{code}",
                            )
                            self._register_asset("enhanced", code, name, series)
                else:
                    raw = pd.read_excel(file, sheet_name=xl.sheet_names[0])
                    if raw.shape[0] >= 3 and raw.shape[1] >= 2:
                        date_col = raw.columns[0]
                        dates = pd.to_datetime(raw.iloc[2:][date_col], errors="coerce")
                        names = raw.iloc[0]
                        data = raw.iloc[2:].copy()
                        if dates.notna().sum() >= 3:
                            for code in raw.columns[1:]:
                                values = (
                                    data[code]
                                    .replace(["空", "--", "-", ""], pd.NA)
                                    .pipe(pd.to_numeric, errors="coerce")
                                )
                                series = pd.Series(values.values, index=dates, name=f"enhanced:{code}")
                                name = str(names.get(code, code)).strip()
                                self._register_asset("enhanced", str(code), name, series)
            except Exception:
                continue

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
        groups = {"fund": [], "index": [], "enhanced": []}
        for meta in sorted(self.meta.values(), key=lambda x: (x.module, x.name, x.code)):
            groups.setdefault(meta.module, []).append(meta.__dict__)
        return {
            "groups": groups,
            "defaults": self.default_selection(),
            "pring": self.pring_summary(),
        }

    def default_selection(self) -> dict[str, list[str]]:
        code_to_id = {(m.module, m.code): m.id for m in self.meta.values()}
        return {
            "equity": [code_to_id.get(("fund", "510300.SH"))],
            "commodity": [
                code_to_id.get(("fund", "159980.SZ")),
                code_to_id.get(("fund", "518880.SH")),
                code_to_id.get(("fund", "159981.SZ")),
                code_to_id.get(("fund", "159985.SZ")),
            ],
            "convertible": [code_to_id.get(("fund", "511380.SH"))],
            "pure_bond": [code_to_id.get(("fund", "166016.SZ"))],
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


def validate_asset_modules(selected: dict[str, list[str]], module: str, source_name: str) -> None:
    bad = [
        f"{store.meta[asset_id].name}({store.meta[asset_id].code})"
        for ids in selected.values()
        for asset_id in ids
        if store.meta[asset_id].module != module
    ]
    if bad:
        module_label = {"fund": "基金", "index": "指数"}.get(module, module)
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
    validate_asset_modules(selected, "fund", "主回测篮子")
    validate_asset_modules(splice_selected, "index", "拼接模拟池")

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


def stage_target_weights(stage: int) -> dict[str, float]:
    if stage not in STAGE_DOMINANT:
        raise ValueError(f"不支持的普林格 Stage: {stage}")
    dominant = STAGE_DOMINANT[stage]
    weights = {key: 0.10 for key in CATEGORY_LABELS}
    weights[dominant] = 0.70
    return weights


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


def reequal_category(
    values: dict[str, float],
    ids: list[str],
) -> None:
    total = float(sum(values.pop(asset_id, 0.0) for asset_id in ids))
    values.update(distribute_value(total, ids))


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


def exit_to_pure_bond(
    main_values: dict[str, float],
    escape_values: dict[str, float],
    dominant: str,
    active: dict[str, list[str]],
) -> tuple[dict[str, float], dict[str, float]]:
    sold_value = float(sum(main_values.pop(asset_id, 0.0) for asset_id in active[dominant]))
    reequal_category(main_values, active["pure_bond"])
    escape_values = distribute_value(sold_value, active["pure_bond"])
    return main_values, escape_values


def reenter_from_pure_bond(
    main_values: dict[str, float],
    escape_values: dict[str, float],
    dominant: str,
    active: dict[str, list[str]],
) -> tuple[dict[str, float], dict[str, float]]:
    returned_value = float(sum(escape_values.values()))
    reequal_category(main_values, active["pure_bond"])
    existing = float(sum(main_values.pop(asset_id, 0.0) for asset_id in active[dominant]))
    main_values.update(distribute_value(existing + returned_value, active[dominant]))
    return main_values, {}


def apply_returns(
    main_values: dict[str, float],
    escape_values: dict[str, float],
    returns: pd.Series,
) -> None:
    for values in (main_values, escape_values):
        for asset_id in list(values):
            daily_return = float(returns.get(asset_id, 0.0))
            values[asset_id] *= 1.0 + daily_return


def ma20_escape_state(
    nav: pd.Series,
    ma20: pd.Series,
    dates: pd.DatetimeIndex,
    position: int,
    currently_escaped: bool,
    confirmation_days: int,
) -> bool:
    end_position = position - 1
    start_position = end_position - confirmation_days + 1
    if start_position < 0:
        return currently_escaped

    signal_dates = dates[start_position : end_position + 1]
    nav_window = nav.reindex(signal_dates)
    ma_window = ma20.reindex(signal_dates)
    if nav_window.isna().any() or ma_window.isna().any():
        return currently_escaped

    above = nav_window >= ma_window
    if currently_escaped:
        return not bool(above.all())
    return bool((~above).all())


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
            "convertible": bool(ma20_controls_payload.get("convertible", False)),
        }
    else:
        legacy_enabled = bool(payload.get("ma20Enabled", True))
        ma20_controls = {"equity": legacy_enabled, "commodity": legacy_enabled, "convertible": False}
    ma20_enabled = any(ma20_controls.values())
    ma20_three_day = bool(payload.get("ma20ThreeDay", False))
    ma20_confirmation_days = 3 if ma20_three_day else 1

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

    dates = prepared.dates[prepared.dates > first_signal_date]
    if len(dates) < 40:
        raise ValueError("首条普林格信号生效后的共同区间不足 40 个交易日，无法稳定回测")
    asset_returns = prepared.asset_returns.reindex(dates).fillna(0.0)
    signal_returns = {
        key: values.reindex(dates).fillna(0.0)
        for key, values in prepared.signal_returns.items()
    }

    signal_nav = {
        key: (1.0 + values).cumprod()
        for key, values in signal_returns.items()
    }
    signal_ma20 = {
        key: values.rolling(window=20).mean()
        for key, values in signal_nav.items()
    }
    events = build_rebalance_events(store.pring_df, dates)

    strategy_main: dict[str, float] = {}
    strategy_escape: dict[str, float] = {}
    theory_main: dict[str, float] = {}
    theory_escape: dict[str, float] = {}
    escape_category: str | None = None
    current_stage: int | None = None
    previous_active: dict[str, list[str]] | None = None

    strategy_returns: list[float] = []
    theory_returns: list[float] = []
    strategy_nav_values: list[float] = []
    theory_nav_values: list[float] = []
    rows: list[dict[str, Any]] = []
    trade_logs: list[dict[str, Any]] = []
    escape_eq: dict[pd.Timestamp, bool] = {}
    escape_com: dict[pd.Timestamp, bool] = {}
    escape_cb: dict[pd.Timestamp, bool] = {}
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
    ) -> None:
        weights = category_weights(strategy_main, strategy_escape, active)
        dominant = STAGE_DOMINANT[stage]
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

    for i, d in enumerate(dates):
        d = pd.Timestamp(d)
        prev_date = pd.Timestamp(dates[i - 1]) if i > 0 else None
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
            dominant = STAGE_DOMINANT[current_stage]
            targets = stage_target_weights(current_stage)
            strategy_total = portfolio_total(strategy_main, strategy_escape) or 1.0
            theory_total = portfolio_total(theory_main, theory_escape) or 1.0
            should_escape = (
                dominant != "pure_bond"
                and ma20_controls.get(dominant, False)
                and ma20_escape_state(
                    signal_nav[dominant],
                    signal_ma20[dominant],
                    dates,
                    i,
                    escape_category == dominant,
                    ma20_confirmation_days,
                )
            )
            strategy_main, strategy_escape = rebalance_values(
                strategy_total,
                targets,
                active,
                dominant if should_escape else None,
            )
            theory_main, theory_escape = rebalance_values(theory_total, targets, active)
            escape_category = dominant if should_escape else None

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
            if should_escape:
                confirmation_text = "连续3日位于MA20下方" if ma20_three_day else "位于MA20下方"
                reason += f" + {CATEGORY_LABELS[dominant]}{confirmation_text}，70%优势仓转入纯债"
            append_trade(
                d,
                event["type"],
                reason,
                current_stage,
                active,
                prev_date,
                event.get("signal_date"),
            )
        else:
            if current_stage is None:
                current_stage = stage_for_date(store.pring_df, d)
            dominant = STAGE_DOMINANT[current_stage]
            if switched:
                append_trade(
                    d,
                    "splice_switch",
                    "模拟拼接切换至基金，保留四类资产市值并恢复类别内等权",
                    current_stage,
                    active,
                    prev_date,
                )

            should_escape = (
                dominant != "pure_bond"
                and ma20_controls.get(dominant, False)
                and ma20_escape_state(
                    signal_nav[dominant],
                    signal_ma20[dominant],
                    dates,
                    i,
                    escape_category == dominant,
                    ma20_confirmation_days,
                )
            )
            if should_escape and escape_category is None:
                strategy_main, strategy_escape = exit_to_pure_bond(
                    strategy_main, strategy_escape, dominant, active
                )
                escape_category = dominant
                append_trade(
                    d,
                    "ma20_exit",
                    (
                        f"{CATEGORY_LABELS[dominant]}优势仓连续3日低于MA20，全部撤退至纯债"
                        if ma20_three_day
                        else f"{CATEGORY_LABELS[dominant]}优势仓跌破MA20，全部撤退至纯债"
                    ),
                    current_stage,
                    active,
                    prev_date,
                )
            elif not should_escape and escape_category == dominant:
                strategy_main, strategy_escape = reenter_from_pure_bond(
                    strategy_main, strategy_escape, dominant, active
                )
                escape_category = None
                append_trade(
                    d,
                    "ma20_reentry",
                    (
                        f"{CATEGORY_LABELS[dominant]}优势仓连续3日站上MA20，避险份额原路买回"
                        if ma20_three_day
                        else f"{CATEGORY_LABELS[dominant]}优势仓收复MA20，避险份额原路买回"
                    ),
                    current_stage,
                    active,
                    prev_date,
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
        escape_eq[d] = escape_category == "equity"
        escape_com[d] = escape_category == "commodity"
        escape_cb[d] = escape_category == "convertible"

        rows.append(
            {
                "date": d.strftime("%Y-%m-%d"),
                "equityWeight": as_float(weights["equity"], 6),
                "commodityWeight": as_float(weights["commodity"], 6),
                "convertibleWeight": as_float(weights["convertible"], 6),
                "pureBondWeight": as_float(weights["pure_bond"], 6),
                "equityEscape": escape_eq[d],
                "commodityEscape": escape_com[d],
                "convertibleEscape": escape_cb[d],
                "stage": current_stage,
                "dominantAsset": dominant,
            }
        )
        previous_active = active

    strategy_ret = pd.Series(strategy_returns, index=dates)
    theory_ret = pd.Series(theory_returns, index=dates)
    nav_strategy = pd.Series(strategy_nav_values, index=dates)
    nav_theory = pd.Series(theory_nav_values, index=dates)

    benchmark_series = find_benchmark_series()
    benchmark_prices = (
        benchmark_series.reindex(prepared.raw_prices.index.union(dates))
        .sort_index()
        .ffill()
        .reindex(dates)
        .dropna()
    )
    if len(benchmark_prices) == len(dates):
        benchmark_ret = benchmark_prices.pct_change(fill_method=None).fillna(0.0)
        nav_benchmark = (1 + benchmark_ret).cumprod()
    else:
        nav_benchmark = nav_theory * np.nan

    df_daily = pd.DataFrame(
        {
            "Eq": pd.Series(contribution_history["equity"], index=dates),
            "Com": pd.Series(contribution_history["commodity"], index=dates),
            "Cb": pd.Series(contribution_history["convertible"], index=dates),
            "Cdb": pd.Series(contribution_history["pure_bond"], index=dates),
            "Strat": strategy_ret,
            "Benchmark": nav_benchmark.pct_change().fillna(0),
        }
    )
    df_daily["Prev_NAV"] = nav_strategy.shift(1).fillna(1.0)
    df_daily["Year"] = df_daily.index.year

    annual = build_annual_attribution(df_daily)
    contribution = build_contribution_summary(df_daily)
    efficiency = build_efficiency(weights_history, contribution, dates)
    escape_diagnostics = {
        "equity": build_escape_diagnostics(
            signal_returns["equity"], signal_returns["pure_bond"], escape_eq, dates
        ),
        "commodity": build_escape_diagnostics(
            signal_returns["commodity"], signal_returns["pure_bond"], escape_com, dates
        ),
        "convertible": build_escape_diagnostics(
            signal_returns["convertible"], signal_returns["pure_bond"], escape_cb, dates
        ),
    }

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

    return {
        "window": {
            "start": dates[0].strftime("%Y-%m-%d"),
            "end": dates[-1].strftime("%Y-%m-%d"),
            "days": int(len(dates)),
            "firstSignalDate": first_signal_date.strftime("%Y-%m-%d"),
        },
        "ma20Enabled": ma20_enabled,
        "ma20Controls": ma20_controls,
        "ma20ThreeDay": ma20_three_day,
        "metrics": [
            metric(nav_strategy, "策略实盘版"),
            metric(nav_theory, "理论无风控"),
            metric(nav_benchmark.dropna(), "沪深300基准") if nav_benchmark.notna().any() else None,
        ],
        "series": rows,
        "tradeLogs": trade_logs,
        "rebalanceStats": {
            "strategyTotal": stage_rebalance_count + three_month_rebalance_count,
            "stageChanges": stage_rebalance_count,
            "threeMonth": three_month_rebalance_count,
            "initialBuild": 1 if trade_logs else 0,
            "ma20Actions": sum(log["rebalanceType"].startswith("ma20") for log in trade_logs),
        },
        "annualAttribution": annual,
        "contributionSummary": contribution,
        "efficiency": efficiency,
        "escapeDiagnostics": escape_diagnostics,
        "selectedAssets": selected_assets,
        "spliceSummary": prepared.splice_summary,
        "spliceContext": prepared.splice_context,
    }


def find_benchmark_series() -> pd.Series:
    for asset_id in ("fund:510300.SH", "index:000300.SH"):
        if asset_id in store.assets:
            return store.assets[asset_id].rename("benchmark")
    first_asset = next(iter(store.assets.values()))
    return first_asset.rename("benchmark")


def build_annual_attribution(df_daily: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for year, group in df_daily.groupby("Year"):
        start_nav = group["Prev_NAV"].iloc[0]
        rows.append(
            {
                "year": str(year),
                "strategy": as_float((1 + group["Strat"]).prod() - 1),
                "benchmark": as_float((1 + group["Benchmark"]).prod() - 1),
                "equity": as_float((group["Eq"] * group["Prev_NAV"]).sum() / start_nav),
                "commodity": as_float((group["Com"] * group["Prev_NAV"]).sum() / start_nav),
                "convertible": as_float((group["Cb"] * group["Prev_NAV"]).sum() / start_nav),
                "pureBond": as_float((group["Cdb"] * group["Prev_NAV"]).sum() / start_nav),
            }
        )
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


def build_escape_diagnostics(
    asset_returns: pd.Series,
    pure_bond_returns: pd.Series,
    escape_flags: dict[pd.Timestamp, bool],
    dates: pd.Index,
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    in_escape = False
    start: pd.Timestamp | None = None
    asset_nav = (1 + asset_returns).cumprod()
    cdb_nav = (1 + pure_bond_returns).cumprod()
    previous_date: pd.Timestamp | None = None

    for d in dates:
        escaping = escape_flags.get(d, False)
        if escaping and not in_escape:
            in_escape = True
            start = d
        elif not escaping and in_escape and start is not None:
            end = previous_date or d
            slice_nav = asset_nav.loc[(asset_nav.index >= start) & (asset_nav.index <= end)]
            if len(slice_nav) > 1:
                diagnostics.append(
                    {
                        "start": start.strftime("%Y-%m-%d"),
                        "end": end.strftime("%Y-%m-%d"),
                        "days": int((end - start).days),
                        "avoidedDrawdown": as_float(slice_nav.min() / slice_nav.iloc[0] - 1),
                        "missedRunup": as_float(slice_nav.max() / slice_nav.iloc[0] - 1),
                        "assetReturn": as_float(slice_nav.iloc[-1] / slice_nav.iloc[0] - 1),
                        "pureBondReturn": as_float(cdb_nav.loc[end] / cdb_nav.loc[start] - 1),
                    }
                )
            in_escape = False
            start = None
        previous_date = d
    return diagnostics


class Handler(BaseHTTPRequestHandler):
    server_version = "LocalBacktest/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/assets":
            self.send_json(store.grouped_assets())
            return
        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/backtest":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(body or "{}")
            self.send_json(run_backtest(payload))
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
        payload = {**payload, "metrics": [m for m in payload.get("metrics", []) if m]} if isinstance(payload, dict) else payload
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
