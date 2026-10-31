import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from frozen_head_guard_gate import evaluate

SOURCE=Path(__file__).resolve().parents[1]/"research"/"frozen_head_guard_sep10_15_2026.json"


class FrozenGuardReplicationGateTests(unittest.TestCase):
    def load(self):
        return json.loads(SOURCE.read_text(encoding="utf-8"))

    def test_verified_779_race_report_does_not_pass_both_periods(self):
        result=evaluate(self.load())
        self.assertFalse(result["production_eligible"])
        self.assertEqual(result["forward_verified_races"],0)
        self.assertEqual(set(result["models"]),{"frozen_head_support","frozen_pair_support"})
        self.assertFalse(result["models"]["frozen_head_support"]["historical_replicated"])
        self.assertFalse(result["models"]["frozen_pair_support"]["historical_replicated"])
        self.assertFalse(result["models"]["frozen_head_support"]["cohorts"][0]["pass_both"])
        self.assertTrue(result["models"]["frozen_head_support"]["cohorts"][1]["pass_both"])

    def test_changed_cohort_or_frozen_SHA_rejected(self):
        trial=self.load()
        trial["cohorts"][1]["test_dates"][0]=trial["cohorts"][0]["test_dates"][0]
        trial["cohorts"][1]["daily_receipts"][0]["day"]=trial["cohorts"][0]["test_dates"][0]
        with self.assertRaisesRegex(ValueError,"overlapping"):
            evaluate(trial)
        trial=self.load()
        trial["cohorts"][0]["daily_receipts"][0]["frozen_predictions_sha256"]="fake"
        with self.assertRaisesRegex(ValueError,"SHA256"):
            evaluate(trial)

    def test_nonnormalized_denominator_and_headpair_mutations_rejected(self):
        trial=self.load()
        trial["cohorts"][0]["results"]["frozen_head_support"]["stakes_yen"]-=100
        with self.assertRaisesRegex(ValueError,"stakes"):
            evaluate(trial)
        trial=self.load()
        trial["cohorts"][1]["results"]["frozen_pair_support"]["pairs_covered"]-=1
        with self.assertRaisesRegex(ValueError,"pair support"):
            evaluate(trial)
        trial=self.load()
        trial["cohorts"][0]["results"]["frozen_head_support"]["miss_reasons"]["EXACT_HIT"]+=1
        with self.assertRaisesRegex(ValueError,"miss classification"):
            evaluate(trial)

    def test_even_two_positive_historical_cohorts_never_production(self):
        trial=self.load()
        for cohort in trial["cohorts"]:
            baseline=cohort["results"]["frozen_temperature"]
            candidate=cohort["results"]["frozen_head_support"]
            hits=baseline["hits"]+1
            candidate["hits"]=hits
            candidate["payout_yen"]=baseline["payout_yen"]+100
            candidate["miss_reasons"]=dict(baseline["miss_reasons"])
            candidate["miss_reasons"]["EXACT_HIT"]=hits
            candidate["miss_reasons"]["HEAD_ABSENT"]-=1
            candidate["gained_hits_vs_frozen"]=1
            candidate["lost_hits_vs_frozen"]=0
        result=evaluate(trial)
        self.assertTrue(result["models"]["frozen_head_support"]["historical_replicated"])
        self.assertFalse(result["production_eligible"])

if __name__=="__main__":
    unittest.main()
