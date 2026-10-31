#!/usr/bin/env python3
"""Independent re-test of the EXACT frozen train-only role temperatures.

Reads a previously saved training+first-holdout research receipt; verifies the
full fit SHA-256 and historical date barrier. Opens only the NEW holdout B/K.
NEVER recalibrates or chooses a candidate based on either holdout K.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path

from archive_backfill import archive_path
from lzh_extract import decode_report
from role_temperature_calibration import ROLES, freeze_digest, TEMPERATURES
from role_temperature_trial import (
    POLICIES, empty_stats, finalize, freeze_test_b, score_test, valid_day
)

RESEARCH_KIND="TRAIN_ONLY_ROLE_TEMPERATURE_HISTORICAL_HOLDOUT"


def checked_training_fit(receipt: dict, test_days: list[date]):
    if receipt.get("report_type") != RESEARCH_KIND:
        raise ValueError("not frozen historical role-temperature receipt")
    if receipt.get("forward_verified_races") != 0 or receipt.get("production_promotion") is not False:
        raise ValueError("invalid historical Forward/production claim")
    fit = receipt["fit"]
    train_receipts = receipt["train_provenance"]
    if len(train_receipts) != 3 or [r["date"] for r in train_receipts] != receipt["training_dates"]:
        raise ValueError("training provenance missing or date mismatch")
    if fit["training_eligible_races"] < 60:
        raise ValueError("too few training races")
    if freeze_digest({"fit": fit, "train_receipts": train_receipts}) != receipt["trained_parameters_sha256"]:
        raise ValueError("training fit hash mismatch; no holdout scoring permitted")
    temperatures = fit["role_temperatures"]
    if set(temperatures) != set(ROLES) or any(t not in TEMPERATURES
                                               for t in temperatures.values()):
        raise ValueError("unapproved role temperature")
    original_train = [date.fromisoformat(s) for s in receipt["training_dates"]]
    first_test = [date.fromisoformat(s) for s in receipt["first_holdout_dates"]]
    if (len(first_test) != 3 or len(set(first_test)) != 3 or
            len(test_days) != 3 or len(set(test_days)) != 3 or
            max(original_train) >= min(first_test) or
            max(first_test) >= min(test_days)):
        raise ValueError("new test must be three unique dates strictly after first historical holdout")
    return temperatures


def run(root: Path, receipt: dict, test_dates: list[date]):
    temperature = checked_training_fit(receipt, test_dates)
    summary = {name: empty_stats() for name in POLICIES}
    test_receipts = []
    for day in sorted(test_dates):
        b_text, bmeta = decode_report(archive_path(root, "B", day))
        valid_day(b_text, day, "B")
        frozen, digest = freeze_test_b(b_text, day, temperature)
        # No new K is read until the full 120-way probability table and tickets
        # are frozen under the original trained temperature hash.
        k_text, kmeta = decode_report(archive_path(root, "K", day))
        stats = score_test(frozen, b_text, k_text, day)
        test_receipts.append({
            "date": str(day), "B_sha256": bmeta["archive_sha256"],
            "K_sha256": kmeta["archive_sha256"],
            "frozen_120way_and_8_tickets_sha256": digest,
            "B_frozen_races": len(frozen),
            "evaluated_races": stats[POLICIES[0]]["races"],
        })
        for key, scores in stats.items():
            for col in ("races", "hits", "stakes_yen", "payout_yen", "logloss_sum",
                        "brier_sum", "head_covered", "pair_covered",
                        "K_positive_markers"):
                summary[key][col] += scores[col]
            summary[key]["misses"].update(scores["misses"])
    final = {name: finalize(values) for name, values in summary.items()}
    n = final[POLICIES[0]]["races"]
    if n < 100 or any(final[name]["races"] != n or final[name]["stakes_yen"] != 800*n
                      for name in POLICIES):
        raise ValueError("insufficient same-population 8-ticket test")
    b, c = (final[key] for key in POLICIES)
    delta = {
        "hit_count": c["hits"] - b["hits"],
        "payout_yen": c["payout_yen"] - b["payout_yen"],
        "avg_logloss": c["average_logloss"] - b["average_logloss"],
        "avg_brier": c["average_brier_120"] - b["average_brier_120"]
    }
    return {
        "mode": "FROZEN_ROLE_TEMPERATURE_INDEPENDENT_HISTORICAL_RETEST_NOT_FORWARD",
        "training_dates": receipt["training_dates"],
        "first_holdout_dates": receipt["first_holdout_dates"],
        "new_holdout_dates": [str(x) for x in sorted(test_dates)],
        "original_fit_sha256": receipt["trained_parameters_sha256"],
        "original_fit_temperatures": temperature,
        "test_receipts": test_receipts,
        "test_metrics": final, "test_differences": delta,
        "increased_hits_and_payout": delta["hit_count"]>0 and delta["payout_yen"]>0,
        "improved_both_proper_scores": delta["avg_logloss"]<0 and delta["avg_brier"]<0,
        "forward_verified_races": 0, "production_promoted": False,
        "warning": "Historical B/K downloaded after race, not certified preclose; no model promotion."
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--fit-receipt", type=Path, required=True)
    p.add_argument("--test", nargs=3, required=True)
    a = p.parse_args()
    receipt = json.loads(a.fit_receipt.read_text(encoding="utf-8"))
    outcome = run(a.root, receipt, [date.fromisoformat(x) for x in a.test])
    print(json.dumps(outcome, ensure_ascii=False, indent=2))


if __name__=="__main__":
    main()
