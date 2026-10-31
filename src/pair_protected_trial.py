#!/usr/bin/env python3
"""Fixed B-only pair-guarded 8-ticket retrospective holdout.

All policy tickets and SHA256 frozen from B BEFORE any K download processing.
No odds/payout/result is an input to a ticket-generation function.
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
from holdout_analysis import classify_ticket_miss, MISS_REASONS
from lzh_extract import decode_report
from pair_protected_candidate import fixed_policies
from quality_policy import k_observations

NAMES=("baseline_local_motor","pair3_head3","pair4_head3")


def freeze_B(text: str, day: date):
    if not text.startswith("STARTB"):
        raise ValueError("invalid B report type")
    validate_report_date(text,day,"B")
    br,be,issues=parse_program(text,day)
    excluded={x[1] for x in issues if len(x)>1 and isinstance(x[1],str)}
    frozen={}
    for key in sorted(br):
        if key in excluded:
            continue
        try:
            frozen[key]=fixed_policies(be[key])
        except (ValueError,TypeError,KeyError):
            continue
    encoded=json.dumps(frozen,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return frozen,hashlib.sha256(encoded.encode()).hexdigest()


def score_day(frozen, b, k, day):
    if not k.startswith("STARTK"):
        raise ValueError("invalid K type")
    validate_report_date(k,day,"K")
    result=parse_results(k,day)
    good=set(reconcile(parse_program(b,day),result)["normal_race_keys"])
    flags=k_observations(k,day)
    outcomes=result[2]
    accepted=sorted(good & set(frozen) & set(outcomes))
    aggregate={name:{"races":0,"hits":0,"stakes_yen":0,"payout_yen":0,
                     "head_covered":0,"head_count_sum":0,"misses":Counter(),
                     "K_marker_present":0}
               for name in NAMES}
    for key in accepted:
        actual=outcomes[key]["trifecta"]
        payout=int(outcomes[key]["payout_yen_per_100"])
        head=actual[0]
        marker=bool(flags.get(key,{}).get("special_evidence") or
                    flags.get(key,{}).get("incident_evidence"))
        for name in NAMES:
            tickets=frozen[key][name]
            why=classify_ticket_miss(tickets,actual)
            out=aggregate[name]
            out["races"]+=1
            out["stakes_yen"]+=800
            out["head_covered"]+=int(any(x[0]==head for x in tickets))
            out["head_count_sum"]+=len({t[0] for t in tickets})
            out["misses"][why]+=1
            out["K_marker_present"]+=int(marker)
            if why=="EXACT_HIT":
                out["hits"]+=1
                out["payout_yen"]+=payout
    for name,out in aggregate.items():
        out["misses"]={reason:out["misses"][reason] for reason in MISS_REASONS}
        if sum(out["misses"].values())!=len(accepted):
            raise ValueError("diagnostic partition mismatch")
        out["hypothetical_hit_rate"]=out["hits"]/out["races"] if out["races"] else None
        out["hypothetical_return_rate"]=out["payout_yen"]/out["stakes_yen"] if out["stakes_yen"] else None
        out["winner_head_coverage_rate"]=out["head_covered"]/out["races"] if out["races"] else None
        out["mean_distinct_heads"]=out["head_count_sum"]/out["races"] if out["races"] else None
    return aggregate


def run(root: Path, days: list[date]):
    if len(days)!=3 or len(set(days))!=3:
        raise ValueError("exactly three unique old dates required")
    daily=[]
    sums={name:{"races":0,"hits":0,"stakes_yen":0,"payout_yen":0,
                "head_covered":0,"head_count_sum":0,"K_marker_present":0,
                "misses":Counter()} for name in NAMES}
    for day in sorted(days):
        b,bmeta=decode_report(archive_path(root,"B",day))
        frozen,freeze_sha=freeze_B(b,day)
        # NEVER open K until the program-only tickets have been frozen.
        k,kmeta=decode_report(archive_path(root,"K",day))
        stats=score_day(frozen,b,k,day)
        daily.append({"date":str(day),"frozen_B_races":len(frozen),
                      "B_archive_sha256":bmeta["archive_sha256"],
                      "K_archive_sha256":kmeta["archive_sha256"],
                      "B_tickets_sha256":freeze_sha,"policies":stats})
        for name,values in stats.items():
            for field in ("races","hits","stakes_yen","payout_yen","head_covered",
                          "head_count_sum","K_marker_present"):
                sums[name][field]+=values[field]
            sums[name]["misses"].update(values["misses"])
    for name,v in sums.items():
        v["misses"]={reason:v["misses"][reason] for reason in MISS_REASONS}
        if sum(v["misses"].values())!=v["races"]:
            raise ValueError("nonexclusive aggregate errors")
        v["hypothetical_hit_rate"]=v["hits"]/v["races"] if v["races"] else None
        v["hypothetical_return_rate"]=v["payout_yen"]/v["stakes_yen"] if v["stakes_yen"] else None
        v["winner_head_coverage_rate"]=v["head_covered"]/v["races"] if v["races"] else None
        v["mean_distinct_heads"]=v["head_count_sum"]/v["races"] if v["races"] else None
    return {"mode":"B_ONLY_PAIR_PRESERVATION_HISTORICAL_NOT_FORWARD",
            "dates":[str(d) for d in sorted(days)],"tickets_per_race":8,
            "fixed_coefficients":True,"odds_used":False,
            "model_promoted":False,"forward_verified_races":0,
            "day_receipts":daily,"aggregate":sums,
            "warnings":["All B/K acquired retrospectively; no authentic preclose snapshot.",
                        "Six finishing entrants does not certify no incident.",
                        "K outcome text affects only scoring and postrace diagnostics.",
                        "No strategy adoption from this holdout without future independent verification."]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--dates",nargs=3,required=True)
    a=p.parse_args()
    print(json.dumps(run(a.root,[date.fromisoformat(s) for s in a.dates]),
                     ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
