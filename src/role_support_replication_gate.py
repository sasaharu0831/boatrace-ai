#!/usr/bin/env python3
"""Fail-closed two-cohort B-only head/pair-guard replication decision.

Even a two-cohort historical success cannot authorize a genuine preclose Forward
production model. Result is only a reproducibility check of fixed research
hypotheses with equal eight-ticket stake per race.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re

MODELS=("baseline_local_motor","head_support_role_second","pair_support_role_second")
SHA=re.compile(r"^[0-9a-f]{64}$")


def evaluate(report):
    if report.get("mode")!="HISTORICAL_SHADOW_NOT_FORWARD":
        raise ValueError("not an eligible historical audit")
    if report.get("forward_verified_races")!=0 or report.get("production_models_promoted")!=0:
        raise ValueError("cannot relabel a retrospective test as genuine Forward")
    if report.get("tickets_per_race")!=8 or report.get("odds_used_for_ticket_selection") is not False:
        raise ValueError("eight ticket, odds-free rules required")
    cohorts=report.get("cohorts",[])
    if len(cohorts)!=2:
        raise ValueError("two historical cohorts required")
    dates=[]
    decision={name:[] for name in MODELS[1:]}
    for cohort in cohorts:
        days=cohort["sha_receipts"]
        if len(days)!=3 or cohort["dates"] != [item["day"] for item in days]:
            raise ValueError("exactly three date receipts per cohort")
        for row in days:
            date.fromisoformat(row["day"])
            dates.append(row["day"])
            for field in ("B_sha256","K_sha256","tickets_sha256"):
                if not isinstance(row.get(field),str) or not SHA.fullmatch(row[field]):
                    raise ValueError("missing B/K/frozen ticket SHA256 receipt")
        models=cohort["models"]
        if set(models)!=set(MODELS):
            raise ValueError("incomplete policy list")
        base=models[MODELS[0]]
        n=base["races"]
        if not isinstance(n,int) or n<100:
            raise ValueError("holdout too small")
        for key in MODELS:
            s=models[key]
            if s["races"]!=n or s["stakes_yen"]!=n*800:
                raise ValueError("unequal eight-ticket exposure")
            if s["head_covered"]!=base["head_covered"]:
                raise ValueError("baseline head support was changed")
            if (key=="pair_support_role_second" and
                    s["pair_covered"]!=base["pair_covered"]):
                raise ValueError("baseline ordered pair support was changed")
            if not isinstance(s["hits"],int) or not 0<=s["hits"]<=n:
                raise ValueError("invalid hit count")
            if not isinstance(s["payout_yen"],int) or s["payout_yen"]<0:
                raise ValueError("invalid payout")
            if s["misses"]["EXACT_HIT"]!=s["hits"] or sum(s["misses"].values())!=n:
                raise ValueError("nonexclusive miss reasons")
            if sum(x["races"] for x in s["by_stage"].values())!=n:
                raise ValueError("stage population inconsistent")
        for key in MODELS[1:]:
            cand=models[key]
            hit=cand["hits"]-base["hits"]
            paid=cand["payout_yen"]-base["payout_yen"]
            decision[key].append({
                "days":cohort["dates"],"races":n,"hit_delta":hit,
                "payout_yen_delta":paid,"roi_delta":paid/(800*n),
                "passed":hit>0 and paid>0
            })
    if len(set(dates))!=6:
        raise ValueError("overlapping research dates")
    return {
        "kind":"TWO_COHORT_B_ONLY_ROLE_GUARD_REPLICATION",
        "decisions":{name:{"cohorts":rows,"replicated":all(x["passed"] for x in rows)}
                     for name,rows in decision.items()},
        "forward_verified_races":0, "production_eligible":False,
        "explanation":"Historical backtests cannot authorize production without independently verified preclose data."
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--report",type=Path,required=True)
    args=p.parse_args()
    print(json.dumps(evaluate(json.loads(args.report.read_text(encoding="utf-8"))),
                     ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
