from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys
from typing import Sequence

from .io import CsvDataError
from .models import Market, PriceBasis
from .pipeline import analyze_loaded_result
from .providers import (
    CsvFileProvider,
    DataRequest,
    ProviderConfigError,
    ProviderRegistry,
    ProviderResolutionError,
    ProviderRouter,
    ProviderRuntimeError,
    build_remote_registry,
    load_provider_config,
    resolve_remote_route,
)


EXIT_OK = 0
EXIT_USAGE = 2
EXIT_DATA = 3
EXIT_ANALYSIS = 4

DEFAULT_REMOTE_BENCHMARKS = {
    Market.CN: "510300",
    Market.US: "VTI",
}


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
            "Create a research-only Cycle of Price Action report from daily "
            "OHLCV CSV data or an explicitly configured remote provider."
        ),
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--input", help="Stock OHLCV CSV file")
    source_group.add_argument(
        "--provider-config",
        help="Explicit TOML configuration for remote data providers",
    )
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
        help="Human-readable CSV data source, for example broker-export",
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
        help="Security type (default: COMMON_STOCK; remote mode currently requires it)",
    )
    parser.add_argument("--benchmark", help="Optional benchmark OHLCV CSV file")
    parser.add_argument(
        "--benchmark-symbol",
        help=(
            "CSV benchmark symbol, or a remote benchmark override "
            "(defaults: CN 510300, US VTI)"
        ),
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


def _validate_source_mode(
    parser: argparse.ArgumentParser,
    arguments: argparse.Namespace,
) -> None:
    if arguments.input:
        if not arguments.source:
            parser.error("--source is required with --input")
        if bool(arguments.benchmark) != bool(arguments.benchmark_symbol):
            parser.error(
                "--benchmark and --benchmark-symbol must be supplied together"
            )
        return
    if arguments.source:
        parser.error("--source is only valid with --input")
    if arguments.benchmark:
        parser.error("--benchmark is only valid with --input")


def run(arguments: argparse.Namespace) -> tuple[Path, Path, list[str]]:
    benchmark_symbol = arguments.benchmark_symbol
    if arguments.provider_config and benchmark_symbol is None:
        benchmark_symbol = DEFAULT_REMOTE_BENCHMARKS[arguments.market]
    request = DataRequest(
        symbol=arguments.symbol,
        market=arguments.market,
        as_of=arguments.as_of,
        price_basis=arguments.price_basis,
        instrument_id=arguments.instrument_id,
        venue=arguments.venue,
        segment=arguments.segment,
        security_type=arguments.security_type,
        benchmark_symbol=benchmark_symbol,
    )
    if arguments.input:
        provider = CsvFileProvider(
            input_path=arguments.input,
            source_label=arguments.source,
            benchmark_path=arguments.benchmark,
        )
        registry = ProviderRegistry((provider,))
        provider_order = (provider.provider_id,)
    else:
        configuration = load_provider_config(arguments.provider_config)
        registry = build_remote_registry(configuration)
        provider_order = resolve_remote_route(
            configuration,
            registry,
            market=arguments.market,
        )
    loaded = ProviderRouter(registry).load(request, provider_order)
    return analyze_loaded_result(
        loaded,
        output_dir=arguments.output_dir,
        overwrite=arguments.overwrite,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    _validate_source_mode(parser, arguments)
    try:
        json_path, markdown_path, warnings = run(arguments)
    except (ProviderConfigError, ProviderRuntimeError) as error:
        print(f"Configuration error [{error.code}]: {error}", file=sys.stderr)
        return EXIT_DATA
    except ProviderResolutionError as error:
        print(f"Data error [{error.code}]: {error}", file=sys.stderr)
        return EXIT_DATA
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
