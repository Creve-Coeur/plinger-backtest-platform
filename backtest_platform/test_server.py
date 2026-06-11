# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

import pandas as pd

import server


class PringStageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        server.store.ensure_loaded()

    def test_monthly_stage_workbook_is_loaded(self) -> None:
        summary = server.store.pring_summary()
        self.assertEqual(summary["source"], server.PRING_FILE_NAME)
        self.assertEqual(summary["rows"], 121)
        self.assertEqual(set(server.store.pring_df["stage"]), set(range(1, 9)))

    def test_default_selection_uses_requested_indexes(self) -> None:
        self.assertEqual(
            server.store.default_selection(),
            {
                "equity": [
                    "index:000852.SH",
                    "index:932000.CSI",
                    "index:000300.SH",
                    "index:000905.SH",
                    "index:399006.SZ",
                ],
                "commodity": ["index:NHCI.NH"],
                "convertible": ["index:931078.CSI"],
                "pure_bond": ["index:H11001.CSI"],
            },
        )

    def test_asset_libraries_are_loaded_from_category_folders(self) -> None:
        assets_by_module = {
            module: [meta for meta in server.store.meta.values() if meta.module == module]
            for module in ("fund", "index", "enhanced")
        }
        self.assertEqual(len(assets_by_module["fund"]), 18)
        self.assertEqual(len(assets_by_module["index"]), 20)
        self.assertEqual(len(assets_by_module["enhanced"]), 163)

        expected_counts = {
            "fund": {"equity": 7, "commodity": 4, "convertible": 1, "pure_bond": 6},
            "index": {"equity": 13, "commodity": 1, "convertible": 1, "pure_bond": 5},
            "enhanced": {"equity": 150, "commodity": 3, "convertible": 10},
        }
        for module, category_counts in expected_counts.items():
            for category, count in category_counts.items():
                self.assertEqual(
                    sum(meta.category == category for meta in assets_by_module[module]),
                    count,
                )

        self.assertEqual(
            server.store.meta["enhanced:000297.OF"].name,
            "鹏华可转债债券A",
        )
        self.assertEqual(
            server.store.meta["enhanced:000297.OF"].category,
            "convertible",
        )

    def test_fund_manager_assets_and_labels_are_loaded(self) -> None:
        manager_assets = [
            meta for meta in server.store.meta.values() if meta.module == "manager"
        ]
        self.assertEqual(len(manager_assets), 52)
        self.assertEqual(
            {meta.cluster for meta in manager_assets},
            {"防守压仓", "核心稳健", "进攻弹性"},
        )
        sample = server.store.meta["manager:008134.OF"]
        self.assertEqual(sample.manager, "伍旋")
        self.assertEqual(sample.roleLabel, "极致防守·压舱石")
        self.assertIn("近全周期有效", sample.fullLabel)

    def test_stage_target_mapping(self) -> None:
        expected = {
            1: "convertible",
            2: "equity",
            3: "equity",
            4: "commodity",
            5: "commodity",
            6: "pure_bond",
            7: "commodity",
            8: "convertible",
        }
        for stage, dominant in expected.items():
            weights = server.stage_target_weights(stage)
            self.assertAlmostEqual(weights[dominant], 0.70)
            self.assertAlmostEqual(sum(weights.values()), 1.0)
            self.assertTrue(all(value == 0.10 for key, value in weights.items() if key != dominant))

    def test_custom_stage_weights_are_validated(self) -> None:
        custom = server.default_stage_weights()
        custom["2"] = {
            "equity": 0.60,
            "commodity": 0.15,
            "convertible": 0.10,
            "pure_bond": 0.15,
        }
        parsed = server.parse_stage_weights(custom)
        self.assertEqual(parsed[2], custom["2"])

        custom["2"]["pure_bond"] = 0.20
        with self.assertRaisesRegex(ValueError, "合计必须为 100%"):
            server.parse_stage_weights(custom)

        custom = server.default_stage_weights()
        custom["9"] = custom["8"]
        with self.assertRaisesRegex(ValueError, "存在未知 Stage 9"):
            server.parse_stage_weights(custom)

    def test_dominant_asset_uses_weight_and_tie_priority(self) -> None:
        custom = server.parse_stage_weights(server.default_stage_weights())
        custom[1] = {
            "equity": 0.25,
            "commodity": 0.25,
            "convertible": 0.25,
            "pure_bond": 0.25,
        }
        self.assertEqual(server.dominant_asset_for_stage(1, custom), "equity")

        custom[1] = {
            "equity": 0.10,
            "commodity": 0.40,
            "convertible": 0.40,
            "pure_bond": 0.10,
        }
        self.assertEqual(server.dominant_asset_for_stage(1, custom), "commodity")

    def test_three_month_rebalance_occurs_after_three_full_months(self) -> None:
        pring = make_pring([("2023-12-31", 1)])
        dates = pd.bdate_range("2024-01-02", "2024-05-03")
        events = server.build_rebalance_events(pring, dates)
        self.assertEqual(events[pd.Timestamp("2024-05-01")]["type"], "three_month")
        self.assertEqual(events[pd.Timestamp("2024-05-01")]["signal_date"], pd.Timestamp("2024-04-30"))

    def test_stage_change_resets_three_month_clock(self) -> None:
        pring = make_pring([("2023-12-31", 1), ("2024-02-29", 2)])
        dates = pd.bdate_range("2024-01-02", "2024-06-05")
        events = server.build_rebalance_events(pring, dates)
        self.assertEqual(events[pd.Timestamp("2024-03-01")]["type"], "stage_change")
        self.assertEqual(events[pd.Timestamp("2024-06-03")]["type"], "three_month")
        self.assertNotIn(pd.Timestamp("2024-05-01"), events)

    def test_stage_change_on_due_month_replaces_three_month_rebalance(self) -> None:
        pring = make_pring([("2023-12-31", 1), ("2024-04-30", 2)])
        dates = pd.bdate_range("2024-01-02", "2024-05-03")
        events = server.build_rebalance_events(pring, dates)
        self.assertEqual(events[pd.Timestamp("2024-05-01")]["type"], "stage_change")
        self.assertEqual(sum(event["type"] == "three_month" for event in events.values()), 0)

    def test_weekend_month_end_uses_next_trading_day(self) -> None:
        pring = make_pring([("2024-07-31", 1), ("2024-08-31", 8)])
        dates = pd.bdate_range("2024-08-01", "2024-09-04")
        events = server.build_rebalance_events(pring, dates)
        self.assertEqual(events[pd.Timestamp("2024-09-02")]["type"], "stage_change")
        self.assertEqual(events[pd.Timestamp("2024-09-02")]["stage"], 8)


class PortfolioAccountingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.active = {
            "equity": ["e1", "e2"],
            "commodity": ["c1"],
            "convertible": ["cb1"],
            "pure_bond": ["b1", "b2"],
        }

    def test_holdings_drift_between_rebalances_and_reset_equal(self) -> None:
        targets = server.stage_target_weights(2)
        main, escape = server.rebalance_values(1.0, targets, self.active)
        server.apply_returns(
            main,
            escape,
            pd.Series({"e1": 0.10, "e2": 0.0, "c1": 0.0, "cb1": 0.0, "b1": 0.0, "b2": 0.0}),
        )
        self.assertGreater(main["e1"], main["e2"])
        total = server.portfolio_total(main, escape)
        main, escape = server.rebalance_values(total, targets, self.active)
        self.assertAlmostEqual(main["e1"], main["e2"])
        self.assertAlmostEqual(server.portfolio_total(main, escape), total)

    def test_kst_windows_and_calculation(self) -> None:
        dates = pd.bdate_range("2020-01-01", periods=360)
        nav = pd.Series(1.0 + pd.RangeIndex(len(dates)) / 1000.0, index=dates)
        result = server.build_long_kst(nav)

        self.assertEqual(result["kst"].first_valid_index(), dates[279])
        self.assertEqual(result["slope10"].first_valid_index(), dates[289])
        self.assertEqual(result["signal"].first_valid_index(), dates[298])

        expected = 0.0
        for roc_period, smooth_period, weight in server.KST_COMPONENTS:
            roc = nav / nav.shift(roc_period) - 1.0
            expected += float(roc.iloc[-smooth_period:].mean()) * weight
        self.assertAlmostEqual(result["kst"].iloc[-1], expected, places=12)

    def test_risk_state_uses_three_tiers_and_warmup_exit(self) -> None:
        date = pd.Timestamp("2024-07-01")
        index = pd.DatetimeIndex([date])
        ma20 = pd.Series([1.0], index=index)

        above = server.risk_state_for_date(
            "equity",
            True,
            pd.Series([1.01], index=index),
            ma20,
            make_kst(index, kst=-1.0, signal=1.0, slope=-1.0),
            date,
        )
        self.assertEqual(above["targetScale"], 1.0)

        partial = server.risk_state_for_date(
            "equity",
            True,
            pd.Series([0.99], index=index),
            ma20,
            make_kst(index, kst=0.5, signal=0.4, slope=-0.1),
            date,
        )
        self.assertAlmostEqual(partial["targetScale"], 4.0 / 7.0)
        self.assertFalse(partial["kstWeak"])

        exit_state = server.risk_state_for_date(
            "equity",
            True,
            pd.Series([0.99], index=index),
            ma20,
            make_kst(index, kst=0.3, signal=0.4, slope=-0.1),
            date,
        )
        self.assertEqual(exit_state["targetScale"], 0.0)
        self.assertTrue(exit_state["kstWeak"])

        warmup = server.risk_state_for_date(
            "equity",
            True,
            pd.Series([0.99], index=index),
            ma20,
            make_kst(index),
            date,
        )
        self.assertEqual(warmup["targetScale"], 0.0)
        self.assertFalse(warmup["kstReady"])

    def test_risk_calibration_only_changes_dominant_and_pure_bond(self) -> None:
        main, _ = server.rebalance_values(1.0, server.stage_target_weights(2), self.active)
        untouched_commodity = main["c1"]
        untouched_convertible = main["cb1"]

        applied = server.calibrate_risk_pair(main, "equity", self.active, 0.40)
        weights = server.category_weights(main, {}, self.active)

        self.assertAlmostEqual(applied, 0.40)
        self.assertAlmostEqual(weights["equity"], 0.40)
        self.assertAlmostEqual(weights["pure_bond"], 0.40)
        self.assertAlmostEqual(main["c1"], untouched_commodity)
        self.assertAlmostEqual(main["cb1"], untouched_convertible)

    def test_full_rebalance_applies_current_risk_tier(self) -> None:
        weights = server.risk_adjusted_weights(2, {"targetScale": 4.0 / 7.0})
        self.assertAlmostEqual(weights["equity"], 0.40)
        self.assertAlmostEqual(weights["commodity"], 0.10)
        self.assertAlmostEqual(weights["convertible"], 0.10)
        self.assertAlmostEqual(weights["pure_bond"], 0.40)
        self.assertEqual(
            server.risk_adjusted_weights(1, {"targetScale": 0.0}),
            server.stage_target_weights(1),
        )

    def test_custom_dominant_weight_scales_risk_tier_by_four_sevenths(self) -> None:
        custom = server.parse_stage_weights(server.default_stage_weights())
        custom[2] = {
            "equity": 0.60,
            "commodity": 0.15,
            "convertible": 0.10,
            "pure_bond": 0.15,
        }
        weights = server.risk_adjusted_weights(
            2,
            {"targetScale": 4.0 / 7.0},
            custom,
        )
        self.assertAlmostEqual(weights["equity"], 0.60 * 4.0 / 7.0)
        self.assertAlmostEqual(weights["commodity"], 0.15)
        self.assertAlmostEqual(weights["convertible"], 0.10)
        self.assertAlmostEqual(
            weights["pure_bond"],
            0.15 + 0.60 * 3.0 / 7.0,
        )

    def test_risk_uses_dynamic_dominant_instead_of_default_stage_mapping(self) -> None:
        custom = server.parse_stage_weights(server.default_stage_weights())
        custom[1] = {
            "equity": 0.60,
            "commodity": 0.15,
            "convertible": 0.10,
            "pure_bond": 0.15,
        }
        weights = server.risk_adjusted_weights(
            1,
            {"targetScale": 4.0 / 7.0},
            custom,
        )
        self.assertAlmostEqual(weights["equity"], 0.60 * 4.0 / 7.0)
        self.assertAlmostEqual(weights["convertible"], 0.10)
        self.assertAlmostEqual(weights["pure_bond"], 0.15 + 0.60 * 3.0 / 7.0)

    def test_requested_date_range_is_clipped_to_common_trading_days(self) -> None:
        dates = pd.bdate_range("2022-01-03", "2024-12-31")
        all_dates, selected, window = server.select_backtest_dates(
            dates,
            pd.Timestamp("2021-12-31"),
            {"start": "2023-01-01", "end": "2024-06-30"},
        )
        self.assertEqual(all_dates[0], pd.Timestamp("2022-01-03"))
        self.assertEqual(selected[0], pd.Timestamp("2023-01-02"))
        self.assertEqual(selected[-1], pd.Timestamp("2024-06-28"))
        self.assertEqual(window["requestedStart"], "2023-01-01")
        self.assertEqual(window["requestedEnd"], "2024-06-30")

    def test_requested_date_range_rejects_dates_outside_common_window(self) -> None:
        dates = pd.bdate_range("2022-01-03", "2024-12-31")
        with self.assertRaisesRegex(ValueError, "不能早于共同可用起点"):
            server.select_backtest_dates(
                dates,
                pd.Timestamp("2021-12-31"),
                {"start": "2022-01-01"},
            )
        with self.assertRaisesRegex(ValueError, "不能晚于共同可用终点"):
            server.select_backtest_dates(
                dates,
                pd.Timestamp("2021-12-31"),
                {"end": "2025-01-01"},
            )


class BacktestIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        server.store.ensure_loaded()

    def test_no_ma20_matches_theory_and_attribution_reconciles(self) -> None:
        result = server.run_backtest(
            {
                "baskets": server.store.default_selection(),
                "spliceSimulation": {"enabled": False, "baskets": {}},
                "ma20Controls": {"equity": False, "commodity": False},
            }
        )
        for row in result["series"]:
            self.assertAlmostEqual(row["strategy"], row["theory"], places=6)
            weight_sum = (
                row["equityWeight"]
                + row["commodityWeight"]
                + row["convertibleWeight"]
                + row["pureBondWeight"]
            )
            self.assertAlmostEqual(weight_sum, 1.0, places=5)
        final_return = result["series"][-1]["strategy"] - 1.0
        self.assertAlmostEqual(final_return, result["contributionSummary"]["totalPoints"], places=6)
        self.assertTrue(
            all(
                {"stage", "dominantAsset", "rebalanceType"}.issubset(log)
                for log in result["tradeLogs"]
            )
        )
        stats = result["rebalanceStats"]
        self.assertEqual(stats["strategyTotal"], stats["stageChanges"] + stats["threeMonth"])

    def test_splice_switch_preserves_accounting(self) -> None:
        result = server.run_backtest(
            {
                "baskets": fund_selection(),
                "spliceSimulation": {
                    "enabled": True,
                    "baskets": {
                        "equity": ["index:000300.SH"],
                        "commodity": ["index:NHCI.NH"],
                        "convertible": ["index:931078.CSI"],
                        "pure_bond": ["index:H11001.CSI"],
                    },
                },
                "ma20Controls": {"equity": True, "commodity": True},
            }
        )
        self.assertEqual(result["window"]["start"], "2016-04-01")
        self.assertTrue(result["spliceContext"]["enabled"])
        self.assertTrue(
            any(log["rebalanceType"] == "splice_switch" for log in result["tradeLogs"])
        )
        final_return = result["series"][-1]["strategy"] - 1.0
        self.assertAlmostEqual(final_return, result["contributionSummary"]["totalPoints"], places=6)

    def test_custom_stage_weights_are_applied_to_portfolio(self) -> None:
        custom = server.default_stage_weights()
        custom["2"] = {
            "equity": 0.60,
            "commodity": 0.15,
            "convertible": 0.10,
            "pure_bond": 0.15,
        }
        result = server.run_backtest(
            {
                "baskets": server.store.default_selection(),
                "spliceSimulation": {"enabled": False, "baskets": {}},
                "ma20Controls": {"equity": False, "commodity": False},
                "stageWeights": custom,
            }
        )
        self.assertEqual(result["stageWeights"]["2"], custom["2"])
        stage_two_log = next(
            log
            for log in result["tradeLogs"]
            if log["stage"] == 2
            and log["rebalanceType"] in {"initial", "stage_change", "three_month"}
        )
        self.assertAlmostEqual(stage_two_log["equityWeight"], 0.60)
        self.assertAlmostEqual(stage_two_log["commodityWeight"], 0.15)

    def test_stage_attribution_is_chronological_and_reconciles(self) -> None:
        result = server.run_backtest(
            {
                "baskets": server.store.default_selection(),
                "spliceSimulation": {"enabled": False, "baskets": {}},
                "ma20Controls": {"equity": True, "commodity": True},
            }
        )
        rows = result["stageAttribution"]
        self.assertTrue(rows)
        self.assertEqual(rows, sorted(rows, key=lambda row: row["start"]))
        self.assertEqual(rows[0]["start"], result["window"]["start"])
        self.assertEqual(rows[-1]["end"], result["window"]["end"])

        daily_stages = [row["stage"] for row in result["series"]]
        expected_segments = 1 + sum(
            current != previous
            for previous, current in zip(daily_stages, daily_stages[1:])
        )
        self.assertEqual(len(rows), expected_segments)
        for row in rows:
            contribution_total = sum(
                row[f"{category}Contribution"]
                for category in server.CATEGORY_PRIORITY
            )
            self.assertAlmostEqual(
                contribution_total,
                row["strategyReturn"],
                places=5,
            )
            self.assertEqual(
                row["dominantAsset"],
                server.dominant_asset_for_stage(
                    row["stage"],
                    server.parse_stage_weights(result["stageWeights"]),
                ),
            )
            self.assertGreater(row["tradingDays"], 0)
            self.assertGreaterEqual(row["consecutiveMonths"], 1)
            ranked_assets = sorted(
                server.CATEGORY_PRIORITY,
                key=lambda category: (
                    -row[f"{category}Return"],
                    server.CATEGORY_PRIORITY.index(category),
                ),
            )
            self.assertEqual(
                row["dominantRank"],
                ranked_assets.index(row["dominantAsset"]) + 1,
            )

    def test_year_stage_attribution_splits_at_year_end_and_reconciles(self) -> None:
        result = server.run_backtest(
            {
                "baskets": server.store.default_selection(),
                "spliceSimulation": {"enabled": False, "baskets": {}},
                "ma20Controls": {"equity": True, "commodity": True},
            }
        )
        rows = result["yearStageAttribution"]
        self.assertTrue(rows)
        self.assertEqual(rows, sorted(rows, key=lambda row: row["start"]))
        self.assertGreaterEqual(len(rows), len(result["stageAttribution"]))

        daily_keys = [
            (row["date"][:4], row["stage"])
            for row in result["series"]
        ]
        expected_segments = 1 + sum(
            current != previous
            for previous, current in zip(daily_keys, daily_keys[1:])
        )
        self.assertEqual(len(rows), expected_segments)

        for row in rows:
            self.assertEqual(row["start"][:4], row["end"][:4])
            contribution_total = sum(
                row[f"{category}Contribution"]
                for category in server.CATEGORY_PRIORITY
            )
            self.assertAlmostEqual(
                contribution_total,
                row["strategyReturn"],
                places=5,
            )
            ranked_assets = sorted(
                server.CATEGORY_PRIORITY,
                key=lambda category: (
                    -row[f"{category}Return"],
                    server.CATEGORY_PRIORITY.index(category),
                ),
            )
            self.assertEqual(
                row["dominantRank"],
                ranked_assets.index(row["dominantAsset"]) + 1,
            )
            self.assertIn(row["dominantRank"], {1, 2, 3, 4})

    def test_custom_date_range_and_manager_asset(self) -> None:
        baskets = server.store.default_selection()
        baskets["equity"] = ["manager:008134.OF"]
        result = server.run_backtest(
            {
                "baskets": baskets,
                "spliceSimulation": {"enabled": False, "baskets": {}},
                "ma20Controls": {"equity": True, "commodity": True},
                "dateRange": {"start": "2023-01-01", "end": "2024-12-31"},
            }
        )
        self.assertGreaterEqual(result["window"]["start"], "2023-01-01")
        self.assertLessEqual(result["window"]["end"], "2024-12-31")
        self.assertEqual(result["availableWindow"]["requestedStart"], "2023-01-01")
        self.assertEqual(result["availableWindow"]["requestedEnd"], "2024-12-31")
        selected = result["selectedAssets"]["equity"][0]
        self.assertEqual(selected["manager"], "伍旋")
        self.assertEqual(selected["cluster"], "防守压仓")

    def test_risk_logs_use_previous_day_and_ignore_legacy_three_day(self) -> None:
        result = server.run_backtest(
            {
                "baskets": server.store.default_selection(),
                "spliceSimulation": {"enabled": False, "baskets": {}},
                "ma20Controls": {"equity": True, "commodity": True, "convertible": True},
                "ma20ThreeDay": True,
            }
        )
        self.assertNotIn("ma20ThreeDay", result)
        self.assertEqual(result["ma20Controls"], {"equity": True, "commodity": True})
        risk_logs = [
            log for log in result["tradeLogs"] if log["rebalanceType"] == "risk_tier"
        ]
        self.assertTrue(risk_logs)
        for log in risk_logs:
            self.assertLess(log["riskSignalDate"], log["start"])
            self.assertIn(log["riskTier"], {0.0, 0.4, 0.7})
            self.assertTrue(
                {
                    "riskTransition",
                    "ma20Above",
                    "kst",
                    "kstSignal",
                    "kstSlope10",
                    "kstReady",
                    "kstWeak",
                }.issubset(log)
            )
        self.assertEqual(result["rebalanceStats"]["riskActions"], len(risk_logs))

    def test_convertible_dominant_stage_never_uses_risk_tier(self) -> None:
        result = server.run_backtest(
            {
                "baskets": server.store.default_selection(),
                "spliceSimulation": {"enabled": False, "baskets": {}},
                "ma20Controls": {"equity": False, "commodity": False, "convertible": True},
            }
        )
        convertible_events = [
            log
            for log in result["tradeLogs"]
            if log["dominantAsset"] == "convertible"
            and log["rebalanceType"] in {"initial", "stage_change", "three_month"}
        ]
        self.assertTrue(convertible_events)
        self.assertTrue(all(log["riskTier"] == 0.70 for log in convertible_events))


def make_pring(rows: list[tuple[str, int]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "signal_date": pd.to_datetime([date for date, _ in rows]),
            "state": [f"Stage {stage}" for _, stage in rows],
            "stage": [stage for _, stage in rows],
        }
    )


def fund_selection() -> dict[str, list[str]]:
    return {
        "equity": ["fund:510300.SH"],
        "commodity": [
            "fund:159980.SZ",
            "fund:518880.SH",
            "fund:159981.SZ",
            "fund:159985.SZ",
        ],
        "convertible": ["fund:511380.SH"],
        "pure_bond": ["fund:166016.SZ"],
    }


def make_kst(
    index: pd.DatetimeIndex,
    kst: float | None = None,
    signal: float | None = None,
    slope: float | None = None,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "kst": [kst],
            "signal": [signal],
            "slope10": [slope],
        },
        index=index,
        dtype=float,
    )


if __name__ == "__main__":
    unittest.main()
