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


@dataclass(frozen=True)
class AssetMeta:
    id: str
    code: str
    name: str
    module: str
    start: str
    end: str
    count: int


class DataStore:
    def __init__(self) -> None:
        self.assets: dict[str, pd.Series] = {}
        self.meta: dict[str, AssetMeta] = {}
        self.pring_df: pd.DataFrame | None = None
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
        candidates = sorted(STRATEGY_DIR.glob("*普林格*调仓*.xlsx"))
        if not candidates:
            candidates = sorted(ROOT_DIR.rglob("*普林格*调仓*.xlsx"))
        if not candidates:
            raise FileNotFoundError("未找到普林格调仓明细 Excel 文件")
        df = pd.read_excel(candidates[0], sheet_name="Sheet1")
        required = [
            "调仓日期",
            "触发宏观状态",
            "核心资产 (70%)",
            "沪深300指数",
            "南华期货:商品指数",
            "中证基金指数:货币基金",
            "中证全债指数",
        ]
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(f"普林格调仓表缺少字段: {', '.join(missing)}")
        df = df[required].copy()
        df["调仓日期"] = pd.to_datetime(df["调仓日期"], errors="coerce")
        df = df.dropna(subset=["调仓日期"]).sort_values("调仓日期")
        weight_cols = required[3:]
        for col in weight_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        return df

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
            "equity": [
                code_to_id.get(("fund", "510300.SH")),
                code_to_id.get(("fund", "512100.SH")),
                code_to_id.get(("fund", "159915.SZ")),
                code_to_id.get(("fund", "513010.SH")),
            ],
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
            "start": self.pring_df["调仓日期"].min().strftime("%Y-%m-%d"),
            "end": self.pring_df["调仓日期"].max().strftime("%Y-%m-%d"),
            "rows": int(len(self.pring_df)),
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
    returns = prices.pct_change().fillna(0)
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
) -> tuple[pd.Index, dict[str, pd.Series], pd.DataFrame, list[dict[str, Any]], dict[str, Any]]:
    raw_prices = build_price_frame(all_ids)
    first_dates = [store.assets[asset_id].index.min() for asset_id in all_ids]
    last_dates = [store.assets[asset_id].index.max() for asset_id in all_ids]
    start_date = max(first_dates + [first_signal_date])
    end_date = min(last_dates)
    prices = raw_prices.loc[(raw_prices.index >= start_date) & (raw_prices.index <= end_date)].dropna(how="any")
    if len(prices) < 40:
        raise ValueError("共同净值区间不足 40 个交易日，无法稳定回测")
    category_returns = build_category_returns_from_prices(prices, selected)
    return prices.index, category_returns, raw_prices, [], {"enabled": False}


def prepare_spliced_series(
    selected: dict[str, list[str]],
    splice_selected: dict[str, list[str]],
    first_signal_date: pd.Timestamp,
) -> tuple[pd.Index, dict[str, pd.Series], pd.DataFrame, list[dict[str, Any]], dict[str, Any]]:
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

    pre_returns = build_category_returns_from_prices(pre_prices, splice_selected)
    post_returns = build_category_returns_from_prices(post_prices, selected)
    category_returns = {
        key: pd.concat([pre_returns[key], post_returns[key]]).sort_index()
        for key in selected.keys()
    }
    dates = category_returns["equity"].index

    splice_summary = [
        {
            "category": key,
            "categoryName": {"equity": "股票", "commodity": "商品", "convertible": "可转债", "pure_bond": "纯债"}[key],
            "proxyAssets": [store.meta[asset_id].__dict__ for asset_id in ids],
            "applied": True,
        }
        for key, ids in splice_selected.items()
    ]
    splice_context = {
        "enabled": True,
        "fundCommonStart": fund_common_start.strftime("%Y-%m-%d"),
        "indexStart": pre_prices.index.min().strftime("%Y-%m-%d"),
        "indexEnd": pre_prices.index.max().strftime("%Y-%m-%d"),
        "fundStart": post_prices.index.min().strftime("%Y-%m-%d"),
        "mode": "index_before_fund_common_start",
    }
    raw_prices = pd.concat([index_prices_all, fund_prices_all], axis=1).sort_index().ffill()
    if len(dates) < 40:
        raise ValueError("拼接后的共同区间不足 40 个交易日，无法稳定回测")
    return dates, category_returns, raw_prices, splice_summary, splice_context


def run_backtest(payload: dict[str, Any]) -> dict[str, Any]:
    store.ensure_loaded()
    if store.pring_df is None:
        raise ValueError("普林格调仓表尚未加载")

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

    labels = {
        "equity": "股票",
        "commodity": "商品",
        "convertible": "可转债",
        "pure_bond": "纯债",
    }
    selected = {
        "equity": equity_ids,
        "commodity": commodity_ids,
        "convertible": convertible_ids,
        "pure_bond": pure_bond_ids,
    }
    missing_categories = [labels[k] for k, v in selected.items() if not v]
    if missing_categories:
        raise ValueError(f"以下资产类别至少需要一只标的: {'、'.join(missing_categories)}")

    all_ids = equity_ids + commodity_ids + convertible_ids + pure_bond_ids
    unknown = [asset_id for asset_id in all_ids if asset_id not in store.assets]
    if unknown:
        raise ValueError(f"资产不存在或尚未加载: {', '.join(unknown)}")

    first_signal_date = store.pring_df["调仓日期"].min()
    if splice_enabled:
        splice_selected = {
            "equity": unique_ids(splice_baskets_payload.get("equity", [])),
            "commodity": unique_ids(splice_baskets_payload.get("commodity", [])),
            "convertible": unique_ids(splice_baskets_payload.get("convertible", [])),
            "pure_bond": unique_ids(splice_baskets_payload.get("pure_bond", [])),
        }
        missing_splice = [labels[k] for k, v in splice_selected.items() if not v]
        if missing_splice:
            raise ValueError(f"模拟拼接开启时，拼接模拟池以下类别至少需要一只指数: {'、'.join(missing_splice)}")
        splice_ids = [asset_id for ids in splice_selected.values() for asset_id in ids]
        unknown_splice = [asset_id for asset_id in splice_ids if asset_id not in store.assets]
        if unknown_splice:
            raise ValueError(f"拼接模拟池资产不存在或尚未加载: {', '.join(unknown_splice)}")
        dates, category_returns, raw_prices, splice_summary, splice_context = prepare_spliced_series(
            selected, splice_selected, first_signal_date
        )
    else:
        dates, category_returns, raw_prices, splice_summary, splice_context = prepare_normal_series(
            selected, all_ids, first_signal_date
        )

    r_eq = category_returns["equity"]
    r_com = category_returns["commodity"]
    r_cb = category_returns["convertible"]
    r_cdb = category_returns["pure_bond"]

    nav_eq = (1 + r_eq).cumprod()
    nav_com = (1 + r_com).cumprod()
    nav_cb = (1 + r_cb).cumprod()
    ma20_eq = nav_eq.rolling(window=20).mean()
    ma20_com = nav_com.rolling(window=20).mean()
    ma20_cb = nav_cb.rolling(window=20).mean()

    weights_df = store.pring_df.set_index("调仓日期")[
        ["沪深300指数", "南华期货:商品指数", "中证基金指数:货币基金", "中证全债指数"]
    ]
    all_weight_dates = sorted(set(dates) | set(weights_df.index))
    weights_daily = weights_df.reindex(all_weight_dates).ffill().loc[dates].fillna(0.0)

    ret_strategy: list[float] = []
    ret_theory: list[float] = []
    rows: list[dict[str, Any]] = []
    trade_logs: list[dict[str, Any]] = []
    escape_eq: dict[pd.Timestamp, bool] = {}
    escape_com: dict[pd.Timestamp, bool] = {}
    escape_cb: dict[pd.Timestamp, bool] = {}
    last_sig: tuple[Any, ...] | None = None

    weights_history = {"equity": [], "commodity": [], "convertible": [], "pure_bond": []}

    for i, d in enumerate(dates):
        w_eq = float(weights_daily.loc[d, "沪深300指数"])
        w_com = float(weights_daily.loc[d, "南华期货:商品指数"])
        w_bond_total = float(
            weights_daily.loc[d, "中证基金指数:货币基金"] + weights_daily.loc[d, "中证全债指数"]
        )
        w_cdb_base = min(0.10, w_bond_total)
        w_cb_base = max(0.0, w_bond_total - 0.10)

        prev_date = dates[i - 1] if i > 0 else dates[0]
        eq_has_ma = pd.notna(ma20_eq.loc[prev_date])
        com_has_ma = pd.notna(ma20_com.loc[prev_date])
        cb_has_ma = pd.notna(ma20_cb.loc[prev_date])
        eq_above = bool(nav_eq.loc[prev_date] >= ma20_eq.loc[prev_date]) if eq_has_ma else True
        com_above = bool(nav_com.loc[prev_date] >= ma20_com.loc[prev_date]) if com_has_ma else True
        cb_above = bool(nav_cb.loc[prev_date] >= ma20_cb.loc[prev_date]) if cb_has_ma else True
        is_eq_heavy = w_eq > 0.65
        is_com_heavy = w_com > 0.65
        is_cb_heavy = w_cb_base > 0.65

        act_eq = eq_above if (ma20_controls["equity"] and is_eq_heavy) else True
        act_com = com_above if (ma20_controls["commodity"] and is_com_heavy) else True
        act_cb = cb_above if (ma20_controls["convertible"] and is_cb_heavy) else True

        final_w_eq = w_eq if act_eq else 0.0
        final_w_com = w_com if act_com else 0.0
        final_w_cb = w_cb_base if act_cb else 0.0
        final_w_cdb = w_cdb_base + (w_eq - final_w_eq) + (w_com - final_w_com) + (w_cb_base - final_w_cb)

        day_ret = final_w_eq * r_eq.loc[d] + final_w_com * r_com.loc[d] + final_w_cb * r_cb.loc[d] + final_w_cdb * r_cdb.loc[d]
        theory_ret = w_eq * r_eq.loc[d] + w_com * r_com.loc[d] + w_cb_base * r_cb.loc[d] + w_cdb_base * r_cdb.loc[d]
        ret_strategy.append(float(day_ret))
        ret_theory.append(float(theory_ret))

        weights_history["equity"].append(final_w_eq)
        weights_history["commodity"].append(final_w_com)
        weights_history["convertible"].append(final_w_cb)
        weights_history["pure_bond"].append(final_w_cdb)
        escape_eq[d] = not act_eq
        escape_com[d] = not act_com
        escape_cb[d] = not act_cb

        sig = (round(w_eq, 6), round(w_com, 6), round(w_cb_base, 6), act_eq, act_com, act_cb)
        if trade_logs and sig == last_sig:
            trade_logs[-1]["end"] = d.strftime("%Y-%m-%d")
            trade_logs[-1]["days"] += 1
        else:
            reason: list[str] = []
            if last_sig is None:
                reason.append("初始建仓")
            else:
                prev_w_eq, prev_w_com, prev_w_cb, prev_act_eq, prev_act_com, prev_act_cb = last_sig
                if round(w_eq, 6) != prev_w_eq or round(w_com, 6) != prev_w_com:
                    reason.append("宏观季度调仓")
                elif round(w_cb_base, 6) != prev_w_cb:
                    reason.append("债券仓位映射变化")
                if act_eq != prev_act_eq:
                    reason.append("股端击穿MA20-撤退至纯债" if not act_eq else "股端收复MA20-买回股票")
                if act_com != prev_act_com:
                    reason.append("商端击穿MA20-撤退至纯债" if not act_com else "商端收复MA20-买回商品")
                if act_cb != prev_act_cb:
                    reason.append("转债端击穿MA20-撤退至纯债" if not act_cb else "转债端收复MA20-买回转债")
            trade_logs.append(
                {
                    "start": d.strftime("%Y-%m-%d"),
                    "end": d.strftime("%Y-%m-%d"),
                    "days": 1,
                    "reason": " + ".join(reason),
                    "equityWeight": as_float(final_w_eq, 4),
                    "commodityWeight": as_float(final_w_com, 4),
                    "convertibleWeight": as_float(final_w_cb, 4),
                    "pureBondWeight": as_float(final_w_cdb, 4),
                    "equityNav": as_float(nav_eq.loc[d], 4),
                    "commodityNav": as_float(nav_com.loc[d], 4),
                    "convertibleNav": as_float(nav_cb.loc[d], 4),
                    "equityMa20": as_float(ma20_eq.loc[prev_date], 4) if is_eq_heavy else None,
                    "commodityMa20": as_float(ma20_com.loc[prev_date], 4) if is_com_heavy else None,
                    "convertibleMa20": as_float(ma20_cb.loc[prev_date], 4) if is_cb_heavy else None,
                }
            )
            last_sig = sig

    strategy_ret = pd.Series(ret_strategy, index=dates)
    theory_ret = pd.Series(ret_theory, index=dates)
    nav_strategy = (1 + strategy_ret).cumprod()
    nav_theory = (1 + theory_ret).cumprod()

    benchmark_series = find_benchmark_series()
    benchmark_prices = benchmark_series.reindex(raw_prices.index.union(dates)).sort_index().ffill().reindex(dates).dropna()
    if len(benchmark_prices) == len(dates):
        benchmark_ret = benchmark_prices.pct_change().fillna(0)
        nav_benchmark = (1 + benchmark_ret).cumprod()
    else:
        nav_benchmark = nav_theory * np.nan

    df_daily = pd.DataFrame(
        {
            "Eq": pd.Series(weights_history["equity"], index=dates) * r_eq,
            "Com": pd.Series(weights_history["commodity"], index=dates) * r_com,
            "Cb": pd.Series(weights_history["convertible"], index=dates) * r_cb,
            "Cdb": pd.Series(weights_history["pure_bond"], index=dates) * r_cdb,
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
        "equity": build_escape_diagnostics(r_eq, r_cdb, escape_eq, dates),
        "commodity": build_escape_diagnostics(r_com, r_cdb, escape_com, dates),
        "convertible": build_escape_diagnostics(r_cb, r_cdb, escape_cb, dates),
    }

    drawdown_strategy = nav_strategy / nav_strategy.cummax() - 1
    drawdown_benchmark = nav_benchmark / nav_benchmark.cummax() - 1 if nav_benchmark.notna().any() else nav_benchmark

    for d in dates:
        rows.append(
            {
                "date": d.strftime("%Y-%m-%d"),
                "strategy": as_float(nav_strategy.loc[d]),
                "theory": as_float(nav_theory.loc[d]),
                "benchmark": as_float(nav_benchmark.loc[d]) if d in nav_benchmark.index else None,
                "drawdown": as_float(drawdown_strategy.loc[d]),
                "benchmarkDrawdown": as_float(drawdown_benchmark.loc[d]) if d in drawdown_benchmark.index else None,
                "equityWeight": as_float(weights_history["equity"][dates.get_loc(d)], 4),
                "commodityWeight": as_float(weights_history["commodity"][dates.get_loc(d)], 4),
                "convertibleWeight": as_float(weights_history["convertible"][dates.get_loc(d)], 4),
                "pureBondWeight": as_float(weights_history["pure_bond"][dates.get_loc(d)], 4),
                "equityEscape": escape_eq[d],
                "commodityEscape": escape_com[d],
                "convertibleEscape": escape_cb[d],
            }
        )

    selected_assets = {
        key: [store.meta[asset_id].__dict__ for asset_id in ids]
        for key, ids in selected.items()
    }

    return {
        "window": {
            "start": dates[0].strftime("%Y-%m-%d"),
            "end": dates[-1].strftime("%Y-%m-%d"),
            "days": int(len(dates)),
            "firstSignalDate": first_signal_date.strftime("%Y-%m-%d"),
        },
        "ma20Enabled": ma20_enabled,
        "ma20Controls": ma20_controls,
        "metrics": [
            metric(nav_strategy, "策略实盘版"),
            metric(nav_theory, "理论无风控"),
            metric(nav_benchmark.dropna(), "沪深300基准") if nav_benchmark.notna().any() else None,
        ],
        "series": rows,
        "tradeLogs": trade_logs,
        "annualAttribution": annual,
        "contributionSummary": contribution,
        "efficiency": efficiency,
        "escapeDiagnostics": escape_diagnostics,
        "selectedAssets": selected_assets,
        "spliceSummary": splice_summary,
        "spliceContext": splice_context,
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

    for d in dates:
        escaping = escape_flags.get(d, False)
        if escaping and not in_escape:
            in_escape = True
            start = d
        elif not escaping and in_escape and start is not None:
            end = d
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
