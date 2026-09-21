from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path


OUTPUT_DIR = Path(__file__).resolve().parent / "golden"
END_DATE = date(2026, 9, 18)
ROW_COUNT = 260


def business_days(end: date, count: int) -> list[date]:
    days: list[date] = []
    current = end
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current -= timedelta(days=1)
    return list(reversed(days))


def write_rows(path: Path, rows: list[tuple[object, ...]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(("date", "open", "high", "low", "close", "volume"))
        writer.writerows(rows)


def cn_rows(days: list[date]) -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    for index, session_date in enumerate(days):
        if index < 240:
            open_price, high, low, close, volume = 100.00, 100.30, 99.70, 100.00, 1000
        elif index < 250:
            open_price, high, low, close, volume = 99.95, 100.30, 98.70, 100.00, 980
        elif index < 259:
            open_price, high, low, close, volume = 100.00, 100.15, 99.85, 100.00, 900
        else:
            open_price, high, low, close, volume = 100.08, 100.55, 100.00, 100.50, 2400
        rows.append(
            (
                session_date.isoformat(),
                f"{open_price:.2f}",
                f"{high:.2f}",
                f"{low:.2f}",
                f"{close:.2f}",
                volume,
            )
        )
    return rows


def us_rows(days: list[date]) -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    for index, session_date in enumerate(days):
        if index < 200:
            open_price, high, low, close, volume = 100.00, 100.30, 99.70, 100.00, 1000
        elif index < 210:
            open_price, high, low, close, volume = 99.95, 100.30, 98.70, 100.00, 980
        elif index < 219:
            open_price, high, low, close, volume = 100.00, 100.15, 99.85, 100.00, 900
        elif index == 219:
            open_price, high, low, close, volume = 100.08, 100.55, 100.00, 100.50, 2400
        elif index < 259:
            close = 100.50 + (index - 219) * 0.22
            open_price, high, low, volume = close - 0.08, close + 0.28, close - 0.28, 1100
        else:
            previous_close = 100.50 + (258 - 219) * 0.22
            open_price, high, low, close, volume = previous_close - 0.20, previous_close + 0.20, 100.80, 101.30, 3200
        rows.append(
            (
                session_date.isoformat(),
                f"{open_price:.2f}",
                f"{high:.2f}",
                f"{low:.2f}",
                f"{close:.2f}",
                volume,
            )
        )
    return rows


def benchmark_rows(
    days: list[date],
    *,
    start: float,
    step: float,
) -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    for index, session_date in enumerate(days):
        close = start + step * index
        rows.append(
            (
                session_date.isoformat(),
                f"{close - 0.20:.2f}",
                f"{close + 0.50:.2f}",
                f"{close - 0.50:.2f}",
                f"{close:.2f}",
                1_000_000 + index * 100,
            )
        )
    return rows


def main() -> None:
    days = business_days(END_DATE, ROW_COUNT)
    write_rows(OUTPUT_DIR / "cn_wedge_pop.csv", cn_rows(days))
    write_rows(
        OUTPUT_DIR / "cn_benchmark.csv",
        benchmark_rows(days, start=3000.0, step=0.50),
    )
    write_rows(OUTPUT_DIR / "us_wedge_drop.csv", us_rows(days))
    write_rows(
        OUTPUT_DIR / "us_benchmark.csv",
        benchmark_rows(days, start=5000.0, step=0.80),
    )
    print(f"Generated four synthetic CSV files in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
