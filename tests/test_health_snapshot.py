import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from health_snapshot import HealthSnapshot, collect_reads


class HealthSnapshotTests(unittest.TestCase):
    def test_slow_read_does_not_block_or_erase_other_sources(self):
        release = threading.Event()
        try:
            started = time.monotonic()
            data, errors = collect_reads({"slow": lambda: release.wait(2), "fast": lambda: 7}, timeout=.03)
            self.assertLess(time.monotonic() - started, .5)
            self.assertEqual(data, {"fast": 7})
            self.assertEqual(errors, ["slow:DeadlineExceeded"])
        finally:
            release.set()

    def test_cold_start_has_a_response_deadline_and_unknown_status(self):
        release = threading.Event()
        snapshot = HealthSnapshot({}, response_timeout=.02)
        try:
            start = time.monotonic()
            result = snapshot.get(lambda: (release.wait(2), {"sources": [], "errors": []})[1] )
            self.assertLess(time.monotonic() - start, .5)
            self.assertEqual(result["cache_status"], "unavailable")
            self.assertEqual(result["sources"], [])
            self.assertIn("health:RefreshInProgress", result["errors"])
        finally:
            release.set()

    def test_expired_snapshot_cannot_clear_an_incident(self):
        release = threading.Event()
        original = {"generated_at": "2026-01-01T00:00:00Z", "errors": [],
                    "sources": [{"id": "pdmr", "status": "current", "health_receipt_at": "old"}]}
        cache = {"at": time.monotonic() - 600, "payload": original}
        snapshot = HealthSnapshot(cache, response_timeout=.02)
        try:
            result = snapshot.get(lambda: (release.wait(2), {"sources": [], "errors": []})[1])
            self.assertEqual(result["cache_status"], "stale")
            self.assertGreater(result["sample_age_seconds"], 599)
            self.assertEqual(result["generated_at"], original["generated_at"])
            self.assertEqual(result["sources"][0]["status"], "unavailable")
            self.assertEqual(result["sources"][0]["last_known_status"], "current")
            self.assertEqual(result["sources"][0]["health_receipt_at"], "old")
            self.assertEqual(original["sources"][0]["status"], "current")
        finally:
            release.set()

    def test_concurrent_requests_share_one_refresh(self):
        calls = []
        release = threading.Event()
        snapshot = HealthSnapshot({}, response_timeout=.02)
        def builder():
            calls.append(1)
            release.wait(2)
            return {"sources": [], "errors": []}
        try:
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: snapshot.get(builder), range(8)))
            self.assertEqual(len(calls), 1)
            self.assertTrue(all(r["cache_status"] == "unavailable" for r in results))
        finally:
            release.set()

    def test_successful_snapshot_is_cached_and_caller_cannot_mutate_it(self):
        snapshot = HealthSnapshot({})
        calls = []
        def builder():
            calls.append(1)
            return {"sources": [{"id": "a", "status": "stale"}], "errors": ["a:HTTPError"]}
        result = snapshot.get(builder)
        result["sources"][0]["status"] = "current"
        second = snapshot.get(builder)
        self.assertEqual(calls, [1])
        self.assertEqual(second["sources"][0]["status"], "stale")
        self.assertEqual(second["errors"], ["a:HTTPError"])

    def test_failed_builder_keeps_unknown_status_and_backs_off(self):
        calls = []
        snapshot = HealthSnapshot({})
        def broken():
            calls.append(1)
            raise RuntimeError("private-path-must-not-leak")
        result = snapshot.get(broken)
        again = snapshot.get(broken)
        self.assertEqual(calls, [1])
        self.assertEqual(result["errors"], ["health:RuntimeError"])
        self.assertEqual(again["cache_status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
