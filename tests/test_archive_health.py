import hashlib
from contextlib import closing
from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from archive_backfill import archive_path, connect, index_existing
from archive_health import inspect

DAY = date(2025, 1, 2)
HEADER = b"\x15\x00-lh5-" + b"x" * 80


class ArchiveHealthTests(unittest.TestCase):
    def test_missing_after_prior_success_keeps_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw = archive_path(root, "B", DAY)
            raw.parent.mkdir(parents=True)
            raw.write_bytes(HEADER)
            with closing(connect(root)) as con:
                index_existing(root, con, DAY, DAY)
            raw.unlink()
            report = inspect(root, DAY, DAY)
            self.assertEqual(report["expected_B_K_archives"], 2)
            self.assertEqual(report["currently_valid_sha256_archives"], 0)
            self.assertEqual(report["missing_archives"], 2)
            self.assertEqual(report["active_anomaly_count"], 1)
            self.assertEqual(report["retryable_archives"], 2)
            self.assertEqual(report["sample_anomalies"][0]["original_sha256"],
                             hashlib.sha256(HEADER).hexdigest())
            self.assertEqual(report["network_requests"], 0)

    def test_conflict_not_automatic_retry_and_history_survives_restore(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw = archive_path(root, "B", DAY)
            raw.parent.mkdir(parents=True)
            raw.write_bytes(HEADER)
            with closing(connect(root)) as con:
                index_existing(root, con, DAY, DAY)
            raw.write_bytes(HEADER[:-1] + b"z")
            report = inspect(root, DAY, DAY)
            self.assertEqual(report["changed_sha256_archives"], 1)
            self.assertEqual(report["retryable_archives"], 1)  # K only
            self.assertEqual(report["active_anomaly_count"], 1)
            raw.write_bytes(HEADER)
            restored = inspect(root, DAY, DAY)
            self.assertEqual(restored["archive_anomaly_history_events"], 2)
            self.assertEqual(restored["active_anomaly_count"], 0)
            self.assertEqual(restored["currently_valid_sha256_archives"], 1)

    def test_recovered_archive_no_longer_counted_as_retry_exhausted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with closing(connect(root)) as con:
                for _ in range(3):
                    con.execute(
                        "INSERT INTO attempts(kind,day,status,attempted_at_jst) VALUES (?,?,?,?)",
                        ("B", str(DAY), "failed", "2025-01-03T10:00:00+09:00"))
                con.commit()
            raw = archive_path(root, "B", DAY)
            raw.parent.mkdir(parents=True)
            raw.write_bytes(HEADER)
            report = inspect(root, DAY, DAY)
            self.assertEqual(report["currently_valid_sha256_archives"], 1)
            self.assertEqual(report["retry_exhausted_archives"], 0)

    def test_exhausted_failure_is_visible_without_network(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with closing(connect(root)) as con:
                for _ in range(3):
                    con.execute(
                        "INSERT INTO attempts(kind,day,status,attempted_at_jst) VALUES (?,?,?,?)",
                        ("B", str(DAY), "failed", "2025-01-03T10:00:00+09:00"))
                con.commit()
            report = inspect(root, DAY, DAY)
            self.assertEqual(report["retry_exhausted_archives"], 1)
            self.assertEqual(report["retryable_archives"], 1)  # K only
            self.assertEqual(report["forward_verified_races"], 0)
            self.assertFalse(report["data_ready_for_training"])


if __name__ == "__main__":
    unittest.main()
