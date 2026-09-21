from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
import math
from typing import Any


class Market(str, Enum):
    CN = "CN"
    US = "US"


class PriceBasis(str, Enum):
    RAW = "raw"
    SPLIT_ADJUSTED = "split_adjusted"
    TOTAL_RETURN = "total_return"


class TriState(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


class Provenance(str, Enum):
    SOURCE_RULE = "source_rule"
    AUTHOR_INTERPRETATION = "author_interpretation"
    MARKET_ADAPTATION = "market_adaptation"
    RESEARCH_PARAMETER = "research_parameter"
    USER_OVERRIDE = "user_override"


@dataclass(frozen=True, slots=True)
class Bar:
    session_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    known_at: datetime | None = None

    def __post_init__(self) -> None:
        values = (self.open, self.high, self.low, self.close, self.volume)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Bar values must be finite numbers")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("OHLC prices must be greater than zero")
        if self.volume < 0:
            raise ValueError("Volume cannot be negative")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("High must be at least open, low, and close")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("Low must be at most open, high, and close")
        if self.known_at is not None and self.known_at.tzinfo is None:
            raise ValueError("known_at must include a timezone when provided")


@dataclass(frozen=True, slots=True)
class DataSet:
    instrument_id: str
    symbol: str
    market: Market
    as_of: date
    source: str
    price_basis: PriceBasis
    bars: tuple[Bar, ...]
    venue: str | None = None
    segment: str | None = None
    security_type: str = "COMMON_STOCK"
    benchmark_symbol: str | None = None
    benchmark_bars: tuple[Bar, ...] = ()
    timestamp_policy: str = "session_date_known_after_close"

    def __post_init__(self) -> None:
        if not self.instrument_id.strip():
            raise ValueError("instrument_id is required")
        if not self.symbol.strip():
            raise ValueError("symbol is required")
        if not self.source.strip():
            raise ValueError("source is required")
        if not self.security_type.strip():
            raise ValueError("security_type is required")
        if not self.bars:
            raise ValueError("At least one price bar is required")
        self._validate_bar_sequence(self.bars, "instrument")
        if self.benchmark_bars:
            self._validate_bar_sequence(self.benchmark_bars, "benchmark")
        if any(bar.session_date > self.as_of for bar in self.bars):
            raise ValueError("Dataset contains a bar after as_of")
        if any(bar.session_date > self.as_of for bar in self.benchmark_bars):
            raise ValueError("Dataset contains a benchmark bar after as_of")
        if not self.timestamp_policy.strip():
            raise ValueError("timestamp_policy is required")

    @staticmethod
    def _validate_bar_sequence(bars: tuple[Bar, ...], label: str) -> None:
        dates = [bar.session_date for bar in bars]
        if dates != sorted(dates):
            raise ValueError(f"{label} bars must be sorted by session_date")
        if len(dates) != len(set(dates)):
            raise ValueError(f"{label} bars contain duplicate session dates")


@dataclass(frozen=True, slots=True)
class FeatureRow:
    bar: Bar
    ema10: float | None
    ema20: float | None
    sma50: float | None
    sma200: float | None
    atr14: float | None
    volume_sma20: float | None
    prior_high20: float | None
    prior_low20: float | None
    range_sma10: float | None
    range_sma20: float | None
    return_5: float | None
    return_20: float | None
    return_60: float | None
    relative_strength_20: float | None
    relative_strength_60: float | None
    ema10_slope: float | None
    ema20_slope: float | None
    distance_ema20_atr: float | None
    ema_spread_atr: float | None
    volume_ratio: float | None
    range_ratio: float | None
    close_location: float | None


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    rule_id: str
    status: TriState
    message: str
    provenance: Provenance
    weight: float = 1.0
    value: float | str | None = None
    threshold: float | str | None = None


@dataclass(frozen=True, slots=True)
class ObservedEvent:
    event_id: str
    event_type: str
    session_date: date
    known_at: datetime | None
    bar_index: int
    leg_id: str
    anchor_event_id: str | None
    sequence_no: int | None
    payload: tuple[tuple[str, float | int | str], ...]
    evidence: tuple[EvidenceItem, ...]


@dataclass(frozen=True, slots=True)
class PhaseAssessment:
    phase: str
    score: float
    confidence: str
    evidence_for: tuple[EvidenceItem, ...]
    evidence_against: tuple[EvidenceItem, ...]
    unknowns: tuple[EvidenceItem, ...]

    def __post_init__(self) -> None:
        if not -1.0 <= self.score <= 1.0:
            raise ValueError("Phase score must be between -1 and 1")


def json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, tuple):
        return [json_value(item) for item in value]
    if isinstance(value, list):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if hasattr(value, "__dataclass_fields__"):
        return {
            field_name: json_value(getattr(value, field_name))
            for field_name in value.__dataclass_fields__
        }
    return value
