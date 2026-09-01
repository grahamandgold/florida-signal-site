from __future__ import annotations

import base64
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
SHADOW_PATH = ROOT / "ops/droplet/utility_intake_shadow.py"
PRODUCTION_PATH = ROOT / "ops/droplet/utility_intake_production.py"

shadow_spec = importlib.util.spec_from_file_location("utility_intake_shadow", SHADOW_PATH)
shadow = importlib.util.module_from_spec(shadow_spec)
assert shadow_spec.loader is not None
sys.modules[shadow_spec.name] = shadow
shadow_spec.loader.exec_module(shadow)

production_spec = importlib.util.spec_from_file_location("utility_intake_production", PRODUCTION_PATH)
production = importlib.util.module_from_spec(production_spec)
assert production_spec.loader is not None
sys.modules[production_spec.name] = production
production_spec.loader.exec_module(production)


FIXED = dt.datetime(2026, 8, 31, 20, 0, tzinfo=dt.timezone.utc)


def fixture(path: Path) -> list[dict[str, object]]:
    connection = sqlite3.connect(path)
    columns = list(production.PARITY_COLUMNS)
    connection.execute(
        "CREATE TABLE permits (" + ",".join(f'\"{column}\" TEXT' for column in columns) + ")"
    )
    values = [
        {
            "permit_number": "ENG-CR-26010001",
            "report_source": "opened_permits",
            "permit_type": "Capacity Request",
            "status": "Applied",
            "applied_date": "2026-08-30",
            "issued_date": None,
            "opened_date": "2026-08-30",
            "finalized_date": None,
            "address": "100 N Andrews Ave",
            "parcel_id": "504210010010",
            "owner_name": "Example Owner",
            "contractor_name": None,
            "description": "Capacity availability",
            "first_seen_at": "2026-08-30T10:00:00Z",
            "last_seen_at": "2026-08-31T10:00:00Z",
            "last_updated_at": "2026-08-31T10:00:00Z",
        },
        {
            "permit_number": "ROW-SEW-26010002.D001",
            "report_source": "opened_permits",
            "permit_type": "Sewer ROW",
            "status": "Open",
            "applied_date": "2026-08-31",
            "issued_date": None,
            "opened_date": "2026-08-31",
            "finalized_date": None,
            "address": "101 N Andrews Ave",
            "parcel_id": "504210010011",
            "owner_name": "Second Owner",
            "contractor_name": "Example Contractor",
            "description": "Sewer work",
            "first_seen_at": "2026-08-31T10:00:00Z",
            "last_seen_at": "2026-08-31T11:00:00Z",
            "last_updated_at": "2026-08-31T11:00:00Z",
        },
    ]
    for row in values:
        connection.execute(
            f"INSERT INTO permits ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
            [row[column] for column in columns],
        )
    connection.commit()
    connection.close()
    return values


class FakeTransport:
    def __init__(
        self,
        remote_rows: list[dict[str, object]],
    ) -> None:
        self.remote_rows = remote_rows
        self.calls: list[tuple[str, str | None]] = []

    def read_projection_page(self, *, cursor=None, limit=1000):
        self.calls.append(("read_projection", cursor))
        ordered = sorted(self.remote_rows, key=lambda row: str(row.get("permit_number") or ""))
        remaining = [row for row in ordered if cursor is None or str(row.get("permit_number") or "") > cursor]
        raw_page = remaining[:limit]
        next_cursor = str(raw_page[-1]["permit_number"]) if raw_page else cursor
        return {
            "schema_version": production.READ_ONLY_TRANSPORT_SCHEMA,
            "projection": production.parity_projection_contract(),
            "cursor": cursor,
            "next_cursor": next_cursor,
            "scanned_count": len(raw_page),
            "declared_total": len(remaining),
            "exhausted": not raw_page,
            "rows": [dict(row) for row in raw_page],
        }


class UtilityIntakeProductionTests(unittest.TestCase):
    def run_case(self, root: Path, transport: FakeTransport):
        database = fixture(root / "permits.sqlite")
        lock = root / ".writer.lock"
        lock.touch()
        before = hashlib.sha256((root / "permits.sqlite").read_bytes()).hexdigest()
        result = production.run_production(
            sqlite_path=root / "permits.sqlite",
            writer_lock_path=lock,
            evidence_dir=root / "runs",
            receipt_dir=root / "receipts",
            latest_attempt_pointer=root / "latest-attempt.json",
            latest_success_pointer=root / "latest-success.json",
            transport=transport,
            run_id="utility-production-test",
            clock=lambda: FIXED,
        )
        after = hashlib.sha256((root / "permits.sqlite").read_bytes()).hexdigest()
        self.assertEqual(before, after)
        return database, result

    def test_complete_parity_writes_immutable_receipt_and_current_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = fixture(root / "remote.sqlite")
            (root / "remote.sqlite").unlink()
            transport = FakeTransport(remote)
            _, result = self.run_case(root, transport)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["exit_code"], 0)
            pointer = json.loads((root / "latest-attempt.json").read_text())
            success_pointer = json.loads((root / "latest-success.json").read_text())
            self.assertEqual(pointer["pointer_kind"], "attempt")
            self.assertEqual(success_pointer["pointer_kind"], "success")
            self.assertEqual(success_pointer["run_id"], pointer["run_id"])
            receipt = json.loads(Path(pointer["receipt_path"]).read_text())
            self.assertEqual(receipt["counts"]["records_attempted"], 2)
            self.assertEqual(receipt["counts"]["records_written"], 0)
            self.assertEqual(receipt["counts"]["records_rejected"], 0)
            self.assertEqual(receipt["parity"]["status"], "passed")
            self.assertEqual(
                receipt["parity"]["supabase"]["projection"]["version"],
                production.PARITY_PROJECTION_VERSION,
            )
            self.assertEqual(receipt["health"]["metrics"]["remote_stability_reads"], 2)
            self.assertTrue(
                receipt["health"]["metrics"]["remote_exact_count_reconciled"]
            )
            self.assertEqual(receipt["health"]["status"], "current")
            self.assertEqual(receipt["health"]["event_through"], "2026-08-31")
            verification = receipt["verification"]
            self.assertTrue(Path(verification["receipt_path"]).is_file())
            self.assertEqual(
                hashlib.sha256(Path(verification["receipt_path"]).read_bytes()).hexdigest(),
                verification["receipt_sha256"],
            )
            self.assertEqual(
                receipt["health"]["metrics"]["verification_receipt_sha256"],
                verification["receipt_sha256"],
            )
            self.assertEqual(Path(pointer["receipt_path"]).stat().st_mode & 0o777, 0o600)
            self.assertEqual((root / "latest-attempt.json").stat().st_mode & 0o777, 0o600)
            self.assertEqual((root / "latest-success.json").stat().st_mode & 0o777, 0o600)

    def test_real_transport_is_get_only_and_exposes_only_the_declared_projection(self):
        exact = {column: None for column in production.PARITY_COLUMNS}
        exact["permit_number"] = "ENG-CR-26010001"
        child = dict(exact)
        child["permit_number"] = "ENG-CR-26010001.D001"

        class Response:
            headers = {"Content-Range": "0-1/2"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return json.dumps([exact, child]).encode("utf-8")

        transport = production.ReadOnlySupabaseTransport(
            "https://project-ref.supabase.co",
            "sb_publishable_" + "x" * 24,
        )
        opener = mock.Mock()
        opener.open.return_value = Response()
        with mock.patch.object(
            production.urllib.request, "build_opener", return_value=opener,
        ) as build_opener:
            page = transport.read_projection_page(cursor=None, limit=10)
        request = opener.open.call_args.args[0]
        query = parse_qs(urlparse(request.full_url).query)
        self.assertIsInstance(build_opener.call_args.args[0], production._RejectRedirects)
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(urlparse(request.full_url).path, "/rest/v1/permits")
        self.assertEqual(query["select"], [",".join(production.PARITY_COLUMNS)])
        self.assertEqual(query["order"], ["permit_number.asc"])
        self.assertIn("permit_number.like.ENG-CR-*", query["or"][0])
        self.assertEqual(set(query), {"select", "or", "order", "limit"})
        self.assertEqual(request.get_header("Apikey"), "sb_publishable_" + "x" * 24)
        self.assertIsNone(request.get_header("Authorization"))
        self.assertEqual(request.get_header("Prefer"), "count=exact")
        self.assertIsNone(request.data)
        self.assertEqual([row["permit_number"] for row in page["rows"]], ["ENG-CR-26010001"])
        self.assertEqual(page["scanned_count"], 2)
        self.assertEqual(page["declared_total"], 2)
        self.assertFalse(page["exhausted"])
        self.assertFalse(hasattr(transport, "publish_health"))
        self.assertFalse(hasattr(transport, "request_json"))

    def test_transport_rejects_service_role_and_nonproject_origins(self):
        payload = base64.urlsafe_b64encode(json.dumps({
            "role": "service_role",
        }).encode("utf-8")).decode("ascii").rstrip("=")
        service_role_jwt = f"header.{payload}.signature"
        for url, key in (
            ("https://project-ref.supabase.co", service_role_jwt),
            ("https://project-ref.supabase.co", "sb_secret_not-allowed-here"),
            ("https://example.com", "sb_publishable_" + "x" * 24),
            ("https://project-ref.supabase.co.evil.example", "sb_publishable_" + "x" * 24),
        ):
            with self.subTest(url=url, key_prefix=key[:10]):
                with self.assertRaises(production.ProductionError):
                    production.ReadOnlySupabaseTransport(url, key)

    def test_local_health_clock_matches_the_immutable_receipt_clock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = fixture(root / "remote.sqlite")
            (root / "remote.sqlite").unlink()
            transport = FakeTransport(remote)
            _, result = self.run_case(root, transport)
            self.assertEqual(result["status"], "ok")
            receipt = json.loads(Path(result["receipt_path"]).read_text())
            self.assertEqual(receipt["health"]["system_time"], receipt["completed_at"])
            self.assertFalse(receipt["safety"]["supabase_health_pointer_upsert"])
            self.assertEqual(receipt["safety"]["remote_methods"], ["GET"])

    def test_row_drift_fails_closed_and_writes_local_error_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = fixture(root / "remote.sqlite")
            (root / "remote.sqlite").unlink()
            remote[0]["status"] = "Changed remotely"
            transport = FakeTransport(remote)
            _, result = self.run_case(root, transport)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["exit_code"], 1)
            receipt = json.loads(Path(result["receipt_path"]).read_text())
            self.assertEqual(receipt["parity"]["status"], "failed")
            self.assertIn("parity failed", receipt["reason_detail"])
            self.assertEqual(receipt["health"]["status"], "error")

    def test_remote_duplicate_identity_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = fixture(root / "remote.sqlite")
            (root / "remote.sqlite").unlink()
            transport = FakeTransport(remote + [dict(remote[0])])
            _, result = self.run_case(root, transport)
            self.assertEqual(result["exit_code"], 1)
            receipt = json.loads(Path(result["receipt_path"]).read_text())
            self.assertIn("duplicate identities", receipt["reason_detail"])

    def test_remote_duplicate_at_cursor_boundary_fails_exact_count_reconciliation(self):
        row = {
            column: ("ENG-CR-26010001" if column == "permit_number" else None)
            for column in production.PARITY_COLUMNS
        }
        with mock.patch.object(production, "REMOTE_PAGE_SIZE", 1):
            with self.assertRaisesRegex(
                production.ProductionError, "declared count changed during pagination",
            ):
                production._remote_projection_once(FakeTransport([row, dict(row)]))

    def test_remote_declared_count_above_scan_cap_fails_before_pagination(self):
        row = {
            column: ("ENG-CR-26010001" if column == "permit_number" else None)
            for column in production.PARITY_COLUMNS
        }

        class OversizeTransport(FakeTransport):
            def read_projection_page(self, *, cursor=None, limit=1000):
                payload = super().read_projection_page(cursor=cursor, limit=limit)
                payload["declared_total"] = production.REMOTE_SCAN_CAP + 1
                return payload

        with self.assertRaisesRegex(production.ProductionError, "exceeds its bounds"):
            production._remote_projection_once(OversizeTransport([row]))

    def test_remote_projection_pages_until_explicit_empty_on_both_stability_reads(self):
        rows = [
            {column: (f"ENG-CR-2601{index:04d}" if column == "permit_number" else None)
             for column in production.PARITY_COLUMNS}
            for index in range(3)
        ]
        transport = FakeTransport(rows)
        with mock.patch.object(production, "REMOTE_PAGE_SIZE", 2):
            projected = production._remote_projection(transport)
        self.assertEqual(len(projected), 3)
        cursors = [cursor for operation, cursor in transport.calls if operation == "read_projection"]
        self.assertEqual(cursors, [None, "ENG-CR-26010001", "ENG-CR-26010002", None, "ENG-CR-26010001", "ENG-CR-26010002"])

    def test_remote_projection_change_between_complete_reads_fails_closed(self):
        remote = [
            {column: ("ENG-CR-26010001" if column == "permit_number" else None)
             for column in production.PARITY_COLUMNS}
        ]

        class ChangingTransport(FakeTransport):
            def read_projection_page(self, *, cursor=None, limit=1000):
                first_page_calls = sum(
                    1 for operation, prior_cursor in self.calls
                    if operation == "read_projection" and prior_cursor is None
                )
                if cursor is None and first_page_calls >= 1:
                    self.remote_rows[0]["status"] = "changed during proof"
                return super().read_projection_page(cursor=cursor, limit=limit)

        with self.assertRaisesRegex(production.ProductionError, "changed across stability reads"):
            production._remote_projection(ChangingTransport(remote))

    def test_receipt_file_fsync_failure_prevents_local_health_receipt_and_removes_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = fixture(root / "remote.sqlite")
            (root / "remote.sqlite").unlink()
            transport = FakeTransport(remote)
            fixture(root / "permits.sqlite")
            lock = root / ".writer.lock"
            lock.touch()
            with mock.patch.object(production.os, "fsync", side_effect=OSError("simulated fsync")):
                with self.assertRaisesRegex(OSError, "simulated fsync"):
                    production.run_production(
                        sqlite_path=root / "permits.sqlite",
                        writer_lock_path=lock,
                        evidence_dir=root / "runs",
                        receipt_dir=root / "receipts",
                        latest_attempt_pointer=root / "latest-attempt.json",
                        latest_success_pointer=root / "latest-success.json",
                        transport=transport,
                        run_id="utility-production-fsync-file",
                        clock=lambda: FIXED,
                    )
            self.assertTrue(all(operation == "read_projection" for operation, _ in transport.calls))
            self.assertFalse((root / "receipts" / "utility-production-fsync-file.verification.json").exists())

    def test_receipt_directory_fsync_failure_prevents_local_health_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = fixture(root / "remote.sqlite")
            (root / "remote.sqlite").unlink()
            transport = FakeTransport(remote)
            fixture(root / "permits.sqlite")
            lock = root / ".writer.lock"
            lock.touch()
            with mock.patch.object(
                production, "_fsync_directory", side_effect=OSError("directory fsync"),
            ):
                with self.assertRaisesRegex(OSError, "directory fsync"):
                    production.run_production(
                        sqlite_path=root / "permits.sqlite",
                        writer_lock_path=lock,
                        evidence_dir=root / "runs",
                        receipt_dir=root / "receipts",
                        latest_attempt_pointer=root / "latest-attempt.json",
                        latest_success_pointer=root / "latest-success.json",
                        transport=transport,
                        run_id="utility-production-fsync-directory",
                        clock=lambda: FIXED,
                    )
            self.assertTrue(all(operation == "read_projection" for operation, _ in transport.calls))

    def test_configuration_receipt_refuses_a_symlink_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target"
            target.mkdir()
            receipt_link = root / "receipts"
            receipt_link.symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(production.ProductionError, "directory is unsafe"):
                production.write_configuration_failure(
                    receipt_dir=receipt_link,
                    latest_attempt_pointer=root / "latest-attempt.json",
                    run_id="utility-config-symlink-proof",
                    error=ValueError("missing config"),
                    clock=lambda: FIXED,
                )
            self.assertEqual(list(target.iterdir()), [])
            self.assertFalse((root / "latest-attempt.json").exists())

    def test_transport_configuration_failure_writes_sanitized_fsynced_receipt_and_pointer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stdout = io.StringIO()
            stderr = io.StringIO()
            secret_marker = "never-write-this-service-secret"
            args = [
                "--sqlite-path", str(root / "permits.sqlite"),
                "--writer-lock-path", str(root / ".writer.lock"),
                "--evidence-dir", str(root / "runs"),
                "--receipt-dir", str(root / "receipts"),
                "--latest-attempt-pointer", str(root / "latest-attempt.json"),
                "--latest-success-pointer", str(root / "latest-success.json"),
                "--run-id", "utility-config-failure",
            ]
            with mock.patch.object(
                production, "ReadOnlySupabaseTransport", side_effect=ValueError(secret_marker),
            ), redirect_stdout(stdout), redirect_stderr(stderr):
                code = production.main(args)
            self.assertEqual(code, 3)
            pointer = json.loads((root / "latest-attempt.json").read_text())
            receipt_path = Path(pointer["receipt_path"])
            receipt = json.loads(receipt_path.read_text())
            combined = stdout.getvalue() + stderr.getvalue() + receipt_path.read_text()
            self.assertNotIn(secret_marker, combined)
            self.assertEqual(receipt["reason_code"], "UTILITY_INTAKE_CONFIGURATION_FAILED")
            self.assertFalse(receipt["safety"]["secret_values_recorded"])
            self.assertEqual(receipt_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(hashlib.sha256(receipt_path.read_bytes()).hexdigest(), pointer["receipt_sha256"])

    def test_configuration_failure_fsyncs_create_only_receipt_and_atomic_pointer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real_open = production.os.open
            real_fsync = production.os.fsync
            with mock.patch.object(
                production.os, "open", wraps=real_open,
            ) as opened, mock.patch.object(
                production.os, "fsync", wraps=real_fsync,
            ) as fsynced:
                result = production.write_configuration_failure(
                    receipt_dir=root / "receipts",
                    latest_attempt_pointer=root / "latest-attempt.json",
                    run_id="utility-config-fsync-proof",
                    error=ValueError("sensitive value must not be recorded"),
                    clock=lambda: FIXED,
                )
            create_calls = [
                item for item in opened.call_args_list
                if len(item.args) >= 3 and item.args[1] & production.os.O_EXCL
            ]
            self.assertEqual(len(create_calls), 2)
            self.assertTrue(all(item.args[2] == 0o600 for item in create_calls))
            self.assertGreaterEqual(fsynced.call_count, 4)
            pointer = json.loads((root / "latest-attempt.json").read_text())
            receipt_path = Path(pointer["receipt_path"])
            self.assertEqual(result["receipt_sha256"], pointer["receipt_sha256"])
            self.assertNotIn("sensitive value", receipt_path.read_text())

    def test_optional_environment_path_reaches_python_and_receipts_missing_scoped_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = [
                "--sqlite-path", str(root / "permits.sqlite"),
                "--writer-lock-path", str(root / ".writer.lock"),
                "--evidence-dir", str(root / "runs"),
                "--receipt-dir", str(root / "receipts"),
                "--latest-attempt-pointer", str(root / "latest-attempt.json"),
                "--latest-success-pointer", str(root / "latest-success.json"),
                "--run-id", "utility-missing-scoped-config",
            ]
            with mock.patch.dict(
                production.os.environ, {}, clear=True,
            ), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = production.main(args)
            self.assertEqual(code, 3)
            receipt = json.loads(Path(json.loads((root / "latest-attempt.json").read_text())["receipt_path"]).read_text())
            self.assertEqual(receipt["reason_code"], "UTILITY_INTAKE_CONFIGURATION_FAILED")
            self.assertEqual(receipt["startup_stage"], "read_only_transport")

    def test_dependency_wait_failure_is_receipted_by_python_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            helper = root / "wait.sh"
            helper.write_text("#!/usr/bin/env bash\nexit 75\n", encoding="utf-8")
            helper.chmod(0o755)
            args = [
                "--sqlite-path", str(root / "permits.sqlite"),
                "--writer-lock-path", str(root / ".writer.lock"),
                "--evidence-dir", str(root / "runs"),
                "--receipt-dir", str(root / "receipts"),
                "--latest-attempt-pointer", str(root / "latest-attempt.json"),
                "--latest-success-pointer", str(root / "latest-success.json"),
                "--dependency-wait-command", str(helper),
                "--run-id", "utility-dependency-failure",
            ]
            environment = {
                "SUPABASE_URL": "https://project-ref.supabase.co",
                "SUPABASE_ANON_KEY": "sb_publishable_" + "x" * 24,
            }
            with mock.patch.dict(
                production.os.environ, environment, clear=True,
            ), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = production.main(args)
            self.assertEqual(code, 3)
            receipt = json.loads(Path(json.loads((root / "latest-attempt.json").read_text())["receipt_path"]).read_text())
            self.assertEqual(receipt["reason_code"], "UTILITY_INTAKE_DEPENDENCY_FAILED")
            self.assertEqual(receipt["startup_stage"], "dependency_wait")

    def test_missing_production_credential_file_is_receipted_after_python_starts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = [
                "--sqlite-path", str(root / "permits.sqlite"),
                "--writer-lock-path", str(root / ".writer.lock"),
                "--evidence-dir", str(root / "runs"),
                "--receipt-dir", str(root / "receipts"),
                "--latest-attempt-pointer", str(root / "latest-attempt.json"),
                "--latest-success-pointer", str(root / "latest-success.json"),
                "--credential-file", str(root / "missing.env"),
                "--run-id", "utility-missing-credential-file",
            ]
            with mock.patch.dict(
                production.os.environ, {}, clear=True,
            ), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = production.main(args)
            self.assertEqual(code, 3)
            pointer = json.loads((root / "latest-attempt.json").read_text())
            receipt = json.loads(Path(pointer["receipt_path"]).read_text())
            self.assertEqual(receipt["startup_stage"], "credential_file")
            self.assertEqual(receipt["health"]["status"], "error")

    def test_empty_source_cannot_publish_current_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            connection = sqlite3.connect(root / "permits.sqlite")
            columns = list(production.PARITY_COLUMNS)
            connection.execute(
                "CREATE TABLE permits (" + ",".join(f'\"{column}\" TEXT' for column in columns) + ")"
            )
            connection.commit()
            connection.close()
            lock = root / ".writer.lock"
            lock.touch()
            transport = FakeTransport([])
            result = production.run_production(
                sqlite_path=root / "permits.sqlite",
                writer_lock_path=lock,
                evidence_dir=root / "runs",
                receipt_dir=root / "receipts",
                latest_attempt_pointer=root / "latest-attempt.json",
                latest_success_pointer=root / "latest-success.json",
                transport=transport,
                run_id="utility-production-empty",
                clock=lambda: FIXED,
            )
            self.assertEqual(result["status"], "failed")
            receipt = json.loads(Path(result["receipt_path"]).read_text())
            self.assertEqual(receipt["health"]["status"], "error")
            self.assertIn("shadow evidence is not admissible: empty", receipt["reason_detail"])

    def test_failed_attempt_preserves_the_prior_latest_success_pointer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = fixture(root / "remote.sqlite")
            (root / "remote.sqlite").unlink()
            self.run_case(root, FakeTransport(remote))
            success_before = (root / "latest-success.json").read_bytes()
            remote[0]["status"] = "drifted"
            result = production.run_production(
                sqlite_path=root / "permits.sqlite",
                writer_lock_path=root / ".writer.lock",
                evidence_dir=root / "runs",
                receipt_dir=root / "receipts",
                latest_attempt_pointer=root / "latest-attempt.json",
                latest_success_pointer=root / "latest-success.json",
                transport=FakeTransport(remote),
                run_id="utility-production-failed-attempt",
                clock=lambda: FIXED,
            )
            self.assertEqual(result["status"], "failed")
            self.assertEqual((root / "latest-success.json").read_bytes(), success_before)
            self.assertEqual(
                json.loads((root / "latest-attempt.json").read_text())["run_id"],
                "utility-production-failed-attempt",
            )

    def test_systemd_provenance_is_captured_but_never_self_attested(self):
        provenance = production.execution_provenance({
            "INVOCATION_ID": "a" * 32,
            "FL_SIGNAL_UTILITY_EXECUTION_CONTEXT": "systemd_timer_expected",
            "FL_SIGNAL_UTILITY_SERVICE_UNIT": "florida-utility-intake.service",
            "FL_SIGNAL_UTILITY_TIMER_UNIT": "florida-utility-intake.timer",
        })
        self.assertEqual(provenance["systemd_invocation_id"], "a" * 32)
        self.assertEqual(provenance["expected_timer_unit"], "florida-utility-intake.timer")
        self.assertFalse(provenance["natural_schedule_verified"])
        self.assertIn("Correlate", provenance["verification_contract"])

    def test_sibling_import_failure_is_receipted_before_environment_or_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = [
                "--sqlite-path", str(root / "permits.sqlite"),
                "--writer-lock-path", str(root / ".writer.lock"),
                "--evidence-dir", str(root / "runs"),
                "--receipt-dir", str(root / "receipts"),
                "--latest-attempt-pointer", str(root / "latest-attempt.json"),
                "--latest-success-pointer", str(root / "latest-success.json"),
                "--run-id", "utility-startup-import-failure",
            ]
            with mock.patch.object(production, "SHADOW_IMPORT_ERROR", ImportError("missing")), \
                    mock.patch.object(production, "shadow", None), \
                    mock.patch.object(production, "ReadOnlySupabaseTransport") as transport, \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = production.main(args)
            self.assertEqual(code, 3)
            transport.assert_not_called()
            pointer = json.loads((root / "latest-attempt.json").read_text())
            receipt = json.loads(Path(pointer["receipt_path"]).read_text())
            self.assertEqual(receipt["startup_stage"], "startup_import")
            self.assertEqual(receipt["safety"]["remote_methods"], [])
            self.assertFalse((root / "latest-success.json").exists())

    def test_service_uses_one_source_transport_and_failure_alerting(self):
        service = (ROOT / "ops/droplet/florida-utility-intake.service").read_text()
        timer = (ROOT / "ops/droplet/florida-utility-intake.timer").read_text()
        environment = (ROOT / "ops/droplet/florida-utility-intake.env.example").read_text()
        wait_helper = (ROOT / "ops/droplet/florida-utility-intake-wait.sh").read_text()
        collector = PRODUCTION_PATH.read_text()
        self.assertIn("OnFailure=florida-healthreport.service", service)
        self.assertIn("florida-utility-intake-wait.sh", service)
        self.assertNotIn("ExecStartPre=", service)
        self.assertNotIn("fs_wait_for_units.sh", service)
        self.assertIn("EnvironmentFile=-/srv/grahamandgold/florida-signal/secrets/florida-utility-intake.env", service)
        self.assertIn("--credential-file /srv/grahamandgold/florida-signal/secrets/florida-utility-intake.env", service)
        self.assertIn("/utility-intake-releases/current/utility_intake_production.py", service)
        self.assertIn("--dependency-wait-command /srv/grahamandgold/florida-signal/utility-intake-releases/current/florida-utility-intake-wait.sh", service)
        self.assertIn("--latest-attempt-pointer /srv/grahamandgold/florida-signal/staging/data/utility-intake/latest-attempt.json", service)
        self.assertIn("--latest-success-pointer /srv/grahamandgold/florida-signal/staging/data/utility-intake/latest-success.json", service)
        self.assertIn("FL_SIGNAL_UTILITY_EXECUTION_CONTEXT=systemd_timer_expected", service)
        self.assertIn("FL_SIGNAL_UTILITY_TIMER_UNIT=florida-utility-intake.timer", service)
        self.assertNotIn("secrets/.env", service)
        variables = [line.split("=", 1)[0] for line in environment.splitlines() if line and not line.startswith("#")]
        self.assertEqual(variables, ["SUPABASE_URL", "SUPABASE_ANON_KEY"])
        self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY", service + environment)
        self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY", collector)
        self.assertNotIn("editorial_pipeline_health?", collector)
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            self.assertNotIn(f'method="{method}"', collector)
        self.assertIn("readonly max_wait_seconds=600", wait_helper)
        self.assertIn("florida-accela.service florida-sync.service", wait_helper)
        self.assertNotIn("credential", wait_helper.lower())
        self.assertNotIn("systemctl start", wait_helper)
        self.assertIn("utility_intake_production.py", service)
        self.assertNotIn("scrape_accela", service)
        self.assertIn("OnCalendar=*:27/30", timer)
        self.assertIn("Persistent=true", timer)

    def test_atomic_installer_stages_before_one_generation_switch_and_keeps_timer_off(self):
        installer = (ROOT / "ops/droplet/install_utility_intake.sh").read_text()
        manifest = (ROOT / "ops/droplet/utility-intake-install.sha256").read_text()
        self.assertIn("utility-intake-install.sha256", installer)
        self.assertIn("freeze_manifest", installer)
        self.assertIn("verify_staged_release_manifest", installer)
        self.assertIn(".source-manifest.sha256", installer)
        self.assertIn("I_APPROVE_EXACT_UTILITY_INTAKE_ATOMIC_INSTALL", installer)
        self.assertIn("utility_intake_production.SHADOW_IMPORT_ERROR is None", installer)
        self.assertIn("intentionally-absent.env", installer)
        self.assertIn('receipt["startup_stage"] == "credential_file"', installer)
        self.assertIn("timer_is_preinstall_safe", installer)
        self.assertIn("service_is_preinstall_safe", installer)
        self.assertIn("validate_staged_release", installer)
        self.assertIn("switch_release", installer)
        self.assertIn('replace_symlink "$final_dir" "$current_path"', installer)
        self.assertIn("os.replace", installer)
        self.assertIn("rollback_release_switch", installer)
        self.assertIn("timer_is_postswitch_safe", installer)
        self.assertLess(
            installer.index("if ! timer_is_preinstall_safe"),
            installer.index('stage_release "$repo_root" "$stage_dir"'),
        )
        self.assertLess(
            installer.index('validate_staged_release "$stage_dir" "$check_root"'),
            installer.index('switch_release "$stage_dir" "$final_dir"'),
        )
        self.assertNotIn("systemctl enable", installer)
        self.assertNotIn("systemctl start", installer)
        for line in manifest.splitlines():
            expected, relative = line.split("  ", 1)
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), expected)

    def test_frozen_manifest_rejects_source_mutation_before_staging(self):
        installer = ROOT / "ops/droplet/install_utility_intake.sh"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repository = root / "repository"
            droplet = repository / "ops/droplet"
            droplet.mkdir(parents=True)
            relative_names = (
                "utility_intake_production.py",
                "utility_intake_shadow.py",
                "florida-utility-intake-wait.sh",
                "florida-utility-intake.service",
                "florida-utility-intake.timer",
            )
            original = {}
            manifest_lines = []
            for name in relative_names:
                raw = f"reviewed:{name}\n".encode()
                original[name] = raw
                (droplet / name).write_bytes(raw)
                digest = hashlib.sha256(raw).hexdigest()
                manifest_lines.append(f"{digest}  ops/droplet/{name}\n")
            manifest = droplet / "utility-intake-install.sha256"
            manifest.write_text("".join(manifest_lines), encoding="ascii")
            rejected_stage = root / "rejected-stage"
            pinned_stage = root / "pinned-stage"
            result = subprocess.run(
                [
                    "/bin/bash", "-c",
                    r'''source "$1"
/usr/bin/install -d -m 0755 "$3"
freeze_manifest "$2/ops/droplet/utility-intake-install.sha256" \
  "$3/.source-manifest.sha256"
printf 'mutated-before-copy\n' >"$2/ops/droplet/utility_intake_production.py"
copy_release_files "$2" "$3"
if verify_staged_release_manifest "$3/.source-manifest.sha256" "$3"; then
  exit 91
fi
printf 'reviewed:utility_intake_production.py\n' \
  >"$2/ops/droplet/utility_intake_production.py"
/usr/bin/install -d -m 0755 "$4"
freeze_manifest "$2/ops/droplet/utility-intake-install.sha256" \
  "$4/.source-manifest.sha256"
copy_release_files "$2" "$4"
verify_staged_release_manifest "$4/.source-manifest.sha256" "$4"
printf 'mutated-after-copy\n' >"$2/ops/droplet/utility_intake_production.py"
verify_staged_release_manifest "$4/.source-manifest.sha256" "$4"''',
                    "manifest-pin-test", str(installer), str(repository),
                    str(rejected_stage), str(pinned_stage),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                (pinned_stage / "utility_intake_production.py").read_bytes(),
                original["utility_intake_production.py"],
            )

    def test_release_switch_late_failure_restores_one_complete_prior_generation(self):
        installer = ROOT / "ops/droplet/install_utility_intake.sh"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            releases = root / "releases"
            units = root / "units"
            old_release = releases / "old"
            stage = releases / ".stage-new"
            final = releases / "new"
            current = releases / "current"
            marker = root / "late-guard-ran"
            units.mkdir(parents=True)
            old_release.mkdir(parents=True)
            stage.mkdir()
            names = (
                "utility_intake_production.py",
                "utility_intake_shadow.py",
                "florida-utility-intake-wait.sh",
                "florida-utility-intake.service",
                "florida-utility-intake.timer",
            )
            for name in names:
                (old_release / name).write_text(f"old:{name}\n", encoding="utf-8")
                (stage / name).write_text(f"new:{name}\n", encoding="utf-8")
            current.symlink_to(old_release)
            (units / "florida-utility-intake.service").symlink_to(
                current / "florida-utility-intake.service"
            )
            (units / "florida-utility-intake.timer").symlink_to(
                current / "florida-utility-intake.timer"
            )
            env = os.environ.copy()
            env["TEST_LATE_GUARD_MARKER"] = str(marker)
            env["TEST_RELEASE_CURRENT"] = str(current)
            env["TEST_RELEASE_UNITS"] = str(units)
            result = subprocess.run(
                [
                    "/bin/bash", "-c",
                    r'''source "$1"
timer_is_preinstall_safe() { return 0; }
service_is_preinstall_safe() { return 0; }
systemd_active_state() { printf 'inactive\n'; }
systemd_enabled_state() { printf 'disabled\n'; }
reload_systemd() { return 0; }
restore_timer_state() { return 0; }
install_post_switch_guard() {
  [[ "$(/usr/bin/readlink "$TEST_RELEASE_CURRENT")" == "$1" ]] || return 2
  /usr/bin/cmp -s "$1/florida-utility-intake.service" \
    "$TEST_RELEASE_UNITS/florida-utility-intake.service" || return 2
  /usr/bin/cmp -s "$1/florida-utility-intake.timer" \
    "$TEST_RELEASE_UNITS/florida-utility-intake.timer" || return 2
  : >"$TEST_LATE_GUARD_MARKER"
  return 1
}
if switch_release "$2" "$3" "$4" "$5" "$6" "$7"; then
  exit 90
fi''',
                    "release-switch-test", str(installer), str(stage), str(final),
                    str(releases), str(current), str(units), str(root / "recovery"),
                ],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(marker.is_file())
            self.assertEqual(current.readlink(), old_release)
            self.assertEqual(
                (units / "florida-utility-intake.service").readlink(),
                current / "florida-utility-intake.service",
            )
            self.assertEqual(
                (units / "florida-utility-intake.timer").readlink(),
                current / "florida-utility-intake.timer",
            )
            self.assertEqual(
                (units / "florida-utility-intake.service").read_text(encoding="utf-8"),
                "old:florida-utility-intake.service\n",
            )
            self.assertEqual(
                (units / "florida-utility-intake.timer").read_text(encoding="utf-8"),
                "old:florida-utility-intake.timer\n",
            )
            self.assertFalse(stage.exists())
            self.assertTrue(final.is_dir())

    def test_release_switch_late_failure_on_first_install_leaves_no_runnable_unit(self):
        installer = ROOT / "ops/droplet/install_utility_intake.sh"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            releases = root / "releases"
            units = root / "units"
            stage = releases / ".stage-new"
            final = releases / "new"
            current = releases / "current"
            releases.mkdir()
            units.mkdir()
            stage.mkdir()
            for name in (
                "utility_intake_production.py",
                "utility_intake_shadow.py",
                "florida-utility-intake-wait.sh",
                "florida-utility-intake.service",
                "florida-utility-intake.timer",
            ):
                (stage / name).write_text(f"new:{name}\n", encoding="utf-8")
            result = subprocess.run(
                [
                    "/bin/bash", "-c",
                    r'''source "$1"
timer_is_preinstall_safe() { return 0; }
service_is_preinstall_safe() { return 0; }
systemd_active_state() { printf 'inactive\n'; }
systemd_enabled_state() { printf 'disabled\n'; }
reload_systemd() { return 0; }
restore_timer_state() { return 0; }
install_post_switch_guard() {
  [[ "$(/usr/bin/readlink "$TEST_RELEASE_CURRENT")" == "$1" ]] || return 2
  /usr/bin/cmp -s "$1/florida-utility-intake.service" \
    "$TEST_RELEASE_UNITS/florida-utility-intake.service" || return 2
  /usr/bin/cmp -s "$1/florida-utility-intake.timer" \
    "$TEST_RELEASE_UNITS/florida-utility-intake.timer" || return 2
  return 1
}
if switch_release "$2" "$3" "$4" "$5" "$6" "$7"; then
  exit 90
fi''',
                    "release-switch-test", str(installer), str(stage), str(final),
                    str(releases), str(current), str(units), str(root / "recovery"),
                ],
                env={
                    **os.environ,
                    "TEST_RELEASE_CURRENT": str(current),
                    "TEST_RELEASE_UNITS": str(units),
                },
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(current.exists())
            self.assertFalse(current.is_symlink())
            for name in ("florida-utility-intake.service", "florida-utility-intake.timer"):
                self.assertFalse((units / name).exists())
                self.assertFalse((units / name).is_symlink())
            self.assertTrue(final.is_dir())

    def test_each_restore_or_reload_failure_is_durable_and_preserves_backup(self):
        installer = ROOT / "ops/droplet/install_utility_intake.sh"
        for failure in ("current", "service", "timer", "daemon_reload"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                releases = root / "releases"
                units = root / "units"
                recovery = root / "recovery-required"
                old_release = releases / "old"
                stage = releases / ".stage-new"
                final = releases / "new"
                current = releases / "current"
                timer_safe_marker = root / "timer-safe"
                units.mkdir(parents=True)
                old_release.mkdir(parents=True)
                stage.mkdir()
                names = (
                    "utility_intake_production.py",
                    "utility_intake_shadow.py",
                    "florida-utility-intake-wait.sh",
                    "florida-utility-intake.service",
                    "florida-utility-intake.timer",
                )
                for name in names:
                    (old_release / name).write_text(f"old:{name}\n", encoding="utf-8")
                    (stage / name).write_text(f"new:{name}\n", encoding="utf-8")
                current.symlink_to(old_release)
                (units / "florida-utility-intake.service").write_text(
                    "old:florida-utility-intake.service\n", encoding="utf-8"
                )
                (units / "florida-utility-intake.timer").write_text(
                    "old:florida-utility-intake.timer\n", encoding="utf-8"
                )
                result = subprocess.run(
                    [
                        "/bin/bash", "-c",
                        r'''source "$1"
timer_is_preinstall_safe() { return 0; }
service_is_preinstall_safe() { return 0; }
systemd_active_state() { printf 'inactive\n'; }
systemd_enabled_state() { printf 'disabled\n'; }
eval "$(declare -f restore_path | /usr/bin/sed '1s/restore_path/original_restore_path/')"
restore_path() {
  if [[ "$3" == "$FAIL_POINT" ]]; then
    return 71
  fi
  original_restore_path "$@"
}
reload_systemd() {
  [[ "$FAIL_POINT" != "daemon_reload" ]]
}
restore_timer_state() {
  : >"$TIMER_SAFE_MARKER"
  return 0
}
install_post_switch_guard() { return 1; }
if switch_release "$2" "$3" "$4" "$5" "$6" "$7"; then
  exit 90
fi
[[ -f "$TIMER_SAFE_MARKER" ]]''',
                        "rollback-injection-test", str(installer), str(stage),
                        str(final), str(releases), str(current), str(units),
                        str(recovery),
                    ],
                    env={
                        **os.environ,
                        "FAIL_POINT": failure,
                        "TIMER_SAFE_MARKER": str(timer_safe_marker),
                    },
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                evidence_files = list(recovery.glob("recovery-required-*.json"))
                self.assertEqual(len(evidence_files), 1)
                evidence = json.loads(evidence_files[0].read_text(encoding="utf-8"))
                self.assertEqual(evidence["status"], "recovery_required")
                expected_failure = (
                    "daemon_reload" if failure == "daemon_reload" else f"restore_{failure}"
                )
                self.assertIn(expected_failure, evidence["failures"])
                self.assertEqual(evidence["timer_active"], "inactive")
                self.assertEqual(evidence["timer_enabled"], "disabled")
                backup_dirs = list(releases.glob(".rollback.*"))
                self.assertEqual(len(backup_dirs), 1)
                self.assertTrue((backup_dirs[0] / "current.present").is_file())
                self.assertTrue(timer_safe_marker.is_file())


if __name__ == "__main__":
    unittest.main()
