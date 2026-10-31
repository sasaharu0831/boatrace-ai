#!/usr/bin/env python3
"""Two genuinely disjoint retrospective holdout gates for B-only role calibration.

A train-only fitted model must beat the SAME unchanged eight-ticket baseline on
exact hits, hypothetical payout, 120-way NLL and Brier score in EACH cohort.
The gate can identify a repeatable historical RESEARCH candidate, but it NEVER
approves production or certifies authentic preclose Forward results.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import math
from pathlib import Path
import re

from role_temperature_retest import checked_training_fit

HEX64 = re.compile(r"^[0-9a-f]{64}$")
NAMES = ("baseline_local_motor", "training_calibrated_roles")


def check_rows(stats, expected_date_rows):
    if set(stats) != set(NAMES):
        raise ValueError("missing historical model comparison")
    baseline = stats[NAMES[0]]
    n = baseline.get("races")
    if not isinstance(n, int) or n < 100 or n != sum(x["evaluated"] for x in expected_date_rows):
        raise ValueError("unverified holdout population")
    for name in NAMES:
        row = stats[name]
        if row["races"] != n or row["stakes_yen"] != 800 * n:
            raise ValueError("not the same eight-ticket research population")
        if not isinstance(row["hits"], int) or not 0 <= row["hits"] <= n:
            raise ValueError("invalid exact hit count")
        if not isinstance(row["payout_yen"], int) or row["payout_yen"] < 0:
            raise ValueError("invalid payout count")
        miss = row.get("misses", {})
        if sum(miss.values()) != n or miss.get("EXACT_HIT") != row["hits"]:
            raise ValueError("inconsistent exclusive miss reasons")
        for total, avg in (("logloss_sum", "average_logloss"),
                           ("brier_sum", "average_brier_120")):
            if not math.isfinite(row[total]) or not math.isfinite(row[avg]):
                raise ValueError("non-finite 120-way score")
            if not math.isclose(row[total] / n, row[avg], rel_tol=0, abs_tol=1e-9):
                raise ValueError("score average differs from stored raw total")
        if not 0 <= row["K_positive_markers"] <= n:
            raise ValueError("invalid K-positive incident/special evidence count")
    if baseline["K_positive_markers"] != stats[NAMES[1]]["K_positive_markers"]:
        raise ValueError("different K marker population")
    return n


def evaluate(first, second):
    if first.get("report_type") != "TRAIN_ONLY_ROLE_TEMPERATURE_HISTORICAL_HOLDOUT":
        raise ValueError("wrong training report type")
    if second.get("kind") != "FROZEN_ROLE_TEMPERATURE_SECOND_HISTORICAL_HOLDOUT":
        raise ValueError("wrong independent retest type")
    if first.get("forward_verified_races") != 0 or second.get("forward_verified_races") != 0:
        raise ValueError("fake preclose Forward history is disallowed")
    if first.get("production_promotion") is not False or second.get("production_promoted") is not False:
        raise ValueError("production promotion flag is disallowed")
    train_dates = [date.fromisoformat(x) for x in first["training_dates"]]
    first_dates = [date.fromisoformat(x) for x in first["first_holdout_dates"]]
    second_dates = [date.fromisoformat(x) for x in second["dates"]]
    if (len(set(train_dates + first_dates + second_dates)) != 9 or
            max(train_dates) >= min(first_dates) or max(first_dates) >= min(second_dates)):
        raise ValueError("overlapping or non-chronological train/test cohorts")
    checked_training_fit(first, second_dates)
    if first["trained_parameters_sha256"] != second["frozen_trained_parameters_sha256"]:
        raise ValueError("test used a changed trained parameter hash")
    temps = first["fit"]["role_temperatures"]
    if temps != second["frozen_trained_temperatures"]:
        raise ValueError("role coefficients changed during second holdout")
    a_receipts = first["first_holdout_receipts"]
    b_receipts = second["official_raw_and_predicted_sha256"]
    if len(a_receipts) != 3 or len(b_receipts) != 3:
        raise ValueError("missing daily SHA receipts")
    for entries, dates, ticket_field in (
        (a_receipts, first_dates, "predictions_and_120way_sha256"),
        (b_receipts, second_dates, "frozen_120way_and_8_tickets_sha256"),
    ):
        if [date.fromisoformat(x["date"]) for x in entries] != dates:
            raise ValueError("daily date receipt mismatch")
        for row in entries:
            for field in ("B_sha256", "K_sha256", ticket_field):
                if not isinstance(row.get(field), str) or not HEX64.fullmatch(row[field]):
                    raise ValueError("invalid official/frozen SHA256 receipt")
    first_daily = [dict(x, evaluated=x["evaluated_races"]) for x in a_receipts]
    second_daily = [dict(x, evaluated=x["evaluated_races"]) for x in b_receipts]
    cohorts = []
    for title, models, receipts in (
        ("first_historical_test", first["first_holdout_models"], first_daily),
        ("independent_second_test", second["metrics"], second_daily),
    ):
        n = check_rows(models, receipts)
        base, calibrated = (models[x] for x in NAMES)
        hit_delta = calibrated["hits"] - base["hits"]
        payout_delta = calibrated["payout_yen"] - base["payout_yen"]
        logloss_delta = calibrated["average_logloss"] - base["average_logloss"]
        brier_delta = calibrated["average_brier_120"] - base["average_brier_120"]
        cohorts.append({
            "name": title, "races": n, "hit_delta": hit_delta,
            "payout_yen_delta": payout_delta,
            "return_percentage_point_delta": 100*payout_delta/(800*n),
            "average_logloss_delta": logloss_delta,
            "average_brier_delta": brier_delta,
            "improved_all_four": (hit_delta > 0 and payout_delta > 0 and
                                  logloss_delta < 0 and brier_delta < 0),
        })
    combined = {}
    for model in NAMES:
        x, y = first["first_holdout_models"][model], second["metrics"][model]
        n, h = x["races"] + y["races"], x["hits"] + y["hits"]
        stake, payout = x["stakes_yen"] + y["stakes_yen"], x["payout_yen"] + y["payout_yen"]
        combined[model] = {
            "races": n, "hits": h, "stakes_yen": stake,
            "payout_yen": payout,
            "hypothetical_hit_rate": h/n,
            "hypothetical_return_rate": payout/stake,
            "average_logloss": (x["logloss_sum"] + y["logloss_sum"]) / n,
            "average_brier_120": (x["brier_sum"] + y["brier_sum"]) / n,
        }
    return {
        "gate": "TRAIN_ONLY_B_ROLE_CALIBRATION_TWO_DISJOINT_HISTORICAL_TESTS",
        "frozen_training_sha256": first["trained_parameters_sha256"],
        "temperatures": temps, "cohorts": cohorts,
        "independent_historical_replication": all(x["improved_all_four"] for x in cohorts),
        "combined_descriptive_totals": combined,
        "research_status": (
            "REPLICATED_HISTORICAL_HYPOTHESIS_ONLY" if all(
                x["improved_all_four"] for x in cohorts
            ) else "FAILED_HISTORICAL_REPLICATION"
        ),
        "production_eligible": False, "forward_verified_races": 0,
        "limitations": [
            "Two historically disjoint test cohorts are not genuine Forward.",
            "Incident-free / operational-normal events not positively certified.",
            "Historical B/K data gathered retrospectively; no live captured preclose evidence.",
            "Even positive historical calibration does not guarantee future profit.",
        ]
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--first", type=Path, required=True)
    p.add_argument("--second", type=Path, required=True)
    a = p.parse_args()
    result = evaluate(json.loads(a.first.read_text(encoding="utf-8")),
                      json.loads(a.second.read_text(encoding="utf-8")))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__=="__main__":
    main()
