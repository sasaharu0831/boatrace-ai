import sys
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from archive_backfill import (
    default_window, archive_path, connect, index_existing, pending, run_limited
)

FAKE_LZH_HEADER = b"\x15\x00-lh5-" + b"a" * 80  # Header shape only, NOT a decompression test.


class BackfillTests(unittest.TestCase):
    def test_four_year_window(self):
        self.assertEqual(default_window(date(2026, 10, 30)),
                         (date(2022, 10, 30), date(2026, 10, 29)))
        self.assertEqual(default_window(date(2024, 2, 29)),
                         (date(2020, 2, 29), date(2024, 2, 28)))

    def test_index_is_hash_checked_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = archive_path(root, "B", date(2025, 1, 2))
            path.parent.mkdir(parents=True)
            path.write_bytes(FAKE_LZH_HEADER)
            with closing(connect(root)) as con:
                first = index_existing(root, con, date(2025, 1, 2), date(2025, 1, 2))
                self.assertEqual(first["indexed_files"], 1)
                self.assertEqual(len(list(pending(con, date(2025, 1, 2), date(2025, 1, 2)))), 1)
                path.write_bytes(b"<html>not LZH</html>")
                second = index_existing(root, con, date(2025, 1, 2), date(2025, 1, 2))
                self.assertEqual(second["invalid_files"], 1)
                self.assertEqual(len(list(pending(con, date(2025, 1, 2), date(2025, 1, 2)))), 2)

    def test_limited_no_repeat_cached_and_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def fake(kind, day, root):
                path = archive_path(root, kind, day)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(FAKE_LZH_HEADER)
                return {"status": "downloaded"}

            with patch("archive_backfill.time.sleep"):
                first = run_limited(root, date(2025, 1, 2), date(2025, 1, 2),
                                    max_files=2, downloader=fake)
            self.assertEqual(first["indexed_files"], 2)
            self.assertEqual(len(first["attempted"]), 2)
            second = run_limited(root, date(2025, 1, 2), date(2025, 1, 2),
                                 max_files=2, downloader=fake)
            self.assertEqual(second["attempted"], [])
            self.assertFalse(second["forward_eligible"])

    def test_failures_exhausted_after_three(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def fail(kind, day, root):
                raise OSError("offline")

            for _ in range(3):
                with patch("archive_backfill.time.sleep"):
                    result = run_limited(root, date(2025, 1, 2), date(2025, 1, 2),
                                         max_files=2, downloader=fail)
                self.assertEqual(len(result["attempted"]), 2)
            result = run_limited(root, date(2025, 1, 2), date(2025, 1, 2),
                                 max_files=2, downloader=fail)
            self.assertEqual(result["attempted"], [])
            self.assertEqual(result["remaining_retryable"], 0)
            self.assertEqual(result["indexed_files"], 0)

    def test_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                run_limited(root, date(2025, 1, 1), date(2025, 1, 1), max_files=7)
            with self.assertRaises(ValueError):
                run_limited(root, date(2025, 1, 1), date(2025, 1, 1),
                            sleep_seconds=1)


if __name__ == "__main__":
    unittest.main()
