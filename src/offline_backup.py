#!/usr/bin/env python3
"""Offline, no-paid-API, resumable backup for a user-controlled BOAT LAB folder.

Never submits credentials or data to a cloud provider. The caller must provide
another persistent storage path and protect it with independent backups.
"""
from __future__ import annotations

import argparse
import errno
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


def publish_without_clobber(staged: Path, target: Path, digest: str) -> str:
    """Publish an already fsynced temp file without ever replacing a target.

    Prefer atomic hardlink publication. Some removable SD/FAT/exFAT and Android
    FUSE mounts disallow hardlinks; use O_EXCL for those filesystems. The fallback
    is not atomic across a power loss: a partial target then fails its checksum
    and must be repaired explicitly, rather than silently trusted.
    """
    try:
        os.link(staged, target)
    except FileExistsError:
        if sha256(target) != digest:
            raise ValueError(f"conflicting existing backup: {target}")
        return "identical"
    except OSError as exc:
        if exc.errno not in (errno.EOPNOTSUPP, errno.ENOTSUP, errno.ENOSYS, errno.EPERM):
            raise
        try:
            fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if sha256(target) != digest:
                raise ValueError(f"conflicting existing backup: {target}")
            return "identical"
        try:
            with os.fdopen(fd, "wb") as out, staged.open("rb") as inp:
                shutil.copyfileobj(inp, out, 1024 * 1024)
                out.flush()
                os.fsync(out.fileno())
            if sha256(target) != digest:
                raise ValueError(f"fallback backup digest mismatch: {target}")
        except BaseException:
            # This invocation created the O_EXCL target; delete an incomplete
            # file on caught errors. Sudden power loss still needs a hash audit.
            target.unlink(missing_ok=True)
            raise
        return "copied"
    return "copied"


def copy_verified(src: Path, dst: Path, *, max_bytes: int) -> str:
    """Verified, nonclobbering copy; unsupported hardlink mounts use O_EXCL."""
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
        return publish_without_clobber(temp, dst, expected)
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
            return {"file": str(target), "backup_relative": f"db-snapshots/{target.name}",
                    "sha256": digest, "status": "identical"}
        status = publish_without_clobber(stage, target, digest)
        return {"file": str(target), "backup_relative": f"db-snapshots/{target.name}",
                "sha256": digest, "status": status}
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
    file_receipts = []
    # Limit newly copied data files, but continue checking already backed-up
    # files to prevent silent inconsistencies.
    raw_new = 0
    metadata_new = 0
    deferred_raw = 0
    deferred_metadata = 0
    for item in listed_files(src):
        relative = item.relative_to(src)
        is_raw = relative.parts[0] == "raw"
        # Separate bounded budgets ensure a long raw backfill does not starve
        # ever-changing manifest, quality and checkpoint records.
        if is_raw and raw_new >= max_files:
            deferred_raw += 1
            continue
        if not is_raw and metadata_new >= max_files:
            deferred_metadata += 1
            continue
        selected_meta_digest = None
        if is_raw:
            # Official raw archives are immutable by date and kind. A changed
            # same-name file is an integrity event, not a silent replacement.
            target = dst / "files" / relative
        else:
            # Manifests, checkpoints and quality labels can legitimately change
            # as new days are added or parser rules improve. Keep every version
            # under an immutable content-addressed name instead.
            selected_meta_digest = sha256(item)
            target = (dst / "metadata-versions" / relative.parent /
                      f"{item.stem}-{selected_meta_digest[:16]}{item.suffix}")
        try:
            status = copy_verified(item, target, max_bytes=MAX_RAW_BYTES)
            if selected_meta_digest is not None and sha256(target) != selected_meta_digest:
                raise ValueError(f"metadata changed during backup: {relative}")
            (copied if status == "copied" else verified).append(relative.as_posix())
            file_receipts.append({
                "source_relative": relative.as_posix(),
                "backup_relative": target.relative_to(dst).as_posix(),
                "sha256": sha256(target), "status": status,
            })
            if status == "copied":
                if is_raw:
                    raw_new += 1
                else:
                    metadata_new += 1
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
        "new_raw_copies": raw_new, "new_metadata_copies": metadata_new,
        "deferred_raw": deferred_raw, "deferred_metadata": deferred_metadata,
        "copy_batch_complete": not bool(conflict or deferred_raw or deferred_metadata),
        "file_receipts": file_receipts,
        "conflicts": conflict, "sqlite_snapshots": dbs,
        "missing_sqlite_files": missing_sqlite,
        "reliable_independent_disk": None,
        "note": "A copied file is not proof of a physically independent backup device.",
    }
    dst.mkdir(parents=True, exist_ok=True)
    with (dst / "backup_audit.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(report, ensure_ascii=False, sort_keys=True) + "\n")
    return report


def verify_backup(backup_root: Path) -> dict:
    """Verify saved receipts without requiring the original source machine."""
    backup_root = Path(backup_root)
    if not backup_root.is_absolute():
        raise ValueError("backup root must be an absolute path")
    root = backup_root.resolve()
    audit = root / "backup_audit.jsonl"
    if not audit.is_file():
        raise FileNotFoundError(audit)
    receipt_files = {}
    snapshots = {}
    with audit.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            for item in record.get("file_receipts", []):
                relative = item["backup_relative"]
                if Path(relative).is_absolute() or ".." in Path(relative).parts:
                    raise ValueError(f"invalid backup relative path in audit line {line_no}")
                receipt_files[relative] = item["sha256"]
            for item in record.get("sqlite_snapshots", []):
                relative = item.get("backup_relative")
                if relative is None:
                    # Legacy receipts used absolute paths and are only
                    # portable if the original mount point still exists.
                    p = Path(item["file"])
                    if not p.is_relative_to(root):
                        raise ValueError(
                            f"legacy snapshot path outside backup root in audit line {line_no}"
                        )
                    relative = p.relative_to(root).as_posix()
                if Path(relative).is_absolute() or ".." in Path(relative).parts:
                    raise ValueError(f"unsafe snapshot path in audit line {line_no}")
                snapshots[relative] = item["sha256"]
    bad = []
    verified = 0
    for relative, digest in sorted({**receipt_files, **snapshots}.items()):
        path = root / relative
        if not path.is_file():
            bad.append({"path": relative, "reason": "missing"})
        elif sha256(path) != digest:
            bad.append({"path": relative, "reason": "sha256 mismatch"})
        else:
            verified += 1
    return {
        "backup_root": str(root), "verified_objects": verified,
        "tracked_objects": len(receipt_files) + len(snapshots),
        "damaged_or_missing": bad, "verified_ok": bool(verified) and not bad,
        "note": "File-integrity evidence only; separate physical storage is not certified.",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path)
    p.add_argument("--backup", type=Path, required=True)
    p.add_argument("--max-files", type=int, default=12)
    p.add_argument("--verify-only", action="store_true")
    args = p.parse_args()
    if args.verify_only:
        report = verify_backup(args.backup)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report["verified_ok"]:
            raise SystemExit(1)
        return
    if args.source is None:
        p.error("--source is required unless --verify-only is set")
    report = backup(args.source, args.backup, max_files=args.max_files)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["conflicts"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
