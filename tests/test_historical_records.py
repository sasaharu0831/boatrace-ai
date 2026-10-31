import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from historical_records import parse_program, parse_results, reconcile, race_key

DAY = date(2026, 10, 28)
B_LINE = [
    "1 5104山田　丈28福岡51A2 6.82 51.38 5.40 30.00 45 33.33 18 31.72 2            9",
    "2 5359佐藤世那20東京55B1 4.76 32.50 2.86 14.29 20 38.10 15 36.36 16          12",
    "3 4474渡辺　崇39福岡57B1 5.32 33.68 5.50 27.78 29 36.36 53 34.51 36           6",
    "4 3726桂林　寛55福岡54B1 4.22 17.91 4.71 29.27 41 40.74 17 36.36 5            5",
    "5 5397寺田夢生24山口46B2 1.63  0.00 1.38  0.00 30 30.00 36 26.81 6            7",
    "6 3584佐々木英53広島53B1 4.71 27.66 5.57 39.29 26 20.00 37 35.37 33          11",
]
K_LINE = [
    "  01  1 5104 山　田　　　　丈 45   18  6.64   1    0.22     1.47.4",
    "  02  3 4474 渡　辺　　　　崇 29   53  6.69   3    0.24     1.50.0",
    "  03  4 3726 桂　林　　　　寛 41   17  6.78   4    0.25     1.51.6",
    "  04  2 5359 佐　藤　　世　那 20   15  6.66   2    0.23     1.52.4",
    "  05  6 3584 佐々木　　英　樹 26   37  6.76   6    0.25     1.52.4",
    "  06  5 5397 寺　田　　夢　生 30   36  6.75   5    0.28     2.01.0",
]


def program():
    return "\n".join(["STARTB", "23BBGN", "ボートレース唐　津",
        "　１Ｒ  朝１戦　　　          Ｈ１８００ｍ  電話投票締切予定０８：３５ ",
        *B_LINE, "ENDB"])


def results():
    return "\n".join(["STARTK", "23KBGN", "唐　津［成績］",
        "   [払戻金]       ３連単           ３連複           ２連単         ２連複",
        "           1R  1-3-4     730    1-3-4     470    1-3     250    1-3     250",
        "   1R       朝１戦　　　                 H1800m  晴　  風  北東　 3m  波　  3cm",
        *K_LINE, "ENDK"])


class ParsingTests(unittest.TestCase):
    def test_match_official_record_fixtures(self):
        b = parse_program(program(), DAY)
        k = parse_results(results(), DAY)
        key = "202610282301"
        self.assertEqual(race_key(DAY, "23", 1), key)
        self.assertEqual(b[0][key]["deadline_jst"], "2026-10-28T08:35:00+09:00")
        self.assertEqual(len(b[1][key]), 6)
        self.assertEqual(b[1][key][0]["racer"], 5104)
        self.assertEqual(b[1][key][0]["motor_number"], 45)
        self.assertEqual(b[1][key][0]["national_win_rate"], 6.82)
        self.assertEqual(len(k[1][key]), 6)
        self.assertEqual(k[2][key]["trifecta"], "1-3-4")
        self.assertEqual(k[2][key]["payout_yen_per_100"], 730)
        audit = reconcile(b, k)
        self.assertEqual(audit["historical_normal_joined"], 1)
        self.assertFalse(audit["forward_eligible"])

    def test_detect_disagreement_and_do_not_leak(self):
        b = parse_program(program().replace("1 5104", "1 9999"), DAY)
        k = parse_results(results(), DAY)
        audit = reconcile(b, k)
        self.assertEqual(audit["historical_normal_joined"], 0)
        self.assertTrue(any(row[0] == "B_K_registration_mismatch" for row in audit["issues"]))

    def test_detect_bad_ticket(self):
        k = parse_results(results().replace("1R  1-3-4     730", "1R  1-2-4     730"), DAY)
        audit = reconcile(parse_program(program(), DAY), k)
        self.assertEqual(audit["historical_normal_joined"], 0)
        self.assertTrue(any(row[0] == "payout_finish_mismatch" for row in audit["issues"]))

    def test_out_of_range_motor_rate_is_quarantined(self):
        bad = program().replace("45 33.33 18 31.72", "45 133.33 18 31.72")
        b = parse_program(bad, DAY)
        self.assertTrue(any(x[0] == "out_of_range_B" for x in b[2]))
        result = reconcile(b, parse_results(results(), DAY))
        self.assertEqual(result["historical_normal_joined"], 0)

    def test_distance_conflict_is_quarantined(self):
        bad = results().replace("H1800m", "H1200m")
        result = reconcile(parse_program(program(), DAY), parse_results(bad, DAY))
        self.assertEqual(result["historical_normal_joined"], 0)
        self.assertTrue(any(x[0] == "B_K_distance_mismatch" for x in result["issues"]))

    def test_duplicate_crew_refused_even_if_six_positions(self):
        b = parse_program(program(), DAY)
        k = parse_results(results(), DAY)
        key = "202610282301"
        b[1][key][1]["racer"] = b[1][key][0]["racer"]
        k[1][key][3]["racer"] = b[1][key][0]["racer"]
        result = reconcile(b, k)
        self.assertEqual(result["historical_normal_joined"], 0)
        self.assertTrue(any(x[0] == "duplicate_B_boat_or_racer" for x in result["issues"]))

    def test_missing_boat_never_eligible(self):
        b = parse_program(program().replace(B_LINE[-1], ""), DAY)
        k = parse_results(results(), DAY)
        self.assertEqual(reconcile(b, k)["historical_normal_joined"], 0)


if __name__ == "__main__":
    unittest.main()
