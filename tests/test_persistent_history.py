import hashlib
import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from archive_backfill import archive_path, index_existing, connect
from historical_records import parse_program, parse_results
from historical_sqlite import persist_day
from persistent_history import assert_storage_is_local, atomic_summary, run_batch
from test_historical_records import DAY, program, results

DATA = b"\x15\x00-lh5-" + b"z" * 80


class PersistentHistoryTests(unittest.TestCase):
    def test_hosted_actions_guard(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            with self.assertRaises(RuntimeError):
                assert_storage_is_local(Path("/home/boatlab/forever"))
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}):
            with self.assertRaises(ValueError):
                assert_storage_is_local(Path("relative/data"))
            with self.assertRaises(ValueError):
                assert_storage_is_local(Path("/tmp/disposable-data"))

    def test_atomic_summary_overwrite_and_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "p" / "checkpoint.json"
            atomic_summary(target, {"count": 1})
            atomic_summary(target, {"count": 2})
            self.assertEqual(json.loads(target.read_text())["count"], 2)

    def test_offline_skips_unchanged_imported_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hashes = {}
            for kind in ("B", "K"):
                path = archive_path(root, kind, DAY)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(DATA)
                hashes[kind] = hashlib.sha256(DATA).hexdigest()
            db = root / "historical_only.sqlite3"
            persist_day(db, DAY, parse_program(program(), DAY),
                        parse_results(results(), DAY), hashes["B"], hashes["K"])
            with patch("persistent_history.assert_storage_is_local", side_effect=lambda x: x):
                report = run_batch(root, DAY, DAY, download=False)
            self.assertEqual(report["imported_days"], [])
            self.assertEqual(report["already_imported_unchanged_days"], 1)
            self.assertEqual(report["inventory"]["indexed_files"], 2)
            self.assertTrue((root / "checkpoint_latest.json").exists())

    def test_quality_checkpoint_repaired_for_existing_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            digest = hashlib.sha256(DATA).hexdigest()
            for kind in ("B", "K"):
                path = archive_path(root, kind, DAY)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(DATA)
            persist_day(root / "historical_only.sqlite3", DAY,
                        parse_program(program(), DAY), parse_results(results(), DAY),
                        digest, digest)

            def fake_decode(path):
                return (program(), {}) if path.parent.parent.name == "B" else (results(), {})

            with patch("persistent_history.assert_storage_is_local", side_effect=lambda x: x), \
                 patch("persistent_history.decode_report", side_effect=fake_decode):
                report = run_batch(root, DAY, DAY, download=False)
            self.assertEqual(report["repaired_quality_days"], [str(DAY)])
            self.assertEqual(report["import_errors"], [])
            saved = json.loads((root / "quality" / f"{DAY}.json").read_text())
            self.assertIn("202610282301", saved["race_labels"])
            self.assertEqual(saved["training_eligible_races"], 0)
            self.assertEqual(report["imported_days"], [])

    def test_import_error_is_audited(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for kind in ("B", "K"):
                path = archive_path(root, kind, DAY)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(DATA)
            with patch("persistent_history.assert_storage_is_local", side_effect=lambda x: x), \
                 patch("persistent_history.import_archives", side_effect=ValueError("bad real LZH")):
                report = run_batch(root, DAY, DAY, download=False)
            self.assertEqual(len(report["import_errors"]), 1)
            self.assertEqual(report["imported_days"], [])
            self.assertEqual(report["import_errors"][0]["day"], str(DAY))


if __name__ == "__main__":
    unittest.main()
