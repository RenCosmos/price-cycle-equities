from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import traceback
import unittest
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from tests.helpers import SCRIPT_ROOT

from price_cycle.indicators import build_features
from price_cycle.models import Market, PriceBasis
from price_cycle.pipeline import analyze_loaded_result, analyze_request
from price_cycle.providers import (
    DataRequest,
    EODHD_TOKEN_SPEC,
    EnvironmentCredentialResolver,
    EodhdDailyProvider,
    EodhdTransportError,
    HttpsEodhdTransport,
    ProviderFailure,
    ProviderRegistry,
    ProviderResolutionError,
    ProviderRouter,
    SecretValue,
)


del SCRIPT_ROOT

TOKEN_MARKER = "fixture-eodhd-secret"


def request(**changes: object) -> DataRequest:
    values: dict[str, object] = {
        "symbol": "600519",
        "market": Market.CN,
        "as_of": date(2026, 8, 31),
        "price_basis": PriceBasis.SPLIT_ADJUSTED,
        "venue": "SSE",
        "segment": "MAIN",
        "benchmark_symbol": "510300",
    }
    values.update(changes)
    return DataRequest(**values)


def trading_dates(end: date, count: int) -> list[date]:
    selected: list[date] = []
    cursor = end
    while len(selected) < count:
        if cursor.weekday() < 5:
            selected.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(selected))


def eod_rows(
    end: date,
    *,
    count: int = 230,
    start_close: float = 100.0,
) -> list[dict[str, object]]:
    rows = []
    for index, session_date in enumerate(trading_dates(end, count)):
        close = start_close + index * 0.2
        rows.append(
            {
                "date": session_date.isoformat(),
                "open": close - 0.1,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "adjusted_close": close,
                "volume": 1000 + index,
            }
        )
    return rows


@dataclass
class FixtureTransport:
    responses: dict[tuple[str, str], object]
    error: Exception | None = None
    calls: list[dict[str, object]] = field(default_factory=list)

    def fetch(
        self,
        *,
        endpoint: str,
        symbol: str,
        token: SecretValue,
        params: dict[str, str],
    ) -> object:
        self.calls.append(
            {
                "endpoint": endpoint,
                "symbol": symbol,
                "token": token,
                "params": dict(params),
            }
        )
        if self.error is not None:
            raise self.error
        return deepcopy(self.responses[(endpoint, symbol)])


def fixture_transport(
    *,
    as_of: date = date(2026, 8, 31),
    instrument_rows: object | None = None,
    instrument_splits: object | None = None,
    benchmark_rows: object | None = None,
    benchmark_splits: object | None = None,
) -> FixtureTransport:
    return FixtureTransport(
        {
            ("eod", "600519.SHG"): (
                eod_rows(as_of)
                if instrument_rows is None
                else instrument_rows
            ),
            ("splits", "600519.SHG"): (
                [] if instrument_splits is None else instrument_splits
            ),
            ("eod", "510300.SHG"): (
                eod_rows(as_of, start_close=200.0)
                if benchmark_rows is None
                else benchmark_rows
            ),
            ("splits", "510300.SHG"): (
                [] if benchmark_splits is None else benchmark_splits
            ),
        }
    )


def provider(
    transport: FixtureTransport,
    *,
    token: str = TOKEN_MARKER,
) -> EodhdDailyProvider:
    return EodhdDailyProvider(
        credential_resolver=EnvironmentCredentialResolver(
            {EODHD_TOKEN_SPEC.environment_variable: token}
        ),
        transport=transport,
    )


class EodhdProviderTests(unittest.TestCase):
    def test_cn_instrument_and_benchmark_are_loaded_atomically(self) -> None:
        transport = fixture_transport()
        selected = provider(transport)
        routed = ProviderRouter(
            ProviderRegistry((selected,))
        ).load(request(), ("eodhd",))

        self.assertEqual(
            [(call["endpoint"], call["symbol"]) for call in transport.calls],
            [
                ("eod", "600519.SHG"),
                ("splits", "600519.SHG"),
                ("eod", "510300.SHG"),
                ("splits", "510300.SHG"),
            ],
        )
        self.assertEqual(routed.dataset.venue, "SSE")
        self.assertEqual(routed.dataset.segment, "MAIN")
        self.assertEqual(routed.dataset.benchmark_symbol, "510300")
        self.assertEqual(len(routed.artifacts), 2)
        self.assertEqual(
            {artifact.role for artifact in routed.artifacts},
            {"instrument", "benchmark"},
        )
        self.assertEqual(routed.volume_scope, "vendor_reported_unverified")
        self.assertEqual(routed.volume_basis, "unknown")
        self.assertEqual(routed.zero_volume_policy, "unknown")
        self.assertEqual(routed.volume_completeness, 1.0)
        self.assertFalse(routed.dataset.volume_evidence_eligible)
        self.assertEqual(routed.diagnostics["data_provider_id"], "eodhd")
        self.assertNotIn(TOKEN_MARKER, repr(routed))

        features = build_features(routed.dataset)
        self.assertTrue(all(row.volume_sma20 is None for row in features))
        self.assertTrue(all(row.volume_ratio is None for row in features))

    def test_current_session_is_excluded_until_conservative_close_cutoff(self) -> None:
        observed_at = datetime(2026, 8, 31, 6, 0, tzinfo=timezone.utc)
        transport = fixture_transport(as_of=date(2026, 8, 30))
        selected = EodhdDailyProvider(
            credential_resolver=EnvironmentCredentialResolver(
                {EODHD_TOKEN_SPEC.environment_variable: TOKEN_MARKER}
            ),
            transport=transport,
            clock=lambda: observed_at,
        )
        loaded = selected.load(request(benchmark_symbol=None))
        self.assertEqual(loaded.dataset.as_of, date(2026, 8, 31))
        self.assertLessEqual(
            loaded.dataset.bars[-1].session_date,
            date(2026, 8, 30),
        )
        self.assertTrue(
            all(call["params"]["to"] == "2026-08-30" for call in transport.calls)
        )
        self.assertTrue(
            all(
                artifact.retrieved_at == observed_at
                for artifact in loaded.artifacts
            )
        )

    def test_split_adjustment_uses_only_later_ex_dates(self) -> None:
        rows = [
            {
                "date": "2026-08-27",
                "open": 98.0,
                "high": 102.0,
                "low": 97.0,
                "close": 100.0,
                "adjusted_close": 50.0,
                "volume": 2000,
            },
            {
                "date": "2026-08-28",
                "open": 100.0,
                "high": 104.0,
                "low": 99.0,
                "close": 102.0,
                "adjusted_close": 51.0,
                "volume": 2100,
            },
            {
                "date": "2026-08-31",
                "open": 51.0,
                "high": 53.0,
                "low": 50.0,
                "close": 52.0,
                "adjusted_close": 52.0,
                "volume": 2200,
            },
        ]
        transport = fixture_transport(
            instrument_rows=rows,
            instrument_splits=[{"date": "2026-08-31", "split": "2/1"}],
        )
        loaded = provider(transport).load(request(benchmark_symbol=None))
        bars = loaded.dataset.bars
        self.assertEqual([bar.close for bar in bars], [50.0, 51.0, 52.0])
        self.assertEqual([bar.volume for bar in bars], [2000.0, 2100.0, 2200.0])
        self.assertTrue(
            all(bar.known_at is not None and bar.known_at.hour == 23 for bar in bars)
        )

    def test_us_symbol_mapping_and_snapshot_ignore_credential(self) -> None:
        as_of = date(2026, 8, 31)
        responses = {
            ("eod", "AAPL.US"): eod_rows(as_of),
            ("splits", "AAPL.US"): [],
            ("eod", "VTI.US"): eod_rows(as_of, start_close=200.0),
            ("splits", "VTI.US"): [],
        }
        selected_request = request(
            symbol="aapl",
            market=Market.US,
            venue=None,
            segment=None,
            benchmark_symbol="VTI",
        )
        first = provider(
            FixtureTransport(deepcopy(responses)),
            token="first-secret",
        ).load(selected_request)
        second = provider(
            FixtureTransport(deepcopy(responses)),
            token="second-secret",
        ).load(selected_request)
        self.assertEqual(first.snapshot_id, second.snapshot_id)
        self.assertEqual(
            [artifact.snapshot_id for artifact in first.artifacts],
            [artifact.snapshot_id for artifact in second.artifacts],
        )
        self.assertIsNone(first.dataset.venue)
        self.assertEqual(first.dataset.symbol, "aapl")
        self.assertNotIn("first-secret", repr(first))
        self.assertNotIn("second-secret", repr(second))

    def test_missing_credential_and_unsupported_requests_stop_before_transport(self) -> None:
        transport = fixture_transport()
        missing = EodhdDailyProvider(
            credential_resolver=EnvironmentCredentialResolver({}),
            transport=transport,
        )
        with self.assertRaises(ProviderFailure) as caught:
            missing.load(request())
        self.assertEqual(caught.exception.code, "CREDENTIAL_ENV_MISSING")
        self.assertEqual(transport.calls, [])

        invalid_without_credential = EodhdDailyProvider(
            credential_resolver=EnvironmentCredentialResolver({}),
            transport=transport,
        )
        with self.assertRaises(ProviderFailure) as invalid_caught:
            invalid_without_credential.load(
                request(symbol="bad", benchmark_symbol=None)
            )
        self.assertEqual(invalid_caught.exception.code, "INVALID_SYMBOL")
        self.assertEqual(transport.calls, [])

        cases = (
            request(price_basis=PriceBasis.RAW),
            request(symbol="688001", venue="SZSE", segment="STAR"),
            request(symbol="833171", venue="BSE", segment="BSE"),
            request(benchmark_symbol="000300"),
            request(benchmark_symbol="113001"),
            request(
                symbol="AAPL.US",
                market=Market.US,
                venue=None,
                segment=None,
                benchmark_symbol=None,
            ),
            request(
                symbol="AAPL",
                market=Market.US,
                venue="XNAS",
                segment=None,
                benchmark_symbol="VTI",
            ),
            request(
                symbol="AAPL",
                market=Market.US,
                venue=None,
                segment=None,
                security_type="ADR",
                benchmark_symbol="VTI",
            ),
            request(
                symbol="AAPL",
                market=Market.US,
                venue=None,
                segment=None,
                benchmark_symbol="DIA",
            ),
        )
        for selected_request in cases:
            with self.subTest(symbol=selected_request.symbol):
                selected_transport = fixture_transport()
                with self.assertRaises(ProviderFailure):
                    provider(selected_transport).load(selected_request)
                self.assertEqual(selected_transport.calls, [])

    def test_invalid_daily_and_split_payloads_fail_closed(self) -> None:
        valid = eod_rows(date(2026, 8, 31), count=2)
        invalid_cases: tuple[object, object, str] = (
            ([], [], "NO_SOURCE_DATA"),
            ([valid[0], dict(valid[0])], [], "INVALID_SOURCE_DATA"),
            ([{**valid[0], "volume": -1}], [], "INVALID_SOURCE_DATA"),
            ([{key: value for key, value in valid[0].items() if key != "volume"}], [], "INVALID_SOURCE_DATA"),
            (valid, [{"date": "2026-08-31", "split": "bad"}], "INVALID_SOURCE_DATA"),
            (
                valid,
                [
                    {"date": "2026-08-31", "split": "2/1"},
                    {"date": "2026-08-31", "split": "2/1"},
                ],
                "INVALID_SOURCE_DATA",
            ),
        )
        for rows, splits, expected_code in invalid_cases:
            with self.subTest(expected_code=expected_code):
                transport = fixture_transport(
                    instrument_rows=rows,
                    instrument_splits=splits,
                )
                with self.assertRaises(ProviderFailure) as caught:
                    provider(transport).load(request(benchmark_symbol=None))
                self.assertEqual(caught.exception.code, expected_code)

    def test_transport_failure_is_sanitized_and_not_chained(self) -> None:
        hostile = TOKEN_MARKER + " https://example.test/private C:/private"
        transport = fixture_transport()
        transport.error = RuntimeError(hostile)
        with self.assertRaises(ProviderFailure) as caught:
            provider(transport).load(request(benchmark_symbol=None))
        rendered = "".join(traceback.format_exception(caught.exception))
        self.assertEqual(caught.exception.code, "UPSTREAM_HTTP_ERROR")
        self.assertNotIn(TOKEN_MARKER, rendered)
        self.assertNotIn("example.test", rendered)
        self.assertIsNone(caught.exception.__context__)

    def test_pipeline_report_discloses_disabled_volume_and_daily_only_scope(self) -> None:
        routed = ProviderRouter(
            ProviderRegistry((provider(fixture_transport()),))
        ).load(request(), ("eodhd",))
        with tempfile.TemporaryDirectory() as directory:
            json_path, markdown_path, warnings = analyze_loaded_result(
                routed,
                output_dir=directory,
            )
            report = json.loads(Path(json_path).read_text(encoding="utf-8"))
            markdown = Path(markdown_path).read_text(encoding="utf-8")
        self.assertIn("VOLUME_CONFIRMATION_DISABLED", warnings)
        self.assertIn("VOLUME_QUALITY_NOT_PROVIDER_VERIFIED", warnings)
        self.assertIn("INSTRUMENT_IDENTITY_NOT_PROVIDER_VERIFIED", warnings)
        self.assertEqual(
            report["instrument"]["identity_assurance"],
            "symbol_route_inferred_not_master_verified",
        )
        self.assertEqual(
            report["market_context"]["weekly_structure"]["status"],
            "UNKNOWN",
        )
        self.assertEqual(
            report["data_quality"]["evidence_mode"],
            "price_structure_only_volume_unconfirmed",
        )
        self.assertIn(
            "verified_complete_volume_semantics",
            report["data_quality"]["missing_capabilities"],
        )
        self.assertIn(
            "point_in_time_adjusted_price_vintage",
            report["data_quality"]["missing_capabilities"],
        )
        self.assertIn(
            "provider_verified_instrument_master_identity",
            report["data_quality"]["missing_capabilities"],
        )
        self.assertIn("周线结构：UNKNOWN", markdown)
        self.assertIn("阶段事件仅代表价格结构候选", markdown)

    def test_benchmark_failure_aborts_whole_request_without_report(self) -> None:
        selected = provider(fixture_transport(benchmark_rows=[]))
        router = ProviderRouter(ProviderRegistry((selected,)))
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "reports"
            with self.assertRaises(ProviderResolutionError) as caught:
                analyze_request(
                    request(),
                    router=router,
                    provider_order=("eodhd",),
                    output_dir=output_dir,
                )
            self.assertFalse(output_dir.exists())
        self.assertEqual(caught.exception.code, "ALL_PROVIDERS_FAILED")
        self.assertEqual(
            caught.exception.attempts[0].error_code,
            "NO_SOURCE_DATA",
        )


class _ErrorOpener:
    def __init__(self, marker: str) -> None:
        self.marker = marker

    def open(self, request: object, timeout: float) -> object:
        del request, timeout
        raise HTTPError(
            "https://eodhd.com/private?api_token=" + self.marker,
            401,
            "denied " + self.marker,
            {},
            None,
        )


class _RecordingResponse:
    status = 200
    headers = {"Content-Type": "application/json; charset=utf-8"}

    def __init__(self, payload: object) -> None:
        self.payload = json.dumps(payload).encode("utf-8")
        self.closed = False

    def read(self, limit: int) -> bytes:
        return self.payload[:limit]

    def close(self) -> None:
        self.closed = True


class _RecordingOpener:
    def __init__(self, response: _RecordingResponse) -> None:
        self.response = response
        self.request: object | None = None
        self.timeout: float | None = None

    def open(self, request: object, timeout: float) -> _RecordingResponse:
        self.request = request
        self.timeout = timeout
        return self.response


class EodhdTransportTests(unittest.TestCase):
    def test_https_happy_path_uses_fixed_endpoint_and_closes_response(self) -> None:
        response = _RecordingResponse([{"date": "2026-08-31"}])
        opener = _RecordingOpener(response)
        transport = HttpsEodhdTransport(
            opener=opener,
            timeout_seconds=7,
        )
        payload = transport.fetch(
            endpoint="eod",
            symbol="AAPL.US",
            token=SecretValue(TOKEN_MARKER),
            params={"fmt": "json", "from": "2026-01-01"},
        )
        self.assertEqual(payload, [{"date": "2026-08-31"}])
        self.assertTrue(response.closed)
        self.assertEqual(opener.timeout, 7.0)
        url = urlsplit(opener.request.full_url)
        self.assertEqual(url.scheme, "https")
        self.assertEqual(url.netloc, "eodhd.com")
        self.assertEqual(url.path, "/api/eod/AAPL.US")
        query = parse_qs(url.query)
        self.assertEqual(query["api_token"], [TOKEN_MARKER])
        self.assertEqual(query["fmt"], ["json"])

    def test_http_error_does_not_leak_token_url(self) -> None:
        transport = HttpsEodhdTransport(opener=_ErrorOpener(TOKEN_MARKER))
        with self.assertRaises(EodhdTransportError) as caught:
            transport.fetch(
                endpoint="eod",
                symbol="AAPL.US",
                token=SecretValue(TOKEN_MARKER),
                params={"fmt": "json"},
            )
        rendered = "".join(traceback.format_exception(caught.exception))
        self.assertEqual(caught.exception.code, "UPSTREAM_AUTHORIZATION_FAILED")
        self.assertNotIn(TOKEN_MARKER, rendered)
        self.assertIsNone(caught.exception.__context__)

    def test_transport_error_metadata_is_strict(self) -> None:
        with self.assertRaises(ValueError):
            EodhdTransportError("UNTRUSTED_CODE", retryable=False)
        with self.assertRaises(ValueError):
            EodhdTransportError("UPSTREAM_UNAVAILABLE", retryable=1)


if __name__ == "__main__":
    unittest.main()
