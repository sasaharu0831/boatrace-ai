import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from paired_payout_consistency_gate import verify

ROOT=Path(__file__).resolve().parents[1]/"research"


def load():
    report=json.loads((ROOT/"paired_payout_attribution_sep28_oct26_2026.json")
                       .read_text(encoding="utf-8"))
    previous=json.loads((ROOT/"venue_stage_sep28_oct26_2026.json")
                         .read_text(encoding="utf-8"))
    return report,previous


class PairedPayoutConsistencyTests(unittest.TestCase):
    def test_real_763R_attribution_reconciles_to_previous_independent_audit(self):
        report,prior=load()
        result=verify(report,prior)
        self.assertTrue(result["official_and_prior_prediction_digests_match"])
        self.assertEqual([x["races"] for x in result["cohorts"]],[387,376])
        self.assertEqual(result["cohorts"][0]["net_hits"],7)
        self.assertEqual(result["cohorts"][0]["net_hypothetical_paid_yen"],-2220)
        self.assertEqual(result["cohorts"][1]["net_hits"],16)
        self.assertEqual(result["cohorts"][1]["net_hypothetical_paid_yen"],6740)
        self.assertFalse(result["production_eligible"])
        self.assertEqual(result["forward_verified_races"],0)

    def test_forged_payout_or_disjoint_counts_rejected(self):
        report,prior=load()
        report["cohorts"][0]["groups"]["stage:QUALIFYING"]["outcome_payout_yen_per_100_sum"]["baseline_only"]-=100
        with self.assertRaisesRegex(ValueError,"independent earlier audit"):
            verify(report,prior)
        report,prior=load()
        report["cohorts"][1]["groups"]["overall"]["outcome_counts"]["calibrated_only"]+=1
        with self.assertRaisesRegex(ValueError,"mutually exclusive"):
            verify(report,prior)

    def test_hash_date_and_venue_partition_tampering_rejected(self):
        report,prior=load()
        report["cohorts"][0]["source_sha_and_frozen_ticket_sha"][0]["B_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"prediction SHA256 mismatch"):
            verify(report,prior)
        report,prior=load()
        report["cohorts"][0]["groups"]["venue:04"]["calibrated_hits"]+=1
        with self.assertRaisesRegex(ValueError,"payout decomposition"):
            verify(report,prior)
        report,prior=load()
        report["cohorts"][1]["dates"][0]=report["cohorts"][0]["dates"][0]
        with self.assertRaisesRegex(ValueError,"date cohort mismatch"):
            verify(report,prior)

    def test_never_use_payouts_for_model_promotion(self):
        report,prior=load()
        report["automatic_subgroup_router_enabled"]=True
        with self.assertRaisesRegex(ValueError,"preclose routing"):
            verify(report,prior)
        report,prior=load()
        report["forward_verified_races"]=1
        with self.assertRaisesRegex(ValueError,"preclose routing"):
            verify(report,prior)


if __name__=="__main__":
    unittest.main()
