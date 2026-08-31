import importlib.util
import json
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("florida_signal_cms_server", ROOT / "cms" / "server.py")
cms_server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cms_server)


class DataWireServerTests(unittest.TestCase):
    def test_project_state_separates_git_state_from_live_health(self):
        manifest = {
            "schema_version": "FloridaSignalProjectStateV1",
            "state_contract": "Durable state only",
            "current_mode": "STATE RECONCILIATION",
            "verified_at": "2026-08-23T18:48:52-04:00",
            "now": {
                "title": "Submit the prepared City of Fort Lauderdale records request for the 27 locked PDMRs and preserve the receipt",
                "status": "IN_PROGRESS",
            },
            "next": {"title": "Adjudicate", "status": "PAUSED"},
            "active_research": {"study": "PDMR", "status": "PAUSED_NEXT"},
            "blocked_claims": ["93-day proven lead"],
            "sensor_status": [{
                "sensor": "PDMR", "status": "LOCAL_ONLY",
                "detail": "first-public timing is unresolved for all 27 locked PDMRs",
            }],
            "latest_material_decision": {"decision": "Repository is institutional memory"},
            "production_pipeline_registry": [
                {
                    "id": "permits", "label": "Permits", "deployment_status": "PROD",
                    "authority": "DigitalOcean", "touch_policy": "PRESERVE",
                    "health_source": {"type": "public_data_health", "id": "permits"},
                },
                {
                    "id": "pdmr", "label": "PDMR", "deployment_status": "LOCAL_ONLY",
                    "authority": "local Python", "touch_policy": "EXPERIMENTAL",
                    "health_source": {"type": "none", "id": None},
                },
            ],
        }
        health = {"generated_at": "2026-08-23T22:00:00Z", "sources": [
            {
                "id": "permits", "status": "current", "event_through": "2026-08-22",
                "system_time": "2026-08-23T21:40:00Z", "detail": "Live receipt",
            },
            {
                "id": "clerk-preliminary", "status": "current", "event_through": "2026-08-22",
                "system_time": "2026-08-23T20:00:00Z", "detail": "Preliminary receipt",
            },
            {
                "id": "broward", "status": "delayed", "event_through": "2026-08-19",
                "system_time": "2026-08-23T18:00:00Z", "detail": "Verified receipt",
            },
        ]}
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state_path.write_text(json.dumps(manifest), encoding="utf-8")
            with mock.patch.object(cms_server, "PROJECT_STATE_PATH", state_path), \
                    mock.patch.object(cms_server, "public_json", return_value=health):
                code, payload = cms_server.project_state_payload()
        rows = {row["id"]: row for row in payload["operational_health"]}
        self.assertEqual(code, 200)
        self.assertEqual(rows["permits"]["status"], "CURRENT")
        self.assertEqual(rows["permits"]["event_through"], "2026-08-22")
        self.assertEqual(rows["pdmr"]["deployment_status"], "LOCAL_ONLY")
        self.assertEqual(rows["pdmr"]["status"], "UNKNOWN")
        receipts = {row["id"]: row for row in payload["source_receipts"]}
        self.assertEqual(receipts["clerk-preliminary"]["event_through"], "2026-08-22")
        self.assertEqual(receipts["broward"]["event_through"], "2026-08-19")
        self.assertEqual(receipts["broward"]["status"], "DELAYED")
        rendered_state = json.dumps(payload["project_state"])
        self.assertNotIn("locked PDMRs", rendered_state)
        self.assertIn("historical publication metadata", rendered_state)
        self.assertIn("27 public Preliminary Development Meeting Request records", rendered_state)
        self.assertIn("all 27 records in the frozen PDMR research cohort", rendered_state)
        self.assertIn("never inherit", payload["contract"])

    def test_project_state_fails_closed_when_manifest_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.json"
            with mock.patch.object(cms_server, "PROJECT_STATE_PATH", missing):
                code, payload = cms_server.project_state_payload()
        self.assertEqual(code, 503)
        self.assertEqual(payload["status"], "UNKNOWN")
        self.assertIn("No project state was inferred", payload["contract"])

    def test_early_radar_card_separates_exact_folio_from_address_context(self):
        html = (ROOT / "cms" / "home.html").read_text(encoding="utf-8")
        self.assertIn("Candidate evidence context", html)
        self.assertIn("Exact-folio activity", html)
        self.assertIn("Address-only context", html)
        self.assertIn("Coverage incomplete; no absence conclusion is available", html)
        self.assertIn("no project linkage was established by this lookup", html)
        self.assertNotIn("not linked to this project", html)
        self.assertIn("Not independently verified", html)
        self.assertIn("no zero conclusion is available", html)
        self.assertIn("Candidate ranking unchanged", html)
        self.assertIn("Context provenance", html)
        self.assertIn("source date unknown", html)
        self.assertIn("coverage unknown", html)
        self.assertIn("freshness unknown", html)

    def test_pdmr_shadow_detector_is_bounded_and_never_receives_output_path(self):
        payload = {
            "mode": "shadow", "items": [], "publication_effect": "none",
            "records_evaluated": 324, "records_in_window": 69, "eligible_candidates": 53,
        }
        completed = subprocess.CompletedProcess([], 0, stdout=json.dumps(payload), stderr="")
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "detector.py"
            database = Path(directory) / "pdmr.sqlite"
            script.touch()
            database.touch()
            with mock.patch.object(cms_server, "PDMR_CANDIDATE_SCRIPT", script), \
                    mock.patch.object(cms_server, "PDMR_DB_PATH", database), \
                    mock.patch.object(cms_server.subprocess, "run", return_value=completed) as run:
                code, result = cms_server.pdmr_shadow_candidate_payload(limit=999)
        command = run.call_args.args[0]
        self.assertEqual(code, 200)
        self.assertEqual(command[command.index("--limit") + 1], "20")
        self.assertNotIn("--output", command)
        self.assertEqual(run.call_args.kwargs["timeout"], 10)
        self.assertEqual(result["publication_effect"], "none")
        self.assertIn("does not approve", result["contract"])

    def test_pdmr_intent_is_a_bounded_read_only_source_lane(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "pdmr.sqlite"
            with sqlite3.connect(db_path) as db:
                db.executescript("""
                    create table parcel_events (
                      event_id text primary key, parcel_id text, event_type text not null,
                      event_date text, address text, owner_name text, project_name text, summary text,
                      source text not null, source_record_id text not null, source_url text not null,
                      source_record_hash text not null, payload_json text not null,
                      observed_mode text not null, detector_version text not null,
                      first_seen_at text not null, last_seen_at text not null
                    );
                """)
                fields = json.dumps({"fields": {
                    "status": "In Process", "folio": "504212BD0010",
                    "development_stage": "Conceptual Plan", "development_type": "Residential",
                    "units_text": "36", "parking_spaces": "40",
                    "staff_questions": "Confirm streetscape requirements",
                }})
                rows = [
                    ("one", "2026-08-19", "125 N Birch RD", "OWNER ONE", "125 N Birch Road"),
                    ("two", "2026-08-18", "1150 NW 55 ST", "OWNER TWO", "1150 NW 55 Street"),
                ]
                for event_id, event_date, address, owner, project in rows:
                    db.execute("""
                        insert into parcel_events values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        event_id, "504212BD0010", "planning_preapplication", event_date,
                        address, owner, project, "A public pre-application narrative",
                        "fort_lauderdale_lauderbuild_planning", "UDP-PDMR-26131" if event_id == "one" else "UDP-PDMR-26130",
                        "https://aca-prod.accela.com/FTL/Cap/CapDetail.aspx?record=" + event_id,
                        "hash-" + event_id, fields, "backfill", "pdmr-v1.0.0",
                        "2026-08-23T18:00:00+00:00", "2026-08-23T18:22:00+00:00",
                    ))
            with mock.patch.object(cms_server, "PDMR_DB_PATH", db_path), \
                    mock.patch.object(cms_server, "now_iso", return_value="2026-08-23T20:00:00+00:00"):
                code, payload = cms_server.pdmr_intent_payload(limit=1)
                offset_code, offset_payload = cms_server.pdmr_intent_payload(limit=1, offset=1)
                id_code, id_payload = cms_server.pdmr_intent_payload(search="id:UDP-PDMR-26130")
                address_code, address_payload = cms_server.pdmr_intent_payload(search="addr:125 N Birch")
            self.assertEqual(code, 200)
            self.assertEqual(payload["record_count"], 2)
            self.assertEqual(payload["matched_count"], 2)
            self.assertTrue(payload["has_more"])
            self.assertEqual(len(payload["items"]), 1)
            self.assertEqual(payload["items"][0]["source_record_id"], "UDP-PDMR-26131")
            self.assertEqual(payload["items"][0]["development_stage"], "Conceptual Plan")
            self.assertEqual(payload["items"][0]["editorial_state"], "source_record_only")
            self.assertIn("does not nominate a Candidate", payload["contract"])
            self.assertEqual(offset_code, 200)
            self.assertEqual(offset_payload["items"][0]["source_record_id"], "UDP-PDMR-26130")
            self.assertEqual(id_code, 200)
            self.assertEqual(id_payload["matched_count"], 1)
            self.assertEqual(id_payload["items"][0]["source_record_id"], "UDP-PDMR-26130")
            self.assertEqual(address_code, 200)
            self.assertEqual(address_payload["items"][0]["address"], "125 N Birch RD")
            with sqlite3.connect(db_path) as db:
                self.assertEqual(db.execute("select count(*) from parcel_events").fetchone()[0], 2)

    def test_pdmr_intent_does_not_infer_state_when_evidence_db_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.sqlite"
            with mock.patch.object(cms_server, "PDMR_DB_PATH", missing):
                code, payload = cms_server.pdmr_intent_payload()
        self.assertEqual(code, 503)
        self.assertEqual(payload["items"], [])
        self.assertIn("No PDMR state was inferred", payload["contract"])

    def test_brief_bank_and_weight_profiles_are_versioned_private_workflow_state(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "wire.sqlite"
            with mock.patch.object(cms_server, "DB_PATH", db_path):
                cms_server.init_db()
            with sqlite3.connect(db_path) as db:
                brief_columns = {row[1] for row in db.execute("pragma table_info(brief_bank)")}
                profile_columns = {row[1] for row in db.execute("pragma table_info(scoring_profiles)")}
                story_columns = {row[1] for row in db.execute("pragma table_info(stories)")}
            self.assertTrue({"edition_day", "target_date", "target_date_source", "candidate_id", "machine_version",
                             "importance_score", "recency_score", "source_stage",
                             "rules_fired_json", "evidence_hash", "evidence_confidence",
                             "evidence_confidence_reason", "gates_passed_json",
                             "score_reasons_json", "scoring_profile_id"}.issubset(brief_columns))
            self.assertTrue({"weights_json", "status", "backtest_status", "rationale",
                             "parent_profile_id", "created_by"}.issubset(profile_columns))
            self.assertTrue({"writing_style", "headline_mode", "jargon_mode",
                             "ethics_rules_json"}.issubset(story_columns))

    def test_brief_writing_profile_is_part_of_the_publication_gate(self):
        base = {
            "county": "broward-county", "city": "fort-lauderdale", "headline": "A filing changed",
            "dek": "A sourced summary", "body": "A sourced body", "event_date": "2026-08-11",
            "source_title": "Official record", "source_url": "https://example.test/record",
            "topic_tags": ["development"], "geography_tags": ["fort-lauderdale"],
            "claims_status": "passed", "verification_status": "verified", "current_trigger": "Filed Aug. 11",
            "project_identity_basis": "Exact public record ID", "claim_slots": [{"claim": "Filed", "source_url": "https://example.test/record"}],
            "validator_status": "passed", "tags_status": "passed", "editor_name": "Desk editor",
            "writing_style": "ap_florida_signal", "headline_mode": "compelling_precise",
            "jargon_mode": "plain_english", "ethics_rules": sorted(cms_server.REQUIRED_ETHICS_RULES),
        }
        self.assertEqual(cms_server.story_blocks(base), [])
        base["ethics_rules"] = ["attribute_material_claims"]
        self.assertTrue(any("ethics checklist" in block.lower() for block in cms_server.story_blocks(base)))

    def test_signal_machine_contract_is_cross_source_and_honest_about_gaps(self):
        payload = cms_server.signal_machine_payload()
        lanes = payload["lanes"]
        self.assertEqual([lane["id"] for lane in lanes], [
            "decisions", "formation", "capital", "regulatory", "execution",
        ])
        self.assertGreater(lanes[0]["default_multiplier"], lanes[-1]["default_multiplier"])
        self.assertTrue(all(1 <= lane["default_multiplier"] <= 2 for lane in lanes))
        self.assertEqual(lanes[0]["coverage"], "shadow_ranked")
        self.assertEqual(lanes[-1]["coverage"], "shadow_ranked")
        self.assertTrue(all(lane["coverage"] != "shadow_ranked" for lane in lanes[1:-1]))
        self.assertIn("cannot rescue weak evidence", payload["score_contract"]["rule"])
        self.assertEqual(payload["stages"][-3]["label"], "AI consistency check")
        self.assertIn("cannot add sources", payload["stages"][-3]["may"])
        self.assertEqual(payload["stages"][-2]["owner"], "Human desk editor")

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

    def test_early_intel_orders_pdmr_planning_intent_before_permits(self):
        def public_payload(url):
            if url.endswith("/api/meetings"):
                return {"updated_at": "2026-08-12T01:20:00Z", "meetings": [{
                    "category": "government", "date": "2026-08-18", "agenda_available": False,
                }]}
            return {"sources": [
                {"id": "clerk-preliminary", "status": "current", "event_through": "2026-08-11", "system_time": "2026-08-12T00:00:00Z"},
                {"id": "broward", "status": "delayed", "event_through": "2026-08-06"},
                {"id": "sunbiz", "status": "unavailable"},
                {"id": "fdep", "status": "current", "event_through": "2026-08-06"},
                {"id": "faa", "status": "current", "event_through": "2026-08-10"},
                {"id": "permits", "status": "current", "event_through": "2026-08-10"},
            ]}

        with mock.patch.object(cms_server, "public_json", side_effect=public_payload), \
                mock.patch.object(cms_server, "now_iso", return_value="2026-08-12T03:00:00+00:00"), \
                mock.patch.object(cms_server, "pdmr_intent_payload", return_value=(200, {
                    "record_count": 1, "newest_event": "2026-08-12", "last_collected": "2026-08-12T02:00:00Z",
                })):
            payload = cms_server.early_intel_payload()
        self.assertEqual(payload["lanes"][0]["phase"], "01 · Planning intent")
        self.assertEqual(payload["lanes"][0]["label"], "Preliminary Development Meeting Request (PDMR) + agenda packets")
        self.assertEqual(payload["lanes"][0]["automation"], "mixed")
        self.assertEqual(payload["lanes"][0]["status"], "current")
        self.assertEqual(payload["lanes"][1]["connection"], "unavailable")
        self.assertEqual(payload["lanes"][2]["status"], "delayed")
        self.assertEqual(payload["lanes"][-1]["phase"], "05 · Execution")
        self.assertIn("PDMR reaches 2026-08-12", payload["lanes"][0]["headline"])
        self.assertIn("first-public timing remains unresolved", payload["lanes"][0]["note"])
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

    def test_desktop_launcher_wires_external_project_state_and_pdmr_paths(self):
        launcher = (ROOT / "ops" / "datawire-app-launcher.zsh").read_text(encoding="utf-8")
        self.assertIn('florida_source="${FL_SIGNAL_SOURCE_ROOT:-$resources/florida-signal}"', launcher)
        self.assertIn('FL_SIGNAL_PROJECT_STATE_PATH="$project_state_path"', launcher)
        self.assertIn('FL_SIGNAL_PDMR_DB_PATH="$pdmr_db_path"', launcher)
        self.assertIn('FL_SIGNAL_PDMR_CANDIDATE_SCRIPT="$pdmr_candidate_script"', launcher)

    def test_desktop_updater_bundles_verified_local_source_snapshot(self):
        updater = (ROOT / "ops" / "update_datawire_desktop_app.sh").read_text(encoding="utf-8")
        self.assertIn("florida_signal_project_state.json", updater)
        self.assertIn("florida_signal_v1.sqlite", updater)
        self.assertIn("nominate_pdmr_candidates.py", updater)
        self.assertIn("pragma quick_check;", updater)

    def test_pdmr_dates_are_labeled_as_portal_dates_not_filing_dates(self):
        explorer = (ROOT / "cms" / "data.html").read_text(encoding="utf-8")
        home = (ROOT / "cms" / "home.html").read_text(encoding="utf-8")
        self.assertIn('["event_date", "Portal date", dateish]', explorer)
        self.assertNotIn('["event_date", "Filed", dateish]', explorer)
        self.assertIn("newest portal date", home)
        self.assertNotIn("newest filing", home)


if __name__ == "__main__":
    unittest.main()
