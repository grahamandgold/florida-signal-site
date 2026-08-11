import importlib.util
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("florida_signal_server", ROOT / "server.py")
server_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server_module)


class PublicApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.tempdir.name) / "public.sqlite"
        cls.db_patch = mock.patch.object(server_module, "DB_PATH", cls.db_path)
        cls.db_patch.start()
        server_module.init_db()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_module.FloridaSignalHandler)
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.db_patch.stop()
        cls.tempdir.cleanup()

    def request(self, path, method="GET", body=None, origin=None):
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(body).encode("utf-8")
        if origin:
            headers["Origin"] = origin
        request = urllib.request.Request(self.base + path, data=body, method=method, headers=headers)
        with urllib.request.urlopen(request, timeout=5) as response:
            return response, json.loads(response.read().decode("utf-8")) if method != "OPTIONS" else None

    def test_health_and_cors(self):
        response, payload = self.request(
            "/api/health", origin="https://thefloridasignal.com"
        )
        self.assertEqual(response.status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(
            response.headers["Access-Control-Allow-Origin"],
            "https://thefloridasignal.com",
        )

    def test_data_health_keeps_preliminary_and_verified_clerk_clocks_separate(self):
        def rows(path):
            if path.startswith("_meta_sync_runs"):
                return [{"completed_at": "2026-08-11T04:30:00Z", "rows_synced": 10, "errors": 0}]
            if path.startswith("permits?"):
                return [{"applied_date": "2026-08-10", "last_seen_at": "2026-08-11T03:00:00Z"}]
            if path.startswith("dashboard_cache"):
                return [{"updated_at": "2026-08-11T03:00:00Z", "payload": {"stats": {"permits_fresh": "2026-08-10", "broward_fresh": "2026-08-05"}}}]
            if path.startswith("broward_clerk_records_run"):
                return [{"business_date": "2026-08-05", "pulled_at_utc": "2026-08-10T18:11:44Z", "parse_status": "ok", "observed_doc_count": 2446}]
            if path.startswith("broward_clerk_records_doc"):
                return [{"recording_date_iso": "2026-08-05"}]
            if path.startswith("broward_clerk_preliminary"):
                return [{"record_date": "2026-08-10", "preliminary_first_seen_at": "2026-08-11T00:56:06Z", "verification_status": "preliminary", "source": "acclaimweb-public-search"}]
            raise AssertionError(path)

        with mock.patch.object(server_module, "supabase_public_rows", side_effect=rows), mock.patch.object(
            server_module, "meeting_payload", return_value={"updated_at": "2026-08-11T04:45:00Z", "meetings": []}
        ):
            server_module._health_cache.update({"at": 0.0, "payload": None})
            payload = server_module.data_health_payload()

        sources = {source["id"]: source for source in payload["sources"]}
        self.assertEqual(sources["broward"]["event_through"], "2026-08-05")
        self.assertEqual(sources["broward"]["verification"], "verified")
        self.assertEqual(sources["clerk-preliminary"]["event_through"], "2026-08-10")
        self.assertEqual(sources["clerk-preliminary"]["verification"], "preliminary")
        self.assertIn("never presented as verified early", sources["clerk-preliminary"]["detail"])
        self.assertEqual(payload["errors"], [])

    def test_signup_persists_and_repeats_idempotently(self):
        body = {
            "email": "launch-check@example.com",
            "zip": "33301",
            "cities": ["fort-lauderdale"],
            "interests": ["development"],
            "source": "integration-test",
        }
        first, first_payload = self.request("/api/subscribe", "POST", body)
        second, second_payload = self.request("/api/subscribe", "POST", body)
        self.assertEqual(first.status, 201)
        self.assertFalse(first_payload["existing"])
        self.assertEqual(second.status, 200)
        self.assertTrue(second_payload["existing"])

    def test_signup_rejects_bad_zip(self):
        body = {
            "email": "launch-check@example.com",
            "zip": "bad",
            "cities": ["fort-lauderdale"],
            "interests": ["development"],
        }
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("/api/subscribe", "POST", body)
        self.assertEqual(caught.exception.code, 422)


if __name__ == "__main__":
    unittest.main()
