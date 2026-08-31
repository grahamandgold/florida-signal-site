#!/usr/bin/env python3
"""Read-only Fort Lauderdale sewer/utility and engineering-intake shadow view.

This collector reads an explicitly supplied SQLite database in query-only mode
and writes one immutable-on-create local observation bundle. It classifies only
exact reviewed record-number families already stored in that database.

It has no network client, no production SQLite writer, no Supabase, timer,
queue, Candidate, scoring, Desk-connected or publication path. Every run remains
``shadow_file_only`` and is never promotion eligible.
"""

from __future__ import annotations

import argparse
import errno
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import sys
import urllib.parse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence


COLLECTOR_VERSION = "ftl-utility-intake-shadow/1.4.0"
QUERY_VERSION = "ftl-utility-intake-query/1.3.1"
PARSER_VERSION = "ftl-utility-intake-parser/1.2.0"
SCHEMA_VERSION = "FloridaSignalUtilityIntakeShadowReceiptV5"
BUNDLE_SCHEMA_VERSION = "FloridaSignalUtilityIntakeObservationBundleV2"
MANIFEST_SCHEMA_VERSION = "FloridaSignalUtilityIntakeShadowBundleManifestV2"

PERMITS_TABLE = "permits"
ACCELA_DETAILS_TABLE = "accela_details"
IDENTITY_COLUMN = "permit_number"
MAX_STRUCTURE_DEPTH = 32
SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")

FAMILY_SPECS = (
    {
        "family_id": "ENG-CR",
        "tokens": ("ENG", "CR"),
        "label": "water_wastewater_capacity_request",
        "description": "Fort Lauderdale water/wastewater capacity availability request",
        "parent_only": True,
    },
    {
        "family_id": "ENG-OAA",
        "tokens": ("ENG", "OAA"),
        "label": "outside_agency_engineering_intake",
        "description": "Fort Lauderdale outside-agency engineering intake",
        "parent_only": True,
    },
    {
        "family_id": "ROW-SEW",
        "tokens": ("ROW", "SEW"),
        "label": "sewer_right_of_way",
        "description": "Fort Lauderdale sewer right-of-way work",
        "parent_only": False,
    },
    {
        "family_id": "ROW-WTR",
        "tokens": ("ROW", "WTR"),
        "label": "water_right_of_way",
        "description": "Fort Lauderdale water right-of-way work",
        "parent_only": False,
    },
    {
        "family_id": "PLB-SEWCP-WT",
        "tokens": ("PLB", "SEWCP", "WT"),
        "label": "sewer_cap_walk_through",
        "description": "Fort Lauderdale sewer-cap walk-through record",
        "parent_only": False,
    },
)
FAMILY_IDS = tuple(spec["family_id"] for spec in FAMILY_SPECS)
FAMILIES_LONGEST_FIRST = tuple(
    sorted(FAMILY_SPECS, key=lambda spec: len(spec["tokens"]), reverse=True)
)
BROAD_NEGATIVE_PREFIXES = ("ENG-", "ROW-", "PLB-", "TMP-")

APPLICATION_CLOCK_COLUMN = "applied_date"
EVENT_CLOCK_COLUMNS = {
    "opened_at": "opened_date",
    "issued_at": "issued_date",
    "finalized_at": "finalized_date",
    "status_date": "status_date",
}
SOURCE_MODIFIED_COLUMNS = ("source_modified_at", "source_last_modified_at")
PULL_CLOCK_COLUMNS = ("first_seen_at", "last_seen_at")
CAP_ID_KEYS = ("capID1", "capID2", "capID3")
CAP_ID_OPTIONAL_KEYS = ("agencyCode", "Module", "TabName")

ENRICHMENT_COLUMNS = frozenset(
    {
        "address_normalized",
        "street_normalized",
        "owner_normalized",
        "contractor_normalized",
        "cleaned_at",
        "cleaned_by",
        "ai_clean_json",
        "work_type",
        "valuation_usd_clean",
        "parcel_id_verified",
        "parcel_source",
        "lat",
        "lon",
        "geo_source",
        "geocoded_at",
        "geo_match_confidence",
        "permit_category",
        "is_commercial",
        "category_source",
        "category_confidence",
        "contractor_needs_review",
        "contractor_sunbiz_doc",
        "owner_sunbiz_doc",
        "owner_source",
        "is_commercial_source",
        "source_bcpa",
        "source_bcpa_method",
        "source_sunbiz",
        "last_enriched_at",
        "enrichment_version",
        "invalid",
        "invalid_reason",
        "parcel_checked_at",
    }
)
SECRET_KEY_RE = re.compile(
    r"(secret|password|token|api[_-]?key|authorization|private[_-]?key)",
    re.IGNORECASE,
)
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class CollectorError(RuntimeError):
    """Base class for a fail-closed collector error."""


class SourceContractError(CollectorError):
    """The supplied SQLite database cannot support an evidence-safe view."""


@dataclass(frozen=True)
class FamilyMatch:
    family_id: str
    tokens: tuple[str, ...]
    label: str
    description: str


def canonical_json_bytes(value: Any) -> bytes:
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


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("clock must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and value != value:
            return None
        return value
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.isoformat()
        return iso_utc(value)
    return str(value)


def sanitize_value(value: Any, *, depth: int = 0) -> tuple[Any, int]:
    if depth > MAX_STRUCTURE_DEPTH:
        return "<omitted_structure_too_deep>", 1
    if isinstance(value, Mapping):
        return sanitize_mapping(value, depth=depth)
    if isinstance(value, list):
        redacted = 0
        out = []
        for item in value:
            sanitized, count = sanitize_value(item, depth=depth + 1)
            out.append(sanitized)
            redacted += count
        return out, redacted
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            return None, 0
    if isinstance(value, str):
        stripped = value.strip()
        if stripped[:1] in "{[":
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                if SECRET_KEY_RE.search(value):
                    return "<omitted_unparseable_structured_content>", 1
                return value, 0
            return sanitize_value(parsed, depth=depth + 1)
        return value, 0
    return json_safe(value), 0


def sanitize_mapping(value: Mapping[str, Any], *, depth: int = 0) -> tuple[dict[str, Any], int]:
    redacted = 0
    out: dict[str, Any] = {}
    for key, item in value.items():
        name = str(key)
        if SECRET_KEY_RE.search(name):
            out[name] = "<redacted>"
            redacted += 1
            continue
        sanitized, count = sanitize_value(item, depth=depth + 1)
        out[name] = sanitized
        redacted += count
    return out, redacted


def empty_family_counts() -> dict[str, int]:
    return {family_id: 0 for family_id in FAMILY_IDS}


def classify_record_number(permit_number: str) -> FamilyMatch | None:
    tokens = permit_number.split("-")
    for spec in FAMILIES_LONGEST_FIRST:
        family_tokens = spec["tokens"]
        if len(tokens) <= len(family_tokens):
            continue
        if tuple(tokens[: len(family_tokens)]) != family_tokens:
            continue
        if any(not token for token in tokens):
            return None
        if spec.get("parent_only") and "." in permit_number:
            return None
        return FamilyMatch(
            family_id=spec["family_id"],
            tokens=family_tokens,
            label=spec["label"],
            description=spec["description"],
        )
    return None


def broad_negative_prefix(permit_number: str) -> str | None:
    for prefix in BROAD_NEGATIVE_PREFIXES:
        if permit_number.startswith(prefix):
            return prefix.rstrip("-")
    return None


def clock_value(row: Mapping[str, Any], column: str, available: set[str]) -> dict[str, Any]:
    if column not in available:
        return {"value": None, "status": "UNKNOWN_COLUMN_ABSENT", "column": column}
    value = json_safe(row.get(column))
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return {"value": None, "status": "UNKNOWN_VALUE_ABSENT", "column": column}
    if isinstance(value, str):
        return {"value": value, "status": "PRESENT", "column": column}
    return {"value": str(value), "status": "PRESENT", "column": column}


def _first_present_qualified_clock(
    row: Mapping[str, Any] | None, available: set[str]
) -> dict[str, Any] | None:
    if row is None:
        return None
    for column in SOURCE_MODIFIED_COLUMNS:
        if column not in available:
            continue
        result = clock_value(row, column, available)
        if result["status"] == "PRESENT":
            return result
    return None


def source_modified_clock(
    permit_row: Mapping[str, Any],
    permit_columns: set[str],
    supporting: Mapping[str, Any] | None = None,
    supporting_columns: set[str] | None = None,
) -> dict[str, Any]:
    if supporting is None:
        supporting_columns = set()
    else:
        supporting_columns = supporting_columns or set()
    note = (
        "Only source_modified_at or source_last_modified_at may be used; "
        "generic last_updated_at is not a source-modified clock."
    )
    supporting_clock = _first_present_qualified_clock(supporting, supporting_columns)
    if supporting_clock is not None:
        supporting_clock["origin"] = ACCELA_DETAILS_TABLE
        supporting_clock["note"] = note
        return supporting_clock
    permit_clock = _first_present_qualified_clock(permit_row, permit_columns)
    if permit_clock is not None:
        permit_clock["origin"] = PERMITS_TABLE
        permit_clock["note"] = note
        return permit_clock
    available = set(permit_columns) | set(supporting_columns)
    present_columns = [column for column in SOURCE_MODIFIED_COLUMNS if column in available]
    if not present_columns:
        return {
            "value": None,
            "status": "UNKNOWN_COLUMN_ABSENT",
            "column": None,
            "origin": None,
            "note": note,
        }
    origin = (
        ACCELA_DETAILS_TABLE
        if any(column in supporting_columns for column in present_columns)
        else PERMITS_TABLE
    )
    return {
        "value": None,
        "status": "UNKNOWN_VALUE_ABSENT",
        "column": present_columns[0],
        "origin": origin,
        "note": note,
    }


def parse_cap_id(source_url: Any) -> dict[str, Any]:
    if source_url is None or (isinstance(source_url, str) and source_url.strip() == ""):
        return {"value": None, "status": "UNKNOWN_VALUE_ABSENT"}
    if not isinstance(source_url, str):
        return {"value": None, "status": "UNKNOWN_NOT_EXPOSED"}
    parsed = urllib.parse.urlparse(source_url)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    cap: dict[str, str] = {}
    for key in CAP_ID_KEYS:
        values = query.get(key) or query.get(key.lower()) or []
        if len(values) != 1 or not str(values[0]).strip():
            return {"value": None, "status": "UNKNOWN_NOT_EXPOSED"}
        cap[key] = str(values[0]).strip()
    for key in CAP_ID_OPTIONAL_KEYS:
        values = query.get(key) or query.get(key.lower()) or []
        if len(values) == 1 and str(values[0]).strip():
            cap[key] = str(values[0]).strip()
    return {"value": cap, "status": "PRESENT"}


def sidecar_paths(sqlite_path: Path) -> dict[str, Path]:
    return {
        suffix.lstrip("-"): sqlite_path.with_name(sqlite_path.name + suffix)
        for suffix in SIDECAR_SUFFIXES
    }


def file_stat_snapshot(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {
        "size_bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "inode": int(stat.st_ino),
        "device": int(stat.st_dev),
    }


def sidecar_snapshot(sqlite_path: Path) -> dict[str, dict[str, Any]]:
    observed: dict[str, dict[str, Any]] = {}
    for name, path in sidecar_paths(sqlite_path).items():
        try:
            stat = file_stat_snapshot(path)
        except FileNotFoundError:
            observed[name] = {"exists": False, "stat": None}
        else:
            observed[name] = {"exists": True, "stat": stat}
    return observed


def validate_sidecar_preflight(sqlite_path: Path) -> dict[str, dict[str, Any]]:
    observed = sidecar_snapshot(sqlite_path)
    if observed["journal"]["exists"]:
        raise SourceContractError("refusing an active SQLite rollback journal sidecar")
    if observed["wal"]["exists"] != observed["shm"]["exists"]:
        raise SourceContractError("refusing an incomplete SQLite WAL/SHM sidecar pair")
    return observed


def validate_sidecar_postflight(
    before: Mapping[str, Mapping[str, Any]],
    after: Mapping[str, Mapping[str, Any]],
    journal_mode: Any,
) -> tuple[dict[str, Any], str | None]:
    mode = str(journal_mode or "").strip().lower()
    wal_before = bool(before["wal"]["exists"])
    wal_after = bool(after["wal"]["exists"])
    shm_before = bool(before["shm"]["exists"])
    shm_after = bool(after["shm"]["exists"])
    journal_absent = not before["journal"]["exists"] and not after["journal"]["exists"]
    pair_stable = wal_before == wal_after and shm_before == shm_after
    wal_stat_stable = (
        before["wal"]["stat"] == after["wal"]["stat"] if wal_before and wal_after else None
    )
    shm_identity_stable = None
    if shm_before and shm_after:
        shm_identity_stable = all(
            before["shm"]["stat"][field] == after["shm"]["stat"][field]
            for field in ("inode", "device")
        )

    errors = []
    if not journal_absent:
        errors.append("SQLite rollback journal appeared during the read")
    if not pair_stable:
        errors.append("SQLite WAL/SHM sidecar presence changed during the read")
    if (wal_before or wal_after) and mode != "wal":
        errors.append("SQLite WAL/SHM sidecars exist but PRAGMA journal_mode is not wal")
    if wal_stat_stable is False:
        errors.append("SQLite WAL changed during the read")
    if shm_identity_stable is False:
        errors.append("SQLite SHM file identity changed during the read")

    result = {
        "snapshot_mode": "wal_read_transaction" if wal_before else "main_database_read_transaction",
        "journal_mode": mode or None,
        "before": dict(before),
        "after": dict(after),
        "wal_shm_presence_stable": pair_stable,
        "wal_stat_stable": wal_stat_stable,
        "shm_identity_stable": shm_identity_stable,
        "rollback_journal_absent": journal_absent,
        "contract_passed": not errors,
        "note": (
            "A WAL-mode read is one SQLite BEGIN DEFERRED snapshot. The cooperative "
            "writer lock, stable main database and WAL stats, stable SHM identity, "
            "and PRAGMA data_version provide the live-read evidence boundary. SHM "
            "mtime/size may change when SQLite registers a reader."
            if wal_before
            else "No SQLite sidecars were present during the read transaction."
        ),
    }
    error = "; ".join(errors) if errors else None
    return result, error


@contextmanager
def acquire_shared_lock(path: Path) -> Iterator[None]:
    if not path.is_absolute():
        raise CollectorError("--writer-lock-path must be an explicit absolute path")
    if not path.is_file():
        raise CollectorError("writer-lock path does not exist")
    fd = os.open(path, os.O_RDONLY)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in {errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK}:
                raise CollectorError(
                    "writer lock is held exclusively; refusing to read"
                ) from exc
            raise
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(fd)


def connect_query_only(path: Path) -> sqlite3.Connection:
    if not path.is_absolute():
        raise CollectorError("--sqlite-path must be an explicit absolute path")
    if not path.is_file():
        raise SourceContractError("sqlite path is not a file")
    uri = path.as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.isolation_level = None
    connection.execute("PRAGMA query_only = ON")
    flag = connection.execute("PRAGMA query_only").fetchone()[0]
    if int(flag) != 1:
        connection.close()
        raise CollectorError("PRAGMA query_only is not enabled")
    return connection


def list_tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {str(row["name"]) for row in rows}


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def table_columns(connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
        raise SourceContractError("refusing a non-contract table name")
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return [
        {
            "cid": int(row["cid"]),
            "name": str(row["name"]),
            "type": str(row["type"] or ""),
            "notnull": int(row["notnull"]),
            "pk": int(row["pk"]),
        }
        for row in rows
    ]


def table_quick_check(connection: sqlite3.Connection, table: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
        raise SourceContractError("refusing a non-contract table name")
    rows = connection.execute(f"PRAGMA quick_check({table})").fetchall()
    values = [str(row[0]) for row in rows]
    if values != ["ok"]:
        raise SourceContractError(
            f"PRAGMA quick_check({table}) failed: {values[:8]}"
        )
    return "ok"


def sqlite_metadata(connection: sqlite3.Connection, data_version: int) -> dict[str, Any]:
    def pragma(name: str) -> Any:
        row = connection.execute(f"PRAGMA {name}").fetchone()
        return row[0] if row is not None else None

    return {
        "data_version": int(data_version),
        "page_count": int(pragma("page_count") or 0),
        "page_size": int(pragma("page_size") or 0),
        "user_version": int(pragma("user_version") or 0),
        "application_id": int(pragma("application_id") or 0),
        "schema_version": int(pragma("schema_version") or 0),
        "encoding": pragma("encoding"),
        "journal_mode": pragma("journal_mode"),
    }


def load_accela_details(
    connection: sqlite3.Connection, tables: set[str]
) -> tuple[dict[str, dict[str, Any]], dict[str, Any], set[str], list[dict[str, Any]]]:
    if ACCELA_DETAILS_TABLE not in tables:
        return (
            {},
            {"present": False, "rows": 0, "duplicate_identities": 0},
            set(),
            [],
        )
    columns = table_columns(connection, ACCELA_DETAILS_TABLE)
    names = [column["name"] for column in columns]
    if IDENTITY_COLUMN not in names:
        return (
            {},
            {"present": True, "rows": 0, "duplicate_identities": 0},
            set(names),
            columns,
        )
    quoted = ", ".join(quote_ident(name) for name in names)
    rows = connection.execute(
        f"SELECT {quoted} FROM {quote_ident(ACCELA_DETAILS_TABLE)}"
        f" ORDER BY {quote_ident(IDENTITY_COLUMN)} ASC, rowid ASC"
    ).fetchall()
    indexed: dict[str, dict[str, Any]] = {}
    duplicates = 0
    duplicate_ids: set[str] = set()
    for row in rows:
        payload = {key: row[key] for key in names}
        identity = payload.get(IDENTITY_COLUMN)
        if not isinstance(identity, str) or not identity:
            continue
        if identity in duplicate_ids:
            duplicates += 1
            continue
        if identity in indexed:
            duplicates += 1
            indexed.pop(identity, None)
            duplicate_ids.add(identity)
            continue
        indexed[identity] = payload
    return (
        indexed,
        {
            "present": True,
            "rows": len(rows),
            "duplicate_identities": duplicates,
        },
        set(names),
        columns,
    )


def validate_identity(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    if value != value.strip() or value == "":
        return None
    if any(ord(char) < 32 for char in value):
        return None
    if len(value) > 128:
        return None
    return value


def source_fields_from_row(
    row: Mapping[str, Any], available: set[str]
) -> tuple[dict[str, Any], dict[str, Any], int]:
    source: dict[str, Any] = {}
    enrichment: dict[str, Any] = {}
    redacted = 0
    for column in sorted(available):
        sanitized, count = sanitize_value(row.get(column))
        if SECRET_KEY_RE.search(column):
            target = enrichment if column in ENRICHMENT_COLUMNS else source
            target[column] = "<redacted>"
            redacted += 1 + count
            continue
        redacted += count
        if column in ENRICHMENT_COLUMNS:
            enrichment[column] = sanitized
        else:
            source[column] = sanitized
    return source, enrichment, redacted


def cap_id_from_rows(
    *,
    permit_row: Mapping[str, Any],
    permit_columns: set[str],
    supporting: Mapping[str, Any] | None,
    accela_details_present: bool,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    if supporting is not None and "source_url" in supporting:
        candidates.append(parse_cap_id(supporting.get("source_url")))
    if "source_url" in permit_columns:
        candidates.append(parse_cap_id(permit_row.get("source_url")))
    for parsed in candidates:
        if parsed.get("status") == "PRESENT":
            return parsed
    if candidates:
        return candidates[0]
    if not accela_details_present:
        return {"value": None, "status": "UNKNOWN_TABLE_ABSENT"}
    return {"value": None, "status": "UNKNOWN_VALUE_ABSENT"}


def build_observation(
    *,
    identity: str,
    family: FamilyMatch,
    permit_row: Mapping[str, Any],
    permit_columns: set[str],
    supporting: Mapping[str, Any] | None,
    supporting_columns: set[str],
    accela_details_present: bool,
    observed_at: str,
) -> tuple[dict[str, Any], int]:
    source, enrichment, redacted = source_fields_from_row(permit_row, permit_columns)
    supporting_source: dict[str, Any] | None = None
    if supporting is not None:
        supporting_source, supporting_enrichment, extra_redacted = source_fields_from_row(
            supporting, supporting_columns
        )
        enrichment.update(
            {
                f"accela_details.{key}": value
                for key, value in supporting_enrichment.items()
            }
        )
        redacted += extra_redacted
    cap_id = cap_id_from_rows(
        permit_row=permit_row,
        permit_columns=permit_columns,
        supporting=supporting,
        accela_details_present=accela_details_present,
    )

    event_clocks = {
        name: clock_value(permit_row, column, permit_columns)
        for name, column in EVENT_CLOCK_COLUMNS.items()
        if name != "status_date"
    }
    status_column = EVENT_CLOCK_COLUMNS["status_date"]
    if supporting is not None and status_column in supporting_columns:
        event_clocks["status_date"] = clock_value(
            supporting, status_column, supporting_columns
        )
    elif status_column in permit_columns:
        event_clocks["status_date"] = clock_value(
            permit_row, status_column, permit_columns
        )
    elif accela_details_present and status_column in supporting_columns:
        event_clocks["status_date"] = {
            "value": None,
            "status": "UNKNOWN_VALUE_ABSENT",
            "column": status_column,
        }
    else:
        event_clocks["status_date"] = {
            "value": None,
            "status": (
                "UNKNOWN_TABLE_ABSENT"
                if not accela_details_present
                else "UNKNOWN_COLUMN_ABSENT"
            ),
            "column": status_column,
        }

    application_clock = clock_value(permit_row, APPLICATION_CLOCK_COLUMN, permit_columns)
    source_modified = source_modified_clock(
        permit_row,
        permit_columns,
        supporting=supporting,
        supporting_columns=supporting_columns,
    )
    pull_clocks = {
        column: clock_value(permit_row, column, permit_columns)
        for column in PULL_CLOCK_COLUMNS
    }
    content_payload = {
        "identity": identity,
        "family_id": family.family_id,
        "cap_id": cap_id,
        "source": {
            key: value for key, value in source.items() if key not in PULL_CLOCK_COLUMNS
        },
        "supporting_source": (
            {
                key: value
                for key, value in (supporting_source or {}).items()
                if key not in PULL_CLOCK_COLUMNS
            }
            if supporting_source is not None
            else None
        ),
        "application_clock": application_clock,
        "event_clocks": event_clocks,
        "source_modified_clock": source_modified,
    }
    record = {
        "identity": {
            "permit_number": identity,
            "family_id": family.family_id,
            "family_label": family.label,
            "family_description": family.description,
            "record_role": "subpermit" if "." in identity else "parent",
        },
        "cap_id": cap_id,
        "source": source,
        "supporting_source": supporting_source,
        "non_authoritative_enrichment": enrichment or None,
        "clocks": {
            "application": application_clock,
            "event": event_clocks,
            "source_modified": source_modified,
            "pull": pull_clocks,
            "observed_at": observed_at,
            "observed_at_semantics": "collector generated-at clock; not a source event",
        },
        "timing_claims": {
            "earlier_than_pdmr": False,
            "earlier_than_permits": False,
            "allowed_claim": "none",
        },
        "source_content_sha256": sha256_bytes(canonical_json_bytes(content_payload)),
    }
    return record, redacted


class EvidenceBundle:
    """Write one new run directory; never overwrite an existing run."""

    def __init__(self, output_root: Path, run_id: str) -> None:
        if not output_root.is_absolute():
            raise CollectorError("--output-dir must be an explicit absolute path")
        if not RUN_ID_RE.fullmatch(run_id):
            raise CollectorError("run_id contains unsafe characters")
        output_root.mkdir(parents=True, exist_ok=True)
        self.run_dir = output_root / run_id
        self.run_dir.mkdir(mode=0o700)

    @staticmethod
    def _write_private_create_only(path: Path, body: bytes) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(path, flags, 0o600)
        try:
            view = memoryview(body)
            offset = 0
            while offset < len(body):
                written = os.write(fd, view[offset:])
                if written <= 0:
                    raise OSError("evidence-file write made no forward progress")
                offset += written
        except Exception:
            os.close(fd)
            try:
                path.unlink()
            except OSError:
                pass
            raise
        os.close(fd)

    def write_json(self, name: str, value: Any) -> tuple[Path, str]:
        body = canonical_json_bytes(value)
        path = self.run_dir / name
        self._write_private_create_only(path, body)
        return path, sha256_bytes(body)

    def write_jsonl(self, name: str, rows: Sequence[Mapping[str, Any]]) -> tuple[Path, str]:
        body = b"".join(canonical_json_bytes(row) for row in rows)
        path = self.run_dir / name
        self._write_private_create_only(path, body)
        return path, sha256_bytes(body)


def inspect_schema(
    connection: sqlite3.Connection,
) -> tuple[set[str], list[dict[str, Any]], set[str]]:
    tables = list_tables(connection)
    if PERMITS_TABLE not in tables:
        raise SourceContractError("required table permits is absent")
    columns = table_columns(connection, PERMITS_TABLE)
    names = {column["name"] for column in columns}
    if IDENTITY_COLUMN not in names:
        raise SourceContractError("permits.permit_number is absent")
    return tables, columns, names


def logical_input_database_fingerprint(
    *,
    schema_projection: dict[str, Any] | None,
    sqlite_meta: dict[str, Any] | None,
    counts: Mapping[str, int],
    family_counts: Mapping[str, int],
    unknown_counts: Mapping[str, int],
    content_index: Sequence[Mapping[str, Any]],
    rejected_index: Sequence[Mapping[str, Any]],
    unknown_identities: Sequence[str],
) -> str:
    payload = {
        "fingerprint_kind": "contract_relevant_logical_projection",
        "schema_projection": schema_projection,
        "sqlite_metadata": sqlite_meta,
        "rows_scanned": counts.get("rows_scanned", 0),
        "counts": {
            "rows_admitted": counts.get("rows_admitted", 0),
            "rows_rejected": counts.get("rows_rejected", 0),
            "rows_unknown": counts.get("rows_unknown", 0),
        },
        "family_counts": dict(family_counts),
        "unknown_prefix_counts": dict(unknown_counts),
        "admitted_content_index": list(content_index),
        "rejected_index": list(rejected_index),
        "unknown_identity_index": list(unknown_identities),
    }
    return sha256_bytes(canonical_json_bytes(payload))


def run_collection(
    *,
    sqlite_path: Path,
    output_root: Path,
    writer_lock_path: Path,
    run_id: str | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> tuple[Path, dict[str, Any]]:
    started_at = iso_utc(clock())
    if run_id is None:
        run_id = "utility-intake-" + started_at.replace(":", "").replace("-", "")
    sqlite_path = Path(sqlite_path)
    writer_lock_path = Path(writer_lock_path)
    if not sqlite_path.is_absolute():
        raise CollectorError("--sqlite-path must be an explicit absolute path")
    if not sqlite_path.is_file():
        raise SourceContractError("sqlite path is not a file")

    with acquire_shared_lock(writer_lock_path):
        lock_stat_before = file_stat_snapshot(writer_lock_path)
        writer_lock = {
            "path": str(writer_lock_path),
            "basename": writer_lock_path.name,
            "stat_before": lock_stat_before,
            "stat_after": None,
            "stat_unchanged": False,
            "mode": "shared_nonblocking",
        }
        sidecars_before = validate_sidecar_preflight(sqlite_path)
        stat_before = file_stat_snapshot(sqlite_path)
        bundle = EvidenceBundle(output_root, run_id)
        observed_at = iso_utc(clock())
        snapshot = _read_snapshot(sqlite_path, observed_at)
        stat_after = file_stat_snapshot(sqlite_path)
        snapshot["file_stat"] = stat_after
        if stat_after != stat_before:
            snapshot["terminal_error"] = snapshot["terminal_error"] or (
                "SourceContractError: SQLite file stat changed during the read"
            )
            snapshot["stat_unchanged"] = False
        else:
            snapshot["stat_unchanged"] = True
        sidecars_after = sidecar_snapshot(sqlite_path)
        sidecars, sidecar_error = validate_sidecar_postflight(
            sidecars_before,
            sidecars_after,
            (snapshot.get("sqlite_metadata") or {}).get("journal_mode"),
        )
        snapshot["sidecars"] = sidecars
        if sidecar_error:
            snapshot["terminal_error"] = snapshot["terminal_error"] or (
                f"SourceContractError: {sidecar_error}"
            )
        try:
            lock_stat_after = file_stat_snapshot(writer_lock_path)
            writer_lock["stat_after"] = lock_stat_after
            writer_lock["stat_unchanged"] = lock_stat_after == lock_stat_before
            if lock_stat_after != lock_stat_before:
                snapshot["terminal_error"] = snapshot["terminal_error"] or (
                    "SourceContractError: writer-lock path identity changed during the read"
                )
        except OSError as exc:
            snapshot["terminal_error"] = snapshot["terminal_error"] or (
                f"SourceContractError: writer-lock path unavailable after read: {exc}"
            )

    return _write_bundle(
        bundle=bundle,
        sqlite_path=sqlite_path,
        writer_lock=writer_lock,
        run_id=run_id,
        started_at=started_at,
        observed_at=observed_at,
        clock=clock,
        snapshot=snapshot,
        sidecars=sidecars,
    )


def _read_snapshot(sqlite_path: Path, observed_at: str) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "terminal_error": None,
        "query_only": False,
        "schema_projection": None,
        "sqlite_metadata": None,
        "data_version_start": None,
        "data_version_end": None,
        "data_version_stable": False,
        "quick_check": {},
        "accela_stats": {"present": False, "rows": 0, "duplicate_identities": 0},
        "rows": [],
        "rejected_rows": [],
        "unknown_identities": [],
        "family_counts": empty_family_counts(),
        "unknown_counts": {"ENG": 0, "ROW": 0, "PLB": 0, "TMP": 0, "other": 0},
        "counts": {
            "rows_scanned": 0,
            "rows_admitted": 0,
            "rows_rejected": 0,
            "rows_unknown": 0,
            "duplicate_identities": 0,
            "secrets_redacted": 0,
        },
        "rejection_reasons": {},
    }
    connection: sqlite3.Connection | None = None
    try:
        connection = connect_query_only(sqlite_path)
        snapshot["query_only"] = (
            int(connection.execute("PRAGMA query_only").fetchone()[0]) == 1
        )
        data_version_start = int(connection.execute("PRAGMA data_version").fetchone()[0])
        snapshot["data_version_start"] = data_version_start
        connection.execute("BEGIN DEFERRED")
        tables, column_meta, permit_columns = inspect_schema(connection)
        snapshot["quick_check"][PERMITS_TABLE] = table_quick_check(
            connection, PERMITS_TABLE
        )
        supporting_rows, accela_stats, supporting_columns, accela_columns = (
            load_accela_details(connection, tables)
        )
        snapshot["accela_stats"] = accela_stats
        if accela_stats.get("present"):
            snapshot["quick_check"][ACCELA_DETAILS_TABLE] = table_quick_check(
                connection, ACCELA_DETAILS_TABLE
            )
        snapshot["schema_projection"] = {
            "tables": sorted(tables),
            "permits_columns": column_meta,
            "accela_details_columns": accela_columns or None,
        }
        quoted = ", ".join(quote_ident(name) for name in sorted(permit_columns))
        fetched = connection.execute(
            f"SELECT {quoted} FROM {quote_ident(PERMITS_TABLE)}"
            f" ORDER BY {quote_ident(IDENTITY_COLUMN)} ASC, rowid ASC"
        ).fetchall()
        scanned_count = connection.execute(
            f"SELECT COUNT(*) AS n FROM {quote_ident(PERMITS_TABLE)}"
        ).fetchone()["n"]
        if int(scanned_count) != len(fetched):
            raise SourceContractError("permits row count changed during the read")
        snapshot["counts"]["rows_scanned"] = len(fetched)
        seen_identities: set[str] = set()
        for row in fetched:
            payload = {key: row[key] for key in permit_columns}
            identity = validate_identity(payload.get(IDENTITY_COLUMN))
            if identity is None:
                snapshot["counts"]["rows_rejected"] += 1
                reason = "malformed_permit_number"
                snapshot["rejection_reasons"][reason] = (
                    snapshot["rejection_reasons"].get(reason, 0) + 1
                )
                snapshot["rejected_rows"].append(
                    {
                        "permit_number": json_safe(payload.get(IDENTITY_COLUMN)),
                        "reason": reason,
                    }
                )
                continue
            family = classify_record_number(identity)
            if family is None:
                snapshot["counts"]["rows_unknown"] += 1
                snapshot["unknown_identities"].append(identity)
                broad = broad_negative_prefix(identity)
                snapshot["unknown_counts"][broad or "other"] += 1
                continue
            if identity in seen_identities:
                snapshot["counts"]["rows_rejected"] += 1
                snapshot["counts"]["duplicate_identities"] += 1
                reason = "duplicate_business_identity"
                snapshot["rejection_reasons"][reason] = (
                    snapshot["rejection_reasons"].get(reason, 0) + 1
                )
                snapshot["rejected_rows"].append(
                    {
                        "permit_number": identity,
                        "family_id": family.family_id,
                        "reason": reason,
                    }
                )
                continue
            seen_identities.add(identity)
            record, redacted = build_observation(
                identity=identity,
                family=family,
                permit_row=payload,
                permit_columns=permit_columns,
                supporting=supporting_rows.get(identity),
                supporting_columns=supporting_columns,
                accela_details_present=bool(accela_stats.get("present")),
                observed_at=observed_at,
            )
            snapshot["counts"]["secrets_redacted"] += redacted
            snapshot["rows"].append(record)
            snapshot["family_counts"][family.family_id] += 1
            snapshot["counts"]["rows_admitted"] += 1
        snapshot["rows"].sort(key=lambda item: item["identity"]["permit_number"])
        snapshot["rejected_rows"].sort(
            key=lambda item: (
                str(item.get("permit_number") or ""),
                item.get("reason") or "",
            )
        )
        snapshot["unknown_identities"].sort()
        snapshot["sqlite_metadata"] = sqlite_metadata(connection, data_version_start)
        connection.execute("COMMIT")
        # Inside a read transaction, data_version is snapshot-stable even when a
        # different connection commits to the WAL. Re-read only after COMMIT so
        # equality is meaningful concurrent-write evidence.
        data_version_end = int(connection.execute("PRAGMA data_version").fetchone()[0])
        snapshot["data_version_end"] = data_version_end
        if data_version_start != data_version_end:
            raise SourceContractError("PRAGMA data_version changed during the read")
        snapshot["data_version_stable"] = True
    except (CollectorError, sqlite3.Error, OSError, ValueError) as exc:
        snapshot["terminal_error"] = f"{type(exc).__name__}: {exc}"
        if connection is not None:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
    finally:
        if connection is not None:
            connection.close()
    return snapshot


def _write_bundle(
    *,
    bundle: EvidenceBundle,
    sqlite_path: Path,
    writer_lock: Mapping[str, Any],
    run_id: str,
    started_at: str,
    observed_at: str,
    clock: Callable[[], datetime],
    snapshot: dict[str, Any],
    sidecars: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    rows = snapshot["rows"]
    rejected_rows = snapshot["rejected_rows"]
    counts = snapshot["counts"]
    family_counts = snapshot["family_counts"]
    unknown_counts = snapshot["unknown_counts"]
    terminal_error = snapshot["terminal_error"]
    finished_at = iso_utc(clock())
    accounting_ok = counts["rows_scanned"] == (
        counts["rows_admitted"] + counts["rows_rejected"] + counts["rows_unknown"]
    )
    if terminal_error:
        status = "failed"
        reason_code = "COLLECTOR_OR_CONTRACT_FAILURE"
    elif counts["rows_rejected"] or not accounting_ok:
        status = "partial"
        reason_code = "ROW_QUALITY_OR_ACCOUNTING_FAILURE"
    elif counts["rows_admitted"] == 0:
        status = "empty"
        reason_code = None
    else:
        status = "ok"
        reason_code = None

    content_index = [
        {
            "permit_number": row["identity"]["permit_number"],
            "family_id": row["identity"]["family_id"],
            "source_content_sha256": row["source_content_sha256"],
        }
        for row in rows
    ]
    identity_fingerprint = sha256_bytes(
        canonical_json_bytes([item["permit_number"] for item in content_index])
    )
    content_fingerprint = sha256_bytes(canonical_json_bytes(content_index))
    logical_fingerprint = logical_input_database_fingerprint(
        schema_projection=snapshot["schema_projection"],
        sqlite_meta=snapshot["sqlite_metadata"],
        counts=counts,
        family_counts=family_counts,
        unknown_counts=unknown_counts,
        content_index=content_index,
        rejected_index=rejected_rows,
        unknown_identities=snapshot["unknown_identities"],
    )
    schema_contract = {
        "schema_version": "FloridaSignalUtilityIntakeSqliteContractV2",
        "required_table": PERMITS_TABLE,
        "required_identity": IDENTITY_COLUMN,
        "families": list(FAMILY_SPECS),
        "broad_prefixes_excluded": list(BROAD_NEGATIVE_PREFIXES),
        "source_modified_columns": list(SOURCE_MODIFIED_COLUMNS),
        "mode": "shadow_file_only",
    }
    schema_contract_sha = sha256_bytes(canonical_json_bytes(schema_contract))
    source_schema_sha = (
        sha256_bytes(canonical_json_bytes(snapshot["schema_projection"]))
        if snapshot["schema_projection"] is not None
        else None
    )

    _, records_sha = bundle.write_jsonl("shadow-records.jsonl", rows)
    _, rejected_sha = bundle.write_jsonl("rejected-records.jsonl", rejected_rows)
    _, content_index_sha = bundle.write_jsonl("shadow-content-index.jsonl", content_index)
    observation_bundle = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "run_id": run_id,
        "mode": "shadow_file_only",
        "status": status,
        "generated_at": observed_at,
        "records": rows,
        "rejected": rejected_rows,
        "timing_claims": {
            "earlier_than_pdmr": False,
            "earlier_than_permits": False,
            "allowed_claim": "none",
            "note": (
                "This shadow view classifies already stored Fort Lauderdale "
                "record-number families. It does not rank any family as earlier "
                "than PDMR or other permits."
            ),
        },
    }
    _, observation_sha = bundle.write_json("observation-bundle.json", observation_bundle)

    receipt = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "mode": "shadow_file_only",
        "dry_run": True,
        "status": status,
        "reason_code": reason_code,
        "terminal_error": terminal_error,
        "source": {
            "agency": "City of Fort Lauderdale",
            "system": "LauderBuild / Accela records already stored in SQLite",
            "population": (
                "exact ENG-CR, ENG-OAA, ROW-SEW, ROW-WTR and PLB-SEWCP-WT "
                "record-number families"
            ),
            "serving_utility": "UNKNOWN_NOT_IN_SOURCE_ROW",
            "broward_wws_searched": False,
            "coverage_note": (
                "A Fort Lauderdale result cannot establish that Broward Water "
                "and Wastewater Services parcels were searched."
            ),
        },
        "input_database": {
            "path": str(sqlite_path),
            "basename": sqlite_path.name,
            "fingerprint_kind": "contract_relevant_logical_projection",
            "logical_fingerprint_note": (
                "SHA-256 of the contract-relevant logical projection: schema, "
                "SQLite metadata, row-count accounting, admitted content hashes, "
                "rejected index, and unknown identity list. Unknown-row source "
                "content is not hashed. This is not an exact or complete "
                "database snapshot hash and not a byte-for-byte file SHA-256."
            ),
            "stat": snapshot.get("file_stat"),
            "stat_unchanged": snapshot.get("stat_unchanged"),
            "query_only": snapshot["query_only"],
            "data_version_start": snapshot["data_version_start"],
            "data_version_end": snapshot["data_version_end"],
            "data_version_stable": snapshot["data_version_stable"],
            "data_version_contract": (
                "start sampled before BEGIN DEFERRED; end sampled after COMMIT; "
                "equality rejects a concurrent commit visible to this connection"
            ),
            "quick_check": snapshot["quick_check"],
            "sidecars": snapshot.get("sidecars") or sidecars,
            "writer_lock": dict(writer_lock),
        },
        "versions": {
            "collector": COLLECTOR_VERSION,
            "query": QUERY_VERSION,
            "parser": PARSER_VERSION,
        },
        "clocks": {
            "run_started_at": started_at,
            "generated_at": observed_at,
            "finished_at": finished_at,
            "source_modified_at": None,
            "source_modified_status": "UNKNOWN_PER_RECORD",
        },
        "counts": counts,
        "family_counts": family_counts,
        "unknown_prefix_counts": unknown_counts,
        "rejection_reasons": dict(sorted(snapshot["rejection_reasons"].items())),
        "accela_details": snapshot["accela_stats"],
        "timing_claims": {
            "earlier_than_pdmr": False,
            "earlier_than_permits": False,
            "allowed_claim": "none",
        },
        "hashes": {
            "schema_contract_sha256": schema_contract_sha,
            "source_schema_sha256": source_schema_sha,
            "logical_input_database_fingerprint": logical_fingerprint,
            "record_identity_fingerprint": identity_fingerprint,
            "content_fingerprint": content_fingerprint,
            "shadow_records_sha256": records_sha,
            "shadow_content_index_sha256": content_index_sha,
            "rejected_records_sha256": rejected_sha,
            "observation_bundle_sha256": observation_sha,
        },
        "quality": {
            "accounting_identity_passed": accounting_ok and terminal_error is None,
            "business_identity_unique": counts["duplicate_identities"] == 0,
            "query_only": snapshot["query_only"],
            "data_version_stable": snapshot["data_version_stable"],
            "stat_unchanged": bool(snapshot.get("stat_unchanged")),
            "sidecar_contract_passed": bool(sidecars.get("contract_passed")),
            "quick_check_passed": terminal_error is None
            and bool(snapshot["quick_check"]),
            "schema_contract_passed": source_schema_sha is not None,
        },
        "safety": {
            "query_only_sql": True,
            "collector_issued_source_row_writes": False,
            "collector_issued_main_database_content_writes": False,
            "collector_issued_wal_content_writes": False,
            "sqlite_shm_reader_metadata_may_change": True,
            "zero_filesystem_mutation_claimed": False,
            "supabase_writes": False,
            "queue_writes": False,
            "scoring": False,
            "candidate_scoring": False,
            "publication": False,
            "timer_created_or_changed": False,
            "service_created_or_changed": False,
            "desk_green_status": False,
            "connected_label_allowed": False,
            "production_admission": False,
            "promotion_eligible": False,
        },
    }
    _, receipt_sha = bundle.write_json("receipt.json", receipt)
    bundle.write_json(
        "bundle-manifest.json",
        {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "run_id": run_id,
            "generated_at": observed_at,
            "logical_input_database_fingerprint": logical_fingerprint,
            "query_version": QUERY_VERSION,
            "parser_version": PARSER_VERSION,
            "record_identity_fingerprint": identity_fingerprint,
            "content_fingerprint": content_fingerprint,
            "receipt_sha256": receipt_sha,
            "observation_bundle_sha256": observation_sha,
            "shadow_records_sha256": records_sha,
            "shadow_content_index_sha256": content_index_sha,
            "rejected_records_sha256": rejected_sha,
            "promotion_eligible": False,
            "connected_label_allowed": False,
        },
    )
    return bundle.run_dir, receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sqlite-path",
        required=True,
        type=Path,
        help="Explicit absolute SQLite database to read in query-only mode.",
    )
    parser.add_argument(
        "--writer-lock-path",
        required=True,
        type=Path,
        help="Explicit absolute existing writer-lock file for a shared nonblocking flock.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Explicit absolute root for the new shadow evidence bundle.",
    )
    parser.add_argument("--run-id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.sqlite_path.is_absolute():
        print("FATAL: --sqlite-path must be an explicit absolute path", file=sys.stderr)
        return 64
    if not args.writer_lock_path.is_absolute():
        print(
            "FATAL: --writer-lock-path must be an explicit absolute path",
            file=sys.stderr,
        )
        return 64
    if not args.output_dir.is_absolute():
        print("FATAL: --output-dir must be an explicit absolute path", file=sys.stderr)
        return 64
    try:
        run_dir, receipt = run_collection(
            sqlite_path=args.sqlite_path,
            output_root=args.output_dir,
            writer_lock_path=args.writer_lock_path,
            run_id=args.run_id,
        )
    except (CollectorError, OSError) as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 65
    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "status": receipt["status"],
                "mode": receipt["mode"],
                "dry_run": True,
                "promotion_eligible": False,
                "connected_label_allowed": False,
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["status"] in {"ok", "empty"} else 65


if __name__ == "__main__":
    raise SystemExit(main())
