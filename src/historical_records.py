#!/usr/bin/env python3
"""Conservative historical B/K record parser and leakage-safe audit.

Official daily archives downloaded AFTER a race are historical-only even when
the B program contains nominally pre-race fields. Never relabel as FORWARD.
"""
from __future__ import annotations
from datetime import date
import json
import re
import unicodedata

VENUE_MARKER = re.compile(r"^([0-2][0-9])([BK])BGN$")
B_ENTRY = re.compile(
    r"^\s*([1-6])\s*(\d{4})([^0-9]+?)(\d{2})([^\d\s]{2})(\d{2})(A1|A2|B1|B2)\s+"
    r"(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+"
    r"(\d{1,2})\s+(\d+\.\d+)\s+(\d{1,2})\s+(\d+\.\d+)"
)
K_FINISH = re.compile(r"^\s*(0[1-6])\s+([1-6])\s+(\d{4})\s+")


def normalize(s):
    return unicodedata.normalize("NFKC", s)


def race_key(day, venue, rno):
    return f"{day:%Y%m%d}{venue}{rno:02d}"


def sections(text, kind):
    current = None
    lines = []
    for line in text.splitlines():
        m = VENUE_MARKER.fullmatch(line.strip())
        if m and m.group(2) == kind:
            if current is not None:
                yield current, lines
            code = int(m.group(1))
            if not 1 <= code <= 24:
                raise ValueError(f"unknown venue {code}")
            current = f"{code:02d}"
            lines = []
        elif current is not None:
            lines.append(line)
    if current is not None:
        yield current, lines


def parse_program(text, day: date):
    """B: only high-confidence fields; require exactly six clean entries per race."""
    races, entries, issues = {}, {}, []
    for venue, lines in sections(text, "B"):
        key = None
        for line in lines:
            n = normalize(line)
            head = re.match(
                r"^\s*(\d{1,2})R\s+(.+?)\s+H(\d+)m\s+電話投票締切予定(\d{2}):(\d{2})", n)
            if head:
                rno = int(head.group(1))
                if not 1 <= rno <= 12:
                    issues.append(["invalid_race", venue, rno])
                    key = None
                    continue
                key = race_key(day, venue, rno)
                if key in races:
                    issues.append(["duplicate_B_race", key])
                    key = None
                    continue
                races[key] = {
                    "race_key": key, "date": str(day), "venue": venue, "race": rno,
                    "race_name": head.group(2).strip(), "distance_m": int(head.group(3)),
                    "deadline_jst": f"{day}T{head.group(4)}:{head.group(5)}:00+09:00",
                    "source": "B_HISTORICAL_ONLY"
                }
                entries[key] = []
                continue
            if key is None:
                continue
            m = B_ENTRY.match(n)
            if not m:
                continue
            boat, racer = int(m.group(1)), int(m.group(2))
            entry = {
                "race_key": key, "boat": boat, "racer": racer,
                "name": re.sub(r"\s+", "", m.group(3)), "age": int(m.group(4)),
                "branch": m.group(5), "weight_kg": int(m.group(6)),
                "class": m.group(7),
                "national_win_rate": float(m.group(8)),
                "national_2rate": float(m.group(9)),
                "local_win_rate": float(m.group(10)),
                "local_2rate": float(m.group(11)),
                "motor_number": int(m.group(12)), "motor_2rate": float(m.group(13)),
                "boat_number": int(m.group(14)), "boat_2rate": float(m.group(15)),
                "source": "B_HISTORICAL_ONLY"
            }
            entries[key].append(entry)
    for key, rows in entries.items():
        if len(rows) != 6 or {r["boat"] for r in rows} != set(range(1, 7)) or len({r["racer"] for r in rows}) != 6:
            issues.append(["incomplete_or_duplicate_B_entries", key, len(rows)])
        for r in rows:
            if not (0 <= r["motor_2rate"] <= 100 and 0 <= r["boat_2rate"] <= 100
                    and 0 <= r["national_2rate"] <= 100 and 0 <= r["local_2rate"] <= 100):
                issues.append(["out_of_range_B", key, r["boat"]])
    return races, entries, issues


def parse_results(text, day: date):
    """K: finish order and payout stay strictly in the outcome side of the DB."""
    races, entries, payouts, issues = {}, {}, {}, []
    for venue, lines in sections(text, "K"):
        key = None
        for line in lines:
            n = normalize(line)
            # Summary payout table occurs before detailed race reports.
            payout = re.match(r"^\s*(\d{1,2})R\s+([1-6]-[1-6]-[1-6])\s+([\d,]+)\s+", n)
            if payout:
                rno = int(payout.group(1))
                if 1 <= rno <= 12:
                    pkey = race_key(day, venue, rno)
                    ticket = payout.group(2)
                    if len(set(ticket.split("-"))) == 3:
                        payouts[pkey] = {"race_key": pkey, "trifecta": ticket,
                                         "payout_yen_per_100": int(payout.group(3).replace(",", "")),
                                         "source": "K_OUTCOME_ONLY"}
                continue
            head = re.match(r"^\s*(\d{1,2})R\s+(.+?)\s+H(\d+)m(?:\s|$)", n)
            if head:
                rno = int(head.group(1))
                if not 1 <= rno <= 12:
                    key = None
                    continue
                key = race_key(day, venue, rno)
                if key in races:
                    issues.append(["duplicate_K_race", key])
                    key = None
                    continue
                races[key] = {"race_key": key, "date": str(day), "venue": venue,
                              "race": rno, "distance_m": int(head.group(3)),
                              "source": "K_OUTCOME_ONLY"}
                entries[key] = []
                continue
            if key is None:
                continue
            m = K_FINISH.match(n)
            if m:
                entries[key].append({"race_key": key, "finish": int(m.group(1)),
                                     "boat": int(m.group(2)), "racer": int(m.group(3)),
                                     "source": "K_OUTCOME_ONLY"})
    for key, rows in entries.items():
        finishes = [r["finish"] for r in rows]
        boats = [r["boat"] for r in rows]
        if sorted(finishes) != list(range(1, 7)) or sorted(boats) != list(range(1, 7)):
            issues.append(["non_normal_six_finisher_K", key, len(rows)])
        elif key in payouts:
            actual = "-".join(str(next(r["boat"] for r in rows if r["finish"] == rank)) for rank in (1, 2, 3))
            if actual != payouts[key]["trifecta"]:
                issues.append(["payout_finish_mismatch", key, actual, payouts[key]["trifecta"]])
        else:
            issues.append(["missing_K_trifecta", key])
    return races, entries, payouts, issues


def reconcile(b_data, k_data):
    br, be, bi = b_data
    kr, ke, kp, ki = k_data
    problems = list(bi) + list(ki)
    # A flagged race cannot slip into the normal historical pool merely because
    # its six boat / racer IDs happen to match between B and K.
    flagged = {row[1] for row in problems if len(row) > 1 and isinstance(row[1], str)}
    eligible = []
    for key in sorted(set(br) & set(kr)):
        b = be[key]
        k = ke[key]
        if key in flagged or len(b) != 6 or len(k) != 6 or key not in kp:
            continue
        if len({x["boat"] for x in b}) != 6 or len({x["racer"] for x in b}) != 6:
            problems.append(["duplicate_B_boat_or_racer", key])
            continue
        if len({x["boat"] for x in k}) != 6 or len({x["racer"] for x in k}) != 6:
            problems.append(["duplicate_K_boat_or_racer", key])
            continue
        if br[key]["distance_m"] != kr[key]["distance_m"]:
            problems.append(["B_K_distance_mismatch", key])
            continue
        if sorted(r["finish"] for r in k) != list(range(1, 7)):
            continue
        map_b = {r["boat"]: r["racer"] for r in b}
        map_k = {r["boat"]: r["racer"] for r in k}
        if len(map_b) != 6 or len(map_k) != 6 or map_b != map_k:
            problems.append(["B_K_registration_mismatch", key])
            continue
        actual = "-".join(str(next(r["boat"] for r in k if r["finish"] == i)) for i in (1, 2, 3))
        if actual != kp[key]["trifecta"]:
            continue
        eligible.append(key)
    return {
        "B_races": len(br), "K_races": len(kr), "paired_races": len(set(br) & set(kr)),
        "historical_normal_joined": len(eligible), "normal_race_keys": eligible,
        "issues": problems, "forward_eligible": False,
        "note": "These keys are HISTORICAL_ONLY; no proof of predeadline capture or predictions."
    }


def main(argv=None):
    import argparse
    from pathlib import Path
    from lzh_extract import decode_report
    p = argparse.ArgumentParser()
    p.add_argument("--b", required=True, type=Path)
    p.add_argument("--k", required=True, type=Path)
    p.add_argument("--day", required=True)
    args = p.parse_args(argv)
    day = date.fromisoformat(args.day)
    b, bmeta = decode_report(args.b)
    k, kmeta = decode_report(args.k)
    if not b.startswith("STARTB") or not k.startswith("STARTK"):
        raise ValueError("archive B/K type mismatch")
    summary = reconcile(parse_program(b, day), parse_results(k, day))
    summary["B_sha256"] = bmeta["archive_sha256"]
    summary["K_sha256"] = kmeta["archive_sha256"]
    # Strictly no published raw archive or unverified feature feed.
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
