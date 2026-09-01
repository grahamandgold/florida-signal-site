#!/usr/bin/env python3
"""Verify the Fort Lauderdale utility/engineering intake lane.

The existing Accela intake remains the only source transport.  This process
builds the reviewed exact-family projection from the canonical SQLite
authority, proves complete row parity against the RLS-backed read-only
Supabase ``permits`` mirror, writes an immutable local terminal receipt, and
atomically updates a hash-bound local latest pointer used by the private Desk.
It performs no remote write.
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
import subprocess
import sys
from typing import Any, Mapping, Protocol, Sequence
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import utility_intake_shadow as shadow  # noqa: E402


VERIFICATION_SCHEMA = "FloridaSignalUtilityIntakeProductionVerificationV1"
RECEIPT_SCHEMA = "FloridaSignalUtilityIntakeProductionReceiptV2"
LATEST_SCHEMA = "FloridaSignalUtilityIntakeProductionLatestV1"
COLLECTOR_VERSION = "ftl-utility-intake-production/1.0.0"
HEALTH_COMPONENT = "utility-intake"
PARITY_PROJECTION_VERSION = "utility-intake-permits-mirror/1"
READ_ONLY_TRANSPORT_SCHEMA = "FloridaSignalUtilityIntakeReadOnlyMirrorV1"
REMOTE_PAGE_SIZE = 1000
REMOTE_ROW_CAP = 5000
REMOTE_SCAN_CAP = 10000
MAX_RESPONSE_BYTES = 8_000_000
REQUEST_TIMEOUT_SECONDS = 25
DEPENDENCY_TIMEOUT_SECONDS = 620

PARITY_COLUMNS = (
    "permit_number",
    "report_source",
    "permit_type",
    "status",
    "applied_date",
    "issued_date",
    "opened_date",
    "finalized_date",
    "address",
    "parcel_id",
    "owner_name",
    "contractor_name",
    "description",
    "first_seen_at",
    "last_seen_at",
    "last_updated_at",
)


class ProductionError(RuntimeError):
    """A production evidence or parity contract failed closed."""


class DependencyWaitError(ProductionError):
    """A bounded prerequisite wait could not reach a safe terminal state."""


class CredentialFileError(ProductionError):
    """The dedicated host secret file failed its metadata boundary."""


class ScopedTransport(Protocol):
    def read_projection_page(self, *, cursor: str | None, limit: int) -> object: ...


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Keep the publishable key pinned to the configured project origin."""

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    return shadow.iso_utc(value)


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(shadow.canonical_json_bytes(value)).hexdigest()


def parity_projection_contract() -> dict[str, object]:
    projection = {
        "version": PARITY_PROJECTION_VERSION,
        "columns": list(PARITY_COLUMNS),
    }
    return {**projection, "sha256": canonical_sha256(projection)}


def validate_credential_file(path: Path | None) -> None:
    """Enforce the production secret-file boundary inside the receipting process."""
    if path is None:
        return
    if not path.is_absolute():
        raise CredentialFileError("credential file path must be absolute")
    try:
        file_stat = path.lstat()
    except OSError as error:
        raise CredentialFileError("dedicated utility credential file is unavailable") from error
    if path.is_symlink() or not stat.S_ISREG(file_stat.st_mode):
        raise CredentialFileError("dedicated utility credential file is unsafe")
    if (
        stat.S_IMODE(file_stat.st_mode) != 0o600
        or file_stat.st_uid != 0
        or file_stat.st_gid != 0
    ):
        raise CredentialFileError("dedicated utility credential file must be root:root mode 0600")


def wait_for_dependencies(command: Path | None) -> None:
    """Run the reviewed bounded waiter inside Python so failures are receipted."""
    if command is None:
        return
    if not command.is_absolute():
        raise DependencyWaitError("dependency wait command must be absolute")
    try:
        command_stat = command.lstat()
    except OSError as error:
        raise DependencyWaitError("dependency wait command is unavailable") from error
    if command.is_symlink() or not stat.S_ISREG(command_stat.st_mode):
        raise DependencyWaitError("dependency wait command is unsafe")
    if not os.access(command, os.X_OK):
        raise DependencyWaitError("dependency wait command is not executable")
    try:
        result = subprocess.run(
            [str(command)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=DEPENDENCY_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise DependencyWaitError("dependency wait execution failed") from error
    if result.returncode != 0:
        raise DependencyWaitError("dependency wait did not complete successfully")


def _safe_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value)


def _require_real_directory(path: Path, *, create: bool) -> None:
    if create:
        path.mkdir(parents=True, exist_ok=True)
    try:
        metadata = path.lstat()
    except OSError as error:
        raise ProductionError("evidence directory is unavailable") from error
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise ProductionError("evidence directory is unsafe")


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise ProductionError("evidence directory is not a directory")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_json(path: Path, value: object) -> str:
    if not path.is_absolute():
        raise ProductionError("latest pointer path must be absolute")
    _require_real_directory(path.parent, create=True)
    if path.is_symlink():
        raise ProductionError("refusing symlink latest pointer")
    body = shadow.canonical_json_bytes(value)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(temporary, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ProductionError("latest pointer temporary is not regular")
        view = memoryview(body)
        offset = 0
        while offset < len(body):
            written = os.write(fd, view[offset:])
            if written <= 0:
                raise OSError("latest-pointer write made no forward progress")
            offset += written
        os.fsync(fd)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        finally:
            raise
    finally:
        os.close(fd)
    try:
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    os.chmod(path, 0o600)
    _fsync_directory(path.parent)
    return hashlib.sha256(body).hexdigest()


def _write_private_create_only_fsynced(path: Path, body: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ProductionError("receipt path is not a regular file")
        view = memoryview(body)
        offset = 0
        while offset < len(body):
            written = os.write(fd, view[offset:])
            if written <= 0:
                raise OSError("receipt write made no forward progress")
            offset += written
        os.fsync(fd)
    except Exception:
        try:
            os.close(fd)
        finally:
            path.unlink(missing_ok=True)
        raise
    os.close(fd)


def _write_terminal(receipt_dir: Path, filename: str, receipt: object) -> tuple[Path, str]:
    if not receipt_dir.is_absolute():
        raise ProductionError("receipt directory must be absolute")
    _require_real_directory(receipt_dir, create=True)
    os.chmod(receipt_dir, 0o700)
    if Path(filename).name != filename:
        raise ProductionError("receipt filename must not contain path components")
    path = receipt_dir / filename
    body = shadow.canonical_json_bytes(receipt)
    _write_private_create_only_fsynced(path, body)
    _fsync_directory(receipt_dir)
    return path, hashlib.sha256(body).hexdigest()


class ReadOnlySupabaseTransport:
    """GET-only client pinned to the exact public/RLS-backed mirror projection."""

    def __init__(self, url: str, publishable_key: str) -> None:
        parsed = urllib.parse.urlsplit(url.rstrip("/"))
        if (
            parsed.scheme != "https"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
            or not parsed.hostname
            or not re.fullmatch(r"[a-z0-9-]+\.supabase\.co", parsed.hostname)
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ProductionError("SUPABASE_URL must be a pinned project origin")
        if not self._is_publishable_key(publishable_key):
            raise ProductionError("SUPABASE_ANON_KEY must be publishable or carry the anon role")
        self.url = f"{parsed.scheme}://{parsed.hostname}"
        self.publishable_key = publishable_key

    @staticmethod
    def _is_publishable_key(value: str) -> bool:
        if re.fullmatch(r"sb_publishable_[A-Za-z0-9_-]{16,512}", value):
            return True
        pieces = value.split(".")
        if len(pieces) != 3 or any(not piece for piece in pieces):
            return False
        try:
            import base64

            padding = "=" * (-len(pieces[1]) % 4)
            payload = json.loads(base64.urlsafe_b64decode(pieces[1] + padding))
        except (ValueError, json.JSONDecodeError):
            return False
        return isinstance(payload, dict) and payload.get("role") == "anon"

    def _get_rows(self, query: str) -> tuple[list[object], int]:
        headers = {
            "Accept": "application/json",
            "apikey": self.publishable_key,
            "Prefer": "count=exact",
            "User-Agent": COLLECTOR_VERSION,
        }
        request = urllib.request.Request(
            f"{self.url}/rest/v1/permits?{query}",
            method="GET",
            headers=headers,
        )
        try:
            opener = urllib.request.build_opener(_RejectRedirects())
            with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                length = response.headers.get("Content-Length")
                if length and int(length) > MAX_RESPONSE_BYTES:
                    raise ProductionError("Supabase response exceeded the byte cap")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise ProductionError("Supabase response exceeded the byte cap")
                content_range = str(response.headers.get("Content-Range") or "").strip()
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise ProductionError(f"read-only mirror request failed: {type(error).__name__}") from error
        try:
            payload = json.loads(raw or b"null")
        except json.JSONDecodeError as error:
            raise ProductionError("read-only mirror returned non-JSON data") from error
        if not isinstance(payload, list):
            raise ProductionError("read-only mirror response is not a row list")
        count_match = re.fullmatch(r"(?:\d+-\d+|\*)/(\d+)", content_range)
        if count_match is None:
            raise ProductionError("read-only mirror omitted its exact declared count")
        declared_total = int(count_match.group(1))
        if declared_total < len(payload):
            raise ProductionError("read-only mirror declared count is below its page size")
        return payload, declared_total

    def read_projection_page(self, *, cursor: str | None, limit: int) -> object:
        if not 1 <= limit <= REMOTE_PAGE_SIZE:
            raise ProductionError("read-only mirror page size is outside its bound")
        query_values = {
            "select": ",".join(PARITY_COLUMNS),
            "or": "(" + ",".join(
                f"permit_number.like.{family}-*" for family in shadow.FAMILY_IDS
            ) + ")",
            "order": "permit_number.asc",
            "limit": str(limit),
        }
        if cursor is not None:
            if not cursor or len(cursor) > 128 or re.search(r"[^A-Za-z0-9.-]", cursor):
                raise ProductionError("read-only mirror cursor is unsafe")
            query_values["permit_number"] = f"gt.{cursor}"
        raw_rows, declared_total = self._get_rows(urllib.parse.urlencode(query_values))
        if len(raw_rows) > limit:
            raise ProductionError("read-only mirror page exceeded its requested limit")
        prior = cursor
        exact_rows: list[dict[str, object]] = []
        for row in raw_rows:
            if not isinstance(row, dict) or set(row) != set(PARITY_COLUMNS):
                raise ProductionError("read-only mirror row crossed the declared projection")
            identity = str(row.get("permit_number") or "")
            if not identity or (prior is not None and identity <= prior):
                raise ProductionError("read-only mirror page is not strictly ordered")
            prior = identity
            if shadow.classify_record_number(identity) is not None:
                exact_rows.append(row)
        next_cursor = str(raw_rows[-1]["permit_number"]) if raw_rows else cursor
        return {
            "schema_version": READ_ONLY_TRANSPORT_SCHEMA,
            "projection": parity_projection_contract(),
            "cursor": cursor,
            "next_cursor": next_cursor,
            "scanned_count": len(raw_rows),
            "declared_total": declared_total,
            "exhausted": not raw_rows,
            "rows": exact_rows,
        }


def _projection_from_shadow(run_dir: Path) -> list[dict[str, str | None]]:
    path = run_dir / "shadow-records.jsonl"
    rows: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ProductionError(f"invalid shadow JSONL at line {line_number}") from error
        identity = str((record.get("identity") or {}).get("permit_number") or "")
        if not identity or shadow.classify_record_number(identity) is None:
            raise ProductionError("shadow bundle contains a non-contract identity")
        if identity in seen:
            raise ProductionError("shadow bundle contains a duplicate identity")
        seen.add(identity)
        source = record.get("source")
        if not isinstance(source, dict):
            raise ProductionError("shadow bundle lacks its source projection")
        missing = [column for column in PARITY_COLUMNS if column not in source]
        if missing:
            raise ProductionError(f"SQLite utility projection lacks columns: {missing}")
        rows.append({column: _safe_text(source.get(column)) for column in PARITY_COLUMNS})
    rows.sort(key=lambda row: str(row["permit_number"]))
    return rows


def _remote_projection_once(transport: ScopedTransport) -> list[dict[str, str | None]]:
    rows: list[dict[str, str | None]] = []
    cursor: str | None = None
    scanned_total = 0
    initial_declared_total: int | None = None
    expected_remaining: int | None = None
    while True:
        payload = transport.read_projection_page(cursor=cursor, limit=REMOTE_PAGE_SIZE)
        if not isinstance(payload, dict) or set(payload) != {
            "schema_version", "projection", "cursor", "next_cursor",
            "scanned_count", "declared_total", "exhausted", "rows",
        }:
            raise ProductionError("read-only mirror projection response has the wrong shape")
        if payload.get("schema_version") != READ_ONLY_TRANSPORT_SCHEMA:
            raise ProductionError("read-only mirror projection schema mismatch")
        if payload.get("projection") != parity_projection_contract():
            raise ProductionError("read-only mirror projection contract mismatch")
        if payload.get("cursor") != cursor:
            raise ProductionError("read-only mirror projection cursor binding mismatch")
        page_rows = payload.get("rows")
        scanned_count = payload.get("scanned_count")
        declared_total = payload.get("declared_total")
        exhausted = payload.get("exhausted")
        next_cursor = payload.get("next_cursor")
        if (
            not isinstance(page_rows, list)
            or type(scanned_count) is not int
            or type(declared_total) is not int
        ):
            raise ProductionError("read-only mirror projection page metadata is malformed")
        if (
            scanned_count < 0
            or scanned_count > REMOTE_PAGE_SIZE
            or len(page_rows) > scanned_count
            or declared_total < scanned_count
            or declared_total > REMOTE_SCAN_CAP
        ):
            raise ProductionError("read-only mirror projection page exceeds its bounds")
        if initial_declared_total is None:
            initial_declared_total = declared_total
            expected_remaining = declared_total
        if declared_total != expected_remaining:
            raise ProductionError("read-only mirror declared count changed during pagination")
        if exhausted is True:
            if (
                scanned_count != 0
                or declared_total != 0
                or page_rows
                or next_cursor != cursor
                or scanned_total != initial_declared_total
            ):
                raise ProductionError("read-only mirror terminal page is not explicitly empty")
            break
        if exhausted is not False or scanned_count == 0 or not isinstance(next_cursor, str):
            raise ProductionError("read-only mirror projection did not make bounded progress")
        if not next_cursor or (cursor is not None and next_cursor <= cursor):
            raise ProductionError("read-only mirror projection cursor did not advance")
        scanned_total += scanned_count
        if scanned_total > REMOTE_SCAN_CAP:
            raise ProductionError("read-only mirror projection scan exceeded the safety cap")
        if len(rows) + len(page_rows) > REMOTE_ROW_CAP:
            raise ProductionError("Supabase utility projection exceeded the safety cap")
        for raw in page_rows:
            if not isinstance(raw, dict):
                raise ProductionError("read-only mirror projection contains a non-object row")
            if set(raw) != set(PARITY_COLUMNS):
                raise ProductionError("read-only mirror projection exposed undeclared columns")
            identity = str(raw.get("permit_number") or "")
            if shadow.classify_record_number(identity) is None:
                raise ProductionError("read-only mirror projection crossed the exact family boundary")
            if (cursor is not None and identity <= cursor) or identity > next_cursor:
                raise ProductionError("read-only mirror projection row is outside its cursor page")
            rows.append({column: _safe_text(raw.get(column)) for column in PARITY_COLUMNS})
        expected_remaining = declared_total - scanned_count
        cursor = next_cursor
    rows.sort(key=lambda row: str(row["permit_number"]))
    identities = [str(row["permit_number"]) for row in rows]
    if len(identities) != len(set(identities)):
        raise ProductionError("Supabase utility projection contains duplicate identities")
    return rows


def _remote_projection(transport: ScopedTransport) -> list[dict[str, str | None]]:
    first = _remote_projection_once(transport)
    second = _remote_projection_once(transport)
    if rowset_proof(first) != rowset_proof(second):
        raise ProductionError("Supabase utility projection changed across stability reads")
    return second


def rowset_proof(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    ordered = sorted(rows, key=lambda row: str(row.get("permit_number") or ""))
    keys = [str(row.get("permit_number") or "") for row in ordered]
    if any(not key for key in keys) or len(keys) != len(set(keys)):
        raise ProductionError("rowset proof requires unique nonblank identities")
    return {
        "projection": parity_projection_contract(),
        "count": len(ordered),
        "primary_key_set_sha256": canonical_sha256(keys),
        "declared_projection_rowset_sha256": canonical_sha256(ordered),
    }


def prove_parity(
    local_rows: Sequence[Mapping[str, object]],
    remote_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    local = rowset_proof(local_rows)
    remote = rowset_proof(remote_rows)
    return {"status": "passed" if local == remote else "failed", "sqlite": local, "supabase": remote}


def _event_through(rows: Sequence[Mapping[str, object]]) -> str | None:
    candidates = []
    for row in rows:
        value = str(row.get("applied_date") or "")[:10]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            candidates.append(value)
    return max(candidates, default=None)


def run_production(
    *,
    sqlite_path: Path,
    writer_lock_path: Path,
    evidence_dir: Path,
    receipt_dir: Path,
    latest_pointer: Path,
    transport: ScopedTransport,
    run_id: str | None = None,
    clock=now_utc,
) -> dict[str, object]:
    started_at = iso_utc(clock())
    run_id = run_id or f"utility-intake-{started_at.replace(':', '').replace('-', '')}-{uuid4().hex}"
    shadow_run_dir: Path | None = None
    shadow_receipt: dict[str, Any] | None = None
    parity: dict[str, object] | None = None
    local_rows: list[dict[str, str | None]] = []
    remote_rows: list[dict[str, str | None]] = []
    verification_error: Exception | None = None
    try:
        shadow_run_dir, shadow_receipt = shadow.run_collection(
            sqlite_path=sqlite_path,
            output_root=evidence_dir,
            writer_lock_path=writer_lock_path,
            run_id=run_id,
            clock=clock,
        )
        if shadow_receipt.get("status") != "ok":
            raise ProductionError(
                f"shadow evidence is not admissible: {shadow_receipt.get('status')}"
            )
        local_rows = _projection_from_shadow(shadow_run_dir)
        if not local_rows:
            raise ProductionError("utility intake source set is unexpectedly empty")
        remote_rows = _remote_projection(transport)
        parity = prove_parity(local_rows, remote_rows)
        if parity["status"] != "passed":
            raise ProductionError("SQLite/Supabase utility projection parity failed")
    except Exception as caught:
        verification_error = caught

    finished_at = iso_utc(clock())
    counts = {
        "records_attempted": len(local_rows),
        "records_written": 0,
        "records_rejected": int(
            ((shadow_receipt or {}).get("counts") or {}).get("rows_rejected", 0)
        ),
        "sqlite_records": len(local_rows),
        "supabase_records": len(remote_rows),
    }
    verification = {
        "schema_version": VERIFICATION_SCHEMA,
        "run_id": run_id,
        "status": "verified" if verification_error is None else "failed",
        "reason_code": (
            None if verification_error is None else "UTILITY_INTAKE_VERIFICATION_FAILED"
        ),
        "reason_detail": (
            None
            if verification_error is None
            else f"{type(verification_error).__name__}: {str(verification_error)[:1000]}"
        ),
        "started_at": started_at,
        "completed_at": finished_at,
        "source": {
            "agency": "City of Fort Lauderdale",
            "system": "LauderBuild / Accela canonical permits lane",
            "collection_method": "derived exact-family projection; no second source transport",
            "families": list(shadow.FAMILY_IDS),
            "serving_utility": "UNKNOWN_NOT_IN_SOURCE_ROW",
            "broward_wws_searched": False,
        },
        "counts": counts,
        "parity": parity,
        "evidence": {
            "shadow_run_dir": str(shadow_run_dir) if shadow_run_dir else None,
            "shadow_receipt_sha256": (
                canonical_sha256(shadow_receipt) if shadow_receipt is not None else None
            ),
        },
        "versions": {
            "collector": COLLECTOR_VERSION,
            "query": shadow.QUERY_VERSION,
            "parser": shadow.PARSER_VERSION,
        },
        "safety": {
            "source_network_requests": 0,
            "supabase_mirror_requests": "GET-only exact projection",
            "supabase_mirror_pagination": (
                "keyset through explicit empty; exact declared count reconciled; "
                f"raw scan cap {REMOTE_SCAN_CAP}"
            ),
            "sqlite_writes": 0,
            "supabase_source_row_writes": 0,
            "supabase_health_pointer_upsert": False,
            "scoring": False,
            "candidate_promotion": False,
            "publication": False,
        },
    }
    verification_path, verification_sha256 = _write_terminal(
        receipt_dir,
        f"{run_id}.verification.json",
        verification,
    )

    health_status = "current" if verification_error is None else "error"
    metrics: dict[str, object] = {
        "rows_attempted": counts["records_attempted"],
        "rows_written": 0,
        "rows_rejected": counts["records_rejected"],
        "sqlite_rows": counts["sqlite_records"],
        "supabase_rows": counts["supabase_records"],
        "collector_version": COLLECTOR_VERSION,
        "shadow_collector_version": shadow.COLLECTOR_VERSION,
        "verification_receipt_path": str(verification_path),
        "verification_receipt_sha256": verification_sha256,
        "remote_exact_count_reconciled": verification_error is None,
    }
    if parity is not None:
        metrics.update(
            {
                "sqlite_pk_set_sha256": parity["sqlite"]["primary_key_set_sha256"],
                "supabase_pk_set_sha256": parity["supabase"]["primary_key_set_sha256"],
                "sqlite_projection_rowset_sha256": parity["sqlite"]["declared_projection_rowset_sha256"],
                "supabase_projection_rowset_sha256": parity["supabase"]["declared_projection_rowset_sha256"],
                "parity_projection_version": PARITY_PROJECTION_VERSION,
                "parity_projection_sha256": parity_projection_contract()["sha256"],
                "remote_stability_reads": 2,
            }
        )
    health_row = {
        "component": HEALTH_COMPONENT,
        "status": health_status,
        "event_through": _event_through(local_rows),
        "source_through": _event_through(local_rows),
        "system_time": finished_at,
        "detail": (
            f"{len(local_rows)} exact ENG-CR/ENG-OAA/ROW-SEW/ROW-WTR/"
            "PLB-SEWCP-WT records; complete declared 16-column SQLite/Supabase "
            "projection parity passed across two stable read-only mirror reads"
            if verification_error is None
            else (
                "Utility/engineering intake verification failed: "
                f"{type(verification_error).__name__}"
            )
        ),
        "metrics": metrics,
    }

    terminal_error = verification_error
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "run_id": run_id,
        "status": "ok" if terminal_error is None else "failed",
        "reason_code": (
            None
            if terminal_error is None
            else "UTILITY_INTAKE_VERIFICATION_FAILED"
        ),
        "reason_detail": (
            None
            if terminal_error is None
            else f"{type(terminal_error).__name__}: {str(terminal_error)[:1000]}"
        ),
        "started_at": started_at,
        "completed_at": finished_at,
        "counts": counts,
        "parity": parity,
        "verification": {
            "receipt_path": str(verification_path),
            "receipt_sha256": verification_sha256,
        },
        "health": health_row,
        "versions": verification["versions"],
        "safety": {
            **verification["safety"],
            "supabase_health_pointer_upsert": False,
            "remote_methods": ["GET"],
        },
    }
    receipt_path, receipt_sha256 = _write_terminal(receipt_dir, f"{run_id}.json", receipt)
    pointer = {
        "schema_version": LATEST_SCHEMA,
        "run_id": run_id,
        "status": receipt["status"],
        "updated_at": finished_at,
        "receipt_path": str(receipt_path),
        "receipt_sha256": receipt_sha256,
        "counts": receipt["counts"],
    }
    _atomic_write_json(latest_pointer, pointer)
    return {**pointer, "exit_code": 0 if terminal_error is None else 1}


def write_configuration_failure(
    *,
    receipt_dir: Path,
    latest_pointer: Path,
    run_id: str | None,
    error: Exception,
    failure_stage: str = "read_only_transport",
    clock=now_utc,
) -> dict[str, object]:
    started_at = iso_utc(clock())
    safe_run_id = run_id or (
        f"utility-intake-{started_at.replace(':', '').replace('-', '')}-{uuid4().hex}"
    )
    if not shadow.RUN_ID_RE.fullmatch(safe_run_id):
        safe_run_id = (
            f"utility-intake-config-failure-{started_at.replace(':', '').replace('-', '')}-"
            f"{uuid4().hex}"
        )
    completed_at = iso_utc(clock())
    safe_stage = (
        failure_stage
        if failure_stage in {"credential_file", "read_only_transport", "dependency_wait"}
        else "startup_validation"
    )
    reason_code = (
        "UTILITY_INTAKE_DEPENDENCY_FAILED"
        if safe_stage == "dependency_wait"
        else "UTILITY_INTAKE_CONFIGURATION_FAILED"
    )
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "run_id": safe_run_id,
        "status": "failed",
        "reason_code": reason_code,
        "reason_detail": f"{type(error).__name__}: {safe_stage} failed",
        "startup_stage": safe_stage,
        "started_at": started_at,
        "completed_at": completed_at,
        "counts": {
            "records_attempted": 0,
            "records_written": 0,
            "records_rejected": 0,
            "sqlite_records": 0,
            "supabase_records": 0,
        },
        "parity": None,
        "verification": {"receipt_path": None, "receipt_sha256": None},
        "health": {
            "component": HEALTH_COMPONENT,
            "status": "error",
            "event_through": None,
            "source_through": None,
            "system_time": completed_at,
            "detail": f"Utility intake startup failed: {safe_stage}",
            "metrics": {},
        },
        "versions": {
            "collector": COLLECTOR_VERSION,
            "query": shadow.QUERY_VERSION,
            "parser": shadow.PARSER_VERSION,
        },
        "safety": {
            "source_network_requests": 0,
            "sqlite_writes": 0,
            "supabase_source_row_writes": 0,
            "supabase_health_pointer_upsert": False,
            "scoring": False,
            "candidate_promotion": False,
            "publication": False,
            "secret_values_recorded": False,
            "remote_methods": [],
        },
    }
    receipt_path, receipt_sha256 = _write_terminal(
        receipt_dir, f"{safe_run_id}.json", receipt
    )
    pointer = {
        "schema_version": LATEST_SCHEMA,
        "run_id": safe_run_id,
        "status": "failed",
        "updated_at": completed_at,
        "receipt_path": str(receipt_path),
        "receipt_sha256": receipt_sha256,
        "counts": receipt["counts"],
    }
    _atomic_write_json(latest_pointer, pointer)
    return {**pointer, "exit_code": 3}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-path", required=True, type=Path)
    parser.add_argument("--writer-lock-path", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--receipt-dir", required=True, type=Path)
    parser.add_argument("--latest-pointer", required=True, type=Path)
    parser.add_argument("--credential-file", type=Path)
    parser.add_argument("--dependency-wait-command", type=Path)
    parser.add_argument("--run-id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for name in (
        "sqlite_path", "writer_lock_path", "evidence_dir", "receipt_dir",
        "latest_pointer", "credential_file", "dependency_wait_command",
    ):
        if getattr(args, name) is None:
            continue
        if not getattr(args, name).is_absolute():
            print(f"FATAL: --{name.replace('_', '-')} must be absolute", file=sys.stderr)
            return 64
    try:
        validate_credential_file(args.credential_file)
        transport = ReadOnlySupabaseTransport(
            os.environ.get("SUPABASE_URL", ""),
            os.environ.get("SUPABASE_ANON_KEY", ""),
        )
        wait_for_dependencies(args.dependency_wait_command)
    except Exception as error:
        try:
            result = write_configuration_failure(
                receipt_dir=args.receipt_dir,
                latest_pointer=args.latest_pointer,
                run_id=args.run_id,
                error=error,
                failure_stage=(
                    "dependency_wait"
                    if isinstance(error, DependencyWaitError)
                    else (
                        "credential_file"
                        if isinstance(error, CredentialFileError)
                        else "read_only_transport"
                    )
                ),
            )
        except Exception as receipt_error:
            print(
                json.dumps(
                    {
                        "status": "receipt_failure",
                        "error_type": type(receipt_error).__name__,
                    }
                ),
                file=sys.stderr,
            )
            return 3
        print(json.dumps(result, indent=2, sort_keys=True))
        return int(result["exit_code"])
    try:
        result = run_production(
            sqlite_path=args.sqlite_path,
            writer_lock_path=args.writer_lock_path,
            evidence_dir=args.evidence_dir,
            receipt_dir=args.receipt_dir,
            latest_pointer=args.latest_pointer,
            transport=transport,
            run_id=args.run_id,
        )
    except Exception as error:
        print(
            json.dumps({"status": "receipt_failure", "error_type": type(error).__name__}),
            file=sys.stderr,
        )
        return 3
    print(json.dumps(result, indent=2, sort_keys=True))
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
