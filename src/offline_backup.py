#!/usr/bin/env python3
"""Offline, no-paid-API, resumable backup for a user-controlled BOAT LAB folder.

Never submits credentials or data to a cloud provider. The caller must provide
another persistent storage path and protect it with independent backups.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile

MAX_RAW_BYTES = 8 * 1024 * 1024
MAX_FILES_PER_RUN = 24
JST = timezone(timedelta(hours=9))


def sha256(path: Path) -> str:
    with path.open("rb") as src:
        return hashlib.file_digest(src, "sha256").hexdigest()


def separate_roots(source: Path, destination: Path) -> tuple[Path, Path]:
    if not source.is_absolute() or not destination.is_absolute():
        raise ValueError("both source and destination paths must be absolute")
    src = source.resolve()
    dst = destination.resolve()
    if src == dst or src in dst.parents or dst in src.parents:
        raise ValueError("backup roots must not overlap or nest")
    if not src.is_dir():
        raise FileNotFoundError(src)
    if os.getenv("GITHUB_ACTIONS", "").lower() == "true":
        raise RuntimeError("temporary GitHub runner cannot be a permanent backup destination")
    return src, dst


def copy_verified(src: Path, dst: Path, *, max_bytes: int) -> str:
    """Atomic copy; an unexpected existing destination is NEVER overwritten."""
    size = src.stat().st_size
    if not 0 < size <= max_bytes:
        raise ValueError(f"source size outside allowed bounds: {src.name}")
    expected = sha256(src)
    if dst.exists():
        if sha256(dst) != expected:
            raise ValueError(f"backup differs; refusing overwrite: {dst}")
        return "identical"
    dst.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=dst.parent, prefix=".partial-", delete=False) as f:
            temp = Path(f.name)
            with src.open("rb") as inp:
                shutil.copyfileobj(inp, f)
            f.flush()
            os.fsync(f.fileno())
        if sha256(temp) != expected or sha256(src) != expected:
            raise ValueError("source or copied bytes changed during transfer")
        # No existing dst should appear between the check and the publish.
        # Use an exclusive hardlink to avoid replacing a concurrent backup.
        try:
            os.link(temp, dst)
        except FileExistsError:
            if sha256(dst) != expected:
                raise ValueError(f"concurrent backup mismatch: {dst}")
            return "identical"
        return "copied"
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def snapshot_sqlite(source: Path, backup_dir: Path) -> dict:
    """Consistent online SQLite backup, independent of WAL checkpoint timing."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    stage = None
    try:
        with tempfile.NamedTemporaryFile(dir=backup_dir, prefix=".sqlite-stage-", delete=False) as f:
            stage = Path(f.name)
        with sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True) as current:
            with sqlite3.connect(str(stage)) as destination:
                current.backup(destination)
        with sqlite3.connect(f"file:{stage.resolve()}?mode=ro", uri=True) as verify:
            if verify.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError(f"SQLite snapshot integrity check failed: {source.name}")
        digest = sha256(stage)
        target = backup_dir / f"{source.stem}-{digest[:16]}.sqlite3"
        if target.is_file():
            if sha256(target) != digest:
                raise ValueError(f"conflicting database snapshot: {target}")
            return {"file": str(target), "sha256": digest, "status": "identical"}
        try:
            os.link(stage, target)
        except FileExistsError:
            if sha256(target) != digest:
                raise ValueError(f"concurrent database snapshot mismatch: {target}")
            return {"file": str(target), "sha256": digest, "status": "identical"}
        return {"file": str(target), "sha256": digest, "status": "copied"}
    finally:
        if stage is not None:
            stage.unlink(missing_ok=True)


def listed_files(root: Path):
    for kind in ("B", "K"):
        for item in sorted((root / "raw" / kind).glob("*/*.lzh")):
            if item.is_file():
                yield item
    for path in (root / "manifest.jsonl", root / "checkpoint_latest.json"):
        if path.is_file():
            yield path
    for item in sorted((root / "quality").glob("*.json")):
        if item.is_file():
            yield item


def backup(source_root: Path, target_root: Path, *, max_files: int = 12) -> dict:
    if not 1 <= max_files <= MAX_FILES_PER_RUN:
        raise ValueError("max_files must be 1..24")
    src, dst = separate_roots(source_root, target_root)
    copied, verified, missing_sqlite, conflict = [], [], [], []
    # Limit newly copied data files, but continue checking already backed-up
    # files to prevent silent inconsistencies.
    new_copies = 0
    for item in listed_files(src):
        if new_copies >= max_files:
            break
        relative = item.relative_to(src)
        if relative.parts[0] == "raw":
            # Official raw archives are immutable by date and kind. A changed
            # same-name file is an integrity event, not a silent replacement.
            target = dst / "files" / relative
        else:
            # Manifests, checkpoints and quality labels can legitimately change
            # as new days are added or parser rules improve. Keep every version
            # under an immutable content-addressed name instead.
            digest = sha256(item)
            target = (dst / "metadata-versions" / relative.parent /
                      f"{item.stem}-{digest[:16]}{item.suffix}")
        try:
            status = copy_verified(item, target, max_bytes=MAX_RAW_BYTES)
            (copied if status == "copied" else verified).append(relative.as_posix())
            if status == "copied":
                new_copies += 1
        except (ValueError, OSError) as exc:
            conflict.append({"path": relative.as_posix(), "error": str(exc)})
            # Do not ignore a conflicting backup; stop and preserve both copies.
            break
    dbs = []
    if not conflict:
        for name in ("archive_index.sqlite3", "historical_only.sqlite3"):
            f = src / name
            if not f.is_file():
                missing_sqlite.append(name)
                continue
            dbs.append(snapshot_sqlite(f, dst / "db-snapshots"))
    report = {
        "captured_at_jst": datetime.now(JST).isoformat(timespec="seconds"),
        "source": str(src), "backup_root": str(dst),
        "new_file_copies": copied, "matching_existing_files": len(verified),
        "conflicts": conflict, "sqlite_snapshots": dbs,
        "missing_sqlite_files": missing_sqlite,
        "reliable_independent_disk": None,
        "note": "A copied file is not proof of a physically independent backup device.",
    }
    dst.mkdir(parents=True, exist_ok=True)
    with (dst / "backup_audit.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(report, ensure_ascii=False, sort_keys=True) + "\n")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--backup", type=Path, required=True)
    p.add_argument("--max-files", type=int, default=12)
    args = p.parse_args()
    report = backup(args.source, args.backup, max_files=args.max_files)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["conflicts"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
