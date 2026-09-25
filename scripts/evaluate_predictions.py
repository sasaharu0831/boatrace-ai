#!/usr/bin/env python3
"""Evaluate prediction and purchase logs by hit rate, return, and miss type."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('predictions', help='CSV/Parquet with race_id, bet_type, combination, stake, payout, hit')
    parser.add_argument('--output', default='data/predictions/evaluation_summary.csv')
    args = parser.parse_args()

    path = Path(args.predictions)
    df = pd.read_parquet(path) if path.suffix.lower() in {'.parquet', '.pq'} else pd.read_csv(path)
    required = {'race_id', 'bet_type', 'combination', 'stake', 'payout', 'hit'}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f'Missing required columns: {sorted(missing)}')

    df['stake'] = pd.to_numeric(df['stake'], errors='coerce').fillna(0)
    df['payout'] = pd.to_numeric(df['payout'], errors='coerce').fillna(0)
    df['hit'] = pd.to_numeric(df['hit'], errors='coerce').fillna(0).astype(bool)
    df['profit'] = df['payout'] - df['stake']
    summary = pd.DataFrame([{
        'bets': len(df),
        'races': df['race_id'].nunique(),
        'hits': int(df['hit'].sum()),
        'hit_rate': float(df['hit'].mean()),
        'stake_total': float(df['stake'].sum()),
        'payout_total': float(df['payout'].sum()),
        'return_rate': float(df['payout'].sum() / df['stake'].sum()) if df['stake'].sum() else None,
        'profit_total': float(df['profit'].sum()),
    }])
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(output, index=False)
    print(summary.to_string(index=False))


if __name__ == '__main__':
    main()
