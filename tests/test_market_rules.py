from __future__ import annotations

from datetime import date
import unittest

from tests.helpers import SCRIPT_ROOT

from price_cycle.market_rules import RuleResolutionStatus, rules_at
from price_cycle.models import Market, TriState


class MarketRuleTests(unittest.TestCase):
    def test_cn_main_board_rule_is_dated_and_resolved(self) -> None:
        result = rules_at(
            market=Market.CN,
            as_of=date(2026, 9, 18),
            venue="SSE",
            segment="MAIN",
        )
        self.assertEqual(result.status, RuleResolutionStatus.RESOLVED)
        self.assertFalse(result.execution_ready)
        snapshot = result.snapshot
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.valid_from, date(2026, 7, 6))
        self.assertEqual(snapshot.quantity_rule.buy_minimum_shares, 100)
        self.assertEqual(snapshot.quantity_rule.buy_increment_shares, 100)
        self.assertEqual(snapshot.price_rule.standard_daily_limit_pct, 0.10)
        self.assertEqual(snapshot.same_day_resale, TriState.FALSE)
        self.assertTrue(snapshot.sources[0].url.startswith("https://"))

    def test_cn_board_specific_rules_do_not_collapse_to_one_default(self) -> None:
        star = rules_at(
            market=Market.CN,
            as_of=date(2026, 9, 18),
            venue="XSHG",
            segment="STAR",
        ).snapshot
        chinext = rules_at(
            market=Market.CN,
            as_of=date(2026, 9, 18),
            venue="SZSE",
            segment="CHINEXT",
        ).snapshot
        bse = rules_at(
            market=Market.CN,
            as_of=date(2026, 9, 18),
            venue="BSE",
        ).snapshot
        assert star is not None and chinext is not None and bse is not None
        self.assertEqual((star.quantity_rule.buy_minimum_shares, star.quantity_rule.buy_increment_shares), (200, 1))
        self.assertEqual(star.price_rule.standard_daily_limit_pct, 0.20)
        self.assertEqual(chinext.price_rule.standard_daily_limit_pct, 0.20)
        self.assertEqual((bse.quantity_rule.buy_minimum_shares, bse.quantity_rule.buy_increment_shares), (100, 1))
        self.assertEqual(bse.price_rule.standard_daily_limit_pct, 0.30)

    def test_cn_missing_identity_is_partial_and_historical_gap_is_unknown(self) -> None:
        partial = rules_at(market=Market.CN, as_of=date(2026, 9, 18))
        self.assertEqual(partial.status, RuleResolutionStatus.PARTIAL)
        self.assertIn("venue", partial.unknowns)
        self.assertIsNone(partial.snapshot.quantity_rule.buy_minimum_shares)

        historical = rules_at(
            market=Market.CN,
            as_of=date(2026, 7, 5),
            venue="SSE",
            segment="MAIN",
        )
        self.assertEqual(historical.status, RuleResolutionStatus.UNKNOWN)
        self.assertIsNone(historical.snapshot)

    def test_unsupported_cn_combination_fails_closed(self) -> None:
        result = rules_at(
            market=Market.CN,
            as_of=date(2026, 9, 18),
            venue="SSE",
            segment="CHINEXT",
        )
        self.assertEqual(result.status, RuleResolutionStatus.UNKNOWN)
        self.assertFalse(result.execution_ready)

    def test_date_after_last_verification_fails_closed(self) -> None:
        result = rules_at(
            market=Market.CN,
            as_of=date(2026, 9, 22),
            venue="SSE",
            segment="MAIN",
        )
        self.assertEqual(result.status, RuleResolutionStatus.UNKNOWN)
        self.assertIsNone(result.snapshot)
        self.assertIn("verification date", result.unknowns[0])

    def test_us_core_rules_keep_execution_account_dependent(self) -> None:
        result = rules_at(
            market=Market.US,
            as_of=date(2026, 9, 18),
            venue="NYSE",
            security_type="COMMON_STOCK",
        )
        self.assertEqual(result.status, RuleResolutionStatus.RESOLVED)
        self.assertFalse(result.execution_ready)
        snapshot = result.snapshot
        assert snapshot is not None
        self.assertEqual(snapshot.venue, "XNYS")
        self.assertEqual(snapshot.settlement_cycle[:3], "T+1")
        self.assertEqual(snapshot.same_day_resale, TriState.UNKNOWN)
        self.assertEqual(snapshot.regular_sessions[0].start_local, "09:30")
        self.assertEqual(snapshot.regular_sessions[0].end_local, "16:00")
        self.assertIn("BROKER_TRANSITION_STATE_REQUIRED", snapshot.margin_policy)
        self.assertIsNone(snapshot.price_rule.standard_daily_limit_pct)

    def test_us_rule_versions_change_at_effective_date_without_future_leakage(self) -> None:
        before = rules_at(
            market=Market.US,
            as_of=date(2026, 6, 3),
            venue="XNAS",
            security_type="ADR",
        )
        after = rules_at(
            market=Market.US,
            as_of=date(2026, 6, 4),
            venue="XNAS",
            security_type="ADR",
        )
        self.assertEqual(before.status, RuleResolutionStatus.RESOLVED)
        self.assertEqual(after.status, RuleResolutionStatus.RESOLVED)
        self.assertNotEqual(before.rule_version, after.rule_version)
        self.assertNotIn("TRANSITION_STATE", before.snapshot.margin_policy)
        self.assertIn("TRANSITION_STATE", after.snapshot.margin_policy)

    def test_us_missing_venue_is_partial_and_pre_t1_is_unknown(self) -> None:
        partial = rules_at(market=Market.US, as_of=date(2026, 9, 18))
        self.assertEqual(partial.status, RuleResolutionStatus.PARTIAL)
        self.assertIn("venue", partial.unknowns)

        historical = rules_at(
            market=Market.US,
            as_of=date(2024, 5, 27),
            venue="XNYS",
        )
        self.assertEqual(historical.status, RuleResolutionStatus.UNKNOWN)
        self.assertIsNone(historical.snapshot)


if __name__ == "__main__":
    unittest.main()
