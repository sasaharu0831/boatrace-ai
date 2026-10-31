#!/usr/bin/env python3
"""Optional DuckDB inspection of official archive manifest; no model leakage."""
import argparse
import json
from pathlib import Path

def load_manifest(manifest: Path, db_path: Path):
    try:
        import duckdb
    except ImportError as exc:
        raise SystemExit("DuckDB is not installed. Run: pip install duckdb") from exc
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS archive_manifest (
          archive_kind VARCHAR, race_date DATE, official_url VARCHAR,
          sha256 VARCHAR, captured_at_jst VARCHAR, raw_path VARCHAR,
          temporal_eligibility VARCHAR, PRIMARY KEY (archive_kind, race_date, sha256)
        )""")
        if manifest.exists():
            for row in manifest.read_text(encoding="utf-8").splitlines():
                r = json.loads(row)
                if r.get("status") != "downloaded" or r.get("temporal_eligibility") != "HISTORICAL_ONLY":
                    continue
                con.execute("""INSERT INTO archive_manifest VALUES (?, ?, ?, ?, ?, ?, ?)
                  ON CONFLICT DO NOTHING""", [r["kind"], r["date"], r["url"], r["sha256"],
                                              r["downloaded_at_jst"], r["path"], r["temporal_eligibility"]])
        rows = con.execute("SELECT archive_kind, COUNT(*) FROM archive_manifest GROUP BY 1 ORDER BY 1").fetchall()
        return dict(rows)
    finally:
        con.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("data/manifest.jsonl"))
    parser.add_argument("--db", type=Path, default=Path("data/archive.duckdb"))
    args = parser.parse_args()
    print(json.dumps(load_manifest(args.manifest, args.db), ensure_ascii=False))

if __name__ == "__main__":
    main()
