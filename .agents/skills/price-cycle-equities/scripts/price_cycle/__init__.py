"""Deterministic research engine for the price-cycle-equities skill."""

from .models import (
    Bar,
    DataSet,
    EvidenceItem,
    FeatureRow,
    Market,
    ObservedEvent,
    PhaseAssessment,
    PriceBasis,
    Provenance,
    TriState,
)
from .parameters import ResearchParameters
from .market_rules import RuleResolution, RuleResolutionStatus, rules_at
from .providers import (
    CsvFileProvider,
    DataAssuranceMode,
    DataRequest,
    ProviderAttempt,
    ProviderAttemptStatus,
    ProviderFailure,
    ProviderLoadResult,
    ProviderRegistry,
    ProviderResolutionError,
    ProviderRouter,
    SourceArtifact,
)

__all__ = [
    "Bar",
    "CsvFileProvider",
    "DataAssuranceMode",
    "DataSet",
    "DataRequest",
    "EvidenceItem",
    "FeatureRow",
    "Market",
    "ObservedEvent",
    "PhaseAssessment",
    "PriceBasis",
    "ProviderAttempt",
    "ProviderAttemptStatus",
    "ProviderFailure",
    "ProviderLoadResult",
    "ProviderRegistry",
    "ProviderResolutionError",
    "ProviderRouter",
    "Provenance",
    "ResearchParameters",
    "RuleResolution",
    "RuleResolutionStatus",
    "SourceArtifact",
    "TriState",
    "rules_at",
]

__version__ = "0.2.0-alpha.1"
