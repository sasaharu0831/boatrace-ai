import copy
from datetime import date
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_holdout_analysis import DAY, b_report, k_report
from role_temperature_trial import freeze_test_b
from venue_stage_probability_audit import score_day, finalize, run, empty, MIN_DESCRIPTIVE_RACES


TEMP = {"first": 1.5, "second": 1.0, "third": 0.75}
ROOT = Path(__file__).resolve().parents[1] / "research"


class VenueStageAuditTests(unittest.TestCase):
    def setUp(self):
        self.b = b_report()
        self.k = k_report()
        self.frozen, self.sha = freeze_test_b(self.b, DAY, TEMP)

    def test_B_venue_stage_and_K_quality_partitions_are_complete(self):
        r = score_day(self.frozen, self.b, self.k, DAY)
        for name in ("baseline_local_motor", "training_calibrated_roles"):
            self.assertEqual(set(r[name]), {
                "overall", "venue:23", "stage:UNSPECIFIED",
                "K_marker:ABSENT_UNVERIFIED",
            })
            for data in r[name].values():
                self.assertEqual(data["races"], 1)
                self.assertEqual(data["stakes_yen"], 800)
                finalized = finalize(data)
                self.assertEqual(finalized["races"], 1)
                self.assertEqual(sum(finalized["misses"].values()), 1)
                self.assertEqual(finalized["hits"], finalized["misses"]["EXACT_HIT"])
                self.assertGreater(finalized["mean_logloss"], 0)
                self.assertGreater(finalized["mean_brier_120"], 0)

    def test_K_positive_marker_is_not_relabelled_incident_free(self):
        positive = self.k.replace("  01  1 5104", "安定板使用\n  01  1 5104")
        r = score_day(self.frozen, self.b, positive, DAY)
        for name in r:
            self.assertIn("K_marker:POSITIVE", r[name])
            self.assertNotIn("K_marker:ABSENT_UNVERIFIED", r[name])
            self.assertIn("venue:23", r[name])
        self.assertEqual(self.sha, freeze_test_b(self.b, DAY, TEMP)[1])

    def test_K_result_mismatch_quarantines_without_mutating_B(self):
        forged = self.k.replace("1R  1-3-4     730", "1R  2-3-4     730")
        r = score_day(self.frozen, self.b, forged, DAY)
        self.assertEqual(r["baseline_local_motor"], {})
        self.assertEqual(r["training_calibrated_roles"], {})
        self.assertEqual(self.sha, freeze_test_b(self.b, DAY, TEMP)[1])

    def test_no_forecast_when_train_fit_or_dates_unverified(self):
        receipt = json.loads((ROOT/"role_temperature_aug10_17_train_test.json")
                             .read_text(encoding="utf-8"))
        with self.assertRaises(ValueError):
            run(Path("."), receipt, [DAY, DAY, DAY])
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            altered = copy.deepcopy(receipt)
            altered["fit"]["role_temperatures"]["first"] = 1.0
            run(Path("."), altered, [date(2026,11,d) for d in (2,3,4)])

    def test_no_promotable_signal_from_small_or_empty_groups(self):
        self.assertEqual(MIN_DESCRIPTIVE_RACES, 30)
        with self.assertRaisesRegex(ValueError, "miss disagreement"):
            row = empty()
            row["races"] = 1
            row["stakes_yen"] = 800
            finalize(row)


if __name__ == "__main__":
    unittest.main()
