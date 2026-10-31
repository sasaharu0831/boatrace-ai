#!/usr/bin/env python3
"""Export historical program-only features and outcome-only labels separately.

This is for retrospective simulation, NEVER a predeadline-confirmed Forward dataset.
All columns are a positive allowlist: SQL '*' and accidental outcome JOINs are forbidden.
"""
from __future__ import annotations
import argparse
import csv
from pathlib import Path
import sqlite3

FEATURE_COLUMNS = (
    "race_key", "race_date", "venue", "race_number", "race_name",
    "nominal_deadline_jst", "boat", "racer", "class", "national_win_rate",
    "national_2rate", "local_win_rate", "local_2rate", "motor_number",
    "motor_2rate", "boat_number", "boat_2rate", "data_status",
)
OUTCOME_COLUMNS = (
    "race_key", "boat", "racer", "finish", "trifecta", "payout_yen_per_100",
    "data_status",
)

FEATURE_SQL = """
SELECT r.race_key, r.race_date, r.venue, r.race_number, r.race_name,
       r.nominal_deadline_jst, p.boat, p.racer, p.class, p.national_win_rate,
       p.national_2rate, p.local_win_rate, p.local_2rate, p.motor_number,
       p.motor_2rate, p.boat_number, p.boat_2rate, p.data_status
FROM historical_program_entries AS p
JOIN historical_races AS r ON r.race_key = p.race_key
WHERE r.data_status = 'HISTORICAL_ONLY'
ORDER BY r.race_date, r.venue, r.race_number, p.boat
"""
OUTCOME_SQL = """
SELECT k.race_key, k.boat, k.racer, k.finish,
       r.trifecta, r.payout_yen_per_100, k.data_status
FROM historical_result_entries AS k
JOIN historical_races AS r ON r.race_key = k.race_key
WHERE r.data_status = 'HISTORICAL_ONLY'
ORDER BY r.race_date, r.venue, r.race_number, k.boat
"""

def write_csv(path: Path, columns: tuple[str, ...], rows):
    if path.exists():
        raise FileExistsError(f"refuse overwrite to preserve audit: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(columns)
        count = 0
        for row in rows:
            if len(row) != len(columns):
                raise ValueError("query/allowlist column mismatch")
            w.writerow(row)
            count += 1
    return count


def export_partition(db: Path, features: Path, outcomes: Path):
    if features.resolve() == outcomes.resolve():
        raise ValueError("features and outcomes cannot be same path")
    if features.exists() or outcomes.exists():
        raise FileExistsError("refuse overwriting either historical export")
    if not db.is_file():
        raise FileNotFoundError(db)
    with sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True) as con:
        feature_rows = con.execute(FEATURE_SQL).fetchall()
        outcome_rows = con.execute(OUTCOME_SQL).fetchall()
    feature_races = {(row[0], row[6]) for row in feature_rows}
    outcome_races = {(row[0], row[1]) for row in outcome_rows}
    if not feature_races or feature_races != outcome_races:
        raise ValueError("six-boat rows mismatch; refuse exports")
    # Read-only positive allowlist: no payout/finish/winner/result columns.
    if {"trifecta", "finish", "payout_yen_per_100"} & set(FEATURE_COLUMNS):
        raise ValueError("data leakage in feature allowlist")
    feature_count = write_csv(features, FEATURE_COLUMNS, feature_rows)
    outcome_count = write_csv(outcomes, OUTCOME_COLUMNS, outcome_rows)
    return {"feature_boat_rows": feature_count, "outcome_boat_rows": outcome_count,
            "retrospective_races": len({k for k, _ in feature_races}),
            "forward_verified_races": 0, "status": "HISTORICAL_ONLY"}


def main():
    import json
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--features", type=Path, required=True)
    p.add_argument("--outcomes", type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(export_partition(a.db, a.features, a.outcomes), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
