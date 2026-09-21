from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class ResearchParameters:
    ema_short_period: int = 10
    ema_medium_period: int = 20
    sma_intermediate_period: int = 50
    sma_long_period: int = 200
    atr_period: int = 14
    volume_average_period: int = 20
    breakout_lookback: int = 20
    contraction_short_period: int = 10
    contraction_long_period: int = 20
    event_lookback: int = 15
    reversal_lookback: int = 10
    min_history_bars: int = 60
    recent_event_window: int = 3
    min_bars_between_breaks: int = 5
    event_cooldown_bars: int = 5
    ema_touch_atr: float = 0.35
    ema_tightness_atr: float = 0.55
    contraction_ratio_max: float = 0.85
    volume_confirmation_ratio: float = 1.20
    quiet_volume_ratio: float = 0.95
    extension_atr: float = 2.50
    strong_close_location: float = 0.65
    weak_close_location: float = 0.35
    medium_confidence_score: float = 0.50
    high_confidence_score: float = 0.75

    def __post_init__(self) -> None:
        integer_fields = (
            self.ema_short_period,
            self.ema_medium_period,
            self.sma_intermediate_period,
            self.sma_long_period,
            self.atr_period,
            self.volume_average_period,
            self.breakout_lookback,
            self.contraction_short_period,
            self.contraction_long_period,
            self.event_lookback,
            self.reversal_lookback,
            self.min_history_bars,
            self.recent_event_window,
            self.min_bars_between_breaks,
            self.event_cooldown_bars,
        )
        if any(value <= 0 for value in integer_fields):
            raise ValueError("All lookback periods must be positive")
        if self.ema_short_period >= self.ema_medium_period:
            raise ValueError("Short EMA period must be less than medium EMA period")
        if not 0 < self.contraction_ratio_max <= 1:
            raise ValueError("contraction_ratio_max must be in (0, 1]")
        if not 0 <= self.weak_close_location < self.strong_close_location <= 1:
            raise ValueError("Close-location thresholds are invalid")
        if not 0 <= self.medium_confidence_score < self.high_confidence_score <= 1:
            raise ValueError("Confidence thresholds are invalid")

    def values(self) -> dict[str, int | float]:
        return asdict(self)

    def manifest(self) -> list[dict[str, object]]:
        source_rule = {
            "ema_short_period",
            "ema_medium_period",
            "sma_intermediate_period",
            "sma_long_period",
        }
        return [
            {
                "parameter_id": key,
                "value": value,
                "provenance": (
                    "source_rule" if key in source_rule else "research_parameter"
                ),
                "valid_scope": "daily_equities_v0.1",
                "source_or_rationale": (
                    "strategy-spec CORE-03"
                    if key in source_rule
                    else "experimental default; validate with sensitivity tests"
                ),
            }
            for key, value in self.values().items()
        ]
