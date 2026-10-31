import copy
from datetime import date
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from paired_outcome_attribution import apply, empty, finalize, score_day, run
from role_temperature_trial import freeze_test_b
from test_holdout_analysis import DAY, b_report, k_report

ROOT = Path(__file__).resolve().parents[1] / "research"
TEMP = {"first":1.5,"second":1.0,"third":0.75}


def baseline_and_candidate():
    # B and C each contain eight valid, distinct B-only tickets.
    baseline = ["1-2-3", "1-3-4", "1-4-3", "2-1-3",
                "2-3-4", "3-1-2", "4-1-2", "5-1-2"]
    candidate = ["1-2-4", "1-3-4", "1-4-3", "2-1-3",
                 "2-3-4", "3-1-2", "4-1-2", "5-1-2"]
    return baseline, candidate


class PayoutAttributionTests(unittest.TestCase):
    def test_exact_paired_partition_explains_better_hit_rate_worse_return(self):
        b,c = baseline_and_candidate()
        row = empty()
        apply(row, b, c, "1-2-3", 15000)  # baseline only: large payout
        apply(row, b, c, "1-2-4", 1000)   # calibrated only: low payout
        apply(row, b, c, "2-3-4", 1200)   # both
        apply(row, b, c, "1-5-4", 900)    # neither
        apply(row, b, c, "1-2-4", 800)    # calibrated only, low payout
        result=finalize(row)
        self.assertEqual(result["outcome_counts"],
                         {"both_hit":1,"baseline_only":1,"calibrated_only":2,"neither_hit":1})
        self.assertEqual(result["baseline_hits"],2)
        self.assertEqual(result["calibrated_hits"],3)
        self.assertEqual(result["hit_delta"],1)
        self.assertEqual(result["gain_only_paid_yen"],1800)
        self.assertEqual(result["lost_only_paid_yen"],15000)
        self.assertEqual(result["payout_delta_yen"],-13200)
        self.assertEqual(result["baseline_hypothetical_paid_yen"],16200)
        self.assertEqual(result["calibrated_hypothetical_paid_yen"],3000)
        self.assertEqual(result["stakes_yen"],4000)
        self.assertLess(result["calibrated_hypothetical_return_rate"],
                        result["baseline_hypothetical_return_rate"])

    def test_positive_K_markers_are_not_called_accident_free(self):
        b_text, k_text=b_report(),k_report()
        frozen,sha=freeze_test_b(b_text,DAY,TEMP)
        normal=score_day(frozen,b_text,k_text,DAY)
        self.assertIn("K_marker:ABSENT_UNVERIFIED",normal)
        marked=k_text.replace("  01  1 5104","安定板使用\n  01  1 5104")
        flagged=score_day(frozen,b_text,marked,DAY)
        self.assertIn("K_marker:POSITIVE",flagged)
        self.assertNotIn("K_marker:ABSENT_UNVERIFIED",flagged)
        self.assertEqual(flagged["K_marker:POSITIVE"]["K_positive_marker_races"],1)
        self.assertEqual(sha,freeze_test_b(b_text,DAY,TEMP)[1])

    def test_K_mismatch_excludes_race_without_modifying_frozen_B(self):
        b=b_report()
        picks,digest=freeze_test_b(b,DAY,TEMP)
        k=k_report().replace("1R  1-3-4     730","1R  2-3-4     730")
        self.assertEqual(score_day(picks,b,k,DAY),{})
        self.assertEqual(freeze_test_b(b,DAY,TEMP)[1],digest)

    def test_forged_counts_payout_or_tickets_fail_closed(self):
        b,c=baseline_and_candidate()
        row=empty()
        apply(row,b,c,"1-2-4",500)
        row["outcome_counts"]["both_hit"]+=1
        with self.assertRaisesRegex(ValueError,"partition"):
            finalize(row)
        row=empty()
        with self.assertRaisesRegex(ValueError,"eight unique"):
            apply(row,b[:7],c,"1-2-3",100)
        with self.assertRaisesRegex(ValueError,"outcome-only"):
            apply(row,b,c,"1-2-3",-100)

    def test_duplicate_test_days_or_fake_training_hash_refused(self):
        receipt=json.loads((ROOT/"role_temperature_aug10_17_train_test.json")
                           .read_text(encoding="utf-8"))
        with self.assertRaisesRegex(ValueError,"three unique"):
            run(Path("."),receipt,[DAY,DAY,DAY])
        edited=copy.deepcopy(receipt)
        edited["fit"]["role_temperatures"]["first"]=1.25
        with self.assertRaisesRegex(ValueError,"hash mismatch"):
            run(Path("."),edited,[date(2026,10,i) for i in (18,19,20)])


if __name__=="__main__":
    unittest.main()
