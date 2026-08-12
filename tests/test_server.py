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

    def test_postgres_fractional_timestamp_keeps_its_time_of_day(self):
        parsed = server_module.parse_source_time("2026-08-11T23:40:15.61819+00:00")
        self.assertIsNotNone(parsed)
        self.assertEqual((parsed.hour, parsed.minute, parsed.second), (23, 40, 15))
        self.assertEqual(parsed.microsecond, 618190)

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
