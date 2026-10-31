#!/usr/bin/env python3
"""Train-only positional temperature calibration; retrospective B/K research.

All training K outcomes may be used to choose one of five PREDECLARED
temperatures per sequential finishing role. An untouched later period must
be scored without refitting. This is not genuine preclose Forward evidence.
No odds, popularity or payout participates in calibration or ticket selection.
"""
from __future__ import annotations

from itertools import permutations
import hashlib
import json
import math

from shadow_baseline import weights_for, rank_tickets

TEMPERATURES = (0.5, 0.75, 1.0, 1.25, 1.5)
ROLES = ("first", "second", "third")
TICKET_COUNT = 8


def _logs(rows):
    weights = weights_for(rows, "local_motor")
    return {boat: math.log(value) for boat, value in weights.items()}


def role_log_losses(logs, actual):
    """Per-role log loss on a particular observed 3-place finish."""
    parts = [int(x) for x in actual.split("-")]
    if len(parts) != 3 or len(set(parts)) != 3 or any(x not in logs for x in parts):
        raise ValueError("invalid actual outcome")
    available = tuple(sorted(logs))
    per_role = {}
    for role, chosen in zip(ROLES, parts):
        per_role[role] = {}
        for temperature in TEMPERATURES:
            logits = [temperature * logs[boat] for boat in available]
            mx = max(logits)
            denominator_log = mx + math.log(sum(math.exp(x - mx) for x in logits))
            per_role[role][temperature] = denominator_log - temperature * logs[chosen]
        available = tuple(x for x in available if x != chosen)
    return per_role


def fit_temperatures(training_rows):
    """Training rows: only prearranged pairs (six B entries, official K result).

    No payout or race popularity is used. The temperature grid and tie policy
    were frozen before learning. A small quadratic penalty discourages
    overadjustment from an uncalibrated baseline.
    """
    if len(training_rows) < 60:
        raise ValueError("need >=60 joined historical training races")
    losses = {role: {t: 0.0 for t in TEMPERATURES} for role in ROLES}
    for b_entries, outcome in training_rows:
        per_role = role_log_losses(_logs(b_entries), outcome)
        for role in ROLES:
            for t in TEMPERATURES:
                losses[role][t] += per_role[role][t]
    # Penalize extreme weights: fixed in advance, not tuned on the holdout.
    ridge_strength = 2.0
    best = {}
    for role in ROLES:
        best[role] = min(
            TEMPERATURES,
            key=lambda t: (losses[role][t] + ridge_strength * (t - 1.0)**2,
                           abs(t - 1.0), t)
        )
    return {
        "role_temperatures": best,
        "training_eligible_races": len(training_rows),
        "grid": list(TEMPERATURES),
        "ridge_strength": ridge_strength,
        "fit_target": "sum of sequential role negative log likelihood (no payout)",
        "training_losses": {role: {str(t): round(losses[role][t], 8)
                                    for t in TEMPERATURES} for role in ROLES},
        "trained_on_K_outcomes_only_from_training_dates": True,
        "not_genuine_forward": True
    }


def distribution(rows, temperatures):
    logs = _logs(rows)
    if set(temperatures) != set(ROLES) or any(t not in TEMPERATURES
                                               for t in temperatures.values()):
        raise ValueError("unapproved role temperatures")
    result = {}
    for h, s, t in permutations(range(1, 7), 3):
        remaining = tuple(range(1, 7))
        p = 1.0
        for role, boat in zip(ROLES, (h, s, t)):
            tau = temperatures[role]
            mx = max(tau * logs[b] for b in remaining)
            den = sum(math.exp(tau * logs[b] - mx) for b in remaining)
            p *= math.exp(tau * logs[boat] - mx) / den
            remaining = tuple(b for b in remaining if b != boat)
        result[f"{h}-{s}-{t}"] = p
    if len(result) != 120 or not math.isclose(sum(result.values()), 1.0,
                                              rel_tol=0.0, abs_tol=1e-11):
        raise ValueError("120-outcome distribution normalization failed")
    return result


def top_eight(probs):
    if len(probs) != 120:
        raise ValueError("need the full 120-outcome distribution")
    return sorted(probs, key=lambda k: (-probs[k], k))[:TICKET_COUNT]


def score_distribution(probs, actual):
    if actual not in probs:
        raise ValueError("actual result absent from certified finish permutations")
    if any(p < 0 or not math.isfinite(p) for p in probs.values()):
        raise ValueError("invalid probabilities")
    return {
        "negative_log_likelihood": -math.log(probs[actual]),
        "brier_120": sum((p - (1 if key == actual else 0)) ** 2
                         for key, p in probs.items())
    }


def freeze_digest(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False,
                                      sort_keys=True, separators=(",", ":")).encode()).hexdigest()
