#!/usr/bin/env python3
"""Download daily boatrace source files for a configured date range."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator

import requests
import yaml


def iter_dates(start: date, end: date) -> Iterator[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def load_config(path: Path) -> dict:
    with path.open(encoding='utf-8') as f:
        return yaml.safe_load(f)


def fetch(url: str, destination: Path, timeout: int, retries: int) -> dict:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        return {'status': 'skipped', 'path': str(destination)}
    last_error = None
    for attempt in range(retries + 1):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            destination.write_bytes(response.content)
            return {
                'status': 'downloaded',
                'path': str(destination),
                'bytes': len(response.content),
                'sha256': hashlib.sha256(response.content).hexdigest(),
            }
        except requests.RequestException as exc:
            last_error = str(exc)
            if attempt < retries:
                time.sleep(2 ** attempt)
    return {'status': 'failed', 'path': str(destination), 'error': last_error}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='config/data_sources.yaml')
    parser.add_argument('--start-date')
    parser.add_argument('--end-date')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    config = load_config(Path(args.config))
    project = config['project']
    source = config['source']
    raw_dir = Path(config['storage']['raw_dir'])
    start = datetime.strptime(args.start_date or project['start_date'], '%Y-%m-%d').date()
    end = datetime.strptime(args.end_date or project['end_date'], '%Y-%m-%d').date()
    base_url = source.get('base_url', '').rstrip('/')
    templates = source.get('file_templates', {})
    if not base_url or not any(templates.values()):
        raise SystemExit('Set source.base_url and at least one source.file_templates value in config/data_sources.yaml after terms verification.')

    manifest_path = raw_dir / 'manifest.jsonl'
    with manifest_path.open('a', encoding='utf-8') as manifest:
        for target_date in iter_dates(start, end):
            values = {'date': target_date.strftime('%Y%m%d'), 'year': target_date.strftime('%Y'), 'month': target_date.strftime('%m'), 'day': target_date.strftime('%d')}
            for table, template in templates.items():
                if not template:
                    continue
                relative = template.format(**values).lstrip('/')
                url = f'{base_url}/{relative}'
                destination = raw_dir / table / target_date.strftime('%Y') / target_date.strftime('%m') / Path(relative).name
                record = {'table': table, 'date': target_date.isoformat(), 'url': url}
                if args.dry_run:
                    record['status'] = 'planned'
                else:
                    record.update(fetch(url, destination, source.get('request_timeout_seconds', 30), source.get('retry_count', 3)))
                    time.sleep(float(source.get('rate_limit_seconds', 1.0)))
                manifest.write(json.dumps(record, ensure_ascii=False) + '
')
                manifest.flush()


if __name__ == '__main__':
    main()
