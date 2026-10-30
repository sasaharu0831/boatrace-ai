import io
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from boat_free_lab import archive_url, collect, download_archive, evaluate, is_lzh, validate_freeze

class FakeResponse(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *args): self.close()

class FreeLabTests(unittest.TestCase):
    def test_archive_url(self):
        self.assertEqual(archive_url("B", date(2026, 10, 30)),
            "https://www1.mbrace.or.jp/od2/B/202610/b261030.lzh")
        with self.assertRaises(ValueError): archive_url("P", date.today())

    def test_collect_bounded_manifest(self):
        archive = b"\x15\x00-lh5-" + b"a" * 80
        def opener(req, timeout): return FakeResponse(archive)
        with tempfile.TemporaryDirectory() as d:
            out = collect(date(2025, 1, 1), 1, Path(d), opener=opener, sleep_seconds=0)
            self.assertEqual(len(out), 2)
            self.assertTrue(all(x["status"] == "downloaded" for x in out))
            self.assertTrue(all(x["temporal_eligibility"] == "HISTORICAL_ONLY" for x in out))
            self.assertEqual(len((Path(d) / "manifest.jsonl").read_text().splitlines()), 2)
            again = collect(date(2025, 1, 1), 1, Path(d), opener=opener, sleep_seconds=0)
            self.assertTrue(all(x["status"] == "cached" for x in again))

    def test_damaged_existing_archive_kept_for_manual_recovery(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            day = date(2025, 1, 1)
            path = root / "raw" / "B" / "2025" / "b250101.lzh"
            path.parent.mkdir(parents=True)
            original = b"<html>bad local file</html>"
            path.write_bytes(original)
            def forbidden_opener(*args, **kwargs):
                raise AssertionError("should never overwrite or download")
            with self.assertRaisesRegex(ValueError, "invalid signature"):
                download_archive("B", day, root, opener=forbidden_opener)
            self.assertEqual(path.read_bytes(), original)

    def test_oversized_existing_archive_is_never_loaded_or_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            day = date(2025, 1, 1)
            path = root / "raw" / "B" / "2025" / "b250101.lzh"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"\\x15\\x00-lh5-" + b"x" * 120)
            with self.assertRaisesRegex(ValueError, "invalid or oversized"):
                download_archive("B", day, root, max_bytes=100)
            self.assertEqual(path.stat().st_size, 127)

    def test_reject_html_and_long_horizon(self):
        self.assertFalse(is_lzh(b"<html>hi</html>"))
        with self.assertRaises(ValueError): collect(date(2025, 1, 1), 4, Path("ignored"), sleep_seconds=0)

    def test_temporal_gate(self):
        base = {"race_key": "202610300101", "source_time_jst": "2026-10-30T11:00:00+09:00",
                "deadline_jst": "2026-10-30T11:30:00+09:00", "capture_sha256": "a" * 64,
                "source_url": "https://www.boatrace.jp/", "verified_preclose": True}
        pred = {"race_key": base["race_key"], "freeze_time_jst": "2026-10-30T11:25:00+09:00",
                "tickets": ["1-2-3", "1-3-2"]}
        validate_freeze(base, pred)
        with self.assertRaises(ValueError):
            validate_freeze(dict(base, verified_preclose=False), pred)
        with self.assertRaises(ValueError):
            validate_freeze(base, dict(pred, freeze_time_jst="2026-10-30T11:31:00+09:00"))
        with self.assertRaises(ValueError):
            validate_freeze(base, dict(pred, tickets=["1-1-2"]))

    def test_outcome_scoring_separation(self):
        preds = [{"race_key": "A", "status": "FORWARD_VERIFIED", "tickets": ["1-2-3", "1-3-2"]},
                 {"race_key": "B", "status": "SHADOW", "tickets": ["2-3-1"]},
                 {"race_key": "C", "status": "FORWARD_VERIFIED", "tickets": ["1-2-3"]}]
        out = [{"race_key": "A", "incident": False, "trifecta": "1-2-3", "payout_yen_per_100": 360},
               {"race_key": "B", "incident": False, "trifecta": "2-3-1", "payout_yen_per_100": 9999},
               {"race_key": "C", "incident": True, "trifecta": "1-2-3", "payout_yen_per_100": 100}]
        r = evaluate(preds, out)
        self.assertEqual(r["eligible_races"], 1)
        self.assertEqual(r["hits"], 1)
        self.assertEqual(r["return_rate"], 1.8)
        self.assertEqual(evaluate([], [])["hit_rate"], None)

if __name__ == "__main__": unittest.main()
