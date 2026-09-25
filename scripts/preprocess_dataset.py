#!/usr/bin/env python3
"""Normalize source tables and build a race-lane training dataset without future leakage."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {'.parquet', '.pq'}:
        return pd.read_parquet(path)
    return pd.read_csv(path, dtype={'race_id': 'string', 'racer_id': 'string'})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='config/data_sources.yaml')
    parser.add_argument('--entries', required=True)
    parser.add_argument('--results', required=True)
    parser.add_argument('--before-info')
    parser.add_argument('--output')
    args = parser.parse_args()

    with Path(args.config).open(encoding='utf-8') as f:
        config = yaml.safe_load(f)
    entries = read_table(Path(args.entries))
    results = read_table(Path(args.results))
    before_info = read_table(Path(args.before_info)) if args.before_info else None

    required_entries = {'race_id', 'race_date', 'venue_code', 'race_number', 'lane', 'racer_id'}
    required_results = {'race_id', 'lane', 'finish_position'}
    missing = (required_entries - set(entries.columns)) | (required_results - set(results.columns))
    if missing:
        raise SystemExit(f'Missing required columns: {sorted(missing)}')

    entries['race_id'] = entries['race_id'].astype('string')
    results['race_id'] = results['race_id'].astype('string')
    dataset = entries.merge(results[['race_id', 'lane', 'finish_position']], on=['race_id', 'lane'], how='inner', validate='one_to_one')
    if before_info is not None:
        before_info['race_id'] = before_info['race_id'].astype('string')
        dataset = dataset.merge(before_info, on=['race_id', 'lane'], how='left', validate='one_to_one', suffixes=('', '_before'))

    dataset['race_date'] = pd.to_datetime(dataset['race_date'], errors='coerce')
    dataset['finish_position'] = pd.to_numeric(dataset['finish_position'], errors='coerce')
    dataset['is_win'] = (dataset['finish_position'] == 1).astype('Int64')
    dataset['is_top3'] = (dataset['finish_position'] <= 3).astype('Int64')
    dataset = dataset.sort_values(['race_date', 'race_id', 'lane']).reset_index(drop=True)

    output = Path(args.output or Path(config['storage']['processed_dir']) / 'race_lane_dataset.parquet')
    output.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_parquet(output, index=False)
    print(f'Wrote {len(dataset):,} rows to {output}')


if __name__ == '__main__':
    main()
