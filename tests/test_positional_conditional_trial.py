import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from positional_conditional_trial import POLICIES, freeze_program, score_day, run
from test_holdout_analysis import DAY,b_report,k_report


class PositionalTrialTests(unittest.TestCase):
    def test_B_first_and_K_only_score(self):
        frozen,stages,digest=freeze_program(b_report(),DAY)
        self.assertEqual(len(digest),64)
        self.assertEqual(len(frozen),1)
        self.assertEqual(set(frozen["202610282301"]),set(POLICIES))
        scored=score_day(frozen,stages,b_report(),k_report(),DAY)
        for row in scored.values():
            self.assertEqual(row["races"],1)
            self.assertEqual(row["stakes_yen"],800)
            self.assertEqual(sum(row["misses"].values()),1)
            self.assertEqual(row["misses"]["EXACT_HIT"],row["hits"])

    def test_inconsistent_K_payout_quarantined_not_frozen(self):
        frozen,stages,digest=freeze_program(b_report(),DAY)
        bad=k_report().replace("1R  1-3-4     730","1R  2-3-4     730")
        metrics=score_day(frozen,stages,b_report(),bad,DAY)
        self.assertTrue(all(row["races"]==0 for row in metrics.values()))
        self.assertEqual(freeze_program(b_report(),DAY)[2],digest)

    def test_invalid_dates_rejected_before_external_access(self):
        with self.assertRaises(ValueError):
            run(Path("."),[DAY,DAY,DAY])
        with self.assertRaises(ValueError):
            run(Path("."),[DAY,DAY])


if __name__=="__main__":
    unittest.main()
