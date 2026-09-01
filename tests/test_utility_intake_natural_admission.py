from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops/droplet/utility_intake_natural_admission.py"
SPEC = importlib.util.spec_from_file_location("utility_intake_natural_admission", SCRIPT)
admission = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(admission)

FIXED = datetime(2026, 9, 1, 3, 5, tzinfo=timezone.utc)


class UtilityIntakeNaturalAdmissionTests(unittest.TestCase):
    @staticmethod
    def _write_json(path: Path, value: object) -> str:
        raw = admission.canonical_json_bytes(value)
        path.write_bytes(raw)
        path.chmod(0o600)
        return hashlib.sha256(raw).hexdigest()

    def _fixture(self, root: Path) -> dict[str, Path]:
        receipt_dir = root / "receipts"
        receipt_dir.mkdir(parents=True)
        receipt_dir.chmod(0o700)
        run_id = "utility-natural-test"
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
            "service_unit": admission.SERVICE_UNIT,
            "expected_timer_unit": admission.TIMER_UNIT,
            "natural_schedule_verified": False,
            "verification_contract": "Correlate journal evidence independently.",
        }
        parity = {"status": "passed", "sqlite": {"count": 2}, "supabase": {"count": 2}}
        versions = {"collector": "utility-intake-production/1", "query": "q/1", "parser": "p/1"}
        verification_path = receipt_dir / f"{run_id}.verification.json"
        verification_sha = self._write_json(verification_path, {
            "schema_version": admission.VERIFICATION_SCHEMA,
            "run_id": run_id,
            "status": "verified",
            "completed_at": "2026-09-01T03:00:20Z",
            "counts": counts,
            "parity": parity,
            "execution": execution,
        })
        outcome_path = receipt_dir / f"{run_id}.json"
        outcome_sha = self._write_json(outcome_path, {
            "schema_version": admission.RECEIPT_SCHEMA,
            "run_id": run_id,
            "status": "ok",
            "started_at": "2026-09-01T03:00:10Z",
            "completed_at": "2026-09-01T03:00:20Z",
            "counts": counts,
            "parity": parity,
            "versions": versions,
            "verification": {
                "receipt_path": str(verification_path),
                "receipt_sha256": verification_sha,
            },
            "execution": execution,
        })
        pointer = {
            "schema_version": admission.LATEST_SCHEMA,
            "pointer_kind": "attempt",
            "run_id": run_id,
            "status": "ok",
            "updated_at": "2026-09-01T03:00:20Z",
            "receipt_path": str(outcome_path),
            "receipt_sha256": outcome_sha,
            "counts": counts,
            "execution": execution,
        }
        latest_attempt = root / "latest-attempt.json"
        latest_success = root / "latest-success.json"
        self._write_json(latest_attempt, pointer)
        self._write_json(latest_success, {**pointer, "pointer_kind": "success"})
        timer_show = root / "timer-show.properties"
        timer_show.write_text("\n".join([
            f"Id={admission.TIMER_UNIT}",
            "LoadState=loaded",
            "ActiveState=active",
            "UnitFileState=enabled",
            f"Unit={admission.SERVICE_UNIT}",
            "LastTriggerUSec=Mon 2026-08-31 23:00:00 EDT",
            "LastTriggerUSecMonotonic=123456789",
            "NextElapseUSecRealtime=Mon 2026-08-31 23:27:00 EDT",
        ]) + "\n", encoding="utf-8")
        timer_show.chmod(0o600)
        timer_journal = root / "timer.jsonl"
        timer_journal.write_text(json.dumps({
            "__REALTIME_TIMESTAMP": "1788231600000000",
            "UNIT": admission.TIMER_UNIT,
            "MESSAGE": f"Triggered {admission.SERVICE_UNIT}.",
        }) + "\n", encoding="utf-8")
        service_journal = root / "service.jsonl"
        service_journal.write_text(json.dumps({
            # The collector emits its terminal JSON after completed_at; the
            # invocation ID, not an invented pre-start log, binds this row.
            "__REALTIME_TIMESTAMP": "1788231621000000",
            "_SYSTEMD_UNIT": admission.SERVICE_UNIT,
            "_SYSTEMD_INVOCATION_ID": "a" * 32,
            "MESSAGE": "collector entered",
        }) + "\n", encoding="utf-8")
        return {
            "latest_attempt_pointer": latest_attempt,
            "latest_success_pointer": latest_success,
            "receipt_dir": receipt_dir,
            "latest_natural_pointer": root / "latest-natural.json",
            "timer_show_path": timer_show,
            "timer_journal_path": timer_journal,
            "service_journal_path": service_journal,
        }

    def test_exact_natural_evidence_writes_immutable_attestation_and_pointer(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._fixture(Path(tmp))
            pointer = admission.admit(
                **paths, approval=admission.APPROVAL, clock=lambda: FIXED,
            )
            self.assertEqual(pointer["status"], "verified")
            self.assertEqual(pointer["pointer_kind"], "natural")
            self.assertFalse(pointer["execution"]["natural_schedule_verified"])
            attestation_path = Path(pointer["receipt_path"])
            self.assertEqual(attestation_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(paths["latest_natural_pointer"].stat().st_mode & 0o777, 0o600)
            attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
            self.assertEqual(attestation["schema_version"], admission.NATURAL_SCHEMA)
            self.assertEqual(
                attestation["schedule"]["trigger_to_outcome_start_usec"], 10_000_000,
            )
            self.assertEqual(
                attestation["schedule"]["timer_last_trigger_realtime_usec"],
                1_788_231_600_000_000,
            )
            self.assertEqual(
                hashlib.sha256(attestation_path.read_bytes()).hexdigest(),
                pointer["receipt_sha256"],
            )

    def test_manual_or_wrong_invocation_evidence_cannot_admit(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._fixture(Path(tmp))
            paths["timer_journal_path"].write_text(json.dumps({
                "__REALTIME_TIMESTAMP": "1788231600000000",
                "UNIT": admission.TIMER_UNIT,
                "MESSAGE": "Timer unit started without triggering a service.",
            }) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(admission.AdmissionError, "exact service trigger"):
                admission.admit(
                    **paths, approval=admission.APPROVAL, clock=lambda: FIXED,
                )
            self.assertFalse(paths["latest_natural_pointer"].exists())

            paths = self._fixture(Path(tmp) / "wrong-invocation")
            rows = [json.loads(paths["service_journal_path"].read_text())]
            rows[0]["_SYSTEMD_INVOCATION_ID"] = "b" * 32
            paths["service_journal_path"].write_text(
                json.dumps(rows[0]) + "\n", encoding="utf-8",
            )
            with self.assertRaisesRegex(admission.AdmissionError, "outcome invocation"):
                admission.admit(
                    **paths, approval=admission.APPROVAL, clock=lambda: FIXED,
                )
            self.assertFalse(paths["latest_natural_pointer"].exists())

    def test_exact_approval_is_required_before_any_admission_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._fixture(Path(tmp))
            with self.assertRaisesRegex(admission.AdmissionError, "exact.*approval"):
                admission.admit(**paths, approval="approved", clock=lambda: FIXED)
            self.assertFalse(paths["latest_natural_pointer"].exists())
            self.assertFalse(any(paths["receipt_dir"].glob("*.natural.json")))

    def test_systemd_last_trigger_must_match_the_journal_trigger(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._fixture(Path(tmp))
            text = paths["timer_show_path"].read_text(encoding="utf-8")
            paths["timer_show_path"].write_text(
                text.replace("23:00:00 EDT", "22:00:00 EDT"), encoding="utf-8",
            )
            with self.assertRaisesRegex(admission.AdmissionError, "bounded run"):
                admission.admit(
                    **paths, approval=admission.APPROVAL, clock=lambda: FIXED,
                )
            self.assertFalse(paths["latest_natural_pointer"].exists())

    def test_conflicting_same_run_attestation_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._fixture(Path(tmp))
            first = admission.admit(
                **paths, approval=admission.APPROVAL, clock=lambda: FIXED,
            )
            receipt_path = Path(first["receipt_path"])
            before = receipt_path.read_bytes()
            before_inode = receipt_path.stat().st_ino
            timer_show = paths["timer_show_path"].read_text(encoding="utf-8")
            paths["timer_show_path"].write_text(
                timer_show.replace("23:27:00 EDT", "23:57:00 EDT"),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(admission.AdmissionError, "conflicts"):
                admission.admit(
                    **paths, approval=admission.APPROVAL, clock=lambda: FIXED,
                )
            self.assertEqual(receipt_path.read_bytes(), before)
            self.assertEqual(receipt_path.stat().st_ino, before_inode)


if __name__ == "__main__":
    unittest.main()
