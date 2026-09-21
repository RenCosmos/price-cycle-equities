from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from tests.helpers import SCRIPT_ROOT

from price_cycle.io import CsvDataError, load_bars_csv, load_dataset
from price_cycle.models import Bar, DataSet, Market, PriceBasis


class CsvIoTests(unittest.TestCase):
    def _write(self, directory: str, content: str) -> Path:
        path = Path(directory) / "bars.csv"
        path.write_text(content, encoding="utf-8")
        return path

    def test_filters_future_and_not_yet_known_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(
                directory,
                "date,open,high,low,close,volume,known_at\n"
                "2025-01-01,10,11,9,10.5,100,2025-01-01T16:00:00+08:00\n"
                "2025-01-02,11,12,10,11.5,110,2025-01-03T00:00:00+08:00\n"
                "2025-01-03,12,13,11,12.5,120,2025-01-03T16:00:00+08:00\n",
            )
            result = load_bars_csv(
                path, as_of=date(2025, 1, 2), market=Market.CN
            )
            self.assertEqual(len(result.bars), 1)
            self.assertEqual(result.excluded_after_as_of, 1)
            self.assertEqual(result.excluded_not_yet_known, 1)

    def test_descending_input_is_normalized_and_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(
                directory,
                "date,open,high,low,close,volume\n"
                "2025-01-02,11,12,10,11.5,110\n"
                "2025-01-01,10,11,9,10.5,100\n",
            )
            result = load_bars_csv(
                path, as_of=date(2025, 1, 2), market=Market.US
            )
            self.assertTrue(result.reordered)
            self.assertEqual(result.bars[0].session_date, date(2025, 1, 1))

    def test_missing_column_and_duplicate_date_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = self._write(
                directory,
                "date,open,high,low,close\n"
                "2025-01-01,10,11,9,10.5\n",
            )
            with self.assertRaisesRegex(CsvDataError, "volume"):
                load_bars_csv(missing, as_of=date(2025, 1, 1), market=Market.US)

            duplicate = self._write(
                directory,
                "date,open,high,low,close,volume\n"
                "2025-01-01,10,11,9,10.5,100\n"
                "2025-01-01,10,11,9,10.5,100\n",
            )
            with self.assertRaisesRegex(CsvDataError, "duplicate"):
                load_bars_csv(
                    duplicate, as_of=date(2025, 1, 1), market=Market.US
                )

    def test_dataset_uses_explicit_metadata_and_marks_fallback_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(
                directory,
                "date,open,high,low,close,volume\n"
                "2025-01-01,10,11,9,10.5,100\n",
            )
            dataset, diagnostics = load_dataset(
                input_path=path,
                symbol="TEST",
                market=Market.US,
                as_of=date(2025, 1, 1),
                source="unit-test",
                price_basis=PriceBasis.RAW,
                venue="XNYS",
                segment="NMS",
                security_type="ADR",
            )
            self.assertEqual(dataset.instrument_id, "US:TEST")
            self.assertEqual(dataset.venue, "XNYS")
            self.assertEqual(dataset.security_type, "ADR")
            self.assertTrue(diagnostics["instrument_id_is_fallback"])

    def test_dataset_rejects_future_benchmark_bar(self) -> None:
        instrument = Bar(
            session_date=date(2025, 1, 1),
            open=10.0,
            high=11.0,
            low=9.0,
            close=10.5,
            volume=100.0,
        )
        future_benchmark = Bar(
            session_date=date(2025, 1, 2),
            open=20.0,
            high=21.0,
            low=19.0,
            close=20.5,
            volume=200.0,
        )
        with self.assertRaisesRegex(ValueError, "benchmark bar after as_of"):
            DataSet(
                instrument_id="US:TEST",
                symbol="TEST",
                market=Market.US,
                as_of=date(2025, 1, 1),
                source="unit-test",
                price_basis=PriceBasis.RAW,
                bars=(instrument,),
                benchmark_symbol="BENCH",
                benchmark_bars=(future_benchmark,),
            )

    def test_benchmark_filtering_and_reordering_are_audited(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            primary = root / "primary.csv"
            benchmark = root / "benchmark.csv"
            primary.write_text(
                "date,open,high,low,close,volume\n"
                "2025-01-01,10,11,9,10.5,100\n",
                encoding="utf-8",
            )
            benchmark.write_text(
                "date,open,high,low,close,volume,known_at\n"
                "2025-01-01,20,21,19,20.5,200,\n"
                "2024-12-31,19,20,18,19.5,190,\n"
                "2025-01-02,21,22,20,21.5,210,2025-01-03T00:00:00-05:00\n"
                "2025-01-03,22,23,21,22.5,220,\n",
                encoding="utf-8",
            )
            _, diagnostics = load_dataset(
                input_path=primary,
                symbol="TEST",
                market=Market.US,
                as_of=date(2025, 1, 2),
                source="unit-test",
                price_basis=PriceBasis.RAW,
                benchmark_path=benchmark,
                benchmark_symbol="BENCH",
            )
            self.assertEqual(diagnostics["benchmark_input_rows"], 4)
            self.assertEqual(diagnostics["benchmark_usable_rows"], 2)
            self.assertEqual(diagnostics["benchmark_excluded_after_as_of"], 1)
            self.assertEqual(
                diagnostics["benchmark_excluded_not_yet_known"],
                1,
            )
            self.assertTrue(diagnostics["benchmark_input_reordered"])


if __name__ == "__main__":
    unittest.main()
