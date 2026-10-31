#!/usr/bin/env python3
"""Historical two-cohort eight-ticket guarded-frozen-model gate; no production.

Requires identical train SHA, nonoverlapping later holdouts, 8 tickets each,
same scored races, full 120-way frozen SHA receipts and baseline head/pair
support. Candidate must improve both hits AND retrospective payout over the
frozen calibrated model in EACH cohort. An historical pass is NOT a live
Forward pass or evidence of positive profit.
"""
from __future__ import annotations
from datetime import date
import math
import re

MODELS=("baseline_local_motor","frozen_temperature",
        "frozen_head_support","frozen_pair_support")
SHA=re.compile(r"^[0-9a-f]{64}$")


def evaluate(record):
    if record.get("mode")!="B_ONLY_FROZEN_HEAD_GUARD_TWO_COHORT_HISTORICAL":
        raise ValueError("wrong audit type")
    if record.get("forward_verified_races")!=0 or record.get("production_promoted") is not False:
        raise ValueError("no authentic preclose Forward evidence")
    if record.get("tickets_per_race")!=8:
        raise ValueError("not eight tickets per race")
    if not SHA.fullmatch(record.get("trained_parameters_sha256","")):
        raise ValueError("frozen training SHA256 absent")
    parts=record.get("cohorts",[])
    if len(parts)!=2:
        raise ValueError("two independent test cohorts required")
    all_dates=[]
    comparisons={name:[] for name in MODELS[2:]}
    for cohort in parts:
        days=cohort["daily_receipts"]
        if len(days)!=3 or [x["day"] for x in days]!=cohort["test_dates"]:
            raise ValueError("three verified daily frozen receipts required")
        for row in days:
            date.fromisoformat(row["day"])
            all_dates.append(row["day"])
            for field in ("B_sha256","K_sha256","frozen_predictions_sha256"):
                if not isinstance(row.get(field),str) or not SHA.fullmatch(row[field]):
                    raise ValueError("invalid B/K/prediction SHA256")
        data=cohort["results"]
        if set(data)!=set(MODELS):
            raise ValueError("incomplete four-policy comparison")
        n=data["frozen_temperature"]["races"]
        if not isinstance(n,int) or n<100 or sum(x["evaluated"] for x in days)!=n:
            raise ValueError("test cohort population wrong")
        baseline=data["baseline_local_motor"]
        frozen=data["frozen_temperature"]
        for name in MODELS:
            row=data[name]
            if row["races"]!=n or row["stakes_yen"]!=800*n:
                raise ValueError("different 8-ticket stakes or population")
            if not isinstance(row["hits"],int) or not 0<=row["hits"]<=n:
                raise ValueError("invalid hit count")
            if not isinstance(row["payout_yen"],int) or row["payout_yen"]<0:
                raise ValueError("invalid payout")
            if row["miss_reasons"]["EXACT_HIT"]!=row["hits"] or sum(row["miss_reasons"].values())!=n:
                raise ValueError("not mutually exclusive miss classification")
            if (row["gained_hits_vs_frozen"]-row["lost_hits_vs_frozen"]
                    !=row["hits"]-frozen["hits"]):
                raise ValueError("hit transition counts do not reconcile")
            if row["K_positive_markers"]!=baseline["K_positive_markers"]:
                raise ValueError("K marker denominator mismatch")
        for name in MODELS[2:]:
            row=data[name]
            if row["heads_covered"]!=baseline["heads_covered"]:
                raise ValueError("first-place support changed")
            if name=="frozen_pair_support" and row["pairs_covered"]!=baseline["pairs_covered"]:
                raise ValueError("first-second pair support changed")
            hit_delta=row["hits"]-frozen["hits"]
            payout_delta=row["payout_yen"]-frozen["payout_yen"]
            comparisons[name].append({
                "dates":cohort["test_dates"],"races":n,
                "hit_delta_vs_frozen":hit_delta,"payout_delta_vs_frozen_yen":payout_delta,
                "return_delta_percentage_points":100*payout_delta/(800*n),
                "pass_both":hit_delta>0 and payout_delta>0
            })
        probs=cohort["probability_scores"]
        for key in ("baseline","calibrated"):
            for metric in ("average_logloss","average_brier_120"):
                if not math.isfinite(probs[key][metric]):
                    raise ValueError("invalid proper probability score")
    if len(set(all_dates))!=6 or max(parts[0]["test_dates"])>=min(parts[1]["test_dates"]):
        raise ValueError("overlapping or unordered holdouts")
    result={name:{"cohorts":rows,
                  "historical_replicated":all(x["pass_both"] for x in rows)}
            for name,rows in comparisons.items()}
    return {
        "type":"FROZEN_TEMPERATURE_GUARDS_HISTORICAL_REPLICATION",
        "models":result,
        "forward_verified_races":0,
        "production_eligible":False,
        "note":"Only historical nonpreclose research; improvement is relative to frozen calibration, not proof of profit."
    }
