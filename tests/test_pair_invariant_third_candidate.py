import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pair_invariant_third_candidate import fixed_policies, pair_from_ticket, reallocate_thirds
from historical_records import parse_program
from test_historical_records import DAY, program


class PairInvariantTests(unittest.TestCase):
    def setUp(self):
        self.rows = parse_program(program(), DAY)[1]["202610282301"]

    def test_pair_coverage_always_identical_eight_unique_tickets(self):
        for variants in (self.rows, list(reversed(self.rows))):
            selections = fixed_policies(variants)
            base = selections["baseline_local_motor"]
            base_pairs = {pair_from_ticket(ticket) for ticket in base}
            for policy, picks in selections.items():
                self.assertEqual(len(picks), 8, policy)
                self.assertEqual(len(set(picks)), 8, policy)
                self.assertEqual({pair_from_ticket(t) for t in picks}, base_pairs)
                self.assertEqual({t[0] for t in picks}, {t[0] for t in base})

    def test_intentionally_infeasible_quota_keeps_unmodified_baseline(self):
        # Across a broad, predeclared range of synthetic B-only inputs verify
        # no branch destroys a baseline pair, even when 8 slots are insufficient.
        for shift in range(9):
            rows = copy.deepcopy(self.rows)
            for r in rows:
                r["local_win_rate"] = 1.0 + ((r["boat"] + shift) % 9)
                r["motor_2rate"] = float((r["boat"] * 13 + shift * 7) % 91)
            picks = fixed_policies(rows)
            baseline = picks["baseline_local_motor"]
            basepairs = {pair_from_ticket(t) for t in baseline}
            for label in ("keep_pairs_top1_third3", "keep_pairs_top2_third2"):
                candidate = picks[label]
                self.assertEqual({pair_from_ticket(t) for t in candidate}, basepairs)
                if len(basepairs) > 6:
                    self.assertEqual(candidate, baseline)

    def test_outcome_and_national_fields_cannot_change_B_ticket_set(self):
        expected = fixed_policies(self.rows)
        modified = copy.deepcopy(self.rows)
        for i, entry in enumerate(modified):
            entry["national_win_rate"] = 1000 + i
            entry["national_2rate"] = 200 + i
            entry["actual_finish"] = 6 - i
            entry["trifecta"] = "6-5-4"
            entry["payout_yen_per_100"] = 999999
        self.assertEqual(expected, fixed_policies(modified))

    def test_invalid_policy_and_corrupt_motor_rejected(self):
        with self.assertRaises(ValueError):
            reallocate_thirds(self.rows, "tuned_after_K")
        with self.assertRaises(ValueError):
            pair_from_ticket("1-1-2")
        broken = copy.deepcopy(self.rows)
        broken[0]["motor_2rate"] = 110.0
        with self.assertRaises(ValueError):
            fixed_policies(broken)


if __name__ == "__main__":
    unittest.main()
