import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from quality_policy import classification_audit, k_observations, stage_from_title
from test_historical_records import DAY, program, results


class QualityPolicyTests(unittest.TestCase):
    def test_stage_explicit_only(self):
        self.assertEqual(stage_from_title("準優勝戦"), "SEMIFINAL")
        self.assertEqual(stage_from_title("優勝戦"), "FINAL")
        self.assertEqual(stage_from_title("予選特賞"), "QUALIFYING")
        self.assertEqual(stage_from_title("一般戦"), "GENERAL")
        self.assertEqual(stage_from_title("選抜戦"), "SELECTION")
        self.assertEqual(stage_from_title("朝１戦"), "UNSPECIFIED")

    def test_no_positive_marker_is_not_negative_proof(self):
        audit = classification_audit(program(), results(), DAY)
        self.assertEqual(audit["historical_six_finisher_join"], 1)
        self.assertEqual(audit["training_eligible_races"], 0)
        flags = audit["race_labels"]["202610282301"]
        self.assertEqual(flags["stage"], "UNSPECIFIED")
        self.assertEqual(flags["special_status"], "UNVERIFIED")
        self.assertEqual(flags["incident_status"], "UNVERIFIED")
        self.assertEqual(flags["training_pool"], "UNVERIFIED_NOT_ADMITTED")

    def test_detect_positive_special_markers_in_k_only(self):
        fake = results().replace(
            "   1R       朝１戦",
            "安定板使用\n   1R       朝１戦"
        ).replace("  01  1 5104", "安定板使用　進入固定\n  01  1 5104")
        audit = classification_audit(program(), fake, DAY)
        flag = audit["race_labels"]["202610282301"]
        self.assertCountEqual(flag["special_evidence"],
                              ["STABILITY_PLATE_MENTION", "FIXED_ENTRY_MENTION"])
        self.assertEqual(flag["special_status"], "EVIDENCE_PRESENT")
        self.assertEqual(audit["training_eligible_races"], 0)

    def test_detect_incident_evidence_without_promoting_eligibility(self):
        fake = results().replace("  01  1 5104", "返還　失格\n  01  1 5104")
        flags = k_observations(fake, DAY)["202610282301"]
        self.assertCountEqual(flags["incident_evidence"],
                              ["REFUND_MENTION", "DISQUALIFICATION_MENTION"])
        audit = classification_audit(program(), fake, DAY)
        self.assertEqual(audit["training_eligible_races"], 0)

    def test_b_only_race_has_missing_k_status(self):
        missing = results().replace("23KBGN", "22KBGN")
        audit = classification_audit(program(), missing, DAY)
        record = audit["race_labels"]["202610282301"]
        self.assertEqual(record["special_status"], "K_REPORT_MISSING")
        self.assertEqual(audit["historical_six_finisher_join"], 0)


if __name__ == "__main__":
    unittest.main()
