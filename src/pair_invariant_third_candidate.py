#!/usr/bin/env python3
"""B-only 8-ticket third-place reallocations preserving EVERY baseline (head, second) pair.

Two predeclared research candidates:
- keep_pairs_top1_third3: reserve 3 distinct 3rd boats for top baseline pair.
- keep_pairs_top2_third2: reserve 2 distinct 3rd boats for both top baseline pairs.

All existing baseline first/second pairs are retained. If eight slots cannot
satisfy the constraint, return the unchanged baseline. K, odds, payouts,
result and popularity never enter this decision.
"""
from __future__ import annotations

from collections import Counter
from pair_protected_candidate import score_rows
from shadow_baseline import rank_tickets

RULES = {"keep_pairs_top1_third3": (1, 3), "keep_pairs_top2_third2": (2, 2)}
COUNT = 8


def pair_from_ticket(ticket: str):
    parts = ticket.split("-")
    if len(parts) != 3 or len(set(parts)) != 3 or any(p not in "123456" for p in parts):
        raise ValueError("invalid three-way ticket")
    return (int(parts[0]), int(parts[1]))


def reallocate_thirds(rows, policy: str):
    if policy not in RULES:
        raise ValueError("unknown predeclared pair-preserving policy")
    ranked = score_rows(rows)
    baseline = rank_tickets(rows, "local_motor")
    baseline_pairs = {pair_from_ticket(t) for t in baseline}
    pair_order = []
    for _, _, _, pair in ranked:
        if pair in baseline_pairs and pair not in pair_order:
            pair_order.append(pair)
    if set(pair_order) != baseline_pairs:
        raise ValueError("baseline pair coverage mismatch")
    top_n, thirds_per_pair = RULES[policy]
    targets = pair_order[:top_n]
    quotas = {pair: (thirds_per_pair if pair in targets else 1) for pair in baseline_pairs}
    if sum(quotas.values()) > COUNT:
        return baseline
    compulsory = []
    for pair in pair_order:
        choices = [entry[1] for entry in ranked if entry[3] == pair]
        if len(choices) < quotas[pair]:
            raise ValueError("insufficient third variants for protected pair")
        compulsory.extend(choices[:quotas[pair]])
    unique = set(compulsory)
    if len(unique) != len(compulsory):
        raise ValueError("duplicate mandatory ticket")
    ranked_in_baseline_pairs = [entry[1] for entry in ranked if entry[3] in baseline_pairs]
    chosen = compulsory + [ticket for ticket in ranked_in_baseline_pairs
                           if ticket not in unique][:COUNT-len(compulsory)]
    order = {entry[1]: i for i, entry in enumerate(ranked)}
    chosen.sort(key=lambda x: order[x])
    if len(chosen) != COUNT or len(set(chosen)) != COUNT:
        raise ValueError("not exactly eight unique tickets")
    if {pair_from_ticket(t) for t in chosen} != baseline_pairs:
        raise ValueError("lost a baseline first-second pair")
    for pair in targets:
        if sum(pair_from_ticket(t) == pair for t in chosen) < thirds_per_pair:
            raise ValueError("third-place quota was not met")
    return chosen


def fixed_policies(rows):
    baseline = rank_tickets(rows, "local_motor")
    return {
        "baseline_local_motor": baseline,
        "keep_pairs_top1_third3": reallocate_thirds(rows, "keep_pairs_top1_third3"),
        "keep_pairs_top2_third2": reallocate_thirds(rows, "keep_pairs_top2_third2"),
    }
