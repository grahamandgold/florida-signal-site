import importlib.util
import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("florida_signal_cms_server", ROOT / "cms" / "server.py")
cms_server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cms_server)


class DataWireServerTests(unittest.TestCase):
    def test_review_queue_defaults_to_ready_and_bounds_paging(self):
        path, limit, offset, readiness = cms_server.review_queue_path({
            "status": ["not-a-status"], "limit": ["9999"], "offset": ["-4"]
        })
        self.assertIn("review_status=eq.NEW", path)
        self.assertIn("evidence_ready=eq.true", path)
        self.assertIn("limit=20", path)
        self.assertIn("offset=0", path)
        self.assertEqual((limit, offset, readiness), (20, 0, "ready"))

    def test_investigation_context_uses_exact_permit_and_never_changes_evidence(self):
        item = {
            "verified_parcel_id": "504210410390",
            "evidence_packet": {"records": [{
                "source_table": "permits", "source_record_id": "BLD-GEN-26080223",
                "address": "808 SW 8 TER",
            }]},
        }
        packet_before = json.dumps(item["evidence_packet"], sort_keys=True)
        with mock.patch.object(cms_server, "supabase_request", return_value=(200, [{
            "permit_number": "BLD-GEN-26080223", "address": "808 SW 8 TER",
            "parcel_id_verified": "504210410390", "lat": 26.1, "lon": -80.15,
        }])) as request:
            result = cms_server.attach_investigation_context(item)
        self.assertIn("permit_number=eq.BLD-GEN-26080223", request.call_args.args[0])
        self.assertEqual(result["investigation"]["status"], "located")
        self.assertEqual(result["investigation"]["folio"], "504210410390")
        self.assertEqual(json.dumps(item["evidence_packet"], sort_keys=True), packet_before)

    def test_pipeline_schedule_reports_only_future_florida_timers(self):
        raw = json.dumps([
            {"unit": "florida-enrich.timer", "next": 1786500000000000, "last": 1786492817511663},
            {"unit": "sysstat-collect.timer", "next": 1786500000000000, "last": 0},
            {"unit": "florida-sync.timer", "next": 0, "last": 1786492817511663},
        ])
        completed = subprocess.CompletedProcess([], 0, stdout=raw, stderr="")
        with mock.patch.object(cms_server.subprocess, "run", return_value=completed) as run:
            code, payload = cms_server.pipeline_schedule()
        self.assertEqual(code, 200)
        self.assertEqual([job["unit"] for job in payload["jobs"]], ["florida-enrich.timer"])
        self.assertEqual(payload["jobs"][0]["label"], "Enrich permits")
        self.assertIn("proves scheduling only", payload["contract"])
        self.assertEqual(run.call_args.kwargs["timeout"], 8)

    def test_pipeline_schedule_fails_without_inventing_status(self):
        with mock.patch.object(cms_server.subprocess, "run", side_effect=subprocess.TimeoutExpired("ssh", 8)):
            code, payload = cms_server.pipeline_schedule()
        self.assertEqual(code, 502)
        self.assertIn("No timer status was inferred", payload["contract"])

    def test_early_intel_orders_decisions_before_permits_and_exposes_packet_gap(self):
        def public_payload(url):
            if url.endswith("/api/meetings"):
                return {"updated_at": "2026-08-12T01:20:00Z", "meetings": [{
                    "category": "government", "date": "2026-08-18", "agenda_available": False,
                }]}
            return {"sources": [
                {"id": "clerk-preliminary", "event_through": "2026-08-11", "system_time": "2026-08-12T00:00:00Z"},
                {"id": "broward", "event_through": "2026-08-06"},
                {"id": "sunbiz", "status": "unavailable"},
                {"id": "fdep", "event_through": "2026-08-06"},
                {"id": "faa", "event_through": "2026-08-10"},
                {"id": "permits", "event_through": "2026-08-10"},
            ]}

        with mock.patch.object(cms_server, "public_json", side_effect=public_payload):
            payload = cms_server.early_intel_payload()
        self.assertEqual(payload["lanes"][0]["phase"], "01 · Decisions")
        self.assertEqual(payload["lanes"][-1]["phase"], "05 · Execution")
        self.assertIn("0 posted agenda", payload["lanes"][0]["headline"])
        self.assertIn("not five complete candidate detectors", payload["contract"])

    def test_agenda_watch_filters_boilerplate_and_preserves_public_receipts(self):
        rows = [
            {"item_id": 1, "title": "NOTICES:", "watch_terms": ["development"], "attachments": []},
            {
                "item_id": 2, "event_id": 10, "agenda_number": "OSR-3",
                "title": "Second Reading - Quasi-Judicial Ordinance Approving a Rezoning",
                "matter_file": "26-0592", "matter_type": "ORDINANCE SECOND READING",
                "watch_terms": ["development"], "source_url": "https://example.test/item",
                "first_seen_at": "2026-07-22T00:00:00Z", "last_seen_at": "2026-07-23T00:00:00Z",
                "legistar_events": {
                    "event_date": "2026-07-02", "event_time": "6:00 PM",
                    "location": "City Hall", "body_name": "City Commission",
                    "agenda_url": "https://example.test/agenda.pdf",
                },
                "attachments": [{
                    "MatterAttachmentName": "Staff memo", "MatterAttachmentFileName": "memo.pdf",
                    "MatterAttachmentHyperlink": "https://example.test/memo.pdf",
                    "MatterAttachmentShowOnInternetPage": True,
                }],
            },
        ]
        meetings = {
            "updated_at": "2026-08-11T23:00:00Z", "calendar_url": "https://example.test/calendar",
            "meetings": [{
                "title": "City Commission Regular Meeting", "date": "2026-08-18",
                "time": "6:00 PM", "location": "Police Community Room",
                "category": "government", "agenda_available": False,
                "agenda_url": "https://example.test/calendar", "details_url": "https://example.test/meeting",
                "source": "Fort Lauderdale Legistar",
            }],
        }
        with mock.patch.object(cms_server, "supabase_request", return_value=(200, rows)), \
                mock.patch.object(cms_server, "public_json", return_value=meetings):
            code, payload = cms_server.agenda_watch_payload()
        self.assertEqual(code, 200)
        self.assertEqual(payload["matched_rows"], 2)
        self.assertEqual(payload["actionable_rows"], 1)
        self.assertEqual(payload["public_attachments"], 1)
        self.assertEqual(payload["event_start"], "2026-07-02")
        self.assertEqual(payload["event_through"], "2026-07-02")
        self.assertEqual(payload["item_index_observed_through"], "2026-07-23T00:00:00Z")
        self.assertEqual(payload["government_entities"], ["City of Fort Lauderdale"])
        self.assertEqual(payload["public_bodies"], ["City Commission"])
        self.assertEqual(payload["upcoming_meetings"][0]["event_time"], "6:00 PM")
        self.assertFalse(payload["upcoming_meetings"][0]["agenda_available"])
        self.assertEqual(payload["items"][0]["event_time"], "6:00 PM")
        self.assertEqual(payload["items"][0]["agenda_url"], "https://example.test/agenda.pdf")
        self.assertIn("entitlement", payload["items"][0]["why_developers_care"])
        self.assertIn("who benefits", payload["items"][0]["stakeholder_test"])
        self.assertEqual(payload["items"][0]["attachments"][0]["url"], "https://example.test/memo.pdf")

    def test_sunbiz_private_proxy_is_exact_bounded_and_service_role_only(self):
        rows = [
            {"search_name": "EXAMPLE OWNER LLC", "matched_name": "EXAMPLE OWNER LLC", "source": "sunbiz-sftp-corpus"},
            {"search_name": "EXTRA ROW", "matched_name": "EXTRA ROW", "source": "sunbiz-sftp-corpus"},
        ]
        with mock.patch.object(cms_server, "supabase_request", return_value=(200, rows)) as request:
            code, payload = cms_server.sunbiz_entities_payload({
                "limit": ["1"], "offset": ["0"], "search": ["Example Owner, LLC"],
            })
        query = request.call_args.args[0]
        self.assertEqual(code, 200)
        self.assertIn("source=eq.sunbiz-sftp-corpus", query)
        self.assertIn("search_name_norm=eq.EXAMPLEOWNERLLC", query)
        self.assertIn("limit=2", query)
        self.assertEqual(len(payload["items"]), 1)
        self.assertTrue(payload["has_more"])
        self.assertIn("no fuzzy identity claim", payload["contract"])


if __name__ == "__main__":
    unittest.main()
