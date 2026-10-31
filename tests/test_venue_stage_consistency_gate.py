import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from venue_stage_consistency_gate import evaluate

FILE=Path(__file__).resolve().parents[1]/"research"/"venue_stage_sep28_oct26_2026.json"


class VenueStageConsistencyTests(unittest.TestCase):
    def load(self):
        return json.loads(FILE.read_text(encoding="utf-8"))

    def test_actual_subgroup_research_has_no_production_router(self):
        result=evaluate(self.load())
        self.assertFalse(result["subgroup_model_router_authorized"])
        self.assertFalse(result["production_eligible"])
        self.assertEqual(result["forward_verified_races"],0)
        self.assertEqual([c["races"] for c in result["cohort_summaries"]],[387,376])
        self.assertEqual(result["sufficiently_populated_venue_groups_in_both"],
                         ["venue:04","venue:05","venue:24"])
        self.assertIn("stage:QUALIFYING",result["sufficiently_populated_B_stage_groups_in_both"])

    def test_reject_missing_daily_sha_and_retroactive_forward_claim(self):
        report=self.load()
        report["cohorts"][0]["source_receipts"][0]["B_sha256"]="FAKE"
        with self.assertRaisesRegex(ValueError,"SHA256"):
            evaluate(report)
        report=self.load()
        report["forward_verified_races"]=1
        with self.assertRaisesRegex(ValueError,"production"):
            evaluate(report)

    def test_reject_forged_subgroup_counts_and_derived_scores(self):
        report=self.load()
        report["cohorts"][0]["groups"]["stage:QUALIFYING"]["calibrated"]["hits"]+=1
        with self.assertRaisesRegex(ValueError,"miss partition"):
            evaluate(report)
        report=self.load()
        group=report["cohorts"][0]["groups"]["stage:QUALIFYING"]["calibrated"]
        group["hits"]+=1
        group["misses"]["EXACT_HIT"]+=1
        group["misses"]["HEAD_ABSENT"]-=1
        with self.assertRaisesRegex(ValueError,"reconcile"):
            evaluate(report)
        report=self.load()
        report["cohorts"][1]["groups"]["overall"]["baseline"]["mean_logloss"]+=0.01
        with self.assertRaisesRegex(ValueError,"logloss"):
            evaluate(report)

    def test_group_minimum_is_not_significance_test(self):
        report=self.load()
        report["cohorts"][0]["groups"]["stage:FINAL"]["sufficient_for_descriptive_comparison"]=True
        with self.assertRaisesRegex(ValueError,"sample-size"):
            evaluate(report)

    def test_overlap_rejected(self):
        report=self.load()
        day=report["cohorts"][0]["dates"][0]
        report["cohorts"][1]["dates"][0]=day
        report["cohorts"][1]["source_receipts"][0]["day"]=day
        with self.assertRaisesRegex(ValueError,"overlapping"):
            evaluate(report)


if __name__=="__main__":
    unittest.main()
