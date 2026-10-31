import csv
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from historical_export import FEATURE_COLUMNS, OUTCOME_COLUMNS, export_partition
from historical_records import parse_program, parse_results
from historical_sqlite import persist_day
from test_historical_records import DAY, program, results


class ExportTests(unittest.TestCase):
    def _db(self, folder):
        db = Path(folder) / "h.sqlite"
        persist_day(db, DAY, parse_program(program(), DAY), parse_results(results(), DAY),
                    "a" * 64, "b" * 64)
        return db

    def test_feature_and_outcome_not_leaked(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            db = self._db(folder)
            features = root / "private" / "historical_features.csv"
            outcomes = root / "restricted" / "historical_outcomes.csv"
            summary = export_partition(db, features, outcomes)
            self.assertEqual(summary["retrospective_races"], 1)
            self.assertEqual(summary["forward_verified_races"], 0)
            self.assertEqual(summary["feature_boat_rows"], 6)
            self.assertEqual(summary["outcome_boat_rows"], 6)
            with features.open(encoding="utf-8", newline="") as f:
                columns = next(csv.reader(f))
            with outcomes.open(encoding="utf-8", newline="") as f:
                out = list(csv.DictReader(f))
            self.assertEqual(tuple(columns), FEATURE_COLUMNS)
            self.assertEqual(tuple(out[0].keys()), OUTCOME_COLUMNS)
            self.assertTrue({"trifecta", "finish", "payout_yen_per_100"}.isdisjoint(columns))
            self.assertEqual(out[0]["trifecta"], "1-3-4")

    def test_anti_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            db = self._db(folder)
            f, o = root / "f.csv", root / "o.csv"
            export_partition(db, f, o)
            with self.assertRaises(FileExistsError):
                export_partition(db, f, o)

    def test_refuse_same_output(self):
        with tempfile.TemporaryDirectory() as folder:
            db = self._db(folder)
            out = Path(folder) / "same.csv"
            with self.assertRaises(ValueError):
                export_partition(db, out, out)

    def test_refuse_mismatch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            db = self._db(folder)
            with sqlite3.connect(db) as con:
                con.execute("DELETE FROM historical_result_entries WHERE boat=6")
            f, o = root / "f.csv", root / "o.csv"
            with self.assertRaises(ValueError):
                export_partition(db, f, o)
            self.assertFalse(f.exists())
            self.assertFalse(o.exists())


if __name__ == "__main__":
    unittest.main()
