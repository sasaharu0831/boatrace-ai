import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from frozen_head_guard import NAMES,fixed_predictions,pair
from role_temperature_calibration import distribution,top_eight
from shadow_baseline import rank_tickets
from historical_records import parse_program
from test_historical_records import DAY,program

FROZEN={"first":1.5,"second":1.0,"third":0.75}


class FrozenHeadGuardTests(unittest.TestCase):
    def setUp(self):
        self.rows=parse_program(program(),DAY)[1]["202610282301"]

    def verify(self,rows):
        picks,probs=fixed_predictions(rows,FROZEN)
        self.assertEqual(set(picks),set(NAMES))
        self.assertEqual(len(probs),120)
        self.assertAlmostEqual(sum(probs.values()),1.0,places=11)
        self.assertEqual(picks["baseline_local_motor"],rank_tickets(rows,"local_motor"))
        self.assertEqual(picks["frozen_temperature"],top_eight(probs))
        heads={t[0] for t in picks["baseline_local_motor"]}
        pairs={pair(t) for t in picks["baseline_local_motor"]}
        for key in NAMES:
            self.assertEqual(len(picks[key]),8)
            self.assertEqual(len(set(picks[key])),8)
        for key in NAMES[2:]:
            self.assertEqual({t[0] for t in picks[key]},heads)
        self.assertEqual({pair(t) for t in picks["frozen_pair_support"]},pairs)
        return picks

    def test_preserves_exact_B_only_head_pair_support(self):
        self.verify(self.rows)

    def test_deterministic_across_entry_order_and_synthetic_B_rows(self):
        self.assertEqual(self.verify(self.rows),self.verify(list(reversed(self.rows))))
        for shift in range(12):
            rows=copy.deepcopy(self.rows)
            for r in rows:
                r["local_win_rate"]=float(1+(r["boat"]+shift)%9)
                r["motor_2rate"]=float((r["boat"]*11+shift*5)%90)
            self.verify(rows)

    def test_K_result_odds_payout_popularity_never_affect_predictions(self):
        original=self.verify(self.rows)
        revised=copy.deepcopy(self.rows)
        for r in revised:
            r.update({"national_win_rate":500,"national_2rate":100,
                      "K_result":"6-5-4","odds":99999,
                      "payout_yen_per_100":30000,"popularity":4})
        self.assertEqual(original,self.verify(revised))

    def test_bad_frozen_parameters_or_B_input_rejected(self):
        with self.assertRaises(ValueError):
            fixed_predictions(self.rows,{"first":1.0})
        bad=copy.deepcopy(self.rows)
        bad[0]["motor_2rate"]=float("nan")
        with self.assertRaises(ValueError):
            fixed_predictions(bad,FROZEN)
        with self.assertRaises(ValueError):
            pair("1-1-2")


if __name__=="__main__":
    unittest.main()
