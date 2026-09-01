#!/usr/bin/env python3
"""Replicate the bounded utility-intake receipt chain for the localhost Desk.

The source is a fixed read-only SSH alias and fixed producer directory.  The
script copies two pointer snapshots, validates every hash-bound receipt between
them, and atomically installs only stable bytes into the private Desk data
directory. A cross-process lock prevents overlapping refreshes, and scp trusts
only the caller's explicit, protected known-hosts file. It never contacts
Supabase and never issues a remote write.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from typing import Any, Sequence
from uuid import uuid4


LATEST_SCHEMA = "FloridaSignalUtilityIntakeProductionLatestV2"
RECEIPT_SCHEMA = "FloridaSignalUtilityIntakeProductionReceiptV3"
VERIFICATION_SCHEMA = "FloridaSignalUtilityIntakeProductionVerificationV1"
REMOTE_ROOT = Path("/srv/grahamandgold/florida-signal/staging/data/utility-intake")
REMOTE_RECEIPTS = REMOTE_ROOT / "receipts"
MAX_FILE_BYTES = 2_000_000
MAX_KNOWN_HOSTS_BYTES = 1_000_000
POINTER_NAMES = ("latest-attempt.json", "latest-success.json")
SAFE_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,220}")


class SyncError(RuntimeError):
    pass


def _read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise SyncError("snapshot input is not a regular file")
    size = path.stat().st_size
    if size <= 0 or size > MAX_FILE_BYTES:
        raise SyncError("snapshot input size is outside its bound")
    raw = path.read_bytes()
    if len(raw) != size:
        raise SyncError("snapshot input changed during read")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise SyncError("snapshot input is not valid JSON") from error
    if not isinstance(payload, dict):
        raise SyncError("snapshot input is not an object")
    return payload, raw


def _remote_receipt_name(value: Any) -> str:
    path = Path(str(value or ""))
    if (
        not path.is_absolute()
        or path.parent != REMOTE_RECEIPTS
        or not SAFE_NAME_RE.fullmatch(path.name)
    ):
        raise SyncError("receipt path crossed the fixed producer directory")
    return path.name


def _validate_pointer(path: Path, kind: str) -> tuple[dict[str, Any], bytes]:
    pointer, raw = _read_json(path)
    if set(pointer) != {
        "schema_version", "pointer_kind", "run_id", "status", "updated_at",
        "receipt_path", "receipt_sha256", "counts", "execution",
    }:
        raise SyncError("latest pointer has the wrong shape")
    if (
        pointer.get("schema_version") != LATEST_SCHEMA
        or pointer.get("pointer_kind") != kind
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}", str(pointer.get("run_id") or ""))
        or pointer.get("status") not in {"ok", "failed"}
        or (kind == "success" and pointer.get("status") != "ok")
        or not re.fullmatch(r"[0-9a-f]{64}", str(pointer.get("receipt_sha256") or ""))
        or not isinstance(pointer.get("counts"), dict)
        or not isinstance(pointer.get("execution"), dict)
    ):
        raise SyncError("latest pointer contract failed")
    _remote_receipt_name(pointer.get("receipt_path"))
    return pointer, raw


def _copy_remote(
    scp: Path, host: str, known_hosts: Path, remote_name: str, destination: Path,
) -> None:
    if not SAFE_NAME_RE.fullmatch(remote_name):
        raise SyncError("remote filename is unsafe")
    try:
        result = subprocess.run(
            [
                str(scp), "-q", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                "-o", "StrictHostKeyChecking=yes",
                "-o", f"UserKnownHostsFile={known_hosts}",
                "-o", "GlobalKnownHostsFile=/dev/null",
                f"{host}:{REMOTE_ROOT / remote_name}", str(destination),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise SyncError("bounded read-only receipt copy failed") from error
    if result.returncode != 0:
        raise SyncError("bounded read-only receipt copy failed")


def _copy_remote_receipt(
    scp: Path, host: str, known_hosts: Path, name: str, destination: Path,
) -> None:
    if not SAFE_NAME_RE.fullmatch(name):
        raise SyncError("remote receipt filename is unsafe")
    try:
        result = subprocess.run(
            [
                str(scp), "-q", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                "-o", "StrictHostKeyChecking=yes",
                "-o", f"UserKnownHostsFile={known_hosts}",
                "-o", "GlobalKnownHostsFile=/dev/null",
                f"{host}:{REMOTE_RECEIPTS / name}", str(destination),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise SyncError("bounded read-only receipt copy failed") from error
    if result.returncode != 0:
        raise SyncError("bounded read-only receipt copy failed")


def _validate_outcome(
    path: Path, pointer: dict[str, Any], copied: dict[str, bytes], *, scp: Path, host: str,
    known_hosts: Path, scratch: Path,
) -> None:
    outcome_name = _remote_receipt_name(pointer.get("receipt_path"))
    outcome, raw = _read_json(path)
    if hashlib.sha256(raw).hexdigest() != pointer["receipt_sha256"]:
        raise SyncError("outcome receipt hash mismatch")
    if (
        outcome.get("schema_version") != RECEIPT_SCHEMA
        or outcome.get("run_id") != pointer.get("run_id")
        or outcome.get("status") != pointer.get("status")
        or outcome.get("completed_at") != pointer.get("updated_at")
        or outcome.get("counts") != pointer.get("counts")
        or outcome.get("execution") != pointer.get("execution")
    ):
        raise SyncError("outcome receipt is not bound to latest")
    copied[outcome_name] = raw
    if outcome.get("status") != "ok":
        return
    verification = outcome.get("verification")
    if not isinstance(verification, dict):
        raise SyncError("successful outcome lacks verification binding")
    verification_name = _remote_receipt_name(verification.get("receipt_path"))
    verification_sha = str(verification.get("receipt_sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", verification_sha):
        raise SyncError("verification receipt hash is malformed")
    verification_path = scratch / f"receipt-{uuid4().hex}-{verification_name}"
    _copy_remote_receipt(scp, host, known_hosts, verification_name, verification_path)
    verification_receipt, verification_raw = _read_json(verification_path)
    if hashlib.sha256(verification_raw).hexdigest() != verification_sha:
        raise SyncError("verification receipt hash mismatch")
    if (
        verification_receipt.get("schema_version") != VERIFICATION_SCHEMA
        or verification_receipt.get("run_id") != outcome.get("run_id")
        or verification_receipt.get("status") != "verified"
        or verification_receipt.get("completed_at") != outcome.get("completed_at")
        or verification_receipt.get("counts") != outcome.get("counts")
        or verification_receipt.get("parity") != outcome.get("parity")
        or verification_receipt.get("execution") != outcome.get("execution")
    ):
        raise SyncError("verification receipt is not bound to outcome")
    copied[verification_name] = verification_raw


def _real_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise SyncError("snapshot destination is unsafe")
    os.chmod(path, 0o700)


def _validate_known_hosts(path: Path) -> None:
    if not path.is_absolute() or path.is_symlink():
        raise SyncError("known-hosts path must be an absolute regular file")
    try:
        metadata = path.lstat()
    except OSError as error:
        raise SyncError("known-hosts path is unavailable") from error
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size <= 0
        or metadata.st_size > MAX_KNOWN_HOSTS_BYTES
        or metadata.st_mode & 0o022
    ):
        raise SyncError("known-hosts file is unsafe")


def _acquire_sync_lock(destination: Path) -> int:
    lock_path = destination / ".sync.lock"
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise SyncError("receipt sync lock is not a regular file")
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        try:
            os.close(descriptor)
        except (OSError, UnboundLocalError):
            pass
        raise SyncError("receipt sync is already active") from error
    except Exception:
        try:
            os.close(descriptor)
        except (OSError, UnboundLocalError):
            pass
        raise
    return descriptor


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_fsynced_temporary(path: Path, raw: bytes) -> Path:
    """Write private bytes beside *path* without publishing them."""

    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(temporary, flags, 0o600)
    try:
        view = memoryview(raw)
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, view[offset:])
            if written <= 0:
                raise OSError("snapshot write made no forward progress")
            offset += written
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
    except Exception:
        try:
            os.close(descriptor)
        finally:
            temporary.unlink(missing_ok=True)
        raise
    os.close(descriptor)
    return temporary


def _read_immutable_bytes(path: Path) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise SyncError("immutable receipt destination is unsafe") from error
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_size > MAX_FILE_BYTES
        ):
            raise SyncError("immutable receipt destination is unsafe")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                raise SyncError("immutable receipt changed during comparison")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise SyncError("immutable receipt changed during comparison")
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
            raise SyncError("immutable receipt changed during comparison")
        try:
            current = os.lstat(path)
        except OSError as error:
            raise SyncError("immutable receipt changed during comparison") from error
        if (
            stat.S_ISLNK(current.st_mode)
            or current.st_dev != after.st_dev
            or current.st_ino != after.st_ino
        ):
            raise SyncError("immutable receipt changed during comparison")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _create_or_compare_immutable(path: Path, raw: bytes) -> None:
    """Publish a receipt once, or prove an existing same-name receipt identical."""

    temporary = _write_fsynced_temporary(path, raw)
    try:
        try:
            # Hard-link publication is atomic and create-only. It can never replace
            # a prior immutable receipt, including a same-run conflicting receipt.
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError:
            if _read_immutable_bytes(path) != raw:
                raise SyncError("immutable receipt conflicts with existing bytes")
            return
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_replace_pointer(path: Path, raw: bytes) -> None:
    if path.is_symlink():
        raise SyncError("refusing symlink snapshot destination")
    temporary = _write_fsynced_temporary(path, raw)
    try:
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _sync_receipts_locked(
    *, destination: Path, host: str, known_hosts: Path, scp: Path, attempts: int,
) -> dict[str, Any]:
    for attempt_number in range(1, attempts + 1):
        with tempfile.TemporaryDirectory(prefix="utility-receipts-", dir=str(destination)) as tmp:
            scratch = Path(tmp)
            first: dict[str, tuple[dict[str, Any], bytes]] = {}
            for name, kind in zip(POINTER_NAMES, ("attempt", "success")):
                copied_path = scratch / f"first-{name}"
                _copy_remote(scp, host, known_hosts, name, copied_path)
                first[name] = _validate_pointer(copied_path, kind)

            receipts: dict[str, bytes] = {}
            for pointer, _raw in first.values():
                outcome_name = _remote_receipt_name(pointer["receipt_path"])
                if outcome_name in receipts:
                    continue
                outcome_path = scratch / f"receipt-{uuid4().hex}-{outcome_name}"
                _copy_remote_receipt(scp, host, known_hosts, outcome_name, outcome_path)
                _validate_outcome(
                    outcome_path, pointer, receipts, scp=scp, host=host,
                    known_hosts=known_hosts, scratch=scratch,
                )

            stable = True
            for name, kind in zip(POINTER_NAMES, ("attempt", "success")):
                copied_path = scratch / f"second-{name}"
                _copy_remote(scp, host, known_hosts, name, copied_path)
                _pointer, second_raw = _validate_pointer(copied_path, kind)
                if second_raw != first[name][1]:
                    stable = False
            if not stable:
                continue

            for name, raw in receipts.items():
                _create_or_compare_immutable(destination / "receipts" / name, raw)
            for name in POINTER_NAMES:
                _atomic_replace_pointer(destination / name, first[name][1])
            return {
                "status": "synced",
                "attempt": attempt_number,
                "receipt_files": len(receipts),
                "latest_attempt_run_id": first["latest-attempt.json"][0]["run_id"],
                "latest_success_run_id": first["latest-success.json"][0]["run_id"],
            }
    raise SyncError("producer pointers changed during every bounded snapshot attempt")


def sync_receipts(
    *, destination: Path, host: str, known_hosts: Path, scp: Path, attempts: int = 3,
) -> dict[str, Any]:
    if not destination.is_absolute():
        raise SyncError("snapshot destination must be absolute")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", host):
        raise SyncError("SSH alias is unsafe")
    if not scp.is_absolute() or scp.is_symlink() or not os.access(scp, os.X_OK):
        raise SyncError("scp executable is unsafe")
    if type(attempts) is not int or not 1 <= attempts <= 3:
        raise SyncError("snapshot attempts are outside the bound")
    _validate_known_hosts(known_hosts)
    _real_private_directory(destination)
    receipts_dir = destination / "receipts"
    _real_private_directory(receipts_dir)
    descriptor = _acquire_sync_lock(destination)
    try:
        return _sync_receipts_locked(
            destination=destination, host=host, known_hosts=known_hosts,
            scp=scp, attempts=attempts,
        )
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--ssh-host", default="florida")
    parser.add_argument("--known-hosts", required=True, type=Path)
    parser.add_argument("--scp", type=Path, default=Path("/usr/bin/scp"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = sync_receipts(
            destination=args.destination, host=args.ssh_host,
            known_hosts=args.known_hosts, scp=args.scp,
        )
    except (OSError, SyncError) as error:
        print(json.dumps({"status": "unavailable", "error_type": type(error).__name__}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
