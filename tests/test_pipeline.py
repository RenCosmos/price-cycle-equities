from __future__ import annotations

import unittest

from tests.helpers import SCRIPT_ROOT

from price_cycle.models import PhaseAssessment
from price_cycle.pipeline import _apply_evidence_availability


del SCRIPT_ROOT


def assessment(confidence: str) -> PhaseAssessment:
    return PhaseAssessment(
        phase="Wedge Pop",
        score=0.8,
        confidence=confidence,
        evidence_for=(),
        evidence_against=(),
        unknowns=(),
    )


class PipelineSafetyTests(unittest.TestCase):
    def test_unverified_volume_caps_high_confidence_only(self) -> None:
        high = assessment("HIGH")
        medium = assessment("MEDIUM")
        disabled = _apply_evidence_availability(
            (high, medium),
            volume_evidence_eligible=False,
        )
        self.assertEqual(
            [item.confidence for item in disabled],
            ["MEDIUM", "MEDIUM"],
        )
        self.assertEqual(disabled[0].score, high.score)

        enabled = _apply_evidence_availability(
            (high, medium),
            volume_evidence_eligible=True,
        )
        self.assertEqual(enabled, (high, medium))


if __name__ == "__main__":
    unittest.main()
