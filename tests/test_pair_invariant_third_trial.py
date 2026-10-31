import copy
from datetime import date
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pair_invariant_third_trial import MODELS, freeze_program, run, score
from pair_invariant_third_candidate import pair_from_ticket
from test_holdout_analysis import DAY, b_report, k_report


class PairInvariantTrialTests(unittest.TestCase):
    def test_B_frozen_before_K_and_same_support(self):
        frozen, digest = freeze_program(b_report(), DAY)
        self.assertEqual(len(digest), 64)
        self.assertEqual(len(frozen), 1)
        rows = frozen["202610282301"]
        self.assertEqual(set(rows), set(MODELS))
        baseline = {pair_from_ticket(t) for t in rows["baseline_local_motor"]}
        for name, tickets in rows.items():
            self.assertEqual(len(tickets), 8)
            self.assertEqual(len(set(tickets)), 8)
            self.assertEqual({pair_from_ticket(t) for t in tickets}, baseline)
        result = score(frozen, b_report(), k_report(), DAY)
        for name in MODELS:
            row = result[name]
            self.assertEqual(row["races"], 1)
            self.assertEqual(row["stakes_yen"], 800)
            self.assertEqual(sum(row["miss_reasons"].values()), 1)
            self.assertEqual(row["hits"], row["miss_reasons"]["EXACT_HIT"])
            self.assertEqual(row["head_second_pair_covered"],
                             result["baseline_local_motor"]["head_second_pair_covered"])

    def test_K_tampering_cannot_rewrite_B_freeze(self):
        frozen, digest = freeze_program(b_report(), DAY)
        invalid = k_report().replace("1R  1-3-4     730",
                                     "1R  2-3-4     730")
        x = score(frozen, b_report(), invalid, DAY)
        self.assertTrue(all(row["races"] == 0 for row in x.values()))
        self.assertEqual(freeze_program(b_report(), DAY), (frozen, digest))

    def test_reject_duplicates_and_bad_days(self):
        with self.assertRaises(ValueError):
            run(Path("."), [DAY, DAY, DAY])
        with self.assertRaises(ValueError):
            run(Path("."), [DAY])
        with self.assertRaises(ValueError):
            run(Path("."), [DAY, DAY, date(2026, 9, 1)])


if __name__ == "__main__":
    unittest.main()
