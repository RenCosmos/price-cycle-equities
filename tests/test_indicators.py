from __future__ import annotations

from datetime import date, timedelta
import math
import unittest

from tests.helpers import make_bars, make_dataset

from price_cycle.indicators import (
    atr,
    build_features,
    ema,
    period_returns,
    prior_rolling_high,
    sma,
)
from price_cycle.models import Bar, DataSet, Market, PriceBasis


class IndicatorTests(unittest.TestCase):
    def test_warmup_boundaries_and_seeds(self) -> None:
        values = [100.0 + index for index in range(220)]
        ema10 = ema(values, 10)
        ema20 = ema(values, 20)
        sma50 = sma(values, 50)
        sma200 = sma(values, 200)

        self.assertIsNone(ema10[8])
        self.assertAlmostEqual(ema10[9], 104.5)
        self.assertAlmostEqual(ema10[10], 105.5)
        self.assertIsNone(ema20[18])
        self.assertAlmostEqual(ema20[19], 109.5)
        self.assertAlmostEqual(ema20[20], 110.5)
        self.assertIsNone(sma50[48])
        self.assertAlmostEqual(sma50[49], 124.5)
        self.assertIsNone(sma200[198])
        self.assertAlmostEqual(sma200[199], 199.5)

    def test_wilder_atr_seed_and_recursion(self) -> None:
        values = atr(make_bars(20), 14)
        self.assertIsNone(values[12])
        self.assertAlmostEqual(values[13], 2.0)
        self.assertAlmostEqual(values[14], 2.0)

    def test_prior_high_strictly_excludes_current_row(self) -> None:
        highs = [float(index) for index in range(25)]
        highs[20] = 999.0
        result = prior_rolling_high(highs, 20)
        self.assertIsNone(result[19])
        self.assertEqual(result[20], 19.0)
        self.assertEqual(result[21], 999.0)

    def test_returns_use_exact_lag(self) -> None:
        closes = [100.0 + index for index in range(70)]
        self.assertAlmostEqual(period_returns(closes, 5)[5], 0.05)
        self.assertAlmostEqual(period_returns(closes, 20)[20], 0.20)
        self.assertAlmostEqual(period_returns(closes, 60)[60], 0.60)

    def test_normalized_range_contraction_and_close_location(self) -> None:
        bars = []
        for index in range(20):
            half_range = 2.0 if index < 10 else 1.0
            bars.append(
                Bar(
                    session_date=date(2025, 1, 1) + timedelta(days=index),
                    open=100.0,
                    high=100.0 + half_range,
                    low=100.0 - half_range,
                    close=100.0,
                    volume=1000.0,
                )
            )
        features = build_features(make_dataset(tuple(bars)))
        self.assertAlmostEqual(features[-1].range_sma10 or 0.0, 0.02)
        self.assertAlmostEqual(features[-1].range_sma20 or 0.0, 0.03)
        self.assertAlmostEqual(features[-1].range_ratio or 0.0, 2.0 / 3.0)

        flat = Bar(
            session_date=date(2025, 2, 1),
            open=100.0,
            high=100.0,
            low=100.0,
            close=100.0,
            volume=0.0,
        )
        flat_features = build_features(make_dataset((flat,)))
        self.assertIsNone(flat_features[0].close_location)

    def test_relative_strength_uses_exact_date_anchors(self) -> None:
        start = date(2025, 1, 1)
        stock = []
        benchmark = []
        for index in range(21):
            stock_close = 100.0 + index
            benchmark_close = 100.0 + index * 0.5
            stock.append(
                Bar(
                    start + timedelta(days=index),
                    stock_close,
                    stock_close + 1,
                    stock_close - 1,
                    stock_close,
                    1000,
                )
            )
            benchmark.append(
                Bar(
                    start + timedelta(days=index),
                    benchmark_close,
                    benchmark_close + 1,
                    benchmark_close - 1,
                    benchmark_close,
                    1000,
                )
            )
        features = build_features(
            make_dataset(tuple(stock), benchmark_bars=tuple(benchmark))
        )
        expected = 1.2 / 1.1 - 1.0
        self.assertAlmostEqual(features[20].relative_strength_20 or 0.0, expected)

        missing_anchor = tuple(benchmark[1:])
        missing_features = build_features(
            make_dataset(tuple(stock), benchmark_bars=missing_anchor)
        )
        self.assertIsNone(missing_features[20].relative_strength_20)

    def test_future_rows_do_not_change_past_features(self) -> None:
        full_bars = make_bars(120)
        full_benchmark = make_bars(120, start_close=200.0, step=0.5)
        full = build_features(
            make_dataset(full_bars, benchmark_bars=full_benchmark)
        )
        prefix_bars = full_bars[:80]
        prefix_benchmark = full_benchmark[:80]
        prefix = build_features(
            make_dataset(prefix_bars, benchmark_bars=prefix_benchmark)
        )
        self.assertEqual(prefix, full[:80])

    def test_invalid_bar_values_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Bar(date(2025, 1, 1), 100, 99, 98, 100, 1)
        with self.assertRaises(ValueError):
            Bar(date(2025, 1, 1), 100, 101, 99, 100, -1)
        with self.assertRaises(ValueError):
            Bar(date(2025, 1, 1), 100, math.inf, 99, 100, 1)


if __name__ == "__main__":
    unittest.main()
