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


class UtilityDeskBridgeTests(unittest.TestCase):
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
        self.assertIn("and(permit_number.gte.ENG-CR,permit_number.lt.ENG-CS,permit_number.like.ENG-CR-*)", query["or"][0])
        self.assertIn("and(permit_number.gte.PLB-SEWCP-WT,permit_number.lt.PLB-SEWCP-WU,permit_number.like.PLB-SEWCP-WT-*)", query["or"][0])
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
