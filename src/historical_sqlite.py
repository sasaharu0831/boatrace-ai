#!/usr/bin/env python3
"""Import validated historical normal races into a durable local SQLite database.

NEVER provides a forward-prediction interface; only certified historical joins.
Actual durable persistence requires --db on a persistent volume, not RUNNER_TEMP.
"""
from __future__ import annotations
import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3

from historical_records import parse_program, parse_results, reconcile
from lzh_extract import decode_report

JST = timezone(timedelta(hours=9))


def create_schema(con):
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript("""
    CREATE TABLE IF NOT EXISTS historical_races (
      race_key TEXT PRIMARY KEY, race_date TEXT NOT NULL, venue TEXT NOT NULL,
      race_number INTEGER NOT NULL, race_name TEXT NOT NULL, distance_m INTEGER NOT NULL,
      nominal_deadline_jst TEXT NOT NULL, trifecta TEXT NOT NULL, payout_yen_per_100 INTEGER NOT NULL,
      data_status TEXT NOT NULL CHECK(data_status = 'HISTORICAL_ONLY'),
      UNIQUE (race_date, venue, race_number)
    );
    CREATE TABLE IF NOT EXISTS historical_program_entries (
      race_key TEXT NOT NULL REFERENCES historical_races(race_key) ON DELETE CASCADE,
      boat INTEGER NOT NULL, racer INTEGER NOT NULL, name TEXT NOT NULL,
      class TEXT NOT NULL, branch TEXT NOT NULL, national_win_rate REAL NOT NULL,
      national_2rate REAL NOT NULL, local_win_rate REAL NOT NULL, local_2rate REAL NOT NULL,
      motor_number INTEGER NOT NULL, motor_2rate REAL NOT NULL,
      boat_number INTEGER NOT NULL, boat_2rate REAL NOT NULL,
      data_status TEXT NOT NULL CHECK(data_status = 'HISTORICAL_ONLY'),
      PRIMARY KEY (race_key, boat)
    );
    CREATE TABLE IF NOT EXISTS historical_result_entries (
      race_key TEXT NOT NULL REFERENCES historical_races(race_key) ON DELETE CASCADE,
      finish INTEGER NOT NULL, boat INTEGER NOT NULL, racer INTEGER NOT NULL,
      data_status TEXT NOT NULL CHECK(data_status = 'K_OUTCOME_ONLY'),
      PRIMARY KEY (race_key, finish), UNIQUE (race_key, boat)
    );
    CREATE TABLE IF NOT EXISTS historical_import_audit (
      race_date TEXT PRIMARY KEY, B_sha256 TEXT NOT NULL, K_sha256 TEXT NOT NULL,
      B_races INTEGER NOT NULL, K_races INTEGER NOT NULL,
      paired_races INTEGER NOT NULL, historical_normal_joined INTEGER NOT NULL,
      excluded_or_issues_json TEXT NOT NULL,
      imported_at_jst TEXT NOT NULL,
      data_status TEXT NOT NULL CHECK(data_status = 'HISTORICAL_ONLY')
    );
    """)


def validate_report_date(text, day, kind):
    normalized = re.sub(r"\s+", "", text)
    from unicodedata import normalize
    normalized = normalize("NFKC", normalized)
    if kind == "B":
        expected = f"{day.year}年{day.month}月{day.day}日"
    elif kind == "K":
        expected = f"{day.year}/{day.month}/{day.day}"
    else:
        raise ValueError("unsupported archive")
    if expected not in normalized:
        raise ValueError(f"{kind} report date mismatch or absent: {expected}")


def persist_day(db_path: Path, day: date, b, k, bsha: str, ksha: str):
    audit = reconcile(b, k)
    if audit["B_races"] == 0 or audit["K_races"] == 0 or audit["historical_normal_joined"] == 0:
        raise ValueError("refuse to replace the database with empty/unvalidated records")
    for digest in (bsha, ksha):
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("expected actual raw SHA256")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    try:
        create_schema(con)
        con.execute("BEGIN")
        # Never destroy a previously imported day merely because a new download
        # or parser revision yields fewer/different races. Review differences
        # independently first and restore explicitly from a verified backup.
        prior = con.execute(
            "SELECT B_sha256,K_sha256 FROM historical_import_audit WHERE race_date=?",
            (str(day),)
        ).fetchone()
        prior_keys = {row[0] for row in con.execute(
            "SELECT race_key FROM historical_races WHERE race_date=?", (str(day),)
        )}
        new_keys = set(audit["normal_race_keys"])
        if prior is not None:
            if tuple(prior) != (bsha, ksha):
                raise ValueError(
                    "source archive hash changed for imported day; "
                    "quarantine/review instead of automatic replacement"
                )
            if prior_keys != new_keys:
                raise ValueError(
                    "historical coverage changed for imported day; "
                    "quarantine/review instead of deleting existing races"
                )
        elif prior_keys:
            raise ValueError("existing races have no import audit; refuse destructive replacement")
        # A repeat of the identical source and RaceKeys is idempotent.
        con.execute("DELETE FROM historical_races WHERE race_date = ?", (str(day),))
        br, be, _ = b
        kr, ke, kp, _ = k
        for key in audit["normal_race_keys"]:
            race = br[key]
            payout = kp[key]
            con.execute("""INSERT INTO historical_races VALUES (?,?,?,?,?,?,?,?,?,?)""", (
                key, str(day), race["venue"], race["race"], race["race_name"],
                race["distance_m"], race["deadline_jst"], payout["trifecta"],
                payout["payout_yen_per_100"], "HISTORICAL_ONLY"))
            for entry in be[key]:
                con.execute("""INSERT INTO historical_program_entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    key, entry["boat"], entry["racer"], entry["name"],
                    entry["class"], entry["branch"], entry["national_win_rate"],
                    entry["national_2rate"], entry["local_win_rate"], entry["local_2rate"],
                    entry["motor_number"], entry["motor_2rate"], entry["boat_number"],
                    entry["boat_2rate"], "HISTORICAL_ONLY"))
            for entry in ke[key]:
                con.execute("""INSERT INTO historical_result_entries VALUES (?,?,?,?,?)""", (
                    key, entry["finish"], entry["boat"], entry["racer"], "K_OUTCOME_ONLY"))
        con.execute("""INSERT OR REPLACE INTO historical_import_audit VALUES (?,?,?,?,?,?,?,?,?,?)""", (
            str(day), bsha, ksha, audit["B_races"], audit["K_races"],
            audit["paired_races"], audit["historical_normal_joined"],
            json.dumps(audit["issues"], ensure_ascii=False),
            datetime.now(JST).isoformat(timespec="seconds"), "HISTORICAL_ONLY"))
        con.commit()
        audit["database"] = str(db_path)
        audit["stored_program_rows"] = 6 * len(audit["normal_race_keys"])
        audit["stored_result_rows"] = 6 * len(audit["normal_race_keys"])
        return audit
    except:
        con.rollback()
        raise
    finally:
        con.close()


def import_archives(day: date, b_path: Path, k_path: Path, db_path: Path):
    b_text, binfo = decode_report(b_path)
    k_text, kinfo = decode_report(k_path)
    if not b_text.startswith("STARTB") or not k_text.startswith("STARTK"):
        raise ValueError("B/K archives misidentified")
    validate_report_date(b_text, day, "B")
    validate_report_date(k_text, day, "K")
    audit = persist_day(db_path, day, parse_program(b_text, day), parse_results(k_text, day),
                        binfo["archive_sha256"], kinfo["archive_sha256"])
    print(json.dumps({key: val for key, val in audit.items() if key not in ("normal_race_keys", "issues")},
                     ensure_ascii=False, indent=2))
    return audit


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--b", required=True, type=Path)
    p.add_argument("--k", required=True, type=Path)
    p.add_argument("--day", required=True)
    p.add_argument("--db", type=Path, required=True)
    args = p.parse_args()
    import_archives(date.fromisoformat(args.day), args.b, args.k, args.db)


if __name__ == "__main__":
    main()
