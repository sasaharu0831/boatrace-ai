#!/usr/bin/env python3
"""Incremental no-paid-API B/K archive and retrospective DB on local persistent disk.

NOT suitable for a disposable GitHub runner; no claim of zero hosting/electricity costs.
Requires free p7zip-full/7z for extraction and Python stdlib.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
import json
import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile

from archive_backfill import connect, default_window, run_limited
from historical_sqlite import import_archives
from lzh_extract import decode_report
from quality_policy import classification_audit

MAX_IMPORTS = 3


def assert_storage_is_local(root: Path) -> Path:
    """Fail closed on disposable hosted Actions and relative paths."""
    if not root.is_absolute():
        raise ValueError("--root must be an absolute persistent directory path")
    if os.environ.get("GITHUB_ACTIONS", "").lower() == "true":
        raise RuntimeError("GitHub-hosted Actions is ephemeral; use an actual persistent disk instead")
    if str(root.resolve()).startswith(("/tmp/", "/var/tmp/")):
        raise ValueError("temporary filesystem is not accepted as durable storage")
    return root.resolve()


def complete_days(root: Path, start: date, end: date):
    """Only local pairs indexed from their current files+hashes may be imported."""
    con = connect(root)
    try:
        rows = con.execute("""
          SELECT a.day,a.kind,a.sha256,a.file_path FROM archives AS a
          WHERE a.day BETWEEN ? AND ?
            AND NOT EXISTS (
              SELECT 1 FROM archive_anomalies AS q
              WHERE q.kind=a.kind AND q.day=a.day
            )
          ORDER BY a.day,a.kind
        """, (str(start), str(end))).fetchall()
    finally:
        con.close()
    grouped = {}
    for day, kind, sha, path in rows:
        grouped.setdefault(day, {})[kind] = (sha, Path(path))
    for day, kinds in sorted(grouped.items()):
        if not ("B" in kinds and "K" in kinds):
            continue
        valid = True
        for kind in ("B", "K"):
            digest, path = kinds[kind]
            if not path.is_file():
                valid = False
                break
            with path.open("rb") as handle:
                if hashlib.file_digest(handle, "sha256").hexdigest() != digest:
                    valid = False
                    break
        if valid:
            yield day, kinds


def previous_import_hashes(db_path: Path):
    if not db_path.exists():
        return {}
    with sqlite3.connect(db_path) as con:
        exists = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='historical_import_audit'"
        ).fetchone()
        if not exists:
            return {}
        return {day: (bsha,ksha) for day,bsha,ksha in
                con.execute("SELECT race_date,B_sha256,K_sha256 FROM historical_import_audit")}


def atomic_summary(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=path.parent, prefix=".checkpoint-",
                                         suffix=".json", delete=False) as f:
            handle = Path(f.name)
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(handle, path)
    finally:
        if handle is not None and handle.exists():
            handle.unlink()


def run_batch(root: Path, start: date, end: date, *,
              max_files: int = 6, max_imports: int = MAX_IMPORTS,
              download: bool = True):
    root = assert_storage_is_local(root)
    if not 1 <= max_imports <= MAX_IMPORTS:
        raise ValueError("max_imports must be 1..3")
    if start > end:
        raise ValueError("reversed date window")
    report = {"root": str(root), "start": str(start), "end": str(end),
              "historic_only": True, "production_forward_count": 0}
    if download:
        report["network"] = run_limited(root, start, end, max_files=max_files,
                                        sleep_seconds=2)
    else:
        # Reconcile downloaded hashes without network, same as regular collector.
        from archive_backfill import index_existing
        con = connect(root)
        try:
            report["inventory"] = index_existing(root, con, start, end)
        finally:
            con.close()
    db_path = root / "historical_only.sqlite3"
    past = previous_import_hashes(db_path)
    imported, repaired_quality, skipped, errors = [], [], 0, []
    for day_str, pair in complete_days(root, start, end):
        hashes = (pair["B"][0], pair["K"][0])
        qfile = root / "quality" / f"{day_str}.json"
        if past.get(day_str) == hashes:
            if not qfile.is_file() and len(repaired_quality) < max_imports:
                try:
                    b_text, _ = decode_report(pair["B"][1])
                    k_text, _ = decode_report(pair["K"][1])
                    quality = classification_audit(b_text, k_text, date.fromisoformat(day_str))
                    quality["B_sha256"], quality["K_sha256"] = hashes
                    atomic_summary(qfile, quality)
                    repaired_quality.append(day_str)
                except (OSError, ValueError, RuntimeError) as exc:
                    errors.append({"day": day_str, "reason": "quality repair: " + str(exc)[:200]})
            skipped += 1
            continue
        if len(imported) >= max_imports:
            break
        day = date.fromisoformat(day_str)
        try:
            # Date/header verification and SQLite transaction live in import_archives.
            audit = import_archives(day, pair["B"][1], pair["K"][1], db_path)
            b_text, _ = decode_report(pair["B"][1])
            k_text, _ = decode_report(pair["K"][1])
            quality = classification_audit(b_text, k_text, day)
            quality["B_sha256"], quality["K_sha256"] = hashes
            atomic_summary(root / "quality" / f"{day}.json", quality)
            imported.append({"day": day_str, "normal_joined": audit["historical_normal_joined"],
                             "stage_counts": quality["stage_counts_B"]})
        except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
            errors.append({"day": day_str, "reason": str(exc)[:300]})
    report["imported_days"] = imported
    report["repaired_quality_days"] = repaired_quality
    report["already_imported_unchanged_days"] = skipped
    report["import_errors"] = errors
    report["db_path"] = str(db_path)
    atomic_summary(root / "checkpoint_latest.json", report)
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True,
                   help="Absolute persistent LOCAL directory; never $RUNNER_TEMP")
    p.add_argument("--start", help="YYYY-MM-DD, default four calendar years ago")
    p.add_argument("--end", help="YYYY-MM-DD, default yesterday JST")
    p.add_argument("--max-files", type=int, default=6)
    p.add_argument("--max-imports", type=int, default=3)
    p.add_argument("--offline", action="store_true", help="No HTTP downloads; reindex and import cached files")
    args = p.parse_args()
    from boat_free_lab import JST
    start, end = default_window(datetime.now(JST).date())
    if args.start:
        start = date.fromisoformat(args.start)
    if args.end:
        end = date.fromisoformat(args.end)
    if end >= datetime.now(JST).date():
        p.error("end must be before today JST")
    r = run_batch(args.root.expanduser(), start, end, max_files=args.max_files,
                  max_imports=args.max_imports, download=not args.offline)
    print(json.dumps(r, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
