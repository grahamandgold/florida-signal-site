import hashlib
import importlib.util
import io
import json
import sqlite3
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
            if path.startswith("fdep_erp?select=received_date"):
                return [{"received_date": "2026-08-10"}]
            if path.startswith("fdep_erp?select=last_fetched_at"):
                return [{"last_fetched_at": "2026-08-11T03:10:00Z"}]
            if path.startswith("faa_oeaaa?select=date_entered"):
                return [{"date_entered": "2026-08-10"}]
            if path.startswith("faa_oeaaa?select=last_fetched_at"):
                return [{"last_fetched_at": "2026-08-11T03:20:00Z"}]
            if path.startswith("sunbiz_entities"):
                return []
            if path.startswith("broward_property_transfer_freshness"):
                return [{"snapshot_is_current": True, "snapshot_event_through": "2026-08-05", "snapshot_lag_business_days": 0, "source_age_business_days": 3}]
            if path.startswith("editorial_pipeline_health"):
                return [{
                    "component": "sunbiz-exact-resolver",
                    "status": "current",
                    "event_through": None,
                    "source_through": "2026-08-11",
                    "system_time": "2026-08-11T03:50:00Z",
                    "detail": "Private exact-match Sunbiz resolver refreshed; raw entity rows remain private.",
                    "metrics": {"exact_rows": 583},
                }]
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
        self.assertEqual(sources["sunbiz"]["status"], "current")
        self.assertEqual(sources["sunbiz"]["system_time"], "2026-08-11T03:50:00Z")
        self.assertIsNone(sources["sunbiz"]["event_through"])
        self.assertIn("remain private", sources["sunbiz"]["detail"])
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


class MailchimpUpsertTests(unittest.TestCase):
    def setUp(self):
        self.cfg = mock.patch.multiple(
            server_module,
            MAILCHIMP_API_KEY="test-key",
            MAILCHIMP_SERVER_PREFIX="us2",
            MAILCHIMP_AUDIENCE_ID="aud123",
            MAILCHIMP_ZIP_MERGE_TAG="WATCHZIP",
            MAILCHIMP_CITIES_MERGE_TAG="",
            MAILCHIMP_INTERESTS_MERGE_TAG="",
            MAILCHIMP_UTM_CAMPAIGN_TAG="UTMCAMP",
            MAILCHIMP_UTM_SOURCE_TAG="UTMSRCE",
            MAILCHIMP_UTM_MEDIUM_TAG="UTMMED",
        )
        self.cfg.start()

    def tearDown(self):
        self.cfg.stop()

    def _response(self, status=200):
        response = mock.Mock()
        response.status = status
        response.__enter__ = mock.Mock(return_value=response)
        response.__exit__ = mock.Mock(return_value=False)
        return response

    def test_subscribe_handler_lowercases_email_before_upsert(self):
        source = Path(server_module.__file__).read_text()
        self.assertIn('email = str(payload.get("email", "")).strip().lower()', source)

    def test_existing_member_is_not_written(self):
        with mock.patch.object(server_module.urllib.request, "urlopen", return_value=self._response(200)) as urlopen:
            ok = server_module.mailchimp_upsert("John@Gmail.com", "33301", ["fort-lauderdale"], ["development"])
        self.assertTrue(ok)
        self.assertEqual(urlopen.call_count, 1)
        request = urlopen.call_args[0][0]
        self.assertEqual(request.get_method(), "GET")
        expected_hash = hashlib.md5(b"john@gmail.com").hexdigest()
        self.assertIn(expected_hash, request.full_url)

    def test_new_member_created_subscribed_with_normalized_hash(self):
        not_found = urllib.error.HTTPError(
            "https://example.test/members", 404, "Not Found", hdrs={}, fp=io.BytesIO(b"{}")
        )
        created = self._response(200)

        def opener(request, timeout=12):
            if request.get_method() == "GET":
                raise not_found
            return created

        with mock.patch.object(server_module.urllib.request, "urlopen", side_effect=opener) as urlopen:
            ok = server_module.mailchimp_upsert("  John@Gmail.com ", "33301", ["fort-lauderdale"], ["development"])
        self.assertTrue(ok)
        methods = [call.args[0].get_method() for call in urlopen.call_args_list]
        self.assertEqual(methods, ["GET", "PUT"])
        put = urlopen.call_args_list[1].args[0]
        payload = json.loads(put.data.decode("utf-8"))
        self.assertEqual(payload["status_if_new"], "subscribed")
        self.assertEqual(payload["email_address"], "john@gmail.com")
        expected_hash = hashlib.md5(b"john@gmail.com").hexdigest()
        self.assertIn(expected_hash, put.full_url)
        self.assertNotIn("status", payload)
        self.assertEqual(payload["merge_fields"]["WATCHZIP"], "33301")
        self.assertNotIn("UTMCAMP", payload["merge_fields"])

    def test_new_member_writes_utm_campaign_merge_field(self):
        not_found = urllib.error.HTTPError(
            "https://example.test/members", 404, "Not Found", hdrs={}, fp=io.BytesIO(b"{}")
        )
        created = self._response(200)

        def opener(request, timeout=12):
            if request.get_method() == "GET":
                raise not_found
            return created

        with mock.patch.object(server_module.urllib.request, "urlopen", side_effect=opener) as urlopen:
            ok = server_module.mailchimp_upsert(
                "reader@example.com",
                "33301",
                ["fort-lauderdale"],
                ["development"],
                {"utm_campaign": "featured", "utm_source": "linkedin", "utm_medium": "profile"},
            )
        self.assertTrue(ok)
        payload = json.loads(urlopen.call_args_list[1].args[0].data.decode("utf-8"))
        self.assertEqual(payload["merge_fields"]["UTMCAMP"], "featured")
        self.assertEqual(payload["merge_fields"]["UTMSRCE"], "linkedin")
        self.assertEqual(payload["merge_fields"]["UTMMED"], "profile")

    def test_lookup_failure_does_not_write(self):
        with mock.patch.object(
            server_module.urllib.request,
            "urlopen",
            side_effect=urllib.error.URLError("timeout"),
        ) as urlopen:
            ok = server_module.mailchimp_upsert("john@gmail.com", "33301", ["fort-lauderdale"], ["development"])
        self.assertFalse(ok)
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(urlopen.call_args[0][0].get_method(), "GET")


class AnalyticsEventTests(unittest.TestCase):
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
            return response, json.loads(response.read().decode("utf-8"))

    def test_share_click_keeps_method_and_drops_email(self):
        response, payload = self.request(
            "/api/events",
            method="POST",
            origin="https://thefloridasignal.com",
            body={
                "event": "share_click",
                "page": "/",
                "session_id": "qa-linkedin-click",
                "properties": {
                    "method": "linkedin",
                    "device": "desktop",
                    "email": "secret@example.com",
                    "zip": "33301",
                },
            },
        )
        self.assertEqual(response.status, 201)
        self.assertTrue(payload["ok"])
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                "select event_name, page_path, properties_json from analytics_events order by id desc limit 1"
            ).fetchone()
        self.assertEqual(row[0], "share_click")
        self.assertEqual(row[1], "/")
        stored = json.loads(row[2])
        self.assertEqual(stored["method"], "linkedin")
        self.assertEqual(stored["device"], "desktop")
        self.assertNotIn("email", stored)
        self.assertNotIn("zip", stored)


if __name__ == "__main__":
    unittest.main()
