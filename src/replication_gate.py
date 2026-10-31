#!/usr/bin/env python3
"""Read-only two-cohort replication gate for historical B-only 8-point research.

This only judges whether a frozen research candidate improves BOTH exact hits
and hypothetical ROI on two disjoint cohorts. It NEVER promotes to production,
because authentic predeadline evidence and incident-free verification are absent.
"""
from __future__ import annotations
import argparse
from datetime import date
import json
from pathlib import Path

CANDIDATE = "keep_pairs_top2_third2"
BASELINE = "baseline_local_motor"
MIN_RACES_EACH = 100


def summarize(a: dict, b: dict):
    first_dates = a.get("dates", [])
    second_dates = b.get("repeat_dates", [])
    if (len(first_dates) != 3 or len(set(first_dates)) != 3 or
            len(second_dates) != 3 or len(set(second_dates)) != 3 or
            set(first_dates) & set(second_dates)):
        raise ValueError("two independently disjoint three-day cohorts required")
    for dates in (first_dates, second_dates):
        for text in dates:
            date.fromisoformat(text)
    if a.get("forward_verified_races") != 0 or b.get("forward_verified_races") != 0:
        raise ValueError("historical trials must never be described as genuine Forward")
    if not a.get("baseline_pair_support_exactly_preserved"):
        raise ValueError("first trial did not prove 1st/2nd pair invariant")
    if b.get("replication_gate", {}).get("pass_both") is True:
        # Never trust a hand-edited decision label; recalculate independently.
        pass
    evaluations = []
    for label, trial in (
        ("first_historical_cohort", a["policies"]),
        ("independent_replication_cohort", b["replication_results"]),
    ):
        base, cand = trial[BASELINE], trial[CANDIDATE]
        for value in (base, cand):
            n = value.get("races", 0)
            if not isinstance(n, int) or n < MIN_RACES_EACH:
                raise ValueError("insufficient historical cohort size")
            if value.get("stakes_yen") != 800 * n:
                raise ValueError("must evaluate exactly 8 tickets at 100 yen each")
            if not isinstance(value.get("hits"), int) or not 0 <= value["hits"] <= n:
                raise ValueError("invalid exact hit count")
            if not isinstance(value.get("payout_yen"), int) or value["payout_yen"] < 0:
                raise ValueError("invalid historical payout total")
        if cand["races"] != base["races"] or cand["stakes_yen"] != base["stakes_yen"]:
            raise ValueError("candidate and baseline use different races/stakes")
        if (cand.get("head_covered") != base.get("head_covered") or
                cand.get("head_second_pair_covered") !=
                base.get("head_second_pair_covered")):
            raise ValueError("1st/2nd pair coverage changed despite invariant")
        hit_delta = cand["hits"] - base["hits"]
        payout_delta = cand["payout_yen"] - base["payout_yen"]
        evaluations.append({
            "cohort": label, "races": base["races"],
            "hit_delta": hit_delta, "payout_delta_yen": payout_delta,
            "hit_rate_delta": hit_delta / base["races"],
            "return_rate_delta": payout_delta / base["stakes_yen"],
            "improved_both": hit_delta > 0 and payout_delta > 0,
        })
    passed = all(row["improved_both"] for row in evaluations)
    return {
        "type": "HISTORICAL_TWO_COHORT_REPLICATION_GATE",
        "candidate": CANDIDATE, "baseline": BASELINE,
        "cohorts": evaluations, "replicated_both_metrics": passed,
        "status": "HISTORICAL_REPLICATION_ONLY" if passed else "REJECT_RESEARCH_PROMOTION",
        "production_eligible": False, "forward_verified_races": 0,
        "warning": "Even two positive historical cohorts would NOT establish preclose authenticated Forward performance."
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--first", type=Path, required=True)
    p.add_argument("--second", type=Path, required=True)
    args = p.parse_args()
    data = summarize(json.loads(args.first.read_text(encoding="utf-8")),
                     json.loads(args.second.read_text(encoding="utf-8")))
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
