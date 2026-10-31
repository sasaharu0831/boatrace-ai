import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from head_diversification_candidate import candidate_tickets, policies
from shadow_baseline import rank_tickets
from test_historical_records import DAY, program
from historical_records import parse_program


class HeadDiversificationTests(unittest.TestCase):
    def setUp(self):
        self.rows = parse_program(program(), DAY)[1]["202610282301"]

    def test_head_two_and_three_guaranteed_eight_distinct_tickets(self):
        for required in (2, 3):
            result = candidate_tickets(self.rows, minimum_heads=required)
            self.assertEqual(len(result), 8)
            self.assertEqual(len(set(result)), 8)
            self.assertGreaterEqual(len({t.split("-")[0] for t in result}), required)
            for ticket in result:
                parts = ticket.split("-")
                self.assertEqual(len(parts), 3)
                self.assertEqual(len(set(parts)), 3)
                self.assertTrue(all(x in "123456" for x in parts))

    def test_default_head_one_reduces_to_fixed_base_rank(self):
        self.assertEqual(candidate_tickets(self.rows, minimum_heads=1),
                         rank_tickets(self.rows, "local_motor"))

    def test_no_national_rate_or_result_in_prediction(self):
        a = policies(self.rows)
        changed = copy.deepcopy(self.rows)
        for i, row in enumerate(changed):
            row["national_win_rate"] = 1000 * i
            row["national_2rate"] = 300 + i
            row["name"] = "changed after B"
        self.assertEqual(a, policies(changed))

    def test_order_independent_and_reproducible(self):
        self.assertEqual(policies(self.rows), policies(list(reversed(self.rows))))
        self.assertEqual(policies(self.rows), policies(self.rows))

    def test_invalid_count_or_metric_fails_closed(self):
        with self.assertRaises(ValueError):
            candidate_tickets(self.rows, minimum_heads=7)
        with self.assertRaises(ValueError):
            candidate_tickets(self.rows, minimum_heads=0)
        with self.assertRaises(ValueError):
            candidate_tickets(self.rows, base_policy="unknown")
        b = copy.deepcopy(self.rows)
        b[0]["motor_2rate"] = 102
        with self.assertRaises(ValueError):
            policies(b)


if __name__ == "__main__":
    unittest.main()
