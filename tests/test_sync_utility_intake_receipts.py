from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops/mac/sync_utility_intake_receipts.py"
SPEC = importlib.util.spec_from_file_location("sync_utility_intake_receipts", SCRIPT)
syncer = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(syncer)


class UtilityReceiptSyncTests(unittest.TestCase):
    @staticmethod
    def _write_json(path: Path, value):
        raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
        path.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def _remote_fixture(self, root: Path):
        remote = root / "remote" / "utility-intake"
        receipts = remote / "receipts"
        receipts.mkdir(parents=True)
        counts = {
            "records_attempted": 2,
            "records_written": 0,
            "records_rejected": 0,
            "sqlite_records": 2,
            "supabase_records": 2,
        }
        execution = {
            "execution_context": "systemd_timer_expected",
            "systemd_invocation_id": "a" * 32,
            "service_unit": "florida-utility-intake.service",
            "expected_timer_unit": "florida-utility-intake.timer",
            "natural_schedule_verified": False,
            "verification_contract": "correlate journal",
        }
        verification_name = "utility-natural.verification.json"
        verification = {
            "schema_version": syncer.VERIFICATION_SCHEMA,
            "run_id": "utility-natural",
            "status": "verified",
            "completed_at": "2026-09-01T02:27:00Z",
            "counts": counts,
            "parity": {"status": "passed"},
            "execution": execution,
        }
        verification_sha = self._write_json(receipts / verification_name, verification)
        outcome_name = "utility-natural.json"
        outcome = {
            "schema_version": syncer.RECEIPT_SCHEMA,
            "run_id": "utility-natural",
            "status": "ok",
            "completed_at": "2026-09-01T02:27:00Z",
            "counts": counts,
            "parity": verification["parity"],
            "verification": {
                "receipt_path": str(receipts / verification_name),
                "receipt_sha256": verification_sha,
            },
            "health": {"component": "utility-intake", "status": "current"},
            "execution": execution,
        }
        outcome_sha = self._write_json(receipts / outcome_name, outcome)
        pointer = {
            "schema_version": syncer.LATEST_SCHEMA,
            "pointer_kind": "attempt",
            "run_id": "utility-natural",
            "status": "ok",
            "updated_at": "2026-09-01T02:27:00Z",
            "receipt_path": str(receipts / outcome_name),
            "receipt_sha256": outcome_sha,
            "counts": counts,
            "execution": execution,
        }
        self._write_json(remote / "latest-attempt.json", pointer)
        self._write_json(remote / "latest-success.json", {**pointer, "pointer_kind": "success"})
        return remote

    def test_stable_hash_bound_chain_is_atomically_placed_for_localhost(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = self._remote_fixture(root)
            destination = root / "local" / "utility-intake"
            fake_scp = root / "scp"
            fake_scp.write_text("#!/bin/sh\n", encoding="utf-8")
            fake_scp.chmod(0o755)
            calls = []

            def copy(command, **_kwargs):
                calls.append(command)
                source = Path(command[-2].split(":", 1)[1])
                shutil.copyfile(source, Path(command[-1]))
                return subprocess.CompletedProcess(command, 0)

            with mock.patch.object(syncer, "REMOTE_ROOT", remote), \
                    mock.patch.object(syncer, "REMOTE_RECEIPTS", remote / "receipts"), \
                    mock.patch.object(syncer.subprocess, "run", side_effect=copy):
                result = syncer.sync_receipts(
                    destination=destination, host="florida", scp=fake_scp,
                )
            self.assertEqual(result["status"], "synced")
            self.assertEqual(result["latest_attempt_run_id"], "utility-natural")
            self.assertEqual(result["latest_success_run_id"], "utility-natural")
            self.assertEqual(len(calls), 6)  # two pointers, outcome, verification, two pointers
            self.assertTrue(all(command[0] == str(fake_scp) for command in calls))
            self.assertTrue(all("BatchMode=yes" in command for command in calls))
            self.assertEqual((destination / "latest-attempt.json").stat().st_mode & 0o777, 0o600)
            self.assertEqual((destination / "receipts/utility-natural.json").stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                (destination / "receipts/utility-natural.verification.json").read_bytes(),
                (remote / "receipts/utility-natural.verification.json").read_bytes(),
            )

    def test_outcome_hash_mismatch_preserves_existing_local_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = self._remote_fixture(root)
            destination = root / "local" / "utility-intake"
            destination.mkdir(parents=True)
            existing = destination / "latest-attempt.json"
            existing.write_text("preserve me\n", encoding="utf-8")
            (remote / "receipts/utility-natural.json").write_text("{}\n", encoding="utf-8")
            fake_scp = root / "scp"
            fake_scp.write_text("#!/bin/sh\n", encoding="utf-8")
            fake_scp.chmod(0o755)

            def copy(command, **_kwargs):
                shutil.copyfile(Path(command[-2].split(":", 1)[1]), Path(command[-1]))
                return subprocess.CompletedProcess(command, 0)

            with mock.patch.object(syncer, "REMOTE_ROOT", remote), \
                    mock.patch.object(syncer, "REMOTE_RECEIPTS", remote / "receipts"), \
                    mock.patch.object(syncer.subprocess, "run", side_effect=copy):
                with self.assertRaisesRegex(syncer.SyncError, "hash mismatch"):
                    syncer.sync_receipts(
                        destination=destination, host="florida", scp=fake_scp,
                    )
            self.assertEqual(existing.read_text(), "preserve me\n")

    def test_remote_path_escape_and_unsafe_host_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_scp = root / "scp"
            fake_scp.write_text("#!/bin/sh\n", encoding="utf-8")
            fake_scp.chmod(0o755)
            with self.assertRaisesRegex(syncer.SyncError, "SSH alias"):
                syncer.sync_receipts(
                    destination=root / "local", host="florida;touch-x", scp=fake_scp,
                )
            with self.assertRaisesRegex(syncer.SyncError, "producer directory"):
                syncer._remote_receipt_name("/tmp/escape.json")


if __name__ == "__main__":
    unittest.main()
