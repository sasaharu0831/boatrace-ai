import copy
from datetime import date
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from holdout_analysis import evaluate_day, analyze_holdout, classify_ticket_miss, MISS_REASONS
from test_historical_records import DAY, program, results


def b_report():
    return program().replace("ボートレース唐　津", "２０２６年１０月２８日\nボートレース唐　津")


def k_report():
    return results().replace("唐　津［成績］", "2026/10/28\n唐　津［成績］")


class HoldoutTests(unittest.TestCase):
    def test_miss_classes_are_mutually_exclusive(self):
        base = ["1-2-3", "1-3-2", "1-4-2", "2-1-3",
                "2-3-1", "3-1-2", "3-2-1", "4-1-2"]
        self.assertEqual(classify_ticket_miss(base, "1-2-3"), "EXACT_HIT")
        self.assertEqual(classify_ticket_miss(base, "6-1-2"), "HEAD_ABSENT")
        # With 1-4-2 present, outcome 1-2-4 is specifically a swap.
        self.assertEqual(classify_ticket_miss(base, "1-2-4"), "SECOND_THIRD_SWAPPED")
        self.assertEqual(classify_ticket_miss(base, "1-4-3"), "HEAD_PRESENT_SECOND_ABSENT")
        self.assertEqual(classify_ticket_miss(base, "1-2-5"), "HEAD_SECOND_PRESENT_THIRD_ABSENT")
        swapped = ["1-3-2", "1-5-2", "2-1-3", "2-3-1",
                   "3-1-2", "3-2-1", "4-1-2", "5-1-2"]
        self.assertEqual(classify_ticket_miss(swapped, "1-2-3"), "SECOND_THIRD_SWAPPED")
        with self.assertRaises(ValueError):
            classify_ticket_miss(base, "1-1-2")

    def test_miss_diagnostics_sum_to_population(self):
        report = evaluate_day(b_report(), k_report(), DAY)
        for policy in report["groups"]:
            n = report["groups"][policy]["overall"]["races"]
            reasons = report["miss_diagnostics"][policy]["overall"]
            self.assertEqual(set(reasons), set(MISS_REASONS))
            self.assertEqual(sum(reasons.values()), n)
            self.assertEqual(reasons["EXACT_HIT"],
                             report["groups"][policy]["overall"]["hits"])

    def test_single_race_has_distinct_strata(self):
        report = evaluate_day(b_report(), k_report(), DAY)
        self.assertEqual(report["B_races_frozen_before_K"], 1)
        self.assertEqual(report["historical_joined"], 1)
        self.assertEqual(report["forward_verified_races"], 0)
        for policy in ("lane_only", "local_only", "local_motor"):
            groups = report["groups"][policy]
            self.assertEqual(groups["overall"]["races"], 1)
            self.assertEqual(groups["overall"]["stakes_yen"], 800)
            self.assertIn("venue:23", groups)
            self.assertIn("stage:UNSPECIFIED", groups)
            self.assertIn("marker:NO_K_MARKER_UNVERIFIED", groups)
            self.assertEqual(groups["overall"]["payout_yen"],
                             730 if groups["overall"]["hits"] else 0)

    def test_k_positive_marker_separate_denominator(self):
        fake_k = k_report().replace(
            "  01  1 5104", "安定板使用\n  01  1 5104")
        report = evaluate_day(b_report(), fake_k, DAY)
        self.assertEqual(report["K_positive_marker_races_in_joined"], 1)
        for policy in report["groups"]:
            groups = report["groups"][policy]
            self.assertEqual(groups["marker:K_MARKER_PRESENT"]["races"], 1)
            self.assertNotIn("marker:NO_K_MARKER_UNVERIFIED", groups)

    def test_bad_payout_discarded_not_retuned(self):
        fake_k = k_report().replace("1R  1-3-4     730", "1R  2-3-4     730")
        report = evaluate_day(b_report(), fake_k, DAY)
        self.assertEqual(report["historical_joined"], 0)
        self.assertEqual(report["B_races_frozen_before_K"], 1)

    def test_report_date_mismatch_is_fatal(self):
        with self.assertRaises(ValueError):
            evaluate_day(b_report(), k_report(), date(2026, 10, 27))

    def test_b_only_weights_unchanged_by_outcome_text(self):
        first = evaluate_day(b_report(), k_report(), DAY)
        second = evaluate_day(b_report(), k_report().replace("730", "730"), DAY)
        self.assertEqual(first["B_ticket_sha256"], second["B_ticket_sha256"])

    def test_cannot_claim_genuine_forward_with_invalid_dates(self):
        with self.assertRaises(ValueError):
            analyze_holdout(Path("."), [DAY, DAY])
        with self.assertRaises(ValueError):
            analyze_holdout(Path("."), [DAY, DAY, DAY, DAY])


if __name__ == "__main__":
    unittest.main()
