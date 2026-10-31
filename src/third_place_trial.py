#!/usr/bin/env python3
"""No-leakage fixed eight-ticket third-place redundancy historical trial.

The B-only ticket set (and SHA256) is fixed before opening K. This is strictly
HISTORICAL_ONLY, not independently time-attested genuine Forward.
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
from quality_policy import k_observations
from third_place_redundancy import fixed_policies

MODELS = ("baseline_local_motor", "pair2_third3", "pair3_third2")


def freeze_b(text, day):
    if not text.startswith("STARTB"):
        raise ValueError("not B report")
    validate_report_date(text, day, "B")
    races, boats, issues = parse_program(text, day)
    invalid = {item[1] for item in issues
               if len(item) > 1 and isinstance(item[1], str)}
    frozen = {}
    for key in sorted(races):
        if key in invalid:
            continue
        try:
            frozen[key] = fixed_policies(boats[key])
        except (ValueError, TypeError, KeyError):
            continue
    canonical = json.dumps(frozen, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"))
    return frozen, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def score_day(frozen, b_text, k_text, day):
    if not k_text.startswith("STARTK"):
        raise ValueError("not K report")
    validate_report_date(k_text, day, "K")
    b = parse_program(b_text, day)
    k = parse_results(k_text, day)
    joined = reconcile(b, k)
    kflags = k_observations(k_text, day)
    outcome = k[2]
    accepted = sorted(set(joined["normal_race_keys"]) & set(frozen) & set(outcome))
    counts = {name: {"races": 0, "hits": 0, "stakes_yen": 0, "payout_yen": 0,
                     "head_covered": 0, "head_second_pair_covered": 0,
                     "K_positive_marker_races": 0, "misses": Counter()}
              for name in MODELS}
    for key in accepted:
        actual = outcome[key]["trifecta"]
        winner = actual.split("-")
        payout = int(outcome[key]["payout_yen_per_100"])
        marker = bool(kflags.get(key, {}).get("special_evidence") or
                      kflags.get(key, {}).get("incident_evidence"))
        for name in MODELS:
            tickets = frozen[key][name]
            why = classify_ticket_miss(tickets, actual)
            item = counts[name]
            item["races"] += 1
            item["stakes_yen"] += 800
            item["head_covered"] += int(any(t.split("-")[0] == winner[0] for t in tickets))
            item["head_second_pair_covered"] += int(any(t.split("-")[:2] == winner[:2]
                                                         for t in tickets))
            item["K_positive_marker_races"] += int(marker)
            item["misses"][why] += 1
            if why == "EXACT_HIT":
                item["hits"] += 1
                item["payout_yen"] += payout
    for name, item in counts.items():
        item["misses"] = {reason: item["misses"][reason] for reason in MISS_REASONS}
        if sum(item["misses"].values()) != item["races"]:
            raise ValueError("inconsistent diagnostics")
        item["hypothetical_hit_rate"] = item["hits"]/item["races"] if item["races"] else None
        item["hypothetical_return_rate"] = (item["payout_yen"]/item["stakes_yen"]
                                             if item["stakes_yen"] else None)
        item["head_coverage_rate"] = (item["head_covered"]/item["races"]
                                      if item["races"] else None)
        item["head_second_pair_coverage_rate"] = (
            item["head_second_pair_covered"]/item["races"] if item["races"] else None)
    return counts


def run(root, days):
    if len(days) != 3 or len(set(days)) != 3:
        raise ValueError("exactly three distinct dates")
    per_day = []
    aggregate = {name: {"races": 0, "hits": 0, "stakes_yen": 0,
                        "payout_yen": 0, "head_covered": 0,
                        "head_second_pair_covered": 0, "K_positive_marker_races": 0,
                        "misses": Counter()} for name in MODELS}
    for day in sorted(days):
        b_text, bmeta = decode_report(archive_path(root, "B", day))
        frozen, predicted_sha = freeze_b(b_text, day)
        # No access to any K before the B-only tickets and hash are frozen.
        k_text, kmeta = decode_report(archive_path(root, "K", day))
        scored = score_day(frozen, b_text, k_text, day)
        per_day.append({"date": str(day), "B_sha256": bmeta["archive_sha256"],
                        "K_sha256": kmeta["archive_sha256"],
                        "B_ticket_sha256": predicted_sha,
                        "B_frozen_races": len(frozen), "results": scored})
        for name, scored_policy in scored.items():
            sums = aggregate[name]
            for field in ("races", "hits", "stakes_yen", "payout_yen",
                          "head_covered", "head_second_pair_covered",
                          "K_positive_marker_races"):
                sums[field] += scored_policy[field]
            sums["misses"].update(scored_policy["misses"])
    for name, item in aggregate.items():
        item["misses"] = {reason: item["misses"][reason] for reason in MISS_REASONS}
        if sum(item["misses"].values()) != item["races"]:
            raise ValueError("aggregate population mismatch")
        item["hypothetical_hit_rate"] = item["hits"]/item["races"] if item["races"] else None
        item["hypothetical_return_rate"] = (item["payout_yen"]/item["stakes_yen"]
                                             if item["stakes_yen"] else None)
        item["head_coverage_rate"] = (item["head_covered"]/item["races"]
                                      if item["races"] else None)
        item["head_second_pair_coverage_rate"] = (
            item["head_second_pair_covered"]/item["races"] if item["races"] else None)
    return {"mode": "B_ONLY_THIRD_REDUNDANCY_HISTORICAL_NOT_FORWARD",
            "dates": [str(d) for d in sorted(days)],
            "ticket_count": 8, "base_coefficients_unchanged": True,
            "model_promotion": False, "forward_verified_races": 0,
            "per_day": per_day, "aggregate": aggregate,
            "warnings": [
                "Official historical B archives retrieved postrace are not authentic predeadline frozen sources.",
                "No odds, popularity or K result/payout influenced B-only ticket selection.",
                "Six finishers and no positive K keywords do not certify an incident-free race.",
                "Only a new independent cohort can validate a selected model."
            ]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True, type=Path)
    p.add_argument("--dates", nargs=3, required=True)
    args = p.parse_args()
    print(json.dumps(run(args.root, [date.fromisoformat(d) for d in args.dates]),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
