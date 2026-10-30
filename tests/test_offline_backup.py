import hashlib
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from offline_backup import backup, copy_verified, separate_roots, sha256

FAKE_LZH = b"\x15\x00-lh5-" + b"abc123" * 11


class OfflineBackupTests(unittest.TestCase):
    def test_verified_copy_and_resume(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "source"
            dst = Path(td) / "second-storage"
            src.mkdir()
            raw = src / "raw" / "B" / "2026"
            raw.mkdir(parents=True)
            path = raw / "b261028.lzh"
            path.write_bytes(FAKE_LZH)
            with patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}):
                first = backup(src, dst, max_files=1)
                second = backup(src, dst, max_files=1)
            target = dst / "files" / "raw" / "B" / "2026" / "b261028.lzh"
            self.assertEqual(first["new_file_copies"], ["raw/B/2026/b261028.lzh"])
            self.assertEqual(second["new_file_copies"], [])
            self.assertEqual(second["matching_existing_files"], 1)
            self.assertEqual(sha256(target), hashlib.sha256(FAKE_LZH).hexdigest())
            self.assertTrue((dst / "backup_audit.jsonl").exists())

    def test_changed_destination_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            src, dest = Path(td) / "source", Path(td) / "target"
            source = src / "raw" / "K" / "2026"
            source.mkdir(parents=True)
            path = source / "k261028.lzh"
            path.write_bytes(FAKE_LZH)
            with patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}):
                backup(src, dest, max_files=1)
                dst_file = dest / "files" / "raw" / "K" / "2026" / "k261028.lzh"
                dst_file.write_bytes(b"tampered")
                report = backup(src, dest, max_files=1)
            self.assertEqual(len(report["conflicts"]), 1)
            self.assertEqual(dst_file.read_bytes(), b"tampered")

    def test_sqlite_is_snapshotted_and_checked(self):
        with tempfile.TemporaryDirectory() as td:
            src, dest = Path(td) / "source", Path(td) / "backup"
            src.mkdir()
            database = src / "historical_only.sqlite3"
            with sqlite3.connect(database) as con:
                con.execute("CREATE TABLE t(v TEXT)")
                con.execute("INSERT INTO t(v) VALUES ('readable')")
                con.commit()
            with patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}):
                record = backup(src, dest)
            self.assertEqual(len(record["sqlite_snapshots"]), 1)
            path = Path(record["sqlite_snapshots"][0]["file"])
            self.assertTrue(path.is_file())
            with sqlite3.connect(path) as con:
                self.assertEqual(con.execute("SELECT v FROM t").fetchone()[0], "readable")

    def test_paths_not_nested_or_ephemeral_ci(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "source"
            src.mkdir()
            with patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}):
                with self.assertRaises(ValueError):
                    separate_roots(src, src / "nested")
                with self.assertRaises(ValueError):
                    separate_roots(src, src)
                with self.assertRaises(ValueError):
                    separate_roots(Path("relative"), Path(td) / "target")
            with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
                with self.assertRaises(RuntimeError):
                    separate_roots(src, Path(td) / "different")

    def test_copy_rejects_oversized_file(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "s"
            dst = Path(td) / "d"
            src.write_bytes(b"abcdefghij")
            with self.assertRaises(ValueError):
                copy_verified(src, dst, max_bytes=5)
            self.assertFalse(dst.exists())


if __name__ == "__main__":
    unittest.main()
