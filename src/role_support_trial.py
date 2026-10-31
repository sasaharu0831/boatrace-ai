#!/usr/bin/env python3
"""Disjoint historical B-only trial of role-second ranking with head/pair guards.

The unchanged B-only local_motor baseline and both research candidates use
eight tickets. All B predictions and their digest are frozen before opening
any K result archive. K is used for scoring only. NOT true Forward.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
from pathlib import Path

from archive_backfill import archive_path
from historical_records import parse_program, parse_results, reconcile
from historical_sqlite import validate_report_date
from holdout_analysis import classify_ticket_miss, MISS_REASONS
from lzh_extract import decode_report
from quality_policy import k_observations, stage_from_title
from role_support_candidates import MODELS, _pair, fixed_policies


def freeze_b(text, day):
    if not text.startswith("STARTB"):
        raise ValueError("not an official B report")
    validate_report_date(text, day, "B")
    races, entry, issues = parse_program(text, day)
    invalid = {issue[1] for issue in issues
               if len(issue)>1 and isinstance(issue[1],str)}
    frozen, stages = {}, {}
    for key in sorted(races):
        if key in invalid:
            continue
        try:
            tickets = fixed_policies(entry[key])
        except (ValueError, TypeError, KeyError):
            continue
        frozen[key] = tickets
        stages[key] = stage_from_title(races[key]["race_name"])
    if not frozen:
        raise ValueError("no B-only predictions")
    content = json.dumps(frozen, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"))
    return frozen, stages, hashlib.sha256(content.encode("utf-8")).hexdigest()


def blank():
    return {"races":0, "hits":0, "stakes_yen":0, "payout_yen":0,
            "head_covered":0, "pair_covered":0, "K_marker_present":0,
            "tickets_changed":0, "gain_hit_only":0, "lost_hit_only":0,
            "misses":Counter(),
            "by_stage":defaultdict(lambda:{"races":0,"hits":0})}


def finish(x):
    y = {k:v for k,v in x.items() if k not in ("misses","by_stage")}
    y["misses"] = {name:x["misses"][name] for name in MISS_REASONS}
    y["by_stage"] = {k:dict(v) for k,v in sorted(x["by_stage"].items())}
    if sum(y["misses"].values())!=y["races"] or y["misses"]["EXACT_HIT"]!=y["hits"]:
        raise ValueError("inconsistent exclusive hit/miss accounting")
    y["hypothetical_hit_rate"] = y["hits"]/y["races"] if y["races"] else None
    y["hypothetical_return_rate"] = y["payout_yen"]/y["stakes_yen"] if y["stakes_yen"] else None
    y["head_coverage_rate"] = y["head_covered"]/y["races"] if y["races"] else None
    y["pair_coverage_rate"] = y["pair_covered"]/y["races"] if y["races"] else None
    return y


def score_day(frozen, stages, b_text, k_text, day):
    if not k_text.startswith("STARTK"):
        raise ValueError("not an official K report")
    validate_report_date(k_text, day, "K")
    k = parse_results(k_text, day)
    good = set(reconcile(parse_program(b_text, day), k)["normal_race_keys"])
    outcomes = k[2]
    flags = k_observations(k_text,day)
    metrics = {name: blank() for name in MODELS}
    accepted = sorted(good & frozen.keys() & outcomes.keys())
    for key in accepted:
        actual = outcomes[key]["trifecta"]
        head, second, third = actual.split("-")
        payout = int(outcomes[key]["payout_yen_per_100"])
        marker = bool(flags.get(key,{}).get("special_evidence")
                      or flags.get(key,{}).get("incident_evidence"))
        base = frozen[key]["baseline_local_motor"]
        baseline_hit = actual in base
        base_heads={ticket[0] for ticket in base}
        base_pairs={_pair(ticket) for ticket in base}
        for name in MODELS:
            tickets = frozen[key][name]
            if len(tickets)!=8 or len(set(tickets))!=8:
                raise ValueError("not eight distinct tickets")
            if {t[0] for t in tickets}!=base_heads:
                raise ValueError("changed baseline head support")
            if name=="pair_support_role_second" and {_pair(t) for t in tickets}!=base_pairs:
                raise ValueError("changed baseline ordered pair support")
            m=metrics[name]
            reason=classify_ticket_miss(tickets,actual)
            hit=reason=="EXACT_HIT"
            m["races"]+=1
            m["hits"]+=int(hit)
            m["stakes_yen"]+=800
            m["payout_yen"]+=payout if hit else 0
            m["head_covered"]+=int(head in {t[0] for t in tickets})
            m["pair_covered"]+=int((head,second) in {_pair(t) for t in tickets})
            m["K_marker_present"]+=int(marker)
            m["tickets_changed"]+=int(tickets!=base)
            m["gain_hit_only"]+=int(hit and not baseline_hit)
            m["lost_hit_only"]+=int(baseline_hit and not hit)
            m["misses"][reason]+=1
            row=m["by_stage"][stages[key]]
            row["races"]+=1
            row["hits"]+=int(hit)
    result = {p:finish(values) for p,values in metrics.items()}
    if any(x["races"]!=len(accepted) for x in result.values()):
        raise ValueError("policy populations differ")
    if any(x["head_covered"]!=result["baseline_local_motor"]["head_covered"]
           for x in result.values()):
        raise ValueError("head coverage not invariant")
    if result["pair_support_role_second"]["pair_covered"]!=result["baseline_local_motor"]["pair_covered"]:
        raise ValueError("pair coverage not invariant")
    return result


def run(root:Path, days:list[date]):
    if len(days)!=3 or len(set(days))!=3:
        raise ValueError("three unique historical days required")
    totals={p:blank() for p in MODELS}
    receipts=[]
    for day in sorted(days):
        b,meta_b=decode_report(archive_path(root,"B",day))
        frozen,stages,frozen_sha=freeze_b(b,day)
        # K cannot be accessed before B-only predictions are frozen.
        k,meta_k=decode_report(archive_path(root,"K",day))
        trial=score_day(frozen,stages,b,k,day)
        receipts.append({"day":str(day),"B_sha256":meta_b["archive_sha256"],
                         "K_sha256":meta_k["archive_sha256"],
                         "tickets_sha256":frozen_sha,
                         "B_frozen":len(frozen),"evaluated":trial[MODELS[0]]["races"]})
        for name,row in trial.items():
            x=totals[name]
            for field in ("races","hits","stakes_yen","payout_yen","head_covered",
                          "pair_covered","K_marker_present","tickets_changed",
                          "gain_hit_only","lost_hit_only"):
                x[field]+=row[field]
            x["misses"].update(row["misses"])
            for stage,agg in row["by_stage"].items():
                x["by_stage"][stage]["races"]+=agg["races"]
                x["by_stage"][stage]["hits"]+=agg["hits"]
    result={name:finish(x) for name,x in totals.items()}
    if any(x["races"]!=result[MODELS[0]]["races"] for x in result.values()):
        raise ValueError("unequal evaluation populations")
    return {"mode":"B_ONLY_SECOND_ROLE_SUPPORT_GUARDS_HISTORICAL_NOT_FORWARD",
            "dates":[str(day) for day in sorted(days)],
            "cohort_receipts":receipts,"aggregate":result,
            "tickets_per_race":8,"fixed_untrained_coefficients":True,
            "outcomes_used_for_ticket_selection":False,
            "forward_verified_races":0,"production_promoted":False,
            "caveats":["Official B/K files obtained postrace: not true Forward.",
                       "Six-finisher joins and missing K markers do not certify accident-free status.",
                       "Uncalibrated conditional scores are hypotheses and do not establish expected profit.",
                       "No postrace results, odds or payouts used to select tickets."]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--dates",nargs=3,required=True)
    a=p.parse_args()
    print(json.dumps(run(a.root,[date.fromisoformat(x) for x in a.dates]),ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
