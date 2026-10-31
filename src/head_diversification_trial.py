#!/usr/bin/env python3
"""Holdout of frozen B-only head-diversification candidates, NOT true Forward.

Three predeclared policies: local_motor fixed baseline and two candidates with
minimum 2/3 distinct first-place boats among eight tickets. Does not optimize
coefficients or choose a winning policy from outcomes.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path

from archive_backfill import archive_path
from historical_records import parse_program, parse_results, reconcile
from historical_sqlite import validate_report_date
from head_diversification_candidate import policies
from holdout_analysis import classify_ticket_miss
from lzh_extract import decode_report
from quality_policy import k_observations
from shadow_baseline import rank_tickets

NAMES = ("baseline_local_motor", "local_motor_head2", "local_motor_head3")
ERRORS = ("EXACT_HIT", "HEAD_ABSENT", "SECOND_THIRD_SWAPPED",
          "HEAD_PRESENT_SECOND_ABSENT", "HEAD_SECOND_PRESENT_THIRD_ABSENT")


def freeze_candidates(b_text, day):
    if not b_text.startswith("STARTB"):
        raise ValueError("invalid B file")
    validate_report_date(b_text, day, "B")
    races, entries, issues = parse_program(b_text, day)
    bad = {i[1] for i in issues if len(i)>1 and isinstance(i[1],str)}
    frozen={}
    for key in sorted(races):
        if key in bad:
            continue
        try:
            rows=entries[key]
            c=policies(rows)
            c["baseline_local_motor"]=rank_tickets(rows,"local_motor")
            frozen[key]={name:c[name] for name in NAMES}
        except (ValueError,TypeError,KeyError):
            continue
    canonical=json.dumps(frozen,sort_keys=True,separators=(",",":"),ensure_ascii=False)
    return frozen, hashlib.sha256(canonical.encode()).hexdigest()


def score_day(frozen, k_text, b_text, day):
    if not k_text.startswith("STARTK"):
        raise ValueError("invalid K file")
    validate_report_date(k_text,day,"K")
    k=parse_results(k_text,day)
    accepted=set(reconcile(parse_program(b_text,day),k)["normal_race_keys"])
    flags=k_observations(k_text,day)
    outcomes=k[2]
    out={name:{"races":0,"hits":0,"stakes_yen":0,"payout_yen":0,
               "head_covered":0,"sum_distinct_predicted_heads":0,
               "miss_reasons":Counter(),"K_positive_marker_races":0}
         for name in NAMES}
    for key in sorted(accepted & set(frozen) & set(outcomes)):
        result=outcomes[key]
        actual=result["trifecta"]
        head=actual.split("-")[0]
        marker=bool(flags.get(key,{}).get("special_evidence")
                    or flags.get(key,{}).get("incident_evidence"))
        for name in NAMES:
            picks=frozen[key][name]
            if len(picks)!=8 or len(set(picks))!=8:
                raise ValueError("invalid frozen ticket set")
            x=out[name]
            x["races"]+=1
            x["stakes_yen"]+=800
            x["sum_distinct_predicted_heads"]+=len({s.split("-")[0] for s in picks})
            x["head_covered"]+=int(any(s.startswith(head+"-") for s in picks))
            reason=classify_ticket_miss(picks,actual)
            x["miss_reasons"][reason]+=1
            if reason=="EXACT_HIT":
                x["hits"]+=1
                x["payout_yen"]+=int(result["payout_yen_per_100"])
            x["K_positive_marker_races"]+=int(marker)
    for name,x in out.items():
        x["miss_reasons"]={k:x["miss_reasons"][k] for k in ERRORS}
        if sum(x["miss_reasons"].values()) != x["races"]:
            raise ValueError("miss count not equal population")
        x["hypothetical_hit_rate"]=x["hits"]/x["races"] if x["races"] else None
        x["hypothetical_return_rate"]=x["payout_yen"]/x["stakes_yen"] if x["stakes_yen"] else None
        x["winner_head_coverage_rate"]=x["head_covered"]/x["races"] if x["races"] else None
        x["mean_distinct_predicted_heads"]=x["sum_distinct_predicted_heads"]/x["races"] if x["races"] else None
    return out


def run(root: Path, days: list[date]):
    if len(days)!=3 or len(set(days))!=3:
        raise ValueError("exactly three distinct historical days required")
    per_day=[]
    totals={name:{"races":0,"hits":0,"stakes_yen":0,"payout_yen":0,
                  "head_covered":0,"sum_distinct_predicted_heads":0,
                  "K_positive_marker_races":0,"miss_reasons":Counter()}
            for name in NAMES}
    for day in sorted(days):
        b,bmeta=decode_report(archive_path(root,"B",day))
        frozen,digest=freeze_candidates(b,day) # must occur before even OPENING K
        k,kmeta=decode_report(archive_path(root,"K",day))
        result=score_day(frozen,k,b,day)
        per_day.append({"day":str(day),"B_sha256":bmeta["archive_sha256"],
                        "K_sha256":kmeta["archive_sha256"],"B_frozen_sha256":digest,
                        "B_frozen_races":len(frozen),"results":result})
        for name,stats in result.items():
            x=totals[name]
            for field in ("races","hits","stakes_yen","payout_yen","head_covered",
                          "sum_distinct_predicted_heads","K_positive_marker_races"):
                x[field]+=stats[field]
            x["miss_reasons"].update(stats["miss_reasons"])
    for name,x in totals.items():
        x["miss_reasons"]={k:x["miss_reasons"][k] for k in ERRORS}
        x["hypothetical_hit_rate"]=x["hits"]/x["races"] if x["races"] else None
        x["hypothetical_return_rate"]=x["payout_yen"]/x["stakes_yen"] if x["stakes_yen"] else None
        x["winner_head_coverage_rate"]=x["head_covered"]/x["races"] if x["races"] else None
        x["mean_distinct_predicted_heads"]=x["sum_distinct_predicted_heads"]/x["races"] if x["races"] else None
    return {"mode":"HISTORICAL_HEAD_DIVERSIFICATION_NOT_FORWARD",
            "dates":[str(d) for d in sorted(days)],"eight_tickets_each":True,
            "fixed_coefficients":True,"K_used_only_for_scoring":True,
            "per_day":per_day,"aggregate":totals,
            "forward_verified_races":0,"production_promotion":False,
            "notes":["Historical program B retrieved after race completion, not a real-time preclose snapshot.",
                     "No odds, payout, popularity, or outcomes used to choose tickets.",
                     "Incident-free status not independently authenticated; K markers are descriptive only.",
                     "No result-dependent selection of winning candidate allowed.",
                     "Separate new untouched OOS/true Forward required before production."]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",required=True,type=Path)
    p.add_argument("--dates",required=True,nargs=3)
    a=p.parse_args()
    print(json.dumps(run(a.root,[date.fromisoformat(d) for d in a.dates]),ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
