import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from multi_day_audit import inspect_pair, inspect_days
from test_historical_records import DAY, program, results


def b_fixture():
    return program().replace('ボートレース唐　津', '2026年10月28日\nボートレース唐　津')


def k_fixture():
    return results().replace('唐　津［成績］', '2026/10/28\n唐　津［成績］')


class MultiDayAuditTests(unittest.TestCase):
    def test_strict_historical_only_coverage(self):
        d = inspect_pair(b_fixture(), k_fixture(), DAY)
        self.assertEqual(d["B_races"], 1)
        self.assertEqual(d["K_races"], 1)
        self.assertEqual(d["paired_races"], 1)
        self.assertEqual(d["historical_six_finisher_join"], 1)
        self.assertEqual(d["B_only_races"], 0)
        self.assertIsNone(d["retrospective_model_accuracy"])
        self.assertEqual(d["forward_verified_races"], 0)

    def test_quarantined_bad_program_is_reported(self):
        bad = b_fixture().replace("45 33.33 18 31.72", "45 133.33 18 31.72")
        d = inspect_pair(bad, k_fixture(), DAY)
        self.assertEqual(d["historical_six_finisher_join"], 0)
        self.assertEqual(d["issues_by_reason"].get("out_of_range_B"), 1)

    def test_rejects_wrong_archive_day(self):
        with self.assertRaises(ValueError):
            inspect_pair(b_fixture(), k_fixture(), date(2026, 10, 29))

    def test_bound_days_and_never_claim_forward(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                inspect_days(Path(directory), [DAY] * 2)
            with self.assertRaises(ValueError):
                inspect_days(Path(directory), [date(2030, 1, 1)])
            with self.assertRaises(ValueError):
                inspect_days(Path(directory), [
                    date(2026, 10, 24), date(2026, 10, 25),
                    date(2026, 10, 26), date(2026, 10, 27)
                ])

    def test_pair_mismatched_distance_not_admitted(self):
        d = inspect_pair(b_fixture(), k_fixture().replace("H1800m", "H1200m"), DAY)
        self.assertEqual(d["historical_six_finisher_join"], 0)
        self.assertEqual(d["issues_by_reason"]["B_K_distance_mismatch"], 1)


if __name__ == "__main__":
    unittest.main()
