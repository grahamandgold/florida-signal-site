import importlib.util
from datetime import datetime, timedelta, timezone
import hashlib
import inspect
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


def utility_health(
    rows, *, system_time="2026-09-01T01:00:00Z", metrics_override=None,
    natural_schedule_verified=True,
):
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
        "latest_attempt_at": system_time,
        "latest_attempt_status": "ok",
        "latest_successful_run_at": system_time,
        "latest_successful_run_id": "utility-test-run",
        "natural_schedule_verified": natural_schedule_verified,
        "natural_admission_run_id": (
            "utility-test-natural-run" if natural_schedule_verified else None
        ),
        "natural_admission_verified_at": (
            system_time if natural_schedule_verified else None
        ),
        "natural_admission_reason": (
            "independent_natural_run_admitted"
            if natural_schedule_verified
            else "independent_natural_run_admission_missing"
        ),
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

        exact_rows = [row for row in rows if cms_server.utility_intake_family(row["permit_number"])]
        with mock.patch.object(
            cms_server, "utility_intake_remote_projection", return_value=exact_rows,
        ) as read_projection, mock.patch.object(
            cms_server, "load_utility_intake_local_health", return_value=health[0],
        ), mock.patch.object(
            cms_server, "validate_utility_intake_health", side_effect=lambda value, *_args, **_kwargs: {
                **value,
                "validation": {"projection_bound": True, "fresh": True, "reason": None},
            },
        ):
            code, sewer = cms_server.utility_intake_payload({
                "lane": ["sewer_utility"], "limit": ["10"], "offset": ["0"],
            }, observed_at=UTILITY_NOW)
            _, engineering = cms_server.utility_intake_payload({
                "lane": ["engineering"], "limit": ["10"], "offset": ["0"],
            }, observed_at=UTILITY_NOW)
        self.assertEqual(read_projection.call_count, 2)
        self.assertEqual(code, 200)
        self.assertEqual({row["permit_number"] for row in sewer["items"]}, {
            "ENG-CR-260001", "ROW-SEW-260003.D001", "ROW-WTR-260004", "PLB-SEWCP-WT-260005",
        })
        self.assertEqual([row["permit_number"] for row in engineering["items"]], ["ENG-OAA-260002"])
        self.assertEqual(sewer["health"]["status"], "current")
        self.assertTrue(sewer["health"]["validation"]["projection_bound"])
        self.assertEqual(sewer["all_lane_record_count"], 5)
        self.assertEqual(sewer["last_collected"], "2026-09-01T01:00:00Z")
        self.assertIn("does not establish the serving utility", sewer["contract"])
        self.assertIn("no claim that a record predates PDMR", sewer["contract"])

    def test_utility_desk_transport_is_publishable_get_only_and_projection_pinned(self):
        row = utility_row("ENG-CR-260001", applied_date="2026-08-30")

        class Response:
            headers = {"Content-Range": "0-0/1"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return json.dumps([row]).encode("utf-8")

        opener = mock.Mock()
        opener.open.return_value = Response()
        with mock.patch.object(
            cms_server, "SUPABASE_URL", "https://project-ref.supabase.co",
        ), mock.patch.object(
            cms_server, "SUPABASE_ANON_KEY", "sb_publishable_" + "x" * 24,
        ), mock.patch.object(
            cms_server.urllib.request, "build_opener", return_value=opener,
        ) as build_opener:
            page = cms_server.utility_intake_read_projection_page(cursor=None, limit=10)
        request = opener.open.call_args.args[0]
        query = parse_qs(urlparse(request.full_url).query)
        self.assertIsInstance(build_opener.call_args.args[0], cms_server._UtilityRejectRedirects)
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(urlparse(request.full_url).path, "/rest/v1/permits")
        self.assertEqual(query["select"], [",".join(cms_server.UTILITY_INTAKE_PARITY_COLUMNS)])
        self.assertEqual(query["order"], ["permit_number.asc"])
        self.assertNotIn("offset", query)
        self.assertEqual(request.get_header("Apikey"), "sb_publishable_" + "x" * 24)
        self.assertIsNone(request.get_header("Authorization"))
        self.assertIsNone(request.data)
        self.assertEqual(page["rows"][0]["permit_number"], "ENG-CR-260001")

    def test_utility_desk_transport_rejects_service_role_or_unpinned_origin(self):
        with mock.patch.object(cms_server, "SUPABASE_ANON_KEY", "sb_secret_forbidden"):
            with self.assertRaisesRegex(ValueError, "anon publishable"):
                cms_server.utility_intake_read_projection_page(cursor=None, limit=10)
        with mock.patch.object(
            cms_server, "SUPABASE_URL", "https://supabase.co.evil.example",
        ), mock.patch.object(
            cms_server, "SUPABASE_ANON_KEY", "sb_publishable_" + "x" * 24,
        ):
            with self.assertRaisesRegex(ValueError, "pinned"):
                cms_server.utility_intake_read_projection_page(cursor=None, limit=10)
        payload_source = inspect.getsource(cms_server.utility_intake_payload)
        self.assertNotIn("supabase_request", payload_source)
        self.assertIn("utility_intake_remote_projection", payload_source)

    def test_utility_intake_duplicate_identity_fails_closed(self):
        duplicate = utility_row("ROW-SEW-260003", applied_date="2026-08-29")
        with mock.patch.object(
            cms_server,
            "utility_intake_remote_projection",
            return_value=[duplicate, dict(duplicate)],
        ):
            code, payload = cms_server.utility_intake_payload({"lane": ["all"]})
        self.assertEqual(code, 502)
        self.assertIn("Duplicate utility identity", payload["error"])

    def test_utility_intake_pages_until_explicit_empty_even_after_short_page(self):
        rows = [
            utility_row(f"ROW-SEW-26000{index}", applied_date="2026-08-29")
            for index in range(3)
        ]
        cursors = []

        def page(*, cursor, limit):
            cursors.append(cursor)
            remaining = [row for row in rows if cursor is None or row["permit_number"] > cursor]
            payload = remaining[:2]
            return {
                "cursor": cursor,
                "next_cursor": payload[-1]["permit_number"] if payload else cursor,
                "scanned_count": len(payload),
                "declared_total": len(remaining),
                "exhausted": not payload,
                "rows": payload,
            }

        with mock.patch.object(cms_server, "utility_intake_read_projection_page", side_effect=page):
            payload = cms_server._utility_remote_projection_once()
        self.assertEqual(len(payload), 3)
        self.assertEqual(cursors, [None, rows[1]["permit_number"], rows[2]["permit_number"]])

    def test_utility_intake_health_loads_only_from_hash_bound_local_receipts(self):
        rows = [utility_row("ENG-CR-260001", applied_date="2026-08-30")]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipts = root / "receipts"
            receipts.mkdir()
            producer_receipts = Path("/producer/utility-intake/receipts")
            counts = {
                "records_attempted": 1,
                "records_written": 0,
                "records_rejected": 0,
                "sqlite_records": 1,
                "supabase_records": 1,
            }
            proof = cms_server.utility_intake_projection_proof(rows)
            parity = {"status": "passed", "sqlite": proof, "supabase": proof}
            versions = {"collector": "utility/1", "query": "q/1", "parser": "p/1"}
            execution = {
                "execution_context": "systemd_timer_expected",
                "systemd_invocation_id": "a" * 32,
                "service_unit": "florida-utility-intake.service",
                "expected_timer_unit": "florida-utility-intake.timer",
                "natural_schedule_verified": False,
                "verification_contract": "correlate journal",
            }
            verification_path = receipts / "bound.verification.json"
            verification_path.write_text(json.dumps({
                "schema_version": cms_server.UTILITY_INTAKE_VERIFICATION_SCHEMA,
                "run_id": "utility-local-binding",
                "status": "verified",
                "completed_at": "2026-09-01T01:00:00Z",
                "counts": counts,
                "parity": parity,
                "versions": versions,
                "execution": execution,
            }, sort_keys=True) + "\n", encoding="utf-8")
            verification_sha = hashlib.sha256(verification_path.read_bytes()).hexdigest()
            health = utility_health(rows, metrics_override={
                "verification_receipt_path": str(producer_receipts / verification_path.name),
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
                    "receipt_path": str(producer_receipts / verification_path.name),
                    "receipt_sha256": verification_sha,
                },
                "health": health,
                "versions": versions,
                "execution": execution,
            }
            outcome_path = receipts / "utility-local-binding.json"
            outcome_path.write_text(json.dumps(outcome, sort_keys=True) + "\n", encoding="utf-8")
            pointer = {
                "schema_version": cms_server.UTILITY_INTAKE_LATEST_SCHEMA,
                "pointer_kind": "attempt",
                "run_id": "utility-local-binding",
                "status": "ok",
                "updated_at": "2026-09-01T01:00:00Z",
                "receipt_path": str(producer_receipts / outcome_path.name),
                "receipt_sha256": hashlib.sha256(outcome_path.read_bytes()).hexdigest(),
                "counts": outcome["counts"],
                "execution": execution,
            }
            latest_attempt = root / "latest-attempt.json"
            latest_success = root / "latest-success.json"
            latest_attempt.write_text(json.dumps(pointer, sort_keys=True) + "\n", encoding="utf-8")
            success_pointer = {**pointer, "pointer_kind": "success"}
            latest_success.write_text(
                json.dumps(success_pointer, sort_keys=True) + "\n", encoding="utf-8",
            )
            natural_attestation_path = receipts / "utility-local-binding.natural.json"
            natural_schedule = {
                "timer_unit": cms_server.UTILITY_INTAKE_TIMER_UNIT,
                "service_unit": cms_server.UTILITY_INTAKE_SERVICE_UNIT,
                "timer_active": True,
                "timer_enabled": True,
                "timer_target": cms_server.UTILITY_INTAKE_SERVICE_UNIT,
                "timer_last_trigger": "Mon 2026-09-01 01:00:00 UTC",
                "timer_last_trigger_realtime_usec": 100,
                "timer_last_trigger_monotonic": "123456",
                "timer_next_elapse": "Mon 2026-09-01 01:27:00 UTC",
                "trigger_realtime_usec": 100,
                "outcome_started_realtime_usec": 103,
                "trigger_to_outcome_start_usec": 3,
                "service_journal_first_realtime_usec": 101,
                "service_journal_last_realtime_usec": 104,
            }
            natural_attestation = {
                "schema_version": cms_server.UTILITY_INTAKE_NATURAL_SCHEMA,
                "status": "verified",
                "run_id": "utility-local-binding",
                "verified_at": "2026-09-01T01:05:00Z",
                "outcome": {
                    "receipt_path": str(producer_receipts / outcome_path.name),
                    "receipt_sha256": pointer["receipt_sha256"],
                    "completed_at": outcome["completed_at"],
                    "counts": counts,
                    "versions": versions,
                },
                "verification": outcome["verification"],
                "execution": execution,
                "schedule": natural_schedule,
                "evidence": {
                    "latest_attempt_sha256": hashlib.sha256(
                        latest_attempt.read_bytes()
                    ).hexdigest(),
                    "latest_success_sha256": hashlib.sha256(
                        latest_success.read_bytes()
                    ).hexdigest(),
                    "timer_show_sha256": "3" * 64,
                    "timer_journal_sha256": "4" * 64,
                    "service_journal_sha256": "5" * 64,
                },
                "contract": "Independent test-only natural admission.",
            }
            natural_attestation_path.write_text(
                json.dumps(natural_attestation, sort_keys=True) + "\n", encoding="utf-8",
            )
            latest_natural = root / "latest-natural.json"
            latest_natural.write_text(json.dumps({
                "schema_version": cms_server.UTILITY_INTAKE_NATURAL_LATEST_SCHEMA,
                "pointer_kind": "natural",
                "run_id": "utility-local-binding",
                "status": "verified",
                "updated_at": natural_attestation["verified_at"],
                "receipt_path": str(producer_receipts / natural_attestation_path.name),
                "receipt_sha256": hashlib.sha256(
                    natural_attestation_path.read_bytes()
                ).hexdigest(),
                "outcome_receipt_path": str(producer_receipts / outcome_path.name),
                "outcome_receipt_sha256": pointer["receipt_sha256"],
                "execution": execution,
            }, sort_keys=True) + "\n", encoding="utf-8")

            with mock.patch.object(
                cms_server, "UTILITY_INTAKE_RECEIPT_DIR", receipts,
            ), mock.patch.object(
                cms_server, "UTILITY_INTAKE_PRODUCER_RECEIPT_DIR", producer_receipts,
            ), mock.patch.object(
                cms_server, "UTILITY_INTAKE_LATEST_ATTEMPT_POINTER", latest_attempt,
            ), mock.patch.object(
                cms_server, "UTILITY_INTAKE_LATEST_SUCCESS_POINTER", latest_success,
            ), mock.patch.object(
                cms_server, "UTILITY_INTAKE_LATEST_NATURAL_POINTER", latest_natural,
            ):
                loaded = cms_server.load_utility_intake_local_health()
                self.assertEqual(loaded["status"], "current")
                self.assertEqual(loaded["metrics"]["verification_receipt_sha256"], verification_sha)
                self.assertTrue(loaded["natural_schedule_verified"])
                self.assertEqual(
                    loaded["natural_admission_run_id"], "utility-local-binding",
                )

                outcome["health"]["metrics"]["sqlite_rows"] = 2
                outcome_path.write_text(
                    json.dumps(outcome, sort_keys=True) + "\n", encoding="utf-8",
                )
                pointer["receipt_sha256"] = hashlib.sha256(
                    outcome_path.read_bytes()
                ).hexdigest()
                latest_attempt.write_text(
                    json.dumps(pointer, sort_keys=True) + "\n", encoding="utf-8",
                )
                success_pointer["receipt_sha256"] = pointer["receipt_sha256"]
                latest_success.write_text(
                    json.dumps(success_pointer, sort_keys=True) + "\n", encoding="utf-8",
                )
                metric_rejected = cms_server.load_utility_intake_local_health()
                self.assertEqual(metric_rejected["status"], "unverified")

                outcome["health"]["metrics"]["sqlite_rows"] = 1
                outcome_path.write_text(
                    json.dumps(outcome, sort_keys=True) + "\n", encoding="utf-8",
                )
                pointer["receipt_sha256"] = "0" * 64
                latest_attempt.write_text(
                    json.dumps(pointer, sort_keys=True) + "\n", encoding="utf-8",
                )
                rejected = cms_server.load_utility_intake_local_health()
                self.assertEqual(rejected["status"], "unverified")
                self.assertNotIn(str(outcome_path), rejected["detail"])

    def test_utility_intake_health_preserves_latest_success_after_failed_attempt(self):
        attempt = {
            "run_id": "utility-failed-attempt",
            "status": "failed",
            "completed_at": "2026-09-01T01:27:00Z",
            "execution": {"systemd_invocation_id": "b" * 32},
            "health": {
                "component": "utility-intake",
                "status": "error",
                "system_time": "2026-09-01T01:27:00Z",
                "detail": "bounded failure",
                "metrics": {},
            },
        }
        success = {
            "run_id": "utility-prior-success",
            "status": "ok",
            "completed_at": "2026-09-01T00:57:00Z",
            "execution": {"systemd_invocation_id": "a" * 32},
            "health": {
                "component": "utility-intake",
                "status": "current",
                "system_time": "2026-09-01T00:57:00Z",
                "metrics": {},
            },
        }

        with mock.patch.object(
            cms_server, "_load_utility_pointer", side_effect=[attempt, success],
        ) as load_pointer:
            health = cms_server.load_utility_intake_local_health()

        self.assertEqual(
            load_pointer.call_args_list,
            [
                mock.call(cms_server.UTILITY_INTAKE_LATEST_ATTEMPT_POINTER, "attempt"),
                mock.call(cms_server.UTILITY_INTAKE_LATEST_SUCCESS_POINTER, "success"),
            ],
        )
        self.assertEqual(health["status"], "error")
        self.assertEqual(health["latest_attempt_status"], "failed")
        self.assertEqual(health["latest_attempt_at"], "2026-09-01T01:27:00Z")
        self.assertEqual(health["latest_successful_run_id"], "utility-prior-success")
        self.assertEqual(health["latest_successful_run_at"], "2026-09-01T00:57:00Z")
        self.assertEqual(health["latest_success_execution"], success["execution"])

    def test_prior_natural_run_cannot_admit_a_new_manual_success(self):
        outcome = {
            "run_id": "utility-new-manual-success",
            "status": "ok",
            "completed_at": "2026-09-01T01:00:00Z",
            "execution": {"systemd_invocation_id": "a" * 32},
            "versions": {"collector": "utility/1", "query": "q/1", "parser": "p/1"},
            "_local_receipt_sha256": "1" * 64,
            "_latest_pointer_sha256": "2" * 64,
            "health": {
                "component": "utility-intake",
                "status": "current",
                "system_time": "2026-09-01T01:00:00Z",
                "metrics": {},
            },
        }
        admission = {
            "run_id": "utility-prior-natural",
            "verified_at": "2026-09-01T00:30:00Z",
            "versions": outcome["versions"],
            "outcome_receipt_sha256": outcome["_local_receipt_sha256"],
            "latest_success_pointer_sha256": outcome["_latest_pointer_sha256"],
            "schedule": {"timer_enabled": True},
        }
        with mock.patch.object(
            cms_server, "_load_utility_pointer", side_effect=[outcome, outcome],
        ), mock.patch.object(
            cms_server, "_load_utility_natural_admission", return_value=admission,
        ):
            health = cms_server.load_utility_intake_local_health()
        self.assertFalse(health["natural_schedule_verified"])
        self.assertEqual(
            health["natural_admission_reason"], "latest_success_not_naturally_admitted",
        )

    def test_same_run_label_cannot_substitute_changed_success_bytes(self):
        outcome = {
            "run_id": "utility-shared-label",
            "status": "ok",
            "completed_at": "2026-09-01T01:00:00Z",
            "execution": {"systemd_invocation_id": "a" * 32},
            "versions": {"collector": "utility/1", "query": "q/1", "parser": "p/1"},
            "_local_receipt_sha256": "1" * 64,
            "_latest_pointer_sha256": "2" * 64,
            "health": {
                "component": "utility-intake",
                "status": "current",
                "system_time": "2026-09-01T01:00:00Z",
                "metrics": {},
            },
        }
        admission = {
            "run_id": outcome["run_id"],
            "verified_at": "2026-09-01T01:05:00Z",
            "versions": outcome["versions"],
            "outcome_receipt_sha256": "3" * 64,
            "latest_success_pointer_sha256": outcome["_latest_pointer_sha256"],
            "schedule": {"timer_enabled": True},
        }
        with mock.patch.object(
            cms_server, "_load_utility_pointer", side_effect=[outcome, outcome],
        ), mock.patch.object(
            cms_server, "_load_utility_natural_admission", return_value=admission,
        ):
            health = cms_server.load_utility_intake_local_health()
        self.assertFalse(health["natural_schedule_verified"])
        self.assertEqual(
            health["natural_admission_reason"],
            "latest_success_bytes_not_naturally_admitted",
        )

    def test_utility_receipt_refresher_repeats_after_failure_and_stops_with_desk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "sync.py"
            script.write_text("# test helper\n", encoding="utf-8")
            known_hosts = root / "known_hosts"
            known_hosts.write_text("florida ssh-ed25519 test\n", encoding="utf-8")
            finished = cms_server.threading.Event()
            calls = []

            def runner(command, **kwargs):
                calls.append((command, kwargs))
                if len(calls) == 1:
                    return subprocess.CompletedProcess(command, 1, stdout="", stderr="failed")
                finished.set()
                return subprocess.CompletedProcess(
                    command, 0, stdout='{"status":"synced"}\n', stderr="",
                )

            refresher = cms_server.UtilityReceiptRefresher(
                script=script,
                destination=root / "local",
                ssh_host="florida",
                known_hosts=known_hosts,
                interval_seconds=0.01,
                process_timeout_seconds=1,
                runner=runner,
            )
            refresher.start()
            self.assertTrue(finished.wait(1), "recurring refresh did not retry")
            refresher.stop()

            call_count = len(calls)
            self.assertGreaterEqual(call_count, 2)
            self.assertEqual(refresher.last_status, "synced")
            self.assertIn("--known-hosts", calls[-1][0])
            self.assertEqual(calls[-1][0][-1], str(known_hosts))
            self.assertTrue(calls[-1][1]["check"] is False)
            self.assertEqual(calls[-1][1]["timeout"], 1)
            cms_server.threading.Event().wait(0.03)
            self.assertEqual(len(calls), call_count)

    def test_utility_receipt_refresher_failure_preserves_snapshot_for_stale_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "sync.py"
            script.write_text("# test helper\n", encoding="utf-8")
            known_hosts = root / "known_hosts"
            known_hosts.write_text("florida ssh-ed25519 test\n", encoding="utf-8")
            destination = root / "local"
            destination.mkdir()
            prior = destination / "latest-success.json"
            prior.write_text("preserved receipt pointer\n", encoding="utf-8")

            refresher = cms_server.UtilityReceiptRefresher(
                script=script,
                destination=destination,
                ssh_host="florida",
                known_hosts=known_hosts,
                runner=lambda command, **kwargs: subprocess.CompletedProcess(
                    command, 1, stdout="", stderr="network unavailable",
                ),
            )
            self.assertFalse(refresher.sync_once())
            self.assertEqual(refresher.last_status, "sync_failed")
            self.assertEqual(prior.read_text(encoding="utf-8"), "preserved receipt pointer\n")

            rows = [utility_row("ENG-CR-260001", applied_date="2026-08-30")]
            stale = utility_health(rows, system_time="2026-08-31T23:00:00Z")[0]
            proof = cms_server.utility_intake_projection_proof(rows)
            verification = destination / "test.verification.json"
            verification.write_text("{}\n", encoding="utf-8")
            stale["metrics"].update({
                "verification_receipt_path": str(verification),
                "verification_receipt_sha256": hashlib.sha256(
                    verification.read_bytes()
                ).hexdigest(),
            })
            with mock.patch.object(
                cms_server, "UTILITY_INTAKE_RECEIPT_DIR", destination,
            ):
                checked = cms_server.validate_utility_intake_health(
                    stale, proof, observed_at=UTILITY_NOW,
                )
            self.assertEqual(checked["status"], "stale")
            self.assertEqual(checked["validation"]["reason"], "scheduled_receipt_overdue")

    def test_utility_receipt_refresher_lifecycle_is_owned_by_server(self):
        events = []

        class Refresher:
            def start(self):
                events.append("refresh-start")

            def stop(self):
                events.append("refresh-stop")

        class Server:
            def __init__(self, address, handler):
                events.append(("server-created", address, handler))

            def serve_forever(self):
                events.append("serve")

            def server_close(self):
                events.append("server-close")

        cms_server.serve_data_wire(
            "127.0.0.1", 8788, refresher=Refresher(), server_factory=Server,
        )
        self.assertEqual(
            events,
            [
                ("server-created", ("127.0.0.1", 8788), cms_server.Handler),
                "refresh-start", "serve", "refresh-stop", "server-close",
            ],
        )

    def test_utility_receipt_refresher_start_failure_still_closes_server(self):
        events = []

        class Refresher:
            def start(self):
                events.append("refresh-start-failed")
                raise RuntimeError("thread unavailable")

            def stop(self):
                events.append("unexpected-stop")

        class Server:
            def __init__(self, _address, _handler):
                pass

            def serve_forever(self):
                events.append("unexpected-serve")

            def server_close(self):
                events.append("server-close")

        with self.assertRaisesRegex(RuntimeError, "thread unavailable"):
            cms_server.serve_data_wire(
                "127.0.0.1", 8788, refresher=Refresher(), server_factory=Server,
            )
        self.assertEqual(events, ["refresh-start-failed", "server-close"])

    def test_utility_receipt_refresher_stop_terminates_active_helper_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "blocking-sync.py"
            script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
            known_hosts = root / "known_hosts"
            known_hosts.write_text("florida ssh-ed25519 test\n", encoding="utf-8")
            refresher = cms_server.UtilityReceiptRefresher(
                script=script,
                destination=root / "local",
                ssh_host="florida",
                known_hosts=known_hosts,
                interval_seconds=300,
                process_timeout_seconds=30,
            )
            refresher.start()
            process = None
            for _attempt in range(100):
                with refresher._process_lock:
                    process = refresher._active_process
                if process is not None:
                    break
                cms_server.threading.Event().wait(0.01)
            self.assertIsNotNone(process, "managed sync helper did not start")
            refresher.stop()
            self.assertIsNone(refresher._thread)
            self.assertIsNotNone(process.poll())

    def test_utility_intake_health_downgrades_projection_mismatch_and_staleness(self):
        rows = [utility_row("ENG-CR-260001", applied_date="2026-08-30")]
        mismatch = utility_health(rows, metrics_override={"supabase_rows": 99})
        stale = utility_health(rows, system_time="2026-08-31T23:00:00Z")

        def run(health):
            with tempfile.TemporaryDirectory() as tmp:
                receipt_dir = Path(tmp)
                receipt = receipt_dir / "health.verification.json"
                receipt.write_text("{}\n", encoding="utf-8")
                health[0]["metrics"].update({
                    "verification_receipt_path": str(receipt),
                    "verification_receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
                })
                with mock.patch.object(
                    cms_server, "utility_intake_remote_projection", return_value=rows,
                ), mock.patch.object(
                    cms_server, "load_utility_intake_local_health", return_value=health[0],
                ), mock.patch.object(
                    cms_server, "UTILITY_INTAKE_RECEIPT_DIR", receipt_dir,
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

    def test_utility_intake_manual_canary_cannot_render_current_or_automated(self):
        rows = [utility_row("ENG-CR-260001", applied_date="2026-08-30")]
        health = utility_health(
            rows,
            system_time="2026-09-01T01:00:00Z",
            natural_schedule_verified=False,
        )[0]
        checked = cms_server.validate_utility_intake_health(
            health,
            cms_server.utility_intake_projection_proof(rows),
            observed_at=UTILITY_NOW,
        )
        self.assertEqual(checked["reported_status"], "current")
        self.assertEqual(checked["status"], "unverified")
        self.assertFalse(checked["validation"]["natural_schedule_verified"])
        self.assertEqual(
            checked["validation"]["reason"],
            "independent_natural_run_admission_missing",
        )

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
            receipt_path.write_text("{}\n", encoding="utf-8")
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
        self.assertIn('data-receipt-automation', html)
        self.assertIn('manual canary does not establish automation', html)
        self.assertIn('data-receipt-attempt', html)
        self.assertIn('Latest successful parity run', html)
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
        self.assertIn('FL_SIGNAL_UTILITY_LOCAL_ROOT="$utility_local_root"', launcher)
        self.assertIn('FL_SIGNAL_UTILITY_LATEST_ATTEMPT_POINTER="$utility_local_root/latest-attempt.json"', launcher)
        self.assertIn('FL_SIGNAL_UTILITY_LATEST_SUCCESS_POINTER="$utility_local_root/latest-success.json"', launcher)
        self.assertIn('FL_SIGNAL_UTILITY_LATEST_NATURAL_POINTER="$utility_local_root/latest-natural.json"', launcher)
        self.assertIn('FL_SIGNAL_UTILITY_SYNC_SCRIPT="$utility_sync_script"', launcher)
        self.assertIn('FL_SIGNAL_UTILITY_KNOWN_HOSTS="$utility_known_hosts"', launcher)
        self.assertIn('FL_SIGNAL_UTILITY_SYNC_INTERVAL_SECONDS="$utility_sync_interval"', launcher)
        self.assertIn('sync_utility_intake_receipts.py', launcher)
        self.assertNotIn('/usr/bin/python3 "$utility_sync_script"', launcher)
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
        self.assertIn("sync_utility_intake_receipts.py", updater)
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
