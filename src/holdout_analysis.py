#!/usr/bin/env python3
"""Independent historical holdout: frozen B-only ranking, then K-only scoring.

No fitted weights, no result-derived ticket selection. The default October
2026 evaluation dates are disjoint from the prior October 27-29 retrospective
trial. This is NOT independently time-attested live Forward prediction.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import date
import json
from pathlib import Path

from archive_backfill import archive_path
from historical_records import parse_program, parse_results, reconcile
from historical_sqlite import validate_report_date
from lzh_extract import decode_report
from quality_policy import k_observations
from shadow_baseline import POLICIES, TICKETS, freeze_b_only


def new_score():
    return {"races": 0, "hits": 0, "stakes_yen": 0, "payout_yen": 0}


def accumulate(target, ticket_set, actual, payout):
    target["races"] += 1
    target["stakes_yen"] += len(ticket_set) * 100
    if actual in ticket_set:
        target["hits"] += 1
        target["payout_yen"] += payout


def finish_score(score):
    result = dict(score)
    result["hypothetical_hit_rate"] = (
        score["hits"] / score["races"] if score["races"] else None)
    result["hypothetical_return_rate"] = (
        score["payout_yen"] / score["stakes_yen"] if score["stakes_yen"] else None)
    return result


def evaluate_day(b_text: str, k_text: str, day: date) -> dict:
    if not b_text.startswith("STARTB") or not k_text.startswith("STARTK"):
        raise ValueError("official B/K file marker mismatch")
    validate_report_date(b_text, day, "B")
    validate_report_date(k_text, day, "K")

    # Crucial ordering: freeze tickets from B only, with K not an input.
    frozen, stages, prediction_sha = freeze_b_only(b_text, day)
    b = parse_program(b_text, day)
    k = parse_results(k_text, day)
    joined = reconcile(b, k)
    flags = k_observations(k_text, day)
    _, _, payouts, _ = k
    accepted = sorted(set(joined["normal_race_keys"]) & set(frozen))
    # Paired finishers can still have unobserved operational/incident specials.
    grouped = {p: defaultdict(new_score) for p in POLICIES}
    positive_markers = set()
    for racekey in accepted:
        stage = stages[racekey]
        venue = racekey[8:10]
        k_marker = bool(flags.get(racekey, {}).get("special_evidence") or
                        flags.get(racekey, {}).get("incident_evidence"))
        group_marker = "K_MARKER_PRESENT" if k_marker else "NO_K_MARKER_UNVERIFIED"
        if k_marker:
            positive_markers.add(racekey)
        actual = payouts[racekey]["trifecta"]
        payout = int(payouts[racekey]["payout_yen_per_100"])
        for policy in POLICIES:
            tickets = frozen[racekey][policy]
            if len(tickets) != TICKETS:
                raise ValueError("ticket cardinality mismatch")
            for group in ("overall", f"venue:{venue}", f"stage:{stage}",
                          f"marker:{group_marker}", f"stage+marker:{stage}/{group_marker}"):
                accumulate(grouped[policy][group], tickets, actual, payout)

    totals = {p: {key: finish_score(value) for key, value in sorted(groups.items())}
              for p, groups in grouped.items()}
    n = len(accepted)
    if any(totals[p].get("overall", {}).get("races", 0) != n for p in POLICIES):
        raise ValueError("population mismatch across policies")
    return {
        "date": day.isoformat(), "B_ticket_sha256": prediction_sha,
        "B_races_frozen_before_K": len(frozen),
        "B_races": joined["B_races"], "K_races": joined["K_races"],
        "paired_races": joined["paired_races"],
        "historical_joined": n,
        "K_positive_marker_races_in_joined": len(positive_markers),
        "groups": totals,
        "forward_verified_races": 0
    }


def analyze_holdout(root: Path, days: list[date]) -> dict:
    if not 1 <= len(days) <= 3 or len(set(days)) != len(days):
        raise ValueError("1..3 unique historical days")
    day_reports = []
    combined = {p: defaultdict(new_score) for p in POLICIES}
    for day in sorted(days):
        # Read and validate B before any K archive is read.
        b_text, bmeta = decode_report(archive_path(root, "B", day))
        if not b_text.startswith("STARTB"):
            raise ValueError("not an official B report")
        validate_report_date(b_text, day, "B")
        frozen, stages, digest = freeze_b_only(b_text, day)
        # The frozen tickets were generated above before opening any K file.
        k_text, kmeta = decode_report(archive_path(root, "K", day))
        report = evaluate_day(b_text, k_text, day)
        if digest != report["B_ticket_sha256"]:
            raise ValueError("B-only prediction changed after K access")
        report["B_archive_sha256"] = bmeta["archive_sha256"]
        report["K_archive_sha256"] = kmeta["archive_sha256"]
        day_reports.append(report)
        for policy in POLICIES:
            for group, score in report["groups"][policy].items():
                dest = combined[policy][group]
                for field in ("races", "hits", "stakes_yen", "payout_yen"):
                    dest[field] += score[field]
    groups = {p: {k: finish_score(v) for k, v in sorted(vals.items())}
              for p, vals in combined.items()}
    return {
        "mode": "HISTORICAL_OOS_SHADOW_NOT_FORWARD",
        "ticket_count": TICKETS, "model_coefficients_unchanged": True,
        "weights_fit_on_holdout": False,
        "dates": [d.isoformat() for d in sorted(days)],
        "per_day": day_reports, "aggregate": groups,
        "forward_verified_races": 0, "production_models_promoted": 0,
        "caveats": [
            "Program B was acquired retrospectively, not independently authenticated before close.",
            "No odds/popularity/results/payout used in ticket selection.",
            "K positive marker is outcome-side metadata; no K marker is NOT proof of an incident-free race.",
            "Payout affects only retrospective ROI after tickets frozen.",
            "No strategy choice should be made from this small holdout without a new independent period."
        ],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True, type=Path)
    p.add_argument("--dates", nargs="+", required=True)
    a = p.parse_args()
    report = analyze_holdout(a.root, [date.fromisoformat(d) for d in a.dates])
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
