import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from pair_protected_trial import freeze_B, score_day, run, NAMES
from test_holdout_analysis import b_report, k_report, DAY


class PairProtectedTrialTests(unittest.TestCase):
    def test_B_only_frozen_then_K_diagnostics(self):
        frozen,digest=freeze_B(b_report(),DAY)
        self.assertEqual(len(digest),64)
        self.assertEqual(set(frozen["202610282301"]),set(NAMES))
        observed=score_day(frozen,b_report(),k_report(),DAY)
        for name in NAMES:
            x=observed[name]
            self.assertEqual(x["races"],1)
            self.assertEqual(x["stakes_yen"],800)
            self.assertEqual(x["hits"],x["misses"]["EXACT_HIT"])
            self.assertEqual(sum(x["misses"].values()),1)

    def test_outcome_changes_never_change_B_ticket_sha(self):
        frozen,original=freeze_B(b_report(),DAY)
        broken=k_report().replace("1R  1-3-4     730","1R  2-3-4     730")
        result=score_day(frozen,b_report(),broken,DAY)
        self.assertTrue(all(s["races"]==0 for s in result.values()))
        self.assertEqual(freeze_B(b_report(),DAY)[1],original)

    def test_duplicate_days_refused(self):
        with self.assertRaises(ValueError):
            run(Path("."),[DAY,DAY,DAY])
        with self.assertRaises(ValueError):
            run(Path("."),[DAY])


if __name__=="__main__":
    unittest.main()
