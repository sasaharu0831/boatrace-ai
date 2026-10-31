#!/usr/bin/env python3
"""B-only positional ranking on a disjoint historical holdout, never Forward.

A genuine timestamped preclose capture and independent freeze attestation
are unavailable. Do not make production or profitable wagering claims.
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
from holdout_analysis import MISS_REASONS, classify_ticket_miss
from lzh_extract import decode_report
from positional_conditional import POLICIES, frozen_policies
from quality_policy import k_observations, stage_from_title


def freeze_program(text, day):
    if not text.startswith("STARTB"):
        raise ValueError("not B program")
    validate_report_date(text, day, "B")
    races, entries, issues = parse_program(text, day)
    bad = {item[1] for item in issues if len(item)>1 and isinstance(item[1],str)}
    picks, stages = {}, {}
    for key in sorted(races):
        if key in bad:
            continue
        try:
            picks[key] = frozen_policies(entries[key])
            stages[key] = stage_from_title(races[key]["race_name"])
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
    if not picks:
        raise ValueError("no usable B-only program races")
    canonical = json.dumps(picks, sort_keys=True, ensure_ascii=False, separators=(",",":"))
    return picks, stages, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def score_day(picks, stages, b_text, k_text, day):
    if not k_text.startswith("STARTK"):
        raise ValueError("not K result")
    validate_report_date(k_text, day, "K")
    outcomes = parse_results(k_text, day)
    good = set(reconcile(parse_program(b_text, day), outcomes)["normal_race_keys"])
    payouts = outcomes[2]
    flags = k_observations(k_text, day)
    accepted = sorted(good & picks.keys() & payouts.keys())
    metrics = {name: {"races":0, "hits":0, "stakes_yen":0,
                      "payout_yen":0, "head_covered":0,"pair_covered":0,
                      "K_positive_marker":0, "misses":Counter(),
                      "by_stage":defaultdict(lambda: {"races":0,"hits":0})}
               for name in POLICIES}
    for key in accepted:
        actual = payouts[key]["trifecta"]
        payout = int(payouts[key]["payout_yen_per_100"])
        order = actual.split("-")
        marker = bool(flags.get(key,{}).get("special_evidence") or
                      flags.get(key,{}).get("incident_evidence"))
        for name in POLICIES:
            tickets = picks[key][name]
            reason = classify_ticket_miss(tickets, actual)
            m = metrics[name]
            m["races"] += 1
            m["stakes_yen"] += 800
            m["head_covered"] += int(any(x.split("-")[0] == order[0] for x in tickets))
            m["pair_covered"] += int(any(x.split("-")[:2] == order[:2] for x in tickets))
            m["K_positive_marker"] += int(marker)
            m["misses"][reason] += 1
            stage = m["by_stage"][stages[key]]
            stage["races"] += 1
            if reason == "EXACT_HIT":
                m["hits"] += 1
                m["payout_yen"] += payout
                stage["hits"] += 1
    for m in metrics.values():
        m["misses"] = {name:m["misses"][name] for name in MISS_REASONS}
        m["by_stage"] = dict(m["by_stage"])
        if sum(m["misses"].values()) != m["races"] or m["misses"]["EXACT_HIT"] != m["hits"]:
            raise ValueError("postrace miss category totals inconsistent")
    return metrics


def run(root: Path, dates: list[date]):
    if len(dates) != 3 or len(set(dates)) != 3:
        raise ValueError("exactly three disjoint historical dates")
    daily = []
    sums = {name: {"races":0, "hits":0,"stakes_yen":0,"payout_yen":0,
                   "head_covered":0,"pair_covered":0,"K_positive_marker":0,
                   "misses":Counter(),"by_stage":defaultdict(lambda:{"races":0,"hits":0})}
            for name in POLICIES}
    for day in sorted(dates):
        b_text, bmeta = decode_report(archive_path(root,"B",day))
        picks, stages, freeze_sha = freeze_program(b_text, day)
        # K is NOT even opened until B-only tickets and their SHA exist.
        k_text, kmeta = decode_report(archive_path(root,"K",day))
        metrics = score_day(picks, stages, b_text, k_text, day)
        daily.append({"day":str(day),"B_sha256":bmeta["archive_sha256"],
                      "K_sha256":kmeta["archive_sha256"],
                      "frozen_tickets_sha256":freeze_sha,
                      "B_frozen_races":len(picks),
                      "evaluated":metrics["baseline_local_motor"]["races"]})
        for name in POLICIES:
            r = metrics[name]
            t = sums[name]
            for col in ("races","hits","stakes_yen","payout_yen",
                        "head_covered","pair_covered","K_positive_marker"):
                t[col] += r[col]
            t["misses"].update(r["misses"])
            for stage, val in r["by_stage"].items():
                for col in ("races","hits"):
                    t["by_stage"][stage][col] += val[col]
    result = {}
    for name,t in sums.items():
        t["misses"] = {key:t["misses"][key] for key in MISS_REASONS}
        t["by_stage"] = dict(t["by_stage"])
        if sum(t["misses"].values()) != t["races"]:
            raise ValueError("aggregate diagnostics mismatch")
        t["hypothetical_hit_rate"] = t["hits"]/t["races"] if t["races"] else None
        t["hypothetical_return_rate"] = t["payout_yen"]/t["stakes_yen"] if t["stakes_yen"] else None
        t["head_coverage_rate"] = t["head_covered"]/t["races"] if t["races"] else None
        t["pair_coverage_rate"] = t["pair_covered"]/t["races"] if t["races"] else None
        result[name] = t
    if any(result[p]["races"] != result[POLICIES[0]]["races"] for p in POLICIES):
        raise ValueError("different evaluation denominators")
    return {"mode":"B_ONLY_POSITIONAL_CONDITIONAL_HISTORICAL_NOT_FORWARD",
            "dates":[str(d) for d in sorted(dates)],"daily":daily,"aggregate":result,
            "tickets_per_race":8,"fixed_coefficients":True,
            "odds_K_outcomes_used_for_ticket_selection":False,
            "forward_verified_races":0,"production_promoted":False,
            "limitations":["B/K obtained after race; not genuine preclose Forward.",
                           "K-positive and absent marker groups are NOT certified accident-free.",
                           "Positional coefficients are declared research hypotheses, not calibrated probabilities.",
                           "No historical selection licenses live production."]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--dates",nargs=3,required=True)
    args=p.parse_args()
    print(json.dumps(run(args.root,[date.fromisoformat(x) for x in args.dates]),
                     ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
