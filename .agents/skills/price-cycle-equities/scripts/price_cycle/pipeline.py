from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Sequence

from .cycle import assess_current, detect_events
from .indicators import build_features
from .models import PhaseAssessment
from .parameters import ResearchParameters
from .providers.base import (
    DataRequest,
    ProviderLoadResult,
    ProviderRouter,
)
from .report import build_report, write_report_files


def _apply_evidence_availability(
    assessments: tuple[PhaseAssessment, ...],
    *,
    volume_evidence_eligible: bool,
) -> tuple[PhaseAssessment, ...]:
    if volume_evidence_eligible:
        return assessments
    return tuple(
        replace(item, confidence="MEDIUM")
        if item.confidence == "HIGH"
        else item
        for item in assessments
    )


def analyze_loaded_result(
    loaded: ProviderLoadResult,
    *,
    output_dir: str | Path,
    overwrite: bool = False,
    parameters: ResearchParameters | None = None,
) -> tuple[Path, Path, list[str]]:
    selected_parameters = parameters or ResearchParameters()
    dataset = loaded.dataset
    features = build_features(dataset, selected_parameters)
    events = detect_events(
        features,
        instrument_id=dataset.instrument_id,
        parameters=selected_parameters,
    )
    assessments = assess_current(
        features,
        events,
        parameters=selected_parameters,
    )
    assessments = _apply_evidence_availability(
        assessments,
        volume_evidence_eligible=dataset.volume_evidence_eligible,
    )
    instrument_artifact = next(
        artifact
        for artifact in loaded.artifacts
        if artifact.role == "instrument"
    )
    report = build_report(
        dataset=dataset,
        diagnostics=loaded.diagnostics,
        features=features,
        assessments=assessments,
        events=events,
        parameters=selected_parameters,
        input_filename=loaded.artifact_name,
        input_sha256=instrument_artifact.snapshot_id,
    )
    json_path, markdown_path = write_report_files(
        report,
        output_dir=output_dir,
        overwrite=overwrite,
    )
    return json_path, markdown_path, list(report["data_quality"]["warnings"])


def analyze_request(
    request: DataRequest,
    *,
    router: ProviderRouter,
    provider_order: Sequence[str],
    output_dir: str | Path,
    overwrite: bool = False,
    parameters: ResearchParameters | None = None,
) -> tuple[Path, Path, list[str]]:
    loaded = router.load(request, provider_order)
    return analyze_loaded_result(
        loaded,
        output_dir=output_dir,
        overwrite=overwrite,
        parameters=parameters,
    )
