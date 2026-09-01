#!/usr/bin/env python3
"""Default-off, verified offsite backup for the SFWMD evidence lane.

One invocation inventories immutable evidence, canonical/alert/backup receipts,
failure ledgers, timer canaries, and a writer-locked SQLite snapshot; sends the
bounded set to an S3-backed restic repository; restores that exact snapshot to
a private temporary directory; verifies every byte/count/hash; and only then
writes a create-only local backup receipt.  It never fetches SFWMD or mutates
source/current state.
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
import subprocess
import tempfile
import uuid
from typing import Any, Callable, Mapping, Sequence
import urllib.parse


BACKUP_SCHEMA = "FloridaSignalSfwmdOffsiteBackupReceiptV1"
MANIFEST_SCHEMA = "FloridaSignalSfwmdOffsiteBackupManifestV1"
MAX_FILES = 50_000
MAX_TOTAL_BYTES = 50 * 1024 * 1024 * 1024
MAX_RESTIC_OUTPUT_BYTES = 2_000_000


class BackupError(RuntimeError):
    pass


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ) + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def iso_utc(value: dt.datetime) -> str:
    if value.tzinfo is None:
        raise BackupError("backup clock must be timezone-aware")
    return value.astimezone(dt.timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _absolute_regular(path: Path, label: str) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise BackupError(f"{label} must be an absolute regular file")
    return path


def _absolute_directory(path: Path, label: str) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise BackupError(f"{label} must be an absolute real directory")
    return path


def _safe_path_text(path: Path, label: str) -> str:
    value = str(path)
    if any(character in value for character in ("\x00", "\r", "\n")):
        raise BackupError(f"{label} contains a forbidden path delimiter")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise BackupError(f"{label} is not UTF-8 encodable") from exc
    return value


def _open_writer_lock(path: Path):
    if not path.is_absolute():
        raise BackupError("writer lock path must be absolute")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise BackupError("writer lock cannot be a symlink")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise BackupError("writer lock is not a regular file")
    return os.fdopen(fd, "a+b")


def _create_sqlite_snapshot_unlocked(source: Path, destination: Path) -> None:
    _absolute_regular(source, "canonical SQLite database")
    if not destination.is_absolute() or destination.exists():
        raise BackupError("SQLite snapshot target must be a new absolute path")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as read_connection, \
            sqlite3.connect(destination) as snapshot_connection:
        read_connection.backup(snapshot_connection)
        integrity = snapshot_connection.execute("pragma integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise BackupError("SQLite snapshot failed integrity_check")
    os.chmod(destination, 0o400)


def create_sqlite_snapshot(source: Path, destination: Path, writer_lock_path: Path) -> None:
    with _open_writer_lock(writer_lock_path) as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        _create_sqlite_snapshot_unlocked(source, destination)


def build_manifest(sources: Mapping[str, Path], created_at: str) -> dict[str, Any]:
    if not sources or len(set(sources.values())) != len(sources):
        raise BackupError("backup sources must be nonempty and path-unique")
    entries: list[dict[str, Any]] = []
    source_contracts: list[dict[str, str]] = []
    total_bytes = 0
    for label, source in sorted(sources.items()):
        if re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", label) is None:
            raise BackupError("backup source label is invalid")
        if (
            not source.is_absolute()
            or source.is_symlink() or not source.exists()
        ):
            raise BackupError(f"backup source {label} is missing or unsafe")
        _safe_path_text(source, f"backup source {label}")
        if source.is_file():
            source_type = "file"
            paths = [source]
        elif source.is_dir():
            source_type = "directory"
            paths = sorted(source.rglob("*"))
        else:
            raise BackupError(f"backup source {label} is not regular")
        source_contracts.append({
            "source_label": label,
            "source_path": str(source),
            "source_type": source_type,
        })
        for path in paths:
            _safe_path_text(path, "backup inventory path")
            if path.is_symlink():
                raise BackupError("backup source contains a symlink")
            if path.is_dir():
                continue
            if not path.is_file():
                raise BackupError("backup source contains a non-regular object")
            size = path.stat().st_size
            total_bytes += size
            if len(entries) + 1 > MAX_FILES or total_bytes > MAX_TOTAL_BYTES:
                raise BackupError("backup inventory exceeds its file or byte cap")
            relative = "." if source.is_file() else path.relative_to(source).as_posix()
            entries.append({
                "source_label": label,
                "source_path": str(source),
                "relative_path": relative,
                "bytes": size,
                "sha256": sha256_file(path),
            })
    return {
        "schema_version": MANIFEST_SCHEMA,
        "created_at": created_at,
        "file_count": len(entries),
        "total_bytes": total_bytes,
        "sources": source_contracts,
        "entries": entries,
    }


def verify_restored_manifest(
    manifest: Mapping[str, Any],
    restore_root: Path,
    *,
    allowed_extra: set[Path] | None = None,
) -> dict[str, int]:
    if (
        not isinstance(manifest, Mapping)
        or set(manifest) != {
            "schema_version", "created_at", "file_count", "total_bytes", "sources", "entries"
        }
        or manifest.get("schema_version") != MANIFEST_SCHEMA
        or not isinstance(manifest.get("sources"), list)
        or not isinstance(manifest.get("entries"), list)
    ):
        raise BackupError("restored backup manifest is invalid")
    seen: set[Path] = set()
    expected_by_source: dict[Path, set[Path]] = {}
    file_sources: set[Path] = set()
    labels_by_source: dict[Path, str] = {}
    for source in manifest["sources"]:
        if not isinstance(source, Mapping) or set(source) != {
            "source_label", "source_path", "source_type"
        }:
            raise BackupError("restored backup source contract is invalid")
        source_path = Path(str(source["source_path"]))
        source_label = str(source["source_label"])
        if (
            not source_path.is_absolute() or source_path in expected_by_source
            or re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", source_label) is None
            or source["source_type"] not in {"file", "directory"}
        ):
            raise BackupError("restored backup source identity is invalid")
        expected_by_source[source_path] = set()
        labels_by_source[source_path] = source_label
        if source["source_type"] == "file":
            file_sources.add(source_path)
    observed_bytes = 0
    for entry in manifest["entries"]:
        if not isinstance(entry, Mapping) or set(entry) != {
            "source_label", "source_path", "relative_path", "bytes", "sha256"
        }:
            raise BackupError("restored backup entry contract is invalid")
        original = Path(str(entry["source_path"]))
        relative = str(entry["relative_path"])
        if (
            original not in expected_by_source
            or entry["source_label"] != labels_by_source[original]
            or relative.startswith("/") or ".." in Path(relative).parts
            or ((original in file_sources) != (relative == "."))
        ):
            raise BackupError("restored backup path is unsafe")
        restored_source = restore_root / original.as_posix().lstrip("/")
        restored = restored_source if relative == "." else restored_source / relative
        if restored in seen or restored.is_symlink() or not restored.is_file():
            raise BackupError("restored backup is missing, duplicated, or unsafe")
        seen.add(restored)
        expected_by_source[original].add(restored)
        size = restored.stat().st_size
        if size != entry["bytes"] or sha256_file(restored) != entry["sha256"]:
            raise BackupError("restored backup byte/hash verification failed")
        observed_bytes += size
    if manifest["file_count"] != len(seen) or manifest["total_bytes"] != observed_bytes:
        raise BackupError("restored backup aggregate counts disagree")
    for original, expected in expected_by_source.items():
        restored_source = restore_root / original.as_posix().lstrip("/")
        if original in file_sources:
            actual = {restored_source} if restored_source.is_file() and not restored_source.is_symlink() else set()
        else:
            if not expected and not restored_source.exists():
                actual = set()
                if actual != expected:
                    raise BackupError("restored backup contains missing or extra files")
                continue
            if restored_source.is_symlink() or not restored_source.is_dir():
                raise BackupError("restored backup directory is missing or unsafe")
            actual = set()
            for candidate in restored_source.rglob("*"):
                if candidate.is_symlink() or (not candidate.is_dir() and not candidate.is_file()):
                    raise BackupError("restored backup contains an unsafe object")
                if candidate.is_file():
                    actual.add(candidate)
        if actual != expected:
            raise BackupError("restored backup contains missing or extra files")
    permitted_extra = set(allowed_extra or set())
    for path in permitted_extra:
        try:
            path.relative_to(restore_root)
        except ValueError as exc:
            raise BackupError("restored extra-file allowance escapes its root") from exc
        if path.is_symlink() or not path.is_file():
            raise BackupError("restored extra-file allowance is unsafe")
    all_restored_files: set[Path] = set()
    for candidate in restore_root.rglob("*"):
        if candidate.is_symlink() or (not candidate.is_dir() and not candidate.is_file()):
            raise BackupError("restored backup contains an unsafe object")
        if candidate.is_file():
            all_restored_files.add(candidate)
    if all_restored_files != seen | permitted_extra:
        raise BackupError("restored backup contains files outside its exact manifest")
    return {"verified_files": len(seen), "verified_bytes": observed_bytes}


def _run_restic(command: list[str], env: Mapping[str, str]) -> bytes:
    result = subprocess.run(
        command,
        env=dict(env),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60 * 60,
    )
    if (
        len(result.stdout) > MAX_RESTIC_OUTPUT_BYTES
        or len(result.stderr) > MAX_RESTIC_OUTPUT_BYTES
        or result.returncode != 0
    ):
        raise BackupError("restic command failed or exceeded its output cap")
    return result.stdout


def _snapshot_id(output: bytes) -> str:
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        snapshot_id = value.get("snapshot_id") if isinstance(value, dict) else None
        if isinstance(snapshot_id, str) and re.fullmatch(r"[0-9a-f]{8,64}", snapshot_id):
            return snapshot_id
    raise BackupError("restic did not return a bounded snapshot id")


def _write_receipt(path: Path, value: Mapping[str, Any]) -> None:
    if not path.is_absolute() or path.is_symlink():
        raise BackupError("backup receipt path is unsafe")
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    body = canonical_bytes(value)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        offset = 0
        while offset < len(body):
            written = os.write(fd, body[offset:])
            if written <= 0:
                raise BackupError("backup receipt write made no progress")
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


def backup_and_verify(
    *,
    sqlite_path: Path,
    writer_lock_path: Path,
    evidence_dir: Path,
    receipt_dir: Path,
    alert_receipt_dir: Path,
    failure_dir: Path,
    provenance_dir: Path,
    backup_receipt_dir: Path,
    restic_bin: Path = Path("/usr/bin/restic"),
    runner: Callable[[list[str], Mapping[str, str]], bytes] = _run_restic,
    clock: Callable[[], dt.datetime] = utc_now,
) -> dict[str, Any]:
    if os.environ.get("FLORIDA_SIGNAL_SFWMD_BACKUP_ENABLED") != "1":
        return {"status": "disabled", "verified": False}
    repository = os.environ.get("RESTIC_REPOSITORY", "")
    if not repository.startswith("s3:https://"):
        raise BackupError("RESTIC_REPOSITORY must be an offsite S3 HTTPS repository")
    endpoint = urllib.parse.urlparse(repository[len("s3:"):])
    if (
        not endpoint.hostname or endpoint.username or endpoint.password
        or endpoint.query or endpoint.fragment
    ):
        raise BackupError("offsite S3 repository endpoint is invalid")
    password_file = Path(os.environ.get("RESTIC_PASSWORD_FILE", ""))
    _absolute_regular(password_file, "restic password file")
    if password_file.stat().st_mode & 0o077:
        raise BackupError("restic password file permissions are too broad")
    _absolute_regular(restic_bin, "restic binary")
    for path, label in (
        (evidence_dir, "evidence directory"), (receipt_dir, "receipt directory"),
        (alert_receipt_dir, "alert receipt directory"),
        (failure_dir, "failure directory"), (provenance_dir, "provenance directory"),
        (backup_receipt_dir, "backup receipt directory"),
    ):
        _absolute_directory(path, label)
    created_at = iso_utc(clock())
    backup_id = str(uuid.uuid4())
    with tempfile.TemporaryDirectory(prefix="sfwmd-backup-") as temporary:
        staging = Path(temporary)
        os.chmod(staging, 0o700)
        sqlite_snapshot = staging / "canonical-sfwmd.sqlite"
        with _open_writer_lock(writer_lock_path) as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            _create_sqlite_snapshot_unlocked(sqlite_path, sqlite_snapshot)
            sources = {
                "evidence": evidence_dir,
                "receipts": receipt_dir,
                "alert_receipts": alert_receipt_dir,
                "failures": failure_dir,
                "provenance": provenance_dir,
                "backup_receipts": backup_receipt_dir,
                "canonical_sqlite": sqlite_snapshot,
            }
            manifest = build_manifest(sources, created_at)
        manifest_path = staging / "sfwmd-backup-manifest.json"
        manifest_path.write_bytes(canonical_bytes(manifest))
        os.chmod(manifest_path, 0o400)
        sources["manifest"] = manifest_path
        manifest_sha = sha256_file(manifest_path)
        allowed_environment = {
            "RESTIC_REPOSITORY", "RESTIC_PASSWORD_FILE", "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_DEFAULT_REGION",
            "AWS_REGION",
        }
        environment = {
            key: value for key, value in os.environ.items()
            if key in allowed_environment
        }
        archived_files = sorted({
            str(
                Path(entry["source_path"])
                if entry["relative_path"] == "."
                else Path(entry["source_path"]) / entry["relative_path"]
            )
            for entry in manifest["entries"]
        } | {str(manifest_path)})
        paths_file = staging / "restic-files.txt"
        paths_file.write_bytes(b"".join(
            _safe_path_text(Path(path), "restic input path").encode("utf-8") + b"\x00"
            for path in archived_files
        ))
        os.chmod(paths_file, 0o400)
        output = runner([
            str(restic_bin), "backup", "--no-cache", "--json", "--tag", "florida-signal-sfwmd",
            "--host", "florida-signal-sfwmd", "--files-from-raw", str(paths_file),
        ], environment)
        snapshot_id = _snapshot_id(output)
        restore_root = staging / "restore"
        restore_root.mkdir(mode=0o700)
        runner([
            str(restic_bin), "restore", "--no-cache", snapshot_id, "--target", str(restore_root)
        ], environment)
        restored_manifest_path = restore_root / manifest_path.as_posix().lstrip("/")
        if not restored_manifest_path.is_file() or sha256_file(restored_manifest_path) != manifest_sha:
            raise BackupError("restored manifest does not match the uploaded manifest")
        restored_manifest = json.loads(restored_manifest_path.read_text(encoding="utf-8"))
        verified = verify_restored_manifest(
            restored_manifest,
            restore_root,
            allowed_extra={restored_manifest_path},
        )
    receipt = {
        "schema_version": BACKUP_SCHEMA,
        "backup_id": backup_id,
        "status": "verified",
        "created_at": created_at,
        "completed_at": iso_utc(clock()),
        "snapshot_id": snapshot_id,
        "repository_scheme": "s3+https",
        "repository_host": endpoint.hostname,
        "repository_fingerprint_sha256": hashlib.sha256(repository.encode()).hexdigest(),
        "manifest_sha256": manifest_sha,
        "file_count": manifest["file_count"],
        "total_bytes": manifest["total_bytes"],
        **verified,
        "restore_verified": True,
        "credentials_persisted": False,
        "source_state_mutated": False,
    }
    receipt_path = backup_receipt_dir / f"{backup_id}.json"
    _write_receipt(receipt_path, receipt)
    return {"status": "verified", "verified": True, "backup_id": backup_id,
            "snapshot_id": snapshot_id, "receipt_path": str(receipt_path)}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-path", required=True, type=Path)
    parser.add_argument("--writer-lock-path", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--receipt-dir", required=True, type=Path)
    parser.add_argument("--alert-receipt-dir", required=True, type=Path)
    parser.add_argument("--failure-dir", required=True, type=Path)
    parser.add_argument("--provenance-dir", required=True, type=Path)
    parser.add_argument("--backup-receipt-dir", required=True, type=Path)
    parser.add_argument("--restic-bin", type=Path, default=Path("/usr/bin/restic"))
    args = parser.parse_args(argv)
    try:
        result = backup_and_verify(**vars(args))
    except (BackupError, OSError, sqlite3.Error, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "failed", "error_class": type(exc).__name__}, sort_keys=True))
        return 65
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
