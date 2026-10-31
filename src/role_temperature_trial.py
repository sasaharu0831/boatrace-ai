#!/usr/bin/env python3
"""Strict historical train-before-test of role temperatures on official B/K.

Workflow: parse training B, THEN training K => train temperatures => hash
frozen parameters => open each later TEST B and freeze the full 120-way
distribution and 8 picks => open TEST K only to score. No re-fit or selection
after test K. This is historical shadow analysis, not true Forward.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path

from archive_backfill import archive_path
from historical_records import parse_program, parse_results, reconcile
from historical_sqlite import validate_report_date
from holdout_analysis import classify_ticket_miss, MISS_REASONS
from lzh_extract import decode_report
from quality_policy import k_observations
from role_temperature_calibration import (
    ROLES, distribution, fit_temperatures, freeze_digest, top_eight,
    score_distribution
)
from shadow_baseline import rank_tickets

BASE_TEMPS = {role: 1.0 for role in ROLES}
POLICIES = ("baseline_local_motor", "training_calibrated_roles")


def valid_day(text, day, kind):
    if not text.startswith("START" + kind):
        raise ValueError(f"wrong {kind} report type")
    validate_report_date(text, day, kind)


def training_observations(b, k, day):
    valid_day(b, day, "B")
    valid_day(k, day, "K")
    parsed_b = parse_program(b, day)
    parsed_k = parse_results(k, day)
    accepted = set(reconcile(parsed_b, parsed_k)["normal_race_keys"])
    flags = k_observations(k, day)
    entries = parsed_b[1]
    outcomes = parsed_k[2]
    observations = []
    positive_markers = 0
    for key in sorted(accepted):
        flag = flags.get(key, {})
        if flag.get("special_evidence") or flag.get("incident_evidence"):
            positive_markers += 1
            continue
        observations.append((entries[key], outcomes[key]["trifecta"]))
    return observations, positive_markers


def freeze_test_b(text, day, trained):
    """Only test B rows and already-frozen, earlier-date coefficients."""
    valid_day(text, day, "B")
    races, entries, issues = parse_program(text, day)
    bad = {x[1] for x in issues if len(x) > 1 and isinstance(x[1], str)}
    frozen = {}
    for key in sorted(races):
        if key in bad:
            continue
        try:
            rows = entries[key]
            baseline = distribution(rows, BASE_TEMPS)
            candidate = distribution(rows, trained)
            if top_eight(baseline) != rank_tickets(rows, "local_motor"):
                raise ValueError("unmodified baseline 8 picks do not reproduce")
            frozen[key] = {
                "baseline_local_motor": {
                    "tickets": top_eight(baseline), "probabilities": baseline,
                },
                "training_calibrated_roles": {
                    "tickets": top_eight(candidate), "probabilities": candidate,
                },
            }
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    if not frozen:
        raise ValueError("no valid test B race for eight-ticket scoring")
    # The SHA commits BOTH the entire 120-way distribution and 8 ticket choices.
    return frozen, freeze_digest(frozen)


def empty_stats():
    return {"races": 0, "hits": 0, "stakes_yen": 0, "payout_yen": 0,
            "logloss_sum": 0.0, "brier_sum": 0.0,
            "head_covered": 0, "pair_covered": 0, "K_positive_markers": 0,
            "misses": Counter()}


def finalize(row):
    result = dict(row)
    result["misses"] = {k: row["misses"][k] for k in MISS_REASONS}
    n = result["races"]
    if sum(result["misses"].values()) != n or result["misses"]["EXACT_HIT"] != result["hits"]:
        raise ValueError("exclusive miss category failure")
    result["hypothetical_hit_rate"] = result["hits"] / n if n else None
    result["hypothetical_return_rate"] = (result["payout_yen"] / result["stakes_yen"]
                                           if result["stakes_yen"] else None)
    result["average_logloss"] = result["logloss_sum"] / n if n else None
    result["average_brier_120"] = result["brier_sum"] / n if n else None
    result["head_coverage"] = result["head_covered"] / n if n else None
    result["pair_coverage"] = result["pair_covered"] / n if n else None
    return result


def score_test(frozen, b, k, day):
    valid_day(k, day, "K")
    joined = reconcile(parse_program(b, day), parse_results(k, day))
    eligible = sorted(set(joined["normal_race_keys"]) & set(frozen))
    flags = k_observations(k, day)
    payouts = parse_results(k, day)[2]
    totals = {name: empty_stats() for name in POLICIES}
    for key in eligible:
        if key not in payouts:
            raise ValueError("valid K join missing 3-way outcome")
        actual = payouts[key]["trifecta"]
        payout = int(payouts[key]["payout_yen_per_100"])
        actual_boats = actual.split("-")
        marker = bool(flags.get(key, {}).get("special_evidence") or
                      flags.get(key, {}).get("incident_evidence"))
        for name in POLICIES:
            row = frozen[key][name]
            pick = row["tickets"]
            probs = row["probabilities"]
            losses = score_distribution(probs, actual)
            stat = totals[name]
            stat["races"] += 1
            stat["stakes_yen"] += 800
            stat["payout_yen"] += payout if actual in pick else 0
            stat["hits"] += int(actual in pick)
            stat["logloss_sum"] += losses["negative_log_likelihood"]
            stat["brier_sum"] += losses["brier_120"]
            stat["head_covered"] += int(any(t.split("-")[0] == actual_boats[0] for t in pick))
            stat["pair_covered"] += int(any(t.split("-")[:2] == actual_boats[:2] for t in pick))
            stat["K_positive_markers"] += int(marker)
            stat["misses"][classify_ticket_miss(pick, actual)] += 1
    return {name: finalize(row) for name, row in totals.items()}


def run(root: Path, train_dates: list[date], test_dates: list[date]):
    if (len(train_dates) != 3 or len(test_dates) != 3 or
            len(set(train_dates)) != 3 or len(set(test_dates)) != 3 or
            max(train_dates) >= min(test_dates)):
        raise ValueError("three unique older training dates, followed by three untouched test dates required")
    observations, training_receipts = [], []
    for day in sorted(train_dates):
        b, bmeta = decode_report(archive_path(root, "B", day))
        k, kmeta = decode_report(archive_path(root, "K", day))
        found, marked = training_observations(b, k, day)
        observations.extend(found)
        training_receipts.append({
            "date": str(day), "B_sha256": bmeta["archive_sha256"],
            "K_sha256": kmeta["archive_sha256"],
            "training_rows_excluding_positive_K_markers": len(found),
            "excluded_positive_K_markers": marked,
        })
    fit = fit_temperatures(observations)
    # Trained parameters and their training provenance are immutable from here.
    fit_hash = freeze_digest({"fit": fit, "train_receipts": training_receipts})
    values = {name: empty_stats() for name in POLICIES}
    test_receipts = []
    for day in sorted(test_dates):
        b, bmeta = decode_report(archive_path(root, "B", day))
        predictions, frozen_sha = freeze_test_b(b, day, fit["role_temperatures"])
        # First possible test K access is below this SHA-256 freeze.
        k, kmeta = decode_report(archive_path(root, "K", day))
        scored = score_test(predictions, b, k, day)
        test_receipts.append({
            "date": str(day), "B_sha256": bmeta["archive_sha256"],
            "K_sha256": kmeta["archive_sha256"],
            "predictions_and_120way_sha256": frozen_sha,
            "B_only_prediction_races": len(predictions),
            "evaluated_races": scored["baseline_local_motor"]["races"],
        })
        for name, row in scored.items():
            total = values[name]
            for field in ("races", "hits", "stakes_yen", "payout_yen",
                          "logloss_sum", "brier_sum", "head_covered", "pair_covered",
                          "K_positive_markers"):
                total[field] += row[field]
            total["misses"].update(row["misses"])
    metrics = {name: finalize(row) for name, row in values.items()}
    if metrics[POLICIES[0]]["races"] == 0 or (
            metrics[POLICIES[0]]["races"] != metrics[POLICIES[1]]["races"]):
        raise ValueError("no verified common test denominator")
    base, trained = (metrics[name] for name in POLICIES)
    return {
        "mode": "TRAIN_ONLY_TEMPERATURE_CALIBRATION_HISTORICAL_NOT_FORWARD",
        "train_dates": [str(d) for d in sorted(train_dates)],
        "test_dates": [str(d) for d in sorted(test_dates)],
        "train_receipts": training_receipts,
        "fit": fit, "trained_parameters_sha256": fit_hash,
        "test_receipts": test_receipts,
        "test_metrics": metrics,
        "test_deltas": {
            "exact_hits": trained["hits"] - base["hits"],
            "payout_yen": trained["payout_yen"] - base["payout_yen"],
            "mean_logloss": trained["average_logloss"] - base["average_logloss"],
            "mean_brier_120": trained["average_brier_120"] - base["average_brier_120"],
        },
        "test_simultaneously_improves_hits_roi": (
            trained["hits"] > base["hits"] and trained["payout_yen"] > base["payout_yen"]),
        "test_improves_both_proper_scoring_rules": (
            trained["average_logloss"] < base["average_logloss"] and
            trained["average_brier_120"] < base["average_brier_120"]),
        "forward_verified_races": 0,
        "production_promoted": False,
        "warnings": [
            "Train data were past outcomes; no K from any test date was used in fitting.",
            "All B/K obtained postrace, never certified genuine preclose Forward.",
            "B-only temperatures fitted from training data do not prove calibrated future odds.",
            "Six finishers and absence of K keywords do not prove race is incident-free.",
            "Even positive one-period results cannot authorize production or future-profit claims."
        ]
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True, type=Path)
    p.add_argument("--train", nargs=3, required=True)
    p.add_argument("--test", nargs=3, required=True)
    a = p.parse_args()
    report = run(a.root, [date.fromisoformat(x) for x in a.train],
                 [date.fromisoformat(x) for x in a.test])
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
