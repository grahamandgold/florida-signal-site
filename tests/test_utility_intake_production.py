from __future__ import annotations

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
        *,
        fail_health: bool = False,
        normalized_system_time: bool = False,
    ) -> None:
        self.remote_rows = remote_rows
        self.fail_health = fail_health
        self.normalized_system_time = normalized_system_time
        self.health: dict[str, object] | None = None
        self.calls: list[tuple[str, str]] = []

    def request_json(self, method, path, *, body=None, prefer=None):
        self.calls.append((method, path))
        if path.startswith("permits?"):
            query = parse_qs(urlparse(path).query)
            offset = int(query.get("offset", ["0"])[0])
            limit = int(query.get("limit", ["1000"])[0])
            return self.remote_rows[offset : offset + limit]
        if path.startswith("editorial_pipeline_health?"):
            if self.fail_health:
                raise production.ProductionError("simulated health failure")
            self.health = dict(body[0])
            returned = dict(body[0])
            if self.normalized_system_time:
                returned["system_time"] = returned["system_time"].replace("Z", "+00:00")
            return [returned]
        raise AssertionError(path)


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
            self.assertEqual(transport.health["metrics"]["remote_stability_reads"], 2)
            self.assertTrue(receipt["health"]["published"])
            self.assertEqual(transport.health["status"], "current")
            self.assertEqual(transport.health["event_through"], "2026-08-31")
            verification = receipt["verification"]
            self.assertTrue(Path(verification["receipt_path"]).is_file())
            self.assertEqual(
                hashlib.sha256(Path(verification["receipt_path"]).read_bytes()).hexdigest(),
                verification["receipt_sha256"],
            )
            self.assertEqual(
                transport.health["metrics"]["verification_receipt_sha256"],
                verification["receipt_sha256"],
            )
            self.assertEqual(Path(pointer["receipt_path"]).stat().st_mode & 0o777, 0o600)
            self.assertEqual((root / "latest.json").stat().st_mode & 0o777, 0o600)

    def test_postgres_timestamp_rendering_is_compared_as_an_instant(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = fixture(root / "remote.sqlite")
            (root / "remote.sqlite").unlink()
            transport = FakeTransport(remote, normalized_system_time=True)
            _, result = self.run_case(root, transport)
            self.assertEqual(result["status"], "ok")

    def test_health_failure_retains_verified_evidence_and_terminal_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = fixture(root / "remote.sqlite")
            (root / "remote.sqlite").unlink()
            transport = FakeTransport(remote, fail_health=True)
            _, result = self.run_case(root, transport)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["exit_code"], 1)
            receipt = json.loads(Path(result["receipt_path"]).read_text())
            self.assertEqual(receipt["reason_code"], "UTILITY_INTAKE_HEALTH_PUBLICATION_FAILED")
            self.assertFalse(receipt["health"]["published"])
            verification_path = Path(receipt["verification"]["receipt_path"])
            verification = json.loads(verification_path.read_text())
            self.assertEqual(verification["status"], "verified")
            self.assertEqual(
                hashlib.sha256(verification_path.read_bytes()).hexdigest(),
                receipt["verification"]["receipt_sha256"],
            )

    def test_row_drift_fails_closed_and_publishes_error(self):
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
            self.assertEqual(transport.health["status"], "error")

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
        offsets = [
            int(parse_qs(urlparse(path).query)["offset"][0])
            for method, path in transport.calls if path.startswith("permits?")
        ]
        self.assertEqual(offsets, [0, 2, 3, 0, 2, 3])

    def test_remote_projection_change_between_complete_reads_fails_closed(self):
        remote = [
            {column: ("ENG-CR-26010001" if column == "permit_number" else None)
             for column in production.PARITY_COLUMNS}
        ]

        class ChangingTransport(FakeTransport):
            def request_json(self, method, path, *, body=None, prefer=None):
                permit_calls = sum(1 for _, prior in self.calls if prior.startswith("permits?"))
                if path.startswith("permits?") and permit_calls >= 2:
                    self.remote_rows[0]["status"] = "changed during proof"
                return super().request_json(method, path, body=body, prefer=prefer)

        with self.assertRaisesRegex(production.ProductionError, "changed across stability reads"):
            production._remote_projection(ChangingTransport(remote))

    def test_receipt_file_fsync_failure_prevents_health_publication_and_removes_partial(self):
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
            self.assertFalse(any(path.startswith("editorial_pipeline_health?") for _, path in transport.calls))
            self.assertFalse((root / "receipts" / "utility-production-fsync-file.verification.json").exists())

    def test_receipt_directory_fsync_failure_prevents_health_publication(self):
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
            self.assertFalse(any(path.startswith("editorial_pipeline_health?") for _, path in transport.calls))

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
                production, "SupabaseTransport", side_effect=ValueError(secret_marker),
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
            self.assertEqual(transport.health["status"], "error")
            receipt = json.loads(Path(result["receipt_path"]).read_text())
            self.assertIn("shadow evidence is not admissible: empty", receipt["reason_detail"])

    def test_service_uses_one_source_transport_and_failure_alerting(self):
        service = (ROOT / "ops/droplet/florida-utility-intake.service").read_text()
        timer = (ROOT / "ops/droplet/florida-utility-intake.timer").read_text()
        environment = (ROOT / "ops/droplet/florida-utility-intake.env.example").read_text()
        wait_helper = (ROOT / "ops/droplet/florida-utility-intake-wait.sh").read_text()
        self.assertIn("OnFailure=florida-healthreport.service", service)
        self.assertIn("florida-utility-intake-wait.sh", service)
        self.assertNotIn("fs_wait_for_units.sh", service)
        self.assertIn("secrets/florida-utility-intake.env", service)
        self.assertNotIn("secrets/.env", service)
        variables = [line.split("=", 1)[0] for line in environment.splitlines() if line and not line.startswith("#")]
        self.assertEqual(variables, ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"])
        self.assertIn("readonly max_wait_seconds=600", wait_helper)
        self.assertIn("florida-accela.service florida-sync.service", wait_helper)
        self.assertIn('credential_mode" != "600"', wait_helper)
        self.assertIn('credential_owner" != "root:root"', wait_helper)
        self.assertNotIn("systemctl start", wait_helper)
        self.assertIn("utility_intake_production.py", service)
        self.assertNotIn("scrape_accela", service)
        self.assertIn("OnCalendar=*:27/30", timer)
        self.assertIn("Persistent=true", timer)


if __name__ == "__main__":
    unittest.main()
