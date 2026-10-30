import sqlite3
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from historical_records import parse_program, parse_results
from historical_sqlite import persist_day, validate_report_date
from test_historical_records import program, results, DAY

SHA_B = "a" * 64
SHA_K = "b" * 64


class HistoricalSqliteTests(unittest.TestCase):
    def test_atomically_store_and_repeat_no_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "history.sqlite"
            b = parse_program(program(), DAY)
            k = parse_results(results(), DAY)
            for _ in range(2):
                audit = persist_day(db, DAY, b, k, SHA_B, SHA_K)
                self.assertEqual(audit["stored_program_rows"], 6)
                self.assertEqual(audit["stored_result_rows"], 6)
            with sqlite3.connect(db) as con:
                self.assertEqual(con.execute("select count(*) from historical_races").fetchone()[0], 1)
                self.assertEqual(con.execute("select count(*) from historical_program_entries").fetchone()[0], 6)
                self.assertEqual(con.execute("select count(*) from historical_result_entries").fetchone()[0], 6)
                self.assertEqual(con.execute("select count(*) from historical_import_audit").fetchone()[0], 1)
                self.assertEqual(con.execute("select distinct data_status from historical_races").fetchone()[0],
                                 "HISTORICAL_ONLY")
                self.assertEqual(con.execute("select distinct data_status from historical_result_entries").fetchone()[0],
                                 "K_OUTCOME_ONLY")

    def test_mismatched_racers_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "h.db"
            b = parse_program(program().replace("1 5104", "1 9999"), DAY)
            with self.assertRaises(ValueError):
                persist_day(db, DAY, b, parse_results(results(), DAY), SHA_B, SHA_K)
            if db.exists():
                with sqlite3.connect(db) as con:
                    self.assertEqual(con.execute("select count(*) from historical_races").fetchone()[0], 0)

    def test_header_date_protection(self):
        validate_report_date("2026年10月28日", DAY, "B")
        validate_report_date("2026/10/28", DAY, "K")
        with self.assertRaises(ValueError):
            validate_report_date("2026/10/27", DAY, "K")

    def test_bad_hash_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                persist_day(Path(tmp)/"h.db", DAY, parse_program(program(), DAY),
                            parse_results(results(), DAY), "bad", SHA_K)


if __name__ == "__main__":
    unittest.main()
