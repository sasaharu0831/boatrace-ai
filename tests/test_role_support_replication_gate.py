import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from role_support_replication_gate import evaluate

REPORT=Path(__file__).resolve().parents[1]/"research"/"role_support_aug20_27_replication.json"


class RoleSupportGateTests(unittest.TestCase):
    def load(self):
        return json.loads(REPORT.read_text(encoding="utf-8"))

    def test_actual_two_cohort_outcomes_reject_promotion(self):
        result=evaluate(self.load())
        self.assertEqual(result["forward_verified_races"],0)
        self.assertFalse(result["production_eligible"])
        self.assertTrue(result["decisions"]["head_support_role_second"]["cohorts"][0]["passed"])
        self.assertFalse(result["decisions"]["head_support_role_second"]["cohorts"][1]["passed"])
        self.assertFalse(result["decisions"]["head_support_role_second"]["replicated"])
        self.assertFalse(result["decisions"]["pair_support_role_second"]["replicated"])

    def test_even_two_hypothetical_good_cohorts_not_production(self):
        report=self.load()
        for cohort in report["cohorts"]:
            b=cohort["models"]["baseline_local_motor"]
            c=cohort["models"]["head_support_role_second"]
            c["hits"]=b["hits"]+1
            c["payout_yen"]=b["payout_yen"]+100
            c["misses"]=dict(b["misses"])
            c["misses"]["EXACT_HIT"]+=1
            c["misses"]["HEAD_ABSENT"]-=1
        result=evaluate(report)
        self.assertTrue(result["decisions"]["head_support_role_second"]["replicated"])
        self.assertFalse(result["production_eligible"])

    def test_tampered_hash_and_overlapping_dates_rejected(self):
        report=self.load()
        report["cohorts"][0]["sha_receipts"][0]["tickets_sha256"]="NOT A SHA"
        with self.assertRaisesRegex(ValueError,"SHA256"):
            evaluate(report)
        report=self.load()
        earlier=report["cohorts"][0]["sha_receipts"][0]["day"]
        report["cohorts"][1]["sha_receipts"][0]["day"]=earlier
        report["cohorts"][1]["dates"][0]=earlier
        with self.assertRaisesRegex(ValueError,"overlapping"):
            evaluate(report)

    def test_stake_pair_and_hit_tampering_rejected(self):
        report=self.load()
        report["cohorts"][0]["models"]["head_support_role_second"]["stakes_yen"]-=100
        with self.assertRaisesRegex(ValueError,"eight-ticket"):
            evaluate(report)
        report=self.load()
        report["cohorts"][1]["models"]["pair_support_role_second"]["pair_covered"]-=1
        with self.assertRaisesRegex(ValueError,"pair support"):
            evaluate(report)
        report=self.load()
        report["cohorts"][1]["models"]["head_support_role_second"]["misses"]["EXACT_HIT"]+=1
        with self.assertRaisesRegex(ValueError,"miss reasons"):
            evaluate(report)


if __name__=="__main__":
    unittest.main()
