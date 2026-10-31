import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from third_place_redundancy import CANDIDATES, choose_tickets, fixed_policies
from pair_protected_candidate import score_rows
from historical_records import parse_program
from test_historical_records import DAY, program


class ThirdPlaceRedundancyTests(unittest.TestCase):
    def setUp(self):
        self.rows = parse_program(program(), DAY)[1]["202610282301"]

    def test_predeclared_top_pairs_reserve_distinct_thirds(self):
        ranked = score_rows(self.rows)
        pairs = []
        for _, _, _, pair in ranked:
            if pair not in pairs:
                pairs.append(pair)
        for variant, (pair_count, required) in CANDIDATES.items():
            tickets = choose_tickets(self.rows, variant)
            self.assertEqual(len(tickets), 8)
            self.assertEqual(len(set(tickets)), 8)
            for pair in pairs[:pair_count]:
                matches = [tuple(map(int, t.split("-"))) for t in tickets
                           if tuple(map(int, t.split("-")[:2])) == pair]
                self.assertGreaterEqual(len(matches), required)
                self.assertEqual(len({item[2] for item in matches}), len(matches))
            for ticket in tickets:
                boats = ticket.split("-")
                self.assertEqual(len(boats), 3)
                self.assertEqual(len(set(boats)), 3)

    def test_only_B_allowed_no_outcome_or_national_dependency(self):
        old = fixed_policies(self.rows)
        revised = copy.deepcopy(self.rows)
        for i, entry in enumerate(revised):
            entry["national_win_rate"] = 1000 + i
            entry["national_2rate"] = 80 + i
            entry["actual_finish"] = i
            entry["K_result"] = "6-5-4"
            entry["payout"] = 999999
        self.assertEqual(old, fixed_policies(revised))

    def test_deterministic_under_B_row_reordering(self):
        self.assertEqual(fixed_policies(self.rows),
                         fixed_policies(list(reversed(self.rows))))
        self.assertEqual(fixed_policies(self.rows), fixed_policies(self.rows))

    def test_invalid_rule_or_motor_is_rejected(self):
        with self.assertRaises(ValueError):
            choose_tickets(self.rows, "pair4_third4")
        bad = copy.deepcopy(self.rows)
        bad[0]["motor_2rate"] = 150
        with self.assertRaises(ValueError):
            fixed_policies(bad)


if __name__ == "__main__":
    unittest.main()
