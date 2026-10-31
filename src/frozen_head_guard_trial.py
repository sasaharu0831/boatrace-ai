#!/usr/bin/env python3
"""Immutable August-trained 8-ticket head/pair guards; historical validation only.

The August 10-12 fitted temperatures are independently SHA256 checked. TEST B
alone determines all 120 scores and four sets of 8 tickets; these are frozen
BEFORE accessing TEST K. K results and payouts are outcome-only, never inputs
to model selection or fitting. Nothing is presented as genuine preclose Forward.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path
from archive_backfill import archive_path
from frozen_head_guard import NAMES,fixed_predictions,pair
from historical_records import parse_program,parse_results,reconcile
from historical_sqlite import validate_report_date
from holdout_analysis import classify_ticket_miss,MISS_REASONS
from lzh_extract import decode_report
from quality_policy import k_observations
from role_temperature_calibration import freeze_digest,score_distribution,distribution,ROLES
from role_temperature_retest import checked_training_fit

BASE_TEMP={role:1.0 for role in ROLES}


def freeze_b(b_text,day,temperatures):
    if not b_text.startswith("STARTB"):
        raise ValueError("expected B program report")
    validate_report_date(b_text,day,"B")
    races,boats,issues=parse_program(b_text,day)
    bad={i[1] for i in issues if len(i)>1 and isinstance(i[1],str)}
    snapshot={}
    for key in sorted(races):
        if key in bad:
            continue
        try:
            picks,role_prob=fixed_predictions(boats[key],temperatures)
            baseline_prob=distribution(boats[key],BASE_TEMP)
        except (ValueError,TypeError,OverflowError,KeyError):
            continue
        snapshot[key]={"picks":picks,"baseline_prob":baseline_prob,"frozen_prob":role_prob}
    if not snapshot:
        raise ValueError("no valid B-only forecasts")
    return snapshot,freeze_digest(snapshot)


def stats_zero():
    return {"races":0,"hits":0,"stakes_yen":0,"payout_yen":0,
            "heads_covered":0,"pairs_covered":0,"changed_tickets":0,
            "gained_hits_vs_frozen":0,"lost_hits_vs_frozen":0,
            "K_positive_markers":0,"miss_reasons":Counter()}


def stats_end(x):
    y=dict(x)
    y["miss_reasons"]={k:x["miss_reasons"][k] for k in MISS_REASONS}
    n=y["races"]
    if sum(y["miss_reasons"].values())!=n or y["miss_reasons"]["EXACT_HIT"]!=y["hits"]:
        raise ValueError("miss classification/population mismatch")
    y["hypothetical_hit_rate"]=y["hits"]/n if n else None
    y["hypothetical_return_rate"]=y["payout_yen"]/y["stakes_yen"] if n else None
    y["head_coverage_rate"]=y["heads_covered"]/n if n else None
    y["pair_coverage_rate"]=y["pairs_covered"]/n if n else None
    return y


def score(frozen,b_text,k_text,day):
    if not k_text.startswith("STARTK"):
        raise ValueError("expected K outcome report")
    validate_report_date(k_text,day,"K")
    k=parse_results(k_text,day)
    good=set(reconcile(parse_program(b_text,day),k)["normal_race_keys"])
    outcomes=k[2]
    markers=k_observations(k_text,day)
    metrics={name:stats_zero() for name in NAMES}
    nll={"baseline":0.0,"calibrated":0.0}
    brier={"baseline":0.0,"calibrated":0.0}
    for key in sorted(good & set(frozen) & set(outcomes)):
        actual=outcomes[key]["trifecta"]
        actualparts=actual.split("-")
        payout=int(outcomes[key]["payout_yen_per_100"])
        positive=bool(markers.get(key,{}).get("incident_evidence") or
                      markers.get(key,{}).get("special_evidence"))
        data=frozen[key]
        picks=data["picks"]
        baseline=picks["baseline_local_motor"]
        raw_cal=picks["frozen_temperature"]
        for label,probabilities in (
            ("baseline",data["baseline_prob"]),
            ("calibrated",data["frozen_prob"]),
        ):
            losses=score_distribution(probabilities,actual)
            nll[label]+=losses["negative_log_likelihood"]
            brier[label]+=losses["brier_120"]
        baseline_heads={x[0] for x in baseline}
        baseline_pairs={pair(x) for x in baseline}
        frozen_hit=actual in raw_cal
        for name in NAMES:
            selected=picks[name]
            if len(selected)!=8 or len(set(selected))!=8:
                raise ValueError("invalid 8 ticket frozen set")
            if name in ("frozen_head_support","frozen_pair_support") and {
                x[0] for x in selected} != baseline_heads:
                raise ValueError("baseline head support broken")
            if name=="frozen_pair_support" and {pair(x) for x in selected}!=baseline_pairs:
                raise ValueError("baseline pair support broken")
            row=metrics[name]
            hit=actual in selected
            row["races"]+=1
            row["hits"]+=int(hit)
            row["stakes_yen"]+=800
            row["payout_yen"]+=payout if hit else 0
            row["heads_covered"]+=int(actualparts[0] in {x[0] for x in selected})
            row["pairs_covered"]+=int(tuple(actualparts[:2]) in {pair(x) for x in selected})
            row["changed_tickets"]+=int(selected!=raw_cal)
            row["gained_hits_vs_frozen"]+=int(hit and not frozen_hit)
            row["lost_hits_vs_frozen"]+=int(not hit and frozen_hit)
            row["K_positive_markers"]+=int(positive)
            row["miss_reasons"][classify_ticket_miss(selected,actual)]+=1
    out={name:stats_end(x) for name,x in metrics.items()}
    n=out[NAMES[0]]["races"]
    if any(row["races"]!=n or row["stakes_yen"]!=800*n for row in out.values()):
        raise ValueError("candidate cohorts do not match")
    if any(out[name]["heads_covered"]!=out[NAMES[0]]["heads_covered"]
           for name in NAMES[2:]):
        raise ValueError("changed head coverage")
    if out["frozen_pair_support"]["pairs_covered"]!=out[NAMES[0]]["pairs_covered"]:
        raise ValueError("changed baseline pair coverage")
    return out, {"sum_nll":nll,"sum_brier":brier}


def run(root,fit_receipt,days):
    if len(days)!=3 or len(set(days))!=3:
        raise ValueError("exactly three unique dates")
    temps=checked_training_fit(fit_receipt,days)
    cumulative={name:stats_zero() for name in NAMES}
    nll={"baseline":0.0,"calibrated":0.0}
    brier={"baseline":0.0,"calibrated":0.0}
    day_receipts=[]
    for day in sorted(days):
        b,bmeta=decode_report(archive_path(root,"B",day))
        frozen,digest=freeze_b(b,day,temps)
        # No test K file is opened until the full B-only prediction snapshot is frozen.
        k,kmeta=decode_report(archive_path(root,"K",day))
        result,proper=score(frozen,b,k,day)
        day_receipts.append({
            "day":str(day),"B_sha256":bmeta["archive_sha256"],
            "K_sha256":kmeta["archive_sha256"],
            "frozen_predictions_sha256":digest,"B_races_frozen":len(frozen),
            "evaluated":result[NAMES[0]]["races"]})
        for name,row in result.items():
            target=cumulative[name]
            for field in ("races","hits","stakes_yen","payout_yen","heads_covered",
                          "pairs_covered","changed_tickets","gained_hits_vs_frozen",
                          "lost_hits_vs_frozen","K_positive_markers"):
                target[field]+=row[field]
            target["miss_reasons"].update(row["miss_reasons"])
        for name in ("baseline","calibrated"):
            nll[name]+=proper["sum_nll"][name]
            brier[name]+=proper["sum_brier"][name]
    final={name:stats_end(row) for name,row in cumulative.items()}
    n=final[NAMES[0]]["races"]
    if n<100:
        raise ValueError("insufficient historical evaluation races")
    proper={
        key:{"average_logloss":nll[key]/n,"average_brier_120":brier[key]/n}
        for key in ("baseline","calibrated")
    }
    return {"mode":"FROZEN_TRAINED_B_ONLY_HEAD_GUARD_HISTORICAL_NOT_FORWARD",
            "train_dates":fit_receipt["training_dates"],
            "frozen_trained_sha256":fit_receipt["trained_parameters_sha256"],
            "temperatures":temps,"test_dates":[str(d) for d in sorted(days)],
            "daily_receipts":day_receipts,"results":final,
            "probability_scores":proper,
            "probability_scores_for_guarded_picks":"same calibrated 120-way distribution; ticket subset changes only",
            "forward_verified_races":0,"production_promoted":False,
            "limitations":[
                "Historical B/K retrieved after races, NOT independently preclose Forward.",
                "No result/odds/payout fed to B-only prediction or trained frozen weights.",
                "K marker absence or six finishers does not prove incident-free.",
                "Proper scoring rules measure probability distribution; guards only reorder eight-ticket subset."
            ]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",required=True,type=Path)
    p.add_argument("--fit-receipt",required=True,type=Path)
    p.add_argument("--test",required=True,nargs=3)
    a=p.parse_args()
    fit=json.loads(a.fit_receipt.read_text(encoding="utf-8"))
    print(json.dumps(run(a.root,fit,[date.fromisoformat(x) for x in a.test]),ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
