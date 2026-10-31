import copy
from datetime import date
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from head_diversification_trial import NAMES, freeze_candidates, score_day, run
from test_historical_records import DAY, program, results


def B():
    return program().replace("ボートレース唐　津","２０２６年１０月２８日\nボートレース唐　津")


def K():
    return results().replace("唐　津［成績］","2026/10/28\n唐　津［成績］")


class HeadCandidateTrialTests(unittest.TestCase):
    def test_frozen_b_only_three_policies_and_timestamp_independent(self):
        frozen,sha=freeze_candidates(B(),DAY)
        self.assertEqual(len(frozen),1)
        x=frozen["202610282301"]
        self.assertEqual(set(x),set(NAMES))
        self.assertTrue(len(sha)==64)
        for policy,tickets in x.items():
            self.assertEqual(len(tickets),8)
            self.assertEqual(len(set(tickets)),8)
            if policy=="local_motor_head3":
                self.assertGreaterEqual(len({t[0] for t in tickets}),3)

    def test_scoring_counts_are_consistent_and_historical_only(self):
        frozen,sha=freeze_candidates(B(),DAY)
        a=score_day(frozen,K(),B(),DAY)
        for policy,stats in a.items():
            self.assertEqual(stats["races"],1)
            self.assertEqual(stats["stakes_yen"],800)
            self.assertEqual(sum(stats["miss_reasons"].values()),1)
            self.assertEqual(stats["miss_reasons"]["EXACT_HIT"],stats["hits"])
            self.assertEqual(stats["head_covered"],int(stats["winner_head_coverage_rate"]))
        modified=K().replace("1R  1-3-4     730","1R  2-3-4     730")
        bad=score_day(frozen,modified,B(),DAY)
        self.assertTrue(all(v["races"]==0 for v in bad.values()))
        self.assertEqual(sha,freeze_candidates(B(),DAY)[1])

    def test_future_outcome_cannot_change_b_freeze(self):
        frozen,sha=freeze_candidates(B(),DAY)
        k2=K().replace("1R  1-3-4     730","1R  6-1-3     999")
        self.assertEqual(freeze_candidates(B(),DAY),(frozen,sha))
        # K mismatch may quarantine this result, but must never rewrite B.
        score_day(frozen,k2,B(),DAY)
        self.assertEqual(freeze_candidates(B(),DAY)[1],sha)

    def test_run_rejects_incomplete_days(self):
        with self.assertRaises(ValueError):
            run(Path("."),[DAY])
        with self.assertRaises(ValueError):
            run(Path("."),[DAY,DAY,DAY])


if __name__ == "__main__":
    unittest.main()
