#!/usr/bin/env python3
"""Research-only eight-ticket head diversification; never tune from result K.

This candidate is not an approved production model. The only inputs come from
the B program six boat records. Prices, popularity, payouts and K are forbidden.
"""
from __future__ import annotations

from itertools import combinations, permutations
import math

from shadow_baseline import POLICIES, weights_for

TICKET_COUNT = 8


def candidate_tickets(rows, *, base_policy="local_motor", minimum_heads=3):
    """Maximum sum of uncalibrated PL scores subject to >=N distinct 1st heads.

    For each N-head subset, reserve its highest-probability ticket for every
    chosen head, fill the other slots from all remaining tickets by score, and
    keep the best feasible subset. This enumerates only C(6,N) candidate subsets.
    """
    if base_policy not in POLICIES:
        raise ValueError("unsupported fixed baseline")
    if not isinstance(minimum_heads, int) or not 1 <= minimum_heads <= 6:
        raise ValueError("minimum_heads must be an integer from 1 to 6")
    weights = weights_for(rows, base_policy)
    total = sum(weights.values())
    ranked = []
    for head, second, third in permutations(range(1, 7), 3):
        denominator = (total * (total - weights[head]) *
                       (total - weights[head] - weights[second]))
        score = (weights[head] * weights[second] * weights[third]) / denominator
        if not math.isfinite(score) or score <= 0:
            raise ValueError("invalid ordering score")
        ranked.append((score, f"{head}-{second}-{third}", head))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]))
    top_by_head = {head: next(item for item in ranked if item[2] == head)
                   for head in range(1, 7)}
    best = None
    for heads in combinations(range(1, 7), minimum_heads):
        compulsory = [top_by_head[h] for h in heads]
        mandatory = {item[1] for item in compulsory}
        selected = compulsory + [
            item for item in ranked if item[1] not in mandatory
        ][:TICKET_COUNT - minimum_heads]
        selected.sort(key=lambda item: (-item[0], item[1]))
        tickets = tuple(item[1] for item in selected)
        key = (sum(item[0] for item in selected), tickets)
        if best is None or key[0] > best[0] + 1e-15 or (
                abs(key[0] - best[0]) <= 1e-15 and key[1] < best[1]):
            best = key
    assert best is not None
    picks = list(best[1])
    if len(picks) != TICKET_COUNT or len(set(picks)) != TICKET_COUNT:
        raise ValueError("non-unique tickets")
    if len({ticket[0] for ticket in picks}) < minimum_heads:
        raise ValueError("head diversification guarantee violated")
    return picks


def policies(rows):
    """Two predeclared candidates using identical motor/base weights."""
    return {
        "local_motor_head2": candidate_tickets(rows, minimum_heads=2),
        "local_motor_head3": candidate_tickets(rows, minimum_heads=3)
    }
