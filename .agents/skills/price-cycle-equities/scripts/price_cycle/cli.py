from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys
from typing import Sequence

from .cycle import assess_current, detect_events
from .indicators import build_features
from .io import CsvDataError, load_dataset
from .models import Market, PriceBasis
from .parameters import ResearchParameters
from .report import build_report, sha256_file, write_report_files


EXIT_OK = 0
EXIT_USAGE = 2
EXIT_DATA = 3
EXIT_ANALYSIS = 4


def _date_value(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "date must use YYYY-MM-DD"
        ) from error


def _market_value(value: str) -> Market:
    try:
        return Market(value.upper())
    except ValueError as error:
        raise argparse.ArgumentTypeError("market must be CN or US") from error


def _price_basis_value(value: str) -> PriceBasis:
    try:
        return PriceBasis(value.lower())
    except ValueError as error:
        choices = ", ".join(item.value for item in PriceBasis)
        raise argparse.ArgumentTypeError(
            f"price basis must be one of: {choices}"
        ) from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="price-cycle-analyze",
        description=(
            "Create a research-only Cycle of Price Action report from daily OHLCV CSV data."
        ),
    )
    parser.add_argument("--input", required=True, help="Stock OHLCV CSV file")
    parser.add_argument("--market", required=True, type=_market_value, help="CN or US")
    parser.add_argument("--symbol", required=True, help="Ticker shown in the report")
    parser.add_argument(
        "--as-of",
        required=True,
        type=_date_value,
        help="Research cutoff date in YYYY-MM-DD",
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Human-readable data source, for example broker-export",
    )
    parser.add_argument(
        "--price-basis",
        required=True,
        type=_price_basis_value,
        help="raw, split_adjusted, or total_return",
    )
    parser.add_argument(
        "--instrument-id",
        help="Stable listing identifier; fallback is MARKET:symbol",
    )
    parser.add_argument(
        "--venue",
        help="Exchange code, for example SSE, SZSE, BSE, XNYS, or XNAS",
    )
    parser.add_argument(
        "--segment",
        help="Board or segment, for example MAIN, STAR, CHINEXT, or BSE",
    )
    parser.add_argument(
        "--security-type",
        default="COMMON_STOCK",
        help="Security type (default: COMMON_STOCK; ADR is supported for US research)",
    )
    parser.add_argument("--benchmark", help="Optional benchmark OHLCV CSV file")
    parser.add_argument(
        "--benchmark-symbol",
        help="Required together with --benchmark",
    )
    parser.add_argument(
        "--output-dir",
        default="reports",
        help="Report root directory (default: reports)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing report for the same market/symbol/as-of date",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show a Python traceback for unexpected errors",
    )
    return parser


def _validate_pairs(
    parser: argparse.ArgumentParser,
    arguments: argparse.Namespace,
) -> None:
    if bool(arguments.benchmark) != bool(arguments.benchmark_symbol):
        parser.error("--benchmark and --benchmark-symbol must be supplied together")


def run(arguments: argparse.Namespace) -> tuple[Path, Path, list[str]]:
    parameters = ResearchParameters()
    dataset, diagnostics = load_dataset(
        input_path=arguments.input,
        symbol=arguments.symbol,
        market=arguments.market,
        as_of=arguments.as_of,
        source=arguments.source,
        price_basis=arguments.price_basis,
        instrument_id=arguments.instrument_id,
        venue=arguments.venue,
        segment=arguments.segment,
        security_type=arguments.security_type,
        benchmark_path=arguments.benchmark,
        benchmark_symbol=arguments.benchmark_symbol,
    )
    features = build_features(dataset, parameters)
    events = detect_events(
        features,
        instrument_id=dataset.instrument_id,
        parameters=parameters,
    )
    assessments = assess_current(features, events, parameters=parameters)
    report = build_report(
        dataset=dataset,
        diagnostics=diagnostics,
        features=features,
        assessments=assessments,
        events=events,
        parameters=parameters,
        input_filename=Path(arguments.input).name,
        input_sha256=sha256_file(arguments.input),
    )
    json_path, markdown_path = write_report_files(
        report,
        output_dir=arguments.output_dir,
        overwrite=arguments.overwrite,
    )
    warnings = list(report["data_quality"]["warnings"])
    return json_path, markdown_path, warnings


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    _validate_pairs(parser, arguments)
    try:
        json_path, markdown_path, warnings = run(arguments)
    except CsvDataError as error:
        print(f"Data error: {error}", file=sys.stderr)
        return EXIT_DATA
    except (FileExistsError, OSError, ValueError) as error:
        if arguments.debug:
            raise
        print(f"Analysis error: {error}", file=sys.stderr)
        return EXIT_ANALYSIS

    print("Analysis complete (research only; no order was created).")
    print(f"JSON: {json_path.resolve()}")
    print(f"Markdown: {markdown_path.resolve()}")
    if warnings:
        print("Warnings: " + ", ".join(warnings))
    return EXIT_OK
