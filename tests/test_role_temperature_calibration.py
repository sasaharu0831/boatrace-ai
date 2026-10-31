import copy
from datetime import date
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from historical_records import parse_program
from role_temperature_calibration import (
    ROLES, TEMPERATURES, _logs, distribution, fit_temperatures,
    freeze_digest, role_log_losses, score_distribution, top_eight
)
from role_temperature_trial import freeze_test_b, run, score_test, training_observations
from test_holdout_analysis import DAY, b_report, k_report
from shadow_baseline import rank_tickets


class RoleTemperatureCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.rows = parse_program(b_report(), DAY)[1]["202610282301"]
        self.outcome = "1-3-4"
        self.original = {role: 1.0 for role in ROLES}

    def test_baseline_role1_recovers_fixed_top_eight_and_normalizes(self):
        probs = distribution(self.rows, self.original)
        self.assertEqual(len(probs), 120)
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=12)
        self.assertEqual(top_eight(probs), rank_tickets(self.rows, "local_motor"))
        self.assertEqual(len(set(top_eight(probs))), 8)

    def test_train_only_grid_picks_predeclared_temperatures(self):
        observations = [(copy.deepcopy(self.rows), self.outcome) for _ in range(65)]
        fitted = fit_temperatures(observations)
        self.assertEqual(set(fitted["role_temperatures"]), set(ROLES))
        self.assertTrue(all(t in TEMPERATURES for t in fitted["role_temperatures"].values()))
        self.assertEqual(fitted["training_eligible_races"], 65)
        again = fit_temperatures(list(reversed(observations)))
        self.assertEqual(freeze_digest(fitted), freeze_digest(again))
        with self.assertRaisesRegex(ValueError, ">=60"):
            fit_temperatures(observations[:59])

    def test_weights_ignore_national_K_odds_payout_fields(self):
        old = distribution(self.rows, self.original)
        edited = copy.deepcopy(self.rows)
        for i, row in enumerate(edited):
            row.update({"national_win_rate": 500+i, "national_2rate": 100+i,
                        "K_actual": "6-5-4", "payout_yen": 999999, "odds": 10234})
        self.assertEqual(distribution(edited, self.original), old)
        self.assertEqual(distribution(list(reversed(edited)), self.original), old)

    def test_score_120way_is_proper_scoring_rule(self):
        p = distribution(self.rows, self.original)
        outcome = self.outcome
        result = score_distribution(p, outcome)
        self.assertAlmostEqual(result["negative_log_likelihood"], -math.log(p[outcome]))
        self.assertAlmostEqual(result["brier_120"],
                               sum(v*v for v in p.values()) + 1 - 2*p[outcome])
        with self.assertRaises(ValueError):
            score_distribution(p, "1-1-2")

    def test_role_losses_have_five_grid_values(self):
        d = role_log_losses(_logs(self.rows), self.outcome)
        self.assertEqual(set(d), set(ROLES))
        for role in ROLES:
            self.assertEqual(set(d[role]), set(TEMPERATURES))
            self.assertTrue(all(math.isfinite(x) and x > 0 for x in d[role].values()))

    def test_training_observations_read_K_only_from_training_pair(self):
        rows, markers = training_observations(b_report(), k_report(), DAY)
        self.assertEqual(len(rows), 1)
        self.assertEqual(markers, 0)
        self.assertEqual(rows[0][1], self.outcome)
        with self.assertRaises(ValueError):
            training_observations(b_report(), k_report(), date(2026, 10, 27))

    def test_K_outcome_changed_only_changes_scoring_not_B_frozen_hash(self):
        model = dict(self.original)
        b = b_report()
        frozen, digest = freeze_test_b(b, DAY, model)
        initial = score_test(frozen, b, k_report(), DAY)
        self.assertEqual(initial["baseline_local_motor"]["races"], 1)
        self.assertEqual(initial["baseline_local_motor"]["stakes_yen"], 800)
        mismatch = k_report().replace("1R  1-3-4     730",
                                       "1R  2-3-4     730")
        zero = score_test(frozen, b, mismatch, DAY)
        self.assertEqual(zero["baseline_local_motor"]["races"], 0)
        self.assertEqual(digest, freeze_test_b(b, DAY, model)[1])

    def test_training_test_dates_must_be_chronologically_separate(self):
        root = Path(".")
        with self.assertRaisesRegex(ValueError, "older training dates"):
            run(root, [DAY, DAY, DAY], [date(2026, 11, 1)]*3)
        with self.assertRaisesRegex(ValueError, "older training dates"):
            run(root, [date(2026, 10, 29), date(2026, 10, 30), DAY],
                [date(2026, 10, 24), date(2026, 10, 25), date(2026, 10, 26)])


if __name__ == "__main__":
    unittest.main()
