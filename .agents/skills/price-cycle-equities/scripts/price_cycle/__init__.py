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

__all__ = [
    "Bar",
    "DataSet",
    "EvidenceItem",
    "FeatureRow",
    "Market",
    "ObservedEvent",
    "PhaseAssessment",
    "PriceBasis",
    "Provenance",
    "ResearchParameters",
    "RuleResolution",
    "RuleResolutionStatus",
    "TriState",
    "rules_at",
]

__version__ = "0.1.0"
