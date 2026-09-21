from __future__ import annotations

from collections.abc import Sequence
from math import fsum

from .models import Bar, DataSet, FeatureRow
from .parameters import ResearchParameters


def _validate_period(period: int) -> None:
    if period <= 0:
        raise ValueError("period must be positive")


def sma(values: Sequence[float], period: int) -> list[float | None]:
    _validate_period(period)
    result: list[float | None] = [None] * len(values)
    for index in range(period - 1, len(values)):
        result[index] = fsum(values[index - period + 1 : index + 1]) / period
    return result


def ema(values: Sequence[float], period: int) -> list[float | None]:
    """EMA seeded with the first period's simple moving average."""
    _validate_period(period)
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return result
    seed = fsum(values[:period]) / period
    result[period - 1] = seed
    multiplier = 2.0 / (period + 1.0)
    previous = seed
    for index in range(period, len(values)):
        previous = (values[index] - previous) * multiplier + previous
        result[index] = previous
    return result


def true_ranges(bars: Sequence[Bar]) -> list[float]:
    result: list[float] = []
    for index, bar in enumerate(bars):
        if index == 0:
            result.append(bar.high - bar.low)
            continue
        previous_close = bars[index - 1].close
        result.append(
            max(
                bar.high - bar.low,
                abs(bar.high - previous_close),
                abs(bar.low - previous_close),
            )
        )
    return result


def wilder_average(values: Sequence[float], period: int) -> list[float | None]:
    _validate_period(period)
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return result
    previous = fsum(values[:period]) / period
    result[period - 1] = previous
    for index in range(period, len(values)):
        previous = ((period - 1) * previous + values[index]) / period
        result[index] = previous
    return result


def atr(bars: Sequence[Bar], period: int) -> list[float | None]:
    return wilder_average(true_ranges(bars), period)


def prior_rolling_high(values: Sequence[float], period: int) -> list[float | None]:
    _validate_period(period)
    return [
        None if index < period else max(values[index - period : index])
        for index in range(len(values))
    ]


def prior_rolling_low(values: Sequence[float], period: int) -> list[float | None]:
    _validate_period(period)
    return [
        None if index < period else min(values[index - period : index])
        for index in range(len(values))
    ]


def period_returns(values: Sequence[float], period: int) -> list[float | None]:
    _validate_period(period)
    result: list[float | None] = [None] * len(values)
    for index in range(period, len(values)):
        base = values[index - period]
        if base != 0:
            result[index] = values[index] / base - 1.0
    return result


def _slopes(values: Sequence[float | None]) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    for index in range(1, len(values)):
        current = values[index]
        previous = values[index - 1]
        if current is not None and previous is not None and previous != 0:
            result[index] = current / previous - 1.0
    return result


def _benchmark_relative_series(
    dataset: DataSet,
    period: int,
) -> list[float | None]:
    if not dataset.benchmark_bars:
        return [None] * len(dataset.bars)
    benchmark_close_by_date = {
        bar.session_date: bar.close for bar in dataset.benchmark_bars
    }
    result: list[float | None] = [None] * len(dataset.bars)
    for index in range(period, len(dataset.bars)):
        current_bar = dataset.bars[index]
        base_bar = dataset.bars[index - period]
        current_benchmark = benchmark_close_by_date.get(current_bar.session_date)
        base_benchmark = benchmark_close_by_date.get(base_bar.session_date)
        if current_benchmark is None or base_benchmark is None:
            continue
        stock_ratio = current_bar.close / base_bar.close
        benchmark_ratio = current_benchmark / base_benchmark
        if benchmark_ratio > 0:
            result[index] = stock_ratio / benchmark_ratio - 1.0
    return result


def build_features(
    dataset: DataSet,
    parameters: ResearchParameters | None = None,
) -> tuple[FeatureRow, ...]:
    params = parameters or ResearchParameters()
    bars = dataset.bars
    closes = [bar.close for bar in bars]
    highs = [bar.high for bar in bars]
    lows = [bar.low for bar in bars]
    volumes = [bar.volume for bar in bars]
    ranges = [(bar.high - bar.low) / bar.close for bar in bars]

    ema10 = ema(closes, params.ema_short_period)
    ema20 = ema(closes, params.ema_medium_period)
    sma50 = sma(closes, params.sma_intermediate_period)
    sma200 = sma(closes, params.sma_long_period)
    atr14 = atr(bars, params.atr_period)
    volume_sma20 = sma(volumes, params.volume_average_period)
    prior_high20 = prior_rolling_high(highs, params.breakout_lookback)
    prior_low20 = prior_rolling_low(lows, params.breakout_lookback)
    range_sma10 = sma(ranges, params.contraction_short_period)
    range_sma20 = sma(ranges, params.contraction_long_period)
    return_5 = period_returns(closes, 5)
    return_20 = period_returns(closes, 20)
    return_60 = period_returns(closes, 60)
    relative_strength_20 = _benchmark_relative_series(dataset, 20)
    relative_strength_60 = _benchmark_relative_series(dataset, 60)
    ema10_slope = _slopes(ema10)
    ema20_slope = _slopes(ema20)

    rows: list[FeatureRow] = []
    for index, bar in enumerate(bars):
        average_volume = volume_sma20[index]
        current_atr = atr14[index]
        short_range = range_sma10[index]
        long_range = range_sma20[index]
        current_ema10 = ema10[index]
        current_ema20 = ema20[index]

        volume_ratio = (
            bar.volume / average_volume
            if average_volume is not None and average_volume > 0
            else None
        )
        range_ratio = (
            short_range / long_range
            if short_range is not None and long_range is not None and long_range > 0
            else None
        )
        if bar.high == bar.low:
            close_location = None
        else:
            close_location = (bar.close - bar.low) / (bar.high - bar.low)

        distance_ema20_atr = (
            (bar.close - current_ema20) / current_atr
            if current_ema20 is not None
            and current_atr is not None
            and current_atr > 0
            else None
        )
        ema_spread_atr = (
            (current_ema10 - current_ema20) / current_atr
            if current_ema10 is not None
            and current_ema20 is not None
            and current_atr is not None
            and current_atr > 0
            else None
        )

        rows.append(
            FeatureRow(
                bar=bar,
                ema10=current_ema10,
                ema20=current_ema20,
                sma50=sma50[index],
                sma200=sma200[index],
                atr14=current_atr,
                volume_sma20=average_volume,
                prior_high20=prior_high20[index],
                prior_low20=prior_low20[index],
                range_sma10=short_range,
                range_sma20=long_range,
                return_5=return_5[index],
                return_20=return_20[index],
                return_60=return_60[index],
                relative_strength_20=relative_strength_20[index],
                relative_strength_60=relative_strength_60[index],
                ema10_slope=ema10_slope[index],
                ema20_slope=ema20_slope[index],
                distance_ema20_atr=distance_ema20_atr,
                ema_spread_atr=ema_spread_atr,
                volume_ratio=volume_ratio,
                range_ratio=range_ratio,
                close_location=close_location,
            )
        )
    return tuple(rows)
