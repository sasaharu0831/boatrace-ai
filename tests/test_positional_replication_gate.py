import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from positional_replication_gate import evaluate

SOURCE = (Path(__file__).resolve().parents[1] / "research" /
          "positional_role_sep01_08_replication.json")


class PositionalGateTests(unittest.TestCase):
    def load(self):
        return json.loads(SOURCE.read_text(encoding="utf-8"))

    def test_saved_real_two_cohort_report_rejects_both_candidates(self):
        result = evaluate(self.load())
        self.assertFalse(result["production_eligible"])
        self.assertEqual(result["forward_verified_races"], 0)
        self.assertEqual(result["both_metric_replication"],
                         {"role_second_local": False, "role_third_motor": False})
        self.assertTrue(result["cohorts"]["role_second_local"][0]["passes_both"])
        self.assertFalse(result["cohorts"]["role_second_local"][1]["passes_both"])

    def test_even_hypothetical_two_positive_splits_cannot_promote(self):
        doc = self.load()
        for cohort in doc["cohorts"]:
            b = cohort["models"]["baseline_local_motor"]
            c = cohort["models"]["role_second_local"]
            c["hits"] = b["hits"] + 1
            c["misses"] = dict(b["misses"])
            c["misses"]["EXACT_HIT"] = c["hits"]
            c["misses"]["HEAD_ABSENT"] -= 1
            c["payout_yen"] = b["payout_yen"] + 100
            # By-stage counts are unchanged: candidate 3-leg misses are not
            # inferred from the stage-only summary in this counterfactual.
        result = evaluate(doc)
        self.assertTrue(result["both_metric_replication"]["role_second_local"])
        self.assertFalse(result["production_eligible"])

    def test_reject_overlap_or_edited_digest(self):
        doc = self.load()
        doc["cohorts"][1]["days"][0]["day"] = doc["cohorts"][0]["days"][0]["day"]
        with self.assertRaisesRegex(ValueError, "overlap"):
            evaluate(doc)
        doc = self.load()
        doc["cohorts"][0]["days"][0]["frozen_tickets_sha256"] = "fake"
        with self.assertRaisesRegex(ValueError, "SHA256"):
            evaluate(doc)

    def test_reject_false_stakes_hit_mismatch_and_forward_claim(self):
        doc = self.load()
        doc["cohorts"][1]["models"]["role_second_local"]["stakes_yen"] -= 100
        with self.assertRaisesRegex(ValueError, "denominator"):
            evaluate(doc)
        doc = self.load()
        doc["cohorts"][1]["models"]["role_second_local"]["misses"]["EXACT_HIT"] += 1
        with self.assertRaisesRegex(ValueError, "miss partitions"):
            evaluate(doc)
        doc = self.load()
        doc["forward_verified_races"] = 1
        with self.assertRaisesRegex(ValueError, "Forward"):
            evaluate(doc)


if __name__=="__main__":
    unittest.main()
