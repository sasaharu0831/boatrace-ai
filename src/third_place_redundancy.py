#!/usr/bin/env python3
"""Research-only B-program third-place redundancy for fixed 8-ticket selections.

Predeclared candidates protect:
  pair2_third3: top TWO (1st,2nd) ordered pairs with THREE distinct 3rd boats each.
  pair3_third2: top THREE (1st,2nd) ordered pairs with TWO distinct 3rd boats each.
Remaining ticket slots use unchanged local_motor Plackett-Luce rankings.
NO K result, odds, payout or popularity is accepted as an input.
"""
from __future__ import annotations

from pair_protected_candidate import score_rows
from shadow_baseline import rank_tickets

CANDIDATES = {"pair2_third3": (2, 3), "pair3_third2": (3, 2)}
TICKET_COUNT = 8


def choose_tickets(rows, variant):
    if variant not in CANDIDATES:
        raise ValueError("Unknown fixed B-only candidate")
    pair_count, thirds_per_pair = CANDIDATES[variant]
    ranked = score_rows(rows)
    # Distinct (head, second) pairs ranked by their highest B-only PL ticket.
    top_pairs = []
    seen = set()
    for score, ticket, head, pair in ranked:
        if pair not in seen:
            seen.add(pair)
            top_pairs.append(pair)
            if len(top_pairs) == pair_count:
                break
    if len(top_pairs) != pair_count:
        raise ValueError("insufficient B-only pair alternatives")
    required = []
    for pair in top_pairs:
        alternatives = [item[1] for item in ranked if item[3] == pair]
        if len(alternatives) < thirds_per_pair:
            raise ValueError("insufficient third-place alternatives")
        required.extend(alternatives[:thirds_per_pair])
    if len(set(required)) != pair_count * thirds_per_pair:
        raise ValueError("duplicate reserved ticket")
    remaining = TICKET_COUNT - len(required)
    if remaining < 0:
        raise ValueError("over-constrained ticket budget")
    mandatory = set(required)
    picks = required + [item[1] for item in ranked if item[1] not in mandatory][:remaining]
    if len(picks) != TICKET_COUNT or len(set(picks)) != TICKET_COUNT:
        raise ValueError("invalid eight-ticket set")
    for pair in top_pairs:
        count = sum(tuple(map(int,ticket.split("-")[:2])) == pair for ticket in picks)
        if count < thirds_per_pair:
            raise ValueError("third-place redundancy not preserved")
    order = {item[1]: i for i, item in enumerate(ranked)}
    return sorted(picks, key=lambda x: order[x])


def fixed_policies(rows):
    return {
        "baseline_local_motor": rank_tickets(rows, "local_motor"),
        "pair2_third3": choose_tickets(rows, "pair2_third3"),
        "pair3_third2": choose_tickets(rows, "pair3_third2"),
    }
