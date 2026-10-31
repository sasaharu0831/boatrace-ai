#!/usr/bin/env python3
"""Bounded, resumable four-year official B/K historical archive workflow.

Never confuses post-hoc official archives with pre-deadline observations.
SQLite and raw archives must live on a PERSISTENT disk; GitHub runners are ephemeral.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import date, datetime, timedelta
import hashlib
from itertools import islice
import json
from pathlib import Path
import sqlite3
import sys
import time
from urllib.error import HTTPError, URLError

from boat_free_lab import JST, MAX_BYTES, download_archive, is_lzh

KINDS = ("B", "K")
MAX_FILES_PER_RUN = 6


def default_window(today: date) -> tuple[date, date]:
    """Past four calendar years up to yesterday (JST); not including today."""
    end = today - timedelta(days=1)
    try:
        start = today.replace(year=today.year - 4)
    except ValueError:
        start = today.replace(year=today.year - 4, day=28)
    return start, end


def day_range(start: date, end: date):
    if end < start:
        raise ValueError("end precedes start")
    for i in range((end - start).days + 1):
        yield start + timedelta(days=i)


def archive_path(root: Path, kind: str, day: date) -> Path:
    if kind not in KINDS:
        raise ValueError("unsupported archive kind")
    return root / "raw" / kind / str(day.year) / f"{kind.lower()}{day:%y%m%d}.lzh"


def connect(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(root / "archive_index.sqlite3")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""CREATE TABLE IF NOT EXISTS archives (
       kind TEXT NOT NULL CHECK(kind IN ('B','K')),
       day TEXT NOT NULL, file_path TEXT NOT NULL, bytes INTEGER NOT NULL,
       sha256 TEXT NOT NULL, origin TEXT NOT NULL,
       indexed_at_jst TEXT NOT NULL,
       temporal_eligibility TEXT NOT NULL DEFAULT 'HISTORICAL_ONLY',
       PRIMARY KEY(kind, day))""")
    con.execute("""CREATE TABLE IF NOT EXISTS attempts (
       id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, day TEXT NOT NULL,
       status TEXT NOT NULL, attempted_at_jst TEXT NOT NULL, message TEXT NOT NULL DEFAULT '')""")
    con.execute("""CREATE TABLE IF NOT EXISTS archive_anomalies (
       kind TEXT NOT NULL, day TEXT NOT NULL,
       status TEXT NOT NULL CHECK(status IN ('missing','invalid','hash_conflict')),
       original_sha256 TEXT, observed_sha256 TEXT,
       detected_at_jst TEXT NOT NULL,
       PRIMARY KEY(kind,day))""")
    con.execute("""CREATE TABLE IF NOT EXISTS archive_anomaly_history (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       kind TEXT NOT NULL, day TEXT NOT NULL, status TEXT NOT NULL,
       original_sha256 TEXT, observed_sha256 TEXT,
       event_at_jst TEXT NOT NULL)""")
    con.commit()
    return con


def manifest_proofs(root: Path) -> set[tuple[str, str, str]]:
    """A local download receipt, NOT proof of genuine pre-close capture."""
    proofs = set()
    manifest = root / "manifest.jsonl"
    if not manifest.exists():
        return proofs
    with manifest.open(encoding="utf-8") as f:
        for line in f:
            try:
                record = json.loads(line)
            except (ValueError, TypeError):
                continue
            if record.get("status") == "downloaded" and record.get("kind") in KINDS:
                proofs.add((record.get("kind"), record.get("date"), record.get("sha256")))
    return proofs


def index_existing(root: Path, con: sqlite3.Connection, start: date, end: date) -> dict:
    """Reconcile local bytes without destroying the original archive receipt.

    A removed or changed file is an anomaly. An earlier SHA-256 is immutable:
    never reassign it to new bytes merely because the archive path is the same.
    """
    proofs = manifest_proofs(root)
    good = invalid = missing = conflicts = 0
    for day in day_range(start, end):
        day_str = day.isoformat()
        for kind in KINDS:
            path = archive_path(root, kind, day)
            previous = con.execute(
                "SELECT sha256 FROM archives WHERE kind=? AND day=?",
                (kind, day_str)
            ).fetchone()
            old_digest = previous[0] if previous else None
            now = datetime.now(JST).isoformat(timespec="seconds")

            existing_anomaly = con.execute(
                "SELECT status,observed_sha256 FROM archive_anomalies WHERE kind=? AND day=?",
                (kind, day_str)
            ).fetchone()

            def anomaly(status: str, new_digest: str | None = None):
                if existing_anomaly != (status, new_digest):
                    con.execute("""INSERT INTO archive_anomaly_history(
                      kind,day,status,original_sha256,observed_sha256,event_at_jst
                    ) VALUES(?,?,?,?,?,?)""",
                        (kind, day_str, status, old_digest, new_digest, now))
                con.execute("""INSERT INTO archive_anomalies(
                     kind,day,status,original_sha256,observed_sha256,detected_at_jst
                ) VALUES(?,?,?,?,?,?)
                ON CONFLICT(kind,day) DO UPDATE SET
                     status=excluded.status, original_sha256=excluded.original_sha256,
                     observed_sha256=excluded.observed_sha256,
                     detected_at_jst=excluded.detected_at_jst""",
                    (kind, day_str, status, old_digest, new_digest, now))

            if not path.is_file():
                missing += 1
                if previous:
                    anomaly("missing")
                else:
                    con.execute("DELETE FROM archive_anomalies WHERE kind=? AND day=?",
                                (kind, day_str))
                continue
            size = path.stat().st_size
            if not 16 < size <= MAX_BYTES:
                valid = False
            else:
                with path.open("rb") as handle:
                    valid = is_lzh(handle.read(32))
            if not valid:
                invalid += 1
                anomaly("invalid")
                continue

            with path.open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            if old_digest is not None and digest != old_digest:
                conflicts += 1
                anomaly("hash_conflict", digest)
                continue
            origin = ("official_download_receipt"
                      if (kind, day_str, digest) in proofs else "local_unverified_origin")
            con.execute("""INSERT INTO archives(kind, day, file_path, bytes, sha256, origin, indexed_at_jst)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(kind,day) DO UPDATE SET
                file_path=excluded.file_path, bytes=excluded.bytes,
                indexed_at_jst=excluded.indexed_at_jst""",
                (kind, day_str, str(path), size, digest, origin, now))
            if existing_anomaly:
                con.execute("""INSERT INTO archive_anomaly_history(
                   kind,day,status,original_sha256,observed_sha256,event_at_jst
                ) VALUES(?,?,?,?,?,?)""",
                    (kind, day_str, "resolved", old_digest, digest, now))
            con.execute("DELETE FROM archive_anomalies WHERE kind=? AND day=?", (kind, day_str))
            good += 1
    con.commit()
    return {"expected_files": 2 * ((end - start).days + 1),
            "indexed_files": good, "missing_files": missing,
            "invalid_files": invalid, "hash_conflicts": conflicts,
            "window": [start.isoformat(), end.isoformat()]}


def pending(con: sqlite3.Connection, start: date, end: date, *, max_attempts: int = 3):
    """Skip indexed files and exhausted failures; audit still counts those missing."""
    known = {(kind, day) for kind, day in con.execute(
        "SELECT kind,day FROM archives WHERE day>=? AND day<=?", (start.isoformat(), end.isoformat()))}
    anomalies = {(kind, day): status for kind, day, status in con.execute(
        "SELECT kind,day,status FROM archive_anomalies WHERE day>=? AND day<=?",
        (start.isoformat(), end.isoformat()))}
    failures = dict(con.execute("""SELECT kind || ':' || day, COUNT(*) FROM attempts
      WHERE status = 'failed' GROUP BY kind, day"""))
    for day in day_range(start, end):
        keyday = day.isoformat()
        for kind in KINDS:
            anomaly = anomalies.get((kind, keyday))
            # Changed bytes must be manually quarantined/restored. Missing or
            # malformed bytes may be retrieved again, but never rewrite the
            # immutable historical SHA-256 receipt.
            needs_download = (kind, keyday) not in known or anomaly in ("missing", "invalid")
            if anomaly != "hash_conflict" and needs_download and failures.get(f"{kind}:{keyday}", 0) < max_attempts:
                yield kind, day


def run_limited(root: Path, start: date, end: date, *, max_files: int = 2,
                sleep_seconds: float = 2.0, downloader=download_archive):
    if not 1 <= max_files <= MAX_FILES_PER_RUN:
        raise ValueError("max_files must be 1..6")
    if sleep_seconds < 2:
        raise ValueError("requests must be at least 2 seconds apart")
    if end >= datetime.now(JST).date():
        raise ValueError("historical collection cannot include current/future dates")
    with closing(connect(root)) as con:
        index_existing(root, con, start, end)
        todo = list(islice(pending(con, start, end), max_files))
        results = []
        for i, (kind, day) in enumerate(todo):
            if i:
                time.sleep(sleep_seconds)
            try:
                item = downloader(kind, day, root)
                status = item["status"]
                if status not in ("cached", "downloaded"):
                    raise ValueError("unexpected downloader status")
                results.append({"day": day.isoformat(), "kind": kind, "status": status})
            except (HTTPError, URLError, ValueError, TimeoutError, OSError) as exc:
                status = "failed"
                results.append({"day": day.isoformat(), "kind": kind,
                                "status": status, "error": str(exc)[:250]})
            con.execute("INSERT INTO attempts(kind, day, status, attempted_at_jst, message) VALUES (?,?,?,?,?)",
                        (kind, day.isoformat(), status, datetime.now(JST).isoformat(timespec="seconds"),
                         results[-1].get("error", "")))
            con.commit()
        audit = index_existing(root, con, start, end)
        audit["attempted"] = results
        audit["remaining_retryable"] = sum(1 for _ in pending(con, start, end))
        audit["persistent_storage_path"] = str(root.resolve())
        audit["forward_eligible"] = False
        return audit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "run", "audit"))
    parser.add_argument("--root", type=Path, default=Path("data"))
    parser.add_argument("--start", help="YYYY-MM-DD; defaults to 4 calendar years ago")
    parser.add_argument("--end", help="YYYY-MM-DD; defaults to yesterday JST")
    parser.add_argument("--max-files", type=int, default=2)
    args = parser.parse_args(argv)
    start, end = default_window(datetime.now(JST).date())
    if args.start:
        start = date.fromisoformat(args.start)
    if args.end:
        end = date.fromisoformat(args.end)
    if end >= datetime.now(JST).date():
        parser.error("end must be before Japan today")
    if start > end:
        parser.error("start cannot exceed end")
    if args.action == "plan":
        result = {"window": [str(start), str(end)],
                  "expected_files": 2 * ((end - start).days + 1),
                  "network_requests": 0, "note": "plan only; availability unverified"}
    elif args.action == "run":
        result = run_limited(args.root, start, end, max_files=args.max_files)
    else:
        with closing(connect(args.root)) as con:
            result = index_existing(args.root, con, start, end)
            result["remaining_retryable"] = sum(1 for _ in pending(con, start, end))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
