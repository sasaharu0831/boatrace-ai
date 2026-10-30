#!/usr/bin/env python3
"""Offline BOAT LAB four-year archive health report.

Only inventory, never a prediction or an authenticated forward evaluation.
A 'missing' count is not an attempt to download from the official server.
"""
from __future__ import annotations
import argparse
from contextlib import closing
from datetime import date, datetime
import json
from pathlib import Path

from archive_backfill import connect, default_window, index_existing, pending
from boat_free_lab import JST

MAX_SAMPLE = 12


def inspect(root: Path, start: date, end: date) -> dict:
    if start > end or end >= datetime.now(JST).date():
        raise ValueError("historical audit dates must precede Japan today")
    root = root.resolve()
    with closing(connect(root)) as con:
        inventory = index_existing(root, con, start, end)
        current_anomalies = con.execute("""
            SELECT kind,day,status,original_sha256,observed_sha256
            FROM archive_anomalies WHERE day BETWEEN ? AND ?
            ORDER BY day,kind
        """, (str(start), str(end))).fetchall()
        failed = con.execute("""
            SELECT t.kind,t.day,COUNT(*) AS n
            FROM attempts AS t
            LEFT JOIN archives AS a
              ON a.kind=t.kind AND a.day=t.day
            LEFT JOIN archive_anomalies AS q
              ON q.kind=t.kind AND q.day=t.day
            WHERE t.status='failed' AND t.day BETWEEN ? AND ?
              AND (a.kind IS NULL OR q.status IS NOT NULL)
            GROUP BY t.kind,t.day HAVING COUNT(*)>=3
            ORDER BY t.day,t.kind
        """, (str(start), str(end))).fetchall()
        retryable = list(pending(con, start, end))
        history_count = con.execute(
            "SELECT COUNT(*) FROM archive_anomaly_history "
            "WHERE day BETWEEN ? AND ?", (str(start), str(end))
        ).fetchone()[0]
    report = {
        "window": [str(start), str(end)],
        "expected_B_K_archives": inventory["expected_files"],
        "currently_valid_sha256_archives": inventory["indexed_files"],
        "missing_archives": inventory["missing_files"],
        "invalid_archives": inventory["invalid_files"],
        "changed_sha256_archives": inventory["hash_conflicts"],
        "retryable_archives": len(retryable),
        "retry_exhausted_archives": len(failed),
        "active_anomaly_count": len(current_anomalies),
        "archive_anomaly_history_events": history_count,
        "sample_anomalies": [
            {"kind": k, "day": d, "problem": st, "original_sha256": before,
             "observed_sha256": after}
            for k, d, st, before, after in current_anomalies[:MAX_SAMPLE]
        ],
        "sample_retry_exhausted": [
            {"kind": k, "day": d, "failures": n}
            for k, d, n in failed[:MAX_SAMPLE]
        ],
        "network_requests": 0,
        "historical_only": True,
        "forward_verified_races": 0,
        "data_ready_for_training": False,
        "note": "A valid LZH header+SHA256 is not full archive extraction or proof of accident-free races."
    }
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--fail-on-anomalies", action="store_true")
    args = p.parse_args()
    start, end = default_window(datetime.now(JST).date())
    if args.start:
        start = date.fromisoformat(args.start)
    if args.end:
        end = date.fromisoformat(args.end)
    report = inspect(args.root, start, end)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.fail_on_anomalies and report["active_anomaly_count"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
