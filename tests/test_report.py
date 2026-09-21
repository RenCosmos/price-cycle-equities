from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from tests.helpers import make_bars, make_dataset

from price_cycle.cycle import (
    PHASE_FAMILIES,
    PHASES,
    SOURCE_PHASE_FAMILIES,
    assess_current,
    detect_events,
)
from price_cycle.indicators import build_features
from price_cycle.models import PhaseAssessment
from price_cycle.parameters import ResearchParameters
from price_cycle.report import build_report, render_markdown, write_report_files


class ReportTests(unittest.TestCase):
    def _report(
        self,
        assessments_override: tuple[PhaseAssessment, ...] | None = None,
    ) -> dict[str, object]:
        bars = make_bars(220, step=0.25)
        benchmark = make_bars(220, start_close=200.0, step=0.20)
        dataset = make_dataset(bars, benchmark_bars=benchmark)
        parameters = ResearchParameters()
        features = build_features(dataset, parameters)
        events = detect_events(
            features,
            instrument_id=dataset.instrument_id,
            parameters=parameters,
        )
        assessments = (
            assessments_override
            if assessments_override is not None
            else assess_current(features, events, parameters=parameters)
        )
        diagnostics = {
            "input_rows": len(bars),
            "excluded_after_as_of": 0,
            "excluded_not_yet_known": 0,
            "input_reordered": False,
            "instrument_id_is_fallback": False,
        }
        return build_report(
            dataset=dataset,
            diagnostics=diagnostics,
            features=features,
            assessments=assessments,
            events=events,
            parameters=parameters,
            input_filename="bars.csv",
            input_sha256="a" * 64,
            generated_at=datetime(2025, 9, 1, 12, 0, tzinfo=timezone.utc),
        )

    def test_programmatic_contract_and_safety_boundaries(self) -> None:
        report = self._report()
        expected = {
            "schema_version",
            "generated_at",
            "as_of",
            "instrument",
            "market_context",
            "data_quality",
            "phase_taxonomy",
            "candidate_phases",
            "observed_events",
            "canslim",
            "trade_plan",
            "provenance",
            "versions",
        }
        self.assertTrue(expected.issubset(report))
        self.assertEqual(len(report["candidate_phases"]), 8)
        self.assertEqual(
            {phase["phase_family"] for phase in report["candidate_phases"]},
            set(SOURCE_PHASE_FAMILIES),
        )
        self.assertEqual(
            {
                phase["phase"]: phase["phase_family"]
                for phase in report["candidate_phases"]
            },
            PHASE_FAMILIES,
        )
        self.assertEqual(
            report["phase_taxonomy"]["model"],
            "six_source_families_eight_directional_candidates",
        )
        self.assertTrue(
            all(
                phase["score_is_probability"] is False
                for phase in report["candidate_phases"]
            )
        )
        self.assertTrue(
            all(report["canslim"][factor]["status"] == "UNKNOWN" for factor in "CANSLIM")
        )
        self.assertEqual(report["trade_plan"]["status"], "conditional")
        self.assertFalse(report["trade_plan"]["is_order"])
        self.assertIsNone(report["trade_plan"]["order_time"])
        self.assertIsNone(report["trade_plan"]["fill_time"])
        self.assertIn("market_rules", report["market_context"])
        self.assertFalse(report["market_context"]["execution_ready"])

    def test_markdown_has_fixed_section_order_and_evidence_detail(self) -> None:
        markdown = render_markdown(self._report())
        headings = [
            "## 1. 范围与免责声明",
            "## 2. 一句话结论",
            "## 3. 候选阶段",
            "## 4. CAN SLIM",
            "## 5. 市场环境",
            "## 6. 条件式计划",
            "## 7. 数据质量",
            "## 8. 来源与参数",
        ]
        positions = [markdown.index(heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("### 候选阶段证据明细", markdown)
        self.assertIn("是否为订单：否", markdown)

    def test_summary_is_unknown_when_no_phase_has_positive_support(self) -> None:
        assessments = tuple(
            PhaseAssessment(
                phase=phase,
                score=-0.25,
                confidence="NOT_SUPPORTED",
                evidence_for=(),
                evidence_against=(),
                unknowns=(),
            )
            for phase in PHASES
        )
        report = self._report(assessments)
        self.assertEqual(report["_summary"]["status"], "NO_SUPPORTED_PHASE")
        self.assertEqual(report["_summary"]["top_phase"], "UNKNOWN")
        self.assertEqual(report["_summary"]["top_confidence"], "UNKNOWN")
        self.assertIsNone(report["_summary"]["top_score"])
        markdown = render_markdown(report)
        self.assertIn("当前无可确认阶段", markdown)
        self.assertNotIn("当前证据最支持 **UNKNOWN**", markdown)

    def test_written_json_does_not_expose_workspace_path(self) -> None:
        report = self._report()
        with tempfile.TemporaryDirectory() as directory:
            json_path, markdown_path = write_report_files(
                report,
                output_dir=directory,
            )
            payload = json_path.read_text(encoding="utf-8")
            parsed = json.loads(payload)
            self.assertNotIn("_summary", parsed)
            self.assertEqual(parsed["instrument"]["input_filename"], "bars.csv")
            self.assertNotIn(str(Path.cwd()), payload)
            self.assertTrue(markdown_path.is_file())


if __name__ == "__main__":
    unittest.main()
