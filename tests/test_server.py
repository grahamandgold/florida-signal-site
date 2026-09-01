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
from datetime import date, datetime, timezone
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

    def request(self, path, method="GET", body=None, origin=None, extra_headers=None):
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(body).encode("utf-8")
        if origin:
            headers["Origin"] = origin
        if extra_headers:
            headers.update(extra_headers)
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

    def test_preliminary_business_calendar_and_receipt_health(self):
        sunday = datetime(2026, 8, 30, 23, 0, tzinfo=timezone.utc)
        monday_after_release = datetime(2026, 8, 31, 17, 0, tzinfo=timezone.utc)
        fresh_run = {"status": "source_wait", "completed_at": "2026-08-30T22:59:00Z"}

        self.assertEqual(server_module.business_calendar_age("2026-08-28", now=sunday), 0)
        self.assertEqual(
            server_module.business_calendar_age("2026-08-28", now=monday_after_release), 1
        )
        self.assertEqual(
            server_module.business_calendar_age(
                "2026-08-28",
                now=monday_after_release,
                holidays={date(2026, 8, 31)},
            ),
            0,
        )
        self.assertEqual(
            server_module.preliminary_clerk_status("2026-08-28", fresh_run, now=sunday),
            "current",
        )
        self.assertEqual(
            server_module.preliminary_clerk_status(
                "2026-08-28",
                {"status": "failed", "completed_at": "2026-08-30T22:59:00Z"},
                now=sunday,
            ),
            "error",
        )

    def test_preliminary_clock_source_keeps_fetch_only_health_unknown(self):
        source = (ROOT / "server.py").read_text(encoding="utf-8")
        self.assertIn('else "row_fetch_only_no_terminal_receipt"', source)
        self.assertIn("row fetch time is not collector health", source)

    def test_supabase_health_read_retries_one_transient_server_error(self):
        transient = urllib.error.HTTPError("https://example.invalid", 500, "timeout", {}, None)
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'[{"last_fetched_at":"2026-08-30T09:21:10Z"}]'
        with mock.patch.object(urllib.request, "urlopen", side_effect=[transient, response]) as open_url, \
                mock.patch.object(server_module.time, "sleep") as pause:
            rows = server_module.supabase_public_rows("fdep_erp?select=last_fetched_at&limit=1")
        self.assertEqual(rows[0]["last_fetched_at"], "2026-08-30T09:21:10Z")
        self.assertEqual(open_url.call_count, 2)
        pause.assert_called_once_with(0.15)

    def test_pdmr_health_summary_requires_hash_bound_natural_and_four_table_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            collector_dir = root / "collector"
            health_dir = root / "health"
            collector_dir.mkdir()
            health_dir.mkdir()

            def write_json(path, value):
                raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
                path.write_bytes(raw)
                return hashlib.sha256(raw).hexdigest()

            collector_receipt = {
                "schema_version": "FloridaSignalPdmrCollectorReceiptV3",
                "receipt_kind": "pdmr_collector_terminal",
                "run_id": "natural-run-1",
                "started_at": "2026-09-01T09:00:00+00:00",
                "finished_at": "2026-09-01T09:01:00+00:00",
                "status": "ok",
                "exit_code": 0,
                "invocation": "scheduled_live",
                "counts": {
                    "attempted": 25, "inserted": 1, "updated": 2,
                    "migrated": 0, "unchanged": 22,
                    "rejected": 0, "errors": 0,
                },
                "database_run": {"records_seen": 35},
            }
            collector_path = collector_dir / "live-natural-run-1.json"
            collector_sha = write_json(collector_path, collector_receipt)
            collector_pointer = {
                "schema_version": "FloridaSignalPdmrCollectorLatestPointerV1",
                "run_id": "natural-run-1", "status": "ok", "exit_code": 0,
                "receipt_path": str(collector_path), "receipt_sha256": collector_sha,
            }
            table_proof = {
                "status": "passed",
                "local": {"count": 329, "pk_set_sha256": "a" * 64, "rowset_sha256": "b" * 64},
                "supabase": {"count": 329, "pk_set_sha256": "a" * 64, "rowset_sha256": "b" * 64},
            }
            unit_proof = {
                "status": "passed", "timer_enabled": True, "timer_active": True,
                "trigger_start_skew_seconds": 0.001,
            }
            report = {
                "schema_version": "FloridaSignalPdmrHealthReceiptV2",
                "receipt_kind": "pdmr_health_terminal",
                "generated_at": "2026-09-01T09:20:00+00:00",
                "status": "healthy", "alert_count": 0, "alerts": [],
                "automation_proof": {
                    "status": "passed", "collector_invocation": "scheduled_live",
                    "collector_run_id": "natural-run-1",
                    "units": {"collector": unit_proof, "mirror": unit_proof, "health": unit_proof},
                },
                "collector": {"latest_pointer": collector_pointer},
                "local": {"events": 329, "versions": 329, "unresolved_failures": 0, "abandoned_failures": 0, "orphan_running_rows": 0},
                "mirror": {
                    "latest_pointer": {"status": "success", "updated_at": "2026-09-01T09:20:10+00:00"},
                    "cohort": {"status": "complete", "has_more": False},
                    "parity": {
                        "status": "passed",
                        "tables": {
                            "parcel_events": table_proof,
                            "parcel_event_versions": table_proof,
                            "pdmr_collection_failures": {**table_proof, "local": {**table_proof["local"], "count": 0}, "supabase": {**table_proof["supabase"], "count": 0}},
                            "pdmr_collection_runs": {**table_proof, "local": {**table_proof["local"], "count": 1}, "supabase": {**table_proof["supabase"], "count": 1}},
                        },
                    },
                },
            }
            health_path = health_dir / "health-natural-run-1.json"
            health_sha = write_json(health_path, report)
            latest = root / "health-latest.json"
            write_json(latest, {
                "schema_version": "FloridaSignalPdmrHealthLatestV1",
                "status": "healthy", "alert_count": 0,
                "receipt_path": str(health_path), "receipt_sha256": health_sha,
            })
            with mock.patch.multiple(
                server_module,
                PDMR_HEALTH_LATEST_PATH=latest,
                PDMR_HEALTH_RECEIPT_DIR=health_dir,
                PDMR_COLLECTOR_RECEIPT_DIR=collector_dir,
            ):
                summary = server_module.pdmr_health_summary()
            self.assertEqual(summary["status"], "verified")
            self.assertEqual(summary["natural_schedule_proof"], "passed")
            self.assertEqual(summary["local"]["events"], 329)
            self.assertEqual(summary["mirror"]["tables"]["parcel_events"]["supabase_count"], 329)
            self.assertEqual(summary["collector"]["records_attempted"], 25)
            self.assertEqual(summary["collector"]["records_written"], 3)
            self.assertEqual(summary["collector"]["records_rejected"], 0)
            self.assertNotIn(str(root), json.dumps(summary))

            report["automation_proof"]["units"]["collector"] = {
                **unit_proof, "status": "unverified",
            }
            health_sha = write_json(health_path, report)
            write_json(latest, {
                "schema_version": "FloridaSignalPdmrHealthLatestV1",
                "status": "healthy", "alert_count": 0,
                "receipt_path": str(health_path), "receipt_sha256": health_sha,
            })
            with mock.patch.multiple(
                server_module,
                PDMR_HEALTH_LATEST_PATH=latest,
                PDMR_HEALTH_RECEIPT_DIR=health_dir,
                PDMR_COLLECTOR_RECEIPT_DIR=collector_dir,
            ):
                manual = server_module.pdmr_health_summary()
            self.assertEqual(manual["status"], "unverified")
            self.assertEqual(manual["natural_schedule_proof"], "unverified")

            write_json(latest, {
                "schema_version": "FloridaSignalPdmrHealthLatestV1",
                "status": "healthy", "alert_count": 0,
                "receipt_path": str(health_path), "receipt_sha256": "0" * 64,
            })
            with mock.patch.multiple(
                server_module,
                PDMR_HEALTH_LATEST_PATH=latest,
                PDMR_HEALTH_RECEIPT_DIR=health_dir,
                PDMR_COLLECTOR_RECEIPT_DIR=collector_dir,
            ), self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                server_module.pdmr_health_summary()

    def test_data_health_keeps_preliminary_and_verified_clerk_clocks_separate(self):
        def rows(path):
            if path.startswith("_meta_sync_runs"):
                return [{"completed_at": "2026-08-11T04:30:00Z", "rows_synced": 10, "errors": 2}]
            if path.startswith("permits?"):
                return [{"applied_date": "2026-08-10", "last_seen_at": "2026-08-11T03:00:00Z"}]
            if path.startswith("dashboard_cache"):
                return [{"updated_at": "2026-08-11T03:00:00Z", "payload": {"stats": {"permits_fresh": "2026-08-10", "broward_fresh": "2026-08-05"}}}]
            if path.startswith("broward_clerk_records_run"):
                return [{"business_date": "2026-08-05", "pulled_at_utc": "2026-08-10T18:11:44Z", "parse_status": "ok", "observed_doc_count": 2446}]
            if path.startswith("broward_clerk_records_doc"):
                return [{"recording_date_iso": "2026-08-05"}]
            if path.startswith("broward_clerk_preliminary_run"):
                return [{
                    "status": "source_wait",
                    "completed_at": "2026-08-31T21:53:00Z",
                    "observed_at": "2026-08-31T21:52:59Z",
                    "attempted_through": "2026-08-31",
                    "event_through": "2026-08-28",
                    "rows_observed": 0,
                    "rows_new": 0,
                    "reason": "source_not_authoritative_yet",
                }]
            if path.startswith("broward_clerk_preliminary?select=fetched_at"):
                return [{"fetched_at": "2026-08-31T21:52:58Z"}]
            if path.startswith("broward_clerk_preliminary"):
                return [{
                    "record_date": "2026-08-27",
                    "fetched_at": "2026-08-28T00:57:00Z",
                    "preliminary_first_seen_at": "2026-08-28T00:56:06Z",
                    "verification_status": "preliminary",
                    "source": "acclaimweb-public-search",
                }]
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

        pdmr_summary = {
            "status": "verified", "health_status": "healthy",
            "generated_at": "2026-08-11T04:50:00Z", "natural_schedule_proof": "passed",
            "local": {"events": 329, "versions": 329},
            "collector": {"finished_at": "2026-08-11T04:40:00Z", "records_attempted": 25, "records_written": 0, "records_rejected": 0},
            "mirror": {"parity_status": "passed"}, "receipt": {"health_sha256": "a" * 64},
        }
        with mock.patch.object(server_module, "supabase_public_rows", side_effect=rows), mock.patch.object(
            server_module, "meeting_payload", return_value={"updated_at": "2026-08-11T04:45:00Z", "meetings": []}
        ), mock.patch.object(server_module, "pdmr_health_summary", return_value=pdmr_summary):
            server_module._health_cache.update({"at": 0.0, "payload": None})
            payload = server_module.data_health_payload()

        sources = {source["id"]: source for source in payload["sources"]}
        self.assertEqual(sources["broward"]["event_through"], "2026-08-05")
        self.assertEqual(sources["broward"]["verification"], "verified")
        self.assertEqual(sources["clerk-preliminary"]["event_through"], "2026-08-28")
        self.assertEqual(sources["clerk-preliminary"]["verification"], "preliminary")
        self.assertEqual(sources["clerk-preliminary"]["fetched_at"], "2026-08-31T21:52:58Z")
        self.assertEqual(sources["clerk-preliminary"]["health_receipt_at"], "2026-08-31T21:53:00Z")
        self.assertEqual(sources["clerk-preliminary"]["health_receipt_status"], "source_wait")
        self.assertEqual(sources["clerk-preliminary"]["status_basis"], "event_and_terminal_collector_run")
        self.assertNotEqual(
            sources["clerk-preliminary"]["health_receipt_at"],
            "2026-08-28T00:56:06Z",
        )
        self.assertIn("never presented as verified early", sources["clerk-preliminary"]["detail"])
        self.assertEqual(sources["supabase-sync"]["status"], "error")
        self.assertEqual(sources["supabase-sync"]["health_receipt_status"], "failed")
        self.assertEqual(sources["fdep"]["status"], "unavailable")
        self.assertIsNone(sources["fdep"]["health_receipt_at"])
        self.assertEqual(sources["fdep"]["status_basis"], "row_fetch_only_no_terminal_receipt")
        self.assertEqual(sources["faa"]["status"], "unavailable")
        self.assertIsNone(sources["faa"]["health_receipt_at"])
        self.assertEqual(sources["faa"]["status_basis"], "row_fetch_only_no_terminal_receipt")
        self.assertEqual(sources["pdmr"]["metrics"]["local"]["events"], 329)
        self.assertEqual(sources["pdmr"]["status_basis"], "scheduled_terminal_receipts_and_four_table_parity")
        self.assertEqual(sources["sunbiz"]["status"], "current")
        self.assertEqual(sources["sunbiz"]["system_time"], "2026-08-11T03:50:00Z")
        self.assertIsNone(sources["sunbiz"]["event_through"])
        self.assertIn("remain private", sources["sunbiz"]["detail"])
        self.assertIn("row or timer clock never proves", payload["contract"])
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

    def test_honeypot_returns_ok_and_writes_nothing(self):
        body = {
            "email": "bot@example.com",
            "zip": "33301",
            "cities": ["fort-lauderdale"],
            "interests": ["development"],
            "company_website": "https://spam.example",
        }
        response, payload = self.request("/api/subscribe", "POST", body, extra_headers={"X-Forwarded-For": "203.0.113.50"})
        self.assertEqual(response.status, 200)
        self.assertTrue(payload["ok"])
        self.assertNotIn("bot", json.dumps(payload).lower())
        self.assertNotIn("honeypot", json.dumps(payload).lower())
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute("select count(*) from brief_subscribers where email = ?", ("bot@example.com",)).fetchone()
        self.assertEqual(row[0], 0)

    def test_subscribe_rate_limit_is_three_per_hour(self):
        server_module._subscribe_rate_hits.clear()
        body = {
            "zip": "33301",
            "cities": ["fort-lauderdale"],
            "interests": ["development"],
        }
        for index in range(3):
            payload = dict(body, email="rate-%s@example.com" % index)
            response, _ok = self.request("/api/subscribe", "POST", payload, extra_headers={"X-Forwarded-For": "203.0.113.80"})
            self.assertIn(response.status, (200, 201))
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request(
                "/api/subscribe",
                "POST",
                dict(body, email="rate-3@example.com"),
                extra_headers={"X-Forwarded-For": "203.0.113.80"},
            )
        self.assertEqual(caught.exception.code, 429)


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
