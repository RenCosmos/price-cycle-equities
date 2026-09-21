from __future__ import annotations

from hashlib import sha256
from typing import Iterable

from .models import (
    EvidenceItem,
    FeatureRow,
    ObservedEvent,
    PhaseAssessment,
    Provenance,
    TriState,
)
from .parameters import ResearchParameters


PHASES = (
    "Reversal Extension",
    "Wedge Pop",
    "Upside EMA Crossback",
    "Upside Base n' Break",
    "Exhaustion Extension",
    "Wedge Drop",
    "Downside EMA Crossback",
    "Downside Base n' Break",
)

SOURCE_PHASE_FAMILIES = (
    "Reversal Extension",
    "Wedge Pop",
    "EMA Crossback",
    "Base n' Break",
    "Exhaustion Extension",
    "Wedge Drop",
)

# Oliver Kell's public framework names six phase families. The deterministic
# report expands the two direction-dependent families so evidence is explicit.
PHASE_FAMILIES = {
    "Reversal Extension": "Reversal Extension",
    "Wedge Pop": "Wedge Pop",
    "Upside EMA Crossback": "EMA Crossback",
    "Upside Base n' Break": "Base n' Break",
    "Exhaustion Extension": "Exhaustion Extension",
    "Wedge Drop": "Wedge Drop",
    "Downside EMA Crossback": "EMA Crossback",
    "Downside Base n' Break": "Base n' Break",
}

PHASE_DIRECTIONS = {
    "Reversal Extension": "not_applicable",
    "Wedge Pop": "not_applicable",
    "Upside EMA Crossback": "upside",
    "Upside Base n' Break": "upside",
    "Exhaustion Extension": "not_applicable",
    "Wedge Drop": "not_applicable",
    "Downside EMA Crossback": "downside",
    "Downside Base n' Break": "downside",
}

EVENT_FOR_PHASE = {
    "Reversal Extension": "REVERSAL_EXTENSION",
    "Wedge Pop": "WEDGE_POP",
    "Upside EMA Crossback": "UPSIDE_EMA_CROSSBACK",
    "Upside Base n' Break": "UPSIDE_BASE_N_BREAK",
    "Exhaustion Extension": "EXHAUSTION_EXTENSION",
    "Wedge Drop": "WEDGE_DROP",
    "Downside EMA Crossback": "DOWNSIDE_EMA_CROSSBACK",
    "Downside Base n' Break": "DOWNSIDE_BASE_N_BREAK",
}


def _state(condition: bool | None) -> TriState:
    if condition is None:
        return TriState.UNKNOWN
    return TriState.TRUE if condition else TriState.FALSE


def _item(
    rule_id: str,
    condition: bool | None,
    message: str,
    *,
    provenance: Provenance = Provenance.RESEARCH_PARAMETER,
    weight: float = 1.0,
    value: float | str | None = None,
    threshold: float | str | None = None,
) -> EvidenceItem:
    return EvidenceItem(
        rule_id=rule_id,
        status=_state(condition),
        message=message,
        provenance=provenance,
        weight=weight,
        value=value,
        threshold=threshold,
    )


def _band_values(row: FeatureRow) -> tuple[float, float] | None:
    if row.ema10 is None or row.ema20 is None:
        return None
    return min(row.ema10, row.ema20), max(row.ema10, row.ema20)


def _above_band(row: FeatureRow) -> bool | None:
    band = _band_values(row)
    return None if band is None else row.bar.close > band[1]


def _below_band(row: FeatureRow) -> bool | None:
    band = _band_values(row)
    return None if band is None else row.bar.close < band[0]


def _up_slopes(row: FeatureRow) -> bool | None:
    if row.ema10_slope is None or row.ema20_slope is None:
        return None
    return row.ema10_slope > 0 and row.ema20_slope > 0


def _down_slopes(row: FeatureRow) -> bool | None:
    if row.ema10_slope is None or row.ema20_slope is None:
        return None
    return row.ema10_slope < 0 and row.ema20_slope < 0


def _ema_touch(row: FeatureRow, tolerance_atr: float) -> bool | None:
    band = _band_values(row)
    if band is None or row.atr14 is None or row.atr14 <= 0:
        return None
    tolerance = tolerance_atr * row.atr14
    return row.bar.low <= band[1] + tolerance and row.bar.high >= band[0] - tolerance


def _event_id(
    instrument_id: str,
    event_type: str,
    row: FeatureRow,
    leg_id: str,
    anchor_event_id: str | None,
    sequence_no: int | None,
) -> str:
    raw = "|".join(
        (
            instrument_id,
            event_type,
            row.bar.session_date.isoformat(),
            leg_id,
            anchor_event_id or "",
            str(sequence_no or ""),
            "cycle-rules-v0.1.1",
        )
    )
    return sha256(raw.encode("utf-8")).hexdigest()[:20]


def _event(
    *,
    instrument_id: str,
    event_type: str,
    row: FeatureRow,
    bar_index: int,
    leg_id: str,
    anchor_event_id: str | None,
    sequence_no: int | None,
    payload: dict[str, float | int | str],
    evidence: Iterable[EvidenceItem],
) -> ObservedEvent:
    return ObservedEvent(
        event_id=_event_id(
            instrument_id,
            event_type,
            row,
            leg_id,
            anchor_event_id,
            sequence_no,
        ),
        event_type=event_type,
        session_date=row.bar.session_date,
        known_at=row.bar.known_at,
        bar_index=bar_index,
        leg_id=leg_id,
        anchor_event_id=anchor_event_id,
        sequence_no=sequence_no,
        payload=tuple(sorted(payload.items())),
        evidence=tuple(evidence),
    )


def _all_true(*conditions: bool | None) -> bool:
    return all(condition is True for condition in conditions)


def _latest_event(
    events: list[ObservedEvent] | tuple[ObservedEvent, ...],
    event_type: str,
) -> ObservedEvent | None:
    return next(
        (event for event in reversed(events) if event.event_type == event_type),
        None,
    )


def _recent_event(
    events: tuple[ObservedEvent, ...],
    event_type: str,
    latest_index: int,
    window: int,
) -> ObservedEvent | None:
    event = _latest_event(events, event_type)
    if event is None or latest_index - event.bar_index > window:
        return None
    return event


def detect_events(
    features: tuple[FeatureRow, ...],
    *,
    instrument_id: str,
    parameters: ResearchParameters | None = None,
) -> tuple[ObservedEvent, ...]:
    params = parameters or ResearchParameters()
    events: list[ObservedEvent] = []
    direction = "NONE"
    current_leg = "NONE"
    up_leg_count = 0
    down_leg_count = 0
    up_crossback_consumed = False
    down_crossback_consumed = False
    up_base_count = 0
    down_base_count = 0
    last_up_base_index = -10_000
    last_down_base_index = -10_000

    for index, row in enumerate(features):
        previous = features[index - 1] if index > 0 else None
        enough_history = index + 1 >= params.min_history_bars
        strong_close = (
            None
            if row.close_location is None
            else row.close_location >= params.strong_close_location
        )
        weak_close = (
            None
            if row.close_location is None
            else row.close_location <= params.weak_close_location
        )
        volume_confirm = (
            None
            if row.volume_ratio is None
            else row.volume_ratio >= params.volume_confirmation_ratio
        )
        quiet_volume = (
            None
            if row.volume_ratio is None
            else row.volume_ratio <= params.quiet_volume_ratio
        )
        contraction = (
            None
            if row.range_ratio is None
            else row.range_ratio <= params.contraction_ratio_max
        )
        ema_tight = (
            None
            if row.ema_spread_atr is None
            else abs(row.ema_spread_atr) <= params.ema_tightness_atr
        )
        breakout_up = (
            None
            if row.prior_high20 is None
            else row.bar.close > row.prior_high20
        )
        breakout_down = (
            None
            if row.prior_low20 is None
            else row.bar.close < row.prior_low20
        )

        recent_start = max(0, index - params.reversal_lookback + 1)
        recent_distances = [
            feature.distance_ema20_atr
            for feature in features[recent_start : index + 1]
            if feature.distance_ema20_atr is not None
        ]
        deep_negative = (
            None
            if not recent_distances
            else min(recent_distances) <= -params.extension_atr
        )
        last_reversal = _latest_event(events, "REVERSAL_EXTENSION")
        reversal_cooled_down = (
            last_reversal is None
            or index - last_reversal.bar_index >= params.event_cooldown_bars
        )
        reversal_signal = _all_true(
            enough_history,
            deep_negative,
            _above_band(row),
            strong_close,
            reversal_cooled_down,
        )
        if reversal_signal:
            evidence = (
                _item("RE-EXT", deep_negative, "Recent downside extension was observed"),
                _item("RE-RECLAIM", _above_band(row), "Price reclaimed the EMA band"),
                _item("RE-CLOSE", strong_close, "The bar closed in a strong location"),
            )
            events.append(
                _event(
                    instrument_id=instrument_id,
                    event_type="REVERSAL_EXTENSION",
                    row=row,
                    bar_index=index,
                    leg_id=current_leg,
                    anchor_event_id=None,
                    sequence_no=None,
                    payload={},
                    evidence=evidence,
                )
            )

        wedge_pop_signal = _all_true(
            enough_history,
            breakout_up,
            _above_band(row),
            contraction,
            ema_tight,
            volume_confirm,
            strong_close,
            direction != "UP",
        )
        wedge_pop_event: ObservedEvent | None = None
        if wedge_pop_signal:
            up_leg_count += 1
            current_leg = f"UP-{up_leg_count}"
            direction = "UP"
            up_crossback_consumed = False
            up_base_count = 0
            last_up_base_index = -10_000
            evidence = (
                _item("WP-BREAK", breakout_up, "Price closed above the causal pivot"),
                _item("WP-BAND", _above_band(row), "Price closed above the EMA band"),
                _item("WP-CONTRACT", contraction, "Recent normalized range contracted"),
                _item("WP-EMA", ema_tight, "The EMA band was tight"),
                _item("WP-VOLUME", volume_confirm, "Volume confirmed the breakout"),
            )
            wedge_pop_event = _event(
                instrument_id=instrument_id,
                event_type="WEDGE_POP",
                row=row,
                bar_index=index,
                leg_id=current_leg,
                anchor_event_id=None,
                sequence_no=None,
                payload={"pivot": row.prior_high20 or row.bar.close},
                evidence=evidence,
            )
            events.append(wedge_pop_event)

        active_wedge_pop = (
            _latest_event(events, "WEDGE_POP") if direction == "UP" else None
        )
        touch_up = _ema_touch(row, params.ema_touch_atr)
        if (
            direction == "UP"
            and active_wedge_pop is not None
            and index > active_wedge_pop.bar_index
            and not up_crossback_consumed
            and touch_up is True
        ):
            up_crossback_consumed = True
            held_band = (
                None
                if _band_values(row) is None
                else row.bar.close >= _band_values(row)[0]
            )
            evidence = (
                _item("ECB-U-TOUCH", touch_up, "Price made the first EMA-band retest"),
                _item("ECB-U-HOLD", held_band, "Price held or reclaimed the EMA band"),
                _item("ECB-U-SLOPE", _up_slopes(row), "EMA slopes remained positive"),
                _item("ECB-U-VOLUME", quiet_volume, "Retest volume was quiet"),
                _item("ECB-U-CLOSE", strong_close, "The retest closed constructively"),
            )
            events.append(
                _event(
                    instrument_id=instrument_id,
                    event_type="UPSIDE_EMA_CROSSBACK",
                    row=row,
                    bar_index=index,
                    leg_id=current_leg,
                    anchor_event_id=active_wedge_pop.event_id,
                    sequence_no=1,
                    payload={
                        "outcome": (
                            "supported"
                            if _all_true(held_band, _up_slopes(row), quiet_volume)
                            else "failed_or_mixed"
                        )
                    },
                    evidence=evidence,
                )
            )

        base_up_signal = _all_true(
            enough_history,
            direction == "UP",
            breakout_up,
            _above_band(row),
            _up_slopes(row),
            contraction,
            volume_confirm,
            strong_close,
            wedge_pop_event is None,
            index - last_up_base_index >= params.min_bars_between_breaks,
        )
        if base_up_signal:
            up_base_count += 1
            last_up_base_index = index
            anchor = _latest_event(events, "WEDGE_POP")
            evidence = (
                _item("BNB-U-LEG", True, "An active up leg exists"),
                _item("BNB-U-BREAK", breakout_up, "Price broke the causal prior high"),
                _item("BNB-U-CONTRACT", contraction, "The base showed range contraction"),
                _item("BNB-U-VOLUME", volume_confirm, "Volume confirmed the breakout"),
            )
            events.append(
                _event(
                    instrument_id=instrument_id,
                    event_type="UPSIDE_BASE_N_BREAK",
                    row=row,
                    bar_index=index,
                    leg_id=current_leg,
                    anchor_event_id=anchor.event_id if anchor else None,
                    sequence_no=up_base_count,
                    payload={
                        "base_id": f"{current_leg}:U:{index}",
                        "pivot": row.prior_high20 or row.bar.close,
                    },
                    evidence=evidence,
                )
            )

        extended_up = (
            None
            if row.distance_ema20_atr is None
            else row.distance_ema20_atr >= params.extension_atr
        )
        previous_extended_up = (
            previous is not None
            and previous.distance_ema20_atr is not None
            and previous.distance_ema20_atr >= params.extension_atr
        )
        last_exhaustion = _latest_event(events, "EXHAUSTION_EXTENSION")
        exhaustion_cooled_down = (
            last_exhaustion is None
            or index - last_exhaustion.bar_index >= params.event_cooldown_bars
        )
        if _all_true(
            enough_history,
            direction == "UP",
            extended_up,
            not previous_extended_up,
            exhaustion_cooled_down,
        ):
            evidence = (
                _item("EE-DIST", extended_up, "Price was extended above EMA20 in ATR units"),
                _item(
                    "EE-LEG",
                    direction == "UP",
                    "The extension occurred inside an active up leg",
                    provenance=Provenance.AUTHOR_INTERPRETATION,
                ),
            )
            events.append(
                _event(
                    instrument_id=instrument_id,
                    event_type="EXHAUSTION_EXTENSION",
                    row=row,
                    bar_index=index,
                    leg_id=current_leg,
                    anchor_event_id=None,
                    sequence_no=None,
                    payload={"distance_ema20_atr": row.distance_ema20_atr or 0.0},
                    evidence=evidence,
                )
            )

        previous_above_or_in_band = (
            None
            if previous is None or _below_band(previous) is None
            else not _below_band(previous)
        )
        range_expansion = (
            None if row.range_ratio is None else row.range_ratio >= 1.0
        )
        inferred_up_context = (
            None
            if previous is None
            or _above_band(previous) is None
            or _up_slopes(previous) is None
            else _above_band(previous) and _up_slopes(previous)
        )
        if direction == "UP":
            up_context = True
        elif direction == "NONE":
            up_context = inferred_up_context
        else:
            up_context = False
        wedge_drop_signal = _all_true(
            enough_history,
            up_context,
            _below_band(row),
            previous_above_or_in_band,
            weak_close,
            (
                True
                if volume_confirm is True or range_expansion is True
                else None if volume_confirm is None and range_expansion is None else False
            ),
        )
        wedge_drop_event: ObservedEvent | None = None
        if wedge_drop_signal:
            had_active_up_leg = direction == "UP"
            down_leg_count += 1
            previous_leg = current_leg if had_active_up_leg else "INFERRED-UP-CONTEXT"
            anchor = _latest_event(events, "WEDGE_POP") if had_active_up_leg else None
            current_leg = f"DOWN-{down_leg_count}"
            direction = "DOWN"
            down_crossback_consumed = False
            down_base_count = 0
            last_down_base_index = -10_000
            evidence = (
                _item(
                    "WD-UP-CONTEXT",
                    up_context,
                    "An active or immediately inferred uptrend context exists",
                    provenance=Provenance.AUTHOR_INTERPRETATION,
                ),
                _item("WD-BAND", _below_band(row), "Price closed below the EMA band"),
                _item("WD-CLOSE", weak_close, "The bar closed in a weak location"),
                _item(
                    "WD-EXPAND",
                    volume_confirm is True or range_expansion is True,
                    "Volume or range expanded on the break",
                ),
            )
            wedge_drop_event = _event(
                instrument_id=instrument_id,
                event_type="WEDGE_DROP",
                row=row,
                bar_index=index,
                leg_id=current_leg,
                anchor_event_id=anchor.event_id if anchor else None,
                sequence_no=None,
                payload={
                    "context_source": (
                        "active_wedge_pop_leg"
                        if had_active_up_leg
                        else "inferred_previous_bar"
                    ),
                    "previous_leg": previous_leg,
                },
                evidence=evidence,
            )
            events.append(wedge_drop_event)

        active_wedge_drop = (
            _latest_event(events, "WEDGE_DROP") if direction == "DOWN" else None
        )
        touch_down = _ema_touch(row, params.ema_touch_atr)
        if (
            direction == "DOWN"
            and active_wedge_drop is not None
            and index > active_wedge_drop.bar_index
            and not down_crossback_consumed
            and touch_down is True
        ):
            down_crossback_consumed = True
            rejected_band = (
                None
                if _band_values(row) is None
                else row.bar.close <= _band_values(row)[1]
            )
            evidence = (
                _item("ECB-D-TOUCH", touch_down, "Price made the first EMA-band rally"),
                _item("ECB-D-REJECT", rejected_band, "Price was rejected by the EMA band"),
                _item("ECB-D-SLOPE", _down_slopes(row), "EMA slopes remained negative"),
                _item("ECB-D-VOLUME", quiet_volume, "Rally volume was quiet"),
                _item("ECB-D-CLOSE", weak_close, "The rally closed weakly"),
            )
            events.append(
                _event(
                    instrument_id=instrument_id,
                    event_type="DOWNSIDE_EMA_CROSSBACK",
                    row=row,
                    bar_index=index,
                    leg_id=current_leg,
                    anchor_event_id=active_wedge_drop.event_id,
                    sequence_no=1,
                    payload={
                        "outcome": (
                            "supported"
                            if _all_true(rejected_band, _down_slopes(row), quiet_volume)
                            else "failed_or_mixed"
                        )
                    },
                    evidence=evidence,
                )
            )

        base_down_signal = _all_true(
            enough_history,
            direction == "DOWN",
            breakout_down,
            _below_band(row),
            _down_slopes(row),
            contraction,
            volume_confirm,
            weak_close,
            wedge_drop_event is None,
            index - last_down_base_index >= params.min_bars_between_breaks,
        )
        if base_down_signal:
            down_base_count += 1
            last_down_base_index = index
            anchor = _latest_event(events, "WEDGE_DROP")
            evidence = (
                _item("BNB-D-LEG", True, "An active down leg exists"),
                _item("BNB-D-BREAK", breakout_down, "Price broke the causal prior low"),
                _item("BNB-D-CONTRACT", contraction, "The base showed range contraction"),
                _item("BNB-D-VOLUME", volume_confirm, "Volume confirmed the breakdown"),
            )
            events.append(
                _event(
                    instrument_id=instrument_id,
                    event_type="DOWNSIDE_BASE_N_BREAK",
                    row=row,
                    bar_index=index,
                    leg_id=current_leg,
                    anchor_event_id=anchor.event_id if anchor else None,
                    sequence_no=down_base_count,
                    payload={
                        "base_id": f"{current_leg}:D:{index}",
                        "support": row.prior_low20 or row.bar.close,
                    },
                    evidence=evidence,
                )
            )

    return tuple(events)


def _assessment(
    phase: str,
    items: tuple[EvidenceItem, ...],
    params: ResearchParameters,
    *,
    hard_unknown: bool = False,
    hard_not_supported: bool = False,
) -> PhaseAssessment:
    evidence_for = tuple(item for item in items if item.status is TriState.TRUE)
    evidence_against = tuple(item for item in items if item.status is TriState.FALSE)
    unknowns = tuple(item for item in items if item.status is TriState.UNKNOWN)
    total_weight = sum(item.weight for item in items)
    signed_weight = sum(item.weight for item in evidence_for) - sum(
        item.weight for item in evidence_against
    )
    score = signed_weight / total_weight if total_weight else 0.0
    support_weight = sum(item.weight for item in evidence_for)
    if hard_unknown or (not evidence_for and not evidence_against):
        confidence = "UNKNOWN"
    elif hard_not_supported:
        confidence = "NOT_SUPPORTED"
    elif support_weight == 0 or score <= 0:
        confidence = "NOT_SUPPORTED"
    elif score >= params.high_confidence_score and len(evidence_for) >= 4:
        confidence = "HIGH"
    elif score >= params.medium_confidence_score and len(evidence_for) >= 3:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"
    return PhaseAssessment(
        phase=phase,
        score=max(-1.0, min(1.0, score)),
        confidence=confidence,
        evidence_for=evidence_for,
        evidence_against=evidence_against,
        unknowns=unknowns,
    )


def assess_current(
    features: tuple[FeatureRow, ...],
    events: tuple[ObservedEvent, ...],
    *,
    parameters: ResearchParameters | None = None,
) -> tuple[PhaseAssessment, ...]:
    params = parameters or ResearchParameters()
    if not features:
        raise ValueError("At least one feature row is required")
    row = features[-1]
    latest_index = len(features) - 1
    enough_history = len(features) >= params.min_history_bars

    def recent(event_type: str) -> bool | None:
        if not enough_history:
            return None
        return (
            _recent_event(
                events,
                event_type,
                latest_index,
                params.recent_event_window,
            )
            is not None
        )

    def recent_outcome(event_type: str) -> bool | None:
        if not enough_history:
            return None
        event = _recent_event(
            events,
            event_type,
            latest_index,
            params.recent_event_window,
        )
        if event is None:
            return False
        outcome = dict(event.payload).get("outcome")
        if outcome == "supported":
            return True
        if outcome == "failed_or_mixed":
            required_rules = {
                "UPSIDE_EMA_CROSSBACK": {
                    "ECB-U-HOLD",
                    "ECB-U-SLOPE",
                    "ECB-U-VOLUME",
                },
                "DOWNSIDE_EMA_CROSSBACK": {
                    "ECB-D-REJECT",
                    "ECB-D-SLOPE",
                    "ECB-D-VOLUME",
                },
            }.get(event_type, set())
            required_evidence = tuple(
                item for item in event.evidence if item.rule_id in required_rules
            )
            if len(required_evidence) != len(required_rules):
                return None
            if any(
                item.status is TriState.UNKNOWN for item in required_evidence
            ):
                return None
            return False
        return None

    above = _above_band(row)
    below = _below_band(row)
    up = _up_slopes(row)
    down = _down_slopes(row)
    strong = (
        None
        if row.close_location is None
        else row.close_location >= params.strong_close_location
    )
    weak = (
        None
        if row.close_location is None
        else row.close_location <= params.weak_close_location
    )
    volume_confirm = (
        None
        if row.volume_ratio is None
        else row.volume_ratio >= params.volume_confirmation_ratio
    )
    quiet_volume = (
        None
        if row.volume_ratio is None
        else row.volume_ratio <= params.quiet_volume_ratio
    )
    contraction = (
        None
        if row.range_ratio is None
        else row.range_ratio <= params.contraction_ratio_max
    )
    ema_tight = (
        None
        if row.ema_spread_atr is None
        else abs(row.ema_spread_atr) <= params.ema_tightness_atr
    )
    extended_up = (
        None
        if row.distance_ema20_atr is None
        else row.distance_ema20_atr >= params.extension_atr
    )
    extended_down = (
        None
        if row.distance_ema20_atr is None
        else row.distance_ema20_atr <= -params.extension_atr
    )
    breakout_up = (
        None if row.prior_high20 is None else row.bar.close > row.prior_high20
    )
    breakout_down = (
        None if row.prior_low20 is None else row.bar.close < row.prior_low20
    )

    last_wedge_pop = _latest_event(events, "WEDGE_POP")
    last_wedge_drop = _latest_event(events, "WEDGE_DROP")
    active_up = (
        None
        if not enough_history
        else last_wedge_pop is not None
        and (last_wedge_drop is None or last_wedge_pop.bar_index > last_wedge_drop.bar_index)
    )
    active_down = (
        None
        if not enough_history
        else last_wedge_drop is not None
        and (last_wedge_pop is None or last_wedge_drop.bar_index > last_wedge_pop.bar_index)
    )
    upside_crossback_outcome = recent_outcome("UPSIDE_EMA_CROSSBACK")
    downside_crossback_outcome = recent_outcome("DOWNSIDE_EMA_CROSSBACK")

    phase_items: dict[str, tuple[EvidenceItem, ...]] = {
        "Reversal Extension": (
            _item("RE-EVENT", recent("REVERSAL_EXTENSION"), "A recent reversal-extension event exists", weight=2),
            _item("RE-EXT", extended_down, "Price is extended below EMA20"),
            _item("RE-RECLAIM", above, "Price reclaimed the EMA band"),
            _item("RE-CLOSE", strong, "The latest bar closed strongly"),
        ),
        "Wedge Pop": (
            _item("WP-EVENT", recent("WEDGE_POP"), "A recent Wedge Pop event exists", weight=2),
            _item("WP-BREAK", breakout_up, "Price is above the causal prior high"),
            _item("WP-CONTRACT", contraction, "Recent range contracted"),
            _item("WP-EMA", ema_tight, "The EMA band is tight"),
            _item("WP-VOLUME", volume_confirm, "Volume confirms the move"),
        ),
        "Upside EMA Crossback": (
            _item("ECB-U-ANCHOR", active_up, "An active Wedge Pop leg exists", provenance=Provenance.AUTHOR_INTERPRETATION, weight=2),
            _item("ECB-U-EVENT", upside_crossback_outcome, "A recent supported first upside EMA crossback exists", weight=2),
            _item("ECB-U-TOUCH", _ema_touch(row, params.ema_touch_atr), "Price is testing the EMA band"),
            _item("ECB-U-HOLD", above if above is not None else None, "Price holds above the EMA band"),
            _item("ECB-U-SLOPE", up, "EMA slopes are positive"),
            _item("ECB-U-VOLUME", quiet_volume, "Retest volume is quiet"),
        ),
        "Upside Base n' Break": (
            _item("BNB-U-LEG", active_up, "An active up leg exists", weight=2),
            _item("BNB-U-EVENT", recent("UPSIDE_BASE_N_BREAK"), "A recent upside Base n' Break exists", weight=2),
            _item("BNB-U-BREAK", breakout_up, "Price broke the causal prior high"),
            _item("BNB-U-CONTRACT", contraction, "The base is contracted"),
            _item("BNB-U-VOLUME", volume_confirm, "Volume confirms the breakout"),
        ),
        "Exhaustion Extension": (
            _item("EE-LEG", active_up, "An active up leg exists", weight=2),
            _item("EE-EVENT", recent("EXHAUSTION_EXTENSION"), "A recent exhaustion event exists", weight=2),
            _item("EE-DIST", extended_up, "Price is extended above EMA20 in ATR units"),
            _item("EE-MOVE", None if row.return_5 is None else row.return_5 > 0, "The five-bar return is positive"),
        ),
        "Wedge Drop": (
            _item("WD-EVENT", recent("WEDGE_DROP"), "A recent Wedge Drop event exists", weight=2),
            _item("WD-BAND", below, "Price closed below the EMA band"),
            _item("WD-SLOPE", down, "EMA slopes are negative"),
            _item("WD-CLOSE", weak, "The latest bar closed weakly"),
            _item("WD-VOLUME", volume_confirm, "Volume confirms the break"),
        ),
        "Downside EMA Crossback": (
            _item("ECB-D-ANCHOR", active_down, "An active Wedge Drop leg exists", provenance=Provenance.AUTHOR_INTERPRETATION, weight=2),
            _item("ECB-D-EVENT", downside_crossback_outcome, "A recent supported first downside EMA crossback exists", weight=2),
            _item("ECB-D-TOUCH", _ema_touch(row, params.ema_touch_atr), "Price is testing the EMA band from below"),
            _item("ECB-D-REJECT", below, "Price remains below the EMA band"),
            _item("ECB-D-SLOPE", down, "EMA slopes are negative"),
            _item("ECB-D-VOLUME", quiet_volume, "Rally volume is quiet"),
        ),
        "Downside Base n' Break": (
            _item("BNB-D-LEG", active_down, "An active down leg exists", weight=2),
            _item("BNB-D-EVENT", recent("DOWNSIDE_BASE_N_BREAK"), "A recent downside Base n' Break exists", weight=2),
            _item("BNB-D-BREAK", breakout_down, "Price broke the causal prior low"),
            _item("BNB-D-CONTRACT", contraction, "The base is contracted"),
            _item("BNB-D-VOLUME", volume_confirm, "Volume confirms the breakdown"),
        ),
    }

    hard_unknown_phases = {
        "Upside EMA Crossback": not enough_history,
        "Downside EMA Crossback": not enough_history,
    }
    hard_not_supported_phases = {
        "Upside EMA Crossback": upside_crossback_outcome is False,
        "Downside EMA Crossback": downside_crossback_outcome is False,
    }
    assessments = tuple(
        _assessment(
            phase,
            phase_items[phase],
            params,
            hard_unknown=hard_unknown_phases.get(phase, False),
            hard_not_supported=hard_not_supported_phases.get(phase, False),
        )
        for phase in PHASES
    )
    return tuple(sorted(assessments, key=lambda item: item.score, reverse=True))
