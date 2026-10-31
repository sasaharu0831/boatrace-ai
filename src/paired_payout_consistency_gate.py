#!/usr/bin/env python3
"""Offline independent verification of paired postrace payout attribution.

Checks official digest receipts and all four ticket-outcome categories against
the already archived B-only prediction/venue-stage audit. Payout categories are
never used to select or retune any ticket. This gate cannot promote production.
"""
from __future__ import annotations

from datetime import date
import math
import re

HEX64 = re.compile(r"^[0-9a-f]{64}$")
STATUS=("both_hit","baseline_only","calibrated_only","neither_hit")


def verify(report, original):
    if report.get("mode")!="HISTORICAL_POSTRACE_EXPLANATION_NOT_FORWARD":
        raise ValueError("not a strictly retrospective payout report")
    if (report.get("forward_verified_races")!=0 or
        report.get("production_model_promoted") is not False or
        report.get("automatic_subgroup_router_enabled") is not False or
        report.get("no_odds_popularity_or_payout_in_preclose_selection") is not True):
        raise ValueError("postrace payouts never authorize preclose routing")
    if report.get("tickets_per_race")!=8 or report.get("assumed_stake_per_ticket_yen")!=100:
        raise ValueError("wrong eight-ticket historical stake")
    if not HEX64.fullmatch(report.get("trained_parameters_sha256","")):
        raise ValueError("bad trained SHA256")
    if report["trained_parameters_sha256"]!=original["fit_sha256"]:
        raise ValueError("trained fit provenance mismatch")
    if report.get("status_partition")!=list(STATUS):
        raise ValueError("changed exhaustive outcome categories")
    cohorts=report.get("cohorts",[])
    previous=original.get("cohorts",[])
    if len(cohorts)!=2 or len(previous)!=2:
        raise ValueError("exactly two historical comparison cohorts required")
    all_days=[]
    summary=[]
    for cohort, prior in zip(cohorts,previous):
        if cohort["dates"]!=prior["dates"] or len(cohort["dates"])!=3:
            raise ValueError("date cohort mismatch")
        if len(cohort["source_sha_and_frozen_ticket_sha"])!=3:
            raise ValueError("missing original source receipts")
        for curr, old in zip(cohort["source_sha_and_frozen_ticket_sha"],
                             prior["source_receipts"]):
            date.fromisoformat(curr["day"])
            all_days.append(curr["day"])
            if curr["day"]!=old["day"]:
                raise ValueError("B/K day mismatch")
            for key,previous_key in (("B_sha256","B_sha256"),
                                     ("K_sha256","K_sha256"),
                                     ("frozen_predictions_sha256","frozen_120way_SHA256")):
                if not HEX64.fullmatch(curr.get(key,"")):
                    raise ValueError("B/K or pre-K prediction SHA256 invalid")
                if curr[key]!=old[previous_key]:
                    raise ValueError("B/K or B-only frozen prediction SHA256 mismatch")
        current=cohort["groups"]
        original_groups=prior["groups"]
        if set(current)!=set(original_groups):
            raise ValueError("different original venue/stage/K partition keys")
        for key,values in current.items():
            old=original_groups[key]
            n=values["races"]
            if n!=old["n"] or values["stakes_yen"]!=800*n:
                raise ValueError("cohort denominator mismatch")
            counts=values["outcome_counts"]
            payouts=values["outcome_payout_yen_per_100_sum"]
            if set(counts)!=set(STATUS) or set(payouts)!=set(STATUS) or sum(counts.values())!=n:
                raise ValueError("four-outcome mutually exclusive counts not preserved")
            for state in STATUS:
                if not isinstance(counts[state],int) or counts[state]<0:
                    raise ValueError("non-integer or negative outcome count")
                if not isinstance(payouts[state],int) or payouts[state]<0:
                    raise ValueError("non-integer or negative actual K payout")
                if counts[state]==0 and payouts[state]!=0:
                    raise ValueError("nonempty payout on empty outcome set")
            base_hits=counts["both_hit"]+counts["baseline_only"]
            cal_hits=counts["both_hit"]+counts["calibrated_only"]
            base_yen=payouts["both_hit"]+payouts["baseline_only"]
            cal_yen=payouts["both_hit"]+payouts["calibrated_only"]
            for model,hits,paid in (("baseline",base_hits,base_yen),
                                    ("calibrated",cal_hits,cal_yen)):
                if old[model]["hits"]!=hits or old[model]["payout_yen"]!=paid:
                    raise ValueError("forensic payout fails independent earlier audit")
            if (values["baseline_hits"]!=base_hits or
                values["calibrated_hits"]!=cal_hits or
                values["baseline_hypothetical_paid_yen"]!=base_yen or
                values["calibrated_hypothetical_paid_yen"]!=cal_yen or
                values["hit_delta"]!=cal_hits-base_hits or
                values["payout_delta_yen"]!=cal_yen-base_yen or
                values["gain_only_paid_yen"]!=payouts["calibrated_only"] or
                values["lost_only_paid_yen"]!=payouts["baseline_only"]):
                raise ValueError("paired K-only payout decomposition inconsistent")
        overall=current["overall"]
        for dimension in ("venue:","stage:","K_marker:"):
            groups=[x for k,x in current.items() if k.startswith(dimension)]
            for field in ("races","baseline_hits","calibrated_hits",
                          "baseline_hypothetical_paid_yen",
                          "calibrated_hypothetical_paid_yen",
                          "payout_delta_yen","hit_delta"):
                if sum(x[field] for x in groups)!=overall[field]:
                    raise ValueError("forensic venue/stage/K partition fails to reconcile")
        summary.append({
            "dates":cohort["dates"],
            "races":overall["races"],
            "gain_only_hits":overall["gain_only_hits"],
            "lost_only_hits":overall["lost_only_hits"],
            "gain_only_paid_yen":overall["gain_only_paid_yen"],
            "lost_only_paid_yen":overall["lost_only_paid_yen"],
            "net_hits":overall["hit_delta"],
            "net_hypothetical_paid_yen":overall["payout_delta_yen"],
        })
    if len(set(all_days))!=6 or max(cohorts[0]["dates"])>=min(cohorts[1]["dates"]):
        raise ValueError("overlapping or reversed historical dates")
    return {
        "mode":"HISTORICAL_PAYOUT_CAUSAL_ARITHMETIC_CHECK_ONLY",
        "cohorts":summary,
        "official_and_prior_prediction_digests_match":True,
        "four_outcome_categories_exhaustive":True,
        "research_only":True,
        "production_eligible":False,
        "forward_verified_races":0,
        "remark":"Arithmetically attributes retrospective changes; does not prove an economic or causal advantage."
    }
