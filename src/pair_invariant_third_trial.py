#!/usr/bin/env python3
"""Read B before K for a historical (NOT Forward) invariant-pair 8-ticket trial.

Never claims accident-free status based on normal finishers or missing keywords.
Payout belongs exclusively to K-after-B scoring; no odds or K result enters picks.
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
from pair_invariant_third_candidate import fixed_policies, pair_from_ticket
from quality_policy import k_observations

MODELS = ("baseline_local_motor", "keep_pairs_top1_third3", "keep_pairs_top2_third2")


def freeze_program(b_text: str, day: date):
    if not b_text.startswith("STARTB"):
        raise ValueError("invalid B archive marker")
    validate_report_date(b_text, day, "B")
    races, entry, issues = parse_program(b_text, day)
    bad = {problem[1] for problem in issues if len(problem) > 1
           and isinstance(problem[1], str)}
    picks = {}
    for key in sorted(races):
        if key in bad:
            continue
        try:
            group = fixed_policies(entry[key])
            support = {pair_from_ticket(t) for t in group["baseline_local_motor"]}
            if any({pair_from_ticket(t) for t in ts} != support for ts in group.values()):
                raise ValueError("B-only pair support broken")
            picks[key] = group
        except (KeyError, ValueError, TypeError):
            continue
    payload = json.dumps(picks, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    return picks, hashlib.sha256(payload).hexdigest()


def empty():
    return {"races": 0, "hits": 0, "stakes_yen": 0, "payout_yen": 0,
            "head_covered": 0, "head_second_pair_covered": 0,
            "K_marker_positive": 0, "changed_races": 0,
            "miss_reasons": Counter()}


def finish(values):
    result = dict(values)
    result["miss_reasons"] = {key: values["miss_reasons"][key] for key in MISS_REASONS}
    if sum(result["miss_reasons"].values()) != result["races"]:
        raise ValueError("misses do not sum to race count")
    result["hypothetical_hit_rate"] = (
        result["hits"] / result["races"] if result["races"] else None)
    result["hypothetical_return_rate"] = (
        result["payout_yen"] / result["stakes_yen"] if result["stakes_yen"] else None)
    result["head_coverage_rate"] = (
        result["head_covered"] / result["races"] if result["races"] else None)
    result["pair_coverage_rate"] = (
        result["head_second_pair_covered"] / result["races"] if result["races"] else None)
    return result


def score(frozen: dict, b_text: str, k_text: str, day: date):
    if not k_text.startswith("STARTK"):
        raise ValueError("invalid K archive marker")
    validate_report_date(k_text, day, "K")
    results = parse_results(k_text, day)
    qualified = set(reconcile(parse_program(b_text, day), results)["normal_race_keys"])
    payouts = results[2]
    positive = k_observations(k_text, day)
    stats = {model: empty() for model in MODELS}
    for key in sorted(qualified & frozen.keys() & payouts.keys()):
        actual = payouts[key]["trifecta"]
        payout_yen = int(payouts[key]["payout_yen_per_100"])
        winner = actual.split("-")
        marked = bool(positive.get(key, {}).get("special_evidence")
                      or positive.get(key, {}).get("incident_evidence"))
        baseline = frozen[key]["baseline_local_motor"]
        for model in MODELS:
            tickets = frozen[key][model]
            if len(tickets) != 8 or len(set(tickets)) != 8:
                raise ValueError("invalid frozen ticket count")
            if {pair_from_ticket(t) for t in tickets} != {
                    pair_from_ticket(t) for t in baseline}:
                raise ValueError("candidate changed 1st-2nd pair set")
            group = stats[model]
            group["races"] += 1
            group["stakes_yen"] += 800
            group["head_covered"] += int(any(t[0] == winner[0] for t in tickets))
            group["head_second_pair_covered"] += int(
                any(t.split("-")[:2] == winner[:2] for t in tickets))
            group["K_marker_positive"] += int(marked)
            group["changed_races"] += int(tickets != baseline)
            reason = classify_ticket_miss(tickets, actual)
            group["miss_reasons"][reason] += 1
            if reason == "EXACT_HIT":
                group["hits"] += 1
                group["payout_yen"] += payout_yen
    return {k: finish(x) for k, x in stats.items()}


def run(root: Path, days: list[date]):
    if len(days) != 3 or len(set(days)) != 3:
        raise ValueError("exactly three distinct old dates required")
    daily = []
    totals = {p: empty() for p in MODELS}
    for day in sorted(days):
        b_text, bmeta = decode_report(archive_path(root, "B", day))
        picks, frozen_sha = freeze_program(b_text, day)
        # K is deliberately not opened until the B-only picks are frozen.
        k_text, kmeta = decode_report(archive_path(root, "K", day))
        metrics = score(picks, b_text, k_text, day)
        daily.append({"day": str(day),
                      "B_sha256": bmeta["archive_sha256"],
                      "K_sha256": kmeta["archive_sha256"],
                      "frozen_tickets_sha256": frozen_sha,
                      "B_races_frozen": len(picks),
                      "models": metrics})
        for model, row in metrics.items():
            target = totals[model]
            for k in ("races", "hits", "stakes_yen", "payout_yen",
                      "head_covered", "head_second_pair_covered",
                      "K_marker_positive", "changed_races"):
                target[k] += row[k]
            target["miss_reasons"].update(row["miss_reasons"])
    aggregate = {model: finish(values) for model, values in totals.items()}
    n = aggregate["baseline_local_motor"]["races"]
    if any(aggregate[m]["races"] != n for m in MODELS):
        raise ValueError("unequal denominators across policies")
    for model in MODELS[1:]:
        if (aggregate[model]["head_covered"] != aggregate["baseline_local_motor"]["head_covered"]
                or aggregate[model]["head_second_pair_covered"] !=
                aggregate["baseline_local_motor"]["head_second_pair_covered"]):
            raise ValueError("head or pair coverage changed despite invariant")
    return {
        "mode": "B_ONLY_INVARIANT_PAIR_THIRD_REALLOCATION_HISTORICAL_NOT_FORWARD",
        "dates": [str(d) for d in sorted(days)],
        "tickets_per_race": 8, "fixed_weights": True,
        "outcomes_or_odds_used_for_picks": False,
        "pair_support_identical_to_baseline": True,
        "daily": daily, "aggregate": aggregate,
        "forward_verified_races": 0, "production_promotion": False,
        "warnings": [
            "All B/K records were obtained after races; not true Forward.",
            "Normal six-finisher join is not sufficient to certify absence of incidents.",
            "LZH raw files are temporary and not durably archived by this job.",
            "Past payouts and odds never influence B-only ticket construction."
        ]
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True, type=Path)
    p.add_argument("--dates", required=True, nargs=3)
    args = p.parse_args()
    print(json.dumps(run(args.root, [date.fromisoformat(x) for x in args.dates]),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
