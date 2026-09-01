import datetime as dt
import importlib.util
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
import uuid
import urllib.error
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


production = load("sfwmd_operations_production", "ops/droplet/sfwmd_pending_erp_production.py")
alert = load("sfwmd_operations_alert", "ops/droplet/sfwmd_pending_erp_alert.py")
backup = load("sfwmd_operations_backup", "ops/droplet/sfwmd_pending_erp_backup.py")
FIXED_CLOCK = dt.datetime(2026, 8, 31, 10, 20, tzinfo=dt.timezone.utc)


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def getcode(self):
        return self.status

    def read(self, _maximum):
        return b"ok"


class SfwmdOperationsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def failure_pointer(self):
        failure_dir = self.root / "failures"
        production.write_early_failure(
            failure_ledger_dir=failure_dir,
            run_id=str(uuid.uuid4()),
            stage="canonical_commit",
            started_at=production.shadow.iso_utc(FIXED_CLOCK),
            error=production.ProductionError("safe test failure"),
            provenance=production.manual_provenance("manual_service"),
            evidence_bundle_path=None,
            canonical_receipt_committed=False,
            failed_unit=production.MANUAL_SERVICE_UNIT,
            clock=lambda: FIXED_CLOCK,
        )
        return failure_dir

    def test_alert_is_default_off_and_enabled_route_is_bounded_and_receipted(self):
        failure_dir = self.failure_pointer()
        receipts = self.root / "alerts"
        with mock.patch.dict(os.environ, {"FLORIDA_SIGNAL_SFWMD_ALERT_ENABLED": "0"}):
            disabled = alert.deliver_alert(
                failed_unit="florida-sfwmd-pending-erp.service",
                failure_ledger_dir=failure_dir,
                alert_receipt_dir=receipts,
            )
        self.assertEqual(disabled["status"], "disabled")
        self.assertFalse(receipts.exists())
        with mock.patch.dict(os.environ, {"FLORIDA_SIGNAL_SFWMD_ALERT_ENABLED": "0"}):
            inert = alert.deliver_alert(
                failed_unit=production.MANUAL_SERVICE_UNIT,
                failure_ledger_dir=self.root / "does-not-exist",
                alert_receipt_dir=self.root / "also-does-not-exist",
            )
        self.assertEqual(inert["status"], "disabled")

        opener = mock.Mock(return_value=FakeResponse())
        secret_url = "https://hooks.slack.com/services/SECRET/SECRET/SECRET"
        with mock.patch.dict(os.environ, {
            "FLORIDA_SIGNAL_SFWMD_ALERT_ENABLED": "1",
            "FLORIDA_SIGNAL_SFWMD_ALERT_WEBHOOK_URL": secret_url,
        }):
            delivered = alert.deliver_alert(
                failed_unit="florida-sfwmd-pending-erp.service",
                failure_ledger_dir=failure_dir,
                alert_receipt_dir=receipts,
                opener=opener,
                clock=lambda: FIXED_CLOCK,
            )
        self.assertTrue(delivered["delivered"])
        persisted = Path(delivered["receipt_path"]).read_text()
        self.assertNotIn(secret_url, persisted)
        self.assertIn('"endpoint_host":"hooks.slack.com"', persisted)
        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, secret_url)
        self.assertLessEqual(len(request.data), 2_000)
        with mock.patch.dict(os.environ, {
            "FLORIDA_SIGNAL_SFWMD_ALERT_ENABLED": "1",
            "FLORIDA_SIGNAL_SFWMD_ALERT_WEBHOOK_URL": secret_url,
        }):
            replay = alert.deliver_alert(
                failed_unit="florida-sfwmd-pending-erp.service",
                failure_ledger_dir=failure_dir,
                alert_receipt_dir=receipts,
                opener=opener,
                clock=lambda: FIXED_CLOCK,
            )
        self.assertEqual(replay["status"], "already_delivered")
        self.assertEqual(opener.call_count, 1)

    def test_alert_rejects_stale_contract_tampering_and_non_slack_endpoint(self):
        failure_dir = self.failure_pointer()
        pointer = json.loads((failure_dir / "latest.json").read_text())
        receipt_path = Path(pointer["receipt_path"])
        receipt = json.loads(receipt_path.read_text())
        receipt["stage"] = "tampered"
        receipt_path.write_text(json.dumps(receipt))
        with mock.patch.dict(os.environ, {"FLORIDA_SIGNAL_SFWMD_ALERT_ENABLED": "1"}):
            with self.assertRaises(alert.AlertError):
                alert.deliver_alert(
                    failed_unit="florida-sfwmd-pending-erp.service",
                    failure_ledger_dir=failure_dir,
                    alert_receipt_dir=self.root / "alerts",
                )

        failure_dir = self.root / "fresh-failures"
        production.write_early_failure(
            failure_ledger_dir=failure_dir,
            run_id=str(uuid.uuid4()),
            stage="canonical_commit",
            started_at=production.shadow.iso_utc(FIXED_CLOCK),
            error=production.ProductionError("safe test failure"),
            provenance=production.manual_provenance("manual_service"),
            evidence_bundle_path=None,
            canonical_receipt_committed=False,
            failed_unit=production.MANUAL_SERVICE_UNIT,
            clock=lambda: FIXED_CLOCK,
        )
        with mock.patch.dict(os.environ, {
            "FLORIDA_SIGNAL_SFWMD_ALERT_ENABLED": "1",
            "FLORIDA_SIGNAL_SFWMD_ALERT_WEBHOOK_URL": "https://example.com/hook",
        }):
            with self.assertRaisesRegex(alert.AlertError, "Slack HTTPS"):
                alert.deliver_alert(
                    failed_unit="florida-sfwmd-pending-erp.service",
                    failure_ledger_dir=failure_dir,
                    alert_receipt_dir=self.root / "alerts",
                )

    def test_alert_transport_ambiguity_is_durable_and_never_double_posts(self):
        failure_dir = self.failure_pointer()
        receipts = self.root / "ambiguous-alerts"
        environment = {
            "FLORIDA_SIGNAL_SFWMD_ALERT_ENABLED": "1",
            "FLORIDA_SIGNAL_SFWMD_ALERT_WEBHOOK_URL": (
                "https://hooks.slack.com/services/SECRET/SECRET/SECRET"
            ),
        }
        first_opener = mock.Mock(side_effect=urllib.error.URLError("ambiguous timeout"))
        with mock.patch.dict(os.environ, environment):
            with self.assertRaisesRegex(alert.AlertError, "delivery failed"):
                alert.deliver_alert(
                    failed_unit=production.MANUAL_SERVICE_UNIT,
                    failure_ledger_dir=failure_dir,
                    alert_receipt_dir=receipts,
                    opener=first_opener,
                    clock=lambda: FIXED_CLOCK,
                )
            retry_opener = mock.Mock(return_value=FakeResponse())
            retry = alert.deliver_alert(
                failed_unit=production.MANUAL_SERVICE_UNIT,
                failure_ledger_dir=failure_dir,
                alert_receipt_dir=receipts,
                opener=retry_opener,
                clock=lambda: FIXED_CLOCK,
            )
        self.assertEqual(retry["status"], "indeterminate")
        self.assertFalse(retry["delivered"])
        retry_opener.assert_not_called()
        self.assertEqual(len(list(receipts.glob("*.claim.json"))), 1)
        self.assertEqual(list(receipts.glob("*.alert.json")), [])

    def test_failure_pointer_is_monotonic_and_alert_queue_is_run_correlated(self):
        failure_dir = self.root / "queued-failures"
        newer_clock = FIXED_CLOCK + dt.timedelta(minutes=2)
        older_clock = FIXED_CLOCK + dt.timedelta(minutes=1)

        def write_failure(instant):
            return production.write_early_failure(
                failure_ledger_dir=failure_dir,
                run_id=str(uuid.uuid4()),
                stage="canonical_commit",
                started_at=production.shadow.iso_utc(instant),
                error=production.ProductionError("safe queued failure"),
                provenance=production.manual_provenance("manual_service"),
                evidence_bundle_path=None,
                canonical_receipt_committed=False,
                failed_unit=production.MANUAL_SERVICE_UNIT,
                clock=lambda: instant,
            )

        newer = write_failure(newer_clock)
        older = write_failure(older_clock)
        pointer = json.loads((failure_dir / "latest.json").read_text())
        unit_pointer = json.loads(
            (failure_dir / f"{production.MANUAL_SERVICE_UNIT}.latest.json").read_text()
        )
        self.assertEqual(pointer["run_id"], newer["run_id"])
        self.assertEqual(unit_pointer["run_id"], newer["run_id"])

        opener = mock.Mock(return_value=FakeResponse())
        environment = {
            "FLORIDA_SIGNAL_SFWMD_ALERT_ENABLED": "1",
            "FLORIDA_SIGNAL_SFWMD_ALERT_WEBHOOK_URL": (
                "https://hooks.slack.com/services/SECRET/SECRET/SECRET"
            ),
        }
        delivered_ids = []
        with mock.patch.dict(os.environ, environment):
            for _ in range(2):
                delivered = alert.deliver_alert(
                    failed_unit=production.MANUAL_SERVICE_UNIT,
                    failure_ledger_dir=failure_dir,
                    alert_receipt_dir=self.root / "queued-alerts",
                    opener=opener,
                    clock=lambda: newer_clock,
                )
                delivered_ids.append(delivered["run_id"])
            replay = alert.deliver_alert(
                failed_unit=production.MANUAL_SERVICE_UNIT,
                failure_ledger_dir=failure_dir,
                alert_receipt_dir=self.root / "queued-alerts",
                opener=opener,
                clock=lambda: newer_clock,
            )
        self.assertEqual(delivered_ids, [newer["run_id"], older["run_id"]])
        self.assertEqual(replay["status"], "already_delivered")
        self.assertEqual(opener.call_count, 2)

    def test_fractional_second_failure_advances_after_exact_second(self):
        failure_dir = self.root / "fractional-failures"

        def write_failure(instant):
            return production.write_early_failure(
                failure_ledger_dir=failure_dir,
                run_id=str(uuid.uuid4()),
                stage="canonical_commit",
                started_at=production.shadow.iso_utc(instant),
                error=production.ProductionError("safe fractional failure"),
                provenance=production.manual_provenance("manual_service"),
                evidence_bundle_path=None,
                canonical_receipt_committed=False,
                failed_unit=production.MANUAL_SERVICE_UNIT,
                clock=lambda: instant,
            )

        exact = write_failure(FIXED_CLOCK)
        later = write_failure(FIXED_CLOCK + dt.timedelta(microseconds=500_000))
        pointer = json.loads((failure_dir / "latest.json").read_text())
        self.assertIn(".000000Z|", exact["failure_order_key"])
        self.assertIn(".500000Z|", later["failure_order_key"])
        self.assertEqual(pointer["run_id"], later["run_id"])

    def test_backup_manifest_rejects_symlinks_and_verifies_exact_restored_bytes(self):
        source = self.root / "source"
        source.mkdir()
        (source / "evidence.json").write_text("official evidence")
        manifest = backup.build_manifest({"evidence": source}, "2026-08-31T10:20:00Z")
        restore = self.root / "restore"
        destination = restore / source.as_posix().lstrip("/")
        destination.mkdir(parents=True)
        shutil.copy2(source / "evidence.json", destination / "evidence.json")
        verified = backup.verify_restored_manifest(manifest, restore)
        self.assertEqual(verified["verified_files"], 1)
        unexpected = restore / "outside-declared-roots.json"
        unexpected.write_text("not declared")
        with self.assertRaisesRegex(backup.BackupError, "outside its exact manifest"):
            backup.verify_restored_manifest(manifest, restore)
        unexpected.unlink()
        (destination / "evidence.json").write_text("mutated")
        with self.assertRaisesRegex(backup.BackupError, "byte/hash"):
            backup.verify_restored_manifest(manifest, restore)

        link = source / "link"
        link.symlink_to(source / "evidence.json")
        with self.assertRaisesRegex(backup.BackupError, "symlink"):
            backup.build_manifest({"evidence": source}, "2026-08-31T10:20:00Z")

        link.unlink()
        (source / "injected\noutside").write_text("unsafe delimiter")
        with self.assertRaisesRegex(backup.BackupError, "forbidden path delimiter"):
            backup.build_manifest({"evidence": source}, "2026-08-31T10:20:00Z")

    def test_offsite_backup_restores_and_verifies_before_receipting(self):
        database = self.root / "canonical.sqlite"
        with sqlite3.connect(database) as connection:
            connection.execute("create table evidence (value text)")
            connection.execute("insert into evidence values ('durable')")
        directories = {}
        for label in (
            "evidence", "receipts", "alert_receipts", "failures", "provenance",
            "backup_receipts",
        ):
            directories[label] = self.root / label
            directories[label].mkdir()
            if label != "backup_receipts":
                (directories[label] / f"{label}.json").write_text(label)
        restic = self.root / "restic"
        restic.write_text("reviewed binary placeholder")
        restic.chmod(0o500)
        password = self.root / "restic-password"
        password.write_text("secret")
        password.chmod(0o600)
        captured_sources = []
        captured_environments = []

        def runner(command, runner_environment):
            nonlocal captured_sources
            captured_environments.append(dict(runner_environment))
            if command[1] == "backup":
                self.assertIn("--files-from-raw", command)
                paths_file = Path(command[command.index("--files-from-raw") + 1])
                captured_sources = [
                    Path(value.decode("utf-8"))
                    for value in paths_file.read_bytes().split(b"\x00") if value
                ]
                return b'{"message_type":"summary","snapshot_id":"abcdef1234567890"}\n'
            target = Path(command[command.index("--target") + 1])
            for source in captured_sources:
                destination = target / source.as_posix().lstrip("/")
                destination.parent.mkdir(parents=True, exist_ok=True)
                if source.is_dir():
                    shutil.copytree(source, destination)
                else:
                    shutil.copy2(source, destination)
            return b""

        environment = {
            "FLORIDA_SIGNAL_SFWMD_BACKUP_ENABLED": "1",
            "RESTIC_REPOSITORY": "s3:https://offsite.example.test/bucket/florida-signal",
            "RESTIC_PASSWORD_FILE": str(password),
            "AWS_ACCESS_KEY_ID": "process-only",
            "AWS_SECRET_ACCESS_KEY": "process-only-secret",
            "FLORIDA_SIGNAL_SFWMD_ALERT_WEBHOOK_URL": "must-not-reach-restic",
            "SUPABASE_SERVICE_ROLE_KEY": "must-not-reach-restic",
        }
        with mock.patch.dict(os.environ, environment, clear=False):
            result = backup.backup_and_verify(
                sqlite_path=database,
                writer_lock_path=self.root / "writer.lock",
                evidence_dir=directories["evidence"],
                receipt_dir=directories["receipts"],
                alert_receipt_dir=directories["alert_receipts"],
                failure_dir=directories["failures"],
                provenance_dir=directories["provenance"],
                backup_receipt_dir=directories["backup_receipts"],
                restic_bin=restic,
                runner=runner,
                clock=lambda: FIXED_CLOCK,
            )
        self.assertTrue(result["verified"])
        receipt_body = Path(result["receipt_path"]).read_text()
        receipt = json.loads(receipt_body)
        self.assertTrue(receipt["restore_verified"])
        self.assertEqual(receipt["file_count"], receipt["verified_files"])
        self.assertNotIn("process-only", receipt_body)
        self.assertNotIn(str(password), receipt_body)
        self.assertEqual(len(captured_environments), 2)
        for runner_environment in captured_environments:
            self.assertEqual(set(runner_environment), {
                "RESTIC_REPOSITORY", "RESTIC_PASSWORD_FILE", "AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY",
            })
            self.assertNotIn("FLORIDA_SIGNAL_SFWMD_ALERT_WEBHOOK_URL", runner_environment)
            self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY", runner_environment)

    def test_backup_gate_is_inert_before_path_or_secret_access(self):
        with mock.patch.dict(os.environ, {"FLORIDA_SIGNAL_SFWMD_BACKUP_ENABLED": "0"}):
            result = backup.backup_and_verify(
                sqlite_path=Path("relative-and-missing"),
                writer_lock_path=Path("relative-and-missing"),
                evidence_dir=Path("relative-and-missing"),
                receipt_dir=Path("relative-and-missing"),
                alert_receipt_dir=Path("relative-and-missing"),
                failure_dir=Path("relative-and-missing"),
                provenance_dir=Path("relative-and-missing"),
                backup_receipt_dir=Path("relative-and-missing"),
            )
        self.assertEqual(result, {"status": "disabled", "verified": False})


if __name__ == "__main__":
    unittest.main()
