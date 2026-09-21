from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import ClassVar

from ..io import CsvDataError, load_dataset
from .base import (
    DataAssuranceMode,
    DataRequest,
    ProviderFailure,
    ProviderLoadResult,
    SourceArtifact,
)


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_id(
    primary_digest: str,
    benchmark_digest: str | None,
    *,
    request: DataRequest,
    source_label: str,
) -> str:
    digest = sha256()
    artifacts = [("instrument", primary_digest)]
    if benchmark_digest is not None:
        artifacts.append(("benchmark", benchmark_digest))
    for role, artifact_digest in artifacts:
        digest.update(role.encode("utf-8"))
        digest.update(b"\0")
        digest.update(artifact_digest.encode("ascii"))
        digest.update(b"\0")
    metadata = {
        "as_of": request.as_of.isoformat(),
        "benchmark_symbol": request.benchmark_symbol,
        "instrument_id": request.instrument_id,
        "interval": request.interval,
        "market": request.market.value,
        "price_basis": request.price_basis.value,
        "security_type": request.security_type,
        "segment": request.segment,
        "source_label": source_label,
        "symbol": request.symbol,
        "venue": request.venue,
    }
    digest.update(
        json.dumps(
            metadata,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class CsvFileProvider:
    assurance_mode: ClassVar[DataAssuranceMode] = (
        DataAssuranceMode.USER_SUPPLIED_UNVERIFIED
    )
    input_path: str | Path
    source_label: str
    benchmark_path: str | Path | None = None
    provider_id: str = "manual_csv"

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_path", Path(self.input_path))
        if self.benchmark_path is not None:
            object.__setattr__(self, "benchmark_path", Path(self.benchmark_path))
        if not self.source_label.strip():
            raise ValueError("source_label is required")

    def supports(self, request: DataRequest) -> bool:
        return request.interval == "1d"

    def load(self, request: DataRequest) -> ProviderLoadResult:
        input_path = Path(self.input_path)
        benchmark_path = (
            Path(self.benchmark_path)
            if self.benchmark_path is not None
            else None
        )
        if bool(benchmark_path) != bool(request.benchmark_symbol):
            raise ProviderFailure(
                "CSV benchmark artifact and benchmark symbol must be supplied together",
                code="INVALID_PROVIDER_CONFIGURATION",
                retryable=False,
                fallback_allowed=False,
            )
        if not input_path.is_file() or (
            benchmark_path is not None and not benchmark_path.is_file()
        ):
            raise ProviderFailure(
                "One or more configured CSV artifacts are unavailable",
                code="SOURCE_UNAVAILABLE",
                retryable=False,
                fallback_allowed=True,
            )

        try:
            dataset, diagnostics = load_dataset(
                input_path=input_path,
                symbol=request.symbol,
                market=request.market,
                as_of=request.as_of,
                source=self.source_label,
                price_basis=request.price_basis,
                instrument_id=request.instrument_id,
                venue=request.venue,
                segment=request.segment,
                security_type=request.security_type,
                benchmark_path=benchmark_path,
                benchmark_symbol=request.benchmark_symbol,
            )
            primary_digest = _sha256_file(input_path)
            benchmark_digest = (
                _sha256_file(benchmark_path)
                if benchmark_path is not None
                else None
            )
            snapshot_id = _snapshot_id(
                primary_digest,
                benchmark_digest,
                request=request,
                source_label=self.source_label,
            )
        except CsvDataError as error:
            raise ProviderFailure(
                f"Manual CSV validation failed: {error}",
                code="INVALID_SOURCE_DATA",
                retryable=False,
                fallback_allowed=True,
            ) from error
        except OSError as error:
            raise ProviderFailure(
                "A configured CSV artifact could not be read",
                code="SOURCE_UNAVAILABLE",
                retryable=True,
                fallback_allowed=True,
            ) from error

        artifacts = [
            SourceArtifact(
                role="instrument",
                provider_id=self.provider_id,
                source_label=self.source_label,
                artifact_name=input_path.name,
                snapshot_id=primary_digest,
                price_basis=request.price_basis,
                market_data_scope="user_supplied_not_verified",
                volume_scope="user_supplied_not_verified",
                volume_basis="user_supplied_not_verified",
                zero_volume_policy="user_supplied_not_verified",
                timestamp_policy=dataset.timestamp_policy,
            )
        ]
        if benchmark_path is not None:
            artifacts.append(
                SourceArtifact(
                    role="benchmark",
                    provider_id=self.provider_id,
                    source_label=self.source_label,
                    artifact_name=benchmark_path.name,
                    snapshot_id=benchmark_digest,
                    price_basis=request.price_basis,
                    market_data_scope="user_supplied_not_verified",
                    volume_scope="user_supplied_not_verified",
                    volume_basis="user_supplied_not_verified",
                    zero_volume_policy="user_supplied_not_verified",
                    timestamp_policy=dataset.timestamp_policy,
                )
            )
        return ProviderLoadResult(
            provider_id=self.provider_id,
            assurance_mode=self.assurance_mode,
            dataset=dataset,
            diagnostics=diagnostics,
            snapshot_id=snapshot_id,
            artifact_name=input_path.name,
            artifacts=tuple(artifacts),
            market_data_scope="user_supplied_not_verified",
            volume_scope="user_supplied_not_verified",
            volume_basis="user_supplied_not_verified",
            volume_completeness=None,
            zero_volume_policy="user_supplied_not_verified",
            price_basis_assertion="user_declared_not_verified",
        )
