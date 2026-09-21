from __future__ import annotations

from datetime import date, timedelta
import unittest

from tests.helpers import SCRIPT_ROOT

from price_cycle.cycle import PHASES, assess_current, detect_events
from price_cycle.models import Bar, FeatureRow


START = date(2025, 1, 1)


def feature_row(
    index: int,
    *,
    close: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    ema10: float = 100.0,
    ema20: float = 100.0,
    ema10_slope: float = 0.0,
    ema20_slope: float = 0.0,
    prior_high: float = 110.0,
    prior_low: float = 90.0,
    range_ratio: float = 1.0,
    volume_ratio: float = 1.0,
    distance: float = 0.0,
) -> FeatureRow:
    close_location = None if high == low else (close - low) / (high - low)
    return FeatureRow(
        bar=Bar(
            session_date=START + timedelta(days=index),
            open=close,
            high=high,
            low=low,
            close=close,
            volume=1000.0,
        ),
        ema10=ema10,
        ema20=ema20,
        sma50=99.0,
        sma200=None,
        atr14=2.0,
        volume_sma20=1000.0,
        prior_high20=prior_high,
        prior_low20=prior_low,
        range_sma10=0.02,
        range_sma20=0.025,
        return_5=0.02,
        return_20=0.05,
        return_60=None,
        relative_strength_20=None,
        relative_strength_60=None,
        ema10_slope=ema10_slope,
        ema20_slope=ema20_slope,
        distance_ema20_atr=distance,
        ema_spread_atr=(ema10 - ema20) / 2.0,
        volume_ratio=volume_ratio,
        range_ratio=range_ratio,
        close_location=close_location,
    )


def neutral_prefix() -> list[FeatureRow]:
    return [feature_row(index) for index in range(60)]


def wedge_pop(index: int) -> FeatureRow:
    return feature_row(
        index,
        close=110.5,
        high=111.0,
        low=109.0,
        ema10=105.0,
        ema20=104.2,
        ema10_slope=0.01,
        ema20_slope=0.008,
        prior_high=108.0,
        range_ratio=0.80,
        volume_ratio=1.30,
        distance=3.15,
    )


def up_continuation(index: int) -> FeatureRow:
    return feature_row(
        index,
        close=110.0,
        high=111.0,
        low=108.0,
        ema10=105.5,
        ema20=104.8,
        ema10_slope=0.005,
        ema20_slope=0.004,
        prior_high=112.0,
        range_ratio=0.90,
        volume_ratio=0.90,
        distance=2.6,
    )


def up_crossback(index: int) -> FeatureRow:
    return feature_row(
        index,
        close=107.5,
        high=108.0,
        low=104.5,
        ema10=105.5,
        ema20=105.0,
        ema10_slope=0.003,
        ema20_slope=0.002,
        prior_high=112.0,
        range_ratio=0.80,
        volume_ratio=0.80,
        distance=1.25,
    )


class CycleEvidenceTests(unittest.TestCase):
    def test_first_upside_crossback_is_consumed_once(self) -> None:
        rows = neutral_prefix()
        rows.append(wedge_pop(60))
        rows.append(up_continuation(61))
        rows.append(up_crossback(62))
        rows.append(up_continuation(63))
        rows.append(up_crossback(64))
        events = detect_events(tuple(rows), instrument_id="US:TEST")
        crossbacks = [
            event for event in events
            if event.event_type == "UPSIDE_EMA_CROSSBACK"
        ]
        self.assertEqual(len(crossbacks), 1)
        self.assertEqual(crossbacks[0].bar_index, 62)
        self.assertIsNotNone(crossbacks[0].anchor_event_id)

    def test_base_n_break_can_repeat_with_sequence_numbers(self) -> None:
        rows = neutral_prefix()
        rows.append(wedge_pop(60))
        rows.extend(up_continuation(index) for index in range(61, 66))
        rows.append(
            feature_row(
                66,
                close=114.5,
                high=115.0,
                low=112.0,
                ema10=109.0,
                ema20=107.5,
                ema10_slope=0.005,
                ema20_slope=0.004,
                prior_high=113.0,
                range_ratio=0.80,
                volume_ratio=1.30,
                distance=3.5,
            )
        )
        rows.extend(up_continuation(index) for index in range(67, 72))
        rows.append(
            feature_row(
                72,
                close=117.5,
                high=118.0,
                low=116.0,
                ema10=112.0,
                ema20=110.5,
                ema10_slope=0.004,
                ema20_slope=0.003,
                prior_high=116.5,
                range_ratio=0.80,
                volume_ratio=1.30,
                distance=3.5,
            )
        )
        events = detect_events(tuple(rows), instrument_id="US:TEST")
        breaks = [
            event for event in events
            if event.event_type == "UPSIDE_BASE_N_BREAK"
        ]
        self.assertEqual([event.sequence_no for event in breaks], [1, 2])
        self.assertEqual(len({event.event_id for event in breaks}), 2)

    def test_first_downside_crossback_is_consumed_once(self) -> None:
        rows = neutral_prefix()
        rows.append(wedge_pop(60))
        rows.extend(up_continuation(index) for index in range(61, 65))
        rows.append(
            feature_row(
                65,
                close=100.0,
                high=102.0,
                low=99.5,
                ema10=105.0,
                ema20=104.0,
                ema10_slope=-0.01,
                ema20_slope=-0.005,
                prior_high=112.0,
                range_ratio=1.1,
                volume_ratio=1.3,
                distance=-2.0,
            )
        )
        rows.append(
            feature_row(
                66,
                close=100.0,
                high=101.0,
                low=99.0,
                ema10=103.5,
                ema20=104.0,
                ema10_slope=-0.005,
                ema20_slope=-0.004,
                prior_low=98.0,
                volume_ratio=0.8,
            )
        )
        rows.append(
            feature_row(
                67,
                close=100.5,
                high=104.2,
                low=100.0,
                ema10=103.0,
                ema20=104.0,
                ema10_slope=-0.005,
                ema20_slope=-0.004,
                prior_low=98.0,
                range_ratio=0.8,
                volume_ratio=0.8,
                distance=-1.75,
            )
        )
        rows.append(
            feature_row(
                68,
                close=99.5,
                high=100.5,
                low=99.0,
                ema10=102.5,
                ema20=103.5,
                ema10_slope=-0.005,
                ema20_slope=-0.004,
                prior_low=98.0,
                volume_ratio=0.8,
            )
        )
        rows.append(
            feature_row(
                69,
                close=100.0,
                high=103.8,
                low=99.5,
                ema10=102.5,
                ema20=103.5,
                ema10_slope=-0.005,
                ema20_slope=-0.004,
                prior_low=98.0,
                volume_ratio=0.8,
            )
        )
        events = detect_events(tuple(rows), instrument_id="US:TEST")
        crossbacks = [
            event for event in events
            if event.event_type == "DOWNSIDE_EMA_CROSSBACK"
        ]
        self.assertEqual(len(crossbacks), 1)
        self.assertEqual(crossbacks[0].bar_index, 67)

    def test_prefix_replay_is_causal_and_ids_are_deterministic(self) -> None:
        rows = neutral_prefix()
        rows.append(wedge_pop(60))
        rows.append(up_continuation(61))
        prefix = tuple(rows)
        prefix_events = detect_events(prefix, instrument_id="CN:TEST")
        rows.extend((up_crossback(62), up_continuation(63)))
        full_events = detect_events(tuple(rows), instrument_id="CN:TEST")
        self.assertEqual(prefix_events, full_events[: len(prefix_events)])
        self.assertEqual(
            full_events,
            detect_events(tuple(rows), instrument_id="CN:TEST"),
        )

    def test_assessments_keep_all_phases_and_are_not_probabilities(self) -> None:
        rows = neutral_prefix()
        rows.append(wedge_pop(60))
        rows.append(up_continuation(61))
        events = detect_events(tuple(rows), instrument_id="US:TEST")
        assessments = assess_current(tuple(rows), events)
        self.assertEqual({item.phase for item in assessments}, set(PHASES))
        self.assertEqual(len(assessments), 8)
        self.assertNotAlmostEqual(sum(item.score for item in assessments), 1.0)

    def test_short_history_keeps_crossback_confidence_unknown(self) -> None:
        rows = tuple(feature_row(index) for index in range(10))
        assessments = assess_current(rows, ())
        by_phase = {item.phase: item for item in assessments}
        self.assertEqual(
            by_phase["Upside EMA Crossback"].confidence,
            "UNKNOWN",
        )
        self.assertEqual(
            by_phase["Downside EMA Crossback"].confidence,
            "UNKNOWN",
        )


if __name__ == "__main__":
    unittest.main()
