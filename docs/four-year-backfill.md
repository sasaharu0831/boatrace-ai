# BOAT LAB: 4-year historical backfill (no paid APIs)

Run on a persistent disk. GitHub-hosted Actions runners are temporary and **do not preserve the last run's files**.

```bash
python -m unittest discover -s tests -v
python src/archive_backfill.py plan
python src/archive_backfill.py run --root /PATH/TO/PERSISTENT/boatdata --max-files 6
python src/archive_backfill.py audit --root /PATH/TO/PERSISTENT/boatdata
```

- On 2026-10-30 JST the four-year inclusive target is **2022-10-30 through 2026-10-29**, totaling 1,461 days x B/K = **2,922 expected archives**. This is a plan, NOT successful downloads.
- Per execution at most six B/K downloads, >=2 seconds apart, no futures/current day. HTTP errors are logged and after three failures each unavailable file is skipped, **but remains missing** in the audit.
- Repeated runs inspect real local files, validate basic LZH signatures, recompute SHA256 and reconcile `archive_index.sqlite3`. The original downloaded LZH and `manifest.jsonl` must be retained; the DB alone cannot reconstruct raw files.
- A matching local manifest record proves only that the local file and a prior download receipt agree. It is NOT a third-party verified provenance or genuine pre-close freeze.
- LZH decompression and per-race CSV/SQL normalization are **not yet implemented or proven**. The index only tracks B/K file coverage.
- All historical archives are HISTORICAL_ONLY, never FORWARD_VERIFIED; results or payouts must not enter preclose ticket selection.
- The GitHub PR remains draft. Merging is not automatic. The existing scheduled workflow can collect only recent short-lived archives and should not be mistaken for a four-year permanent archive.
- A permanent, automatically writable personal storage destination needs to be configured separately before unattended full backfill can actually persist.

Official download directory: https://www.boatrace.jp/owpc/pc/extra/data/download.html
