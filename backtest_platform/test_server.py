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

    def test_default_equity_contains_only_hs300_fund(self) -> None:
        self.assertEqual(server.store.default_selection()["equity"], ["fund:510300.SH"])

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

    def test_ma20_escape_lot_returns_to_dominant_asset(self) -> None:
        main, escape = server.rebalance_values(1.0, server.stage_target_weights(2), self.active)
        untouched_commodity = main["c1"]
        main, escape = server.exit_to_pure_bond(main, escape, "equity", self.active)
        self.assertAlmostEqual(sum(escape.values()), 0.70)
        server.apply_returns(
            main,
            escape,
            pd.Series({"e1": 0.0, "e2": 0.0, "c1": 0.0, "cb1": 0.0, "b1": 0.10, "b2": 0.0}),
        )
        total_before_reentry = server.portfolio_total(main, escape)
        main, escape = server.reenter_from_pure_bond(main, escape, "equity", self.active)
        self.assertFalse(escape)
        self.assertAlmostEqual(main["e1"], main["e2"])
        self.assertAlmostEqual(main["c1"], untouched_commodity)
        self.assertAlmostEqual(server.portfolio_total(main, escape), total_before_reentry)

    def test_three_day_ma20_reentry_applies_on_next_trading_day(self) -> None:
        dates = pd.bdate_range("2024-07-01", periods=4)
        nav = pd.Series([1.01, 1.02, 1.03, 1.04], index=dates)
        ma20 = pd.Series([1.00, 1.00, 1.00, 1.00], index=dates)
        self.assertFalse(
            server.ma20_escape_state(
                nav,
                ma20,
                dates,
                position=3,
                currently_escaped=True,
                confirmation_days=3,
            )
        )

    def test_three_day_ma20_requires_consecutive_closes(self) -> None:
        dates = pd.bdate_range("2024-07-01", periods=4)
        nav = pd.Series([0.99, 1.01, 0.98, 0.97], index=dates)
        ma20 = pd.Series([1.00, 1.00, 1.00, 1.00], index=dates)
        self.assertFalse(
            server.ma20_escape_state(
                nav,
                ma20,
                dates,
                position=3,
                currently_escaped=False,
                confirmation_days=3,
            )
        )
        self.assertTrue(
            server.ma20_escape_state(
                pd.Series([0.99, 0.98, 0.97, 1.01], index=dates),
                ma20,
                dates,
                position=3,
                currently_escaped=False,
                confirmation_days=3,
            )
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
                "ma20Controls": {"equity": False, "commodity": False, "convertible": False},
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
                "baskets": server.store.default_selection(),
                "spliceSimulation": {
                    "enabled": True,
                    "baskets": {
                        "equity": ["index:000300.SH"],
                        "commodity": ["index:NHCI.NH"],
                        "convertible": ["index:931078.CSI"],
                        "pure_bond": ["index:H11001.CSI"],
                    },
                },
                "ma20Controls": {"equity": True, "commodity": True, "convertible": True},
            }
        )
        self.assertEqual(result["window"]["start"], "2016-04-01")
        self.assertTrue(result["spliceContext"]["enabled"])
        self.assertTrue(
            any(log["rebalanceType"] == "splice_switch" for log in result["tradeLogs"])
        )
        final_return = result["series"][-1]["strategy"] - 1.0
        self.assertAlmostEqual(final_return, result["contributionSummary"]["totalPoints"], places=6)

    def test_three_day_ma20_mode_is_returned_and_logged(self) -> None:
        result = server.run_backtest(
            {
                "baskets": server.store.default_selection(),
                "spliceSimulation": {"enabled": False, "baskets": {}},
                "ma20Controls": {"equity": True, "commodity": True, "convertible": True},
                "ma20ThreeDay": True,
            }
        )
        self.assertTrue(result["ma20ThreeDay"])
        ma20_logs = [
            log for log in result["tradeLogs"] if log["rebalanceType"].startswith("ma20")
        ]
        self.assertTrue(ma20_logs)
        self.assertTrue(all("连续3日" in log["reason"] for log in ma20_logs))


def make_pring(rows: list[tuple[str, int]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "signal_date": pd.to_datetime([date for date, _ in rows]),
            "state": [f"Stage {stage}" for _, stage in rows],
            "stage": [stage for _, stage in rows],
        }
    )


if __name__ == "__main__":
    unittest.main()
