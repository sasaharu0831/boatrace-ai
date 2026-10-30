#!/usr/bin/env python3
"""Free, bounded BOAT RACE official LZH collector.

Historical archive downloads are NEVER authenticated forward predictions.
"""
from __future__ import annotations
import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

JST = timezone(timedelta(hours=9))
ROOT_URL = "https://www1.mbrace.or.jp/od2"
MAX_DAYS = 3
MAX_BYTES = 8 * 1024 * 1024

def archive_url(kind: str, day: date) -> str:
    if kind not in ("B", "K"):
        raise ValueError("kind must be B or K")
    return f"{ROOT_URL}/{kind}/{day:%Y%m}/{kind.lower()}{day:%y%m%d}.lzh"

def is_lzh(data: bytes) -> bool:
    return len(data) > 16 and data[2:3] == b"-" and data[3:5] == b"lh" and data[6:7] == b"-"

def download_archive(kind: str, day: date, root: Path, *, opener=urlopen,
                     max_bytes: int=MAX_BYTES) -> dict:
    if day > datetime.now(JST).date():
        raise ValueError("future date")
    dest = root / "raw" / kind / str(day.year) / f"{kind.lower()}{day:%y%m%d}.lzh"
    url = archive_url(kind, day)
    if dest.exists():
        if not dest.is_file() or not 16 < dest.stat().st_size <= max_bytes:
            raise ValueError("existing raw archive is invalid or oversized; quarantine manually")
        with dest.open("rb") as existing:
            header = existing.read(32)
        if not is_lzh(header):
            # Never silently overwrite damaged local evidence with a fresh copy.
            raise ValueError("existing raw archive has invalid signature; quarantine manually")
        with dest.open("rb") as existing:
            digest = hashlib.file_digest(existing, "sha256").hexdigest()
        return {"date": day.isoformat(), "kind": kind, "status": "cached",
                "url": url, "path": str(dest), "sha256": digest}
    dest.parent.mkdir(parents=True, exist_ok=True)
    capture = datetime.now(JST).isoformat(timespec="seconds")
    req = Request(url, headers={"User-Agent": "BOAT-LAB-Free/0.1 (bounded research archive collection)",
                                "Accept": "application/octet-stream,*/*"})
    temp_name = None
    try:
        with opener(req, timeout=15) as resp:
            data = resp.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise ValueError("archive exceeds max_bytes")
            if not is_lzh(data):
                raise ValueError("response is not a valid-looking LZH archive")
        with tempfile.NamedTemporaryFile(dir=dest.parent, prefix=".partial-", delete=False) as tmp:
            temp_name = tmp.name
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(temp_name, dest)
        record = {"date": day.isoformat(), "kind": kind, "status": "downloaded",
                  "url": url, "path": str(dest), "sha256": hashlib.sha256(data).hexdigest(),
                  "bytes": len(data), "downloaded_at_jst": capture,
                  "source_class": "official_B_program" if kind == "B" else "official_K_result",
                  "temporal_eligibility": "HISTORICAL_ONLY",
                  "warning": "downloaded archive alone never proves preclose capture"}
        with (root / "manifest.jsonl").open("a", encoding="utf-8") as out:
            out.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return record
    finally:
        if temp_name is not None and os.path.exists(temp_name):
            os.unlink(temp_name)

def collect(start: date, days: int, root: Path, *, sleep_seconds=2.0,
            opener=urlopen) -> list[dict]:
    if not 1 <= days <= MAX_DAYS:
        raise ValueError("daily bounds: 1 <= days <= 3")
    records = []
    for i in range(days):
        day = start + timedelta(days=i)
        for kind in ("B", "K"):
            try:
                result = download_archive(kind, day, root, opener=opener)
            except (HTTPError, URLError, ValueError, TimeoutError, OSError) as e:
                result = {"date": day.isoformat(), "kind": kind, "status": "failed",
                          "error": str(e), "url": archive_url(kind, day)}
            records.append(result)
            if sleep_seconds:
                time.sleep(sleep_seconds)
    return records

def validate_freeze(snapshot: dict, prediction: dict) -> None:
    """Structural checks only: not third-party authenticity certification."""
    needed = ("race_key", "source_time_jst", "deadline_jst", "capture_sha256",
              "source_url", "verified_preclose")
    if any(not snapshot.get(k) for k in needed):
        raise ValueError("missing independent preclose evidence")
    if snapshot["verified_preclose"] is not True:
        raise ValueError("unverified snapshot cannot enter forward evaluation")
    if snapshot["race_key"] != prediction.get("race_key"):
        raise ValueError("RaceKey mismatch")
    for field in ("source_time_jst", "deadline_jst"):
        t = datetime.fromisoformat(snapshot[field])
        if t.tzinfo is None:
            raise ValueError("timezone-aware times required")
    source = datetime.fromisoformat(snapshot["source_time_jst"])
    deadline = datetime.fromisoformat(snapshot["deadline_jst"])
    frozen = datetime.fromisoformat(prediction["freeze_time_jst"])
    if frozen.tzinfo is None or not source <= frozen < deadline:
        raise ValueError("source/freeze not genuinely before deadline")
    picks = prediction.get("tickets", [])
    if not 1 <= len(picks) <= 8 or len(set(picks)) != len(picks):
        raise ValueError("expected unique 1-8 tickets")
    for ticket in picks:
        s = ticket.split("-")
        if len(s) != 3 or len(set(s)) != 3 or any(x not in "123456" for x in s):
            raise ValueError("invalid trifecta ticket")
    digest = snapshot["capture_sha256"]
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest.lower()):
        raise ValueError("invalid capture digest")

def evaluate(predictions: list[dict], outcomes: list[dict]) -> dict:
    """Payout is read only AFTER independent picks; never used to choose them."""
    outcome_map = {x["race_key"]: x for x in outcomes}
    total = hits = cost = paid = 0
    for pred in predictions:
        if pred.get("status") != "FORWARD_VERIFIED":
            continue
        outcome = outcome_map.get(pred["race_key"])
        if not outcome or outcome.get("incident") is not False:
            continue
        picks = pred["tickets"]
        total += 1
        cost += 100 * len(picks)
        if outcome["trifecta"] in picks:
            hits += 1
            paid += int(outcome["payout_yen_per_100"])
    return {"eligible_races": total, "hits": hits, "hit_rate": hits / total if total else None,
            "stakes_yen": cost, "payout_yen": paid, "return_rate": paid / cost if cost else None}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("collect")
    p.add_argument("--start", required=True)
    p.add_argument("--days", type=int, default=1)
    p.add_argument("--root", type=Path, default=Path("data"))
    p.add_argument("--sleep", type=float, default=2)
    p = sub.add_parser("evaluate")
    p.add_argument("--predictions", type=Path, required=True)
    p.add_argument("--outcomes", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.action == "collect":
        start = date.fromisoformat(args.start)
        if args.sleep < 1:
            parser.error("sleep must be >= 1 second")
        result = collect(start, args.days, args.root, sleep_seconds=args.sleep)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if all(r["status"] in ("downloaded", "cached") for r in result) else 1
    predictions = json.loads(args.predictions.read_text(encoding="utf-8"))
    outcomes = json.loads(args.outcomes.read_text(encoding="utf-8"))
    print(json.dumps(evaluate(predictions, outcomes), ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
