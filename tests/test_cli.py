from __future__ import annotations

import csv
from datetime import date, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.helpers import SCRIPT_ROOT


ENTRYPOINT = SCRIPT_ROOT / "analyze.py"


class CliTests(unittest.TestCase):
    def _write_bars(self, path: Path, count: int = 220) -> date:
        start = date(2026, 1, 1)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(("date", "open", "high", "low", "close", "volume"))
            for index in range(count):
                session_date = start + timedelta(days=index)
                close = 100.0 + index * 0.20
                writer.writerow(
                    (
                        session_date.isoformat(),
                        f"{close - 0.10:.2f}",
                        f"{close + 1.00:.2f}",
                        f"{close - 1.00:.2f}",
                        f"{close:.2f}",
                        1000 + index * 5,
                    )
                )
        return start + timedelta(days=count - 1)

    def _command(
        self,
        input_path: Path,
        output_dir: Path,
        as_of: date,
        *extra: str,
        price_basis: str = "raw",
    ) -> list[str]:
        return [
            sys.executable,
            str(ENTRYPOINT),
            "--input",
            str(input_path),
            "--market",
            "CN",
            "--symbol",
            "600000",
            "--as-of",
            as_of.isoformat(),
            "--source",
            "unit-test-export",
            "--price-basis",
            price_basis,
            "--venue",
            "SSE",
            "--segment",
            "MAIN",
            "--output-dir",
            str(output_dir),
            *extra,
        ]

    def _run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PYTHONUTF8"] = "1"
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            check=False,
        )

    def test_end_to_end_creates_private_path_free_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bars_path = root / "bars.csv"
            output_dir = root / "reports"
            as_of = self._write_bars(bars_path)
            result = self._run(
                self._command(
                    bars_path,
                    output_dir,
                    as_of,
                    price_basis="split_adjusted",
                )
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            target = output_dir / "cn" / "600000" / as_of.isoformat()
            json_path = target / "report.json"
            markdown_path = target / "report.md"
            self.assertTrue(json_path.is_file())
            self.assertTrue(markdown_path.is_file())
            payload = json_path.read_text(encoding="utf-8")
            report = json.loads(payload)
            input_digest = sha256(bars_path.read_bytes()).hexdigest()
            self.assertEqual(
                report["instrument"]["input_sha256"],
                input_digest,
            )
            self.assertEqual(
                report["data_lineage"]["artifacts"][0]["snapshot_id"],
                input_digest,
            )
            self.assertEqual(
                report["data_lineage"]["data_snapshot_id"],
                report["versions"]["data_snapshot_id"],
            )
            self.assertNotEqual(
                report["data_lineage"]["data_snapshot_id"],
                input_digest,
            )
            self.assertEqual(
                report["data_lineage"]["selected_provider_id"],
                "manual_csv",
            )
            self.assertEqual(
                report["data_lineage"]["attempts"][0]["status"],
                "SUCCESS",
            )
            self.assertEqual(
                report["data_lineage"]["price_basis_assertion"],
                "user_declared_not_verified",
            )
            self.assertEqual(
                report["data_lineage"]["assurance_mode"],
                "user_supplied_unverified",
            )
            self.assertEqual(
                report["data_lineage"]["artifacts"][0]["role"],
                "instrument",
            )
            self.assertIn(
                "PRICE_BASIS_NOT_PROVIDER_VERIFIED",
                report["data_quality"]["warnings"],
            )
            self.assertIn(
                "MARKET_DATA_SCOPE_NOT_PROVIDER_VERIFIED",
                report["data_quality"]["warnings"],
            )
            self.assertIn(
                "VOLUME_QUALITY_NOT_PROVIDER_VERIFIED",
                report["data_quality"]["warnings"],
            )
            self.assertIn(
                "ADJUSTED_PRICE_POINT_IN_TIME_RISK",
                report["data_quality"]["warnings"],
            )
            self.assertEqual(
                report["market_context"]["market_rules_status"],
                "RESOLVED",
            )
            self.assertFalse(report["market_context"]["execution_ready"])
            self.assertNotIn(str(root), payload)
            self.assertIn("no order was created", result.stdout)

    def test_benchmark_arguments_must_be_paired(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bars_path = root / "bars.csv"
            as_of = self._write_bars(bars_path, count=2)
            result = self._run(
                self._command(
                    bars_path,
                    root / "reports",
                    as_of,
                    "--benchmark",
                    str(bars_path),
                )
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("must be supplied together", result.stderr)

    def test_existing_report_is_not_overwritten_without_flag(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bars_path = root / "bars.csv"
            output_dir = root / "reports"
            as_of = self._write_bars(bars_path)
            command = self._command(bars_path, output_dir, as_of)
            first = self._run(command)
            second = self._run(command)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 4)
            self.assertIn("--overwrite", second.stderr)

    def test_bad_csv_returns_data_error_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bars_path = root / "bad.csv"
            bars_path.write_text(
                "date,open,high,low,close\n2025-01-01,10,11,9,10\n",
                encoding="utf-8",
            )
            result = self._run(
                self._command(
                    bars_path,
                    root / "reports",
                    date(2025, 1, 1),
                )
            )
            self.assertEqual(result.returncode, 3)
            self.assertIn("Data error", result.stderr)
            self.assertIn("missing required columns", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse((root / "reports").exists())

    def test_missing_csv_reports_safe_actionable_source_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "private" / "missing.csv"
            result = self._run(
                self._command(
                    missing,
                    root / "reports",
                    date(2025, 1, 1),
                )
            )
            self.assertEqual(result.returncode, 3)
            self.assertIn("SOURCE_UNAVAILABLE", result.stderr)
            self.assertIn("CSV artifacts are unavailable", result.stderr)
            self.assertNotIn(str(missing), result.stderr)
            self.assertFalse((root / "reports").exists())

    def test_source_url_or_private_path_is_rejected_without_disclosure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bars_path = root / "bars.csv"
            as_of = self._write_bars(bars_path, count=2)
            markers = (
                "https://example.test/private?token=fixture-secret",
                "C:/Users/alice/private-source.csv",
            )
            for index, marker in enumerate(markers):
                with self.subTest(index=index):
                    result = self._run(
                        self._command(
                            bars_path,
                            root / f"reports-{index}",
                            as_of,
                            "--source",
                            marker,
                        )
                    )
                    self.assertEqual(result.returncode, 3)
                    self.assertIn(
                        "INVALID_PROVIDER_CONFIGURATION",
                        result.stderr,
                    )
                    self.assertNotIn(marker, result.stderr)
                    self.assertNotIn("fixture-secret", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
