import json
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from frozen_head_guard_trial import NAMES, freeze_b, score, run
from test_holdout_analysis import DAY,b_report,k_report

ROOT=Path(__file__).resolve().parents[1]/"research"


class FrozenGuardTrialTests(unittest.TestCase):
    def test_fixed_B_freeze_and_complete_same_population(self):
        freeze, sha = freeze_b(b_report(),DAY,
                               {"first":1.5,"second":1.0,"third":0.75})
        self.assertEqual(len(sha),64)
        self.assertEqual(len(freeze),1)
        row=freeze["202610282301"]
        self.assertEqual(set(row["picks"]),set(NAMES))
        results,scores=score(freeze,b_report(),k_report(),DAY)
        for name in NAMES:
            r=results[name]
            self.assertEqual(r["races"],1)
            self.assertEqual(r["stakes_yen"],800)
            self.assertEqual(sum(r["miss_reasons"].values()),1)
            self.assertEqual(r["miss_reasons"]["EXACT_HIT"],r["hits"])
            if name in NAMES[2:]:
                self.assertEqual(r["heads_covered"],results[NAMES[0]]["heads_covered"])
        self.assertEqual(results["frozen_pair_support"]["pairs_covered"],
                         results[NAMES[0]]["pairs_covered"])
        self.assertTrue(scores["sum_nll"]["baseline"]>0)

    def test_forged_K_does_not_change_B_prediction_and_is_quarantined(self):
        frozen,sha=freeze_b(b_report(),DAY,
                            {"first":1.5,"second":1.0,"third":0.75})
        bad_k=k_report().replace("1R  1-3-4     730",
                                 "1R  2-3-4     730")
        result,_=score(frozen,b_report(),bad_k,DAY)
        self.assertEqual(result[NAMES[0]]["races"],0)
        self.assertEqual(freeze_b(b_report(),DAY,
                         {"first":1.5,"second":1.0,"third":0.75})[1],sha)

    def test_no_duplicate_dates_and_sha_validated_before_IO(self):
        receipt=json.loads((ROOT/"role_temperature_aug10_17_train_test.json")
                           .read_text(encoding="utf-8"))
        with self.assertRaises(ValueError):
            run(Path("."),receipt,[DAY]*3)
        altered=dict(receipt)
        altered["trained_parameters_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"hash mismatch"):
            run(Path("."),altered,[date(2026,9,i) for i in (10,11,12)])


if __name__=="__main__":
    unittest.main()
