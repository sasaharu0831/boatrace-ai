import sys
import unittest
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from third_place_trial import MODELS, freeze_b, score_day, run
from test_holdout_analysis import b_report, k_report, DAY


class ThirdPlaceTrialTests(unittest.TestCase):
    def test_B_frozen_before_K(self):
        frozen, digest = freeze_b(b_report(), DAY)
        self.assertEqual(len(digest), 64)
        self.assertEqual(len(frozen), 1)
        picks = frozen["202610282301"]
        self.assertEqual(set(picks), set(MODELS))
        for v in picks.values():
            self.assertEqual(len(v), 8)
            self.assertEqual(len(set(v)), 8)
        stats = score_day(frozen, b_report(), k_report(), DAY)
        for policy in MODELS:
            x = stats[policy]
            self.assertEqual(x["races"], 1)
            self.assertEqual(x["stakes_yen"], 800)
            self.assertEqual(sum(x["misses"].values()), 1)
            self.assertEqual(x["misses"]["EXACT_HIT"], x["hits"])
            self.assertGreaterEqual(x["head_covered"], x["head_second_pair_covered"])

    def test_outcome_mismatch_quarantined_and_B_digest_unchanged(self):
        frozen, digest = freeze_b(b_report(), DAY)
        bad_k = k_report().replace("1R  1-3-4     730", "1R  2-3-4     730")
        data = score_day(frozen, b_report(), bad_k, DAY)
        self.assertTrue(all(result["races"] == 0 for result in data.values()))
        self.assertEqual(freeze_b(b_report(), DAY), (frozen, digest))

    def test_duplicate_or_missing_day_rejected(self):
        with self.assertRaises(ValueError):
            run(Path("."), [DAY])
        with self.assertRaises(ValueError):
            run(Path("."), [DAY, DAY, DAY])
        with self.assertRaises(ValueError):
            run(Path("."), [DAY, DAY, date(2026, 10, 27)])

if __name__ == "__main__":
    unittest.main()
