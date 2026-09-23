from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import tempfile
import traceback
import unittest

from tests.helpers import SCRIPT_ROOT, make_bars, make_dataset

from price_cycle.cycle import assess_current, detect_events
from price_cycle.indicators import build_features
from price_cycle.io import load_dataset
from price_cycle.models import Market, PriceBasis
from price_cycle.parameters import ResearchParameters
from price_cycle.providers import (
    CsvFileProvider,
    DataAssuranceMode,
    DataRequest,
    ProviderAttemptStatus,
    ProviderFailure,
    ProviderLoadResult,
    ProviderRegistry,
    ProviderResolutionError,
    ProviderRouter,
    SourceArtifact,
)


class FakeProvider:
    def __init__(
        self,
        provider_id: str,
        *,
        result: ProviderLoadResult | None = None,
        failure: ProviderFailure | None = None,
        supported: bool = True,
        assurance_mode: DataAssuranceMode = DataAssuranceMode.PROVIDER_VERIFIED,
    ) -> None:
        self.provider_id = provider_id
        self.assurance_mode = assurance_mode
        self.result = result
        self.failure = failure
        self.supported = supported
        self.calls = 0

    def supports(self, request: DataRequest) -> bool:
        return self.supported

    def load(self, request: DataRequest) -> ProviderLoadResult:
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        if self.result is None:
            raise AssertionError("Fake provider has no configured result")
        return self.result


def request_for(dataset=None) -> DataRequest:
    selected = dataset or make_dataset(make_bars(220))
    return DataRequest(
        symbol=selected.symbol,
        market=selected.market,
        as_of=selected.as_of,
        price_basis=selected.price_basis,
        instrument_id=selected.instrument_id,
        venue=selected.venue,
        segment=selected.segment,
        security_type=selected.security_type,
        benchmark_symbol=selected.benchmark_symbol,
    )


def result_for(
    provider_id: str,
    dataset=None,
    *,
    scope: str = "full_listing",
    volume_scope: str | None = None,
    volume_basis: str = "raw",
    volume_completeness: float | None = 1.0,
    zero_volume_policy: str = "reported_zero_only",
):
    selected = dataset or make_dataset(make_bars(220))
    resolved_volume_scope = volume_scope or scope
    artifacts = [
        SourceArtifact(
            role="instrument",
            provider_id=provider_id,
            source_label=selected.source,
            artifact_name=f"{provider_id}-instrument.json",
            snapshot_id="b" * 64,
            price_basis=selected.price_basis,
            market_data_scope=scope,
            volume_scope=resolved_volume_scope,
            volume_basis=volume_basis,
            zero_volume_policy=zero_volume_policy,
            timestamp_policy=selected.timestamp_policy,
        )
    ]
    if selected.benchmark_bars:
        artifacts.append(
            SourceArtifact(
                role="benchmark",
                provider_id=provider_id,
                source_label=selected.source,
                artifact_name=f"{provider_id}-benchmark.json",
                snapshot_id="c" * 64,
                price_basis=selected.price_basis,
                market_data_scope=scope,
                volume_scope=resolved_volume_scope,
                volume_basis=volume_basis,
                zero_volume_policy=zero_volume_policy,
                timestamp_policy=selected.timestamp_policy,
            )
        )
    return ProviderLoadResult(
        provider_id=provider_id,
        assurance_mode=DataAssuranceMode.PROVIDER_VERIFIED,
        dataset=selected,
        diagnostics={},
        snapshot_id="a" * 64,
        artifact_name=f"{provider_id}.json",
        artifacts=tuple(artifacts),
        market_data_scope=scope,
        volume_scope=resolved_volume_scope,
        volume_basis=volume_basis,
        volume_completeness=volume_completeness,
        zero_volume_policy=zero_volume_policy,
        price_basis_assertion="provider_verified",
    )


class ProviderRoutingTests(unittest.TestCase):
    def test_invalid_provider_order_returns_stable_resolution_error(self) -> None:
        router = ProviderRouter(ProviderRegistry(()))
        for order in (("Bad Provider",), "manual_csv"):
            with self.subTest(order=order):
                with self.assertRaises(ProviderResolutionError) as caught:
                    router.load(request_for(), order)
                self.assertEqual(
                    caught.exception.code,
                    "INVALID_PROVIDER_ORDER",
                )
                self.assertEqual(caught.exception.attempts, ())

    def test_manual_csv_provider_preserves_legacy_dataset(self) -> None:
        for market in (Market.CN, Market.US):
            with self.subTest(market=market.value), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "bars.csv"
                path.write_text(
                    "date,open,high,low,close,volume\n"
                    "2025-01-02,11,12,10,11.5,110\n"
                    "2025-01-01,10,11,9,10.5,100\n",
                    encoding="utf-8",
                )
                legacy, legacy_diagnostics = load_dataset(
                    input_path=path,
                    symbol="TEST",
                    market=market,
                    as_of=date(2025, 1, 2),
                    source="unit-export",
                    price_basis=PriceBasis.RAW,
                )
                request = DataRequest(
                    symbol="TEST",
                    market=market,
                    as_of=date(2025, 1, 2),
                    price_basis=PriceBasis.RAW,
                )
                provider = CsvFileProvider(path, "unit-export")
                routed = ProviderRouter(
                    ProviderRegistry((provider,))
                ).load(request, (provider.provider_id,))
                self.assertEqual(routed.dataset, legacy)
                self.assertEqual(
                    routed.diagnostics["input_reordered"],
                    legacy_diagnostics["input_reordered"],
                )
                self.assertEqual(
                    routed.diagnostics["price_basis_assertion"],
                    "user_declared_not_verified",
                )
                self.assertEqual(routed.attempts[0].status, ProviderAttemptStatus.SUCCESS)

    def test_chain_uses_priority_and_stops_after_success(self) -> None:
        dataset = make_dataset(make_bars(220))
        first = FakeProvider(
            "primary",
            failure=ProviderFailure(
                "authentication unavailable",
                code="AUTH_UNAVAILABLE",
                retryable=False,
                fallback_allowed=True,
            ),
        )
        second = FakeProvider("backup", result=result_for("backup", dataset))
        third = FakeProvider("unused", result=result_for("unused", dataset))
        router = ProviderRouter(ProviderRegistry((first, second, third)))
        routed = router.load(
            request_for(dataset),
            ("primary", "backup", "unused"),
        )
        self.assertEqual(routed.provider_id, "backup")
        self.assertEqual((first.calls, second.calls, third.calls), (1, 1, 0))
        self.assertEqual(
            [attempt.priority for attempt in routed.attempts],
            [1, 2],
        )
        self.assertEqual(
            [attempt.status for attempt in routed.attempts],
            [
                ProviderAttemptStatus.FAILED_FALLBACK,
                ProviderAttemptStatus.SUCCESS,
            ],
        )
        self.assertTrue(routed.diagnostics["data_provider_fallback_used"])

    def test_global_error_stops_fallback(self) -> None:
        dataset = make_dataset(make_bars(220))
        first = FakeProvider(
            "primary",
            failure=ProviderFailure(
                "ambiguous instrument identity",
                code="AMBIGUOUS_INSTRUMENT",
                retryable=False,
                fallback_allowed=False,
            ),
        )
        second = FakeProvider("backup", result=result_for("backup", dataset))
        router = ProviderRouter(ProviderRegistry((first, second)))
        with self.assertRaises(ProviderResolutionError) as caught:
            router.load(request_for(dataset), ("primary", "backup"))
        self.assertEqual(caught.exception.code, "AMBIGUOUS_INSTRUMENT")
        self.assertEqual((first.calls, second.calls), (1, 0))
        self.assertEqual(
            caught.exception.attempts[0].status,
            ProviderAttemptStatus.FAILED_TERMINAL,
        )

    def test_contract_mismatch_is_rejected_before_fallback_success(self) -> None:
        dataset = make_dataset(make_bars(220))
        wrong_basis = replace(dataset, price_basis=PriceBasis.SPLIT_ADJUSTED)
        broken = FakeProvider(
            "broken",
            result=result_for("broken", wrong_basis),
        )
        backup = FakeProvider("backup", result=result_for("backup", dataset))
        routed = ProviderRouter(
            ProviderRegistry((broken, backup))
        ).load(request_for(dataset), ("broken", "backup"))
        self.assertEqual(routed.provider_id, "backup")
        self.assertEqual(
            routed.attempts[0].error_code,
            "PROVIDER_CONTRACT_VIOLATION",
        )
        self.assertEqual(
            routed.attempts[0].status,
            ProviderAttemptStatus.FAILED_FALLBACK,
        )

    def test_partial_venue_data_is_never_selected(self) -> None:
        dataset = make_dataset(make_bars(220))
        partial = FakeProvider(
            "partial",
            result=result_for("partial", dataset, scope="partial_venue"),
        )
        full = FakeProvider("full", result=result_for("full", dataset))
        routed = ProviderRouter(
            ProviderRegistry((partial, full))
        ).load(request_for(dataset), ("partial", "full"))
        self.assertEqual(routed.provider_id, "full")
        self.assertEqual(
            routed.attempts[0].error_code,
            "INSUFFICIENT_MARKET_COVERAGE",
        )

    def test_artifact_quality_cannot_contradict_result_quality(self) -> None:
        dataset = make_dataset(make_bars(220))
        inconsistent_result = result_for("inconsistent", dataset)
        inconsistent_result = replace(
            inconsistent_result,
            artifacts=(
                replace(
                    inconsistent_result.artifacts[0],
                    volume_basis="unknown",
                ),
            ),
        )
        inconsistent = FakeProvider(
            "inconsistent",
            result=inconsistent_result,
        )
        backup = FakeProvider("backup", result=result_for("backup", dataset))
        routed = ProviderRouter(
            ProviderRegistry((inconsistent, backup))
        ).load(request_for(dataset), ("inconsistent", "backup"))
        self.assertEqual(routed.provider_id, "backup")
        self.assertEqual(
            routed.attempts[0].error_code,
            "PROVIDER_CONTRACT_VIOLATION",
        )

    def test_verified_provider_cannot_claim_manual_data_exception(self) -> None:
        dataset = make_dataset(make_bars(220))
        disguised = result_for(
            "remote",
            dataset,
            scope="user_supplied_not_verified",
            volume_basis="user_supplied_not_verified",
            volume_completeness=None,
            zero_volume_policy="user_supplied_not_verified",
        )
        disguised = replace(
            disguised,
            assurance_mode=DataAssuranceMode.USER_SUPPLIED_UNVERIFIED,
            price_basis_assertion="user_declared_not_verified",
        )
        remote = FakeProvider("remote", result=disguised)
        backup = FakeProvider("backup", result=result_for("backup", dataset))
        routed = ProviderRouter(
            ProviderRegistry((remote, backup))
        ).load(request_for(dataset), ("remote", "backup"))
        self.assertEqual(routed.provider_id, "backup")
        self.assertEqual(
            routed.attempts[0].error_code,
            "PROVIDER_ASSURANCE_VIOLATION",
        )

    def test_provider_error_message_is_sanitized_before_audit(self) -> None:
        dataset = make_dataset(make_bars(220))
        first_marker = "fixture-" + "token-value"
        second_marker = "fixture-" + "key-value"
        third_marker = "fixture-" + "prefixed-token-value"
        fourth_marker = "fixture-" + "bearer-value"
        fifth_marker = "fixture-" + "basic-value"
        sixth_marker = "fixture-" + "proxy-token-value"
        seventh_marker = "fixture-" + "cookie-value"
        sensitive_path = "C:" + "/Users/alice/private.csv"
        unsafe_message = (
            "fetch https://example.test/data?"
            + "token="
            + first_marker
            + " from "
            + sensitive_path
            + " api_"
            + "key="
            + second_marker
            + " TUSHARE_TOKEN="
            + third_marker
            + " Authorization: Bearer "
            + fourth_marker
            + "; Authorization: Basic "
            + fifth_marker
            + "; Proxy-Authorization: Token "
            + sixth_marker
            + "; Cookie: session="
            + seventh_marker
        )
        unsafe = FakeProvider(
            "unsafe",
            failure=ProviderFailure(
                unsafe_message,
                code="SOURCE_UNAVAILABLE",
                retryable=False,
                fallback_allowed=True,
            ),
        )
        backup = FakeProvider("backup", result=result_for("backup", dataset))
        routed = ProviderRouter(
            ProviderRegistry((unsafe, backup))
        ).load(request_for(dataset), ("unsafe", "backup"))
        audited = str(routed.diagnostics["data_provider_attempts"])
        self.assertNotIn(first_marker, audited)
        self.assertNotIn(second_marker, audited)
        self.assertNotIn(third_marker, audited)
        self.assertNotIn(fourth_marker, audited)
        self.assertNotIn(fifth_marker, audited)
        self.assertNotIn(sixth_marker, audited)
        self.assertNotIn(seventh_marker, audited)
        self.assertNotIn(sensitive_path, audited)
        self.assertNotIn("https://example.test", audited)
        self.assertIn("[REDACTED", audited)

    def test_raw_provider_exceptions_are_not_chained_into_public_errors(self) -> None:
        marker = "fixture-" + "terminal-secret"
        dataset = make_dataset(make_bars(220))

        class SupportExplosion:
            provider_id = "support_explosion"
            assurance_mode = DataAssuranceMode.PROVIDER_VERIFIED

            def supports(self, request: DataRequest) -> bool:
                del request
                raise RuntimeError("Authorization: Basic " + marker)

            def load(self, request: DataRequest) -> ProviderLoadResult:
                del request
                raise AssertionError("unreachable")

        class LoadExplosion:
            provider_id = "load_explosion"
            assurance_mode = DataAssuranceMode.PROVIDER_VERIFIED

            def supports(self, request: DataRequest) -> bool:
                del request
                return True

            def load(self, request: DataRequest) -> ProviderLoadResult:
                del request
                raise RuntimeError("TUSHARE_TOKEN=" + marker)

        providers = (
            FakeProvider(
                "terminal",
                failure=ProviderFailure(
                    "TUSHARE_TOKEN=" + marker,
                    code="AUTH_UNAVAILABLE",
                    retryable=False,
                    fallback_allowed=False,
                ),
            ),
            SupportExplosion(),
            LoadExplosion(),
        )
        for provider in providers:
            with self.subTest(provider=provider.provider_id):
                router = ProviderRouter(ProviderRegistry((provider,)))
                with self.assertRaises(ProviderResolutionError) as caught:
                    router.load(
                        request_for(dataset),
                        (provider.provider_id,),
                    )
                rendered = "".join(
                    traceback.format_exception(caught.exception)
                )
                self.assertNotIn(marker, rendered)
                self.assertIsNone(caught.exception.__context__)

    def test_invalid_error_code_is_rejected_before_audit(self) -> None:
        with self.assertRaises(ValueError):
            ProviderFailure(
                "public message",
                code="invalid-code",
                retryable=False,
                fallback_allowed=False,
            )

    def test_provider_booleans_and_completeness_use_strict_types(self) -> None:
        with self.assertRaises(ValueError):
            replace(result_for("safe"), volume_completeness=True)
        for field in ("retryable", "fallback_allowed"):
            arguments = {
                "retryable": False,
                "fallback_allowed": False,
            }
            arguments[field] = "false"
            with self.subTest(field=field), self.assertRaises(ValueError):
                ProviderFailure(
                    "public message",
                    code="SOURCE_UNAVAILABLE",
                    **arguments,
                )

    def test_supports_must_return_an_actual_boolean(self) -> None:
        class StringSupportProvider:
            provider_id = "string_support"
            assurance_mode = DataAssuranceMode.PROVIDER_VERIFIED

            def supports(self, request: DataRequest) -> bool:
                del request
                return "false"

            def load(self, request: DataRequest) -> ProviderLoadResult:
                del request
                raise AssertionError("unreachable")

        provider = StringSupportProvider()
        router = ProviderRouter(ProviderRegistry((provider,)))
        with self.assertRaises(ProviderResolutionError) as caught:
            router.load(request_for(), (provider.provider_id,))
        self.assertEqual(caught.exception.code, "PROVIDER_PROTOCOL_ERROR")
        self.assertIsNone(caught.exception.__context__)

    def test_provider_diagnostics_use_an_explicit_public_allowlist(self) -> None:
        marker = "fixture-private-diagnostic"
        dataset = make_dataset(make_bars(220))
        result = replace(
            result_for("safe", dataset),
            diagnostics={
                "input_rows": 220,
                "provider_debug_payload": marker,
            },
        )
        provider = FakeProvider("safe", result=result)
        routed = ProviderRouter(ProviderRegistry((provider,))).load(
            request_for(dataset),
            ("safe",),
        )
        self.assertEqual(routed.diagnostics["input_rows"], 220)
        self.assertNotIn("provider_debug_payload", routed.diagnostics)
        self.assertNotIn(marker, str(routed.diagnostics))

    def test_allowlisted_diagnostic_values_are_type_checked(self) -> None:
        marker = "fixture-private-diagnostic"
        dataset = make_dataset(make_bars(220))
        unsafe_result = replace(
            result_for("unsafe", dataset),
            diagnostics={"input_rows": marker},
        )
        unsafe = FakeProvider("unsafe", result=unsafe_result)
        backup = FakeProvider("backup", result=result_for("backup", dataset))
        routed = ProviderRouter(
            ProviderRegistry((unsafe, backup))
        ).load(request_for(dataset), ("unsafe", "backup"))
        self.assertEqual(routed.provider_id, "backup")
        self.assertEqual(
            routed.attempts[0].error_code,
            "PROVIDER_CONTRACT_VIOLATION",
        )
        self.assertNotIn(marker, str(routed.diagnostics))

    def test_public_source_label_allows_brand_slash_but_rejects_secrets(self) -> None:
        artifact = result_for("safe").artifacts[0]
        accepted = replace(artifact, source_label="Wind/同花顺")
        self.assertEqual(accepted.source_label, "Wind/同花顺")
        with self.assertRaises(ValueError):
            replace(
                artifact,
                source_label="TUSHARE_TOKEN=fixture-secret",
            )

    def test_public_metadata_fields_reject_secret_shaped_values(self) -> None:
        result = result_for("safe")
        artifact = result.artifacts[0]
        mutations = (
            lambda: replace(result, snapshot_id="fixture-secret"),
            lambda: replace(artifact, snapshot_id="fixture-secret"),
            lambda: replace(
                artifact,
                artifact_name="token=fixture-secret.csv",
            ),
            lambda: replace(
                artifact,
                timestamp_policy="fixture-secret",
            ),
            lambda: replace(
                artifact,
                revision_id="Authorization: Basic fixture-secret",
            ),
        )
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(ValueError):
                mutation()

    def test_dataset_source_is_revalidated_before_report_output(self) -> None:
        base_dataset = make_dataset(make_bars(220))
        unsafe_dataset = replace(
            base_dataset,
            source="Authorization: Basic fixture-secret",
        )
        unsafe_result = replace(
            result_for("unsafe", base_dataset),
            dataset=unsafe_dataset,
        )
        unsafe = FakeProvider("unsafe", result=unsafe_result)
        backup = FakeProvider(
            "backup",
            result=result_for("backup", base_dataset),
        )
        routed = ProviderRouter(
            ProviderRegistry((unsafe, backup))
        ).load(request_for(base_dataset), ("unsafe", "backup"))
        self.assertEqual(routed.provider_id, "backup")
        self.assertNotIn("fixture-secret", str(routed.diagnostics))

    def test_dataset_source_must_match_instrument_artifact(self) -> None:
        base_dataset = make_dataset(make_bars(220))
        mismatched_dataset = replace(base_dataset, source="other-safe-source")
        mismatched_result = replace(
            result_for("mismatch", base_dataset),
            dataset=mismatched_dataset,
        )
        mismatch = FakeProvider("mismatch", result=mismatched_result)
        backup = FakeProvider(
            "backup",
            result=result_for("backup", base_dataset),
        )
        routed = ProviderRouter(
            ProviderRegistry((mismatch, backup))
        ).load(request_for(base_dataset), ("mismatch", "backup"))
        self.assertEqual(routed.provider_id, "backup")
        self.assertEqual(
            routed.attempts[0].error_code,
            "PROVIDER_CONTRACT_VIOLATION",
        )

    def test_unsafe_volume_semantics_are_never_selected(self) -> None:
        dataset = make_dataset(make_bars(220))
        cases = (
            (
                {"volume_scope": "partial_venue"},
                "INSUFFICIENT_VOLUME_COVERAGE",
            ),
            (
                {"volume_completeness": 0.95},
                "INCOMPLETE_VOLUME",
            ),
            (
                {"volume_completeness": None},
                "UNKNOWN_VOLUME_COMPLETENESS",
            ),
            (
                {"volume_basis": "unknown"},
                "UNKNOWN_VOLUME_BASIS",
            ),
            (
                {"zero_volume_policy": "missing_as_zero"},
                "UNSAFE_ZERO_VOLUME_POLICY",
            ),
        )
        for quality, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                unsafe = FakeProvider(
                    "unsafe",
                    result=result_for("unsafe", dataset, **quality),
                )
                backup = FakeProvider(
                    "backup",
                    result=result_for("backup", dataset),
                )
                routed = ProviderRouter(
                    ProviderRegistry((unsafe, backup))
                ).load(request_for(dataset), ("unsafe", "backup"))
                self.assertEqual(routed.provider_id, "backup")
                self.assertEqual(
                    routed.attempts[0].error_code,
                    expected_code,
                )

    def test_vendor_unverified_volume_requires_evidence_to_be_disabled(self) -> None:
        dataset = make_dataset(make_bars(220))
        unsafe = FakeProvider(
            "unsafe",
            result=result_for(
                "unsafe",
                dataset,
                volume_scope="vendor_reported_unverified",
            ),
        )
        backup = FakeProvider(
            "backup",
            result=result_for("backup", dataset),
        )
        routed = ProviderRouter(
            ProviderRegistry((unsafe, backup))
        ).load(request_for(dataset), ("unsafe", "backup"))
        self.assertEqual(routed.provider_id, "backup")
        self.assertEqual(
            routed.attempts[0].error_code,
            "UNVERIFIED_VOLUME_EVIDENCE_ENABLED",
        )

        price_only_dataset = replace(
            dataset,
            volume_evidence_eligible=False,
        )
        price_only = FakeProvider(
            "price_only",
            result=result_for(
                "price_only",
                price_only_dataset,
                volume_scope="vendor_reported_unverified",
            ),
        )
        selected = ProviderRouter(
            ProviderRegistry((price_only,))
        ).load(request_for(price_only_dataset), ("price_only",))
        self.assertEqual(selected.provider_id, "price_only")

        unknown_volume_semantics = FakeProvider(
            "unknown_volume_semantics",
            result=result_for(
                "unknown_volume_semantics",
                price_only_dataset,
                volume_scope="vendor_reported_unverified",
                volume_basis="unknown",
                zero_volume_policy="unknown",
            ),
        )
        selected_unknown = ProviderRouter(
            ProviderRegistry((unknown_volume_semantics,))
        ).load(
            request_for(price_only_dataset),
            ("unknown_volume_semantics",),
        )
        self.assertEqual(selected_unknown.provider_id, "unknown_volume_semantics")

    def test_future_known_at_is_rejected_before_fallback(self) -> None:
        dataset = make_dataset(make_bars(220))
        future_bars = list(dataset.bars)
        future_bars[-1] = replace(
            future_bars[-1],
            known_at=datetime.combine(
                dataset.as_of + timedelta(days=2),
                datetime.max.time(),
                tzinfo=timezone.utc,
            ),
        )
        leaked = replace(dataset, bars=tuple(future_bars))
        future_provider = FakeProvider(
            "future",
            result=result_for("future", leaked),
        )
        backup = FakeProvider("backup", result=result_for("backup", dataset))
        routed = ProviderRouter(
            ProviderRegistry((future_provider, backup))
        ).load(request_for(dataset), ("future", "backup"))
        self.assertEqual(routed.provider_id, "backup")
        self.assertEqual(
            routed.attempts[0].error_code,
            "PROVIDER_CONTRACT_VIOLATION",
        )

    def test_all_sources_fail_closed_with_complete_audit(self) -> None:
        failure = ProviderFailure(
            "temporary outage",
            code="SOURCE_UNAVAILABLE",
            retryable=True,
            fallback_allowed=True,
        )
        first = FakeProvider("first", failure=failure)
        second = FakeProvider("second", failure=failure)
        router = ProviderRouter(ProviderRegistry((first, second)))
        with self.assertRaises(ProviderResolutionError) as caught:
            router.load(request_for(), ("first", "second"))
        self.assertEqual(caught.exception.code, "ALL_PROVIDERS_FAILED")
        self.assertTrue(caught.exception.retryable)
        self.assertEqual(len(caught.exception.attempts), 2)
        self.assertTrue(
            all(
                attempt.status is ProviderAttemptStatus.FAILED_FALLBACK
                for attempt in caught.exception.attempts
            )
        )

    def test_strategy_semantics_do_not_depend_on_provider_name(self) -> None:
        base = make_dataset(make_bars(220, step=0.25))
        datasets = (
            replace(base, source="mainland-source"),
            replace(base, source="independent-source"),
        )
        outputs = []
        parameters = ResearchParameters()
        for provider_id, dataset in zip(("mainland", "independent"), datasets):
            provider = FakeProvider(
                provider_id,
                result=result_for(provider_id, dataset),
            )
            routed = ProviderRouter(
                ProviderRegistry((provider,))
            ).load(request_for(dataset), (provider_id,))
            features = build_features(routed.dataset, parameters)
            events = detect_events(
                features,
                instrument_id=routed.dataset.instrument_id,
                parameters=parameters,
            )
            assessments = assess_current(features, events, parameters=parameters)
            outputs.append((features, events, assessments))
        self.assertEqual(outputs[0], outputs[1])


if __name__ == "__main__":
    unittest.main()
