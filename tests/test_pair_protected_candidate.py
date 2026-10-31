import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from pair_protected_candidate import fixed_policies, pair_protected_tickets, score_rows
from test_historical_records import DAY, program
from historical_records import parse_program


class PairProtectionTests(unittest.TestCase):
    def setUp(self):
        self.rows=parse_program(program(),DAY)[1]["202610282301"]

    def test_two_fixed_candidates_protect_top_second_pairs(self):
        ranked=score_rows(self.rows)
        required=[]
        seen=set()
        for x in ranked:
            if x[3] not in seen:
                required.append(x[1]);seen.add(x[3])
            if len(required)==4:
                break
        for anchors in (3,4):
            chosen=pair_protected_tickets(self.rows,anchors)
            self.assertEqual(len(chosen),8)
            self.assertEqual(len(set(chosen)),8)
            self.assertGreaterEqual(len({t.split("-")[0] for t in chosen}),3)
            self.assertTrue(set(required[:anchors]).issubset(chosen))

    def test_never_consume_national_win_rates_or_result(self):
        prior=fixed_policies(self.rows)
        changed=copy.deepcopy(self.rows)
        for i,row in enumerate(changed):
            row["national_win_rate"]=100+i
            row["national_2rate"]=99+i
            row["winner"]=6-i
            row["payout_yen"]=9999999
        self.assertEqual(prior,fixed_policies(changed))

    def test_deterministic_under_entry_order(self):
        self.assertEqual(fixed_policies(self.rows),fixed_policies(list(reversed(self.rows))))
        self.assertEqual(fixed_policies(self.rows),fixed_policies(self.rows))

    def test_bad_parameters_fail_closed(self):
        with self.assertRaises(ValueError):
            pair_protected_tickets(self.rows,2)
        with self.assertRaises(ValueError):
            pair_protected_tickets(self.rows,4,2)
        invalid=copy.deepcopy(self.rows)
        invalid[1]["motor_2rate"]=120
        with self.assertRaises(ValueError):
            fixed_policies(invalid)


if __name__ == "__main__":
    unittest.main()
