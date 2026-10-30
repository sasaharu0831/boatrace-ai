#!/usr/bin/env python3
"""Safely turn ONE official historical LZH archive into its CP932 report text.

This parser does NOT certify forward eligibility and does not create model features.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

MAX_COMPRESSED = 8 * 1024 * 1024
MAX_DECOMPRESSED = 16 * 1024 * 1024


def decode_report(path: Path, *, seven_zip: str | None = None) -> tuple[str, dict]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    data = path.read_bytes()
    if not (16 < len(data) <= MAX_COMPRESSED and data[2:3] == b"-"
            and data[3:5] == b"lh" and data[6:7] == b"-"):
        raise ValueError("not a bounded LZH-looking file")
    tool = seven_zip or shutil.which("7z") or shutil.which("7za") or shutil.which("7zr")
    if not tool:
        raise RuntimeError("7z is missing; install free p7zip-full; do not use an online converter")
    cmd = [tool, "e", "-so", "-bd", str(path)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        # Bound output before reading everything: avoids accepting huge decompression bombs.
        out = proc.stdout.read(MAX_DECOMPRESSED + 1)
        if len(out) > MAX_DECOMPRESSED:
            proc.kill()
            raise ValueError("decompressed content exceeds 16 MiB")
        rc = proc.wait(timeout=45)
        err = proc.stderr.read(4096)
        if rc or not out:
            raise ValueError(f"7z extraction failed (exit={rc}): {err.decode('utf-8','replace')[:200]}")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        proc.stdout.close()
        proc.stderr.close()
    # BOM-independent CP932/Shift-JIS: do not silently drop invalid bytes.
    report = out.decode("cp932", errors="strict")
    metadata = {
        "archive_sha256": hashlib.sha256(data).hexdigest(),
        "report_sha256": hashlib.sha256(out).hexdigest(),
        "report_bytes": len(out),
        "line_count": len(report.splitlines()),
        "decode": "cp932",
        "temporal_eligibility": "HISTORICAL_ONLY",
    }
    return report, metadata


def inspect_text(text: str):
    """Only report structural hints, not claim race/runner parsing is validated."""
    import re
    lines = text.splitlines()
    return {
        "sample_lines": [line[:120] for line in lines if line.strip()][:10],
        "venue_candidates": [line[:120] for line in lines if "［番組］" in line or "［成績］" in line][:6],
        "race_candidates": [line[:120] for line in lines if re.search(r"(^|\s)(?:[0-9]{1,2}R|[０-９]{1,2}Ｒ)\s", line)][:8],
        "entry_candidates": [line[:120] for line in lines if re.search(r"^\s*(?:0[1-6]|[1-6])\s+\d\s+\d{4}",line)][:3],
    }


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("lzh", type=Path)
    p.add_argument("--print-structure", action="store_true")
    args = p.parse_args(argv)
    text, audit = decode_report(args.lzh)
    if args.print_structure:
        audit["inspection"] = inspect_text(text)
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
