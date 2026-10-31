#!/usr/bin/env python3
"""Offline read-only two-cohort B-only positional ranking replication gate.

Never permits production: independently authenticated predeadline capture and
incident-free evidence are NOT established by historical B/K archive records.
"""
from __future__ import annotations
import argparse
from datetime import date
import json
from pathlib import Path
import re

MODELS = ("baseline_local_motor", "role_second_local", "role_third_motor")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def evaluate(report):
    if report.get("report_type") != "B_ONLY_ROLE_CONDITIONAL_TWO_COHORT_HISTORICAL_REPLICATION":
        raise ValueError("wrong input report type")
    if report.get("forward_verified_races") != 0 or report.get("production_models_promoted") != 0:
        raise ValueError("historical report must not claim Forward or production use")
    if not report.get("predictions_frozen_from_B_before_K") or report.get("tickets_per_race") != 8:
        raise ValueError("no B-first freeze or not eight tickets")
    cohorts = report.get("cohorts", [])
    if len(cohorts) != 2:
        raise ValueError("two disjoint historical cohorts required")
    all_dates = []
    evaluations = {model: [] for model in MODELS[1:]}
    for cohort in cohorts:
        days = cohort["days"]
        if len(days) != 3:
            raise ValueError("three days required in each cohort")
        for row in days:
            date.fromisoformat(row["day"])
            all_dates.append(row["day"])
            for field in ("B_sha256", "K_sha256", "frozen_tickets_sha256"):
                if not isinstance(row.get(field), str) or not HEX64.fullmatch(row[field]):
                    raise ValueError("missing source or frozen ticket SHA256")
        stats = cohort["models"]
        if set(stats) != set(MODELS):
            raise ValueError("missing fixed candidate model")
        base = stats[MODELS[0]]
        n = base["races"]
        if not isinstance(n, int) or n < 100:
            raise ValueError("holdout too small")
        for model in MODELS:
            x = stats[model]
            if x["races"] != n or x["stakes_yen"] != 800 * n:
                raise ValueError("same eight-ticket denominator/stake required")
            if not isinstance(x["hits"], int) or not 0 <= x["hits"] <= n:
                raise ValueError("invalid exact hits")
            if not isinstance(x["payout_yen"], int) or x["payout_yen"] < 0:
                raise ValueError("invalid payout")
            if x["misses"]["EXACT_HIT"] != x["hits"] or sum(x["misses"].values()) != n:
                raise ValueError("unverified miss partitions")
            if sum(a["races"] for a in x["by_stage"].values()) != n:
                raise ValueError("unverified B-stage denominators")
        for model in MODELS[1:]:
            candidate = stats[model]
            gain_hits = candidate["hits"] - base["hits"]
            gain_payout = candidate["payout_yen"] - base["payout_yen"]
            evaluations[model].append({
                "dates": [row["day"] for row in days],
                "races": n, "hit_delta": gain_hits,
                "payout_yen_delta": gain_payout,
                "return_rate_delta": gain_payout / (800 * n),
                "passes_both": gain_hits > 0 and gain_payout > 0,
            })
    if len(all_dates) != len(set(all_dates)):
        raise ValueError("overlap between historical holdouts")
    replicated = {model: all(x["passes_both"] for x in rows)
                  for model, rows in evaluations.items()}
    return {
        "gate_type": "HISTORICAL_POSITIONAL_ROLE_TWO_COHORT_ONLY",
        "cohorts": evaluations,
        "both_metric_replication": replicated,
        "production_eligible": False,
        "forward_verified_races": 0,
        "warning": "Even positive historical replication never authenticates a predeadline Forward wager.",
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--report",type=Path,required=True)
    args=p.parse_args()
    print(json.dumps(evaluate(json.loads(args.report.read_text(encoding="utf-8"))),
                     ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
