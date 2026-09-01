import importlib.util
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
DESK_SERVICE_TARGET = f"gui/{os.getuid()}/com.floridasignal.datawire.server"
SPEC = importlib.util.spec_from_file_location("florida_signal_cms_server", ROOT / "cms" / "server.py")
cms_server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cms_server)


UTILITY_NOW = datetime(2026, 9, 1, 1, 30, tzinfo=timezone.utc)


def utility_row(permit_number: str, **values):
    row = {column: None for column in cms_server.UTILITY_INTAKE_PARITY_COLUMNS}
    row.update({
        "permit_number": permit_number,
        "report_source": "opened_permits",
        "status": "Applied",
        "first_seen_at": "2026-08-30T10:00:00Z",
        "last_seen_at": "2026-09-01T00:30:00Z",
        "last_updated_at": "2026-09-01T00:30:00Z",
    })
    row.update(values)
    return row


def utility_health(rows, *, system_time="2026-09-01T01:00:00Z", metrics_override=None):
    exact = [row for row in rows if cms_server.utility_intake_family(row.get("permit_number"))]
    proof = cms_server.utility_intake_projection_proof(exact)
    metrics = {
        "rows_attempted": proof["count"],
        "rows_written": 0,
        "rows_rejected": 0,
        "sqlite_rows": proof["count"],
        "supabase_rows": proof["count"],
        "sqlite_pk_set_sha256": proof["primary_key_set_sha256"],
        "supabase_pk_set_sha256": proof["primary_key_set_sha256"],
        "sqlite_projection_rowset_sha256": proof["declared_projection_rowset_sha256"],
        "supabase_projection_rowset_sha256": proof["declared_projection_rowset_sha256"],
        "parity_projection_version": cms_server.UTILITY_INTAKE_PROJECTION_VERSION,
        "parity_projection_sha256": proof["projection"]["sha256"],
        "remote_stability_reads": 2,
        "remote_exact_count_reconciled": True,
        "verification_receipt_path": "/srv/grahamandgold/florida-signal/staging/data/utility-intake/receipts/test.verification.json",
        "verification_receipt_sha256": "a" * 64,
    }
    metrics.update(metrics_override or {})
    return [{
        "component": "utility-intake",
        "status": "current",
        "event_through": "2026-08-31",
        "system_time": system_time,
        "detail": "Bound declared projection parity",
        "metrics": metrics,
    }]


def utility_request(rows, *, page_size=None):
    def request(path, *args, **kwargs):
        query = parse_qs(urlparse(path).query)
        offset = int(query.get("offset", ["0"])[0])
        requested = int(query.get("limit", ["1000"])[0])
        limit = min(requested, page_size) if page_size else requested
        return 200, rows[offset:offset + limit]
    return request


class DataWireServerTests(unittest.TestCase):
    @staticmethod
    def _write_executable(path, body):
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)

    def _desk_command_fixture(self, directory, scenario):
        root = Path(directory)
        state = root / "state"
        fake_bin = root / "bin"
        home = root / "home"
        state.mkdir()
        fake_bin.mkdir()
        home.mkdir()
        log_path = root / "events.log"

        self._write_executable(fake_bin / "launchctl", r'''#!/bin/bash
set -u
action="${1:-}"
job="$FAKE_DESK_STATE/job"
removing="$FAKE_DESK_STATE/removing"
log() { printf '%s\n' "$*" >> "$FAKE_DESK_LOG"; }
case "$action" in
  print)
    if [[ -f "$removing" ]]; then
      count="$(<"$removing")"
      if (( count > 0 )); then
        printf '%s\n' "$((count - 1))" > "$removing"
        log "launchctl print ${2:-} loaded"
        exit 0
      fi
      /bin/rm -f "$removing" "$job"
      log "launchctl print ${2:-} absent"
      exit 1
    fi
    if [[ -f "$job" ]]; then
      log "launchctl print ${2:-} loaded"
      exit 0
    fi
    log "launchctl print ${2:-} absent"
    exit 1
    ;;
  bootout)
    log "launchctl bootout ${2:-}"
    if [[ -f "$job" && ( "$FAKE_DESK_SCENARIO" == "launcher_async" || "$FAKE_DESK_SCENARIO" == "updater_managed" ) ]]; then
      printf '2\n' > "$removing"
    else
      /bin/rm -f "$job" "$removing"
    fi
    exit 0
    ;;
  submit)
    if [[ "$FAKE_DESK_SCENARIO" == "submit_fail" ]]; then
      log "launchctl submit failed"
      exit 64
    fi
    : > "$job"
    log "launchctl submit success"
    exit 0
    ;;
esac
log "launchctl unexpected $*"
exit 65
''')
        self._write_executable(fake_bin / "lsof", r'''#!/bin/bash
set -u
log() { printf '%s\n' "$*" >> "$FAKE_DESK_LOG"; }
case "$FAKE_DESK_SCENARIO" in
  occupied)
    log "lsof busy unrelated"
    printf '999\n'
    exit 0
    ;;
  launcher_async)
    counter="$FAKE_DESK_STATE/port_count"
    if [[ -f "$counter" ]]; then
      count="$(<"$counter")"
      if (( count > 0 )); then
        printf '%s\n' "$((count - 1))" > "$counter"
        log "lsof busy old-desk"
        printf '777\n'
        exit 0
      fi
      /bin/rm -f "$counter"
    fi
    ;;
  updater_legacy|updater_unverified)
    if [[ -f "$FAKE_DESK_STATE/listener" ]]; then
      log "lsof busy candidate"
      printf '321\n'
      exit 0
    fi
    ;;
esac
log "lsof free"
exit 1
''')
        self._write_executable(fake_bin / "curl", r'''#!/bin/bash
set -u
if [[ "$FAKE_DESK_SCENARIO" == "health_wrong" ]]; then
  printf '%s\n' "curl wrong-service" >> "$FAKE_DESK_LOG"
  printf '{"ok":true,"service":"not-the-data-wire"}\n'
else
  printf '%s\n' "curl expected-service" >> "$FAKE_DESK_LOG"
  printf '{"ok":true,"service":"the-data-wire","admin_writes_enabled":true}\n'
  if [[ "$FAKE_DESK_SCENARIO" == "curl_exit_fail" ]]; then
    exit 28
  fi
fi
''')
        self._write_executable(fake_bin / "sleep", r'''#!/bin/bash
printf '%s\n' "sleep $*" >> "$FAKE_DESK_LOG"
''')
        self._write_executable(fake_bin / "open", r'''#!/bin/bash
printf '%s\n' "open $*" >> "$FAKE_DESK_LOG"
''')
        self._write_executable(fake_bin / "osascript", r'''#!/bin/bash
printf '%s\n' "alert" >> "$FAKE_DESK_LOG"
''')
        self._write_executable(fake_bin / "ps", r'''#!/bin/bash
printf '%s\n' "ps $*" >> "$FAKE_DESK_LOG"
if [[ "$*" == *"uid="* ]]; then
  /usr/bin/id -u
  exit 0
fi
if [[ "$FAKE_DESK_SCENARIO" == "updater_legacy" ]]; then
  printf '%s\n' "$FAKE_EXPECTED_COMMAND"
else
  printf '%s\n' "/usr/bin/python3 /tmp/unrelated/server.py --port 8788"
fi
''')
        self._write_executable(fake_bin / "kill", r'''#!/bin/bash
printf '%s\n' "kill $*" >> "$FAKE_DESK_LOG"
/bin/rm -f "$FAKE_DESK_STATE/listener"
''')

        if scenario in {"launcher_async", "updater_managed"}:
            (state / "job").touch()
        if scenario == "launcher_async":
            (state / "port_count").write_text("2\n", encoding="utf-8")
        if scenario in {"updater_legacy", "updater_unverified"}:
            (state / "listener").touch()

        env = os.environ.copy()
        env.update({
            "HOME": str(home),
            "FAKE_DESK_LOG": str(log_path),
            "FAKE_DESK_STATE": str(state),
            "FAKE_DESK_SCENARIO": scenario,
            "FL_SIGNAL_DESK_LAUNCHCTL_BIN": str(fake_bin / "launchctl"),
            "FL_SIGNAL_DESK_LSOF_BIN": str(fake_bin / "lsof"),
            "FL_SIGNAL_DESK_CURL_BIN": str(fake_bin / "curl"),
            "FL_SIGNAL_DESK_SLEEP_BIN": str(fake_bin / "sleep"),
            "FL_SIGNAL_DESK_OPEN_BIN": str(fake_bin / "open"),
            "FL_SIGNAL_DESK_OSASCRIPT_BIN": str(fake_bin / "osascript"),
            "FL_SIGNAL_DESK_PS_BIN": str(fake_bin / "ps"),
            "FL_SIGNAL_DESK_KILL_BIN": str(fake_bin / "kill"),
        })
        env["FAKE_EXPECTED_COMMAND"] = (
            "/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/"
            "Versions/3.9/Resources/Python.app/Contents/MacOS/Python "
            f"{home}/Desktop/Florida Signal Data Wire.app/"
            "Contents/MacOS/../Resources/cms/server.py --port 8788"
        )
        env["FL_SIGNAL_DESK_PYTHON_ARGV0"] = env["FAKE_EXPECTED_COMMAND"].split(" ", 1)[0]
        return env, log_path

    def _run_launcher_scenario(self, scenario):
        with tempfile.TemporaryDirectory() as directory:
            env, log_path = self._desk_command_fixture(directory, scenario)
            result = subprocess.run(
                ["/bin/zsh", str(ROOT / "ops" / "datawire-app-launcher.zsh")],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            events = log_path.read_text(encoding="utf-8").splitlines()
        return result, events

    def _run_updater_restart_scenario(self, scenario):
        with tempfile.TemporaryDirectory() as directory:
            env, log_path = self._desk_command_fixture(directory, scenario)
            result = subprocess.run(
                [
                    "/bin/bash", "-c",
                    'source "$1"; coordinate_desk_restart_after_update',
                    "desk-restart-test", str(ROOT / "ops" / "update_datawire_desktop_app.sh"),
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            events = log_path.read_text(encoding="utf-8").splitlines()
        return result, events

    def test_preliminary_clock_uses_business_days_and_fetch_only_fails_closed(self):
        sunday = datetime(2026, 8, 30, 23, 0, tzinfo=timezone.utc)
        monday_after_release = datetime(2026, 8, 31, 17, 0, tzinfo=timezone.utc)
        self.assertEqual(cms_server.business_calendar_age("2026-08-28", now=sunday), 0)
        self.assertEqual(
            cms_server.business_calendar_age(
                "2026-08-28",
                now=monday_after_release,
                holidays={date(2026, 8, 31)},
            ),
            0,
        )
        base = {
            "status": "current",
            "event_through": "2026-08-27",
            "health_receipt_at": "2026-08-29T20:00:00Z",
            "health_receipt_status": "ok",
            "status_basis": "event_and_terminal_collector_run",
        }
        fetch_only = cms_server.overlay_preliminary_clock(
            base, {}, {"fetched_at": "2026-08-30T22:58:00Z"}
        )
        self.assertEqual(fetch_only["status"], "unavailable")
        self.assertIsNone(fetch_only["health_receipt_at"])
        self.assertIsNone(fetch_only["health_receipt_status"])
        self.assertEqual(fetch_only["status_basis"], "row_fetch_only_no_terminal_receipt")
        self.assertEqual(fetch_only["system_time"], "2026-08-30T22:58:00Z")

        fdep = cms_server.require_terminal_health({
            "id": "fdep",
            "status": "current",
            "event_through": "2026-08-28",
            "fetched_at": "2026-08-30T09:20:00Z",
        })
        self.assertEqual(fdep["status"], "unavailable")
        self.assertEqual(fdep["status_basis"], "row_fetch_only_no_terminal_receipt")
        self.assertEqual(fdep["system_time"], "2026-08-30T09:20:00Z")
        self.assertIsNone(fdep["health_receipt_at"])

        with mock.patch.object(cms_server, "now_iso", return_value="2026-08-30T23:00:00Z"):
            terminal = cms_server.overlay_preliminary_clock(
                base,
                {
                    "status": "source_wait",
                    "completed_at": "2026-08-30T22:59:00Z",
                    "event_through": "2026-08-28",
                },
                {"fetched_at": "2026-08-30T22:58:00Z"},
            )
        self.assertEqual(terminal["event_through"], "2026-08-28")
        self.assertEqual(terminal["status"], "current")

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
                "fetched_at": "2026-08-23T21:40:00Z",
                "health_receipt_at": None,
                "health_receipt_status": None,
                "status_basis": "row_observation_only",
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
        def private_receipt(path, method="GET", body=None, prefer=""):
            if path.startswith("broward_clerk_preliminary_run"):
                return 200, [{
                    "status": "source_wait",
                    "completed_at": "2026-08-23T22:20:00Z",
                    "event_through": "2026-08-22",
                    "reason": "source_not_authoritative_yet",
                }]
            if path.startswith("broward_clerk_preliminary?select=fetched_at"):
                return 200, [{"fetched_at": "2026-08-23T22:19:00Z"}]
            raise AssertionError(path)
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state_path.write_text(json.dumps(manifest), encoding="utf-8")
            with mock.patch.object(cms_server, "PROJECT_STATE_PATH", state_path), \
                    mock.patch.object(cms_server, "public_json", return_value=health), \
                    mock.patch.object(cms_server, "supabase_request", side_effect=private_receipt), \
                    mock.patch.object(cms_server, "now_iso", return_value="2026-08-23T22:30:00Z"), \
                    mock.patch.object(cms_server, "pdmr_intent_payload", return_value=(200, {
                        "record_count": 329,
                        "newest_event": "2026-08-22",
                        "last_collected": "2026-08-23T21:45:00Z",
                    })):
                code, payload = cms_server.project_state_payload()
        rows = {row["id"]: row for row in payload["operational_health"]}
        self.assertEqual(code, 200)
        self.assertEqual(rows["permits"]["status"], "CURRENT")
        self.assertEqual(rows["permits"]["event_through"], "2026-08-22")
        self.assertEqual(rows["permits"]["fetched_at"], "2026-08-23T21:40:00Z")
        self.assertEqual(rows["permits"]["status_basis"], "row_observation_only")
        self.assertEqual(rows["pdmr"]["deployment_status"], "LOCAL_ONLY")
        self.assertEqual(rows["pdmr"]["status"], "UNKNOWN")
        receipts = {row["id"]: row for row in payload["source_receipts"]}
        self.assertEqual(receipts["clerk-preliminary"]["event_through"], "2026-08-22")
        self.assertEqual(receipts["clerk-preliminary"]["fetched_at"], "2026-08-23T22:19:00Z")
        self.assertEqual(receipts["clerk-preliminary"]["health_receipt_at"], "2026-08-23T22:20:00Z")
        self.assertEqual(receipts["clerk-preliminary"]["health_receipt_status"], "source_wait")
        self.assertEqual(receipts["clerk-preliminary"]["status_basis"], "event_and_terminal_collector_run")
        self.assertEqual(receipts["broward"]["event_through"], "2026-08-19")
        self.assertEqual(receipts["broward"]["status"], "DELAYED")
        self.assertEqual(receipts["pdmr-local"]["status"], "CURRENT")
        self.assertEqual(receipts["pdmr-local"]["event_through"], "2026-08-22")
        self.assertEqual(receipts["pdmr-local"]["fetched_at"], "2026-08-23T21:45:00Z")
        self.assertIsNone(receipts["pdmr-local"]["health_receipt_at"])
        self.assertEqual(receipts["pdmr-local"]["status_basis"], "manual_snapshot_observation")
        self.assertIn("329 public source records", receipts["pdmr-local"]["detail"])
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
                {"id": "clerk-preliminary", "status": "current", "event_through": "2026-08-11", "system_time": "2026-08-11T20:00:00Z"},
                {"id": "broward", "status": "delayed", "event_through": "2026-08-06", "health_receipt_at": "2026-08-11T18:00:00Z", "status_basis": "event_and_authoritative_terminal_run"},
                {"id": "sunbiz", "status": "unavailable"},
                {"id": "fdep", "status": "unavailable", "event_through": "2026-08-06", "fetched_at": "2026-08-12T01:00:00Z", "status_basis": "row_fetch_only_no_terminal_receipt"},
                {"id": "faa", "status": "unavailable", "event_through": "2026-08-10", "fetched_at": "2026-08-12T01:10:00Z", "status_basis": "row_fetch_only_no_terminal_receipt"},
                {"id": "permits", "status": "current", "event_through": "2026-08-10", "fetched_at": "2026-08-12T01:20:00Z", "status_basis": "row_observation_only"},
            ]}

        def private_payload(path, method="GET", body=None, prefer=""):
            if path.startswith("sunbiz_entities"):
                return 200, []
            if path.startswith("broward_clerk_preliminary_run"):
                return 200, [{
                    "status": "source_wait",
                    "completed_at": "2026-08-12T02:30:00Z",
                    "event_through": "2026-08-11",
                    "reason": "source_not_authoritative_yet",
                }]
            if path.startswith("broward_clerk_preliminary?select=fetched_at"):
                return 200, [{"fetched_at": "2026-08-12T02:29:00Z"}]
            raise AssertionError(path)

        with mock.patch.object(cms_server, "public_json", side_effect=public_payload), \
                mock.patch.object(cms_server, "supabase_request", side_effect=private_payload), \
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
        capital_clocks = {row["id"]: row for row in payload["lanes"][2]["source_clocks"]}
        self.assertEqual(capital_clocks["clerk-preliminary"]["event_through"], "2026-08-11")
        self.assertEqual(capital_clocks["clerk-preliminary"]["fetched_at"], "2026-08-12T02:29:00Z")
        self.assertEqual(capital_clocks["clerk-preliminary"]["health_receipt_at"], "2026-08-12T02:30:00Z")
        self.assertEqual(capital_clocks["broward"]["health_receipt_at"], "2026-08-11T18:00:00Z")
        regulatory_clocks = {row["id"]: row for row in payload["lanes"][3]["source_clocks"]}
        self.assertEqual(payload["lanes"][3]["connection"], "connected")
        self.assertEqual(payload["lanes"][3]["status"], "unavailable")
        self.assertIsNone(regulatory_clocks["fdep"]["health_receipt_at"])
        self.assertEqual(regulatory_clocks["fdep"]["fetched_at"], "2026-08-12T01:00:00Z")
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

    def test_utility_intake_proxy_uses_exact_families_and_health_receipt(self):
        rows = [
            utility_row("ENG-CR-260001", applied_date="2026-08-30", address="1 A St"),
            utility_row("ENG-CR-260001.D001", applied_date="2026-08-30"),
            utility_row("ENG-OAA-260002", applied_date="2026-08-31", address="2 B St"),
            utility_row("ENG-OAA-260002.D001", applied_date="2026-08-31"),
            utility_row("ROW-SEW-260003.D001", applied_date="2026-08-29"),
            utility_row("ROW-WTR-260004", applied_date="2026-08-28"),
            utility_row("PLB-SEWCP-WT-260005", applied_date="2026-08-27"),
            utility_row("ENG-GENERAL-260006", applied_date="2026-08-31"),
        ]
        health = utility_health(rows)

        with mock.patch.object(
            cms_server, "supabase_request", side_effect=utility_request(rows),
        ) as call, mock.patch.object(
            cms_server, "load_utility_intake_local_health", return_value=health[0],
        ):
            code, sewer = cms_server.utility_intake_payload({
                "lane": ["sewer_utility"], "limit": ["10"], "offset": ["0"],
            }, observed_at=UTILITY_NOW)
            _, engineering = cms_server.utility_intake_payload({
                "lane": ["engineering"], "limit": ["10"], "offset": ["0"],
            }, observed_at=UTILITY_NOW)
        permit_queries = [item.args[0] for item in call.call_args_list if item.args[0].startswith("permits?")]
        self.assertTrue(all(item.args[0].startswith("permits?") for item in call.call_args_list))
        self.assertEqual(code, 200)
        self.assertEqual({row["permit_number"] for row in sewer["items"]}, {
            "ENG-CR-260001", "ROW-SEW-260003.D001", "ROW-WTR-260004", "PLB-SEWCP-WT-260005",
        })
        self.assertEqual([row["permit_number"] for row in engineering["items"]], ["ENG-OAA-260002"])
        self.assertEqual(sewer["health"]["status"], "current")
        self.assertTrue(sewer["health"]["validation"]["projection_bound"])
        self.assertEqual(sewer["all_lane_record_count"], 5)
        self.assertEqual(sewer["last_collected"], "2026-09-01T01:00:00Z")
        self.assertIn("permit_number.like.ENG-CR-*", permit_queries[0])
        self.assertIn("does not establish the serving utility", sewer["contract"])
        self.assertIn("no claim that a record predates PDMR", sewer["contract"])

    def test_utility_intake_duplicate_identity_fails_closed(self):
        duplicate = utility_row("ROW-SEW-260003", applied_date="2026-08-29")
        with mock.patch.object(
            cms_server,
            "supabase_request",
            side_effect=utility_request([duplicate, dict(duplicate)]),
        ):
            code, payload = cms_server.utility_intake_payload({"lane": ["all"]})
        self.assertEqual(code, 502)
        self.assertIn("Duplicate utility identity", payload["error"])

    def test_utility_intake_pages_until_explicit_empty_even_after_short_page(self):
        rows = [
            utility_row(f"ROW-SEW-26000{index}", applied_date="2026-08-29")
            for index in range(3)
        ]
        health = utility_health(rows)
        offsets = []

        def request(path, *args, **kwargs):
            query = path.split("?", 1)[1]
            params = dict(item.split("=", 1) for item in query.split("&") if "=" in item)
            offset = int(params["offset"])
            offsets.append(offset)
            return 200, rows[offset:offset + 2]

        with mock.patch.object(
            cms_server, "supabase_request", side_effect=request,
        ), mock.patch.object(
            cms_server, "load_utility_intake_local_health", return_value=health[0],
        ):
            code, payload = cms_server.utility_intake_payload(
                {"lane": ["all"]}, observed_at=UTILITY_NOW,
            )
        self.assertEqual(code, 200)
        self.assertEqual(payload["record_count"], 3)
        self.assertEqual(offsets, [0, 2, 3])

    def test_utility_intake_health_loads_only_from_hash_bound_local_receipts(self):
        rows = [utility_row("ENG-CR-260001", applied_date="2026-08-30")]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipts = root / "receipts"
            receipts.mkdir()
            counts = {
                "records_attempted": 1,
                "records_written": 0,
                "records_rejected": 0,
                "sqlite_records": 1,
                "supabase_records": 1,
            }
            proof = cms_server.utility_intake_projection_proof(rows)
            parity = {"status": "passed", "sqlite": proof, "supabase": proof}
            verification_path = receipts / "bound.verification.json"
            verification_path.write_text(json.dumps({
                "schema_version": cms_server.UTILITY_INTAKE_VERIFICATION_SCHEMA,
                "run_id": "utility-local-binding",
                "status": "verified",
                "completed_at": "2026-09-01T01:00:00Z",
                "counts": counts,
                "parity": parity,
            }, sort_keys=True) + "\n", encoding="utf-8")
            verification_sha = hashlib.sha256(verification_path.read_bytes()).hexdigest()
            health = utility_health(rows, metrics_override={
                "verification_receipt_path": str(verification_path),
                "verification_receipt_sha256": verification_sha,
            })[0]
            outcome = {
                "schema_version": cms_server.UTILITY_INTAKE_RECEIPT_SCHEMA,
                "run_id": "utility-local-binding",
                "status": "ok",
                "completed_at": "2026-09-01T01:00:00Z",
                "counts": counts,
                "parity": parity,
                "verification": {
                    "receipt_path": str(verification_path),
                    "receipt_sha256": verification_sha,
                },
                "health": health,
            }
            outcome_path = receipts / "utility-local-binding.json"
            outcome_path.write_text(json.dumps(outcome, sort_keys=True) + "\n", encoding="utf-8")
            pointer = {
                "schema_version": cms_server.UTILITY_INTAKE_LATEST_SCHEMA,
                "run_id": "utility-local-binding",
                "status": "ok",
                "updated_at": "2026-09-01T01:00:00Z",
                "receipt_path": str(outcome_path),
                "receipt_sha256": hashlib.sha256(outcome_path.read_bytes()).hexdigest(),
                "counts": outcome["counts"],
            }
            latest = root / "latest.json"
            latest.write_text(json.dumps(pointer, sort_keys=True) + "\n", encoding="utf-8")

            with mock.patch.object(
                cms_server, "UTILITY_INTAKE_RECEIPT_DIR", receipts,
            ), mock.patch.object(
                cms_server, "UTILITY_INTAKE_LATEST_POINTER", latest,
            ):
                loaded = cms_server.load_utility_intake_local_health()
                self.assertEqual(loaded["status"], "current")
                self.assertEqual(loaded["metrics"]["verification_receipt_sha256"], verification_sha)

                outcome["health"]["metrics"]["sqlite_rows"] = 2
                outcome_path.write_text(
                    json.dumps(outcome, sort_keys=True) + "\n", encoding="utf-8",
                )
                pointer["receipt_sha256"] = hashlib.sha256(
                    outcome_path.read_bytes()
                ).hexdigest()
                latest.write_text(
                    json.dumps(pointer, sort_keys=True) + "\n", encoding="utf-8",
                )
                metric_rejected = cms_server.load_utility_intake_local_health()
                self.assertEqual(metric_rejected["status"], "unverified")

                outcome["health"]["metrics"]["sqlite_rows"] = 1
                outcome_path.write_text(
                    json.dumps(outcome, sort_keys=True) + "\n", encoding="utf-8",
                )
                pointer["receipt_sha256"] = "0" * 64
                latest.write_text(json.dumps(pointer, sort_keys=True) + "\n", encoding="utf-8")
                rejected = cms_server.load_utility_intake_local_health()
                self.assertEqual(rejected["status"], "unverified")
                self.assertNotIn(str(outcome_path), rejected["detail"])

    def test_utility_intake_health_downgrades_projection_mismatch_and_staleness(self):
        rows = [utility_row("ENG-CR-260001", applied_date="2026-08-30")]
        mismatch = utility_health(rows, metrics_override={"supabase_rows": 99})
        stale = utility_health(rows, system_time="2026-08-31T23:00:00Z")

        def run(health):
            def request(path, *args, **kwargs):
                return 200, rows if "offset=0" in path else []
            with mock.patch.object(
                cms_server, "supabase_request", side_effect=request,
            ), mock.patch.object(
                cms_server, "load_utility_intake_local_health", return_value=health[0],
            ):
                return cms_server.utility_intake_payload(
                    {"lane": ["all"]}, observed_at=UTILITY_NOW,
                )[1]["health"]

        mismatch_health = run(mismatch)
        stale_health = run(stale)
        self.assertEqual(mismatch_health["status"], "unverified")
        self.assertIn("supabase_rows", mismatch_health["validation"]["reason"])
        self.assertEqual(stale_health["status"], "stale")
        self.assertEqual(stale_health["validation"]["reason"], "scheduled_receipt_overdue")

    def test_utility_intake_health_rejects_unexpected_empty_projection(self):
        health = utility_health([], system_time=UTILITY_NOW.isoformat())[0]
        proof = cms_server.utility_intake_projection_proof([])
        checked = cms_server.validate_utility_intake_health(
            health, proof, observed_at=UTILITY_NOW,
        )
        self.assertEqual(checked["status"], "unverified")
        self.assertEqual(checked["validation"]["reason"], "unexpected_empty_projection")

    def test_utility_intake_health_checks_local_verification_receipt_when_accessible(self):
        rows = [utility_row("ENG-CR-260001", applied_date="2026-08-30")]
        with tempfile.TemporaryDirectory() as tmp:
            receipt_dir = Path(tmp)
            receipt_path = receipt_dir / "test.verification.json"
            receipt_path.write_text("verified\n", encoding="utf-8")
            health = utility_health(rows, metrics_override={
                "verification_receipt_path": str(receipt_path),
                "verification_receipt_sha256": "0" * 64,
            })
            proof = cms_server.utility_intake_projection_proof(rows)
            with mock.patch.object(cms_server, "UTILITY_INTAKE_RECEIPT_DIR", receipt_dir):
                checked = cms_server.validate_utility_intake_health(
                    health[0], proof, observed_at=UTILITY_NOW,
                )
        self.assertEqual(checked["status"], "unverified")
        self.assertEqual(checked["validation"]["reason"], "verification_receipt_hash_mismatch")

    def test_utility_intake_health_rejects_unsafe_or_missing_configured_receipt(self):
        rows = [utility_row("ENG-CR-26010001")]
        proof = cms_server.utility_intake_projection_proof(rows)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target.json"
            target.write_text("{}", encoding="utf-8")
            link = root / "receipt.json"
            link.symlink_to(target)
            health = utility_health(rows, system_time=UTILITY_NOW.isoformat())[0]
            health["metrics"].update({
                "verification_receipt_path": str(link),
                "verification_receipt_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            })
            with mock.patch.object(cms_server, "UTILITY_INTAKE_RECEIPT_DIR", root):
                checked = cms_server.validate_utility_intake_health(
                    health, proof, observed_at=UTILITY_NOW,
                )
                self.assertEqual(checked["status"], "unverified")
                self.assertEqual(
                    checked["validation"]["reason"], "verification_receipt_path_unsafe",
                )
                health["metrics"]["verification_receipt_path"] = str(root / "missing.json")
                checked = cms_server.validate_utility_intake_health(
                    health, proof, observed_at=UTILITY_NOW,
                )
                self.assertEqual(checked["status"], "unverified")
                self.assertEqual(
                    checked["validation"]["reason"], "verification_receipt_missing",
                )

    def test_data_explorer_marks_utility_lanes_automated_not_research(self):
        html = (ROOT / "cms" / "data.html").read_text(encoding="utf-8")
        self.assertIn('table: "utility_sewer_intake"', html)
        self.assertIn('table: "engineering_intake"', html)
        self.assertIn('componentId: "utility-intake", refresh: "automated"', html)
        self.assertIn('privateParams: { lane: "sewer_utility" }', html)
        self.assertIn('privateParams: { lane: "engineering" }', html)
        self.assertIn('data-receipt-total', html)
        self.assertIn('data-receipt-event', html)
        self.assertIn('data-receipt-collected', html)
        self.assertIn('data-receipt-health', html)
        self.assertIn('data-receipt-detail', html)
        self.assertNotIn("ENG-CR, ENG-OAA and TMP workflows; source contract not built", html)

    def test_desktop_launcher_wires_external_project_state_and_pdmr_paths(self):
        launcher = (ROOT / "ops" / "datawire-app-launcher.zsh").read_text(encoding="utf-8")
        self.assertIn('resources="${launcher_path:h:h}/Resources"', launcher)
        self.assertIn('florida_source="${FL_SIGNAL_SOURCE_ROOT:-$resources/florida-signal}"', launcher)
        self.assertIn('FL_SIGNAL_PROJECT_STATE_PATH="$project_state_path"', launcher)
        self.assertIn('FL_SIGNAL_PDMR_DB_PATH="$pdmr_db_path"', launcher)
        self.assertIn('FL_SIGNAL_PDMR_CANDIDATE_SCRIPT="$pdmr_candidate_script"', launcher)
        self.assertIn('job_label="com.floridasignal.datawire.server"', launcher)
        self.assertIn('if [[ "${1:-}" == "--serve" ]]', launcher)
        self.assertIn('exec /usr/bin/python3 "$resources/cms/server.py" --port 8788', launcher)
        self.assertIn('service_target="gui/$(/usr/bin/id -u)/$job_label"', launcher)
        self.assertIn('"$launchctl_bin" bootout "$service_target"', launcher)
        self.assertIn('"$launchctl_bin" submit -l "$job_label"', launcher)
        self.assertNotIn('/bin/kill "$process_id"', launcher)
        self.assertIn('payload.get("ok") is True', launcher)
        self.assertIn('payload.get("service") == "the-data-wire"', launcher)
        self.assertIn('payload.get("admin_writes_enabled") is True', launcher)

    def test_desktop_launcher_waits_for_async_removal_and_port_release(self):
        result, events = self._run_launcher_scenario("launcher_async")
        self.assertEqual(result.returncode, 0, result.stderr)
        loaded = f"launchctl print {DESK_SERVICE_TARGET} loaded"
        absent = f"launchctl print {DESK_SERVICE_TARGET} absent"
        bootout = f"launchctl bootout {DESK_SERVICE_TARGET}"
        self.assertGreaterEqual(events.count(loaded), 3)
        self.assertGreaterEqual(events.count("lsof busy old-desk"), 2)
        self.assertLess(events.index(bootout), events.index(absent))
        self.assertLess(events.index(absent), events.index("lsof free"))
        self.assertLess(events.index("lsof free"), events.index("launchctl submit success"))
        self.assertLess(events.index("launchctl submit success"),
                        next(index for index, event in enumerate(events) if event.startswith("open ")))

    def test_desktop_launcher_fails_closed_when_submit_fails(self):
        result, events = self._run_launcher_scenario("submit_fail")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("launchctl submit failed", events)
        self.assertIn("alert", events)
        self.assertFalse(any(event.startswith("open ") for event in events))

    def test_desktop_launcher_does_not_kill_an_unrelated_port_owner(self):
        result, events = self._run_launcher_scenario("occupied")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("lsof busy unrelated", events)
        self.assertFalse(any(event.startswith("launchctl submit") for event in events))
        self.assertFalse(any(event.startswith("kill ") for event in events))
        self.assertFalse(any(event.startswith("open ") for event in events))

    def test_desktop_launcher_rejects_wrong_health_service(self):
        result, events = self._run_launcher_scenario("health_wrong")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("launchctl submit success", events)
        self.assertIn("curl wrong-service", events)
        self.assertGreaterEqual(events.count(f"launchctl bootout {DESK_SERVICE_TARGET}"), 2)
        self.assertFalse(any(event.startswith("open ") for event in events))

    def test_desktop_launcher_rejects_json_from_failed_curl(self):
        result, events = self._run_launcher_scenario("curl_exit_fail")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("launchctl submit success", events)
        self.assertIn("curl expected-service", events)
        self.assertFalse(any(event.startswith("open ") for event in events))

    def test_desktop_updater_bundles_verified_local_source_snapshot(self):
        updater = (ROOT / "ops" / "update_datawire_desktop_app.sh").read_text(encoding="utf-8")
        self.assertIn("florida_signal_project_state.json", updater)
        self.assertIn("florida_signal_v1.sqlite", updater)
        self.assertIn("nominate_pdmr_candidates.py", updater)
        self.assertIn("FL_SIGNAL_PROJECT_STATE_SOURCE", updater)
        self.assertIn("FL_SIGNAL_PDMR_DB_SOURCE", updater)
        self.assertIn("FL_SIGNAL_PDMR_CANDIDATE_SOURCE", updater)
        self.assertIn("pragma quick_check;", updater)
        self.assertIn("coordinate_desk_restart_after_update", updater)
        self.assertIn("is_expected_legacy_desk_pid", updater)
        self.assertIn('service_target="gui/$(/usr/bin/id -u)/$job_label"', updater)
        self.assertIn('"$launchctl_bin" bootout "$service_target"', updater)
        self.assertIn('/usr/bin/cmp -s "$project_state_source"', updater)

    def test_desktop_updater_removes_managed_job_before_reopen(self):
        result, events = self._run_updater_restart_scenario("updater_managed")
        self.assertEqual(result.returncode, 0, result.stderr)
        remove_index = events.index(f"launchctl bootout {DESK_SERVICE_TARGET}")
        absent_index = events.index(f"launchctl print {DESK_SERVICE_TARGET} absent")
        open_index = next(index for index, event in enumerate(events) if event.startswith("open "))
        self.assertLess(remove_index, absent_index)
        self.assertLess(absent_index, open_index)
        self.assertFalse(any(event.startswith("kill ") for event in events))

    def test_desktop_updater_kills_only_verified_legacy_app_listener(self):
        verified, verified_events = self._run_updater_restart_scenario("updater_legacy")
        self.assertEqual(verified.returncode, 0, verified.stderr)
        remove_index = verified_events.index(f"launchctl bootout {DESK_SERVICE_TARGET}")
        ps_index = next(index for index, event in enumerate(verified_events) if event.startswith("ps "))
        kill_index = verified_events.index("kill 321")
        open_index = next(index for index, event in enumerate(verified_events) if event.startswith("open "))
        self.assertLess(remove_index, ps_index)
        self.assertLess(ps_index, kill_index)
        self.assertLess(kill_index, open_index)

        unverified, unverified_events = self._run_updater_restart_scenario("updater_unverified")
        self.assertNotEqual(unverified.returncode, 0)
        self.assertTrue(any(event.startswith("ps ") for event in unverified_events))
        self.assertFalse(any(event.startswith("kill ") for event in unverified_events))
        self.assertFalse(any(event.startswith("open ") for event in unverified_events))

    def test_desktop_updater_preserves_separate_override_provenance_with_spaces(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "three separate sources"
            source_dir.mkdir()
            project_state = source_dir / "canonical project state.json"
            pdmr_db = source_dir / "pdmr evidence.sqlite"
            candidate = source_dir / "candidate source.py"
            project_payload = {"schema_version": "FloridaSignalProjectStateV1", "marker": "canonical"}
            project_state.write_text(json.dumps(project_payload), encoding="utf-8")
            with sqlite3.connect(pdmr_db) as db:
                db.execute("create table provenance (marker text not null)")
                db.execute("insert into provenance values ('pdmr-override')")
            candidate.write_text("# candidate-override\n", encoding="utf-8")
            destination = root / "staged app resources" / "florida-signal"
            env = os.environ.copy()
            env.update({
                "HOME": str(root / "home"),
                "FL_SIGNAL_PROJECT_STATE_SOURCE": str(project_state),
                "FL_SIGNAL_PDMR_DB_SOURCE": str(pdmr_db),
                "FL_SIGNAL_PDMR_CANDIDATE_SOURCE": str(candidate),
            })
            result = subprocess.run(
                [
                    "/bin/bash", "-c",
                    'source "$1"; copy_verified_source_snapshot "$2"',
                    "snapshot-test", str(ROOT / "ops" / "update_datawire_desktop_app.sh"),
                    str(destination),
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            bundled_state = destination / "data/reference/florida_signal_project_state.json"
            bundled_db = destination / "data/pdmr/florida_signal_v1.sqlite"
            bundled_candidate = destination / "scripts/nominate_pdmr_candidates.py"
            self.assertEqual(bundled_state.read_bytes(), project_state.read_bytes())
            self.assertEqual(bundled_db.read_bytes(), pdmr_db.read_bytes())
            self.assertEqual(bundled_candidate.read_bytes(), candidate.read_bytes())
            with sqlite3.connect(bundled_db) as db:
                marker = db.execute("select marker from provenance").fetchone()[0]
            self.assertEqual(marker, "pdmr-override")

    def test_pdmr_dates_are_labeled_as_portal_dates_not_filing_dates(self):
        explorer = (ROOT / "cms" / "data.html").read_text(encoding="utf-8")
        home = (ROOT / "cms" / "home.html").read_text(encoding="utf-8")
        self.assertIn('["event_date", "Portal date", dateish]', explorer)
        self.assertNotIn('["event_date", "Filed", dateish]', explorer)
        self.assertIn("newest portal date", home)
        self.assertNotIn("newest filing", home)


if __name__ == "__main__":
    unittest.main()
