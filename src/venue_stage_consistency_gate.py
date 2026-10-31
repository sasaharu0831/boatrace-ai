#!/usr/bin/env python3
"""Integrity and descriptive-only two-cohort checks for venue/stage audits.

This NEVER selects, fits, promotes, or deploys a model per venue or stage.
Multiple testing means even two seemingly favorable historical subgroups
are NOT proof of a real advantage. Original B/K bytes are not available here;
a 64-hex receipt is a format check, not independent source verification.
"""
from __future__ import annotations
from datetime import date
import math
import re

HEX64=re.compile(r"^[0-9a-f]{64}$")
DIMENSIONS=("venue:","stage:","K_marker:")
MODELS=("baseline","calibrated")


def evaluate(report):
    if report.get("mode")!="HISTORICAL_B_ONLY_VENUE_STAGE_TWO_COHORT_DIAGNOSTIC_NOT_FORWARD":
        raise ValueError("unsupported subgroup evidence")
    if report.get("forward_verified_races") != 0 or (
        report.get("production_model_changed") is not False or
        report.get("subgroup_router_enabled") is not False):
        raise ValueError("postrace subgroup evidence must never enable production")
    if not HEX64.fullmatch(report.get("fit_sha256","")):
        raise ValueError("missing frozen temperature model digest")
    cohorts=report.get("cohorts",[])
    if len(cohorts)!=2:
        raise ValueError("two disjoint historical cohorts required")
    unique_days=[]
    summaries=[]
    for cohort in cohorts:
        dates=cohort["dates"]
        receipts=cohort["source_receipts"]
        groups=cohort["groups"]
        if len(dates)!=3 or [r["day"] for r in receipts]!=dates:
            raise ValueError("three matching B/K/frozen receipts required")
        for day, row in zip(dates,receipts):
            date.fromisoformat(day)
            unique_days.append(day)
            for field in ("B_sha256","K_sha256","frozen_120way_SHA256"):
                if not HEX64.fullmatch(row.get(field,"")):
                    raise ValueError("missing source SHA256 format")
        overall=groups["overall"]
        if overall["n"]!=sum(x["historical_scored"] for x in receipts):
            raise ValueError("daily population mismatch")
        if overall["n"]<100:
            raise ValueError("cohort too small")
        for key, group in groups.items():
            n=group["n"]
            if n<1 or group["sufficient_for_descriptive_comparison"]!=(n>=30):
                raise ValueError("incorrect exploratory sample-size gate")
            for model in MODELS:
                r=group[model]
                if r["races"]!=n or r["stakes_yen"]!=800*n:
                    raise ValueError("subgroup models have different denominators")
                if sum(r["misses"].values())!=n or r["misses"]["EXACT_HIT"]!=r["hits"]:
                    raise ValueError("invalid exclusive miss partition")
                if not math.isclose(r["mean_logloss"]*n,r["logloss_sum"],rel_tol=0,abs_tol=1e-7):
                    raise ValueError("logloss mean is inconsistent")
                if not math.isclose(r["mean_brier_120"]*n,r["brier_sum"],rel_tol=0,abs_tol=1e-7):
                    raise ValueError("brier mean is inconsistent")
        for prefix in DIMENSIONS:
            selection=[v for k,v in groups.items() if k.startswith(prefix)]
            if sum(x["n"] for x in selection)!=overall["n"]:
                raise ValueError("subgroup race count doesn't reconcile")
            for model in MODELS:
                for metric in ("hits","payout_yen","races"):
                    measured=sum(s[model][metric] for s in selection)
                    if measured!=overall[model][metric]:
                        raise ValueError("subgroup totals don't reconcile")
        summaries.append({
            "dates": dates, "races": overall["n"],
            "hit_delta": overall["calibrated"]["hits"]-overall["baseline"]["hits"],
            "payout_yen_delta": overall["calibrated"]["payout_yen"]-overall["baseline"]["payout_yen"],
            "mean_logloss_delta": overall["delta_avg_logloss"],
            "mean_brier_delta": overall["delta_avg_brier"],
        })
    if len(set(unique_days))!=6 or max(cohorts[0]["dates"])>=min(cohorts[1]["dates"]):
        raise ValueError("overlapping historical test dates")
    venue_names=set.intersection(*[
        {k for k,v in c["groups"].items()
         if k.startswith("venue:") and v["n"]>=30}
        for c in cohorts
    ])
    stage_names=set.intersection(*[
        {k for k,v in c["groups"].items()
         if k.startswith("stage:") and v["n"]>=30}
        for c in cohorts
    ])
    return {
        "kind":"VENUE_STAGE_TWO_HISTORICAL_COHORTS_DESCRIPTIVE_ONLY",
        "cohort_summaries":summaries,
        "sufficiently_populated_venue_groups_in_both":sorted(venue_names),
        "sufficiently_populated_B_stage_groups_in_both":sorted(stage_names),
        "subgroup_model_router_authorized":False,
        "production_eligible":False,
        "forward_verified_races":0,
        "limitations":[
            ">=30 per cohort is merely an exploratory reporting threshold, not statistical significance.",
            "Stage/venue lists are selected AFTER seeing historical outcomes (multiple comparisons).",
            "Any future proposed router needs predeclared separate data and genuine Forward verification.",
            "Original source contents not retained; SHA256 receipt format alone cannot prove origin.",
        ]
    }
