from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import Enum
import math
import re
from typing import Iterable, Protocol, Sequence

from ..io import analysis_cutoff
from ..models import DataSet, Market, PriceBasis


_PROVIDER_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_QUOTED_PATH_PATTERN = re.compile(
    r"(['\"])(?:[a-zA-Z]:[\\/]|\\\\|/)[^'\"]+\1"
)
_WINDOWS_PATH_PATTERN = re.compile(
    r"(?i)(?:[a-z]:[\\/]|\\\\)[^\s,;]+"
)
_POSIX_PATH_PATTERN = re.compile(r"(?<![:\w])/(?:[^\s,;]+)")
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b((?:[a-z0-9]+[_-])*(?:api[_-]?key|access[_-]?token|"
    r"refresh[_-]?token|token|authorization|password|secret))"
    r"\b\s*[:=]\s*"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;&]+)"
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[^\s,;]+")
_AUTHORIZATION_HEADER_PATTERN = re.compile(
    r"(?i)\b(?:proxy[-_])?authorization\s*[:=]\s*[^\r\n,;]+"
)
_COOKIE_HEADER_PATTERN = re.compile(
    r"(?i)\b(?:set-cookie|cookie)\s*[:=]\s*[^\r\n,]+"
)
_ERROR_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_SNAPSHOT_ID_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_COUNT_DIAGNOSTIC_KEYS = {
    "input_rows",
    "usable_rows",
    "excluded_after_as_of",
    "excluded_not_yet_known",
    "benchmark_rows",
    "benchmark_input_rows",
    "benchmark_usable_rows",
    "benchmark_excluded_after_as_of",
    "benchmark_excluded_not_yet_known",
}
_BOOLEAN_DIAGNOSTIC_KEYS = {
    "input_reordered",
    "instrument_id_is_fallback",
    "benchmark_supplied",
    "benchmark_input_reordered",
}
_TIMESTAMP_POLICIES = {"session_date_known_after_close"}
_MARKET_DATA_SCOPES = {
    "full_listing",
    "partial_venue",
    "unknown",
    "user_supplied_not_verified",
}
_VOLUME_SCOPES = {
    "full_listing",
    "partial_venue",
    "unknown",
    "user_supplied_not_verified",
    "vendor_reported_unverified",
}
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

    def __post_init__(self) -> None:
        _validate_provider_id(self.provider_id)
        if type(self.priority) is not int or self.priority < 1:
            raise ValueError("provider attempt priority must be positive")
        if not isinstance(self.status, ProviderAttemptStatus):
            raise ValueError("provider attempt status is invalid")
        if self.error_code is not None and not _ERROR_CODE_PATTERN.fullmatch(
            self.error_code
        ):
            raise ValueError("provider error code has an invalid format")
        if self.message is not None and not isinstance(self.message, str):
            raise ValueError("provider attempt message must be a string")
        if self.retryable is not None and type(self.retryable) is not bool:
            raise ValueError("provider attempt retryable must be boolean")
        if (
            self.fallback_allowed is not None
            and type(self.fallback_allowed) is not bool
        ):
            raise ValueError("provider attempt fallback_allowed must be boolean")

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
        _validate_public_label(self.source_label, field="source_label")
        _validate_artifact_name(self.artifact_name)
        _validate_snapshot_id(self.snapshot_id, field="artifact snapshot_id")
        _validate_quality_fields(
            market_data_scope=self.market_data_scope,
            volume_scope=self.volume_scope,
            volume_basis=self.volume_basis,
            zero_volume_policy=self.zero_volume_policy,
        )
        _validate_timestamp_policy(self.timestamp_policy)
        if self.retrieved_at is not None and self.retrieved_at.tzinfo is None:
            raise ValueError("artifact retrieved_at must include a timezone")
        if self.revision_id is not None:
            _validate_public_label(self.revision_id, field="revision_id")


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
        if not isinstance(self.dataset, DataSet):
            raise ValueError("dataset must be a DataSet")
        if not isinstance(self.diagnostics, dict):
            raise ValueError("diagnostics must be a dictionary")
        _validate_snapshot_id(self.snapshot_id, field="snapshot_id")
        _validate_artifact_name(self.artifact_name)
        if not isinstance(self.artifacts, tuple) or not self.artifacts:
            raise ValueError("At least one source artifact is required")
        if any(not isinstance(item, SourceArtifact) for item in self.artifacts):
            raise ValueError("artifacts must contain SourceArtifact values")
        if not isinstance(self.attempts, tuple) or any(
            not isinstance(item, ProviderAttempt) for item in self.attempts
        ):
            raise ValueError("attempts must contain ProviderAttempt values")
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
        if self.volume_completeness is not None:
            if isinstance(self.volume_completeness, bool) or not isinstance(
                self.volume_completeness,
                (int, float),
            ):
                raise ValueError("volume_completeness must be numeric")
            if (
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
        if not isinstance(message, str):
            raise ValueError("provider failure message must be a string")
        if not isinstance(code, str) or not _ERROR_CODE_PATTERN.fullmatch(code):
            raise ValueError("provider error code has an invalid format")
        if type(retryable) is not bool:
            raise ValueError("provider retryable must be boolean")
        if type(fallback_allowed) is not bool:
            raise ValueError("provider fallback_allowed must be boolean")
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
    if not isinstance(artifact_name, str):
        raise ValueError("artifact_name must be a string")
    normalized = artifact_name.strip()
    if (
        not normalized
        or len(normalized) > 128
        or "/" in normalized
        or "\\" in normalized
        or any(ord(character) < 32 or ord(character) == 127 for character in normalized)
        or _URL_PATTERN.search(normalized)
        or _SECRET_ASSIGNMENT_PATTERN.search(normalized)
        or _AUTHORIZATION_HEADER_PATTERN.search(normalized)
        or _COOKIE_HEADER_PATTERN.search(normalized)
        or _BEARER_PATTERN.search(normalized)
    ):
        raise ValueError("artifact_name must be a filename or opaque label, not a path")


def _validate_snapshot_id(value: str, *, field: str) -> None:
    if not _SNAPSHOT_ID_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


def _validate_public_label(value: str, *, field: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"artifact {field} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"artifact {field} is required")
    if len(normalized) > 128:
        raise ValueError(f"artifact {field} is too long")
    if (
        any(ord(character) < 32 or ord(character) == 127 for character in normalized)
        or _URL_PATTERN.search(normalized)
        or _QUOTED_PATH_PATTERN.search(normalized)
        or _WINDOWS_PATH_PATTERN.search(normalized)
        or _POSIX_PATH_PATTERN.search(normalized)
        or _AUTHORIZATION_HEADER_PATTERN.search(normalized)
        or _COOKIE_HEADER_PATTERN.search(normalized)
        or _SECRET_ASSIGNMENT_PATTERN.search(normalized)
        or _BEARER_PATTERN.search(normalized)
    ):
        raise ValueError(f"artifact {field} must be a public label")


def _validate_timestamp_policy(value: str) -> None:
    if value not in _TIMESTAMP_POLICIES:
        raise ValueError("timestamp_policy is not supported")


def _sanitize_public_message(message: str) -> str:
    sanitized = " ".join(message.split())
    sanitized = _URL_PATTERN.sub("[REDACTED_URL]", sanitized)
    sanitized = _QUOTED_PATH_PATTERN.sub("[REDACTED_PATH]", sanitized)
    sanitized = _WINDOWS_PATH_PATTERN.sub("[REDACTED_PATH]", sanitized)
    sanitized = _POSIX_PATH_PATTERN.sub("[REDACTED_PATH]", sanitized)
    sanitized = _AUTHORIZATION_HEADER_PATTERN.sub(
        "Authorization=[REDACTED]",
        sanitized,
    )
    sanitized = _COOKIE_HEADER_PATTERN.sub("Cookie=[REDACTED]", sanitized)
    sanitized = _BEARER_PATTERN.sub("Bearer [REDACTED]", sanitized)
    sanitized = _SECRET_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group(1)}=[REDACTED]",
        sanitized,
    )
    if not sanitized:
        return "Provider failed without a public detail"
    if len(sanitized) > 500:
        return sanitized[:497] + "..."
    return sanitized


def _validated_public_diagnostics(
    result: ProviderLoadResult,
) -> dict[str, object]:
    diagnostics: dict[str, object] = {}
    for key in _COUNT_DIAGNOSTIC_KEYS:
        if key not in result.diagnostics:
            continue
        value = result.diagnostics[key]
        if type(value) is not int or value < 0:
            raise ProviderFailure(
                "Provider supplied an invalid public diagnostic value",
                code="PROVIDER_CONTRACT_VIOLATION",
                retryable=False,
                fallback_allowed=True,
            )
        diagnostics[key] = value
    for key in _BOOLEAN_DIAGNOSTIC_KEYS:
        if key not in result.diagnostics:
            continue
        value = result.diagnostics[key]
        if type(value) is not bool:
            raise ProviderFailure(
                "Provider supplied an invalid public diagnostic value",
                code="PROVIDER_CONTRACT_VIOLATION",
                retryable=False,
                fallback_allowed=True,
            )
        diagnostics[key] = value
    supplied_policy = result.diagnostics.get(
        "timestamp_policy",
        result.dataset.timestamp_policy,
    )
    if supplied_policy != result.dataset.timestamp_policy:
        raise ProviderFailure(
            "Provider diagnostics contradicted the dataset timestamp policy",
            code="PROVIDER_CONTRACT_VIOLATION",
            retryable=False,
            fallback_allowed=True,
        )
    diagnostics["timestamp_policy"] = result.dataset.timestamp_policy
    return diagnostics


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
        if isinstance(provider_order, (str, bytes)):
            raise ProviderResolutionError(
                "Provider order must be a sequence of provider IDs",
                code="INVALID_PROVIDER_ORDER",
                attempts=(),
            )
        order = tuple(provider_order)
        if not order:
            raise ProviderResolutionError(
                "No data providers were configured",
                code="EMPTY_PROVIDER_ORDER",
                attempts=(),
            )
        if any(
            not isinstance(provider_id, str)
            or not _PROVIDER_ID_PATTERN.fullmatch(provider_id)
            for provider_id in order
        ):
            raise ProviderResolutionError(
                "Provider order contains an invalid provider ID",
                code="INVALID_PROVIDER_ORDER",
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

            protocol_error: ProviderResolutionError | None = None
            try:
                supported = provider.supports(request)
                if type(supported) is not bool:
                    raise TypeError("Provider supports() must return bool")
            except Exception:
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
                protocol_error = ProviderResolutionError(
                    "A data provider violated the provider protocol",
                    code="PROVIDER_PROTOCOL_ERROR",
                    attempts=tuple(attempts),
                )
            if protocol_error is not None:
                raise protocol_error

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

            terminal_error: ProviderResolutionError | None = None
            try:
                result = provider.load(request)
                self._validate_result(
                    request,
                    provider_id,
                    provider.assurance_mode,
                    result,
                )
                public_diagnostics = _validated_public_diagnostics(result)
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
                terminal_error = ProviderResolutionError(
                    public_message,
                    code=error.code,
                    attempts=tuple(attempts),
                    retryable=error.retryable,
                )
            except Exception:
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
                terminal_error = ProviderResolutionError(
                    "A data provider raised an unexpected error",
                    code="UNEXPECTED_PROVIDER_ERROR",
                    attempts=tuple(attempts),
                )

            if terminal_error is not None:
                raise terminal_error

            attempts.append(
                ProviderAttempt(
                    provider_id=provider_id,
                    priority=priority,
                    status=ProviderAttemptStatus.SUCCESS,
                )
            )
            routed_attempts = tuple(attempts)
            diagnostics = dict(public_diagnostics)
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
        metadata_error: ProviderFailure | None = None
        try:
            _validate_public_label(dataset.source, field="dataset source")
            _validate_timestamp_policy(dataset.timestamp_policy)
        except ValueError:
            metadata_error = ProviderFailure(
                "Provider dataset metadata was not safe for public output",
                code="PROVIDER_CONTRACT_VIOLATION",
                retryable=False,
                fallback_allowed=True,
            )
        if metadata_error is not None:
            raise metadata_error
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
            result.volume_scope == "vendor_reported_unverified"
            and dataset.volume_evidence_eligible
        ):
            raise ProviderFailure(
                "Unverified provider volume was eligible for Cycle confirmation",
                code="UNVERIFIED_VOLUME_EVIDENCE_ENABLED",
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
        if (
            result.volume_basis == "unknown"
            and dataset.volume_evidence_eligible
        ):
            raise ProviderFailure(
                "Provider volume adjustment basis is unknown while volume "
                "evidence is enabled",
                code="UNKNOWN_VOLUME_BASIS",
                retryable=False,
                fallback_allowed=True,
            )
        if result.zero_volume_policy == "missing_as_zero" or (
            result.zero_volume_policy == "unknown"
            and dataset.volume_evidence_eligible
        ):
            raise ProviderFailure(
                "Provider zero-volume semantics are unsafe while volume "
                "evidence is enabled",
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
        instrument_artifact = next(
            (
                artifact
                for artifact in result.artifacts
                if artifact.role == "instrument"
            ),
            None,
        )
        if (
            instrument_artifact is None
            or instrument_artifact.source_label != dataset.source
        ):
            mismatches.append("instrument_source_label")
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
        if any(
            artifact.timestamp_policy != dataset.timestamp_policy
            for artifact in result.artifacts
        ):
            mismatches.append("artifact_timestamp_policy")
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
