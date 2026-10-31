#!/usr/bin/env python3
"""Predeclared B-only pair-preserving 8-ticket research candidates.

Keep the highest-score distinct (1st,2nd) pairs BEFORE reserving tickets
for at least three different 1st-place boats. Fixed local_motor weights only.
Neither K outcome nor payout nor odds can enter this function.
"""
from __future__ import annotations

from itertools import combinations, permutations
import math

from shadow_baseline import rank_tickets, weights_for

COUNT = 8
BASE = "local_motor"
MIN_HEADS = 3
PAIR_ANCHORS = (3, 4)


def score_rows(rows):
    w = weights_for(rows, BASE)
    total = sum(w.values())
    ranking = []
    for a, b, c in permutations(range(1, 7), 3):
        score = (
            (w[a] / total)
            * (w[b] / (total-w[a]))
            * (w[c] / (total-w[a]-w[b]))
        )
        if not math.isfinite(score) or score <= 0:
            raise ValueError("invalid B-only ordering score")
        ranking.append((score, f"{a}-{b}-{c}", a, (a, b)))
    ranking.sort(key=lambda x: (-x[0], x[1]))
    return ranking


def pair_protected_tickets(rows, pair_anchors=3, min_heads=MIN_HEADS):
    if pair_anchors not in PAIR_ANCHORS or min_heads != MIN_HEADS:
        raise ValueError("Only predeclared pair3/pair4 with min_head3 research is supported")
    ranked = score_rows(rows)
    anchors = []
    seen_pairs = set()
    for item in ranked:
        if item[3] not in seen_pairs:
            anchors.append(item)
            seen_pairs.add(item[3])
            if len(anchors) == pair_anchors:
                break
    assert len(anchors) == pair_anchors
    mandatory = {x[1] for x in anchors}
    anchored_heads = {x[2] for x in anchors}
    missing_count = max(0, min_heads-len(anchored_heads))
    remaining_heads = sorted(set(range(1,7))-anchored_heads)
    best = None
    for needed in combinations(remaining_heads, missing_count):
        reserved = [next(x for x in ranked if x[2] == head and x[1] not in mandatory)
                    for head in needed]
        saved = mandatory | {x[1] for x in reserved}
        picks = anchors + reserved
        picks += [x for x in ranked if x[1] not in saved][:COUNT-len(picks)]
        picks.sort(key=lambda x: (-x[0], x[1]))
        tickets = tuple(x[1] for x in picks)
        candidate = (sum(x[0] for x in picks), tickets)
        if best is None or candidate[0] > best[0] + 1e-15 or (
            abs(candidate[0]-best[0]) <= 1e-15 and candidate[1] < best[1]):
            best = candidate
    if best is None:
        raise ValueError("no feasible pair-protected candidate")
    tickets = list(best[1])
    if len(tickets) != COUNT or len(set(tickets)) != COUNT:
        raise ValueError("invalid candidate cardinality")
    if len({t[0] for t in tickets}) < min_heads:
        raise ValueError("insufficient first-place coverage")
    required = {t[1] for t in anchors}
    if not required.issubset(tickets):
        raise ValueError("high-score pair representatives were dropped")
    return tickets


def fixed_policies(rows):
    return {
        "baseline_local_motor": rank_tickets(rows, BASE),
        "pair3_head3": pair_protected_tickets(rows, 3, 3),
        "pair4_head3": pair_protected_tickets(rows, 4, 3),
    }
