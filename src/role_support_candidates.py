#!/usr/bin/env python3
"""Fixed B-only role-second ranking with baseline HEAD / PAIR support guards.

Hypothesis: previously tested second-local role weights may help order seconds
and thirds WITHOUT discarding the original top-8 baseline first-place boats.
One candidate preserves exactly that set of heads; a stricter candidate also
preserves every original ordered (head, second) pair. Ticket count remains 8.

All inputs are the program B six boat rows. No K outcomes, odds, popularity,
payouts, or any postrace fields can affect the ticket construction.
"""
from __future__ import annotations

from shadow_baseline import rank_tickets
from positional_conditional import role_probabilities

MODELS = ("baseline_local_motor", "head_support_role_second",
          "pair_support_role_second")
TICKETS = 8
ROLE_POLICY = "role_second_local"


def _pair(ticket: str):
    parts = ticket.split("-")
    if len(parts) != 3 or len(set(parts)) != 3 or any(p not in "123456" for p in parts):
        raise ValueError("invalid 3-way ticket")
    return tuple(parts[:2])


def fixed_policies(rows):
    baseline = rank_tickets(rows, "local_motor", ticket_count=TICKETS)
    scores = role_probabilities(rows, ROLE_POLICY)
    ranked = sorted(scores, key=lambda t: (-scores[t], t))
    base_heads = {t[0] for t in baseline}
    base_pairs = {_pair(t) for t in baseline}

    # Reserve exactly one role-weighted top ticket for each original 1st boat.
    mandatory_head = [next(t for t in ranked if t[0] == head)
                      for head in sorted(base_heads)]
    reserved = set(mandatory_head)
    head_set = mandatory_head + [
        ticket for ticket in ranked if ticket[0] in base_heads and ticket not in reserved
    ][:TICKETS-len(mandatory_head)]

    # Stronger alternative: preserve all baseline head/second ordered pairs,
    # each represented by its best newly role-ranked 3rd-place boat.
    mandatory_pair = [next(t for t in ranked if _pair(t) == pair)
                      for pair in sorted(base_pairs)]
    reserved = set(mandatory_pair)
    pair_set = mandatory_pair + [
        ticket for ticket in ranked if _pair(ticket) in base_pairs and ticket not in reserved
    ][:TICKETS-len(mandatory_pair)]

    index = {ticket: i for i, ticket in enumerate(ranked)}
    head_set.sort(key=index.__getitem__)
    pair_set.sort(key=index.__getitem__)
    for selected in (head_set, pair_set):
        if len(selected) != TICKETS or len(set(selected)) != TICKETS:
            raise ValueError("failed to construct eight distinct tickets")
    if {t[0] for t in head_set} != base_heads or {t[0] for t in pair_set} != base_heads:
        raise ValueError("original head support lost")
    if {_pair(t) for t in pair_set} != base_pairs:
        raise ValueError("original first-second pair support lost")
    return {
        "baseline_local_motor": baseline,
        "head_support_role_second": head_set,
        "pair_support_role_second": pair_set,
    }
