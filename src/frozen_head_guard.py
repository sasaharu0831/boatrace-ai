#!/usr/bin/env python3
"""Two B-only, frozen-temperature eight-ticket head-support research candidates.

Do NOT fit, edit, blend, or choose model coefficients on test outcomes.
The original B-only baseline determines which first-place boats to preserve.
The frozen historical temperature model ranks third-position alternatives.
This selector never accepts K results, payout, odds or popularity.
"""
from __future__ import annotations
from shadow_baseline import rank_tickets
from role_temperature_calibration import distribution, top_eight, ROLES

NAMES=("baseline_local_motor","frozen_temperature",
       "frozen_head_support","frozen_pair_support")


def pair(ticket):
    pieces=ticket.split("-")
    if len(pieces)!=3 or len(set(pieces))!=3 or any(p not in "123456" for p in pieces):
        raise ValueError("bad trifecta ticket")
    return (pieces[0],pieces[1])


def _guarded(probs, baseline, preserve_pairs):
    if len(probs)!=120 or len(baseline)!=8 or len(set(baseline))!=8:
        raise ValueError("missing full 120 probabilities or 8 baseline tickets")
    ranked=sorted(probs,key=lambda t:(-probs[t],t))
    heads={t[0] for t in baseline}
    pairs={pair(t) for t in baseline}
    if preserve_pairs:
        representatives=[next(t for t in ranked if pair(t)==p) for p in sorted(pairs)]
        candidates=[t for t in ranked if pair(t) in pairs]
    else:
        representatives=[next(t for t in ranked if t[0]==h) for h in sorted(heads)]
        candidates=[t for t in ranked if t[0] in heads]
    mandatory=set(representatives)
    chosen=representatives+[t for t in candidates if t not in mandatory][:8-len(representatives)]
    chosen.sort(key=ranked.index)
    if len(chosen)!=8 or len(set(chosen))!=8:
        raise ValueError("could not choose 8 distinct constrained tickets")
    if {t[0] for t in chosen}!=heads:
        raise ValueError("lost baseline first-place support")
    if preserve_pairs and {pair(t) for t in chosen}!=pairs:
        raise ValueError("lost baseline ordered 1st-2nd pair support")
    return chosen


def fixed_predictions(rows, temperatures):
    if set(temperatures)!=set(ROLES):
        raise ValueError("unverified frozen temperatures")
    baseline=rank_tickets(rows,"local_motor")
    probs=distribution(rows,temperatures)
    return {
        "baseline_local_motor":baseline,
        "frozen_temperature":top_eight(probs),
        "frozen_head_support":_guarded(probs,baseline,False),
        "frozen_pair_support":_guarded(probs,baseline,True),
    },probs
