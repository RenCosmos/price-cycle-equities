from __future__ import annotations

from dataclasses import replace
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest

from tests.helpers import SCRIPT_ROOT

from price_cycle.cycle import assess_current, detect_events
from price_cycle.indicators import build_features
from price_cycle.io import load_dataset
from price_cycle.models import Bar, Market, PriceBasis
from price_cycle.parameters import ResearchParameters
from price_cycle.report import build_report, sha256_file


REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_ROOT = REPO_ROOT / "examples" / "golden"


class GoldenExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        manifest = json.loads(
            (GOLDEN_ROOT / "expected.json").read_text(encoding="utf-8")
        )
        cls.cases = manifest["cases"]

    def _analyze(self, case: dict[str, object]):
        dataset, diagnostics = load_dataset(
            input_path=GOLDEN_ROOT / str(case["input"]),
            benchmark_path=GOLDEN_ROOT / str(case["benchmark"]),
            benchmark_symbol=str(case["benchmark_symbol"]),
            symbol=str(case["symbol"]),
            instrument_id=str(case["instrument_id"]),
            market=Market(str(case["market"])),
            as_of=date.fromisoformat(str(case["as_of"])),
            source="synthetic-golden",
            price_basis=PriceBasis.RAW,
            venue=str(case["venue"]),
            segment=(str(case["segment"]) if case["segment"] is not None else None),
            security_type=str(case["security_type"]),
        )
        parameters = ResearchParameters()
        features = build_features(dataset, parameters)
        events = detect_events(
            features,
            instrument_id=dataset.instrument_id,
            parameters=parameters,
        )
        assessments = assess_current(features, events, parameters=parameters)
        report = build_report(
            dataset=dataset,
            diagnostics=diagnostics,
            features=features,
            assessments=assessments,
            events=events,
            parameters=parameters,
            input_filename=str(case["input"]),
            input_sha256=sha256_file(GOLDEN_ROOT / str(case["input"])),
        )
        return dataset, features, events, assessments, report

    def test_locked_cross_market_event_sequences(self) -> None:
        for case in self.cases:
            with self.subTest(case=case["id"]):
                _, _, events, assessments, report = self._analyze(case)
                event_summary = [
                    {
                        "date": event.session_date.isoformat(),
                        "type": event.event_type,
                    }
                    for event in events
                ]
                self.assertEqual(event_summary, case["expected_events"])
                self.assertEqual(assessments[0].phase, case["expected_top_phase"])
                self.assertEqual(
                    assessments[0].confidence,
                    case["expected_top_confidence"],
                )
                self.assertEqual(
                    report["market_context"]["market_rules_status"],
                    case["expected_market_rules_status"],
                )
                self.assertEqual(
                    report["data_quality"]["warnings"],
                    case["expected_warnings"],
                )
                self.assertFalse(report["trade_plan"]["is_order"])

    def test_future_row_is_filtered_before_the_golden_analysis(self) -> None:
        case = self.cases[0]
        original_dataset, original_features, original_events, _, _ = self._analyze(case)
        original_text = (GOLDEN_ROOT / str(case["input"])).read_text(encoding="utf-8")
        future_row = "2026-09-21,1.00,1000.00,0.50,999.00,9999999\n"
        with tempfile.TemporaryDirectory() as directory:
            future_path = Path(directory) / "with-future.csv"
            future_path.write_text(original_text + future_row, encoding="utf-8")
            filtered, diagnostics = load_dataset(
                input_path=future_path,
                benchmark_path=GOLDEN_ROOT / str(case["benchmark"]),
                benchmark_symbol=str(case["benchmark_symbol"]),
                symbol=str(case["symbol"]),
                instrument_id=str(case["instrument_id"]),
                market=Market.CN,
                as_of=date.fromisoformat(str(case["as_of"])),
                source="synthetic-future-test",
                price_basis=PriceBasis.RAW,
                venue="SSE",
                segment="MAIN",
            )
        filtered_features = build_features(filtered)
        filtered_events = detect_events(
            filtered_features,
            instrument_id=filtered.instrument_id,
        )
        self.assertEqual(filtered.bars, original_dataset.bars)
        self.assertEqual(filtered_features, original_features)
        self.assertEqual(filtered_events, original_events)
        self.assertEqual(diagnostics["excluded_after_as_of"], 1)

    def test_price_scaling_preserves_structural_event_sequence(self) -> None:
        case = self.cases[1]
        dataset, features, events, assessments, _ = self._analyze(case)

        def scaled_bar(bar: Bar, factor: float) -> Bar:
            return Bar(
                session_date=bar.session_date,
                open=bar.open * factor,
                high=bar.high * factor,
                low=bar.low * factor,
                close=bar.close * factor,
                volume=bar.volume,
                known_at=bar.known_at,
            )

        scaled = replace(
            dataset,
            bars=tuple(scaled_bar(bar, 10.0) for bar in dataset.bars),
            benchmark_bars=tuple(
                scaled_bar(bar, 10.0) for bar in dataset.benchmark_bars
            ),
        )
        scaled_features = build_features(scaled)
        scaled_events = detect_events(
            scaled_features,
            instrument_id=scaled.instrument_id,
        )
        scaled_assessments = assess_current(scaled_features, scaled_events)

        fingerprint = lambda event: (
            event.event_type,
            event.session_date,
            event.leg_id,
            event.sequence_no,
        )
        self.assertEqual(
            [fingerprint(event) for event in scaled_events],
            [fingerprint(event) for event in events],
        )
        self.assertEqual(
            [(item.phase, item.score, item.confidence) for item in scaled_assessments],
            [(item.phase, item.score, item.confidence) for item in assessments],
        )


if __name__ == "__main__":
    unittest.main()
