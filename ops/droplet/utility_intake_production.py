#!/usr/bin/env python3
"""Verify and publish the Fort Lauderdale utility/engineering intake lane.

The existing Accela intake remains the only source transport.  This process
builds the reviewed exact-family projection from the canonical SQLite
authority, proves complete row parity against the Supabase ``permits`` mirror,
writes an immutable local terminal receipt, and updates only the sanitized
``editorial_pipeline_health`` pointer used by the Desk.
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
REMOTE_PAGE_SIZE = 1000
REMOTE_ROW_CAP = 5000
MAX_RESPONSE_BYTES = 8_000_000
REQUEST_TIMEOUT_SECONDS = 25

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
REMOTE_OR_FILTER = ",".join(
    (
        "permit_number.like.ENG-CR-*",
        "permit_number.like.ENG-OAA-*",
        "permit_number.like.ROW-SEW-*",
        "permit_number.like.ROW-WTR-*",
        "permit_number.like.PLB-SEWCP-WT-*",
    )
)


class ProductionError(RuntimeError):
    """A production evidence or parity contract failed closed."""


class JsonTransport(Protocol):
    def request_json(
        self,
        method: str,
        path: str,
        *,
        body: object | None = None,
        prefer: str | None = None,
    ) -> object: ...


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


def _safe_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value)


def _atomic_write_json(path: Path, value: object) -> str:
    if not path.is_absolute():
        raise ProductionError("latest pointer path must be absolute")
    path.parent.mkdir(parents=True, exist_ok=True)
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
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
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
    receipt_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(receipt_dir, 0o700)
    if Path(filename).name != filename:
        raise ProductionError("receipt filename must not contain path components")
    path = receipt_dir / filename
    body = shadow.canonical_json_bytes(receipt)
    _write_private_create_only_fsynced(path, body)
    directory_fd = os.open(receipt_dir, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return path, hashlib.sha256(body).hexdigest()


class SupabaseTransport:
    """Small bounded PostgREST client; credentials remain process-only."""

    def __init__(self, url: str, service_key: str) -> None:
        self.url = url.rstrip("/")
        self.service_key = service_key
        if not self.url.startswith("https://"):
            raise ProductionError("SUPABASE_URL must be https")
        if not service_key:
            raise ProductionError("SUPABASE_SERVICE_ROLE_KEY is required")

    def request_json(
        self,
        method: str,
        path: str,
        *,
        body: object | None = None,
        prefer: str | None = None,
    ) -> object:
        data = None if body is None else shadow.canonical_json_bytes(body)
        headers = {
            "Accept": "application/json",
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "User-Agent": COLLECTOR_VERSION,
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        if prefer:
            headers["Prefer"] = prefer
        request = urllib.request.Request(
            f"{self.url}/rest/v1/{path}",
            method=method,
            data=data,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                length = response.headers.get("Content-Length")
                if length and int(length) > MAX_RESPONSE_BYTES:
                    raise ProductionError("Supabase response exceeded the byte cap")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise ProductionError("Supabase response exceeded the byte cap")
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise ProductionError(f"Supabase request failed: {type(error).__name__}") from error
        try:
            return json.loads(raw or b"null")
        except json.JSONDecodeError as error:
            raise ProductionError("Supabase returned non-JSON data") from error


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


def _remote_projection_once(transport: JsonTransport) -> list[dict[str, str | None]]:
    rows: list[dict[str, str | None]] = []
    offset = 0
    while True:
        query = urllib.parse.urlencode(
            {
                "select": ",".join(PARITY_COLUMNS),
                "or": f"({REMOTE_OR_FILTER})",
                "order": "permit_number.asc",
                "limit": str(REMOTE_PAGE_SIZE),
                "offset": str(offset),
            }
        )
        payload = transport.request_json("GET", f"permits?{query}")
        if not isinstance(payload, list):
            raise ProductionError("Supabase permits response is not a row list")
        if not payload:
            break
        if offset + len(payload) > REMOTE_ROW_CAP:
            raise ProductionError("Supabase utility pagination exceeded the safety cap")
        for raw in payload:
            if not isinstance(raw, dict):
                raise ProductionError("Supabase permits response contains a non-object row")
            identity = str(raw.get("permit_number") or "")
            # The PostgREST prefix filter is only a transport bound.  The exact
            # reviewed classifier remains the admission authority.
            if shadow.classify_record_number(identity) is None:
                continue
            missing = [column for column in PARITY_COLUMNS if column not in raw]
            if missing:
                raise ProductionError(f"Supabase utility projection lacks columns: {missing}")
            rows.append({column: _safe_text(raw.get(column)) for column in PARITY_COLUMNS})
        offset += len(payload)
    rows.sort(key=lambda row: str(row["permit_number"]))
    identities = [str(row["permit_number"]) for row in rows]
    if len(identities) != len(set(identities)):
        raise ProductionError("Supabase utility projection contains duplicate identities")
    return rows


def _remote_projection(transport: JsonTransport) -> list[dict[str, str | None]]:
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


def _same_instant(left: object, right: object) -> bool:
    try:
        left_value = datetime.fromisoformat(str(left).replace("Z", "+00:00"))
        right_value = datetime.fromisoformat(str(right).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if left_value.tzinfo is None or right_value.tzinfo is None:
        return False
    return left_value.astimezone(timezone.utc) == right_value.astimezone(timezone.utc)


def _publish_health(
    transport: JsonTransport,
    *,
    status: str,
    system_time: str,
    event_through: str | None,
    detail: str,
    metrics: dict[str, object],
) -> dict[str, object]:
    row = {
        "component": HEALTH_COMPONENT,
        "status": status,
        "event_through": event_through,
        "source_through": event_through,
        "system_time": system_time,
        "detail": detail[:2000],
        "metrics": metrics,
    }
    payload = transport.request_json(
        "POST",
        "editorial_pipeline_health?on_conflict=component",
        body=[row],
        prefer="resolution=merge-duplicates,return=representation",
    )
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise ProductionError("health upsert did not return one row")
    stored = payload[0]
    for key in ("component", "status"):
        if stored.get(key) != row[key]:
            raise ProductionError(f"health readback mismatch for {key}")
    if not _same_instant(stored.get("system_time"), row["system_time"]):
        raise ProductionError("health readback mismatch for system_time")
    if stored.get("metrics") != metrics:
        raise ProductionError("health readback metrics mismatch")
    return row


def run_production(
    *,
    sqlite_path: Path,
    writer_lock_path: Path,
    evidence_dir: Path,
    receipt_dir: Path,
    latest_pointer: Path,
    transport: JsonTransport,
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

    health_error: Exception | None = None
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
    try:
        health_row = _publish_health(
            transport,
            status=health_status,
            system_time=finished_at,
            event_through=_event_through(local_rows),
            detail=(
                f"{len(local_rows)} exact ENG-CR/ENG-OAA/ROW-SEW/ROW-WTR/"
                "PLB-SEWCP-WT records; complete declared 16-column SQLite/Supabase "
                "projection parity passed across two stable remote reads"
                if verification_error is None
                else (
                    "Utility/engineering intake verification failed: "
                    f"{type(verification_error).__name__}"
                )
            ),
            metrics=metrics,
        )
    except Exception as caught:
        health_error = caught
        health_row = None

    terminal_error = verification_error or health_error
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "run_id": run_id,
        "status": "ok" if terminal_error is None else "failed",
        "reason_code": (
            None
            if terminal_error is None
            else (
                "UTILITY_INTAKE_VERIFICATION_FAILED"
                if verification_error is not None
                else "UTILITY_INTAKE_HEALTH_PUBLICATION_FAILED"
            )
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
        "health": {
            "component": HEALTH_COMPONENT,
            "published": health_row is not None,
            "status": health_row.get("status") if health_row else None,
            "system_time": health_row.get("system_time") if health_row else None,
        },
        "versions": verification["versions"],
        "safety": {
            **verification["safety"],
            "supabase_health_pointer_upsert": health_row is not None,
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
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "run_id": safe_run_id,
        "status": "failed",
        "reason_code": "UTILITY_INTAKE_CONFIGURATION_FAILED",
        "reason_detail": f"{type(error).__name__}: transport initialization failed",
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
        "health": {"component": HEALTH_COMPONENT, "published": False, "status": None},
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
    parser.add_argument("--run-id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for name in ("sqlite_path", "writer_lock_path", "evidence_dir", "receipt_dir", "latest_pointer"):
        if not getattr(args, name).is_absolute():
            print(f"FATAL: --{name.replace('_', '-')} must be absolute", file=sys.stderr)
            return 64
    try:
        transport = SupabaseTransport(
            os.environ.get("SUPABASE_URL", ""),
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
        )
    except Exception as error:
        try:
            result = write_configuration_failure(
                receipt_dir=args.receipt_dir,
                latest_pointer=args.latest_pointer,
                run_id=args.run_id,
                error=error,
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
