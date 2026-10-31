import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from replication_gate import summarize, BASELINE, CANDIDATE


ROOT = Path(__file__).resolve().parents[1] / "research"


def load():
    a = json.loads((ROOT / "pair_invariant_20260925_27.json").read_text(encoding="utf-8"))
    b = json.loads((ROOT / "pair_invariant_20260920_22_replication.json").read_text(encoding="utf-8"))
    return a, b


class ReplicationGateTests(unittest.TestCase):
    def test_real_disjoint_cohorts_fail_both_metric_gate(self):
        a, b = load()
        result = summarize(a, b)
        self.assertFalse(result["replicated_both_metrics"])
        self.assertFalse(result["production_eligible"])
        self.assertEqual(result["forward_verified_races"], 0)
        self.assertTrue(result["cohorts"][0]["improved_both"])
        self.assertFalse(result["cohorts"][1]["improved_both"])
        self.assertEqual(result["cohorts"][0]["hit_delta"], 4)
        self.assertEqual(result["cohorts"][1]["hit_delta"], -4)

    def test_positive_historical_replicates_still_never_production(self):
        a, b = load()
        b = copy.deepcopy(b)
        cohort = b["replication_results"]
        baseline = cohort[BASELINE]
        candidate = cohort[CANDIDATE]
        candidate["hits"] = baseline["hits"] + 1
        candidate["payout_yen"] = baseline["payout_yen"] + 100
        result = summarize(a, b)
        self.assertTrue(result["replicated_both_metrics"])
        self.assertFalse(result["production_eligible"])
        self.assertEqual(result["forward_verified_races"], 0)

    def test_overlap_refused(self):
        a, b = load()
        b["repeat_dates"] = a["dates"]
        with self.assertRaisesRegex(ValueError, "disjoint"):
            summarize(a, b)

    def test_mismatched_ticket_budgets_rejected(self):
        a, b = load()
        b["replication_results"][CANDIDATE]["stakes_yen"] -= 100
        with self.assertRaisesRegex(ValueError, "8 tickets"):
            summarize(a, b)

    def test_false_pair_cover_rejected(self):
        a, b = load()
        b["replication_results"][CANDIDATE]["head_second_pair_covered"] -= 1
        with self.assertRaisesRegex(ValueError, "pair coverage"):
            summarize(a, b)


if __name__ == "__main__":
    unittest.main()
