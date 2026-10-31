#!/usr/bin/env python3
"""Predeclared positional Plackett–Luce research policies, B PROGRAM ONLY.

Role-specific weights for head, second and third are separately normalized.
These coefficients are hypotheses fixed BEFORE reading any holdout K results;
they are NOT fitted or calibrated probabilities. Never use odds/popularity/K.
"""
from __future__ import annotations

from itertools import permutations
import math

from shadow_baseline import LANE_PRIOR, rank_tickets, validate_entries, weights_for

TICKET_COUNT = 8
POLICIES = ("baseline_local_motor", "role_second_local", "role_third_motor")
# (second_lane_exp, second_local_coef, second_motor_coef,
#  third_lane_exp, third_local_coef, third_motor_coef)
# Fixed, hand-declared sensitivity probes; not derived from historical payouts.
ROLE_COEFFICIENTS = {
    "role_second_local": (0.55, 0.26, 0.004, 0.20, 0.09, 0.012),
    "role_third_motor": (0.75, 0.14, 0.008, 0.18, 0.04, 0.020),
}


def role_probabilities(rows, policy):
    if policy not in ROLE_COEFFICIENTS:
        raise ValueError("unknown fixed positional policy")
    validate_entries(rows)
    coeff = ROLE_COEFFICIENTS[policy]
    head = weights_for(rows, "local_motor")
    second, third = {}, {}
    for item in rows:
        boat = item["boat"]
        local = item["local_win_rate"] - 5
        motor = item["motor_2rate"] - 35
        second[boat] = LANE_PRIOR[boat] ** coeff[0] * math.exp(
            coeff[1] * local + coeff[2] * motor)
        third[boat] = LANE_PRIOR[boat] ** coeff[3] * math.exp(
            coeff[4] * local + coeff[5] * motor)
    total_h = sum(head.values())
    values = {}
    for h, s, t in permutations(range(1, 7), 3):
        p = (
            head[h] / total_h *
            second[s] / sum(second[b] for b in range(1, 7) if b != h) *
            third[t] / sum(third[b] for b in range(1, 7) if b not in (h, s))
        )
        if not 0 < p < 1 or not math.isfinite(p):
            raise ValueError("invalid role probability")
        values[f"{h}-{s}-{t}"] = p
    if len(values) != 120 or not math.isclose(sum(values.values()), 1.0, abs_tol=1e-12):
        raise ValueError("role-conditional 120-way normalization failed")
    return values


def ranked_tickets(rows, policy):
    if policy == "baseline_local_motor":
        return rank_tickets(rows, "local_motor", ticket_count=TICKET_COUNT)
    distribution = role_probabilities(rows, policy)
    return sorted(distribution, key=lambda k: (-distribution[k], k))[:TICKET_COUNT]


def frozen_policies(rows):
    return {name: ranked_tickets(rows, name) for name in POLICIES}
