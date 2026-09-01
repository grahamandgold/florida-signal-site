#!/usr/bin/env python3
"""Bounded, default-off SFWMD failure alert delivery.

The systemd OnFailure unit invokes this program.  It reads only the durable,
secret-free early-failure pointer, sends a small Slack webhook message when the
independent alert gate is enabled, and writes a hash-bound local delivery
receipt.  The webhook URL is process-only and never enters an artifact.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Callable, Mapping, Sequence


MAX_LEDGER_BYTES = 128_000
MAX_FAILURE_RECEIPTS = 10_000
MAX_RESPONSE_BYTES = 16_000
TIMEOUT_SECONDS = 15
ALERT_SCHEMA = "FloridaSignalSfwmdAlertDeliveryV1"
ALERT_CLAIM_SCHEMA = "FloridaSignalSfwmdAlertClaimV1"
RUN_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
UNIT_RE = re.compile(r"^florida-sfwmd-pending-erp(?:-timer)?\.service$")
UTC_CLOCK_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$"
)


class AlertError(RuntimeError):
    pass


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ) + "\n").encode("utf-8")


def iso_utc(value: dt.datetime) -> str:
    if value.tzinfo is None:
        raise AlertError("alert clock must be timezone-aware")
    return value.astimezone(dt.timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _load_exact_json(path: Path, *, keys: set[str], label: str) -> tuple[dict[str, Any], bytes]:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise AlertError(f"{label} is missing or unsafe")
    if path.stat().st_size > MAX_LEDGER_BYTES:
        raise AlertError(f"{label} exceeds its byte cap")
    body = path.read_bytes()
    try:
        value = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AlertError(f"{label} is invalid JSON") from exc
    if not isinstance(value, dict) or set(value) != keys or body != canonical_bytes(value):
        raise AlertError(f"{label} contract is not exact")
    return value, body


def load_failure_receipt(receipt_path: Path, ledger_dir: Path) -> dict[str, Any]:
    if receipt_path.parent.resolve(strict=True) != ledger_dir.resolve(strict=True):
        raise AlertError("SFWMD failure receipt escapes its ledger")
    receipt, body = _load_exact_json(
        receipt_path,
        keys={
            "schema_version", "run_id", "status", "stage", "failed_unit",
            "failure_order_key", "natural_run", "provenance", "started_at", "failed_at",
            "error_class", "evidence_bundle_path", "canonical_receipt_committed",
            "alert_required", "safety",
        },
        label="SFWMD failure receipt",
    )
    run_id = str(receipt.get("run_id") or "")
    stage = str(receipt.get("stage") or "")
    failed_unit = receipt.get("failed_unit")
    if (
        receipt["schema_version"] != "FloridaSignalSfwmdEarlyFailureV1"
        or not RUN_ID_RE.fullmatch(run_id)
        or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", stage) is None
        or (failed_unit is not None and UNIT_RE.fullmatch(str(failed_unit)) is None)
        or receipt_path.name != f"{run_id}.{stage}.failure.json"
        or receipt["status"] != "failed"
        or receipt["alert_required"] is not True
        or receipt.get("failure_order_key") != f"{receipt.get('failed_at')}|{run_id}|{stage}"
        or receipt["safety"] != {
            "source_state_mutation_claimed": False,
            "scoring": False,
            "publication": False,
        }
    ):
        raise AlertError("SFWMD failure receipt contract is invalid")
    if (
        UTC_CLOCK_RE.fullmatch(str(receipt.get("started_at") or "")) is None
        or UTC_CLOCK_RE.fullmatch(str(receipt.get("failed_at") or "")) is None
    ):
        raise AlertError("SFWMD failure clocks are invalid")
    try:
        started = dt.datetime.fromisoformat(str(receipt["started_at"]).replace("Z", "+00:00"))
        failed = dt.datetime.fromisoformat(str(receipt["failed_at"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise AlertError("SFWMD failure clocks are invalid") from exc
    if (
        started.tzinfo is None or failed.tzinfo is None
        or started.utcoffset() != dt.timedelta(0) or failed.utcoffset() != dt.timedelta(0)
        or started > failed
    ):
        raise AlertError("SFWMD failure clocks are invalid")
    return {
        **receipt,
        "_receipt_path": str(receipt_path),
        "_receipt_sha256": hashlib.sha256(body).hexdigest(),
    }


def _write_create_only(path: Path, value: Mapping[str, Any]) -> None:
    if not path.is_absolute():
        raise AlertError("alert receipt path must be absolute")
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    body = canonical_bytes(value)
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        if path.read_bytes() != body:
            raise AlertError("alert delivery already has a conflicting receipt")
        return
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise AlertError("alert receipt is not a regular file")
        offset = 0
        while offset < len(body):
            written = os.write(fd, body[offset:])
            if written <= 0:
                raise AlertError("alert receipt write made no progress")
            offset += written
        os.fsync(fd)
    except Exception:
        os.close(fd)
        path.unlink(missing_ok=True)
        raise
    os.close(fd)
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _failure_artifact_paths(
    failure: Mapping[str, Any], alert_receipt_dir: Path
) -> tuple[Path, Path]:
    stem = (
        f"{failure['run_id']}.{failure['stage']}."
        f"{str(failure['_receipt_sha256'])[:16]}"
    )
    return (
        alert_receipt_dir / f"{stem}.claim.json",
        alert_receipt_dir / f"{stem}.alert.json",
    )


def _load_claim(path: Path, failure: Mapping[str, Any]) -> dict[str, Any]:
    claim, _ = _load_exact_json(
        path,
        keys={
            "schema_version", "delivery_id", "run_id", "failed_unit", "failure_stage",
            "failure_receipt_path", "failure_receipt_sha256", "claimed_at",
        },
        label="SFWMD alert claim",
    )
    if (
        claim.get("schema_version") != ALERT_CLAIM_SCHEMA
        or claim.get("delivery_id") != str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"florida-signal-sfwmd-alert:{failure['_receipt_sha256']}",
        ))
        or claim.get("run_id") != failure["run_id"]
        or claim.get("failed_unit") != failure["failed_unit"]
        or claim.get("failure_stage") != failure["stage"]
        or claim.get("failure_receipt_path") != failure["_receipt_path"]
        or claim.get("failure_receipt_sha256") != failure["_receipt_sha256"]
        or UTC_CLOCK_RE.fullmatch(str(claim.get("claimed_at") or "")) is None
    ):
        raise AlertError("SFWMD alert claim does not match its failure")
    return claim


def _load_delivery(
    path: Path, failure: Mapping[str, Any], claim: Mapping[str, Any]
) -> dict[str, Any]:
    delivery, _ = _load_exact_json(
        path,
        keys={
            "schema_version", "delivery_id", "run_id", "failed_unit", "failure_stage",
            "failure_receipt_path", "failure_receipt_sha256", "claim_sha256",
            "delivered_at", "transport", "endpoint_host", "http_status",
            "response_sha256", "secrets_persisted",
        },
        label="SFWMD alert delivery receipt",
    )
    if (
        delivery.get("schema_version") != ALERT_SCHEMA
        or delivery.get("delivery_id") != claim["delivery_id"]
        or delivery.get("run_id") != failure["run_id"]
        or delivery.get("failed_unit") != failure["failed_unit"]
        or delivery.get("failure_stage") != failure["stage"]
        or delivery.get("failure_receipt_path") != failure["_receipt_path"]
        or delivery.get("failure_receipt_sha256") != failure["_receipt_sha256"]
        or delivery.get("claim_sha256") != hashlib.sha256(canonical_bytes(claim)).hexdigest()
        or delivery.get("transport") != "slack_webhook"
        or delivery.get("endpoint_host") != "hooks.slack.com"
        or not isinstance(delivery.get("http_status"), int)
        or not 200 <= delivery["http_status"] < 300
        or re.fullmatch(r"[0-9a-f]{64}", str(delivery.get("response_sha256") or "")) is None
        or delivery.get("secrets_persisted") is not False
        or UTC_CLOCK_RE.fullmatch(str(delivery.get("delivered_at") or "")) is None
    ):
        raise AlertError("SFWMD alert delivery receipt is invalid")
    return delivery


def _try_create_claim(path: Path, claim: Mapping[str, Any]) -> bool:
    if not path.is_absolute():
        raise AlertError("alert claim path must be absolute")
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        return False
    body = canonical_bytes(claim)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise AlertError("alert claim is not a regular file")
        offset = 0
        while offset < len(body):
            written = os.write(fd, body[offset:])
            if written <= 0:
                raise AlertError("alert claim write made no progress")
            offset += written
        os.fsync(fd)
    except Exception:
        os.close(fd)
        path.unlink(missing_ok=True)
        raise
    os.close(fd)
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return True


def _list_failures(failure_ledger_dir: Path, failed_unit: str) -> list[dict[str, Any]]:
    if (
        not failure_ledger_dir.is_absolute() or failure_ledger_dir.is_symlink()
        or not failure_ledger_dir.is_dir()
    ):
        raise AlertError("SFWMD failure ledger is missing or unsafe")
    paths = sorted(failure_ledger_dir.glob("*.failure.json"))
    if len(paths) > MAX_FAILURE_RECEIPTS:
        raise AlertError("SFWMD failure ledger exceeds its receipt cap")
    failures = [load_failure_receipt(path, failure_ledger_dir) for path in paths]
    return sorted(
        (failure for failure in failures if failure["failed_unit"] == failed_unit),
        key=lambda failure: (failure["failure_order_key"], failure["_receipt_path"]),
    )


def deliver_alert(
    *,
    failed_unit: str,
    failure_ledger_dir: Path,
    alert_receipt_dir: Path,
    opener: Callable[..., Any] | None = None,
    clock: Callable[[], dt.datetime] = utc_now,
) -> dict[str, Any]:
    if not UNIT_RE.fullmatch(failed_unit):
        raise AlertError("OnFailure supplied an unexpected unit")
    if os.environ.get("FLORIDA_SIGNAL_SFWMD_ALERT_ENABLED") != "1":
        return {"status": "disabled", "run_id": None, "delivered": False}
    failures = _list_failures(failure_ledger_dir, failed_unit)
    if not failures:
        raise AlertError("OnFailure has no correlated durable failure receipt")
    delivered: list[tuple[dict[str, Any], Path]] = []
    indeterminate: list[dict[str, Any]] = []
    pending: list[tuple[dict[str, Any], Path, Path]] = []
    for failure in failures:
        claim_path, receipt_path = _failure_artifact_paths(failure, alert_receipt_dir)
        if receipt_path.exists():
            claim = _load_claim(claim_path, failure)
            _load_delivery(receipt_path, failure, claim)
            delivered.append((failure, receipt_path))
        elif claim_path.exists():
            _load_claim(claim_path, failure)
            indeterminate.append(failure)
        else:
            pending.append((failure, claim_path, receipt_path))
    if not pending:
        if indeterminate:
            return {
                "status": "indeterminate", "run_id": indeterminate[0]["run_id"],
                "delivered": False,
            }
        failure, receipt_path = delivered[-1]
        return {
            "status": "already_delivered", "run_id": failure["run_id"],
            "delivered": True, "receipt_path": str(receipt_path),
        }
    # The OnFailure invocation most likely corresponds to the newest durable
    # receipt. Prioritize it so a disabled-window backlog cannot hide the
    # current failure; older receipts remain available for explicit replay.
    failure, claim_path, receipt_path = pending[-1]
    webhook = os.environ.get("FLORIDA_SIGNAL_SFWMD_ALERT_WEBHOOK_URL", "")
    parsed = urllib.parse.urlparse(webhook)
    if (
        parsed.scheme != "https" or parsed.hostname != "hooks.slack.com"
        or not parsed.path.startswith("/services/") or parsed.username or parsed.password
        or parsed.query or parsed.fragment
    ):
        raise AlertError("alert webhook must be a Slack HTTPS services endpoint")
    claim = {
        "schema_version": ALERT_CLAIM_SCHEMA,
        "delivery_id": str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"florida-signal-sfwmd-alert:{failure['_receipt_sha256']}",
        )),
        "run_id": failure["run_id"],
        "failed_unit": failed_unit,
        "failure_stage": failure["stage"],
        "failure_receipt_path": failure["_receipt_path"],
        "failure_receipt_sha256": failure["_receipt_sha256"],
        "claimed_at": iso_utc(clock()),
    }
    if not _try_create_claim(claim_path, claim):
        # Another OnFailure handler won the durable claim. Never duplicate the
        # webhook; the next invocation will reconcile claim/receipt state.
        _load_claim(claim_path, failure)
        return {"status": "claimed_elsewhere", "run_id": failure["run_id"], "delivered": False}
    message = {
        "text": (
            "Florida Signal SFWMD collection failed. "
            f"unit={failed_unit} run={failure['run_id']} stage={failure['stage']} "
            f"failed_at={failure['failed_at']}. Inspect the host failure ledger; "
            "do not infer source absence or retry unboundedly."
        )
    }
    request = urllib.request.Request(
        webhook,
        data=canonical_bytes(message),
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "florida-signal-sfwmd-alert/1"},
    )
    try:
        response_context = (opener or urllib.request.urlopen)(request, timeout=TIMEOUT_SECONDS)
        with response_context as response:
            status_value = getattr(response, "status", None)
            status = int(status_value if status_value is not None else response.getcode())
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        raise AlertError(f"alert delivery failed: {type(exc).__name__}") from exc
    if len(body) > MAX_RESPONSE_BYTES or not 200 <= status < 300:
        raise AlertError("alert endpoint returned a rejected or oversized response")
    receipt = {
        "schema_version": ALERT_SCHEMA,
        "delivery_id": claim["delivery_id"],
        "run_id": failure["run_id"],
        "failed_unit": failed_unit,
        "failure_stage": failure["stage"],
        "failure_receipt_path": failure["_receipt_path"],
        "failure_receipt_sha256": failure["_receipt_sha256"],
        "claim_sha256": hashlib.sha256(canonical_bytes(claim)).hexdigest(),
        "delivered_at": iso_utc(clock()),
        "transport": "slack_webhook",
        "endpoint_host": parsed.hostname,
        "http_status": status,
        "response_sha256": hashlib.sha256(body).hexdigest(),
        "secrets_persisted": False,
    }
    _write_create_only(receipt_path, receipt)
    return {"status": "delivered", "run_id": failure["run_id"], "delivered": True,
            "receipt_path": str(receipt_path)}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--failed-unit", required=True)
    parser.add_argument("--failure-ledger-dir", required=True, type=Path)
    parser.add_argument("--alert-receipt-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = deliver_alert(
            failed_unit=args.failed_unit,
            failure_ledger_dir=args.failure_ledger_dir,
            alert_receipt_dir=args.alert_receipt_dir,
        )
    except AlertError as exc:
        print(json.dumps({"status": "failed", "error_class": type(exc).__name__}, sort_keys=True))
        return 65
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("status") in {"delivered", "already_delivered", "disabled"} else 65


if __name__ == "__main__":
    raise SystemExit(main())
