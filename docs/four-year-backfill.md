# BOAT LAB: No-paid-API historical collector and conservative evaluation

## Confirmed by real GitHub Actions (2026-10-28 example)

- Official downloaded B/K archives were decompressed using free `p7zip-full` and strictly decoded as CP932.
- `historical_records.py` joined 106 six-finisher race keys by date/venue/race, validating B/K racer IDs and the K trifecta.
- `historical_sqlite.py` imported **106 races, 636 B boat rows, 636 K result rows**, then repeated the import with no duplicates.
- `quality_policy.py` separates race stages and explicitly **does not** infer absence of incidents/special operations when no keyword was found.
- `historical_export.py` exports B-derived features and K-derived outcome labels as **separate, allowlisted CSVs**. This is a historical simulation, **never** authenticated Forward.
- GitHub test execution: https://github.com/sasaharu0831/boatrace-ai/actions/runs/41080733361


## Local offline backup with no paid API

To keep history across machine failures, copy it to a **separate storage location you control** (ideally a different physical device). This repository cannot supply a disk or secretly connect a cloud account, so the actual backup destination must exist and have sufficient free space.

```bash
python src/offline_backup.py \
  --source /ABSOLUTE/PERSISTENT/DISK/boatdata \
  --backup /ABSOLUTE/SECOND-STORAGE/boatdata-backup \
  --max-files 24
```

Re-run the command to continue. Raw LZH files are immutable in the backup; changed bytes cause a hard stop for manual review, rather than overwriting. Changing `manifest.jsonl`, `checkpoint_latest.json` and quality JSON documents are saved by their SHA-256 version name. SQLite databases are backed up using the SQLite backup API and verified with `PRAGMA integrity_check`. Backups include `backup_audit.jsonl` receipts. No network API calls or subscriptions are required.

**Important:** Two directories on the *same physical drive* are not an independent backup. Files may be written to a local disk without any provider cost, but electricity, hardware and storage capacity are not guaranteed free.

## Multi-day independent verification (2026-10-27, 28, 29)

A second official-data probe succeeded on 2026-10-27 and 2026-10-29. Together with the separate 2026-10-28 verification, it produced **413 matched B/K race records and 363 historical six-finisher registration/result joins**. The stricter reconciliation discards bad B percentage stats, racer duplicates, and mismatched B/K distance before accepting a historical normal join. This is *not* an accuracy measurement and does not prove an incident-free race.

The small aggregate-and-hash checkpoint is at `research/verified_coverage_2026-10-27_to_29.json`. It contains no raw archives or race selections. To re-run an **offline** audit from archive files on a persistent local disk:

```bash
python src/multi_day_audit.py \
  --root /ABSOLUTE/PERSISTENT/DISK/boatdata \
  --dates 2026-10-27 2026-10-28 2026-10-29 \
  --require-positive
```

CI evidence: [2026-10-27/29 coverage](https://github.com/sasaharu0831/boatrace-ai/actions/runs/41089419845), [2026-10-28 join, SQLite, no-leakage CSV](https://github.com/sasaharu0831/boatrace-ai/actions/runs/41089419562). These jobs use GitHub's temporary filesystem and do not create a perpetual raw-data archive.

## Permanent local disk (zero paid API usage)

Install Python 3 and free 7zip/p7zip-full locally. Use an **absolute storage path** on a disk that you control and back up; do not use `$RUNNER_TEMP`, `/tmp` or any temporary GitHub Actions workspace.

```bash
python -m unittest discover -s tests -v
python src/archive_backfill.py plan
python src/persistent_history.py --root /ABSOLUTE/PERSISTENT/DISK/boatdata --max-files 6 --max-imports 3
python src/persistent_history.py --root /ABSOLUTE/PERSISTENT/DISK/boatdata --offline
python src/archive_backfill.py audit --root /ABSOLUTE/PERSISTENT/DISK/boatdata
python src/historical_export.py \
  --db /ABSOLUTE/PERSISTENT/DISK/boatdata/historical_only.sqlite3 \
  --features /ABSOLUTE/PERSISTENT/DISK/boatdata/exports/features_history.csv \
  --outcomes /ABSOLUTE/PERSISTENT/DISK/boatdata/restricted/outcomes_history.csv
```

`persistent_history.py` downloads at most 6 missing B/K files per call, >=2 seconds apart, then imports at most 3 available complete pairs, recording file hashes, import hashes, stage/incident evidence and an atomic checkpoint. Run it again to resume; unchanged imported days are skipped. Entries with repeated download failures can be inspected in the SQLite `attempts` table, and are not silently assumed complete.

- Sample target computed on 2026-10-30 JST: **2022-10-30 to 2026-10-29**, 1,461 dates x B/K = **2,922 possible daily files**. The target is NOT a download completion claim. Subsequent executions roll the four-year window unless `--start`/`--end` are specified.
- Keep `raw/`, `manifest.jsonl`, `archive_index.sqlite3`, `historical_only.sqlite3`, `quality/` and checkpoint files together. Back them up in a separate location. This script does not set up a cloud backup or schedule.
- Programs are retrospective copies. `nominal_deadline_jst` is printed in the program, **not** independent proof of the time the archive was downloaded or frozen.
- `HISTORICAL_ONLY` and `K_OUTCOME_ONLY` remain separate. Results and payouts must never be inputs for choosing historical "preclose" tickets.
- Six finishers are not sufficient to classify a race as incident-free. Semifinals, finals, stabilizer and other operational differences need separate denominators, and unknown markers remain `UNVERIFIED`.
- A model is **not** production-eligible until actual prior-to-deadline independent capture and Freeze are demonstrated; this repo currently has no such verified forecast run.
- One-day GitHub workflows use temporary runners and **do not preserve four years of official files**. Official raw archives and extracted personal datasets are not published from this public PR.
- A free cloud destination with automatic write permission has not been connected. To operate unattended at no paid API cost, a persistent local device/drive or an eligible explicitly connected free storage provider is still required.
- The current PR is a draft and must be reviewed before merge or any daily schedule is enabled.

Official source: https://www.boatrace.jp/owpc/pc/extra/data/download.html
