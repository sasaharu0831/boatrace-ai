import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from role_temperature_replication_gate import evaluate

ROOT=Path(__file__).resolve().parents[1]/"research"


def reports():
    a=json.loads((ROOT/"role_temperature_aug10_17_train_test.json").read_text(encoding="utf-8"))
    b=json.loads((ROOT/"role_temperature_aug28_30_retest.json").read_text(encoding="utf-8"))
    return a,b


class RoleTemperatureTwoCohortGateTests(unittest.TestCase):
    def test_actual_independent_487_and_426_are_both_better_on_four_metrics(self):
        a,b=reports()
        r=evaluate(a,b)
        self.assertEqual(r["combined_descriptive_totals"]["baseline_local_motor"]["races"],913)
        self.assertTrue(r["independent_historical_replication"])
        self.assertFalse(r["production_eligible"])
        self.assertEqual(r["forward_verified_races"],0)
        self.assertTrue(all(x["improved_all_four"] for x in r["cohorts"]))
        self.assertEqual(r["temperatures"],{"first":1.5,"second":1,"third":0.75})

    def test_single_cohort_regression_rejects_even_if_aggregate_is_positive(self):
        a,b=reports()
        p=b["metrics"]["training_calibrated_roles"]
        base=b["metrics"]["baseline_local_motor"]
        p["hits"]=base["hits"]-1
        p["misses"]["EXACT_HIT"]=p["hits"]
        p["misses"]["HEAD_ABSENT"]+=20
        # Ensure the summed miss population remains intact.
        self.assertEqual(sum(p["misses"].values()),p["races"])
        r=evaluate(a,b)
        self.assertFalse(r["independent_historical_replication"])
        self.assertEqual(r["research_status"],"FAILED_HISTORICAL_REPLICATION")
        self.assertFalse(r["production_eligible"])

    def test_no_tampering_with_original_fit_or_frozen_receipts(self):
        a,b=reports()
        a["fit"]["role_temperatures"]["first"]=1.25
        with self.assertRaisesRegex(ValueError,"hash mismatch"):
            evaluate(a,b)
        a,b=reports()
        b["official_raw_and_predicted_sha256"][0]["frozen_120way_and_8_tickets_sha256"]="not-sha"
        with self.assertRaisesRegex(ValueError,"SHA256"):
            evaluate(a,b)

    def test_day_overlap_stake_and_miss_count_are_rejected(self):
        a,b=reports()
        b["dates"][0]=a["first_holdout_dates"][0]
        with self.assertRaisesRegex(ValueError,"chronological"):
            evaluate(a,b)
        a,b=reports()
        b["metrics"]["training_calibrated_roles"]["stakes_yen"]-=100
        with self.assertRaisesRegex(ValueError,"eight-ticket"):
            evaluate(a,b)
        a,b=reports()
        b["metrics"]["training_calibrated_roles"]["misses"]["EXACT_HIT"]+=1
        with self.assertRaisesRegex(ValueError,"miss"):
            evaluate(a,b)

    def test_forward_status_fails_closed(self):
        a,b=reports()
        a["forward_verified_races"]=1
        with self.assertRaisesRegex(ValueError,"Forward"):
            evaluate(a,b)


if __name__=="__main__":
    unittest.main()
