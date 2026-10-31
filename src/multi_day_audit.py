#!/usr/bin/env python3
"""Bounded independent-day historical B/K audit, never a Forward backtest.

Report coverage and quarantine reasons; do not publish any racer personal data
or transfer result-derived fields into model inputs.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import date, datetime
import json
from pathlib import Path

from archive_backfill import archive_path
from boat_free_lab import JST
from historical_records import parse_program, parse_results, reconcile
from historical_sqlite import validate_report_date
from lzh_extract import decode_report
from quality_policy import classification_audit

MAX_DAYS = 3


def inspect_pair(b_text: str, k_text: str, day: date) -> dict:
    if not b_text.startswith("STARTB") or not k_text.startswith("STARTK"):
        raise ValueError("unexpected B/K archive type")
    validate_report_date(b_text, day, "B")
    validate_report_date(k_text, day, "K")
    b, k = parse_program(b_text, day), parse_results(k_text, day)
    joined = reconcile(b, k)
    qa = classification_audit(b_text, k_text, day)
    if qa["historical_six_finisher_join"] != joined["historical_normal_joined"]:
        raise ValueError("classification join disagrees with base reconciliation")
    reasons = Counter(item[0] for item in joined["issues"])
    return {
        "day": str(day),
        "B_races": joined["B_races"],
        "K_races": joined["K_races"],
        "paired_races": joined["paired_races"],
        "historical_six_finisher_join": joined["historical_normal_joined"],
        "B_only_races": len(b[0].keys() - k[0].keys()),
        "K_only_races": len(k[0].keys() - b[0].keys()),
        "issues_by_reason": dict(sorted(reasons.items())),
        "stage_counts_B": qa["stage_counts_B"],
        "K_special_evidence_count": qa["K_special_evidence_count"],
        "K_incident_evidence_count": qa["K_incident_evidence_count"],
        "historical_only": True,
        "forward_verified_races": 0,
        "retrospective_model_accuracy": None,
    }


def inspect_days(root: Path, dates: list[date]) -> dict:
    if not 1 <= len(dates) <= MAX_DAYS or len(set(dates)) != len(dates):
        raise ValueError("only 1..3 distinct days per run")
    today = datetime.now(JST).date()
    if any(day >= today for day in dates):
        raise ValueError("current/future date cannot be postrace-audited")
    reports = []
    for day in dates:
        b, bmeta = decode_report(archive_path(root, "B", day))
        k, kmeta = decode_report(archive_path(root, "K", day))
        audit = inspect_pair(b, k, day)
        audit["B_sha256"] = bmeta["archive_sha256"]
        audit["K_sha256"] = kmeta["archive_sha256"]
        reports.append(audit)
    total = lambda key: sum(x[key] for x in reports)
    return {
        "days": reports,
        "days_verified": len(reports),
        "total_B_races": total("B_races"),
        "total_K_races": total("K_races"),
        "total_historical_six_finisher_join": total("historical_six_finisher_join"),
        "forward_verified_races": 0,
        "prediction_accuracy": None,
        "note": "This is a multi-day parser coverage test, NOT forecast performance or incident-free certification."
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--dates", nargs="+", required=True, help="1..3 past JST YYYY-MM-DD dates")
    p.add_argument("--require-positive", action="store_true",
                   help="CI: fail if any day has zero B, K, or historical normal joins")
    args = p.parse_args()
    try:
        dates = [date.fromisoformat(day) for day in args.dates]
        report = inspect_days(args.root, dates)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.require_positive and any(
            not min(d["B_races"], d["K_races"], d["historical_six_finisher_join"])
            for d in report["days"]
        ):
            p.error("at least one day had no parseable B/K historical data")
    except (OSError, ValueError, RuntimeError) as exc:
        p.error(str(exc))


if __name__ == "__main__":
    main()
