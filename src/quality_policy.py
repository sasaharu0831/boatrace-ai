#!/usr/bin/env python3
"""Auditable race segmentation of historical B/K official reports.

No result-derived flag, disqualification, or payout may enter preclose models.
No inference of 'incident-free' from absence of an incident keyword.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import json
import re

from historical_records import normalize, parse_program, parse_results, reconcile, race_key, sections
from lzh_extract import decode_report

K_RACE = re.compile(r"^\s*(\d{1,2})R\s+(.+?)\s+H(\d+)m(?:\s|$)")
# Only positive text evidence; absence of a marker is never verification of absence.
SPECIAL_TERMS = {
    "安定板": "STABILITY_PLATE_MENTION",
    "進入固定": "FIXED_ENTRY_MENTION",
}
INCIDENT_TERMS = {
    "フライング": "FLYING_MENTION",
    "失格": "DISQUALIFICATION_MENTION",
    "返還": "REFUND_MENTION",
    "欠場": "WITHDRAWAL_MENTION",
    "転覆": "CAPSIZE_MENTION",
    "落水": "FALL_OVERBOARD_MENTION",
    "沈没": "SINKING_MENTION",
}
EXCEPTION_ENTRY = re.compile(r"^\s*(F|K|L|S[0-2])\s+([1-6])\s+\d{4}\b")


def stage_from_title(title: str) -> str:
    t = normalize(title).replace(" ", "")
    if "準優" in t:
        return "SEMIFINAL"
    if "優勝" in t:
        return "FINAL"
    if "予選" in t:
        return "QUALIFYING"
    if "一般" in t:
        return "GENERAL"
    if "選抜" in t:
        return "SELECTION"
    return "UNSPECIFIED"


def k_observations(text: str, day: date) -> dict:
    """Inspect detailed K race blocks, excluding summary payout tables."""
    observed = {}
    for venue, lines in sections(text, "K"):
        key = None
        block = []
        def flush():
            if key is None:
                return
            joined = "\n".join(block)
            specials = sorted({label for term, label in SPECIAL_TERMS.items() if term in joined})
            incidents = sorted({label for term, label in INCIDENT_TERMS.items() if term in joined})
            if any(EXCEPTION_ENTRY.match(line) for line in block):
                incidents.append("EXCEPTION_ENTRY")
                incidents = sorted(set(incidents))
            observed[key] = {
                "special_evidence": specials, "incident_evidence": incidents,
                "special_status": "EVIDENCE_PRESENT" if specials else "UNVERIFIED",
                "incident_status": "EVIDENCE_PRESENT" if incidents else "UNVERIFIED",
                "source": "K_OUTCOME_ONLY",
            }
        for line in lines:
            n = normalize(line)
            head = K_RACE.match(n)
            if head:
                number = int(head.group(1))
                if 1 <= number <= 12:
                    flush()
                    key = race_key(day, venue, number)
                    block = [n]
                else:
                    flush()
                    key = None
                    block = []
            elif key is not None:
                block.append(n)
        flush()
    return observed


def classification_audit(b_text: str, k_text: str, day: date) -> dict:
    b = parse_program(b_text, day)
    k = parse_results(k_text, day)
    audit = reconcile(b, k)
    b_races = b[0]
    flags = k_observations(k_text, day)
    class_by_key = {}
    for key, race in sorted(b_races.items()):
        info = flags.get(key)
        class_by_key[key] = {
            "stage": stage_from_title(race["race_name"]),
            "special_evidence": (info or {}).get("special_evidence", []),
            "incident_evidence": (info or {}).get("incident_evidence", []),
            "special_status": (info or {}).get("special_status", "K_REPORT_MISSING"),
            "incident_status": (info or {}).get("incident_status", "K_REPORT_MISSING"),
            "historical_six_finisher_join": key in audit["normal_race_keys"],
            "training_pool": "UNVERIFIED_NOT_ADMITTED",
        }
    return {
        "day": str(day),
        "stage_counts_B": dict(sorted(Counter(x["stage"] for x in class_by_key.values()).items())),
        "K_special_evidence_count": sum(bool(x["special_evidence"]) for x in class_by_key.values()),
        "K_incident_evidence_count": sum(bool(x["incident_evidence"]) for x in class_by_key.values()),
        "K_missing_for_B_count": sum(x["special_status"] == "K_REPORT_MISSING" for x in class_by_key.values()),
        "historical_six_finisher_join": audit["historical_normal_joined"],
        "training_eligible_races": 0,
        "race_labels": class_by_key,
        "warnings": [
            "Six finished runners is not proof of an accident-free race.",
            "No observed special keyword is NOT proof that no operational special occurred.",
            "K-origin observations are OUTCOME_ONLY, never legal preclose features.",
            "B archives obtained after races lack authenticated preclose Freeze timestamps.",
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--b", required=True)
    p.add_argument("--k", required=True)
    p.add_argument("--day", required=True)
    p.add_argument("--summary-only", action="store_true")
    args = p.parse_args()
    day = date.fromisoformat(args.day)
    b, binfo = decode_report(args.b)
    k, kinfo = decode_report(args.k)
    if not b.startswith("STARTB") or not k.startswith("STARTK"):
        raise ValueError("official archive type mismatch")
    report = classification_audit(b, k, day)
    report["archive_sha256"] = {"B": binfo["archive_sha256"], "K": kinfo["archive_sha256"]}
    if args.summary_only:
        report.pop("race_labels")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
