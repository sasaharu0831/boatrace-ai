#!/usr/bin/env python3
"""Fixed B-only eight-ticket historical SHADOW experiment (NO live betting advice).

Predictions are generated and frozen from program (B) before any K processing.
The B archives may have been downloaded after the races; NOT true Forward.
Models are fixed heuristics: NOT fitted, calibrated, or tuned on the test dates.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import hashlib
import itertools
import json
import math
from pathlib import Path

from historical_records import parse_program, parse_results, reconcile
from lzh_extract import decode_report
from quality_policy import k_observations, stage_from_title

# Predeclared, untrained, transparent ranking hypotheses.
# No odds, popularity, K results, or payout enter ticket generation.
LANE_PRIOR = {1: 2.60, 2: 1.45, 3: 1.15, 4: 0.92, 5: 0.70, 6: 0.53}
POLICIES = ("lane_only", "local_only", "local_motor")
TICKETS = 8


def validate_entries(rows):
    if len(rows) != 6:
        raise ValueError("six B rows required")
    boats = {r["boat"] for r in rows}
    racers = {r["racer"] for r in rows}
    if boats != set(range(1, 7)) or len(racers) != 6:
        raise ValueError("boat/racer mapping not unique")
    for r in rows:
        for name in ("local_win_rate", "motor_2rate"):
            value = r[name]
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("missing or invalid B-only metric")
        if not 0 <= r["local_win_rate"] <= 10:
            raise ValueError("local win rate outside physically plausible bounds")
        if not 0 <= r["motor_2rate"] <= 100:
            raise ValueError("motor 2-rate out of bounds")


def weights_for(rows, policy):
    validate_entries(rows)
    if policy not in POLICIES:
        raise ValueError("unknown policy")
    w = {}
    for r in rows:
        boat = r["boat"]
        weight = LANE_PRIOR[boat]
        if policy in ("local_only", "local_motor"):
            weight *= math.exp(0.19 * (r["local_win_rate"] - 5.0))
        if policy == "local_motor":
            weight *= math.exp(0.012 * (r["motor_2rate"] - 35.0))
        w[boat] = weight
    return w


def rank_tickets(rows, policy, ticket_count=TICKETS):
    """Exactly 120 PL orders; no outcome or odds argument by design."""
    if ticket_count not in (6, 7, 8):
        raise ValueError("allowed ticket count must be six to eight")
    weights = weights_for(rows, policy)
    total = sum(weights.values())
    pairs = []
    for a, b, c in itertools.permutations(range(1, 7), 3):
        probability = (
            weights[a] / total
            * weights[b] / (total - weights[a])
            * weights[c] / (total - weights[a] - weights[b])
        )
        pairs.append((probability, f"{a}-{b}-{c}"))
    pairs.sort(key=lambda x: (-x[0], x[1]))
    # The scores are hypothetical PL ordering weights, NOT calibrated win odds.
    return [ticket for _, ticket in pairs[:ticket_count]]


def freeze_b_only(b_text, day):
    """Do not pass K, payout or result objects through this interface."""
    if not b_text.startswith("STARTB"):
        raise ValueError("not B program text")
    races, entries, issues = parse_program(b_text, day)
    bad = {x[1] for x in issues if len(x) > 1 and isinstance(x[1], str)}
    picks = {}
    stages = {}
    for key in sorted(races):
        if key in bad:
            continue
        try:
            picks[key] = {p: rank_tickets(entries[key], p) for p in POLICIES}
        except (KeyError, ValueError, TypeError):
            continue
        stages[key] = stage_from_title(races[key]["race_name"])
    frozen = json.dumps(picks, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return picks, stages, hashlib.sha256(frozen.encode("utf-8")).hexdigest()


def evaluate_posthoc(picks, stages, k_text, b_text, day):
    """Only after freezing B-only tickets may K ever be decoded/processed."""
    kr = parse_results(k_text, day)
    good = set(reconcile(parse_program(b_text, day), kr)["normal_race_keys"])
    flags = k_observations(k_text, day)
    _, _, payouts, _ = kr
    per = {p: {"evaluated": 0, "hits": 0, "stakes_yen": 0,
               "payout_yen": 0, "by_stage": {}, "K_positive_marker_count": 0}
           for p in POLICIES}
    for key in sorted(good & set(picks) & set(payouts)):
        actual = payouts[key]["trifecta"]
        payout_yen = payouts[key]["payout_yen_per_100"]
        stage = stages.get(key, "UNSPECIFIED")
        flag = flags.get(key, {})
        marker = bool(flag.get("special_evidence") or flag.get("incident_evidence"))
        for policy in POLICIES:
            data = per[policy]
            data["evaluated"] += 1
            data["stakes_yen"] += 100 * len(picks[key][policy])
            hit = actual in picks[key][policy]
            data["hits"] += int(hit)
            data["payout_yen"] += payout_yen if hit else 0
            data["K_positive_marker_count"] += int(marker)
            stage_stats = data["by_stage"].setdefault(stage, {"evaluated": 0, "hits": 0})
            stage_stats["evaluated"] += 1
            stage_stats["hits"] += int(hit)
    for policy, r in per.items():
        n = r["evaluated"]
        r["hypothetical_hit_rate"] = r["hits"] / n if n else None
        r["hypothetical_return_rate"] = (r["payout_yen"] / r["stakes_yen"]
                                         if r["stakes_yen"] else None)
        for stage in r["by_stage"].values():
            stage["hypothetical_hit_rate"] = stage["hits"] / stage["evaluated"]
    return per


def run_days(root: Path, days: list[date]):
    if not 1 <= len(days) <= 3 or len(set(days)) != len(days):
        raise ValueError("1..3 unique days only")
    combined = {p: {"evaluated": 0, "hits": 0, "stakes_yen": 0,
                    "payout_yen": 0, "K_positive_marker_count": 0}
                for p in POLICIES}
    digests, day_metrics = [], []
    for day in sorted(days):
        b_path = root / "raw" / "B" / str(day.year) / f"b{day:%y%m%d}.lzh"
        k_path = root / "raw" / "K" / str(day.year) / f"k{day:%y%m%d}.lzh"
        b, bsha = decode_report(b_path)
        picks, stages, digest = freeze_b_only(b, day)
        # The first possible K access is after B tickets and their SHA are fixed.
        k, ksha = decode_report(k_path)
        if not k.startswith("STARTK"):
            raise ValueError("not K result text")
        metrics = evaluate_posthoc(picks, stages, k, b, day)
        day_metrics.append({
            "day": str(day), "B_only_prediction_sha256": digest,
            "B_archive_sha256": bsha["archive_sha256"],
            "K_archive_sha256": ksha["archive_sha256"],
            "B_only_races_with_8_tickets": len(picks),
            "policies": metrics
        })
        digests.append(digest)
        for policy in POLICIES:
            for field in combined[policy]:
                combined[policy][field] += metrics[policy][field]
    for item in combined.values():
        item["hypothetical_hit_rate"] = (item["hits"] / item["evaluated"]
                                          if item["evaluated"] else None)
        item["hypothetical_return_rate"] = (item["payout_yen"] / item["stakes_yen"]
                                             if item["stakes_yen"] else None)
    return {
        "mode": "HISTORICAL_SHADOW_NOT_FORWARD",
        "predeclared_heuristics": list(POLICIES),
        "tickets_per_race": TICKETS,
        "predictions_frozen_from_B_before_K_parsing": True,
        "B_prediction_digests": digests,
        "days": day_metrics, "aggregate": combined,
        "forward_verified_races": 0,
        "production_model_changed": False,
        "warnings": [
            "B archives acquired after races are historical, not truly preclose.",
            "No odds or payout used to rank tickets; K is used only for scoring.",
            "K missing explicit incident markers does NOT prove accident-free.",
            "Model scores are uncalibrated fixed ranking heuristics.",
            "No parameter was fitted on or selected by these K results."
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--dates", required=True, nargs="+")
    args = parser.parse_args()
    days = [date.fromisoformat(x) for x in args.dates]
    print(json.dumps(run_days(args.root, days), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
