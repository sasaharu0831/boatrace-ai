import copy
from datetime import date
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from role_temperature_retest import checked_training_fit
from role_temperature_calibration import freeze_digest

SOURCE=Path(__file__).resolve().parents[1]/"research"/"role_temperature_aug10_17_train_test.json"


class FrozenRetestTests(unittest.TestCase):
    def setUp(self):
        self.receipt=json.loads(SOURCE.read_text(encoding="utf-8"))
        self.dates=[date(2026,8,i) for i in (28,29,30)]

    def test_verifies_original_model_sha_and_never_refits(self):
        coeff=checked_training_fit(self.receipt,self.dates)
        self.assertEqual(coeff,{"first":1.5,"second":1,"third":0.75})
        self.assertEqual(self.receipt["trained_parameters_sha256"],
                         freeze_digest({"fit":self.receipt["fit"],
                                        "train_receipts":self.receipt["train_provenance"]}))

    def test_modified_temperature_or_train_provenance_rejected(self):
        a=copy.deepcopy(self.receipt)
        a["fit"]["role_temperatures"]["first"]=1.25
        with self.assertRaisesRegex(ValueError,"hash mismatch"):
            checked_training_fit(a,self.dates)
        a=copy.deepcopy(self.receipt)
        a["train_provenance"][0]["K_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"hash mismatch"):
            checked_training_fit(a,self.dates)

    def test_test_dates_not_overlap_training_or_first_holdout(self):
        for dates in (
            [date(2026,8,10),date(2026,8,11),date(2026,8,12)],
            [date(2026,8,15),date(2026,8,16),date(2026,8,17)],
            [date(2026,8,17),date(2026,8,28),date(2026,8,29)],
            [date(2026,8,28)]*3,
        ):
            with self.assertRaisesRegex(ValueError,"strictly after"):
                checked_training_fit(self.receipt,dates)

    def test_fake_forward_promotion_refused(self):
        a=copy.deepcopy(self.receipt)
        a["forward_verified_races"]=1
        with self.assertRaisesRegex(ValueError,"Forward"):
            checked_training_fit(a,self.dates)


if __name__=="__main__":
    unittest.main()
