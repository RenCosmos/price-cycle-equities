from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import Enum
import math
import re
from typing import Iterable, Protocol, Sequence

from ..io import analysis_cutoff
from ..models import DataSet, Market, PriceBasis


_PROVIDER_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_QUOTED_PATH_PATTERN = re.compile(
    r"(['\"])(?:[a-zA-Z]:[\\/]|\\\\|/)[^'\"]+\1"
)
_WINDOWS_PATH_PATTERN = re.compile(
    r"(?i)(?:[a-z]:[\\/]|\\\\)[^\s,;]+"
)
_POSIX_PATH_PATTERN = re.compile(r"(?<![:\w])/(?:[^\s,;]+)")
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|token|"
    r"authorization|password|secret)\b\s*[:=]\s*"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;&]+)"
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[^\s,;]+")
_MARKET_DATA_SCOPES = {
    "full_listing",
    "partial_venue",
    "unknown",
    "user_supplied_not_verified",
}
_VOLUME_SCOPES = _MARKET_DATA_SCOPES
_VOLUME_BASES = {
    "raw",
    "split_adjusted",
    "unknown",
    "user_supplied_not_verified",
}
_ZERO_VOLUME_POLICIES = {
    "reported_zero_only",
    "missing_as_zero",
    "unknown",
    "user_supplied_not_verified",
}
_PRICE_BASIS_ASSERTIONS = {
    "provider_verified",
    "user_declared_not_verified",
}
_ARTIFACT_ROLES = {"instrument", "benchmark"}


@dataclass(frozen=True, slots=True)
class DataRequest:
    symbol: str
    market: Market
    as_of: date
    price_basis: PriceBasis
    instrument_id: str | None = None
    venue: str | None = None
    segment: str | None = None
    security_type: str = "COMMON_STOCK"
    benchmark_symbol: str | None = None
    interval: str = "1d"

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol is required")
        if not self.security_type.strip():
            raise ValueError("security_type is required")
        if self.benchmark_symbol is not None and not self.benchmark_symbol.strip():
            raise ValueError("benchmark_symbol cannot be blank")
        if self.interval != "1d":
            raise ValueError("The current deterministic engine supports interval=1d only")


class DataAssuranceMode(str, Enum):
    USER_SUPPLIED_UNVERIFIED = "user_supplied_unverified"
    PROVIDER_VERIFIED = "provider_verified"


class ProviderAttemptStatus(str, Enum):
    SUCCESS = "SUCCESS"
    SKIPPED_UNSUPPORTED = "SKIPPED_UNSUPPORTED"
    FAILED_FALLBACK = "FAILED_FALLBACK"
    FAILED_TERMINAL = "FAILED_TERMINAL"


@dataclass(frozen=True, slots=True)
class ProviderAttempt:
    provider_id: str
    priority: int
    status: ProviderAttemptStatus
    error_code: str | None = None
    message: str | None = None
    retryable: bool | None = None
    fallback_allowed: bool | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "priority": self.priority,
            "status": self.status.value,
            "error_code": self.error_code,
            "message": self.message,
            "retryable": self.retryable,
            "fallback_allowed": self.fallback_allowed,
        }


@dataclass(frozen=True, slots=True)
class SourceArtifact:
    role: str
    provider_id: str
    source_label: str
    artifact_name: str
    snapshot_id: str
    price_basis: PriceBasis
    market_data_scope: str
    volume_scope: str
    volume_basis: str
    zero_volume_policy: str
    timestamp_policy: str
    retrieved_at: datetime | None = None
    revision_id: str | None = None

    def __post_init__(self) -> None:
        if self.role not in _ARTIFACT_ROLES:
            raise ValueError("artifact role must be instrument or benchmark")
        _validate_provider_id(self.provider_id)
        if not self.source_label.strip():
            raise ValueError("artifact source_label is required")
        _validate_artifact_name(self.artifact_name)
        if not self.snapshot_id.strip():
            raise ValueError("artifact snapshot_id is required")
        _validate_quality_fields(
            market_data_scope=self.market_data_scope,
            volume_scope=self.volume_scope,
            volume_basis=self.volume_basis,
            zero_volume_policy=self.zero_volume_policy,
        )
        if not self.timestamp_policy.strip():
            raise ValueError("artifact timestamp_policy is required")
        if self.retrieved_at is not None and self.retrieved_at.tzinfo is None:
            raise ValueError("artifact retrieved_at must include a timezone")


@dataclass(frozen=True, slots=True)
class ProviderLoadResult:
    provider_id: str
    assurance_mode: DataAssuranceMode
    dataset: DataSet
    diagnostics: dict[str, object]
    snapshot_id: str
    artifact_name: str
    artifacts: tuple[SourceArtifact, ...]
    market_data_scope: str
    volume_scope: str
    volume_basis: str
    volume_completeness: float | None
    zero_volume_policy: str
    price_basis_assertion: str
    attempts: tuple[ProviderAttempt, ...] = ()

    def __post_init__(self) -> None:
        _validate_provider_id(self.provider_id)
        if not isinstance(self.assurance_mode, DataAssuranceMode):
            raise ValueError("assurance_mode must be a DataAssuranceMode")
        if not self.snapshot_id.strip():
            raise ValueError("snapshot_id is required")
        _validate_artifact_name(self.artifact_name)
        if not self.artifacts:
            raise ValueError("At least one source artifact is required")
        artifact_roles = [artifact.role for artifact in self.artifacts]
        if len(artifact_roles) != len(set(artifact_roles)):
            raise ValueError("Source artifact roles must be unique")
        if "instrument" not in artifact_roles:
            raise ValueError("An instrument source artifact is required")
        if any(artifact.provider_id != self.provider_id for artifact in self.artifacts):
            raise ValueError("All source artifacts must match result provider_id")
        _validate_quality_fields(
            market_data_scope=self.market_data_scope,
            volume_scope=self.volume_scope,
            volume_basis=self.volume_basis,
            zero_volume_policy=self.zero_volume_policy,
        )
        if self.price_basis_assertion not in _PRICE_BASIS_ASSERTIONS:
            raise ValueError(
                "price_basis_assertion must be provider_verified "
                "or user_declared_not_verified"
            )
        if self.volume_completeness is not None and (
            not math.isfinite(self.volume_completeness)
            or not 0.0 <= self.volume_completeness <= 1.0
        ):
            raise ValueError("volume_completeness must be between 0 and 1")


class ProviderFailure(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        retryable: bool,
        fallback_allowed: bool,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.fallback_allowed = fallback_allowed


class ProviderResolutionError(ProviderFailure):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        attempts: tuple[ProviderAttempt, ...],
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message,
            code=code,
            retryable=retryable,
            fallback_allowed=False,
        )
        self.attempts = attempts


class DataProvider(Protocol):
    @property
    def provider_id(self) -> str:
        ...

    @property
    def assurance_mode(self) -> DataAssuranceMode:
        ...

    def supports(self, request: DataRequest) -> bool:
        ...

    def load(self, request: DataRequest) -> ProviderLoadResult:
        ...


def _validate_provider_id(provider_id: str) -> None:
    if not _PROVIDER_ID_PATTERN.fullmatch(provider_id):
        raise ValueError(
            "provider_id must use lowercase letters, digits, dot, underscore, or hyphen"
        )


def _validate_artifact_name(artifact_name: str) -> None:
    if (
        not artifact_name.strip()
        or "/" in artifact_name
        or "\\" in artifact_name
    ):
        raise ValueError("artifact_name must be a filename or opaque label, not a path")


def _sanitize_public_message(message: str) -> str:
    sanitized = " ".join(message.split())
    sanitized = _URL_PATTERN.sub("[REDACTED_URL]", sanitized)
    sanitized = _QUOTED_PATH_PATTERN.sub("[REDACTED_PATH]", sanitized)
    sanitized = _WINDOWS_PATH_PATTERN.sub("[REDACTED_PATH]", sanitized)
    sanitized = _POSIX_PATH_PATTERN.sub("[REDACTED_PATH]", sanitized)
    sanitized = _SECRET_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group(1)}=[REDACTED]",
        sanitized,
    )
    sanitized = _BEARER_PATTERN.sub("Bearer [REDACTED]", sanitized)
    if not sanitized:
        return "Provider failed without a public detail"
    if len(sanitized) > 500:
        return sanitized[:497] + "..."
    return sanitized


def _validate_quality_fields(
    *,
    market_data_scope: str,
    volume_scope: str,
    volume_basis: str,
    zero_volume_policy: str,
) -> None:
    if market_data_scope not in _MARKET_DATA_SCOPES:
        raise ValueError(f"Unsupported market_data_scope: {market_data_scope}")
    if volume_scope not in _VOLUME_SCOPES:
        raise ValueError(f"Unsupported volume_scope: {volume_scope}")
    if volume_basis not in _VOLUME_BASES:
        raise ValueError(f"Unsupported volume_basis: {volume_basis}")
    if zero_volume_policy not in _ZERO_VOLUME_POLICIES:
        raise ValueError(f"Unsupported zero_volume_policy: {zero_volume_policy}")


class ProviderRegistry:
    def __init__(self, providers: Iterable[DataProvider] = ()) -> None:
        self._providers: dict[str, DataProvider] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: DataProvider) -> None:
        provider_id = provider.provider_id
        _validate_provider_id(provider_id)
        if not isinstance(provider.assurance_mode, DataAssuranceMode):
            raise ValueError(
                f"Provider {provider_id} must declare a DataAssuranceMode"
            )
        if provider_id in self._providers:
            raise ValueError(f"Duplicate provider_id: {provider_id}")
        self._providers[provider_id] = provider

    def get(self, provider_id: str) -> DataProvider | None:
        return self._providers.get(provider_id)

    @property
    def provider_ids(self) -> tuple[str, ...]:
        return tuple(self._providers)


class ProviderRouter:
    def __init__(self, registry: ProviderRegistry) -> None:
        self._registry = registry

    def load(
        self,
        request: DataRequest,
        provider_order: Sequence[str],
    ) -> ProviderLoadResult:
        order = tuple(provider_order)
        if not order:
            raise ProviderResolutionError(
                "No data providers were configured",
                code="EMPTY_PROVIDER_ORDER",
                attempts=(),
            )
        if len(order) != len(set(order)):
            raise ProviderResolutionError(
                "Provider order contains duplicate provider IDs",
                code="INVALID_PROVIDER_ORDER",
                attempts=(),
            )

        attempts: list[ProviderAttempt] = []
        for priority, provider_id in enumerate(order, start=1):
            provider = self._registry.get(provider_id)
            if provider is None:
                attempts.append(
                    ProviderAttempt(
                        provider_id=provider_id,
                        priority=priority,
                        status=ProviderAttemptStatus.FAILED_TERMINAL,
                        error_code="UNKNOWN_PROVIDER",
                        message="Provider is not registered",
                        retryable=False,
                        fallback_allowed=False,
                    )
                )
                raise ProviderResolutionError(
                    f"Unknown data provider: {provider_id}",
                    code="UNKNOWN_PROVIDER",
                    attempts=tuple(attempts),
                )

            try:
                supported = provider.supports(request)
            except Exception as error:
                attempts.append(
                    ProviderAttempt(
                        provider_id=provider_id,
                        priority=priority,
                        status=ProviderAttemptStatus.FAILED_TERMINAL,
                        error_code="PROVIDER_PROTOCOL_ERROR",
                        message="Provider failed while checking request support",
                        retryable=False,
                        fallback_allowed=False,
                    )
                )
                raise ProviderResolutionError(
                    "A data provider violated the provider protocol",
                    code="PROVIDER_PROTOCOL_ERROR",
                    attempts=tuple(attempts),
                ) from error

            if not supported:
                attempts.append(
                    ProviderAttempt(
                        provider_id=provider_id,
                        priority=priority,
                        status=ProviderAttemptStatus.SKIPPED_UNSUPPORTED,
                        error_code="UNSUPPORTED_REQUEST",
                        message="Provider does not support this request",
                        retryable=False,
                        fallback_allowed=True,
                    )
                )
                continue

            try:
                result = provider.load(request)
                self._validate_result(
                    request,
                    provider_id,
                    provider.assurance_mode,
                    result,
                )
            except ProviderFailure as error:
                public_message = _sanitize_public_message(str(error))
                status = (
                    ProviderAttemptStatus.FAILED_FALLBACK
                    if error.fallback_allowed
                    else ProviderAttemptStatus.FAILED_TERMINAL
                )
                attempts.append(
                    ProviderAttempt(
                        provider_id=provider_id,
                        priority=priority,
                        status=status,
                        error_code=error.code,
                        message=public_message,
                        retryable=error.retryable,
                        fallback_allowed=error.fallback_allowed,
                    )
                )
                if error.fallback_allowed:
                    continue
                raise ProviderResolutionError(
                    public_message,
                    code=error.code,
                    attempts=tuple(attempts),
                    retryable=error.retryable,
                ) from error
            except Exception as error:
                attempts.append(
                    ProviderAttempt(
                        provider_id=provider_id,
                        priority=priority,
                        status=ProviderAttemptStatus.FAILED_TERMINAL,
                        error_code="UNEXPECTED_PROVIDER_ERROR",
                        message="Provider raised an unexpected error",
                        retryable=False,
                        fallback_allowed=False,
                    )
                )
                raise ProviderResolutionError(
                    "A data provider raised an unexpected error",
                    code="UNEXPECTED_PROVIDER_ERROR",
                    attempts=tuple(attempts),
                ) from error

            attempts.append(
                ProviderAttempt(
                    provider_id=provider_id,
                    priority=priority,
                    status=ProviderAttemptStatus.SUCCESS,
                )
            )
            routed_attempts = tuple(attempts)
            diagnostics = dict(result.diagnostics)
            diagnostics.update(
                {
                    "data_provider_id": provider_id,
                    "data_provider_attempts": [
                        attempt.as_dict() for attempt in routed_attempts
                    ],
                    "data_provider_fallback_used": len(routed_attempts) > 1,
                    "data_snapshot_id": result.snapshot_id,
                    "data_assurance_mode": result.assurance_mode.value,
                    "market_data_scope": result.market_data_scope,
                    "volume_scope": result.volume_scope,
                    "volume_basis": result.volume_basis,
                    "volume_completeness": result.volume_completeness,
                    "zero_volume_policy": result.zero_volume_policy,
                    "price_basis_assertion": result.price_basis_assertion,
                    "source_artifacts": [
                        {
                            "role": artifact.role,
                            "provider_id": artifact.provider_id,
                            "source_label": artifact.source_label,
                            "artifact_name": artifact.artifact_name,
                            "snapshot_id": artifact.snapshot_id,
                            "price_basis": artifact.price_basis.value,
                            "market_data_scope": artifact.market_data_scope,
                            "volume_scope": artifact.volume_scope,
                            "volume_basis": artifact.volume_basis,
                            "zero_volume_policy": artifact.zero_volume_policy,
                            "timestamp_policy": artifact.timestamp_policy,
                            "retrieved_at": (
                                artifact.retrieved_at.isoformat()
                                if artifact.retrieved_at is not None
                                else None
                            ),
                            "revision_id": artifact.revision_id,
                        }
                        for artifact in result.artifacts
                    ],
                }
            )
            return replace(
                result,
                diagnostics=diagnostics,
                attempts=routed_attempts,
            )

        message = "All configured data providers were unavailable or unsupported"
        if attempts:
            last_attempt = attempts[-1]
            last_code = last_attempt.error_code or last_attempt.status.value
            last_message = last_attempt.message or "No public detail was supplied"
            message += (
                f"; last attempt {last_attempt.provider_id} "
                f"[{last_code}]: {last_message}"
            )
        raise ProviderResolutionError(
            message,
            code="ALL_PROVIDERS_FAILED",
            attempts=tuple(attempts),
            retryable=any(attempt.retryable is True for attempt in attempts),
        )

    @staticmethod
    def _validate_result(
        request: DataRequest,
        provider_id: str,
        declared_assurance_mode: DataAssuranceMode,
        result: ProviderLoadResult,
    ) -> None:
        dataset = result.dataset
        assurance_mismatches: list[str] = []
        if result.assurance_mode is not declared_assurance_mode:
            assurance_mismatches.append("assurance_mode")
        if declared_assurance_mode is DataAssuranceMode.USER_SUPPLIED_UNVERIFIED:
            if result.market_data_scope != "user_supplied_not_verified":
                assurance_mismatches.append("manual_market_data_scope")
            if result.volume_scope != "user_supplied_not_verified":
                assurance_mismatches.append("manual_volume_scope")
            if result.volume_basis != "user_supplied_not_verified":
                assurance_mismatches.append("manual_volume_basis")
            if result.volume_completeness is not None:
                assurance_mismatches.append("manual_volume_completeness")
            if result.zero_volume_policy != "user_supplied_not_verified":
                assurance_mismatches.append("manual_zero_volume_policy")
            if result.price_basis_assertion != "user_declared_not_verified":
                assurance_mismatches.append("manual_price_basis_assertion")
        else:
            if result.market_data_scope == "user_supplied_not_verified":
                assurance_mismatches.append("verified_market_data_scope")
            if result.volume_scope == "user_supplied_not_verified":
                assurance_mismatches.append("verified_volume_scope")
            if result.volume_basis == "user_supplied_not_verified":
                assurance_mismatches.append("verified_volume_basis")
            if result.zero_volume_policy == "user_supplied_not_verified":
                assurance_mismatches.append("verified_zero_volume_policy")
            if result.price_basis_assertion != "provider_verified":
                assurance_mismatches.append("verified_price_basis_assertion")
        if assurance_mismatches:
            raise ProviderFailure(
                "Provider result contradicted its declared assurance mode: "
                + ", ".join(assurance_mismatches),
                code="PROVIDER_ASSURANCE_VIOLATION",
                retryable=False,
                fallback_allowed=True,
            )
        if result.market_data_scope in {"partial_venue", "unknown"}:
            raise ProviderFailure(
                "Provider market coverage is partial or unknown, "
                "which is insufficient for Cycle evidence scoring",
                code="INSUFFICIENT_MARKET_COVERAGE",
                retryable=False,
                fallback_allowed=True,
            )
        if result.volume_scope in {"partial_venue", "unknown"}:
            raise ProviderFailure(
                "Provider volume coverage is partial or unknown, "
                "which is insufficient for Cycle evidence scoring",
                code="INSUFFICIENT_VOLUME_COVERAGE",
                retryable=False,
                fallback_allowed=True,
            )
        if (
            result.volume_completeness is None
            and result.volume_scope != "user_supplied_not_verified"
        ):
            raise ProviderFailure(
                "Provider did not establish complete volume coverage",
                code="UNKNOWN_VOLUME_COMPLETENESS",
                retryable=False,
                fallback_allowed=True,
            )
        if (
            result.volume_completeness is not None
            and result.volume_completeness < 1.0
        ):
            raise ProviderFailure(
                "Provider reported incomplete volume coverage",
                code="INCOMPLETE_VOLUME",
                retryable=False,
                fallback_allowed=True,
            )
        if result.volume_basis == "unknown":
            raise ProviderFailure(
                "Provider volume adjustment basis is unknown",
                code="UNKNOWN_VOLUME_BASIS",
                retryable=False,
                fallback_allowed=True,
            )
        if result.zero_volume_policy in {"missing_as_zero", "unknown"}:
            raise ProviderFailure(
                "Provider may encode missing volume as zero",
                code="UNSAFE_ZERO_VOLUME_POLICY",
                retryable=False,
                fallback_allowed=True,
            )
        mismatches: list[str] = []
        if result.provider_id != provider_id:
            mismatches.append("provider_id")
        if dataset.symbol != request.symbol:
            mismatches.append("symbol")
        if dataset.market is not request.market:
            mismatches.append("market")
        if dataset.as_of != request.as_of:
            mismatches.append("as_of")
        if dataset.price_basis is not request.price_basis:
            mismatches.append("price_basis")
        if dataset.security_type != request.security_type:
            mismatches.append("security_type")
        if request.instrument_id is not None and dataset.instrument_id != request.instrument_id:
            mismatches.append("instrument_id")
        if request.venue is not None and dataset.venue != request.venue:
            mismatches.append("venue")
        if request.segment is not None and dataset.segment != request.segment:
            mismatches.append("segment")
        if dataset.benchmark_symbol != request.benchmark_symbol:
            mismatches.append("benchmark_symbol")
        if bool(dataset.benchmark_bars) != bool(request.benchmark_symbol):
            mismatches.append("benchmark_bars")
        expected_roles = {"instrument"}
        if request.benchmark_symbol:
            expected_roles.add("benchmark")
        if {artifact.role for artifact in result.artifacts} != expected_roles:
            mismatches.append("source_artifacts")
        if any(
            artifact.price_basis is not request.price_basis
            for artifact in result.artifacts
        ):
            mismatches.append("artifact_price_basis")
        if any(
            artifact.market_data_scope != result.market_data_scope
            for artifact in result.artifacts
        ):
            mismatches.append("artifact_market_data_scope")
        if any(
            artifact.volume_scope != result.volume_scope
            for artifact in result.artifacts
        ):
            mismatches.append("artifact_volume_scope")
        if any(
            artifact.volume_basis != result.volume_basis
            for artifact in result.artifacts
        ):
            mismatches.append("artifact_volume_basis")
        if any(
            artifact.zero_volume_policy != result.zero_volume_policy
            for artifact in result.artifacts
        ):
            mismatches.append("artifact_zero_volume_policy")
        cutoff = analysis_cutoff(request.as_of, request.market)
        for role, bars in (
            ("instrument", dataset.bars),
            ("benchmark", dataset.benchmark_bars),
        ):
            if any(bar.session_date > request.as_of for bar in bars):
                mismatches.append(f"{role}_future_session")
            if any(
                bar.known_at is not None and bar.known_at > cutoff
                for bar in bars
            ):
                mismatches.append(f"{role}_future_known_at")
        if mismatches:
            raise ProviderFailure(
                "Provider result violated the normalized data contract: "
                + ", ".join(mismatches),
                code="PROVIDER_CONTRACT_VIOLATION",
                retryable=False,
                fallback_allowed=True,
            )
