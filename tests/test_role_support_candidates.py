import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from historical_records import parse_program
from test_historical_records import DAY, program
from role_support_candidates import MODELS, _pair, fixed_policies


class RoleSupportTests(unittest.TestCase):
    def setUp(self):
        self.rows = parse_program(program(), DAY)[1]["202610282301"]

    def check_support(self, rows):
        results = fixed_policies(rows)
        self.assertEqual(set(results), set(MODELS))
        base = results["baseline_local_motor"]
        heads = {t[0] for t in base}
        pairs = {_pair(t) for t in base}
        for name, tickets in results.items():
            self.assertEqual(len(tickets), 8, name)
            self.assertEqual(len(set(tickets)), 8, name)
            self.assertEqual({t[0] for t in tickets}, heads, name)
        self.assertEqual({_pair(t) for t in results["pair_support_role_second"]}, pairs)
        return results

    def test_preserves_heads_and_pairs_while_reordering_roles(self):
        self.check_support(self.rows)

    def test_deterministic_for_row_order_and_moderate_synthetic_variants(self):
        self.assertEqual(self.check_support(self.rows),
                         self.check_support(list(reversed(self.rows))))
        for shift in range(12):
            rows = copy.deepcopy(self.rows)
            for row in rows:
                row["local_win_rate"] = 1.0 + (row["boat"] + shift) % 9
                row["motor_2rate"] = (row["boat"]*17 + shift*3) % 99
            self.check_support(rows)

    def test_outcomes_and_national_rates_never_enter_selection(self):
        baseline = self.check_support(self.rows)
        rows = copy.deepcopy(self.rows)
        for i, row in enumerate(rows):
            row.update({"national_win_rate": 999.0 + i,
                        "national_2rate": 100 + i, "K_finish": i,
                        "payout_yen_per_100": 999999, "odds": 999,
                        "popularity": i})
        self.assertEqual(self.check_support(rows), baseline)

    def test_corrupted_B_values_are_rejected(self):
        rows = copy.deepcopy(self.rows)
        rows[0]["local_win_rate"] = 100
        with self.assertRaises(ValueError):
            fixed_policies(rows)
        rows = copy.deepcopy(self.rows)
        rows[0]["motor_2rate"] = float("nan")
        with self.assertRaises(ValueError):
            fixed_policies(rows)


if __name__=="__main__":
    unittest.main()
