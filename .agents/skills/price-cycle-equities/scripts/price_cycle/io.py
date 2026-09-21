from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import Bar, DataSet, Market, PriceBasis


REQUIRED_COLUMNS = ("date", "open", "high", "low", "close", "volume")
MARKET_TIMEZONES = {
    Market.CN: "Asia/Shanghai",
    Market.US: "America/New_York",
}


class CsvDataError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CsvLoadResult:
    bars: tuple[Bar, ...]
    total_rows: int
    excluded_after_as_of: int
    excluded_not_yet_known: int
    reordered: bool


def parse_iso_datetime(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise CsvDataError(f"Invalid known_at timestamp: {value!r}") from error
    if parsed.tzinfo is None:
        raise CsvDataError("known_at must include a UTC offset or Z suffix")
    return parsed


def analysis_cutoff(as_of: date, market: Market) -> datetime:
    timezone = ZoneInfo(MARKET_TIMEZONES[market])
    return datetime.combine(as_of, time.max, tzinfo=timezone)


def _parse_float(row_number: int, field: str, value: str | None) -> float:
    if value is None or not value.strip():
        raise CsvDataError(f"Row {row_number}: missing {field}")
    try:
        return float(value)
    except ValueError as error:
        raise CsvDataError(
            f"Row {row_number}: {field} must be numeric, got {value!r}"
        ) from error


def load_bars_csv(
    path: str | Path,
    *,
    as_of: date,
    market: Market,
) -> CsvLoadResult:
    csv_path = Path(path)
    if not csv_path.is_file():
        raise CsvDataError(f"CSV file not found: {csv_path}")

    cutoff = analysis_cutoff(as_of, market)
    parsed_bars: list[Bar] = []
    total_rows = 0
    excluded_after_as_of = 0
    excluded_not_yet_known = 0

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise CsvDataError("CSV has no header row")
        normalized_fields = {name.strip().lower(): name for name in reader.fieldnames}
        missing = [field for field in REQUIRED_COLUMNS if field not in normalized_fields]
        if missing:
            raise CsvDataError(
                "CSV is missing required columns: " + ", ".join(missing)
            )

        for row_number, raw_row in enumerate(reader, start=2):
            total_rows += 1
            row = {
                normalized_name: raw_row[original_name]
                for normalized_name, original_name in normalized_fields.items()
            }
            date_text = (row.get("date") or "").strip()
            try:
                session_date = date.fromisoformat(date_text)
            except ValueError as error:
                raise CsvDataError(
                    f"Row {row_number}: date must use YYYY-MM-DD, got {date_text!r}"
                ) from error

            if session_date > as_of:
                excluded_after_as_of += 1
                continue

            known_at_text = (row.get("known_at") or "").strip()
            known_at = parse_iso_datetime(known_at_text) if known_at_text else None
            if known_at is not None and known_at > cutoff:
                excluded_not_yet_known += 1
                continue

            try:
                parsed_bars.append(
                    Bar(
                        session_date=session_date,
                        open=_parse_float(row_number, "open", row.get("open")),
                        high=_parse_float(row_number, "high", row.get("high")),
                        low=_parse_float(row_number, "low", row.get("low")),
                        close=_parse_float(row_number, "close", row.get("close")),
                        volume=_parse_float(row_number, "volume", row.get("volume")),
                        known_at=known_at,
                    )
                )
            except ValueError as error:
                raise CsvDataError(f"Row {row_number}: {error}") from error

    original_dates = [bar.session_date for bar in parsed_bars]
    parsed_bars.sort(key=lambda bar: bar.session_date)
    reordered = original_dates != [bar.session_date for bar in parsed_bars]
    dates = [bar.session_date for bar in parsed_bars]
    if len(dates) != len(set(dates)):
        raise CsvDataError("CSV contains duplicate session dates")
    if not parsed_bars:
        raise CsvDataError("CSV has no usable rows at or before as_of")

    return CsvLoadResult(
        bars=tuple(parsed_bars),
        total_rows=total_rows,
        excluded_after_as_of=excluded_after_as_of,
        excluded_not_yet_known=excluded_not_yet_known,
        reordered=reordered,
    )


def load_dataset(
    *,
    input_path: str | Path,
    symbol: str,
    market: Market,
    as_of: date,
    source: str,
    price_basis: PriceBasis,
    instrument_id: str | None = None,
    venue: str | None = None,
    segment: str | None = None,
    security_type: str = "COMMON_STOCK",
    benchmark_path: str | Path | None = None,
    benchmark_symbol: str | None = None,
) -> tuple[DataSet, dict[str, object]]:
    primary = load_bars_csv(input_path, as_of=as_of, market=market)
    benchmark = (
        load_bars_csv(benchmark_path, as_of=as_of, market=market)
        if benchmark_path is not None
        else None
    )
    resolved_instrument_id = instrument_id or f"{market.value}:{symbol}"
    dataset = DataSet(
        instrument_id=resolved_instrument_id,
        symbol=symbol,
        market=market,
        as_of=as_of,
        source=source,
        price_basis=price_basis,
        bars=primary.bars,
        venue=venue,
        segment=segment,
        security_type=security_type,
        benchmark_symbol=benchmark_symbol,
        benchmark_bars=benchmark.bars if benchmark else (),
    )
    diagnostics: dict[str, object] = {
        "input_rows": primary.total_rows,
        "usable_rows": len(primary.bars),
        "excluded_after_as_of": primary.excluded_after_as_of,
        "excluded_not_yet_known": primary.excluded_not_yet_known,
        "input_reordered": primary.reordered,
        "instrument_id_is_fallback": instrument_id is None,
        "benchmark_supplied": benchmark is not None,
        "benchmark_rows": len(benchmark.bars) if benchmark else 0,
        "timestamp_policy": dataset.timestamp_policy,
    }
    return dataset, diagnostics
