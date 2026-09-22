from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, timedelta
import traceback
import unittest
from unittest.mock import patch

from tests.helpers import SCRIPT_ROOT

from price_cycle.models import Market, PriceBasis
from price_cycle.providers import (
    BlockedTushareTransport,
    DataRequest,
    EnvironmentCredentialResolver,
    ProviderFailure,
    ProviderRegistry,
    ProviderResolutionError,
    ProviderRouter,
    SecretValue,
    TUSHARE_TOKEN_SPEC,
    TushareDailyProvider,
    TushareTransportError,
)
from price_cycle.providers.tushare import (
    HISTORY_CALENDAR_DAYS,
    TUSHARE_DAILY_FIELDS,
)


del SCRIPT_ROOT

TOKEN_MARKER = "fixture-bare-tushare-secret"


def request(**changes: object) -> DataRequest:
    values: dict[str, object] = {
        "symbol": "600000.SH",
        "market": Market.CN,
        "as_of": date(2025, 1, 3),
        "price_basis": PriceBasis.RAW,
        "venue": "SSE",
        "segment": "MAIN",
    }
    values.update(changes)
    return DataRequest(**values)


def fixture_response(
    *,
    fields: list[str] | None = None,
    items: list[list[object]] | None = None,
    code: object = 0,
    message: object = None,
) -> dict[str, object]:
    selected_fields = list(TUSHARE_DAILY_FIELDS) if fields is None else fields
    selected_items = (
        [
            ["600000.SH", "20250103", 10.0, 10.8, 9.9, 10.5, 123.45],
            ["600000.SH", "20250102", 9.8, 10.2, 9.7, 10.0, 100.0],
        ]
        if items is None
        else items
    )
    return {
        "code": code,
        "msg": message,
        "data": {
            "fields": selected_fields,
            "items": selected_items,
        },
    }


@dataclass
class FixtureTransport:
    response: object = field(default_factory=fixture_response)
    error: Exception | None = None
    calls: list[dict[str, object]] = field(default_factory=list)

    def query(
        self,
        *,
        api_name: str,
        token: SecretValue,
        params: dict[str, str],
        fields: tuple[str, ...],
    ) -> object:
        self.calls.append(
            {
                "api_name": api_name,
                "token": token,
                "params": dict(params),
                "fields": tuple(fields),
            }
        )
        if self.error is not None:
            raise self.error
        return deepcopy(self.response)


def provider(
    transport: FixtureTransport | BlockedTushareTransport,
    *,
    token: str = TOKEN_MARKER,
) -> TushareDailyProvider:
    return TushareDailyProvider(
        credential_resolver=EnvironmentCredentialResolver(
            {TUSHARE_TOKEN_SPEC.environment_variable: token}
        ),
        transport=transport,
    )


class TushareProviderTests(unittest.TestCase):
    def test_fixture_normalizes_raw_daily_bars_without_strategy_calculation(self) -> None:
        transport = FixtureTransport()
        loaded = provider(transport).load(request())

        self.assertEqual(len(transport.calls), 1)
        call = transport.calls[0]
        self.assertEqual(call["api_name"], "daily")
        self.assertEqual(call["fields"], TUSHARE_DAILY_FIELDS)
        self.assertIsInstance(call["token"], SecretValue)
        self.assertEqual(call["token"].reveal(), TOKEN_MARKER)
        self.assertEqual(
            call["params"],
            {
                "ts_code": "600000.SH",
                "start_date": (
                    date(2025, 1, 3) - timedelta(days=HISTORY_CALENDAR_DAYS)
                ).strftime("%Y%m%d"),
                "end_date": "20250103",
            },
        )

        self.assertEqual(
            [bar.session_date for bar in loaded.dataset.bars],
            [date(2025, 1, 2), date(2025, 1, 3)],
        )
        self.assertEqual(loaded.dataset.bars[0].volume, 100.0)
        self.assertEqual(loaded.dataset.bars[0].known_at.hour, 17)
        self.assertEqual(
            loaded.dataset.bars[0].known_at.utcoffset(),
            timedelta(hours=8),
        )
        self.assertEqual(loaded.dataset.price_basis, PriceBasis.RAW)
        self.assertEqual(loaded.dataset.venue, "SSE")
        self.assertEqual(loaded.dataset.segment, "MAIN")
        self.assertEqual(loaded.dataset.instrument_id, "CN:600000.SH")
        self.assertTrue(loaded.diagnostics["input_reordered"])
        self.assertEqual(loaded.market_data_scope, "full_listing")
        self.assertEqual(loaded.volume_scope, "unknown")
        self.assertIsNone(loaded.volume_completeness)
        self.assertEqual(loaded.volume_basis, "raw")
        self.assertEqual(loaded.price_basis_assertion, "provider_verified")
        self.assertEqual(len(loaded.snapshot_id), 64)
        self.assertEqual(len(loaded.artifacts[0].snapshot_id), 64)
        self.assertNotEqual(loaded.snapshot_id, loaded.artifacts[0].snapshot_id)
        self.assertIsNotNone(loaded.artifacts[0].retrieved_at)
        self.assertNotIn(TOKEN_MARKER, repr(loaded))

    def test_snapshot_is_canonical_and_does_not_depend_on_token(self) -> None:
        first = provider(FixtureTransport(), token="first-secret").load(request())
        second = provider(FixtureTransport(), token="second-secret").load(request())
        reordered_fields = [
            "vol",
            "close",
            "low",
            "high",
            "open",
            "trade_date",
            "ts_code",
        ]
        third = provider(
            FixtureTransport(
                fixture_response(
                    fields=reordered_fields,
                    items=[
                        [123.45, 10.5, 9.9, 10.8, 10.0, "20250103", "600000.SH"],
                        [100.0, 10.0, 9.7, 10.2, 9.8, "20250102", "600000.SH"],
                    ],
                )
            ),
            token="third-secret",
        ).load(request())

        self.assertEqual(first.snapshot_id, second.snapshot_id)
        self.assertEqual(first.snapshot_id, third.snapshot_id)
        self.assertEqual(
            first.artifacts[0].snapshot_id,
            third.artifacts[0].snapshot_id,
        )
        for marker in ("first-secret", "second-secret", "third-secret"):
            self.assertNotIn(marker, first.snapshot_id)
            self.assertNotIn(marker, third.artifacts[0].snapshot_id)

    def test_catalog_scaffold_cannot_pass_the_volume_quality_gate(self) -> None:
        transport = FixtureTransport()
        router = ProviderRouter(ProviderRegistry((provider(transport),)))
        with self.assertRaises(ProviderResolutionError) as caught:
            router.load(request(), ("tushare",))

        self.assertEqual(caught.exception.code, "ALL_PROVIDERS_FAILED")
        self.assertEqual(len(caught.exception.attempts), 1)
        self.assertEqual(
            caught.exception.attempts[0].error_code,
            "INSUFFICIENT_VOLUME_COVERAGE",
        )
        self.assertEqual(len(transport.calls), 1)

    def test_default_transport_is_network_blocked_and_does_not_reveal_token(self) -> None:
        selected = provider(BlockedTushareTransport())
        self.assertNotIn(TOKEN_MARKER, repr(selected))
        with patch(
            "socket.create_connection",
            side_effect=AssertionError("network must remain blocked"),
        ):
            with self.assertRaises(ProviderFailure) as caught:
                selected.load(request())

        self.assertEqual(caught.exception.code, "SECURE_TRANSPORT_NOT_VERIFIED")
        rendered = "".join(traceback.format_exception(caught.exception))
        self.assertNotIn(TOKEN_MARKER, str(caught.exception))
        self.assertNotIn(TOKEN_MARKER, rendered)
        self.assertIsNone(caught.exception.__context__)

    def test_missing_credential_stops_before_transport(self) -> None:
        transport = FixtureTransport()
        selected = TushareDailyProvider(
            credential_resolver=EnvironmentCredentialResolver({}),
            transport=transport,
        )
        with self.assertRaises(ProviderFailure) as caught:
            selected.load(request())

        self.assertEqual(caught.exception.code, "CREDENTIAL_ENV_MISSING")
        self.assertEqual(transport.calls, [])
        self.assertIsNone(caught.exception.__context__)

    def test_unsupported_requests_stop_before_credential_or_transport(self) -> None:
        cases = (
            request(market=Market.US),
            request(price_basis=PriceBasis.SPLIT_ADJUSTED),
            request(benchmark_symbol="000300.SH"),
            request(security_type="ETF"),
        )
        for selected_request in cases:
            with self.subTest(selected_request=selected_request):
                transport = FixtureTransport()
                selected = TushareDailyProvider(
                    credential_resolver=EnvironmentCredentialResolver({}),
                    transport=transport,
                )
                with self.assertRaises(ProviderFailure) as caught:
                    selected.load(selected_request)
                self.assertEqual(caught.exception.code, "UNSUPPORTED_REQUEST")
                self.assertEqual(transport.calls, [])

    def test_symbol_and_venue_identity_are_never_guessed(self) -> None:
        cases = (
            (request(symbol="600000"), "INVALID_SYMBOL"),
            (request(symbol="600000.sh"), "INVALID_SYMBOL"),
            (request(symbol="600000.SH", venue="SZSE"), "INSTRUMENT_IDENTITY_MISMATCH"),
            (request(symbol="000001.SZ", venue="SSE"), "INSTRUMENT_IDENTITY_MISMATCH"),
            (request(symbol="833171.BJ", venue="SZSE"), "INSTRUMENT_IDENTITY_MISMATCH"),
        )
        for selected_request, expected_code in cases:
            with self.subTest(symbol=selected_request.symbol):
                transport = FixtureTransport()
                selected = TushareDailyProvider(
                    credential_resolver=EnvironmentCredentialResolver({}),
                    transport=transport,
                )
                with self.assertRaises(ProviderFailure) as caught:
                    selected.load(selected_request)
                self.assertEqual(caught.exception.code, expected_code)
                self.assertEqual(transport.calls, [])

    def test_upstream_message_and_unexpected_exception_are_not_disclosed(self) -> None:
        hostile = (
            TOKEN_MARKER
            + " https://example.test/private C:/Users/alice/private "
            + "Authorization: Bearer secret"
        )
        cases = (
            (
                FixtureTransport(
                    fixture_response(code=2002, message=hostile)
                ),
                "UPSTREAM_PERMISSION_DENIED",
            ),
            (FixtureTransport(error=RuntimeError(hostile)), "UPSTREAM_TRANSPORT_ERROR"),
            (
                FixtureTransport(
                    error=TushareTransportError(
                        "UPSTREAM_RESPONSE_INVALID",
                        retryable=False,
                    )
                ),
                "UPSTREAM_RESPONSE_INVALID",
            ),
        )
        for transport, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                with self.assertRaises(ProviderFailure) as caught:
                    provider(transport).load(request())
                rendered = "".join(traceback.format_exception(caught.exception))
                self.assertEqual(caught.exception.code, expected_code)
                self.assertNotIn(TOKEN_MARKER, str(caught.exception))
                self.assertNotIn(TOKEN_MARKER, rendered)
                self.assertNotIn("example.test", rendered)
                self.assertIsNone(caught.exception.__context__)

    def test_transport_error_metadata_is_code_owned_and_strictly_typed(self) -> None:
        with self.assertRaises(ValueError):
            TushareTransportError("UNTRUSTED_CODE", retryable=False)
        with self.assertRaises(ValueError):
            TushareTransportError(
                "UPSTREAM_UNAVAILABLE",
                retryable=1,
            )

    def test_invalid_response_shapes_and_values_fail_closed(self) -> None:
        base_rows = fixture_response()["data"]["items"]
        cases: tuple[tuple[object, str], ...] = (
            ([], "UPSTREAM_RESPONSE_INVALID"),
            ({"code": True, "data": {}}, "UPSTREAM_RESPONSE_INVALID"),
            (
                fixture_response(fields=list(TUSHARE_DAILY_FIELDS[:-1])),
                "UPSTREAM_RESPONSE_INVALID",
            ),
            (
                fixture_response(items=[]),
                "NO_SOURCE_DATA",
            ),
            (
                fixture_response(
                    items=[["000001.SZ", *base_rows[0][1:]]]
                ),
                "INVALID_SOURCE_DATA",
            ),
            (
                fixture_response(
                    items=[["600000.SH", "20250104", *base_rows[0][2:]]]
                ),
                "INVALID_SOURCE_DATA",
            ),
            (
                fixture_response(
                    items=[["600000.SH", "20250103", 10.0, 9.0, 9.5, 10.5, 1.0]]
                ),
                "INVALID_SOURCE_DATA",
            ),
            (
                fixture_response(
                    items=[["600000.SH", "20250103", 10.0, 10.5, 9.5, 10.2, -1.0]]
                ),
                "INVALID_SOURCE_DATA",
            ),
            (
                fixture_response(
                    items=[
                        [
                            "600000.SH",
                            "20250103",
                            10**10000,
                            10.5,
                            9.5,
                            10.2,
                            1.0,
                        ]
                    ]
                ),
                "INVALID_SOURCE_DATA",
            ),
            (
                fixture_response(items=[base_rows[0], list(base_rows[0])]),
                "INVALID_SOURCE_DATA",
            ),
        )
        for response, expected_code in cases:
            with self.subTest(expected_code=expected_code, response_type=type(response)):
                with self.assertRaises(ProviderFailure) as caught:
                    provider(FixtureTransport(response)).load(request())
                self.assertEqual(caught.exception.code, expected_code)


if __name__ == "__main__":
    unittest.main()
