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

    @staticmethod
    def _known_hosts(root: Path) -> Path:
        path = root / "known_hosts"
        path.write_text("florida ssh-ed25519 AAAAC3Nza-test-only\n", encoding="utf-8")
        path.chmod(0o600)
        return path

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
            "versions": {"collector": "utility/1", "query": "q/1", "parser": "p/1"},
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

    def _add_natural_fixture(self, remote: Path):
        success = json.loads((remote / "latest-success.json").read_text(encoding="utf-8"))
        outcome = json.loads(
            (remote / "receipts" / Path(success["receipt_path"]).name).read_text(encoding="utf-8")
        )
        schedule = {
            "timer_unit": syncer.TIMER_UNIT,
            "service_unit": syncer.SERVICE_UNIT,
            "timer_active": True,
            "timer_enabled": True,
            "timer_target": syncer.SERVICE_UNIT,
            "timer_last_trigger": "Mon 2026-09-01 02:26:00 UTC",
            "timer_last_trigger_realtime_usec": 100,
            "timer_last_trigger_monotonic": "123456",
            "timer_next_elapse": "Mon 2026-09-01 02:57:00 UTC",
            "trigger_realtime_usec": 100,
            "outcome_started_realtime_usec": 103,
            "trigger_to_outcome_start_usec": 3,
            "service_journal_first_realtime_usec": 101,
            "service_journal_last_realtime_usec": 104,
        }
        attestation_name = "utility-natural.natural.json"
        attestation = {
            "schema_version": syncer.NATURAL_SCHEMA,
            "status": "verified",
            "run_id": success["run_id"],
            "verified_at": "2026-09-01T02:30:00Z",
            "outcome": {
                "receipt_path": success["receipt_path"],
                "receipt_sha256": success["receipt_sha256"],
                "completed_at": success["updated_at"],
                "counts": success["counts"],
                "versions": outcome["versions"],
            },
            "verification": outcome["verification"],
            "execution": success["execution"],
            "schedule": schedule,
            "evidence": {
                "latest_attempt_sha256": "1" * 64,
                "latest_success_sha256": "2" * 64,
                "timer_show_sha256": "3" * 64,
                "timer_journal_sha256": "4" * 64,
                "service_journal_sha256": "5" * 64,
            },
            "contract": "Independent test-only natural admission.",
        }
        attestation_sha = self._write_json(
            remote / "receipts" / attestation_name, attestation,
        )
        pointer = {
            "schema_version": syncer.NATURAL_LATEST_SCHEMA,
            "pointer_kind": "natural",
            "run_id": success["run_id"],
            "status": "verified",
            "updated_at": attestation["verified_at"],
            "receipt_path": str(remote / "receipts" / attestation_name),
            "receipt_sha256": attestation_sha,
            "outcome_receipt_path": success["receipt_path"],
            "outcome_receipt_sha256": success["receipt_sha256"],
            "execution": success["execution"],
        }
        self._write_json(remote / syncer.NATURAL_POINTER_NAME, pointer)
        return pointer

    def test_stable_hash_bound_chain_is_atomically_placed_for_localhost(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = self._remote_fixture(root)
            destination = root / "local" / "utility-intake"
            fake_scp = root / "scp"
            fake_scp.write_text("#!/bin/sh\n", encoding="utf-8")
            fake_scp.chmod(0o755)
            known_hosts = self._known_hosts(root)
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
                    destination=destination, host="florida",
                    known_hosts=known_hosts, scp=fake_scp,
                )
            self.assertEqual(result["status"], "synced")
            self.assertEqual(result["latest_attempt_run_id"], "utility-natural")
            self.assertEqual(result["latest_success_run_id"], "utility-natural")
            self.assertEqual(len(calls), 7)  # base chain plus optional natural-pointer probe
            self.assertTrue(all(command[0] == str(fake_scp) for command in calls))
            self.assertTrue(all("BatchMode=yes" in command for command in calls))
            self.assertTrue(all("StrictHostKeyChecking=yes" in command for command in calls))
            self.assertTrue(all(
                f"UserKnownHostsFile={known_hosts}" in command for command in calls
            ))
            self.assertTrue(all("GlobalKnownHostsFile=/dev/null" in command for command in calls))
            self.assertEqual((destination / "latest-attempt.json").stat().st_mode & 0o777, 0o600)
            self.assertEqual((destination / "receipts/utility-natural.json").stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                (destination / "receipts/utility-natural.verification.json").read_bytes(),
                (remote / "receipts/utility-natural.verification.json").read_bytes(),
            )

    def test_natural_admission_chain_is_hash_validated_and_synced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = self._remote_fixture(root)
            natural = self._add_natural_fixture(remote)
            destination = root / "local" / "utility-intake"
            fake_scp = root / "scp"
            fake_scp.write_text("#!/bin/sh\n", encoding="utf-8")
            fake_scp.chmod(0o755)
            known_hosts = self._known_hosts(root)

            def copy(command, **_kwargs):
                shutil.copyfile(Path(command[-2].split(":", 1)[1]), Path(command[-1]))
                return subprocess.CompletedProcess(command, 0)

            with mock.patch.object(syncer, "REMOTE_ROOT", remote), \
                    mock.patch.object(syncer, "REMOTE_RECEIPTS", remote / "receipts"), \
                    mock.patch.object(syncer.subprocess, "run", side_effect=copy):
                result = syncer.sync_receipts(
                    destination=destination, host="florida",
                    known_hosts=known_hosts, scp=fake_scp,
                )
            self.assertEqual(result["natural_admission_run_id"], natural["run_id"])
            self.assertEqual(
                (destination / syncer.NATURAL_POINTER_NAME).read_bytes(),
                (remote / syncer.NATURAL_POINTER_NAME).read_bytes(),
            )
            self.assertEqual(
                (destination / "receipts/utility-natural.natural.json").read_bytes(),
                (remote / "receipts/utility-natural.natural.json").read_bytes(),
            )

    def test_malformed_natural_admission_preserves_existing_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = self._remote_fixture(root)
            self._add_natural_fixture(remote)
            natural_pointer = json.loads(
                (remote / syncer.NATURAL_POINTER_NAME).read_text(encoding="utf-8")
            )
            natural_pointer["execution"]["natural_schedule_verified"] = True
            self._write_json(remote / syncer.NATURAL_POINTER_NAME, natural_pointer)
            destination = root / "local" / "utility-intake"
            destination.mkdir(parents=True)
            prior = destination / "latest-attempt.json"
            prior.write_text("preserve me\n", encoding="utf-8")
            fake_scp = root / "scp"
            fake_scp.write_text("#!/bin/sh\n", encoding="utf-8")
            fake_scp.chmod(0o755)
            known_hosts = self._known_hosts(root)

            def copy(command, **_kwargs):
                shutil.copyfile(Path(command[-2].split(":", 1)[1]), Path(command[-1]))
                return subprocess.CompletedProcess(command, 0)

            with mock.patch.object(syncer, "REMOTE_ROOT", remote), \
                    mock.patch.object(syncer, "REMOTE_RECEIPTS", remote / "receipts"), \
                    mock.patch.object(syncer.subprocess, "run", side_effect=copy):
                with self.assertRaisesRegex(syncer.SyncError, "natural-run pointer contract"):
                    syncer.sync_receipts(
                        destination=destination, host="florida",
                        known_hosts=known_hosts, scp=fake_scp,
                    )
            self.assertEqual(prior.read_text(encoding="utf-8"), "preserve me\n")

    def test_identical_same_run_receipts_are_compared_without_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = self._remote_fixture(root)
            destination = root / "local" / "utility-intake"
            fake_scp = root / "scp"
            fake_scp.write_text("#!/bin/sh\n", encoding="utf-8")
            fake_scp.chmod(0o755)
            known_hosts = self._known_hosts(root)

            def copy(command, **_kwargs):
                shutil.copyfile(Path(command[-2].split(":", 1)[1]), Path(command[-1]))
                return subprocess.CompletedProcess(command, 0)

            with mock.patch.object(syncer, "REMOTE_ROOT", remote), \
                    mock.patch.object(syncer, "REMOTE_RECEIPTS", remote / "receipts"), \
                    mock.patch.object(syncer.subprocess, "run", side_effect=copy):
                syncer.sync_receipts(
                    destination=destination, host="florida",
                    known_hosts=known_hosts, scp=fake_scp,
                )
                outcome = destination / "receipts/utility-natural.json"
                verification = destination / "receipts/utility-natural.verification.json"
                before = (outcome.stat().st_ino, verification.stat().st_ino)
                syncer.sync_receipts(
                    destination=destination, host="florida",
                    known_hosts=known_hosts, scp=fake_scp,
                )
            self.assertEqual(
                before,
                (outcome.stat().st_ino, verification.stat().st_ino),
            )

    def test_conflicting_same_run_receipt_fails_and_preserves_original_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = self._remote_fixture(root)
            destination = root / "local" / "utility-intake"
            fake_scp = root / "scp"
            fake_scp.write_text("#!/bin/sh\n", encoding="utf-8")
            fake_scp.chmod(0o755)
            known_hosts = self._known_hosts(root)

            def copy(command, **_kwargs):
                shutil.copyfile(Path(command[-2].split(":", 1)[1]), Path(command[-1]))
                return subprocess.CompletedProcess(command, 0)

            with mock.patch.object(syncer, "REMOTE_ROOT", remote), \
                    mock.patch.object(syncer, "REMOTE_RECEIPTS", remote / "receipts"), \
                    mock.patch.object(syncer.subprocess, "run", side_effect=copy):
                syncer.sync_receipts(
                    destination=destination, host="florida",
                    known_hosts=known_hosts, scp=fake_scp,
                )
                outcome_path = destination / "receipts/utility-natural.json"
                original_outcome = outcome_path.read_bytes()
                original_outcome_inode = outcome_path.stat().st_ino
                original_pointer = (destination / "latest-attempt.json").read_bytes()

                remote_outcome_path = remote / "receipts/utility-natural.json"
                remote_outcome = json.loads(remote_outcome_path.read_text(encoding="utf-8"))
                remote_outcome["conflicting_revision"] = 2
                replacement_sha = self._write_json(remote_outcome_path, remote_outcome)
                for pointer_name in ("latest-attempt.json", "latest-success.json"):
                    pointer_path = remote / pointer_name
                    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
                    pointer["receipt_sha256"] = replacement_sha
                    self._write_json(pointer_path, pointer)

                with self.assertRaisesRegex(syncer.SyncError, "immutable receipt conflicts"):
                    syncer.sync_receipts(
                        destination=destination, host="florida",
                        known_hosts=known_hosts, scp=fake_scp,
                    )
            self.assertEqual(outcome_path.read_bytes(), original_outcome)
            self.assertEqual(outcome_path.stat().st_ino, original_outcome_inode)
            self.assertEqual(
                (destination / "latest-attempt.json").read_bytes(),
                original_pointer,
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
            known_hosts = self._known_hosts(root)

            def copy(command, **_kwargs):
                shutil.copyfile(Path(command[-2].split(":", 1)[1]), Path(command[-1]))
                return subprocess.CompletedProcess(command, 0)

            with mock.patch.object(syncer, "REMOTE_ROOT", remote), \
                    mock.patch.object(syncer, "REMOTE_RECEIPTS", remote / "receipts"), \
                    mock.patch.object(syncer.subprocess, "run", side_effect=copy):
                with self.assertRaisesRegex(syncer.SyncError, "hash mismatch"):
                    syncer.sync_receipts(
                        destination=destination, host="florida",
                        known_hosts=known_hosts, scp=fake_scp,
                    )
            self.assertEqual(existing.read_text(), "preserve me\n")

    def test_remote_path_escape_and_unsafe_host_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_scp = root / "scp"
            fake_scp.write_text("#!/bin/sh\n", encoding="utf-8")
            fake_scp.chmod(0o755)
            known_hosts = self._known_hosts(root)
            with self.assertRaisesRegex(syncer.SyncError, "SSH alias"):
                syncer.sync_receipts(
                    destination=root / "local", host="florida;touch-x",
                    known_hosts=known_hosts, scp=fake_scp,
                )
            with self.assertRaisesRegex(syncer.SyncError, "producer directory"):
                syncer._remote_receipt_name("/tmp/escape.json")

    def test_known_hosts_is_explicit_real_and_not_group_or_world_writable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_scp = root / "scp"
            fake_scp.write_text("#!/bin/sh\n", encoding="utf-8")
            fake_scp.chmod(0o755)
            known_hosts = self._known_hosts(root)
            known_hosts.chmod(0o666)
            with self.assertRaisesRegex(syncer.SyncError, "known-hosts file is unsafe"):
                syncer.sync_receipts(
                    destination=root / "local", host="florida",
                    known_hosts=known_hosts, scp=fake_scp,
                )
            known_hosts.unlink()
            target = root / "trusted-hosts"
            target.write_text("florida ssh-ed25519 test\n", encoding="utf-8")
            known_hosts.symlink_to(target)
            with self.assertRaisesRegex(syncer.SyncError, "absolute regular file"):
                syncer.sync_receipts(
                    destination=root / "local", host="florida",
                    known_hosts=known_hosts, scp=fake_scp,
                )

    def test_process_lock_blocks_overlap_without_touching_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "local"
            destination.mkdir()
            existing = destination / "latest-attempt.json"
            existing.write_text("preserve me\n", encoding="utf-8")
            known_hosts = self._known_hosts(root)
            fake_scp = root / "scp"
            fake_scp.write_text("#!/bin/sh\n", encoding="utf-8")
            fake_scp.chmod(0o755)
            descriptor = syncer._acquire_sync_lock(destination)
            try:
                with mock.patch.object(syncer.subprocess, "run") as run:
                    with self.assertRaisesRegex(syncer.SyncError, "already active"):
                        syncer.sync_receipts(
                            destination=destination, host="florida",
                            known_hosts=known_hosts, scp=fake_scp,
                        )
                    run.assert_not_called()
            finally:
                syncer.fcntl.flock(descriptor, syncer.fcntl.LOCK_UN)
                syncer.os.close(descriptor)
            self.assertEqual(existing.read_text(encoding="utf-8"), "preserve me\n")


if __name__ == "__main__":
    unittest.main()
