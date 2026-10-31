import copy
from datetime import date
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from shadow_baseline import POLICIES, TICKETS, evaluate_posthoc, freeze_b_only, rank_tickets
from historical_records import parse_program
from test_historical_records import DAY, program, results


class BOnlyShadowTests(unittest.TestCase):
    def test_all_policies_generate_eight_valid_unique_tickets(self):
        row_map = parse_program(program(), DAY)[1]
        row = row_map["202610282301"]
        for p in POLICIES:
            selections = rank_tickets(row, p)
            self.assertEqual(len(selections), TICKETS)
            self.assertEqual(len(set(selections)), 8)
            for pick in selections:
                triple = pick.split("-")
                self.assertEqual(len(triple), 3)
                self.assertEqual(len(set(triple)), 3)
                self.assertTrue(set(triple) <= set("123456"))

    def test_local_policy_uses_local_not_national_rate(self):
        original = parse_program(program(), DAY)[1]["202610282301"]
        changed = copy.deepcopy(original)
        for i, row in enumerate(changed):
            row["national_win_rate"] = i * 100
            row["national_2rate"] = i * 20
        self.assertEqual(rank_tickets(original, "local_only"),
                         rank_tickets(changed, "local_only"))
        self.assertEqual(rank_tickets(original, "local_motor"),
                         rank_tickets(changed, "local_motor"))

    def test_freeze_is_identical_independent_of_result_information(self):
        original, stages, digest = freeze_b_only(program(), DAY)
        again, stage2, digest2 = freeze_b_only(program(), DAY)
        self.assertEqual(original, again)
        self.assertEqual(stages, stage2)
        self.assertEqual(digest, digest2)
        self.assertEqual(len(digest), 64)
        self.assertEqual(len(original), 1)
        self.assertEqual(len(original["202610282301"]), 3)
        self.assertFalse({"trifecta", "payout_yen_per_100"} & original["202610282301"].keys())

    def test_outcome_mutation_changes_score_not_frozen_tickets(self):
        picks, stages, before = freeze_b_only(program(), DAY)
        actual = evaluate_posthoc(picks, stages, results(), program(), DAY)
        altered = results().replace("1R  1-3-4     730", "1R  2-3-4     730")
        after = evaluate_posthoc(picks, stages, altered, program(), DAY)
        # Invalid K payout/finish mismatch is quarantined, not used as a new
        # target for picking or retroactively changing the B snapshot.
        self.assertEqual(sum(x["evaluated"] for x in after.values()), 0)
        self.assertEqual(before, freeze_b_only(program(), DAY)[2])
        self.assertEqual(actual["lane_only"]["evaluated"], 1)

    def test_bad_b_entry_is_quarantined(self):
        bad = program().replace("45 33.33 18 31.72", "45 133.33 18 31.72")
        predictions, _, _ = freeze_b_only(bad, DAY)
        self.assertEqual(predictions, {})

    def test_predicted_tickets_are_stable_when_B_entry_order_changes(self):
        rows = parse_program(program(), DAY)[1]["202610282301"]
        for p in POLICIES:
            self.assertEqual(rank_tickets(rows, p), rank_tickets(list(reversed(rows)), p))

    def test_non_calibrated_probabilities_are_not_claimed(self):
        rows = parse_program(program(), DAY)[1]["202610282301"]
        with self.assertRaises(ValueError):
            rank_tickets(rows, "an_untrained_new_policy")
        with self.assertRaises(ValueError):
            rank_tickets(rows, "lane_only", ticket_count=9)


if __name__ == "__main__":
    unittest.main()
