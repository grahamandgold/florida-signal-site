#!/usr/bin/env python3
"""Default-off production package for SFWMD Pending ERP observations.

The official network fetch and deterministic normalization remain in
``sfwmd_pending_erp_shadow``.  This module verifies that complete evidence
bundle, commits normalized current/version state and an immutable run receipt
in one SQLite transaction, and queues an idempotent private Supabase mirror.

The scheduled command is inert unless ``FLORIDA_SIGNAL_SFWMD_ENABLED=1``.
Mirroring is a second gate and requires ``FLORIDA_SIGNAL_SFWMD_MIRROR_ENABLED=1``
plus process-only Supabase credentials.  There is no scoring, Candidate,
queue, publication, historical scan, or unrestricted backfill path.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import urllib.error
import urllib.request
import uuid
from typing import Any, Callable, Mapping, Protocol, Sequence
from zoneinfo import ZoneInfo


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import sfwmd_pending_erp_shadow as shadow  # noqa: E402


SQLITE_SCHEMA_VERSION = "FloridaSignalSfwmdSqliteV1"
SCHEMA_SQL_PATH = SCRIPT_DIR / "sfwmd_pending_erp_schema.sql"
SQLITE_MIGRATION_SHA256 = "a8f39dfe2d9dcff1ffe85cce16a5771a58138fa2cf6d1dcfc1e96c69a724d088"
SQLITE_OBJECT_MANIFEST_SHA256 = "6b907c0c9943d24884c4365bb3483548e7d9d7ba831e999b3f202418b97ed98f"
RECEIPT_SCHEMA = "FloridaSignalSfwmdPendingErpProductionReceiptV1"
LATEST_SCHEMA = "FloridaSignalSfwmdPendingErpLatestV1"
MIRROR_PAYLOAD_SCHEMA = "FloridaSignalSfwmdPendingErpMirrorPayloadV1"
PROVENANCE_SCHEMA = "FloridaSignalSfwmdRunProvenanceV1"
TIMER_CANARY_SCHEMA = "FloridaSignalSfwmdTimerCanaryV1"
EARLY_FAILURE_SCHEMA = "FloridaSignalSfwmdEarlyFailureV1"
COLLECTOR_VERSION = "sfwmd-pending-erp-production/1.0.0"
MAX_SOURCE_ROWS = shadow.MAX_RECORD_COUNT
MAX_IN_SCOPE_ROWS = 500
# Production units pin one 2,000-row page. Keep bounded retry/headroom while
# refusing evidence generated under an unreviewed high-request pagination plan.
MAX_RAW_RESPONSE_ENTRIES = 64
MAX_RAW_RESPONSE_ATTEMPTS = 6
MAX_SOURCE_OBJECT_ID = 2_147_483_647
MAX_MIRROR_RESPONSE_BYTES = 1_000_000
MIRROR_TIMEOUT_SECONDS = 30
TIMER_UNIT = "florida-sfwmd-pending-erp.timer"
TIMER_SERVICE_UNIT = "florida-sfwmd-pending-erp-timer.service"
MANUAL_SERVICE_UNIT = "florida-sfwmd-pending-erp.service"
TIMER_HOUR = 6
TIMER_MINUTE = 17
TIMER_PROVENANCE_WINDOW_MINUTES = 15
MAX_CGROUP_BYTES = 8_000
RUN_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
SYSTEMD_INVOCATION_RE = re.compile(r"^[0-9a-f]{32}$")
ALERT_UNIT_RE = re.compile(r"^florida-sfwmd-pending-erp(?:-timer)?\.service$")
UTC_CLOCK_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$"
)
SCHEMA_OBJECTS = {
    ("table", "sfwmd_pending_erp_schema"),
    ("table", "sfwmd_pending_erp_runs"),
    ("table", "sfwmd_pending_erp_records"),
    ("table", "sfwmd_pending_erp_versions"),
    ("table", "sfwmd_pending_erp_mirror_outbox"),
    ("table", "sfwmd_pending_erp_state"),
    ("index", "sfwmd_pending_erp_runs_completed_idx"),
    ("index", "sfwmd_pending_erp_records_current_idx"),
    ("index", "sfwmd_pending_erp_outbox_pending_idx"),
    ("trigger", "sfwmd_pending_erp_runs_no_update"),
    ("trigger", "sfwmd_pending_erp_runs_no_delete"),
    ("trigger", "sfwmd_pending_erp_versions_no_update"),
    ("trigger", "sfwmd_pending_erp_versions_no_delete"),
    ("trigger", "sfwmd_pending_erp_outbox_payload_no_update"),
    ("trigger", "sfwmd_pending_erp_outbox_no_delete"),
}


class ProductionError(RuntimeError):
    """A local admission, receipt, or mirror contract failed closed."""


class MirrorTransport(Protocol):
    def commit(self, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def canonical_bytes(value: object) -> bytes:
    return shadow.canonical_json_bytes(value)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _require_absolute(path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise ProductionError(f"{label} must be an explicit absolute path")
    return path


def _open_writer_lock(path: Path):
    _require_absolute(path, "writer lock path")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ProductionError("refusing a symlink writer lock")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise ProductionError("writer lock is not a regular file")
    return os.fdopen(fd, "a+b")


def _write_all(fd: int, body: bytes) -> None:
    view = memoryview(body)
    offset = 0
    while offset < len(body):
        written = os.write(fd, view[offset:])
        if written <= 0:
            raise OSError("durable write made no forward progress")
        offset += written


def write_create_only_fsynced(path: Path, value: object) -> str:
    _require_absolute(path, "receipt path")
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    if path.is_symlink():
        raise ProductionError("refusing a symlink receipt path")
    body = canonical_bytes(value)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        existing = path.read_bytes()
        if existing != body:
            raise ProductionError("run id already has a different terminal receipt")
        return sha256_bytes(existing)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ProductionError("terminal receipt is not a regular file")
        _write_all(fd, body)
        os.fsync(fd)
    except Exception:
        try:
            os.close(fd)
        finally:
            path.unlink(missing_ok=True)
        raise
    os.close(fd)
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return sha256_bytes(body)


def atomic_write_json(path: Path, value: object) -> str:
    _require_absolute(path, "latest pointer")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ProductionError("refusing a symlink latest pointer")
    body = canonical_bytes(value)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(temporary, flags, 0o600)
    try:
        _write_all(fd, body)
        os.fsync(fd)
    except Exception:
        try:
            os.close(fd)
        finally:
            temporary.unlink(missing_ok=True)
        raise
    os.close(fd)
    os.replace(temporary, path)
    os.chmod(path, 0o600)
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return sha256_bytes(body)


def manual_provenance(invocation_kind: str) -> dict[str, Any]:
    if invocation_kind not in {"direct", "manual_service"}:
        raise ProductionError("manual provenance kind is invalid")
    return {
        "schema_version": PROVENANCE_SCHEMA,
        "natural_run": False,
        "invocation_kind": invocation_kind,
        "verified": False,
        "timer_unit": None,
        "service_unit": MANUAL_SERVICE_UNIT if invocation_kind == "manual_service" else None,
        "systemd_invocation_id": None,
        "trigger_timer_realtime_usec": None,
        "runtime_cgroup_sha256": None,
        "scheduled_for": None,
        "canary_path": None,
        "canary_sha256": None,
    }


def _timer_slot(instant: dt.datetime) -> dt.datetime:
    if instant.tzinfo is None:
        raise ProductionError("timer provenance clock must be timezone-aware")
    local = instant.astimezone(ZoneInfo("America/New_York"))
    slot = local.replace(hour=TIMER_HOUR, minute=TIMER_MINUTE, second=0, microsecond=0)
    if local < slot:
        slot -= dt.timedelta(days=1)
    return slot.astimezone(dt.timezone.utc)


def systemd_timer_runtime_context() -> dict[str, str]:
    """Verify systemd timer activation metadata and this process's service cgroup."""
    trigger_unit = os.environ.get("TRIGGER_UNIT", "")
    trigger_usec = os.environ.get("TRIGGER_TIMER_REALTIME_USEC", "")
    cgroup_path = Path("/proc/self/cgroup")
    if trigger_unit != TIMER_UNIT or re.fullmatch(r"[0-9]{1,20}", trigger_usec) is None:
        raise ProductionError("process lacks systemd timer activation metadata")
    if cgroup_path.is_symlink() or not cgroup_path.is_file():
        raise ProductionError("process lacks a readable systemd service cgroup")
    body = cgroup_path.read_bytes()
    if len(body) > MAX_CGROUP_BYTES:
        raise ProductionError("systemd cgroup evidence exceeds its byte cap")
    try:
        evidence = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProductionError("systemd cgroup evidence is not UTF-8") from exc
    lines = evidence.splitlines()
    if not any(line.rsplit("/", 1)[-1] == TIMER_SERVICE_UNIT for line in lines):
        raise ProductionError("process is not running in the timer-only service cgroup")
    return {
        "trigger_unit": trigger_unit,
        "trigger_timer_realtime_usec": trigger_usec,
        "runtime_service_unit": TIMER_SERVICE_UNIT,
        "runtime_cgroup_sha256": sha256_bytes(body),
        "runtime_cgroup_evidence": evidence,
    }


def create_timer_provenance(
    *,
    canary_dir: Path,
    run_id: str,
    systemd_invocation_id: str,
    runtime_context: Mapping[str, Any],
    clock: Callable[[], dt.datetime] = utc_now,
) -> dict[str, Any]:
    """Create the immutable canary available only to the timer-only unit path."""
    if not RUN_ID_RE.fullmatch(run_id):
        raise ProductionError("timer canary run id is invalid")
    invocation_id = systemd_invocation_id
    if not isinstance(invocation_id, str) or not SYSTEMD_INVOCATION_RE.fullmatch(invocation_id):
        raise ProductionError("timer path requires a systemd INVOCATION_ID")
    now = clock()
    slot = _timer_slot(now)
    if not slot <= now.astimezone(dt.timezone.utc) <= slot + dt.timedelta(
        minutes=TIMER_PROVENANCE_WINDOW_MINUTES
    ):
        raise ProductionError("timer invocation falls outside its bounded schedule window")
    expected_runtime_keys = {
        "trigger_unit", "trigger_timer_realtime_usec", "runtime_service_unit",
        "runtime_cgroup_sha256", "runtime_cgroup_evidence",
    }
    if not isinstance(runtime_context, Mapping) or set(runtime_context) != expected_runtime_keys:
        raise ProductionError("systemd timer runtime context is not exact")
    trigger_usec = runtime_context.get("trigger_timer_realtime_usec")
    cgroup_evidence = runtime_context.get("runtime_cgroup_evidence")
    if (
        runtime_context.get("trigger_unit") != TIMER_UNIT
        or runtime_context.get("runtime_service_unit") != TIMER_SERVICE_UNIT
        or not isinstance(trigger_usec, str)
        or re.fullmatch(r"[0-9]{1,20}", trigger_usec) is None
        or not isinstance(runtime_context.get("runtime_cgroup_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", runtime_context["runtime_cgroup_sha256"]) is None
        or not isinstance(cgroup_evidence, str)
        or len(cgroup_evidence.encode("utf-8")) > MAX_CGROUP_BYTES
        or sha256_bytes(cgroup_evidence.encode("utf-8"))
            != runtime_context.get("runtime_cgroup_sha256")
        or not any(
            line.rsplit("/", 1)[-1] == TIMER_SERVICE_UNIT
            for line in cgroup_evidence.splitlines()
        )
    ):
        raise ProductionError("systemd timer runtime context is invalid")
    try:
        trigger_at = dt.datetime.fromtimestamp(int(trigger_usec) / 1_000_000, dt.timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise ProductionError("systemd timer trigger clock is invalid") from exc
    if not slot <= trigger_at <= slot + dt.timedelta(minutes=TIMER_PROVENANCE_WINDOW_MINUTES):
        raise ProductionError("systemd timer trigger clock is outside the schedule window")
    canary = {
        "schema_version": TIMER_CANARY_SCHEMA,
        "run_id": run_id,
        "timer_unit": TIMER_UNIT,
        "service_unit": TIMER_SERVICE_UNIT,
        "systemd_invocation_id": invocation_id,
        "trigger_timer_realtime_usec": trigger_usec,
        "runtime_cgroup_sha256": runtime_context["runtime_cgroup_sha256"],
        "runtime_cgroup_evidence": cgroup_evidence,
        "scheduled_for": shadow.iso_utc(slot),
        "created_at": shadow.iso_utc(now),
    }
    _require_absolute(canary_dir, "timer canary directory")
    canary_path = canary_dir / f"{run_id}.json"
    canary_sha = write_create_only_fsynced(canary_path, canary)
    os.chmod(canary_path, 0o400)
    return {
        "schema_version": PROVENANCE_SCHEMA,
        "natural_run": True,
        "invocation_kind": "systemd_timer",
        "verified": True,
        "timer_unit": TIMER_UNIT,
        "service_unit": TIMER_SERVICE_UNIT,
        "systemd_invocation_id": invocation_id,
        "trigger_timer_realtime_usec": trigger_usec,
        "runtime_cgroup_sha256": runtime_context["runtime_cgroup_sha256"],
        "scheduled_for": canary["scheduled_for"],
        "canary_path": str(canary_path),
        "canary_sha256": canary_sha,
    }


def validate_provenance(provenance: Mapping[str, Any], run_id: str) -> dict[str, Any]:
    expected_keys = {
        "schema_version", "natural_run", "invocation_kind", "verified",
        "timer_unit", "service_unit", "systemd_invocation_id", "scheduled_for",
        "canary_path", "canary_sha256", "trigger_timer_realtime_usec",
        "runtime_cgroup_sha256",
    }
    if not isinstance(provenance, Mapping) or set(provenance) != expected_keys:
        raise ProductionError("run provenance contract is not exact")
    value = dict(provenance)
    if value["schema_version"] != PROVENANCE_SCHEMA:
        raise ProductionError("run provenance schema is unsupported")
    kind = value["invocation_kind"]
    if kind in {"direct", "manual_service"}:
        expected_service = MANUAL_SERVICE_UNIT if kind == "manual_service" else None
        if value != manual_provenance(kind) or value["service_unit"] != expected_service:
            raise ProductionError("manual invocation cannot claim timer provenance")
        return value
    if kind != "systemd_timer" or value.get("natural_run") is not True or value.get("verified") is not True:
        raise ProductionError("only verified systemd-timer provenance is natural")
    if value.get("timer_unit") != TIMER_UNIT or value.get("service_unit") != TIMER_SERVICE_UNIT:
        raise ProductionError("timer provenance names an unexpected unit")
    invocation_id = value.get("systemd_invocation_id")
    trigger_usec_value = value.get("trigger_timer_realtime_usec")
    scheduled_value = value.get("scheduled_for")
    canary_path_value = value.get("canary_path")
    if not isinstance(invocation_id, str) or not SYSTEMD_INVOCATION_RE.fullmatch(invocation_id):
        raise ProductionError("timer provenance invocation id is invalid")
    if (
        not isinstance(trigger_usec_value, str)
        or re.fullmatch(r"[0-9]{1,20}", trigger_usec_value) is None
        or not isinstance(scheduled_value, str)
        or UTC_CLOCK_RE.fullmatch(scheduled_value) is None
        or not isinstance(canary_path_value, str)
        or not isinstance(value.get("canary_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", value["canary_sha256"]) is None
        or not isinstance(value.get("runtime_cgroup_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", value["runtime_cgroup_sha256"]) is None
    ):
        raise ProductionError("timer provenance types or hashes are invalid")
    canary_path = Path(canary_path_value)
    if not canary_path.is_absolute() or canary_path.is_symlink() or not canary_path.is_file():
        raise ProductionError("timer provenance canary is missing or unsafe")
    if canary_path.name != f"{run_id}.json" or (canary_path.stat().st_mode & 0o777) != 0o400:
        raise ProductionError("timer provenance canary identity or mode is invalid")
    body = canary_path.read_bytes()
    if sha256_bytes(body) != value.get("canary_sha256"):
        raise ProductionError("timer provenance canary hash mismatch")
    try:
        canary = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ProductionError("timer provenance canary JSON is invalid") from exc
    if body != canonical_bytes(canary):
        raise ProductionError("timer provenance canary bytes are not canonical")
    expected_canary_keys = {
        "schema_version", "run_id", "timer_unit", "service_unit",
        "systemd_invocation_id", "trigger_timer_realtime_usec",
        "runtime_cgroup_sha256", "runtime_cgroup_evidence", "scheduled_for", "created_at",
    }
    if not isinstance(canary, dict) or set(canary) != expected_canary_keys:
        raise ProductionError("timer provenance canary contract is not exact")
    if canary != {
        "schema_version": TIMER_CANARY_SCHEMA,
        "run_id": run_id,
        "timer_unit": TIMER_UNIT,
        "service_unit": TIMER_SERVICE_UNIT,
        "systemd_invocation_id": invocation_id,
        "trigger_timer_realtime_usec": value["trigger_timer_realtime_usec"],
        "runtime_cgroup_sha256": value["runtime_cgroup_sha256"],
        "runtime_cgroup_evidence": canary.get("runtime_cgroup_evidence"),
        "scheduled_for": value["scheduled_for"],
        "created_at": canary.get("created_at"),
    }:
        raise ProductionError("timer provenance canary fields disagree")
    canary_scheduled = canary.get("scheduled_for")
    canary_created = canary.get("created_at")
    trigger_usec = canary.get("trigger_timer_realtime_usec")
    cgroup_evidence = canary.get("runtime_cgroup_evidence")
    if (
        not isinstance(canary_scheduled, str)
        or UTC_CLOCK_RE.fullmatch(canary_scheduled) is None
        or not isinstance(canary_created, str)
        or UTC_CLOCK_RE.fullmatch(canary_created) is None
        or not isinstance(trigger_usec, str)
        or re.fullmatch(r"[0-9]{1,20}", trigger_usec) is None
        or not isinstance(canary.get("runtime_cgroup_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", canary["runtime_cgroup_sha256"]) is None
        or not isinstance(cgroup_evidence, str)
        or len(cgroup_evidence.encode("utf-8")) > MAX_CGROUP_BYTES
        or sha256_bytes(cgroup_evidence.encode("utf-8"))
            != canary.get("runtime_cgroup_sha256")
        or not any(
            line.rsplit("/", 1)[-1] == TIMER_SERVICE_UNIT
            for line in cgroup_evidence.splitlines()
        )
    ):
        raise ProductionError("timer provenance runtime evidence is invalid")
    try:
        scheduled = dt.datetime.fromisoformat(canary_scheduled.replace("Z", "+00:00"))
        created = dt.datetime.fromisoformat(canary_created.replace("Z", "+00:00"))
        trigger_at = dt.datetime.fromtimestamp(
            int(trigger_usec) / 1_000_000, dt.timezone.utc
        )
    except (OverflowError, OSError, ValueError) as exc:
        raise ProductionError("timer provenance runtime clock is invalid") from exc
    if (
        scheduled.tzinfo is None or created.tzinfo is None
        or scheduled.utcoffset() != dt.timedelta(0)
        or created.utcoffset() != dt.timedelta(0)
        or _timer_slot(scheduled) != scheduled
        or not scheduled <= trigger_at <= created <= scheduled + dt.timedelta(
            minutes=TIMER_PROVENANCE_WINDOW_MINUTES
        )
    ):
        raise ProductionError("timer provenance clocks are invalid")
    return value


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ProductionError(f"{label} is missing or unsafe")
    try:
        body = path.read_bytes()
        if len(body) > 2_000_000:
            raise ProductionError(f"{label} exceeds its evidence byte cap")
        payload = json.loads(body)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProductionError(f"{label} is missing or invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ProductionError(f"{label} must be a JSON object")
    try:
        canonical = canonical_bytes(payload)
    except (TypeError, ValueError) as exc:
        raise ProductionError(f"{label} contains a non-canonical JSON value") from exc
    if body != canonical:
        raise ProductionError(f"{label} bytes are not canonical")
    return payload


def fsync_evidence_bundle(run_dir: Path) -> None:
    """Make the already create-only evidence durable before database admission."""
    directories = [run_dir, run_dir / "raw"]
    allowed_files = {
        "boundary-reference.json", "bundle-manifest.json", "raw-manifest.json",
        "receipt.json", "shadow-content-index.jsonl", "shadow-records.jsonl",
    }
    files: list[Path] = []
    for path in run_dir.iterdir():
        if path.is_symlink():
            raise ProductionError("evidence bundle contains a symlink")
        if path.is_dir():
            if path.name != "raw":
                raise ProductionError("evidence bundle contains an unexpected directory")
        elif path.is_file():
            if path.name not in allowed_files:
                raise ProductionError("evidence bundle contains an unexpected file")
            files.append(path)
        else:
            raise ProductionError("evidence bundle contains a non-regular object")
    for path in (run_dir / "raw").iterdir():
        if path.is_symlink() or not path.is_file():
            raise ProductionError("raw evidence contains a non-regular object")
        files.append(path)
    for path in files:
        if path.is_symlink():
            raise ProductionError("evidence bundle contains a symlink")
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ProductionError("evidence object is not a regular file")
            os.fchmod(fd, 0o400)
            os.fsync(fd)
        finally:
            os.close(fd)
    for directory in reversed(directories):
        os.chmod(directory, 0o500)
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _content_projection(row: Mapping[str, Any]) -> dict[str, Any]:
    attributes = row.get("attributes")
    if not isinstance(attributes, Mapping):
        raise ProductionError("normalized row attributes are missing")
    return {
        "schema_version": "FloridaSignalSfwmdSourceContentV1",
        "attributes": {key: value for key, value in attributes.items() if key != "OBJECTID"},
        "geometry": row.get("geometry"),
    }


def _count_value(counts: Mapping[str, Any], key: str, maximum: int | None = None) -> int:
    value = counts.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProductionError(f"collection count {key} is invalid")
    if maximum is not None and value > maximum:
        raise ProductionError(f"collection count {key} exceeds its safety cap")
    return value


def _evidence_clock(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, str) or UTC_CLOCK_RE.fullmatch(value) is None:
        raise ProductionError(f"{label} is not canonical UTC")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProductionError(f"{label} is invalid") from exc
    if parsed.utcoffset() != dt.timedelta(0):
        raise ProductionError(f"{label} is not UTC")
    return parsed.astimezone(dt.timezone.utc)


def _validate_collection_contract(collection: Mapping[str, Any]) -> None:
    expected_keys = {
        "schema_version", "run_id", "mode", "dry_run", "status", "reason_code",
        "terminal_error", "source", "versions", "clocks", "event_clock_maxima",
        "event_through", "event_through_semantics", "scope", "counts",
        "app_status_counts_observed", "app_status_counts_in_scope", "app_status_policy",
        "rejection_reasons", "pagination", "hashes", "quality", "safety",
    }
    if set(collection) != expected_keys:
        raise ProductionError("collection receipt contract is not exact")
    if collection.get("schema_version") != "FloridaSignalSfwmdPendingErpShadowReceiptV1":
        raise ProductionError("collection receipt schema is not supported")
    if collection.get("mode") != "shadow_file_only" or collection.get("dry_run") is not True:
        raise ProductionError("unexpected collection evidence mode")
    if collection.get("source") != {
        "agency": "South Florida Water Management District",
        "url": shadow.LAYER_URL,
        "layer_id": shadow.LAYER_ID,
        "layer_name": shadow.LAYER_NAME,
        "population": "pending environmental resource applications (all types)",
        "native_wkid": shadow.SOURCE_NATIVE_WKID,
        "query_output_wkid": shadow.OUTPUT_WKID,
        "is_data_versioned": False,
        "historic_moment_supported": False,
    }:
        raise ProductionError("collection source contract changed")
    if collection.get("versions") != {
        "collector": shadow.COLLECTOR_VERSION,
        "parser": shadow.PARSER_VERSION,
        "normalizer": shadow.NORMALIZER_VERSION,
    }:
        raise ProductionError("collection version contract changed")
    if collection.get("safety") != {
        "read_only_source_requests": True,
        "database_writes": False,
        "supabase_writes": False,
        "queue_writes": False,
        "scoring": False,
        "publication": False,
        "timer_created_or_changed": False,
        "production_admission": False,
        "promotion_eligible": False,
        "connected_label_allowed": False,
    }:
        raise ProductionError("collection safety contract changed")
    if collection.get("app_status_policy") != (
        "retained_verbatim_layer_membership_defines_pending_no_allowlist"
    ):
        raise ProductionError("collection status-membership policy changed")
    if collection.get("event_through_semantics") != (
        "maximum AppReceivedDate among included Fort Lauderdale shadow rows"
    ):
        raise ProductionError("collection event-through semantics changed")

    clocks = collection.get("clocks")
    if not isinstance(clocks, Mapping) or set(clocks) != {
        "run_started_at", "observed_at", "source_checked_at", "source_modified_at",
        "source_modified_status", "source_time_zone",
    }:
        raise ProductionError("collection clock contract is not exact")
    started = _evidence_clock(clocks.get("run_started_at"), "collection start clock")
    observed = _evidence_clock(clocks.get("observed_at"), "collection observation clock")
    checked = _evidence_clock(clocks.get("source_checked_at"), "collection source-check clock")
    if (
        not started <= checked <= observed
        or checked != observed
        or clocks.get("source_modified_at") is not None
        or clocks.get("source_modified_status") != "UNKNOWN_NOT_EXPOSED"
        or clocks.get("source_time_zone") != shadow.SOURCE_TIME_ZONE
    ):
        raise ProductionError("collection clocks disagree with the pinned contract")

    maxima = collection.get("event_clock_maxima")
    if not isinstance(maxima, Mapping) or set(maxima) != set(shadow.EVENT_CLOCK_FIELDS):
        raise ProductionError("collection event-clock maxima contract is not exact")
    for key, value in maxima.items():
        if value is not None:
            _evidence_clock(value, f"collection {key} maximum")
    if collection.get("event_through") != maxima.get("app_received_at"):
        raise ProductionError("collection event-through does not match its declared maximum")
    if collection.get("event_through") is not None and _evidence_clock(
        collection["event_through"], "collection event-through"
    ) > observed:
        raise ProductionError("collection event-through is later than observation")

    count_keys = {
        "rows_observed", "rows_shadow_included", "rows_test_excluded",
        "rows_outside_boundary", "rows_rejected", "duplicate_identities",
        "pages_expected", "pages_succeeded",
    }
    counts = collection.get("counts")
    if not isinstance(counts, Mapping) or set(counts) != count_keys:
        raise ProductionError("collection receipt count contract changed")
    for key in count_keys:
        _count_value(counts, key, MAX_SOURCE_ROWS)

    for label in (
        "app_status_counts_observed", "app_status_counts_in_scope", "rejection_reasons"
    ):
        values = collection.get(label)
        if (
            not isinstance(values, Mapping)
            or any(not isinstance(key, str) or not key for key in values)
            or any(isinstance(value, bool) or not isinstance(value, int) or value <= 0
                   for value in values.values())
        ):
            raise ProductionError(f"collection {label} contract is invalid")

    pagination = collection.get("pagination")
    if not isinstance(pagination, Mapping) or set(pagination) != {
        "method", "page_size", "object_ids_start_count", "object_ids_end_count",
        "object_ids_stable", "object_ids_start_sha256", "object_ids_end_sha256",
    }:
        raise ProductionError("collection pagination contract is not exact")
    if (
        pagination.get("method") != "frozen_OBJECTID_set_range_pages_in_ASC_order"
        or isinstance(pagination.get("page_size"), bool)
        or not isinstance(pagination.get("page_size"), int)
        or not 1 <= pagination["page_size"] <= MAX_SOURCE_ROWS
        or isinstance(pagination.get("object_ids_start_count"), bool)
        or not isinstance(pagination.get("object_ids_start_count"), int)
        or not 0 <= pagination["object_ids_start_count"] <= MAX_SOURCE_ROWS
        or isinstance(pagination.get("object_ids_end_count"), bool)
        or not isinstance(pagination.get("object_ids_end_count"), int)
        or not 0 <= pagination["object_ids_end_count"] <= MAX_SOURCE_ROWS
        or not isinstance(pagination.get("object_ids_stable"), bool)
        or any(
            not isinstance(pagination.get(key), str)
            or re.fullmatch(r"[0-9a-f]{64}", pagination[key]) is None
            for key in ("object_ids_start_sha256", "object_ids_end_sha256")
        )
    ):
        raise ProductionError("collection pagination values are invalid")

    hashes = collection.get("hashes")
    if not isinstance(hashes, Mapping) or set(hashes) != {
        "schema_contract_sha256", "source_schema_sha256", "raw_manifest_sha256",
        "shadow_records_sha256", "source_content_index_sha256",
        "boundary_reference_sha256",
    }:
        raise ProductionError("collection hash contract is not exact")
    expected_schema_hash = sha256_bytes(canonical_bytes(shadow.SCHEMA_CONTRACT))
    if hashes.get("schema_contract_sha256") != expected_schema_hash:
        raise ProductionError("collection schema-contract hash changed")
    for key in (
        "raw_manifest_sha256", "shadow_records_sha256", "source_content_index_sha256"
    ):
        if not isinstance(hashes.get(key), str) or re.fullmatch(
            r"[0-9a-f]{64}", hashes[key]
        ) is None:
            raise ProductionError("collection contains an invalid evidence hash")
    for key in ("source_schema_sha256", "boundary_reference_sha256"):
        if hashes.get(key) is not None and (
            not isinstance(hashes[key], str)
            or re.fullmatch(r"[0-9a-f]{64}", hashes[key]) is None
        ):
            raise ProductionError("collection contains an invalid optional evidence hash")

    quality = collection.get("quality")
    if not isinstance(quality, Mapping) or set(quality) != {
        "accounting_identity_passed", "source_count_parity_passed",
        "business_identity_unique", "source_object_id_set_stable",
        "all_pages_succeeded", "schema_contract_passed",
    } or any(not isinstance(value, bool) for value in quality.values()):
        raise ProductionError("collection quality contract is not exact")

    scope = collection.get("scope")
    if not isinstance(scope, Mapping) or set(scope) != {
        "jurisdiction", "basis", "mailing_city_used_for_scope",
        "boundary_source_url", "boundary_layer_id", "boundary_layer_name",
        "boundary_record", "boundary_sha256", "boundary_source_schema_sha256",
    }:
        raise ProductionError("collection scope contract is not exact")
    if (
        scope.get("jurisdiction") != "City of Fort Lauderdale"
        or scope.get("basis") != "official_boundary_polygon_intersection"
        or scope.get("mailing_city_used_for_scope") is not False
        or scope.get("boundary_source_url") != shadow.BOUNDARY_LAYER_URL
        or scope.get("boundary_layer_id") != shadow.BOUNDARY_LAYER_ID
        or scope.get("boundary_layer_name") != shadow.BOUNDARY_LAYER_NAME
    ):
        raise ProductionError("collection scope identity changed")
    for key in ("boundary_sha256", "boundary_source_schema_sha256"):
        if scope.get(key) is not None and (
            not isinstance(scope[key], str)
            or re.fullmatch(r"[0-9a-f]{64}", scope[key]) is None
        ):
            raise ProductionError("collection scope contains an invalid hash")

    status = collection.get("status")
    reasons = {
        "ok": {None},
        "empty": {None},
        "partial": {
            "SOURCE_OBJECT_ID_SET_CHANGED_DURING_RUN",
            "ROW_QUALITY_OR_ACCOUNTING_FAILURE",
        },
        "failed": {"SOURCE_ROW_BUDGET_EXCEEDED", "COLLECTOR_OR_CONTRACT_FAILURE"},
    }
    if status not in reasons or collection.get("reason_code") not in reasons[status]:
        raise ProductionError("collection terminal status contract is invalid")
    if (status == "failed") != isinstance(collection.get("terminal_error"), str):
        raise ProductionError("collection terminal error contract is invalid")
    if status == "failed" and not collection["terminal_error"]:
        raise ProductionError("failed collection is missing its terminal error class")
    if status != "failed" and collection.get("terminal_error") is not None:
        raise ProductionError("non-failed collection contains a terminal error")


def _validate_raw_manifest(
    run_dir: Path,
    raw_manifest: Mapping[str, Any],
) -> tuple[list[str], dict[str, list[dict[str, Any]]]]:
    if set(raw_manifest) != {"schema_version", "responses"}:
        raise ProductionError("raw manifest contract is not exact")
    if raw_manifest.get("schema_version") != "FloridaSignalRawResponseManifestV1":
        raise ProductionError("raw manifest schema is not supported")
    responses = raw_manifest.get("responses")
    if not isinstance(responses, list) or len(responses) > MAX_RAW_RESPONSE_ENTRIES:
        raise ProductionError("raw manifest responses are missing or exceed their cap")
    raw_root = (run_dir / "raw").resolve()
    if (run_dir / "raw").is_symlink() or not raw_root.is_dir():
        raise ProductionError("raw evidence directory is missing or unsafe")
    manifest_raw_files: set[Path] = set()
    groups: dict[str, list[dict[str, Any]]] = {}
    group_order: list[str] = []
    previous_name: str | None = None
    for entry in responses:
        if not isinstance(entry, dict):
            raise ProductionError("raw manifest contains a non-object entry")
        object_path = entry.get("object_path")
        expected_keys = {
            "logical_name", "source_url", "request_params", "attempt", "observed_at",
            "http_status", "error_class", "elapsed_ms", "bytes", "sha256", "object_path",
        }
        if object_path is not None:
            expected_keys.add("truncated")
        if set(entry) != expected_keys:
            raise ProductionError("raw manifest response contract is not exact")
        logical_name = entry.get("logical_name")
        if not isinstance(logical_name, str) or re.fullmatch(
            r"(?:boundary-layer-metadata|boundary-fort-lauderdale|layer-metadata|"
            r"object-ids-start|object-ids-end|page-[0-9]{4})", logical_name
        ) is None:
            raise ProductionError("raw manifest logical response name is invalid")
        if logical_name != previous_name:
            if logical_name in groups:
                raise ProductionError("raw manifest response groups are not contiguous")
            group_order.append(logical_name)
            groups[logical_name] = []
            previous_name = logical_name
        groups[logical_name].append(entry)
        if len(groups[logical_name]) > MAX_RAW_RESPONSE_ATTEMPTS:
            raise ProductionError("raw response attempt count exceeds the collector cap")
        if (
            not isinstance(entry.get("request_params"), dict)
            or any(not isinstance(key, str) or not isinstance(value, str)
                   for key, value in entry["request_params"].items())
        ):
            raise ProductionError("raw manifest request parameters are invalid")
        if logical_name == "boundary-layer-metadata":
            expected_url = shadow.BOUNDARY_LAYER_URL
            expected_params = {"f": "json"}
        elif logical_name == "boundary-fort-lauderdale":
            expected_url = shadow.BOUNDARY_QUERY_URL
            expected_params = {
                "f": "geojson", "where": shadow.BOUNDARY_WHERE,
                "outFields": ",".join(shadow.BOUNDARY_FIELDS),
                "returnGeometry": "true", "outSR": str(shadow.OUTPUT_WKID),
                "orderByFields": "OBJECTID ASC",
            }
        elif logical_name == "layer-metadata":
            expected_url = shadow.LAYER_URL
            expected_params = {"f": "json"}
        elif logical_name in {"object-ids-start", "object-ids-end"}:
            expected_url = shadow.QUERY_URL
            expected_params = {"f": "json", "where": "1=1", "returnIdsOnly": "true"}
        else:
            expected_url = shadow.QUERY_URL
            expected_params = None
        if entry.get("source_url") != expected_url:
            raise ProductionError("raw manifest contains an unapproved source URL")
        if expected_params is not None and entry["request_params"] != dict(
            sorted(expected_params.items())
        ):
            raise ProductionError("raw manifest contains an unexpected source request")
        if expected_params is None:
            page_params = entry["request_params"]
            if (
                set(page_params) != {
                    "f", "where", "outFields", "returnGeometry", "returnZ", "returnM",
                    "outSR", "orderByFields", "resultOffset", "resultRecordCount",
                }
                or page_params["f"] != "json" or page_params["outFields"] != "*"
                or page_params["returnGeometry"] != "true"
                or page_params["returnZ"] != "false" or page_params["returnM"] != "false"
                or page_params["outSR"] != str(shadow.OUTPUT_WKID)
                or page_params["orderByFields"] != "OBJECTID ASC"
                or page_params["resultOffset"] != "0"
                or re.fullmatch(r"[1-9][0-9]{0,3}", page_params["resultRecordCount"]) is None
                or not 1 <= int(page_params["resultRecordCount"]) <= MAX_SOURCE_ROWS
                or re.fullmatch(
                    r"OBJECTID = [1-9][0-9]*|"
                    r"OBJECTID >= [1-9][0-9]* AND OBJECTID <= [1-9][0-9]*",
                    page_params["where"],
                ) is None
            ):
                raise ProductionError("raw feature-page request contract changed")
        _evidence_clock(entry.get("observed_at"), "raw response observation clock")
        attempt = entry.get("attempt")
        elapsed = entry.get("elapsed_ms")
        byte_count = entry.get("bytes")
        http_status = entry.get("http_status")
        error_class = entry.get("error_class")
        if (
            isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 0
            or isinstance(elapsed, bool) or not isinstance(elapsed, int)
            or not 0 <= elapsed <= 1_200_000
            or isinstance(byte_count, bool) or not isinstance(byte_count, int)
            or not 0 <= byte_count <= shadow.DEFAULT_MAX_RESPONSE_BYTES
            or (http_status is not None and (
                isinstance(http_status, bool) or not isinstance(http_status, int)
                or not 100 <= http_status <= 599
            ))
            or (error_class is not None and (
                not isinstance(error_class, str)
                or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,127}", error_class) is None
            ))
            or not isinstance(entry.get("sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None
        ):
            raise ProductionError("raw manifest response metadata is invalid")
        if len(groups[logical_name]) > 1:
            previous_clock = _evidence_clock(
                groups[logical_name][-2].get("observed_at"),
                "prior raw response observation clock",
            )
            current_clock = _evidence_clock(
                entry.get("observed_at"), "raw response observation clock"
            )
            if current_clock < previous_clock:
                raise ProductionError("raw response attempt clocks are not monotonic")
        if object_path is None:
            if (
                len(groups[logical_name]) != 1 or attempt != 0 or byte_count != 0
                or entry.get("sha256") != sha256_bytes(b"") or http_status is not None
                or error_class != "NO_RESPONSE" or elapsed != 0
            ):
                raise ProductionError("no-response evidence is internally inconsistent")
            continue
        if (
            attempt != len(groups[logical_name])
            or not isinstance(entry.get("truncated"), bool)
            or entry["truncated"] != (error_class == "ResponseTooLarge")
            or not isinstance(object_path, str)
        ):
            raise ProductionError("raw response attempt contract is invalid")
        candidate = run_dir / object_path
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise ProductionError("raw evidence object is missing") from exc
        expected_suffix = "json" if byte_count else "empty"
        expected_path = f"raw/{logical_name}.attempt-{attempt:02d}.{expected_suffix}"
        if (
            object_path != expected_path or resolved.parent != raw_root
            or candidate.is_symlink() or not resolved.is_file()
            or resolved in manifest_raw_files
        ):
            raise ProductionError("raw evidence object path or identity is invalid")
        manifest_raw_files.add(resolved)
        if resolved.stat().st_size != byte_count or sha256_file(resolved) != entry["sha256"]:
            raise ProductionError("raw evidence object hash or byte count mismatch")
    actual_raw_files = {path.resolve() for path in (run_dir / "raw").iterdir()}
    if actual_raw_files != manifest_raw_files:
        raise ProductionError("raw manifest does not enumerate the exact raw evidence set")
    for group_index, logical_name in enumerate(group_order):
        attempts = groups[logical_name]
        for attempt_index, entry in enumerate(attempts):
            error_class = entry["error_class"]
            status = entry["http_status"]
            successful_response = (
                error_class is None
                and isinstance(status, int)
                and 200 <= status < 300
            )
            retryable_response = (
                isinstance(status, int)
                and status in shadow.RETRYABLE_HTTP_STATUSES
                and error_class in {None, "HTTPError"}
            )
            retryable_transport = (
                error_class in {"URLError", "TimeoutError", "timeout"}
                and status is None
                and entry["bytes"] == 0
                and entry["sha256"] == sha256_bytes(b"")
            )
            is_final_attempt = attempt_index == len(attempts) - 1
            if error_class == "HTTPError" and (
                not isinstance(status, int) or 200 <= status < 300
            ):
                raise ProductionError("raw HTTP-error evidence is inconsistent")
            if error_class == "ResponseTooLarge" and (
                not isinstance(status, int) or not is_final_attempt
            ):
                raise ProductionError("oversize response evidence is inconsistent")
            if error_class not in {
                None, "HTTPError", "ResponseTooLarge", "URLError", "TimeoutError",
                "timeout", "NO_RESPONSE",
            }:
                raise ProductionError("raw response error class is not collector-generated")
            if not is_final_attempt and not (retryable_response or retryable_transport):
                raise ProductionError("raw response contains an impossible retry transition")
            if (
                is_final_attempt
                and group_index < len(group_order) - 1
                and not successful_response
            ):
                raise ProductionError("collector evidence continues after a failed request")
    fixed_prefix = [
        "boundary-layer-metadata", "boundary-fort-lauderdale", "layer-metadata",
        "object-ids-start",
    ]
    if group_order[:min(len(group_order), len(fixed_prefix))] != fixed_prefix[:len(group_order)]:
        raise ProductionError("raw response sequence is not a valid collector prefix")
    if len(group_order) > len(fixed_prefix):
        tail = group_order[len(fixed_prefix):]
        pages = tail[:-1] if tail[-1] == "object-ids-end" else tail
        if pages != [f"page-{index:04d}" for index in range(1, len(pages) + 1)]:
            raise ProductionError("raw feature-page response sequence is not exact")
    return group_order, groups


def _raw_json_response(
    run_dir: Path,
    groups: Mapping[str, Sequence[Mapping[str, Any]]],
    logical_name: str,
    *,
    source_url: str,
    request_params: Mapping[str, str],
) -> tuple[Any, Mapping[str, Any]]:
    attempts = groups.get(logical_name)
    if not attempts:
        raise ProductionError(f"raw evidence is missing {logical_name}")
    for entry in attempts:
        if entry.get("source_url") != source_url or entry.get("request_params") != dict(
            sorted(request_params.items())
        ):
            raise ProductionError(f"raw {logical_name} request contract changed")
    final = attempts[-1]
    if (
        final.get("object_path") is None
        or final.get("error_class") is not None
        or final.get("truncated") is not False
        or not isinstance(final.get("http_status"), int)
        or not 200 <= final["http_status"] < 300
    ):
        raise ProductionError(f"raw {logical_name} did not finish successfully")
    try:
        payload = json.loads((run_dir / str(final["object_path"])).read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProductionError(f"raw {logical_name} is not valid JSON") from exc
    return payload, final


def _replay_nonfailed_collection(
    *,
    run_dir: Path,
    collection: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    group_order: Sequence[str],
    groups: Mapping[str, Sequence[Mapping[str, Any]]],
    observed_hashes: Mapping[str, str],
    boundary_reference: Mapping[str, Any],
) -> None:
    pagination = collection["pagination"]
    page_size = pagination["page_size"]
    boundary_params = {
        "f": "geojson",
        "where": shadow.BOUNDARY_WHERE,
        "outFields": ",".join(shadow.BOUNDARY_FIELDS),
        "returnGeometry": "true",
        "outSR": str(shadow.OUTPUT_WKID),
        "orderByFields": "OBJECTID ASC",
    }
    try:
        boundary_metadata, _ = _raw_json_response(
            run_dir, groups, "boundary-layer-metadata",
            source_url=shadow.BOUNDARY_LAYER_URL, request_params={"f": "json"},
        )
        boundary_schema = shadow.validate_boundary_layer_metadata(boundary_metadata)
        boundary_payload, boundary_entry = _raw_json_response(
            run_dir, groups, "boundary-fort-lauderdale",
            source_url=shadow.BOUNDARY_QUERY_URL, request_params=boundary_params,
        )
        boundary_components, boundary_record = shadow.validate_boundary_feature(boundary_payload)
        layer_metadata, _ = _raw_json_response(
            run_dir, groups, "layer-metadata",
            source_url=shadow.LAYER_URL, request_params={"f": "json"},
        )
        source_schema = shadow.validate_layer_metadata(layer_metadata)
        ids_params = {"f": "json", "where": "1=1", "returnIdsOnly": "true"}
        start_payload, _ = _raw_json_response(
            run_dir, groups, "object-ids-start",
            source_url=shadow.QUERY_URL, request_params=ids_params,
        )
        start_ids = shadow.validate_object_ids(start_payload)
        if any(not 1 <= object_id <= MAX_SOURCE_OBJECT_ID for object_id in start_ids):
            raise ProductionError("source OBJECTID is outside the admitted positive-int domain")
        if len(start_ids) > MAX_SOURCE_ROWS:
            raise ProductionError("successful evidence exceeds the source row cap")
        chunks = [
            start_ids[index:index + page_size]
            for index in range(0, len(start_ids), page_size)
        ]
        features: list[dict[str, Any]] = []
        for page_number, object_ids in enumerate(chunks, start=1):
            page_where = (
                f"OBJECTID = {object_ids[0]}" if len(object_ids) == 1 else
                f"OBJECTID >= {object_ids[0]} AND OBJECTID <= {object_ids[-1]}"
            )
            page_params = {
                "f": "json", "where": page_where, "outFields": "*",
                "returnGeometry": "true", "returnZ": "false", "returnM": "false",
                "outSR": str(shadow.OUTPUT_WKID), "orderByFields": "OBJECTID ASC",
                "resultOffset": "0", "resultRecordCount": str(len(object_ids)),
            }
            page_payload, _ = _raw_json_response(
                run_dir, groups, f"page-{page_number:04d}",
                source_url=shadow.QUERY_URL, request_params=page_params,
            )
            features.extend(shadow.validate_page(page_payload, object_ids))
        end_payload, _ = _raw_json_response(
            run_dir, groups, "object-ids-end",
            source_url=shadow.QUERY_URL, request_params=ids_params,
        )
        end_ids = shadow.validate_object_ids(end_payload)
    except shadow.CollectorError as exc:
        raise ProductionError("non-failed evidence does not replay against the source contract") from exc
    if len(end_ids) > MAX_SOURCE_ROWS:
        raise ProductionError("successful evidence end identity set exceeds the source row cap")
    if any(not 1 <= object_id <= MAX_SOURCE_OBJECT_ID for object_id in end_ids):
        raise ProductionError("end OBJECTID is outside the admitted positive-int domain")
    expected_group_order = [
        "boundary-layer-metadata", "boundary-fort-lauderdale", "layer-metadata",
        "object-ids-start",
        *(f"page-{number:04d}" for number in range(1, len(chunks) + 1)),
        "object-ids-end",
    ]
    if list(group_order) != expected_group_order:
        raise ProductionError("non-failed raw response sequence is not exact")

    row_observation_values = {
        row.get("clocks", {}).get("observed_at")
        for row in rows if isinstance(row.get("clocks"), Mapping)
    }
    if len(row_observation_values) > 1:
        raise ProductionError("normalized rows disagree on their observation clock")
    normalized_at = (
        next(iter(row_observation_values)) if row_observation_values
        else collection["clocks"]["observed_at"]
    )
    normalized_clock = _evidence_clock(normalized_at, "normalized row observation clock")
    if not (
        _evidence_clock(collection["clocks"]["run_started_at"], "collection start clock")
        <= normalized_clock
        <= _evidence_clock(collection["clocks"]["observed_at"], "collection observation clock")
    ):
        raise ProductionError("normalized row observation clock is outside the collection")

    boundary_sha = str(boundary_entry["sha256"])
    boundary_schema_sha = sha256_bytes(canonical_bytes(boundary_schema))
    source_schema_sha = sha256_bytes(canonical_bytes(source_schema))
    expected_boundary_reference = {
        "schema_version": "FloridaSignalBoundaryReferenceV1",
        "source_url": shadow.BOUNDARY_LAYER_URL,
        "source_agency": "City of Fort Lauderdale",
        "layer_id": shadow.BOUNDARY_LAYER_ID,
        "layer_name": shadow.BOUNDARY_LAYER_NAME,
        "query_where": boundary_params["where"],
        "jurisdiction": "City of Fort Lauderdale",
        "spatial_reference_wkid": shadow.OUTPUT_WKID,
        "record": boundary_record,
        "boundary_sha256": boundary_sha,
        "source_schema_sha256": boundary_schema_sha,
    }
    if dict(boundary_reference) != expected_boundary_reference:
        raise ProductionError("boundary reference does not replay exactly")

    boundary_bboxes = [shadow.rings_bbox(component) for component in boundary_components]
    expected_rows: list[dict[str, Any]] = []
    rejection_reasons: dict[str, int] = {}
    app_status_observed: dict[str, int] = {}
    app_status_in_scope: dict[str, int] = {}
    expected_counts = {
        "rows_observed": len(features),
        "rows_shadow_included": 0,
        "rows_test_excluded": 0,
        "rows_outside_boundary": 0,
        "rows_rejected": 0,
        "duplicate_identities": 0,
        "pages_expected": len(chunks),
        "pages_succeeded": len(chunks),
    }
    seen_identities: set[str] = set()
    for feature in features:
        attributes = feature.get("attributes")
        if isinstance(attributes, Mapping):
            raw_status = attributes.get("AppStatus")
            status_key = "<NULL>" if raw_status is None else str(raw_status)
            app_status_observed[status_key] = app_status_observed.get(status_key, 0) + 1
        category, record, reason = shadow.normalize_feature(
            feature,
            observed_at=str(normalized_at),
            boundary_components=boundary_components,
            boundary_bboxes=boundary_bboxes,
            boundary_sha256=boundary_sha,
        )
        if category == "included" and record is not None:
            identity_key = record["identity_key"]
            if identity_key in seen_identities:
                expected_counts["duplicate_identities"] += 1
                expected_counts["rows_rejected"] += 1
                rejection_reasons["duplicate_business_identity"] = (
                    rejection_reasons.get("duplicate_business_identity", 0) + 1
                )
                continue
            seen_identities.add(identity_key)
            expected_rows.append(record)
            expected_counts["rows_shadow_included"] += 1
            status = record["source"].get("app_status")
            status_key = "<NULL>" if status is None else str(status)
            app_status_in_scope[status_key] = app_status_in_scope.get(status_key, 0) + 1
        elif category == "test_excluded":
            expected_counts["rows_test_excluded"] += 1
        elif category == "outside_boundary":
            expected_counts["rows_outside_boundary"] += 1
        else:
            expected_counts["rows_rejected"] += 1
            safe_reason = reason or "unknown_rejection"
            rejection_reasons[safe_reason] = rejection_reasons.get(safe_reason, 0) + 1
    expected_rows.sort(key=lambda row: row["source"]["object_id"])
    if list(rows) != expected_rows:
        raise ProductionError("normalized rows do not deterministically replay from raw evidence")

    identity_stable = start_ids == end_ids
    accounting_ok = expected_counts["rows_observed"] == sum(
        expected_counts[key] for key in (
            "rows_shadow_included", "rows_test_excluded", "rows_outside_boundary",
            "rows_rejected",
        )
    )
    source_count_parity = expected_counts["rows_observed"] == len(start_ids)
    expected_status = (
        "partial" if not identity_stable else
        "partial" if expected_counts["rows_rejected"] or not accounting_ok or not source_count_parity else
        "empty" if expected_counts["rows_observed"] == 0 else
        "ok"
    )
    expected_reason = (
        "SOURCE_OBJECT_ID_SET_CHANGED_DURING_RUN" if not identity_stable else
        "ROW_QUALITY_OR_ACCOUNTING_FAILURE" if expected_status == "partial" else
        None
    )
    maxima = {
        name: max(
            (row["event_clocks"][name] for row in expected_rows
             if row["event_clocks"].get(name)),
            default=None,
        )
        for name in shadow.EVENT_CLOCK_FIELDS
    }
    expected_receipt = {
        "schema_version": "FloridaSignalSfwmdPendingErpShadowReceiptV1",
        "run_id": collection["run_id"],
        "mode": "shadow_file_only",
        "dry_run": True,
        "status": expected_status,
        "reason_code": expected_reason,
        "terminal_error": None,
        "source": collection["source"],
        "versions": collection["versions"],
        "clocks": collection["clocks"],
        "event_clock_maxima": maxima,
        "event_through": maxima["app_received_at"],
        "event_through_semantics": collection["event_through_semantics"],
        "scope": {
            "jurisdiction": "City of Fort Lauderdale",
            "basis": "official_boundary_polygon_intersection",
            "mailing_city_used_for_scope": False,
            "boundary_source_url": shadow.BOUNDARY_LAYER_URL,
            "boundary_layer_id": shadow.BOUNDARY_LAYER_ID,
            "boundary_layer_name": shadow.BOUNDARY_LAYER_NAME,
            "boundary_record": boundary_record,
            "boundary_sha256": boundary_sha,
            "boundary_source_schema_sha256": boundary_schema_sha,
        },
        "counts": expected_counts,
        "app_status_counts_observed": dict(sorted(app_status_observed.items())),
        "app_status_counts_in_scope": dict(sorted(app_status_in_scope.items())),
        "app_status_policy": collection["app_status_policy"],
        "rejection_reasons": dict(sorted(rejection_reasons.items())),
        "pagination": {
            "method": "frozen_OBJECTID_set_range_pages_in_ASC_order",
            "page_size": page_size,
            "object_ids_start_count": len(start_ids),
            "object_ids_end_count": len(end_ids),
            "object_ids_stable": identity_stable,
            "object_ids_start_sha256": sha256_bytes(canonical_bytes(start_ids)),
            "object_ids_end_sha256": sha256_bytes(canonical_bytes(end_ids)),
        },
        "hashes": {
            "schema_contract_sha256": sha256_bytes(canonical_bytes(shadow.SCHEMA_CONTRACT)),
            "source_schema_sha256": source_schema_sha,
            "raw_manifest_sha256": observed_hashes["raw_manifest"],
            "shadow_records_sha256": observed_hashes["records"],
            "source_content_index_sha256": observed_hashes["content_index"],
            "boundary_reference_sha256": sha256_file(run_dir / "boundary-reference.json"),
        },
        "quality": {
            "accounting_identity_passed": accounting_ok,
            "source_count_parity_passed": source_count_parity,
            "business_identity_unique": expected_counts["duplicate_identities"] == 0,
            "source_object_id_set_stable": identity_stable,
            "all_pages_succeeded": True,
            "schema_contract_passed": True,
        },
        "safety": collection["safety"],
    }
    if dict(collection) != expected_receipt:
        raise ProductionError("collection receipt does not exactly reconcile deterministic replay")


def verify_evidence_bundle(
    run_dir: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, str]]:
    _require_absolute(run_dir, "evidence bundle")
    if not run_dir.is_dir() or run_dir.is_symlink():
        raise ProductionError("evidence bundle must be a real directory")
    collection = _load_json(run_dir / "receipt.json", "collection receipt")
    manifest = _load_json(run_dir / "bundle-manifest.json", "bundle manifest")
    _validate_collection_contract(collection)
    run_id_value = collection.get("run_id")
    run_id = run_id_value if isinstance(run_id_value, str) else ""
    if not RUN_ID_RE.fullmatch(run_id) or manifest.get("run_id") != run_id:
        raise ProductionError("evidence run identity is invalid")

    paths = {
        "records": run_dir / "shadow-records.jsonl",
        "content_index": run_dir / "shadow-content-index.jsonl",
        "raw_manifest": run_dir / "raw-manifest.json",
        "collection_receipt": run_dir / "receipt.json",
        "bundle_manifest": run_dir / "bundle-manifest.json",
    }
    if any(path.is_symlink() or not path.is_file() for path in paths.values()):
        raise ProductionError("evidence bundle has missing or unsafe required files")
    observed_hashes = {name: sha256_file(path) for name, path in paths.items()}
    declared_hashes = collection.get("hashes")
    if not isinstance(declared_hashes, Mapping):
        raise ProductionError("collection receipt hashes are missing")
    for name, key in (
        ("records", "shadow_records_sha256"),
        ("content_index", "source_content_index_sha256"),
        ("raw_manifest", "raw_manifest_sha256"),
    ):
        if declared_hashes.get(key) != observed_hashes[name]:
            raise ProductionError(f"evidence {name} hash mismatch")
    if manifest.get("receipt_sha256") != observed_hashes["collection_receipt"]:
        raise ProductionError("bundle manifest does not bind the collection receipt")
    if manifest.get("shadow_records_sha256") != observed_hashes["records"]:
        raise ProductionError("bundle manifest does not bind normalized records")
    if manifest.get("source_content_index_sha256") != observed_hashes["content_index"]:
        raise ProductionError("bundle manifest does not bind the content index")
    if manifest.get("raw_manifest_sha256") != observed_hashes["raw_manifest"]:
        raise ProductionError("bundle manifest does not bind the raw manifest")

    raw_manifest = _load_json(paths["raw_manifest"], "raw manifest")
    group_order, raw_groups = _validate_raw_manifest(run_dir, raw_manifest)

    rows: list[dict[str, Any]] = []
    canonical_rows: list[bytes] = []
    records_body = paths["records"].read_bytes()
    if len(records_body) > 128 * 1024 * 1024:
        raise ProductionError("normalized evidence exceeds its byte cap")
    for line_number, line in enumerate(records_body.splitlines(), 1):
        try:
            row = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProductionError(f"normalized JSONL is invalid at line {line_number}") from exc
        if not isinstance(row, dict):
            raise ProductionError("normalized JSONL contains a non-object row")
        identity = row.get("identity")
        source = row.get("source")
        if not isinstance(identity, Mapping) or not isinstance(source, Mapping):
            raise ProductionError("normalized row identity/source is missing")
        global_id = shadow.normalize_global_id(identity.get("global_id"))
        app_no = shadow.normalize_app_no(identity.get("app_no"))
        identity_key = f"{global_id}|{app_no}"
        if row.get("identity_key") != identity_key:
            raise ProductionError("normalized row identity key mismatch")
        object_id = source.get("object_id")
        if isinstance(object_id, bool) or not isinstance(object_id, int):
            raise ProductionError("normalized row OBJECTID is invalid")
        try:
            expected_content_hash = sha256_bytes(canonical_bytes(_content_projection(row)))
            canonical_row = canonical_bytes(row)
        except (TypeError, ValueError) as exc:
            raise ProductionError("normalized row contains a non-canonical JSON value") from exc
        if row.get("source_content_sha256") != expected_content_hash:
            raise ProductionError("normalized row source-content hash mismatch")
        if not 1 <= object_id <= MAX_SOURCE_OBJECT_ID:
            raise ProductionError("normalized row OBJECTID is outside the admitted domain")
        rows.append(row)
        canonical_rows.append(canonical_row)
    if records_body != b"".join(canonical_rows):
        raise ProductionError("normalized JSONL bytes are not canonical")

    identities = [str(row["identity_key"]) for row in rows]
    if len(identities) != len(set(identities)):
        raise ProductionError("evidence contains duplicate business identities")
    if len(rows) > MAX_IN_SCOPE_ROWS:
        raise ProductionError("in-scope SFWMD row count exceeds the production safety cap")
    counts = collection["counts"]
    rows_observed = _count_value(counts, "rows_observed", MAX_SOURCE_ROWS)
    if _count_value(counts, "rows_shadow_included", MAX_IN_SCOPE_ROWS) != len(rows):
        raise ProductionError("collection receipt does not reconcile in-scope rows")
    if rows_observed != sum(
        _count_value(counts, key, MAX_SOURCE_ROWS)
        for key in ("rows_shadow_included", "rows_test_excluded", "rows_outside_boundary", "rows_rejected")
    ):
        raise ProductionError("collection receipt accounting identity failed")
    status = str(collection["status"])
    declared_boundary_hash = manifest.get("boundary_reference_sha256")
    collection_boundary_hash = collection.get("hashes", {}).get("boundary_reference_sha256")
    boundary_reference: dict[str, Any] | None = None
    if declared_boundary_hash is not None or collection_boundary_hash is not None:
        boundary_path = run_dir / "boundary-reference.json"
        if boundary_path.is_symlink() or not boundary_path.is_file():
            raise ProductionError("collection is missing declared boundary evidence")
        boundary_hash = sha256_file(boundary_path)
        if collection_boundary_hash != boundary_hash or declared_boundary_hash != boundary_hash:
            raise ProductionError("collection does not consistently bind boundary evidence")
        boundary_reference = _load_json(boundary_path, "boundary reference")
    elif (run_dir / "boundary-reference.json").exists():
        raise ProductionError("undeclared boundary evidence is present")

    expected_manifest = {
        "schema_version": "FloridaSignalSfwmdShadowBundleManifestV1",
        "run_id": run_id,
        "receipt_sha256": observed_hashes["collection_receipt"],
        "raw_manifest_sha256": observed_hashes["raw_manifest"],
        "shadow_records_sha256": observed_hashes["records"],
        "source_content_index_sha256": observed_hashes["content_index"],
        "boundary_sha256": collection["scope"]["boundary_sha256"],
        "boundary_source_schema_sha256": collection["scope"]["boundary_source_schema_sha256"],
        "boundary_reference_sha256": collection_boundary_hash,
        "schema_contract_sha256": sha256_bytes(canonical_bytes(shadow.SCHEMA_CONTRACT)),
        "promotion_eligible": False,
    }
    if manifest != expected_manifest:
        raise ProductionError("bundle manifest contract does not exactly reconcile")

    if status != "failed":
        if boundary_reference is None:
            raise ProductionError("non-failed collection is missing boundary evidence")
        _replay_nonfailed_collection(
            run_dir=run_dir,
            collection=collection,
            rows=rows,
            group_order=group_order,
            groups=raw_groups,
            observed_hashes=observed_hashes,
            boundary_reference=boundary_reference,
        )
    elif (
        rows
        or rows_observed != 0
        or any(_count_value(counts, key) != 0 for key in (
            "rows_shadow_included", "rows_test_excluded", "rows_outside_boundary",
            "rows_rejected", "duplicate_identities",
        ))
        or collection["app_status_counts_observed"]
        or collection["app_status_counts_in_scope"]
        or collection["rejection_reasons"]
        or collection["event_through"] is not None
        or any(value is not None for value in collection["event_clock_maxima"].values())
    ):
        raise ProductionError("failed collection contains inadmissible normalized source claims")

    index = sorted(
        (
            {
                "identity_key": str(row["identity_key"]),
                "source_content_sha256": str(row["source_content_sha256"]),
            }
            for row in rows
        ),
        key=lambda value: value["identity_key"],
    )
    expected_index = b"".join(canonical_bytes(value) for value in index)
    if sha256_bytes(expected_index) != observed_hashes["content_index"]:
        raise ProductionError("content index does not reconcile normalized rows")
    return collection, rows, observed_hashes


def _open_database(path: Path) -> sqlite3.Connection:
    _require_absolute(path, "SQLite path")
    if path.is_symlink() or not path.is_file():
        raise ProductionError("canonical SQLite database is missing or unsafe")
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("pragma foreign_keys=on")
    connection.execute("pragma busy_timeout=30000")
    connection.execute("pragma synchronous=full")
    return connection


def _schema_object_manifest(connection: sqlite3.Connection) -> tuple[list[dict[str, str]], str]:
    rows = connection.execute(
        """
        select type,name,tbl_name,sql from sqlite_master
        where sql is not null and (
          lower(name) glob 'sfwmd_pending_erp_*'
          or lower(tbl_name) glob 'sfwmd_pending_erp_*'
        )
        order by type collate binary,name collate binary
        """
    ).fetchall()
    manifest = [
        {
            "type": str(row[0]),
            "name": str(row[1]),
            "table": str(row[2]),
            # sqlite_master is the installed authority. Preserve the exact SQL
            # text instead of lowercasing literals or collapsing whitespace:
            # case-only definition drift must not be normalized away.
            "sql": str(row[3]).strip(),
        }
        for row in rows
    ]
    return manifest, sha256_bytes(canonical_bytes(manifest))


def _migration_bytes() -> bytes:
    body = SCHEMA_SQL_PATH.read_bytes()
    observed = sha256_bytes(body)
    if observed != SQLITE_MIGRATION_SHA256:
        raise ProductionError("reviewed SFWMD SQLite migration SHA-256 does not match code")
    return body


def _sql_statements(body: str) -> list[str]:
    statements: list[str] = []
    pending = ""
    for line in body.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            statement = pending.strip()
            pending = ""
            if statement:
                statements.append(statement)
    if pending.strip():
        raise ProductionError("SFWMD SQLite migration ends with an incomplete statement")
    return statements


def check_schema(connection: sqlite3.Connection) -> None:
    manifest, observed_manifest_sha = _schema_object_manifest(connection)
    observed_objects = {(row["type"], row["name"]) for row in manifest}
    if observed_objects != SCHEMA_OBJECTS:
        raise ProductionError("SFWMD SQLite object set differs from the reviewed migration")
    if observed_manifest_sha != SQLITE_OBJECT_MANIFEST_SHA256:
        raise ProductionError("SFWMD SQLite object definitions differ from the reviewed migration")
    row = connection.execute(
        """
        select schema_version,migration_sha256,object_manifest_sha256
        from sfwmd_pending_erp_schema where singleton=1
        """
    ).fetchone()
    if row is None or tuple(row) != (
        SQLITE_SCHEMA_VERSION,
        SQLITE_MIGRATION_SHA256,
        SQLITE_OBJECT_MANIFEST_SHA256,
    ):
        raise ProductionError("SFWMD SQLite schema hashes or version are not exact")
    state_rows = connection.execute(
        "select count(*) from sfwmd_pending_erp_state where singleton=1"
    ).fetchone()
    if state_rows is None or state_rows[0] != 1:
        raise ProductionError("SFWMD SQLite monotonic state singleton is missing")


def install_schema(
    *,
    sqlite_path: Path,
    writer_lock_path: Path,
    clock: Callable[[], dt.datetime] = utc_now,
) -> dict[str, Any]:
    """Install the exact reviewed schema atomically; refuse partial/poisoned state."""
    migration = _migration_bytes().decode("utf-8")
    statements = _sql_statements(migration)
    with _open_writer_lock(writer_lock_path) as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        with _open_database(sqlite_path) as connection:
            existing = connection.execute(
                """
                select count(*) from sqlite_master
                where lower(name) glob 'sfwmd_pending_erp_*'
                   or lower(tbl_name) glob 'sfwmd_pending_erp_*'
                """
            ).fetchone()[0]
            if existing:
                try:
                    check_schema(connection)
                except ProductionError as exc:
                    raise ProductionError(
                        "refusing poisoned or partial SFWMD SQLite schema"
                    ) from exc
                return {
                    "status": "already_current",
                    "schema_version": SQLITE_SCHEMA_VERSION,
                    "migration_sha256": SQLITE_MIGRATION_SHA256,
                }
            connection.execute("begin immediate")
            try:
                for statement in statements:
                    connection.execute(statement)
                _, object_manifest_sha = _schema_object_manifest(connection)
                if object_manifest_sha != SQLITE_OBJECT_MANIFEST_SHA256:
                    raise ProductionError(
                        "installed SFWMD SQLite definitions differ from the reviewed manifest"
                    )
                connection.execute(
                    """
                    insert into sfwmd_pending_erp_schema (
                      singleton,schema_version,migration_sha256,
                      object_manifest_sha256,installed_at
                    ) values (1,?,?,?,?)
                    """,
                    (
                        SQLITE_SCHEMA_VERSION,
                        SQLITE_MIGRATION_SHA256,
                        object_manifest_sha,
                        shadow.iso_utc(clock()),
                    ),
                )
                check_schema(connection)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
    return {
        "status": "installed",
        "schema_version": SQLITE_SCHEMA_VERSION,
        "migration_sha256": SQLITE_MIGRATION_SHA256,
        "object_manifest_sha256": object_manifest_sha,
    }


def _record_projection(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return the private normalized mirror row; raw responses never leave disk."""
    identity = row["identity"]
    source = row["source"]
    record_canonical = canonical_bytes(row).decode("utf-8")
    source_content_canonical = canonical_bytes({
        "schema_version": "FloridaSignalSfwmdSourceContentV1",
        "attributes": {
            key: value for key, value in row["attributes"].items() if key != "OBJECTID"
        },
        "geometry": row["geometry"],
    }).decode("utf-8")
    return {
        "identity_key": row["identity_key"],
        "global_id": identity["global_id"],
        "app_no": identity["app_no"],
        "source_object_id": source["object_id"],
        "source_content_sha256": row["source_content_sha256"],
        "event_received_at": (row.get("event_clocks") or {}).get("app_received_at"),
        "record": row,
        "record_canonical": record_canonical,
        "record_sha256": sha256_bytes(record_canonical.encode("utf-8")),
        "source_content_canonical": source_content_canonical,
    }


def _ordered_rows_sha256(rows: Sequence[Mapping[str, Any]]) -> str:
    body = "".join(
        str(row["record_canonical"])
        for row in sorted(rows, key=lambda item: str(item["identity_key"]))
    ).encode("utf-8")
    return sha256_bytes(body)


def _validate_postgres_json_numeric_domain(value: Any) -> None:
    """Admit only numbers whose Python and PostgreSQL JSONB text is identical.

    PostgreSQL expands exponent notation and normalizes negative zero while
    Python's JSON encoder preserves those spellings. Rejecting those two
    forms, and bounding integers to signed bigint, makes the canonical string
    comparison in the private RPC portable and deterministic.
    """
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        if not -(2**63) <= value <= 2**63 - 1:
            raise ProductionError("pending mirror JSON integer exceeds its admitted domain")
        return
    if isinstance(value, float):
        encoded = canonical_bytes(value).decode("utf-8").strip()
        if "e" in encoded.lower() or (value == 0 and encoded.startswith("-")):
            raise ProductionError(
                "pending mirror JSON number is not PostgreSQL-canonical-compatible"
            )
        return
    if isinstance(value, Mapping):
        for nested in value.values():
            _validate_postgres_json_numeric_domain(nested)
        return
    if isinstance(value, (list, tuple)):
        for nested in value:
            _validate_postgres_json_numeric_domain(nested)
        return
    raise ProductionError("pending mirror record contains a non-JSON value")


def _validate_mirror_rows(rows: Sequence[Mapping[str, Any]]) -> str:
    """Validate the exact row contract and independently rebuild its index digest."""
    expected_keys = {
        "identity_key", "global_id", "app_no", "source_object_id",
        "source_content_sha256", "event_received_at", "record",
        "record_canonical", "record_sha256", "source_content_canonical",
    }
    identities: set[str] = set()
    index: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != expected_keys:
            raise ProductionError("pending mirror row contract is not exact")
        record = row.get("record")
        if not isinstance(record, Mapping):
            raise ProductionError("pending mirror row record is invalid")
        _validate_postgres_json_numeric_domain(record)
        canonical = canonical_bytes(record).decode("utf-8")
        attributes = record.get("attributes")
        if not isinstance(attributes, Mapping) or "geometry" not in record:
            raise ProductionError("pending mirror source-content basis is invalid")
        source_canonical = canonical_bytes({
            "schema_version": "FloridaSignalSfwmdSourceContentV1",
            "attributes": {
                key: value for key, value in attributes.items() if key != "OBJECTID"
            },
            "geometry": record["geometry"],
        }).decode("utf-8")
        identity = str(row.get("identity_key") or "")
        content_sha = str(row.get("source_content_sha256") or "")
        if (
            not identity or identity in identities
            or row.get("record_canonical") != canonical
            or row.get("record_sha256") != sha256_bytes(canonical.encode("utf-8"))
            or row.get("source_content_canonical") != source_canonical
            or content_sha != sha256_bytes(source_canonical.encode("utf-8"))
            or record.get("identity_key") != identity
            or record.get("source_content_sha256") != content_sha
            or not re.fullmatch(r"[0-9a-f]{64}", content_sha)
            or (record.get("identity") or {}).get("global_id") != row.get("global_id")
            or (record.get("identity") or {}).get("app_no") != row.get("app_no")
            or (record.get("source") or {}).get("object_id") != row.get("source_object_id")
            or (record.get("event_clocks") or {}).get("app_received_at")
                != row.get("event_received_at")
        ):
            raise ProductionError("pending mirror row hash or identity mismatch")
        identities.add(identity)
        index.append({"identity_key": identity, "source_content_sha256": content_sha})
    return sha256_bytes(b"".join(canonical_bytes(item) for item in sorted(
        index, key=lambda item: item["identity_key"]
    )))


def _database_payload_sha256(
    *,
    run_id: str,
    status: str,
    progress_status: str,
    observed_at: str,
    source_content_index_sha256: str,
    row_count: int,
    ordered_rows_sha256: str,
) -> str:
    basis = (
        "FloridaSignalSfwmdPostgresPayloadV1\n"
        f"{run_id}\n{status}\n{progress_status}\n{observed_at}\n"
        f"{source_content_index_sha256}\n{row_count}\n{ordered_rows_sha256}\n"
    ).encode("utf-8")
    return sha256_bytes(basis)


def _fixed_width_order_clock(value: str) -> str:
    if not isinstance(value, str) or UTC_CLOCK_RE.fullmatch(value) is None:
        raise ProductionError("monotonic order clock is not canonical UTC")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProductionError("monotonic order clock is invalid") from exc
    if parsed.utcoffset() != dt.timedelta(0):
        raise ProductionError("monotonic order clock is not UTC")
    return parsed.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _observation_order_key(observed_at: str, completed_at: str, run_id: str) -> str:
    return (
        f"{_fixed_width_order_clock(observed_at)}|"
        f"{_fixed_width_order_clock(completed_at)}|{run_id}"
    )


def _insert_run_receipt(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    receipt: Mapping[str, Any],
    receipt_sha256: str,
) -> None:
    counts = receipt["counts"]
    connection.execute(
        """
        insert into sfwmd_pending_erp_runs (
          run_id,status,progress_status,natural_run,started_at,observed_at,completed_at,
          event_through,rows_observed,rows_accepted,rows_inserted,rows_updated,
          rows_unchanged,rows_retired,rows_rejected,source_content_index_sha256,
          evidence_bundle_path,evidence_manifest_sha256,collection_receipt_sha256,
          provenance_sha256,observation_order_key,receipt_sha256,receipt_json,created_at
        ) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            run_id,
            receipt["status"],
            receipt["progress_status"],
            int(bool(receipt["natural_run"])),
            receipt["started_at"],
            receipt["observed_at"],
            receipt["completed_at"],
            receipt.get("event_through"),
            counts["rows_observed"],
            counts["rows_accepted"],
            counts["rows_inserted"],
            counts["rows_updated"],
            counts["rows_unchanged"],
            counts["rows_retired"],
            counts["rows_rejected"],
            receipt.get("source_content_index_sha256"),
            receipt["evidence"]["bundle_path"],
            receipt["evidence"]["bundle_manifest_sha256"],
            receipt["evidence"]["collection_receipt_sha256"],
            sha256_bytes(canonical_bytes(receipt["provenance"])),
            receipt["observation_order_key"],
            receipt_sha256,
            canonical_bytes(receipt).decode("utf-8"),
            receipt["completed_at"],
        ),
    )


def _write_latest_pointer(
    latest_pointer: Path,
    receipt_path: Path,
    receipt: Mapping[str, Any],
    receipt_sha256: str,
) -> None:
    atomic_write_json(
        latest_pointer,
        {
            "schema_version": LATEST_SCHEMA,
            "run_id": receipt["run_id"],
            "natural_run": True,
            "status": receipt["status"],
            "progress_status": receipt["progress_status"],
            "connection_state": "not_connected",
            "observation_order_key": receipt["observation_order_key"],
            "completed_at": receipt["completed_at"],
            "event_through": receipt["event_through"],
            "receipt_path": str(receipt_path),
            "receipt_sha256": receipt_sha256,
            "provenance_sha256": sha256_bytes(canonical_bytes(receipt["provenance"])),
            "counts": receipt["counts"],
        },
    )


def commit_bundle(
    *,
    sqlite_path: Path,
    writer_lock_path: Path,
    run_dir: Path,
    receipt_dir: Path,
    latest_pointer: Path,
    provenance: Mapping[str, Any],
    clock: Callable[[], dt.datetime] = utc_now,
) -> dict[str, Any]:
    _require_absolute(receipt_dir, "receipt directory")
    _require_absolute(latest_pointer, "latest pointer")
    if latest_pointer.parent != receipt_dir:
        raise ProductionError("latest pointer must live directly in the receipt directory")
    fsync_evidence_bundle(run_dir)
    collection, rows, evidence_hashes = verify_evidence_bundle(run_dir)
    run_id = str(collection["run_id"])
    verified_provenance = validate_provenance(provenance, run_id)
    natural_run = verified_provenance["natural_run"] is True
    if natural_run:
        try:
            scheduled_for = dt.datetime.fromisoformat(
                str(verified_provenance["scheduled_for"]).replace("Z", "+00:00")
            )
            collection_started = dt.datetime.fromisoformat(
                str(collection["clocks"]["run_started_at"]).replace("Z", "+00:00")
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProductionError("natural run provenance clocks are invalid") from exc
        if (
            scheduled_for.tzinfo is None or collection_started.tzinfo is None
            or not scheduled_for <= collection_started <= scheduled_for + dt.timedelta(
                minutes=TIMER_PROVENANCE_WINDOW_MINUTES
            )
        ):
            raise ProductionError("natural collection did not begin in its timer provenance window")
    completed_at = shadow.iso_utc(clock())
    collection_status = str(collection.get("status") or "failed")
    if collection_status not in {"ok", "empty", "partial", "failed"}:
        raise ProductionError("unsupported collection terminal status")
    collection_counts = collection["counts"]
    successful = collection_status in {"ok", "empty"}
    observed_at = str(collection["clocks"]["observed_at"])
    observation_order_key = _observation_order_key(observed_at, completed_at, run_id)
    with _open_writer_lock(writer_lock_path) as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        with _open_database(sqlite_path) as connection:
            check_schema(connection)
            connection.execute("begin immediate")
            try:
                existing = connection.execute(
                    "select receipt_json, receipt_sha256 from sfwmd_pending_erp_runs where run_id=?",
                    (run_id,),
                ).fetchone()
                if existing is not None:
                    stored = json.loads(existing["receipt_json"])
                    if stored.get("evidence", {}).get("collection_receipt_sha256") != evidence_hashes["collection_receipt"]:
                        raise ProductionError("idempotent run replay has different evidence")
                    if stored.get("provenance") != verified_provenance:
                        raise ProductionError("idempotent replay cannot change run provenance")
                    latest_state = connection.execute(
                        "select latest_natural_run_id from sfwmd_pending_erp_state where singleton=1"
                    ).fetchone()
                    connection.rollback()
                    receipt_path = receipt_dir / f"{run_id}.json"
                    file_sha = write_create_only_fsynced(receipt_path, stored)
                    if file_sha != existing["receipt_sha256"]:
                        raise ProductionError("stored terminal receipt hash mismatch")
                    if natural_run and latest_state and latest_state[0] == run_id:
                        _write_latest_pointer(latest_pointer, receipt_path, stored, file_sha)
                    return {**stored, "idempotent_replay": True, "receipt_path": str(receipt_path)}

                state = connection.execute(
                    """
                    select latest_snapshot_order_key,latest_natural_order_key
                    from sfwmd_pending_erp_state where singleton=1
                    """
                ).fetchone()
                if state is None:
                    raise ProductionError("SFWMD monotonic state row is missing")
                snapshot_advances = bool(
                    natural_run
                    and successful
                    and (state["latest_snapshot_order_key"] is None
                         or observation_order_key > state["latest_snapshot_order_key"])
                )
                natural_latest_advances = bool(
                    natural_run
                    and (state["latest_natural_order_key"] is None
                         or observation_order_key > state["latest_natural_order_key"])
                )
                existing_rows = {}
                if snapshot_advances:
                    existing_rows = {
                        str(row["identity_key"]): row
                        for row in connection.execute(
                            "select identity_key,source_content_sha256,is_current from sfwmd_pending_erp_records"
                        )
                    }
                inserts = updates = unchanged = retired = 0
                if snapshot_advances:
                    for row in rows:
                        prior = existing_rows.get(str(row["identity_key"]))
                        if prior is None:
                            inserts += 1
                        elif prior["source_content_sha256"] != row["source_content_sha256"] or not prior["is_current"]:
                            updates += 1
                        else:
                            unchanged += 1
                    observed_identities = {str(row["identity_key"]) for row in rows}
                    retired = sum(
                        1
                        for identity, prior in existing_rows.items()
                        if prior["is_current"] and identity not in observed_identities
                    )

                accepted = len(rows) if snapshot_advances else 0
                progress_status = (
                    "canary"
                    if not natural_run
                    else "uncommitted"
                    if not successful
                    else "superseded"
                    if not snapshot_advances
                    else "changed"
                    if inserts or updates or retired
                    else "empty"
                    if not rows
                    else "unchanged"
                )
                mirror_rows = [_record_projection(row) for row in rows]
                ordered_rows_sha = _ordered_rows_sha256(mirror_rows)
                source_index_sha = str(collection["hashes"]["source_content_index_sha256"])
                database_payload_sha = _database_payload_sha256(
                    run_id=run_id,
                    status=collection_status,
                    progress_status=progress_status,
                    observed_at=observed_at,
                    source_content_index_sha256=source_index_sha,
                    row_count=len(mirror_rows),
                    ordered_rows_sha256=ordered_rows_sha,
                )
                receipt = {
                    "schema_version": RECEIPT_SCHEMA,
                    "run_id": run_id,
                    "natural_run": natural_run,
                    "provenance": verified_provenance,
                    "observation_order_key": observation_order_key,
                    "status": collection_status,
                    "reason_code": collection.get("reason_code"),
                    "progress_status": progress_status,
                    "connection_state": "not_connected",
                    "started_at": collection["clocks"]["run_started_at"],
                    "observed_at": observed_at,
                    "completed_at": completed_at,
                    "source_checked_at": collection["clocks"]["source_checked_at"],
                    "source_modified_at": None,
                    "source_modified_status": "UNKNOWN_NOT_EXPOSED",
                    "event_through": collection.get("event_through"),
                    "event_through_semantics": collection.get("event_through_semantics"),
                    "counts": {
                        "rows_observed": int(collection_counts["rows_observed"]),
                        "rows_accepted": accepted,
                        "rows_inserted": inserts if successful else 0,
                        "rows_updated": updates if successful else 0,
                        "rows_unchanged": unchanged if successful else 0,
                        "rows_retired": retired if successful else 0,
                        "rows_rejected": int(collection_counts["rows_rejected"]),
                    },
                    "source_content_index_sha256": source_index_sha,
                    "versions": {
                        "production_collector": COLLECTOR_VERSION,
                        **collection["versions"],
                        "sqlite_schema": SQLITE_SCHEMA_VERSION,
                        "sqlite_migration_sha256": SQLITE_MIGRATION_SHA256,
                    },
                    "evidence": {
                        "bundle_path": str(run_dir),
                        "bundle_manifest_sha256": evidence_hashes["bundle_manifest"],
                        "collection_receipt_sha256": evidence_hashes["collection_receipt"],
                        "raw_manifest_sha256": evidence_hashes["raw_manifest"],
                        "normalized_records_sha256": evidence_hashes["records"],
                    },
                    "mirror": {
                        "eligible": natural_run,
                        "state": "pending" if natural_run else "ineligible_canary",
                        "idempotency": "run_id_plus_database_computed_payload_sha256",
                        "digest_basis": "FloridaSignalSfwmdPostgresPayloadV1",
                        "row_count": len(mirror_rows),
                        "ordered_rows_sha256": ordered_rows_sha,
                        "database_payload_sha256": database_payload_sha,
                    },
                    "safety": {
                        "bounded_current_pending_snapshot_only": True,
                        "unrestricted_backfill": False,
                        "scoring": False,
                        "candidate_or_queue_write": False,
                        "publication": False,
                        "connected_label_allowed": False,
                    },
                }
                receipt_sha = sha256_bytes(canonical_bytes(receipt))
                _insert_run_receipt(
                    connection,
                    run_id=run_id,
                    receipt=receipt,
                    receipt_sha256=receipt_sha,
                )

                if snapshot_advances:
                    for row in rows:
                        projection = _record_projection(row)
                        record_json = canonical_bytes(projection["record"]).decode("utf-8")
                        connection.execute(
                            """
                            insert into sfwmd_pending_erp_versions (
                              identity_key,source_content_sha256,record_json,first_observed_at,first_run_id
                            ) values (?,?,?,?,?) on conflict do nothing
                            """,
                            (
                                projection["identity_key"],
                                projection["source_content_sha256"],
                                record_json,
                                receipt["observed_at"],
                                run_id,
                            ),
                        )
                        connection.execute(
                            """
                            insert into sfwmd_pending_erp_records (
                              identity_key,global_id,app_no,source_object_id,source_content_sha256,
                              record_json,event_received_at,first_seen_at,last_seen_at,last_changed_at,
                              is_current,retired_at,last_run_id
                            ) values (?,?,?,?,?,?,?,?,?,?,1,null,?)
                            on conflict(identity_key) do update set
                              global_id=excluded.global_id,
                              app_no=excluded.app_no,
                              source_object_id=excluded.source_object_id,
                              source_content_sha256=excluded.source_content_sha256,
                              record_json=excluded.record_json,
                              event_received_at=excluded.event_received_at,
                              last_seen_at=excluded.last_seen_at,
                              last_changed_at=case
                                when sfwmd_pending_erp_records.source_content_sha256 <> excluded.source_content_sha256
                                  or sfwmd_pending_erp_records.is_current = 0
                                then excluded.last_changed_at
                                else sfwmd_pending_erp_records.last_changed_at
                              end,
                              is_current=1,
                              retired_at=null,
                              last_run_id=excluded.last_run_id
                            """,
                            (
                                projection["identity_key"],
                                projection["global_id"],
                                projection["app_no"],
                                projection["source_object_id"],
                                projection["source_content_sha256"],
                                record_json,
                                projection["event_received_at"],
                                receipt["observed_at"],
                                receipt["observed_at"],
                                receipt["observed_at"],
                                run_id,
                            ),
                        )
                    identities = [str(row["identity_key"]) for row in rows]
                    if identities:
                        placeholders = ",".join("?" for _ in identities)
                        connection.execute(
                            f"""
                            update sfwmd_pending_erp_records
                            set is_current=0,retired_at=?,last_run_id=?
                            where is_current=1 and identity_key not in ({placeholders})
                            """,
                            (receipt["observed_at"], run_id, *identities),
                        )
                    else:
                        connection.execute(
                            """
                            update sfwmd_pending_erp_records
                            set is_current=0,retired_at=?,last_run_id=? where is_current=1
                            """,
                            (receipt["observed_at"], run_id),
                        )

                if natural_run:
                    payload = {
                        "schema_version": MIRROR_PAYLOAD_SCHEMA,
                        "run_id": run_id,
                        "receipt": receipt,
                        "rows": mirror_rows,
                    }
                    connection.execute(
                        """
                        insert into sfwmd_pending_erp_mirror_outbox (
                          run_id,payload_sha256,payload_json,state,attempts
                        ) values (?,?,?,'pending',0)
                        """,
                        (
                            run_id,
                            database_payload_sha,
                            canonical_bytes(payload).decode("utf-8"),
                        ),
                    )
                if snapshot_advances:
                    connection.execute(
                        """
                        update sfwmd_pending_erp_state
                        set latest_snapshot_order_key=?,latest_snapshot_run_id=?,updated_at=?
                        where singleton=1
                        """,
                        (observation_order_key, run_id, completed_at),
                    )
                if natural_latest_advances:
                    connection.execute(
                        """
                        update sfwmd_pending_erp_state
                        set latest_natural_order_key=?,latest_natural_run_id=?,updated_at=?
                        where singleton=1
                        """,
                        (observation_order_key, run_id, completed_at),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

        receipt_path = receipt_dir / f"{run_id}.json"
        file_sha = write_create_only_fsynced(receipt_path, receipt)
        if file_sha != receipt_sha:
            raise ProductionError("terminal file receipt does not match atomic SQLite receipt")
        if natural_latest_advances:
            _write_latest_pointer(latest_pointer, receipt_path, receipt, receipt_sha)
        return {
            **receipt,
            "idempotent_replay": False,
            "latest_pointer_advanced": natural_latest_advances,
            "receipt_path": str(receipt_path),
        }


def repair_receipt_file(
    *,
    sqlite_path: Path,
    writer_lock_path: Path,
    run_dir: Path,
    receipt_dir: Path,
    latest_pointer: Path,
) -> dict[str, Any]:
    """Recreate only a missing exact file receipt from its immutable DB row."""
    _require_absolute(receipt_dir, "receipt directory")
    _require_absolute(latest_pointer, "latest pointer")
    if latest_pointer.parent != receipt_dir:
        raise ProductionError("latest pointer must live directly in the receipt directory")
    fsync_evidence_bundle(run_dir)
    collection, _, evidence_hashes = verify_evidence_bundle(run_dir)
    run_id = str(collection["run_id"])
    with _open_writer_lock(writer_lock_path) as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        with _open_database(sqlite_path) as connection:
            check_schema(connection)
            stored_row = connection.execute(
                "select receipt_json,receipt_sha256 from sfwmd_pending_erp_runs where run_id=?",
                (run_id,),
            ).fetchone()
            latest = connection.execute(
                "select latest_natural_run_id from sfwmd_pending_erp_state where singleton=1"
            ).fetchone()
        if stored_row is None:
            raise ProductionError("repair requires an existing immutable SQLite run receipt")
        receipt = json.loads(stored_row["receipt_json"])
        if receipt.get("evidence", {}).get("collection_receipt_sha256") != evidence_hashes["collection_receipt"]:
            raise ProductionError("repair evidence does not match the immutable SQLite receipt")
        receipt_path = receipt_dir / f"{run_id}.json"
        receipt_sha = write_create_only_fsynced(receipt_path, receipt)
        if receipt_sha != stored_row["receipt_sha256"]:
            raise ProductionError("repaired receipt hash does not match SQLite")
        latest_advanced = bool(
            receipt.get("natural_run") is True and latest and latest[0] == run_id
        )
        if latest_advanced:
            _write_latest_pointer(latest_pointer, receipt_path, receipt, receipt_sha)
    return {
        "status": "repaired",
        "run_id": run_id,
        "natural_run": bool(receipt.get("natural_run")),
        "connection_state": "not_connected",
        "latest_pointer_advanced": latest_advanced,
        "receipt_path": str(receipt_path),
    }


class SupabaseMirrorTransport:
    """Bounded RPC client; credentials stay process-only and never enter receipts."""

    class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            del request, fp, code, msg, headers, newurl
            return None

    def __init__(
        self,
        base_url: str,
        service_key: str,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.service_key = service_key
        if not re.fullmatch(r"https://[A-Za-z0-9.-]+\.supabase\.co", self.base_url):
            raise ProductionError("SUPABASE_URL is missing or outside the approved HTTPS host form")
        if not service_key:
            raise ProductionError("SUPABASE_SERVICE_ROLE_KEY is required for the gated mirror")
        self.opener = opener or urllib.request.build_opener(self._NoRedirectHandler()).open

    def commit(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        request_body = {
            "p_run_id": payload["run_id"],
            "p_payload_sha256": payload["receipt"]["mirror"]["database_payload_sha256"],
            "p_receipt": payload["receipt"],
            "p_rows": payload["rows"],
        }
        request = urllib.request.Request(
            f"{self.base_url}/rest/v1/rpc/fs_commit_sfwmd_pending_erp_run",
            method="POST",
            data=canonical_bytes(request_body),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "apikey": self.service_key,
                "Authorization": f"Bearer {self.service_key}",
                "User-Agent": COLLECTOR_VERSION,
            },
        )
        try:
            with self.opener(request, timeout=MIRROR_TIMEOUT_SECONDS) as response:
                body = response.read(MAX_MIRROR_RESPONSE_BYTES + 1)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProductionError(f"SFWMD mirror request failed: {type(exc).__name__}") from exc
        if len(body) > MAX_MIRROR_RESPONSE_BYTES:
            raise ProductionError("SFWMD mirror response exceeded the byte cap")
        try:
            result = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ProductionError("SFWMD mirror returned invalid JSON") from exc
        if not isinstance(result, Mapping):
            raise ProductionError("SFWMD mirror readback is not an object")
        return result


def flush_one_mirror(
    *,
    sqlite_path: Path,
    writer_lock_path: Path,
    transport: MirrorTransport,
    clock: Callable[[], dt.datetime] = utc_now,
) -> dict[str, Any]:
    with _open_database(sqlite_path) as connection:
        check_schema(connection)
        pending = connection.execute(
            """
            select o.run_id,o.payload_sha256,o.payload_json,
                   r.receipt_json,r.receipt_sha256
            from sfwmd_pending_erp_mirror_outbox o
            join sfwmd_pending_erp_runs r on r.run_id=o.run_id
            where o.state='pending' order by o.rowid limit 1
            """
        ).fetchone()
    if pending is None:
        return {"status": "empty", "mirrored": 0}
    payload = json.loads(pending["payload_json"])
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "run_id", "receipt", "rows"}
        or payload.get("schema_version") != MIRROR_PAYLOAD_SCHEMA
        or payload.get("run_id") != pending["run_id"]
        or not isinstance(payload.get("receipt"), dict)
        or not isinstance(payload.get("rows"), list)
        or canonical_bytes(payload).decode("utf-8") != pending["payload_json"]
    ):
        raise ProductionError("pending mirror payload contract is invalid")
    receipt = payload["receipt"]
    rows = payload["rows"]
    try:
        canonical_receipt = json.loads(pending["receipt_json"])
    except json.JSONDecodeError as exc:
        raise ProductionError("immutable SQLite run receipt is invalid JSON") from exc
    canonical_receipt_body = canonical_bytes(canonical_receipt)
    if (
        canonical_receipt_body.decode("utf-8") != pending["receipt_json"]
        or sha256_bytes(canonical_receipt_body) != pending["receipt_sha256"]
        or receipt != canonical_receipt
        or pending["payload_sha256"]
            != canonical_receipt.get("mirror", {}).get("database_payload_sha256")
    ):
        raise ProductionError("pending mirror is not anchored to its immutable run receipt")
    computed_index_sha = _validate_mirror_rows(rows)
    computed_rows_sha = _ordered_rows_sha256(rows)
    computed_payload_sha = _database_payload_sha256(
        run_id=pending["run_id"],
        status=str(receipt.get("status")),
        progress_status=str(receipt.get("progress_status")),
        observed_at=str(receipt.get("observed_at")),
        source_content_index_sha256=str(receipt.get("source_content_index_sha256")),
        row_count=len(rows),
        ordered_rows_sha256=computed_rows_sha,
    )
    if (
        computed_payload_sha != pending["payload_sha256"]
        or receipt.get("source_content_index_sha256") != computed_index_sha
        or receipt.get("mirror", {}).get("database_payload_sha256") != computed_payload_sha
        or receipt.get("mirror", {}).get("ordered_rows_sha256") != computed_rows_sha
        or receipt.get("mirror", {}).get("row_count") != len(rows)
    ):
        raise ProductionError("pending mirror payload hash mismatch")
    result = transport.commit(payload)
    if set(result) != {"run_id", "payload_sha256", "status", "idempotent_replay"}:
        raise ProductionError("mirror readback has an unexpected contract")
    if str(result.get("run_id")) != pending["run_id"]:
        raise ProductionError("mirror readback run id mismatch")
    if result.get("payload_sha256") != pending["payload_sha256"]:
        raise ProductionError("mirror readback payload hash mismatch")
    if result.get("status") != payload["receipt"]["status"]:
        raise ProductionError("mirror readback terminal status mismatch")
    if not isinstance(result.get("idempotent_replay"), bool):
        raise ProductionError("mirror readback replay flag is invalid")
    attempted_at = shadow.iso_utc(clock())
    with _open_writer_lock(writer_lock_path) as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        with _open_database(sqlite_path) as connection:
            check_schema(connection)
            connection.execute("begin immediate")
            cursor = connection.execute(
                """
                update sfwmd_pending_erp_mirror_outbox
                set state='sent',attempts=attempts+1,last_attempt_at=?,sent_at=?,remote_receipt_json=?
                where run_id=? and state='pending' and payload_sha256=?
                """,
                (
                    attempted_at,
                    attempted_at,
                    canonical_bytes(dict(result)).decode("utf-8"),
                    pending["run_id"],
                    pending["payload_sha256"],
                ),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise ProductionError("mirror outbox compare-and-set failed")
            connection.commit()
    return {"status": "sent", "mirrored": 1, "run_id": pending["run_id"]}


def write_early_failure(
    *,
    failure_ledger_dir: Path,
    run_id: str,
    stage: str,
    started_at: str,
    error: BaseException,
    provenance: Mapping[str, Any] | None,
    evidence_bundle_path: Path | None,
    canonical_receipt_committed: bool,
    failed_unit: str | None,
    clock: Callable[[], dt.datetime] = utc_now,
) -> dict[str, Any]:
    """Persist a secret-free terminal failure when canonical admission cannot."""
    _require_absolute(failure_ledger_dir, "early failure ledger")
    if not RUN_ID_RE.fullmatch(run_id) or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", stage) is None:
        raise ProductionError("early failure identity or stage is invalid")
    if failed_unit is not None and ALERT_UNIT_RE.fullmatch(failed_unit) is None:
        raise ProductionError("early failure systemd unit is invalid")
    failed_at = shadow.iso_utc(clock())
    failure_order_key = f"{_fixed_width_order_clock(failed_at)}|{run_id}|{stage}"
    receipt = {
        "schema_version": EARLY_FAILURE_SCHEMA,
        "run_id": run_id,
        "status": "failed",
        "stage": stage,
        "failed_unit": failed_unit,
        "failure_order_key": failure_order_key,
        "natural_run": bool(provenance and provenance.get("natural_run") is True),
        "provenance": dict(provenance) if provenance is not None else None,
        "started_at": started_at,
        "failed_at": failed_at,
        "error_class": type(error).__name__,
        "evidence_bundle_path": str(evidence_bundle_path) if evidence_bundle_path else None,
        "canonical_receipt_committed": canonical_receipt_committed,
        "alert_required": True,
        "safety": {
            "source_state_mutation_claimed": False,
            "scoring": False,
            "publication": False,
        },
    }
    receipt_path = failure_ledger_dir / f"{run_id}.{stage}.failure.json"
    lock_path = failure_ledger_dir / ".ledger.lock"
    with _open_writer_lock(lock_path) as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        if receipt_path.exists():
            if receipt_path.is_symlink() or not receipt_path.is_file():
                raise ProductionError("early failure receipt is unsafe")
            body = receipt_path.read_bytes()
            try:
                stored = json.loads(body)
            except json.JSONDecodeError as exc:
                raise ProductionError("early failure receipt is invalid JSON") from exc
            if (
                not isinstance(stored, dict)
                or body != canonical_bytes(stored)
                or stored.get("schema_version") != EARLY_FAILURE_SCHEMA
                or stored.get("run_id") != run_id
                or stored.get("stage") != stage
                or stored.get("failed_unit") != failed_unit
                or stored.get("started_at") != started_at
            ):
                raise ProductionError("existing early failure receipt conflicts with this run")
            receipt = stored
            failure_order_key = str(stored.get("failure_order_key") or "")
            receipt_sha = sha256_bytes(body)
        else:
            receipt_sha = write_create_only_fsynced(receipt_path, receipt)
        pointer = {
            "schema_version": "FloridaSignalSfwmdEarlyFailureLatestV1",
            "run_id": run_id,
            "failed_at": receipt["failed_at"],
            "stage": stage,
            "failed_unit": failed_unit,
            "failure_order_key": failure_order_key,
            "receipt_path": str(receipt_path),
            "receipt_sha256": receipt_sha,
            "alert_required": True,
        }
        pointer_paths = [failure_ledger_dir / "latest.json"]
        if failed_unit is not None:
            pointer_paths.append(failure_ledger_dir / f"{failed_unit}.latest.json")
        for pointer_path in pointer_paths:
            should_advance = True
            if pointer_path.exists():
                if pointer_path.is_symlink() or not pointer_path.is_file():
                    raise ProductionError("existing early failure pointer is unsafe")
                pointer_body = pointer_path.read_bytes()
                if len(pointer_body) > 128_000:
                    raise ProductionError("existing early failure pointer exceeds its cap")
                try:
                    existing_pointer = json.loads(pointer_body)
                except json.JSONDecodeError as exc:
                    raise ProductionError(
                        "existing early failure pointer is invalid JSON"
                    ) from exc
                if (
                    not isinstance(existing_pointer, dict)
                    or pointer_body != canonical_bytes(existing_pointer)
                    or set(existing_pointer) != set(pointer)
                    or existing_pointer.get("schema_version")
                        != "FloridaSignalSfwmdEarlyFailureLatestV1"
                    or not isinstance(existing_pointer.get("failure_order_key"), str)
                ):
                    raise ProductionError("existing early failure pointer is not exact")
                should_advance = failure_order_key > existing_pointer["failure_order_key"]
            if should_advance:
                atomic_write_json(pointer_path, pointer)
    return {**receipt, "receipt_path": str(receipt_path), "receipt_sha256": receipt_sha}


def failure_unit_for_provenance(provenance: Mapping[str, Any]) -> str | None:
    if provenance.get("invocation_kind") == "manual_service":
        return MANUAL_SERVICE_UNIT
    if provenance.get("invocation_kind") == "systemd_timer":
        return TIMER_SERVICE_UNIT
    return None


def scheduled_run(
    *,
    sqlite_path: Path,
    writer_lock_path: Path,
    evidence_dir: Path,
    receipt_dir: Path,
    latest_pointer: Path,
    failure_ledger_dir: Path,
    invocation_kind: str = "direct",
    run_id: str | None = None,
    provenance: Mapping[str, Any] | None = None,
    page_size: int = shadow.MAX_RECORD_COUNT,
    clock: Callable[[], dt.datetime] = utc_now,
    transport: shadow.Transport | None = None,
) -> dict[str, Any]:
    if os.environ.get("FLORIDA_SIGNAL_SFWMD_ENABLED") != "1":
        return {
            "status": "disabled",
            "connection_state": "not_connected",
            "natural_run_created": False,
        }
    run_id = run_id or str(uuid.uuid4())
    run_provenance: dict[str, Any] | None = None
    started_at: str | None = None
    run_dir: Path | None = None
    stage = "collection_initialization"
    canonical_receipt_committed = False
    failed_unit_hint: str | None = None
    if invocation_kind == "manual_service":
        failed_unit_hint = MANUAL_SERVICE_UNIT
    if isinstance(provenance, Mapping) and provenance.get("invocation_kind") == "systemd_timer":
        failed_unit_hint = TIMER_SERVICE_UNIT
    try:
        if not RUN_ID_RE.fullmatch(run_id):
            raise ProductionError("scheduled run id is invalid")
        started_at = shadow.iso_utc(clock())
        run_provenance = validate_provenance(
            provenance or manual_provenance(invocation_kind), run_id
        )
        failed_unit_hint = failure_unit_for_provenance(run_provenance)
        source_transport = transport or shadow.NetworkTransport()
        run_dir, _ = shadow.run_collection(
            output_root=_require_absolute(evidence_dir, "evidence directory"),
            transport=source_transport,
            page_size=page_size,
            run_id=run_id,
            clock=clock,
        )
        stage = "canonical_commit"
        receipt = commit_bundle(
            sqlite_path=sqlite_path,
            writer_lock_path=writer_lock_path,
            run_dir=run_dir,
            receipt_dir=receipt_dir,
            latest_pointer=latest_pointer,
            provenance=run_provenance,
            clock=clock,
        )
        canonical_receipt_committed = True
        stage = "mirror_delivery"
        mirror_result: dict[str, Any] = {"status": "disabled", "mirrored": 0}
        if (
            run_provenance["natural_run"] is True
            and os.environ.get("FLORIDA_SIGNAL_SFWMD_MIRROR_ENABLED") == "1"
        ):
            mirror_result = flush_one_mirror(
                sqlite_path=sqlite_path,
                writer_lock_path=writer_lock_path,
                transport=SupabaseMirrorTransport(
                    os.environ.get("SUPABASE_URL", ""),
                    os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
                ),
                clock=clock,
            )
    except Exception as exc:
        # Persist unexpected pre-receipt failures too. BaseException subclasses
        # (operator interrupt/system exit) remain outside this contract.
        failure_started_at = started_at or shadow.iso_utc(utc_now())
        if not canonical_receipt_committed and stage == "canonical_commit":
            try:
                with _open_database(sqlite_path) as connection:
                    check_schema(connection)
                    canonical_receipt_committed = connection.execute(
                        "select 1 from sfwmd_pending_erp_runs where run_id=?",
                        (run_id,),
                    ).fetchone() is not None
            except (ProductionError, OSError, sqlite3.Error):
                canonical_receipt_committed = False
        write_early_failure(
            failure_ledger_dir=failure_ledger_dir,
            run_id=run_id,
            stage=stage,
            started_at=failure_started_at,
            error=exc,
            provenance=run_provenance,
            evidence_bundle_path=run_dir,
            canonical_receipt_committed=canonical_receipt_committed,
            failed_unit=failed_unit_hint,
            clock=clock,
        )
        raise
    if receipt["status"] in {"partial", "failed"}:
        write_early_failure(
            failure_ledger_dir=failure_ledger_dir,
            run_id=run_id,
            stage="canonical_terminal",
            started_at=started_at,
            error=ProductionError(
                f"canonical collection terminal status: {receipt['status']}"
            ),
            provenance=run_provenance,
            evidence_bundle_path=run_dir,
            canonical_receipt_committed=True,
            failed_unit=failure_unit_for_provenance(run_provenance),
            clock=clock,
        )
    return {
        "status": receipt["status"],
        "progress_status": receipt["progress_status"],
        "run_id": receipt["run_id"],
        "connection_state": "not_connected",
        "natural_run": receipt["natural_run"],
        "receipt_path": receipt["receipt_path"],
        "mirror": mirror_result,
    }


def timer_run(
    *,
    canary_dir: Path,
    systemd_invocation_id: str,
    runtime_probe: Callable[[], Mapping[str, Any]] = systemd_timer_runtime_context,
    clock: Callable[[], dt.datetime] = utc_now,
    **scheduled_args: Any,
) -> dict[str, Any]:
    """Run the RefuseManualStart timer service with a journal-correlatable canary."""
    if os.environ.get("FLORIDA_SIGNAL_SFWMD_ENABLED") != "1":
        return {
            "status": "disabled",
            "connection_state": "not_connected",
            "natural_run_created": False,
        }
    run_id = str(uuid.uuid4())
    failure_dir = scheduled_args["failure_ledger_dir"]
    started_at = shadow.iso_utc(clock())
    try:
        runtime_context = runtime_probe()
    except (ProductionError, OSError):
        # A direct process invocation or a manual systemctl invocation does not
        # inherit timer trigger metadata and cannot claim a natural run. It is
        # still useful as an explicit canary, with no current/latest mutation.
        return scheduled_run(
            run_id=run_id,
            invocation_kind="direct",
            provenance=manual_provenance("direct"),
            clock=clock,
            **scheduled_args,
        )
    try:
        provenance = create_timer_provenance(
            canary_dir=canary_dir,
            run_id=run_id,
            systemd_invocation_id=systemd_invocation_id,
            runtime_context=runtime_context,
            clock=clock,
        )
    except Exception as exc:
        write_early_failure(
            failure_ledger_dir=failure_dir,
            run_id=run_id,
            stage="timer_provenance",
            started_at=started_at,
            error=exc,
            provenance=None,
            evidence_bundle_path=None,
            canonical_receipt_committed=False,
            failed_unit=TIMER_SERVICE_UNIT,
            clock=clock,
        )
        raise
    return scheduled_run(
        run_id=run_id,
        provenance=provenance,
        clock=clock,
        **scheduled_args,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    for command in (
        "scheduled-run", "timer-run", "mirror-one", "schema-check",
        "install-schema", "repair-receipt",
    ):
        child = subcommands.add_parser(command)
        child.add_argument("--sqlite-path", required=True, type=Path)
        if command in {"scheduled-run", "timer-run", "mirror-one", "install-schema", "repair-receipt"}:
            child.add_argument("--writer-lock-path", required=True, type=Path)
        if command in {"scheduled-run", "timer-run"}:
            child.add_argument("--evidence-dir", required=True, type=Path)
            child.add_argument("--receipt-dir", required=True, type=Path)
            child.add_argument("--latest-pointer", required=True, type=Path)
            child.add_argument("--failure-ledger-dir", required=True, type=Path)
            child.add_argument("--page-size", type=int, default=shadow.MAX_RECORD_COUNT)
            if command == "scheduled-run":
                child.add_argument(
                    "--invocation-kind",
                    choices=("direct", "manual_service"),
                    default="direct",
                )
            else:
                child.add_argument("--canary-dir", required=True, type=Path)
        elif command == "repair-receipt":
            child.add_argument("--run-dir", required=True, type=Path)
            child.add_argument("--receipt-dir", required=True, type=Path)
            child.add_argument("--latest-pointer", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "install-schema":
            result = install_schema(
                sqlite_path=args.sqlite_path,
                writer_lock_path=args.writer_lock_path,
            )
        elif args.command == "schema-check":
            with _open_database(args.sqlite_path) as connection:
                check_schema(connection)
            result = {"status": "ok", "schema_version": SQLITE_SCHEMA_VERSION}
        elif args.command == "repair-receipt":
            result = repair_receipt_file(
                sqlite_path=args.sqlite_path,
                writer_lock_path=args.writer_lock_path,
                run_dir=args.run_dir,
                receipt_dir=args.receipt_dir,
                latest_pointer=args.latest_pointer,
            )
        elif args.command == "mirror-one":
            if os.environ.get("FLORIDA_SIGNAL_SFWMD_MIRROR_ENABLED") != "1":
                result = {"status": "disabled", "mirrored": 0}
            else:
                result = flush_one_mirror(
                    sqlite_path=args.sqlite_path,
                    writer_lock_path=args.writer_lock_path,
                    transport=SupabaseMirrorTransport(
                        os.environ.get("SUPABASE_URL", ""),
                        os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
                    ),
                )
        elif args.command == "timer-run":
            result = timer_run(
                sqlite_path=args.sqlite_path,
                writer_lock_path=args.writer_lock_path,
                evidence_dir=args.evidence_dir,
                receipt_dir=args.receipt_dir,
                latest_pointer=args.latest_pointer,
                failure_ledger_dir=args.failure_ledger_dir,
                canary_dir=args.canary_dir,
                systemd_invocation_id=os.environ.get("INVOCATION_ID", ""),
                page_size=args.page_size,
            )
        else:
            result = scheduled_run(
                sqlite_path=args.sqlite_path,
                writer_lock_path=args.writer_lock_path,
                evidence_dir=args.evidence_dir,
                receipt_dir=args.receipt_dir,
                latest_pointer=args.latest_pointer,
                failure_ledger_dir=args.failure_ledger_dir,
                invocation_kind=args.invocation_kind,
                page_size=args.page_size,
            )
    except (ProductionError, shadow.CollectorError, OSError, sqlite3.Error) as exc:
        print(
            json.dumps(
                {"status": "failed", "error_class": type(exc).__name__},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 65
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("status") in {
        "ok", "empty", "disabled", "sent", "repaired", "installed", "already_current",
    } else 65


if __name__ == "__main__":
    raise SystemExit(main())
