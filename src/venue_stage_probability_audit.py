#!/usr/bin/env python3
"""Research-only subgroup diagnostics for a PREVIOUSLY FROZEN role model.

No subgroup refitting, winner-conditioned subgroup choice, or model switching.
The model was trained only on 2026-08-10..12. B-only venue and race stage
are assigned BEFORE K is opened. K markers appear only in a POSTRACE-only
parallel partition. Results are retrospective and NOT authentic Forward.
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
from holdout_analysis import MISS_REASONS, classify_ticket_miss
from lzh_extract import decode_report
from quality_policy import stage_from_title, k_observations
from role_temperature_calibration import freeze_digest, score_distribution
from role_temperature_retest import checked_training_fit
from role_temperature_trial import freeze_test_b

MODELS = ("baseline_local_motor", "training_calibrated_roles")
# This rule is predeclared and descriptive, NOT a trained venue/stage router.
MIN_DESCRIPTIVE_RACES = 30


def empty():
    return {"races": 0, "hits": 0, "stakes_yen": 0, "payout_yen": 0,
            "logloss_sum": 0.0, "brier_sum": 0.0, "heads_covered": 0,
            "pairs_covered": 0, "misses": {key: 0 for key in MISS_REASONS}}


def update(row, tickets, probabilities, actual, payout):
    row["races"] += 1
    row["stakes_yen"] += 800
    hit = actual in tickets
    row["hits"] += int(hit)
    row["payout_yen"] += payout if hit else 0
    result = score_distribution(probabilities, actual)
    row["logloss_sum"] += result["negative_log_likelihood"]
    row["brier_sum"] += result["brier_120"]
    parts = actual.split("-")
    row["heads_covered"] += int(any(t.split("-")[0] == parts[0] for t in tickets))
    row["pairs_covered"] += int(any(t.split("-")[:2] == parts[:2] for t in tickets))
    row["misses"][classify_ticket_miss(tickets, actual)] += 1


def finalize(row):
    n = row["races"]
    if sum(row["misses"].values()) != n or row["hits"] != row["misses"]["EXACT_HIT"]:
        raise ValueError("subgroup hit/miss disagreement")
    if row["stakes_yen"] != n*800:
        raise ValueError("invalid eight-point stake")
    return {
        **row,
        "hit_rate": row["hits"]/n if n else None,
        "hypothetical_return": row["payout_yen"]/row["stakes_yen"] if n else None,
        "mean_logloss": row["logloss_sum"]/n if n else None,
        "mean_brier_120": row["brier_sum"]/n if n else None,
        "head_coverage": row["heads_covered"]/n if n else None,
        "pair_coverage": row["pairs_covered"]/n if n else None,
    }


def score_day(frozen, b_text, k_text, day):
    """Venue and B-stage fixed without using K; no K-derived predictor fields."""
    if not k_text.startswith("STARTK"):
        raise ValueError("invalid K archive")
    validate_report_date(k_text, day, "K")
    b = parse_program(b_text, day)
    k = parse_results(k_text, day)
    eligible = sorted(set(reconcile(b, k)["normal_race_keys"]) & set(frozen))
    flags = k_observations(k_text, day)
    outcomes = k[2]

    # Each listed group covers one dimension, not a model-selection signal.
    groups = {name: defaultdict(empty) for name in MODELS}
    for key in eligible:
        if key not in outcomes:
            raise ValueError("validated K join has no result")
        race = b[0][key]
        venue, stage = race["venue"], stage_from_title(race["race_name"])
        positive = bool(flags.get(key, {}).get("special_evidence") or
                        flags.get(key, {}).get("incident_evidence"))
        # The last dimension is postrace quality annotation ONLY.
        partitions = ("overall", f"venue:{venue}", f"stage:{stage}",
                      "K_marker:POSITIVE" if positive else "K_marker:ABSENT_UNVERIFIED")
        result = outcomes[key]
        for model in MODELS:
            candidate = frozen[key][model]
            for group in partitions:
                update(groups[model][group], candidate["tickets"],
                       candidate["probabilities"], result["trifecta"],
                       int(result["payout_yen_per_100"]))
    return {model: {k: v for k, v in rows.items()}
            for model, rows in groups.items()}


def run(root: Path, receipt: dict, days: list[date]):
    if len(days) != 3 or len(set(days)) != 3:
        raise ValueError("three unique holdout dates required")
    temperatures = checked_training_fit(receipt, days)
    group_sums = {name: defaultdict(empty) for name in MODELS}
    daily_receipts = []
    for day in sorted(days):
        b_text, bmeta = decode_report(archive_path(root, "B", day))
        if not b_text.startswith("STARTB"):
            raise ValueError("not B archive")
        validate_report_date(b_text, day, "B")
        frozen, freeze_sha = freeze_test_b(b_text, day, temperatures)
        # Only now read K. This is a retrospective freeze, NOT real preclose.
        k_text, kmeta = decode_report(archive_path(root, "K", day))
        day_groups = score_day(frozen, b_text, k_text, day)
        daily_receipts.append({
            "day": str(day), "B_sha256": bmeta["archive_sha256"],
            "K_sha256": kmeta["archive_sha256"],
            "frozen_120way_SHA256": freeze_sha,
            "B_races_frozen": len(frozen),
            "historical_scored": day_groups[MODELS[0]].get("overall", empty())["races"],
        })
        for model in MODELS:
            for group, score in day_groups[model].items():
                for k in ("races", "hits", "stakes_yen", "payout_yen",
                          "logloss_sum", "brier_sum", "heads_covered", "pairs_covered"):
                    group_sums[model][group][k] += score[k]
                for reason in MISS_REASONS:
                    group_sums[model][group]["misses"][reason] += score["misses"][reason]

    all_groups = sorted(set(group_sums[MODELS[0]]) | set(group_sums[MODELS[1]]))
    comparisons = {}
    for key in all_groups:
        if any(key not in group_sums[model] for model in MODELS):
            raise ValueError("different subgroup support across models")
        base, candidate = (finalize(group_sums[model][key]) for model in MODELS)
        if base["races"] != candidate["races"] or base["races"] == 0:
            raise ValueError("subgroup model denominators differ")
        n = base["races"]
        comparisons[key] = {
            "n": n,
            "descriptive_only": key != "overall",
            "sufficient_for_descriptive_comparison": n >= MIN_DESCRIPTIVE_RACES,
            "baseline": base, "calibrated": candidate,
            "delta_exact_hits": candidate["hits"]-base["hits"],
            "delta_return_pp": 100*(candidate["hypothetical_return"] -
                                   base["hypothetical_return"]),
            "delta_avg_logloss": candidate["mean_logloss"]-base["mean_logloss"],
            "delta_avg_brier": candidate["mean_brier_120"]-base["mean_brier_120"],
        }
    if "overall" not in comparisons or comparisons["overall"]["n"] < 100:
        raise ValueError("too few paired historical test races")
    total = comparisons["overall"]["n"]
    for prefix in ("venue:", "stage:", "K_marker:"):
        subtotal = sum(x["n"] for key, x in comparisons.items() if key.startswith(prefix))
        if subtotal != total:
            raise ValueError(f"{prefix} partition does not reconcile to overall")

    return {
        "mode": "HISTORICAL_B_ONLY_VENUE_STAGE_DIAGNOSTICS_NOT_FORWARD",
        "dates": [str(d) for d in sorted(days)],
        "frozen_training_SHA256": receipt["trained_parameters_sha256"],
        "trained_temperatures": temperatures,
        "daily_receipts": daily_receipts,
        "groups": comparisons,
        "venue_or_stage_model_changed": False,
        "subgroup_router_promoted": False,
        "forward_verified_races": 0, "production_promoted": False,
        "warnings": [
            "No venue/stage model is fitted or selected using these K results.",
            "K marker partitions are postrace annotations, never B-only inputs.",
            "Below 30 races a subgroup is reported as insufficient for description.",
            "30 races is not proof of statistical significance or stable profitability.",
            "All program B files were downloaded AFTER their races, NOT real Forward.",
            "Absent K incident marker does NOT certify race is incident-free.",
        ]
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--fit-receipt", type=Path, required=True)
    p.add_argument("--dates", nargs=3, required=True)
    a = p.parse_args()
    print(json.dumps(run(
        a.root, json.loads(a.fit_receipt.read_text(encoding="utf-8")),
        [date.fromisoformat(d) for d in a.dates]),
        ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
