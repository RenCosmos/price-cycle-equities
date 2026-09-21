from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys


SCRIPT_ROOT = (
    Path(__file__).resolve().parents[1]
    / ".agents"
    / "skills"
    / "price-cycle-equities"
    / "scripts"
)
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from price_cycle.models import Bar, DataSet, Market, PriceBasis


def make_bars(
    count: int,
    *,
    start_close: float = 100.0,
    step: float = 1.0,
    half_range: float = 1.0,
    start_date: date = date(2025, 1, 1),
) -> tuple[Bar, ...]:
    bars = []
    for index in range(count):
        close = start_close + step * index
        bars.append(
            Bar(
                session_date=start_date + timedelta(days=index),
                open=close,
                high=close + half_range,
                low=close - half_range,
                close=close,
                volume=float(index + 1),
            )
        )
    return tuple(bars)


def make_dataset(
    bars: tuple[Bar, ...],
    *,
    benchmark_bars: tuple[Bar, ...] = (),
    market: Market = Market.US,
) -> DataSet:
    return DataSet(
        instrument_id=f"{market.value}:TEST",
        symbol="TEST",
        market=market,
        as_of=bars[-1].session_date,
        source="synthetic-test",
        price_basis=PriceBasis.RAW,
        bars=bars,
        benchmark_symbol="BENCH" if benchmark_bars else None,
        benchmark_bars=benchmark_bars,
    )
