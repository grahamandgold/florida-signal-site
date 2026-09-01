#!/usr/bin/env python3
"""Admit one independently evidenced natural utility-intake timer run.

The collector deliberately cannot call this module and cannot attest that a
systemd timer caused its own invocation.  An operator first preserves the
bounded ``systemctl show`` JSON and the timer/service journal JSONL described
in the production runbook, then runs this tool with the exact approval phrase.
The tool binds those independent records to the immutable successful outcome,
writes one create-only natural-run attestation, and atomically advances only
the dedicated natural-run pointer.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping, Sequence
from uuid import uuid4
from zoneinfo import ZoneInfo


APPROVAL = "I_APPROVE_EXACT_UTILITY_INTAKE_NATURAL_ADMISSION"
LATEST_SCHEMA = "FloridaSignalUtilityIntakeProductionLatestV2"
RECEIPT_SCHEMA = "FloridaSignalUtilityIntakeProductionReceiptV3"
VERIFICATION_SCHEMA = "FloridaSignalUtilityIntakeProductionVerificationV1"
NATURAL_SCHEMA = "FloridaSignalUtilityIntakeNaturalRunAttestationV1"
NATURAL_LATEST_SCHEMA = "FloridaSignalUtilityIntakeNaturalRunLatestV1"
TIMER_UNIT = "florida-utility-intake.timer"
SERVICE_UNIT = "florida-utility-intake.service"
MAX_JSON_BYTES = 2_000_000
MAX_JOURNAL_BYTES = 8_000_000
MAX_TRIGGER_TO_OUTCOME_START_USEC = 15 * 60 * 1_000_000
MAX_SYSTEMD_TRIGGER_CLOCK_SKEW_USEC = 5 * 1_000_000
RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}")
SHA_RE = re.compile(r"[0-9a-f]{64}")


class AdmissionError(RuntimeError):
    pass


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_stable_regular(path: Path, cap: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise AdmissionError("admission evidence is unavailable") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= cap:
            raise AdmissionError("admission evidence is not a bounded regular file")
        remaining = before.st_size
        chunks = []
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65_536))
            if not chunk:
                raise AdmissionError("admission evidence changed during read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise AdmissionError("admission evidence changed during read")
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise AdmissionError("admission evidence changed during read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _read_json(path: Path, cap: int = MAX_JSON_BYTES) -> tuple[dict[str, Any], bytes]:
    raw = _read_stable_regular(path, cap)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise AdmissionError("admission evidence is not valid JSON") from error
    if not isinstance(payload, dict):
        raise AdmissionError("admission evidence is not a JSON object")
    return payload, raw


def _read_journal(path: Path) -> tuple[list[dict[str, Any]], bytes]:
    raw = _read_stable_regular(path, MAX_JOURNAL_BYTES)
    rows = []
    try:
        for line in raw.splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise AdmissionError("journal evidence contains a non-object row")
            rows.append(row)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AdmissionError("journal evidence is not valid JSONL") from error
    if not rows:
        raise AdmissionError("journal evidence is empty")
    return rows, raw


def _pointer(path: Path, kind: str) -> tuple[dict[str, Any], bytes]:
    pointer, raw = _read_json(path)
    if set(pointer) != {
        "schema_version", "pointer_kind", "run_id", "status", "updated_at",
        "receipt_path", "receipt_sha256", "counts", "execution",
    }:
        raise AdmissionError("production latest pointer has the wrong shape")
    if (
        pointer.get("schema_version") != LATEST_SCHEMA
        or pointer.get("pointer_kind") != kind
        or not RUN_ID_RE.fullmatch(str(pointer.get("run_id") or ""))
        or pointer.get("status") != "ok"
        or not SHA_RE.fullmatch(str(pointer.get("receipt_sha256") or ""))
        or not isinstance(pointer.get("counts"), dict)
        or not isinstance(pointer.get("execution"), dict)
    ):
        raise AdmissionError("production latest pointer is not an admissible success")
    return pointer, raw


def _receipt_path(value: Any, receipt_dir: Path) -> Path:
    path = Path(str(value or ""))
    if (
        not path.is_absolute()
        or path.parent != receipt_dir
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,220}", path.name)
    ):
        raise AdmissionError("receipt path crossed the exact receipt directory")
    return path


def _parse_systemctl_show(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = _read_stable_regular(path, MAX_JSON_BYTES)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {}
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise AdmissionError("timer show evidence is not UTF-8") from error
        for line in text.splitlines():
            if not line or "=" not in line:
                raise AdmissionError("timer show evidence is not key=value output")
            key, value = line.split("=", 1)
            if not key or key in payload:
                raise AdmissionError("timer show evidence contains a duplicate property")
            payload[key] = value
    if isinstance(payload, list) and len(payload) == 1 and isinstance(payload[0], dict):
        payload = payload[0]
    if not isinstance(payload, dict):
        raise AdmissionError("timer show evidence has the wrong shape")
    required = {
        "Id", "LoadState", "ActiveState", "UnitFileState", "Unit",
        "LastTriggerUSec", "LastTriggerUSecMonotonic", "NextElapseUSecRealtime",
    }
    if set(payload) != required:
        raise AdmissionError("timer show evidence omitted required properties")
    if (
        payload.get("Id") != TIMER_UNIT
        or payload.get("LoadState") != "loaded"
        or payload.get("ActiveState") != "active"
        or payload.get("UnitFileState") != "enabled"
        or payload.get("Unit") != SERVICE_UNIT
    ):
        raise AdmissionError("timer was not loaded, active, enabled, and bound to the exact service")
    monotonic = str(payload.get("LastTriggerUSecMonotonic") or "")
    if not re.search(r"[1-9][0-9]*", monotonic):
        raise AdmissionError("timer has no nonzero last-trigger monotonic clock")
    if not str(payload.get("LastTriggerUSec") or "").strip() or not str(
        payload.get("NextElapseUSecRealtime") or ""
    ).strip():
        raise AdmissionError("timer trigger/next clocks are absent")
    return payload, raw


def _systemd_realtime_usec(value: Any) -> int:
    text = str(value or "").strip()
    match = re.fullmatch(
        r"[A-Z][a-z]{2} (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) (EST|EDT)",
        text,
    )
    if not match:
        raise AdmissionError("timer last-trigger clock is malformed")
    local = datetime.strptime(
        f"{match.group(1)} {match.group(2)}", "%Y-%m-%d %H:%M:%S",
    ).replace(tzinfo=ZoneInfo("America/New_York"))
    if local.tzname() != match.group(3):
        raise AdmissionError("timer last-trigger timezone is inconsistent")
    return int(local.timestamp() * 1_000_000)


def _journal_time(row: Mapping[str, Any]) -> int | None:
    value = str(row.get("__REALTIME_TIMESTAMP") or "")
    return int(value) if re.fullmatch(r"[0-9]{10,20}", value) else None


def _unit_matches(row: Mapping[str, Any], unit: str) -> bool:
    return row.get("_SYSTEMD_UNIT") == unit or row.get("UNIT") == unit


def _parse_iso_usec(value: Any) -> int:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise AdmissionError("outcome clock is malformed") from error
    if parsed.tzinfo is None:
        raise AdmissionError("outcome clock lacks a timezone")
    return int(parsed.timestamp() * 1_000_000)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise AdmissionError("admission output directory is unsafe")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _require_private_directory(path: Path) -> None:
    if not path.is_absolute():
        raise AdmissionError("admission output directory must be absolute")
    path.mkdir(parents=True, exist_ok=True)
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise AdmissionError("admission output directory is unsafe")
    os.chmod(path, 0o700)


def _write_create_only(path: Path, raw: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                raise OSError("natural-run receipt write stalled")
            offset += written
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
    except Exception:
        try:
            os.close(descriptor)
        finally:
            path.unlink(missing_ok=True)
        raise
    os.close(descriptor)
    _fsync_directory(path.parent)


def _read_immutable_bytes(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise AdmissionError("immutable natural-run receipt is unsafe") from error
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_IMODE(before.st_mode) != 0o600
            or not 0 < before.st_size <= MAX_JSON_BYTES
        ):
            raise AdmissionError("immutable natural-run receipt is unsafe")
        remaining = before.st_size
        chunks = []
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65_536))
            if not chunk:
                raise AdmissionError("immutable natural-run receipt changed during comparison")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise AdmissionError("immutable natural-run receipt changed during comparison")
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise AdmissionError("immutable natural-run receipt changed during comparison")
        current = path.lstat()
        if (
            stat.S_ISLNK(current.st_mode)
            or current.st_dev != after.st_dev
            or current.st_ino != after.st_ino
        ):
            raise AdmissionError("immutable natural-run receipt changed during comparison")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _create_or_compare_immutable(path: Path, raw: bytes) -> None:
    try:
        _write_create_only(path, raw)
    except FileExistsError:
        if _read_immutable_bytes(path) != raw:
            raise AdmissionError("immutable natural-run receipt conflicts with existing bytes")


def _atomic_pointer(path: Path, raw: bytes) -> None:
    if not path.is_absolute():
        raise AdmissionError("natural-run pointer path must be absolute")
    _require_private_directory(path.parent)
    if path.is_symlink():
        raise AdmissionError("natural-run pointer destination is a symlink")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    _write_create_only(temporary, raw)
    try:
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def admit(
    *,
    latest_attempt_pointer: Path,
    latest_success_pointer: Path,
    receipt_dir: Path,
    latest_natural_pointer: Path,
    timer_show_path: Path,
    timer_journal_path: Path,
    service_journal_path: Path,
    approval: str,
    clock=lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    if approval != APPROVAL:
        raise AdmissionError("exact natural-run admission approval is required")
    _require_private_directory(receipt_dir)
    producer_root = receipt_dir.parent
    if (
        latest_attempt_pointer.parent != producer_root
        or latest_success_pointer.parent != producer_root
        or latest_natural_pointer.parent != producer_root
        or latest_attempt_pointer.name != "latest-attempt.json"
        or latest_success_pointer.name != "latest-success.json"
        or latest_natural_pointer.name != "latest-natural.json"
    ):
        raise AdmissionError("admission pointers must use the exact producer directory")
    attempt, attempt_raw = _pointer(latest_attempt_pointer, "attempt")
    success, success_raw = _pointer(latest_success_pointer, "success")
    comparable_attempt = dict(attempt)
    comparable_attempt["pointer_kind"] = "success"
    if comparable_attempt != success:
        raise AdmissionError("latest attempt and success do not identify one successful run")

    outcome_path = _receipt_path(success.get("receipt_path"), receipt_dir)
    outcome, outcome_raw = _read_json(outcome_path)
    outcome_sha = hashlib.sha256(outcome_raw).hexdigest()
    execution = outcome.get("execution")
    invocation_id = str((execution or {}).get("systemd_invocation_id") or "")
    if (
        outcome_sha != success.get("receipt_sha256")
        or outcome.get("schema_version") != RECEIPT_SCHEMA
        or outcome.get("run_id") != success.get("run_id")
        or outcome.get("status") != "ok"
        or outcome.get("completed_at") != success.get("updated_at")
        or outcome.get("counts") != success.get("counts")
        or execution != success.get("execution")
        or not re.fullmatch(r"[0-9a-f]{32}", invocation_id)
        or execution.get("execution_context") != "systemd_timer_expected"
        or execution.get("service_unit") != SERVICE_UNIT
        or execution.get("expected_timer_unit") != TIMER_UNIT
        or execution.get("natural_schedule_verified") is not False
    ):
        raise AdmissionError("successful outcome is not bound to reviewable systemd provenance")

    verification = outcome.get("verification")
    versions = outcome.get("versions")
    if (
        not isinstance(verification, dict)
        or not isinstance(versions, dict)
        or set(versions) != {"collector", "query", "parser"}
        or any(not isinstance(value, str) or not value for value in versions.values())
    ):
        raise AdmissionError("successful outcome lacks verification binding")
    verification_path = _receipt_path(verification.get("receipt_path"), receipt_dir)
    verification_receipt, verification_raw = _read_json(verification_path)
    verification_sha = hashlib.sha256(verification_raw).hexdigest()
    if (
        verification_sha != verification.get("receipt_sha256")
        or verification_receipt.get("schema_version") != VERIFICATION_SCHEMA
        or verification_receipt.get("run_id") != outcome.get("run_id")
        or verification_receipt.get("status") != "verified"
        or verification_receipt.get("completed_at") != outcome.get("completed_at")
        or verification_receipt.get("counts") != outcome.get("counts")
        or verification_receipt.get("parity") != outcome.get("parity")
        or verification_receipt.get("execution") != execution
    ):
        raise AdmissionError("verification receipt is not bound to the successful outcome")

    timer_show, timer_show_raw = _parse_systemctl_show(timer_show_path)
    timer_rows, timer_journal_raw = _read_journal(timer_journal_path)
    service_rows, service_journal_raw = _read_journal(service_journal_path)
    service_times = sorted(
        time
        for row in service_rows
        if row.get("_SYSTEMD_INVOCATION_ID") == invocation_id
        and _unit_matches(row, SERVICE_UNIT)
        if (time := _journal_time(row)) is not None
    )
    timer_times = sorted(
        time
        for row in timer_rows
        if _unit_matches(row, TIMER_UNIT)
        and "trigger" in str(row.get("MESSAGE") or "").lower()
        and SERVICE_UNIT in str(row.get("MESSAGE") or "")
        if (time := _journal_time(row)) is not None
    )
    if not service_times:
        raise AdmissionError("service journal does not contain the outcome invocation")
    outcome_started_usec = _parse_iso_usec(outcome.get("started_at"))
    outcome_completed_usec = _parse_iso_usec(outcome.get("completed_at"))
    eligible_triggers = [
        value for value in timer_times
        if 0 <= outcome_started_usec - value <= MAX_TRIGGER_TO_OUTCOME_START_USEC
    ]
    if not eligible_triggers:
        raise AdmissionError("timer journal has no exact service trigger in the natural-run window")
    trigger_usec = eligible_triggers[-1]
    timer_last_trigger_usec = _systemd_realtime_usec(timer_show["LastTriggerUSec"])
    if (
        outcome_completed_usec < outcome_started_usec
        or min(service_times) < trigger_usec
        or max(service_times) > outcome_completed_usec + 300 * 1_000_000
        or abs(timer_last_trigger_usec - trigger_usec)
        > MAX_SYSTEMD_TRIGGER_CLOCK_SKEW_USEC
    ):
        raise AdmissionError("service journal and outcome clocks do not form one bounded run")

    attempt_after, attempt_after_raw = _pointer(latest_attempt_pointer, "attempt")
    success_after, success_after_raw = _pointer(latest_success_pointer, "success")
    if (
        attempt_after_raw != attempt_raw
        or success_after_raw != success_raw
        or attempt_after != attempt
        or success_after != success
    ):
        raise AdmissionError("production latest pointers changed during admission")

    verified_at = iso_utc(clock())
    run_id = str(outcome["run_id"])
    attestation = {
        "schema_version": NATURAL_SCHEMA,
        "status": "verified",
        "run_id": run_id,
        "verified_at": verified_at,
        "outcome": {
            "receipt_path": str(outcome_path),
            "receipt_sha256": outcome_sha,
            "completed_at": outcome.get("completed_at"),
            "counts": outcome.get("counts"),
            "versions": versions,
        },
        "verification": {
            "receipt_path": str(verification_path),
            "receipt_sha256": verification_sha,
        },
        "execution": execution,
        "schedule": {
            "timer_unit": TIMER_UNIT,
            "service_unit": SERVICE_UNIT,
            "timer_active": True,
            "timer_enabled": True,
            "timer_target": timer_show.get("Unit"),
            "timer_last_trigger": timer_show.get("LastTriggerUSec"),
            "timer_last_trigger_realtime_usec": timer_last_trigger_usec,
            "timer_last_trigger_monotonic": timer_show.get("LastTriggerUSecMonotonic"),
            "timer_next_elapse": timer_show.get("NextElapseUSecRealtime"),
            "trigger_realtime_usec": trigger_usec,
            "outcome_started_realtime_usec": outcome_started_usec,
            "trigger_to_outcome_start_usec": outcome_started_usec - trigger_usec,
            "service_journal_first_realtime_usec": min(service_times),
            "service_journal_last_realtime_usec": max(service_times),
        },
        "evidence": {
            "latest_attempt_sha256": hashlib.sha256(attempt_raw).hexdigest(),
            "latest_success_sha256": hashlib.sha256(success_raw).hexdigest(),
            "timer_show_sha256": hashlib.sha256(timer_show_raw).hexdigest(),
            "timer_journal_sha256": hashlib.sha256(timer_journal_raw).hexdigest(),
            "service_journal_sha256": hashlib.sha256(service_journal_raw).hexdigest(),
        },
        "contract": (
            "Independent operator admission of one natural systemd timer run; the collector "
            "did not attest its own scheduling and no source, mirror, score, Candidate, or "
            "publication row was written."
        ),
    }
    attestation_raw = canonical_json_bytes(attestation)
    attestation_path = receipt_dir / f"{run_id}.natural.json"
    _create_or_compare_immutable(attestation_path, attestation_raw)
    attestation_sha = hashlib.sha256(attestation_raw).hexdigest()
    pointer = {
        "schema_version": NATURAL_LATEST_SCHEMA,
        "pointer_kind": "natural",
        "run_id": run_id,
        "status": "verified",
        "updated_at": verified_at,
        "receipt_path": str(attestation_path),
        "receipt_sha256": attestation_sha,
        "outcome_receipt_path": str(outcome_path),
        "outcome_receipt_sha256": outcome_sha,
        "execution": execution,
    }
    _atomic_pointer(latest_natural_pointer, canonical_json_bytes(pointer))
    return pointer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--latest-attempt-pointer", required=True, type=Path)
    parser.add_argument("--latest-success-pointer", required=True, type=Path)
    parser.add_argument("--receipt-dir", required=True, type=Path)
    parser.add_argument("--latest-natural-pointer", required=True, type=Path)
    parser.add_argument("--timer-show", required=True, type=Path)
    parser.add_argument("--timer-journal", required=True, type=Path)
    parser.add_argument("--service-journal", required=True, type=Path)
    parser.add_argument("--approval", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        pointer = admit(
            latest_attempt_pointer=args.latest_attempt_pointer,
            latest_success_pointer=args.latest_success_pointer,
            receipt_dir=args.receipt_dir,
            latest_natural_pointer=args.latest_natural_pointer,
            timer_show_path=args.timer_show,
            timer_journal_path=args.timer_journal,
            service_journal_path=args.service_journal,
            approval=args.approval,
        )
    except (AdmissionError, OSError, ValueError, TypeError) as error:
        print(json.dumps({"status": "not_admitted", "reason": str(error)}))
        return 1
    print(json.dumps(pointer, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
