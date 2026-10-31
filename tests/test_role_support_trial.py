import sys
import unittest
from pathlib import Path
from datetime import date

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from role_support_trial import MODELS, freeze_b, score_day, run
from test_holdout_analysis import DAY, b_report, k_report


class RoleSupportTrialTests(unittest.TestCase):
    def test_B_only_fixed_freeze_scoring_and_pair_guard(self):
        tickets, stages, digest=freeze_b(b_report(),DAY)
        self.assertEqual(len(digest),64)
        self.assertEqual(len(tickets),1)
        self.assertEqual(set(tickets["202610282301"]),set(MODELS))
        scores=score_day(tickets,stages,b_report(),k_report(),DAY)
        for name in MODELS:
            row=scores[name]
            self.assertEqual(row["races"],1)
            self.assertEqual(row["stakes_yen"],800)
            self.assertEqual(row["hits"],row["misses"]["EXACT_HIT"])
            self.assertEqual(sum(row["misses"].values()),1)
            self.assertEqual(row["head_covered"],scores[MODELS[0]]["head_covered"])
        self.assertEqual(scores[MODELS[-1]]["pair_covered"],scores[MODELS[0]]["pair_covered"])

    def test_K_result_mismatch_quarantined_without_changing_B_sha(self):
        frozen,stages,digest=freeze_b(b_report(),DAY)
        changed_k=k_report().replace("1R  1-3-4     730","1R  2-3-4     730")
        result=score_day(frozen,stages,b_report(),changed_k,DAY)
        self.assertTrue(all(x["races"]==0 for x in result.values()))
        self.assertEqual(digest,freeze_b(b_report(),DAY)[2])

    def test_day_duplicates_and_short_range_rejected(self):
        with self.assertRaises(ValueError):
            run(Path("."),[DAY,DAY,DAY])
        with self.assertRaises(ValueError):
            run(Path("."),[DAY,DAY])
        with self.assertRaises(ValueError):
            run(Path("."),[DAY,DAY,date(2026,9,8)])


if __name__=="__main__":
    unittest.main()
