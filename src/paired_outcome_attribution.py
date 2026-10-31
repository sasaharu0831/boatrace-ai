#!/usr/bin/env python3
"""Postrace-only payout attribution: why NLL improves but hypothetical ROI can fall.

All candidate tickets/probabilities and their SHA are frozen from historical B
using a previously fitted, SHA-verified role-temperature model BEFORE opening K.
K result and payouts are used *only* to classify winners and retrospectively
sum outcome payments. No outcome/payout, odds or popularity is an input to picks.

The paired four-way partition is exhaustive and mutually exclusive:
 both_hit, baseline_only, calibrated_only, neither_hit.
A candidate's exact-hit delta is calibrated_only - baseline_only.
A candidate's hypothetical payout delta is the calibrated_only outcome payout
sum minus the baseline_only outcome payout sum (both-hit payouts cancel).

NEVER use this postrace attribution as a venue router, an odds-based ranking
model, a live recommendation or evidence of certified incident-free races.
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
from quality_policy import k_observations, stage_from_title
from role_temperature_calibration import freeze_digest
from role_temperature_retest import checked_training_fit
from role_temperature_trial import freeze_test_b

STATUS = ("both_hit", "baseline_only", "calibrated_only", "neither_hit")
MIN_DESCRIPTIVE_N = 30


def empty():
    return {
        "races": 0,
        "outcome_counts": {k: 0 for k in STATUS},
        "outcome_payout_yen_per_100_sum": {k: 0 for k in STATUS},
        "K_positive_marker_races": 0,
    }


def apply(summary, baseline, calibrated, actual, payout, positive=False):
    if len(baseline) != 8 or len(calibrated) != 8 or len(set(baseline)) != 8 or len(set(calibrated)) != 8:
        raise ValueError("each B-only policy must have eight unique tickets")
    if (not isinstance(payout, int)) or payout < 0:
        raise ValueError("invalid outcome-only 100-yen payout")
    b, c = actual in baseline, actual in calibrated
    status = ("both_hit" if b and c else "baseline_only" if b else
              "calibrated_only" if c else "neither_hit")
    summary["races"] += 1
    summary["outcome_counts"][status] += 1
    summary["outcome_payout_yen_per_100_sum"][status] += payout
    summary["K_positive_marker_races"] += int(positive)


def finalize(summary):
    n = summary["races"]
    counts, amounts = summary["outcome_counts"], summary["outcome_payout_yen_per_100_sum"]
    if set(counts) != set(STATUS) or set(amounts) != set(STATUS):
        raise ValueError("incomplete paired outcome categories")
    if sum(counts.values()) != n:
        raise ValueError("outcome partition did not reconcile")
    if not 0 <= summary["K_positive_marker_races"] <= n:
        raise ValueError("bad K marker count")
    for name in STATUS:
        if counts[name] < 0 or amounts[name] < 0:
            raise ValueError("negative outcomes or payout")
        if counts[name] == 0 and amounts[name] != 0:
            raise ValueError("impossible payout from an empty category")
    baseline_hits = counts["both_hit"]+counts["baseline_only"]
    calibrated_hits = counts["both_hit"]+counts["calibrated_only"]
    baseline_yen = amounts["both_hit"]+amounts["baseline_only"]
    calibrated_yen = amounts["both_hit"]+amounts["calibrated_only"]
    delta_yen = amounts["calibrated_only"]-amounts["baseline_only"]
    if delta_yen != calibrated_yen-baseline_yen:
        raise ValueError("net payout attribution mismatch")
    stakes = n*800
    return {
        **summary,
        "baseline_hits": baseline_hits,
        "calibrated_hits": calibrated_hits,
        "gain_only_hits": counts["calibrated_only"],
        "lost_only_hits": counts["baseline_only"],
        "hit_delta": calibrated_hits-baseline_hits,
        "baseline_hypothetical_paid_yen": baseline_yen,
        "calibrated_hypothetical_paid_yen": calibrated_yen,
        "gain_only_paid_yen": amounts["calibrated_only"],
        "lost_only_paid_yen": amounts["baseline_only"],
        "payout_delta_yen": delta_yen,
        "stakes_yen": stakes,
        "baseline_hypothetical_return_rate": baseline_yen/stakes if n else None,
        "calibrated_hypothetical_return_rate": calibrated_yen/stakes if n else None,
        "descriptive_sample_at_least_30": n >= MIN_DESCRIPTIVE_N,
    }


def score_day(frozen, b_text, k_text, day):
    if not k_text.startswith("STARTK"):
        raise ValueError("not an official K result report")
    validate_report_date(k_text, day, "K")
    parsed_b = parse_program(b_text, day)
    parsed_k = parse_results(k_text, day)
    eligible = set(reconcile(parsed_b, parsed_k)["normal_race_keys"]) & set(frozen)
    flags = k_observations(k_text, day)
    outcomes = parsed_k[2]
    groups = defaultdict(empty)
    for key in sorted(eligible):
        if key not in outcomes:
            raise ValueError("validated result was not found")
        stage = stage_from_title(parsed_b[0][key]["race_name"])
        venue = parsed_b[0][key]["venue"]
        flag = flags.get(key, {})
        positive = bool(flag.get("incident_evidence") or flag.get("special_evidence"))
        group_names = ("overall", f"stage:{stage}", f"venue:{venue}",
                       "K_marker:POSITIVE" if positive else "K_marker:ABSENT_UNVERIFIED")
        b = frozen[key]["baseline_local_motor"]["tickets"]
        c = frozen[key]["training_calibrated_roles"]["tickets"]
        actual = outcomes[key]["trifecta"]
        payout = int(outcomes[key]["payout_yen_per_100"])
        for group in group_names:
            apply(groups[group], b, c, actual, payout, positive)
    return dict(groups)


def run(root: Path, fit_receipt: dict, days: list[date]):
    if len(days) != 3 or len(set(days)) != 3:
        raise ValueError("exactly three unique historical test dates")
    temperatures = checked_training_fit(fit_receipt, days)
    all_groups = defaultdict(empty)
    daily = []
    for day in sorted(days):
        b_text, bmeta = decode_report(archive_path(root, "B", day))
        if not b_text.startswith("STARTB"):
            raise ValueError("not B program")
        validate_report_date(b_text, day, "B")
        frozen, freeze_sha = freeze_test_b(b_text, day, temperatures)
        # Only after freezing predictions and the SHA can K be opened.
        k_text, kmeta = decode_report(archive_path(root, "K", day))
        groups = score_day(frozen, b_text, k_text, day)
        daily.append({
            "day": str(day),
            "B_sha256": bmeta["archive_sha256"],
            "K_sha256": kmeta["archive_sha256"],
            "frozen_predictions_sha256": freeze_sha,
            "B_frozen_races": len(frozen),
            "evaluated_races": groups.get("overall", empty())["races"],
        })
        for group, measured in groups.items():
            dest = all_groups[group]
            dest["races"] += measured["races"]
            dest["K_positive_marker_races"] += measured["K_positive_marker_races"]
            for status in STATUS:
                dest["outcome_counts"][status] += measured["outcome_counts"][status]
                dest["outcome_payout_yen_per_100_sum"][status] += (
                    measured["outcome_payout_yen_per_100_sum"][status]
                )
    results = {key: finalize(raw) for key, raw in sorted(all_groups.items())}
    if "overall" not in results or results["overall"]["races"] < 100:
        raise ValueError("insufficient same-denominator paired outcomes")
    overall = results["overall"]
    for dimension in ("stage:", "venue:", "K_marker:"):
        selected = [v for k, v in results.items() if k.startswith(dimension)]
        if sum(r["races"] for r in selected) != overall["races"]:
            raise ValueError("subgroup race count mismatch")
        for field in ("hit_delta", "payout_delta_yen", "baseline_hits",
                      "calibrated_hits", "baseline_hypothetical_paid_yen",
                      "calibrated_hypothetical_paid_yen"):
            if sum(v[field] for v in selected) != overall[field]:
                raise ValueError(f"subgroup {field} mismatch")
    return {
        "mode": "B_ONLY_FIXED_TRAINED_POSTRACE_PAYOUT_ATTRIBUTION_NOT_FORWARD",
        "train_dates": fit_receipt["training_dates"],
        "test_dates": [str(d) for d in sorted(days)],
        "frozen_training_SHA256": fit_receipt["trained_parameters_sha256"],
        "temperatures": temperatures,
        "source_and_prediction_SHA_receipts": daily,
        "groups": results,
        "venue_or_stage_model_fitted": False,
        "odds_popularity_or_payout_used_to_choose_tickets": False,
        "payout_used_only_for_outcome_scoring": True,
        "subgroup_router_enabled": False,
        "forward_verified_races": 0,
        "production_promoted": False,
        "warnings": [
            "Paired payout is a postrace explanatory diagnostic, NEVER a preclose predictor.",
            "When exact hit rate increases but return decreases, baseline-only wins can exceed candidate-only wins in total paid yen.",
            "Subgroups were explored after outcomes; never infer a profitable venue or stage.",
            "K marker absent means UNVERIFIED, not no incident or no special.",
            "Historical B and K were collected AFTER these races, not authentic preclose Forward."
        ],
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True, type=Path)
    p.add_argument("--fit-receipt", required=True, type=Path)
    p.add_argument("--dates", nargs=3, required=True)
    a=p.parse_args()
    fit=json.loads(a.fit_receipt.read_text(encoding="utf-8"))
    print(json.dumps(run(a.root, fit, [date.fromisoformat(x) for x in a.dates]),
                     ensure_ascii=False, indent=2))


if __name__=="__main__":
    main()
