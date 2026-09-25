#!/usr/bin/env python3
"""Validate structural integrity and basic time-ordering of boatrace datasets."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


def read_table(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path) if path.suffix.lower() in {'.parquet', '.pq'} else pd.read_csv(path, dtype={'race_id': 'string'})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('dataset')
    args = parser.parse_args()
    df = read_table(Path(args.dataset))
    required = {'race_id', 'race_date', 'lane', 'finish_position'}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f'Missing required columns: {sorted(missing)}')

    errors: list[str] = []
    df['race_date'] = pd.to_datetime(df['race_date'], errors='coerce')
    duplicate_count = int(df.duplicated(['race_id', 'lane']).sum())
    if duplicate_count:
        errors.append(f'duplicate race_id/lane rows: {duplicate_count}')
    null_counts = df[list(required)].isna().sum()
    for column, count in null_counts.items():
        if count:
            errors.append(f'null {column}: {int(count)}')
    bad_lanes = int((~pd.to_numeric(df['lane'], errors='coerce').isin(range(1, 7))).sum())
    if bad_lanes:
        errors.append(f'invalid lanes: {bad_lanes}')
    bad_finishes = int((pd.to_numeric(df['finish_position'], errors='coerce') < 1).sum())
    if bad_finishes:
        errors.append(f'invalid finish positions: {bad_finishes}')

    races = df.groupby('race_id', dropna=False).agg(race_date=('race_date', 'first'), boats=('lane', 'nunique'))
    invalid_boat_count = int((races['boats'] > 6).sum())
    if invalid_boat_count:
        errors.append(f'races with more than 6 unique lanes: {invalid_boat_count}')

    print(f'rows={len(df):,} races={len(races):,} date_min={df.race_date.min()} date_max={df.race_date.max()}')
    if errors:
        print('VALIDATION FAILED')
        for error in errors:
            print(f'- {error}')
        sys.exit(1)
    print('VALIDATION PASSED')


if __name__ == '__main__':
    main()
