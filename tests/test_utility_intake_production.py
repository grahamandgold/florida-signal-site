from __future__ import annotations

import base64
import datetime as dt
import hashlib
import importlib.util
import io
import json
import sqlite3
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
            latest_pointer=root / "latest.json",
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
            pointer = json.loads((root / "latest.json").read_text())
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
            self.assertEqual((root / "latest.json").stat().st_mode & 0o777, 0o600)

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
                        latest_pointer=root / "latest.json",
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
            with mock.patch.object(production.os, "fsync", side_effect=[None, OSError("directory fsync")]):
                with self.assertRaisesRegex(OSError, "directory fsync"):
                    production.run_production(
                        sqlite_path=root / "permits.sqlite",
                        writer_lock_path=lock,
                        evidence_dir=root / "runs",
                        receipt_dir=root / "receipts",
                        latest_pointer=root / "latest.json",
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
                    latest_pointer=root / "latest.json",
                    run_id="utility-config-symlink-proof",
                    error=ValueError("missing config"),
                    clock=lambda: FIXED,
                )
            self.assertEqual(list(target.iterdir()), [])
            self.assertFalse((root / "latest.json").exists())

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
                "--latest-pointer", str(root / "latest.json"),
                "--run-id", "utility-config-failure",
            ]
            with mock.patch.object(
                production, "ReadOnlySupabaseTransport", side_effect=ValueError(secret_marker),
            ), redirect_stdout(stdout), redirect_stderr(stderr):
                code = production.main(args)
            self.assertEqual(code, 3)
            pointer = json.loads((root / "latest.json").read_text())
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
                    latest_pointer=root / "latest.json",
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
            pointer = json.loads((root / "latest.json").read_text())
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
                "--latest-pointer", str(root / "latest.json"),
                "--run-id", "utility-missing-scoped-config",
            ]
            with mock.patch.dict(
                production.os.environ, {}, clear=True,
            ), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = production.main(args)
            self.assertEqual(code, 3)
            receipt = json.loads(Path(json.loads((root / "latest.json").read_text())["receipt_path"]).read_text())
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
                "--latest-pointer", str(root / "latest.json"),
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
            receipt = json.loads(Path(json.loads((root / "latest.json").read_text())["receipt_path"]).read_text())
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
                "--latest-pointer", str(root / "latest.json"),
                "--credential-file", str(root / "missing.env"),
                "--run-id", "utility-missing-credential-file",
            ]
            with mock.patch.dict(
                production.os.environ, {}, clear=True,
            ), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = production.main(args)
            self.assertEqual(code, 3)
            pointer = json.loads((root / "latest.json").read_text())
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
                latest_pointer=root / "latest.json",
                transport=transport,
                run_id="utility-production-empty",
                clock=lambda: FIXED,
            )
            self.assertEqual(result["status"], "failed")
            receipt = json.loads(Path(result["receipt_path"]).read_text())
            self.assertEqual(receipt["health"]["status"], "error")
            self.assertIn("shadow evidence is not admissible: empty", receipt["reason_detail"])

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
        self.assertIn("--dependency-wait-command /srv/grahamandgold/florida-signal/tools/florida-utility-intake-wait.sh", service)
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


if __name__ == "__main__":
    unittest.main()
