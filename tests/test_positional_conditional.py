import copy
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from historical_records import parse_program
from positional_conditional import (
    POLICIES, frozen_policies, ranked_tickets, role_probabilities
)
from shadow_baseline import rank_tickets
from test_historical_records import DAY, program


class PositionalConditionalTests(unittest.TestCase):
    def setUp(self):
        self.rows = parse_program(program(), DAY)[1]["202610282301"]

    def test_120_orders_normalize_separately_by_role(self):
        for policy in POLICIES[1:]:
            probs = role_probabilities(self.rows, policy)
            self.assertEqual(len(probs), 120)
            self.assertTrue(math.isclose(sum(probs.values()), 1.0, abs_tol=1e-12))
            for triple, value in probs.items():
                self.assertTrue(value > 0)
                self.assertEqual(len(set(triple.split("-"))), 3)

    def test_exact_eight_unique_tickets_and_unchanged_baseline(self):
        samples = frozen_policies(self.rows)
        self.assertEqual(set(samples), set(POLICIES))
        self.assertEqual(samples["baseline_local_motor"],
                         rank_tickets(self.rows, "local_motor"))
        for picks in samples.values():
            self.assertEqual(len(picks), 8)
            self.assertEqual(len(set(picks)), 8)

    def test_no_national_results_odds_or_payout_in_weights(self):
        original = frozen_policies(self.rows)
        changed = copy.deepcopy(self.rows)
        for i, row in enumerate(changed):
            row.update({"national_win_rate": 1000+i, "national_2rate": 99+i,
                        "winner": (i+1), "K_result": "6-5-4",
                        "odds": 100, "payout_yen_per_100": 20000})
        self.assertEqual(frozen_policies(changed), original)

    def test_reordering_is_deterministic(self):
        self.assertEqual(frozen_policies(self.rows),
                         frozen_policies(list(reversed(self.rows))))
        self.assertEqual(frozen_policies(self.rows), frozen_policies(self.rows))

    def test_invalid_role_and_missing_B_metric_fail_closed(self):
        with self.assertRaises(ValueError):
            role_probabilities(self.rows, "later_tuned_variant")
        broken = copy.deepcopy(self.rows)
        broken[0]["motor_2rate"] = float("nan")
        with self.assertRaises(ValueError):
            frozen_policies(broken)
        broken = copy.deepcopy(self.rows)
        broken[0]["local_win_rate"] = 100
        with self.assertRaises(ValueError):
            ranked_tickets(broken, "role_second_local")


if __name__ == "__main__":
    unittest.main()
