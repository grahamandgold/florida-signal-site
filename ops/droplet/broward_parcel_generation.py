#!/usr/bin/env python3
"""Build a deterministic, evidence-preserving Broward parcel generation.

The collector is intentionally unable to promote a generation.  Its only live
write path is a narrow set of staging RPCs added by the companion migration.
The default invocation is a file-only, at-most-25-row canary.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence


SOURCE_LAYER_URL = (
    "https://services.arcgis.com/JMAJrTsHNLrSsWf5/arcgis/rest/services/"
    "PARCEL_POLY_BCPA_TAXROLL/FeatureServer/0"
)
SOURCE_ITEM_ID = "4b6c15240fdc492a87b8f984b11d2854"
SOURCE_ITEM_URL = (
    "https://www.arcgis.com/sharing/rest/content/items/"
    + SOURCE_ITEM_ID
)
SYSTEM_OBJECT_ID_FIELD = "OBJECTID_12"
STABLE_SOURCE_OBJECT_ID_FIELD = "OBJECTID"
WINNER_RULE = "minimum_numeric_OBJECTID_then_minimum_OBJECTID_12"
NORMALIZER_VERSION = "broward-folio-centroid-sale-date-v2"
FAILURE_EVIDENCE_MANIFEST_SCHEMA = (
    "FloridaSignalTerminalFailureEvidenceManifestV1"
)
SALE_DATE_FIELD = "SALE_DATE_1"
SALE_DATE_MIN = "0001-01-01"
SALE_DATE_MAX = "9999-12-31"
SALE_DATE_MIN_EPOCH_MS = -62_135_596_800_000
SALE_DATE_MAX_EPOCH_MS = 253_402_300_799_999
SALE_DATE_INVALID_REASON = "invalid_arcgis_epoch_milliseconds"
SALE_DATE_OUT_OF_RANGE_REASON = (
    "arcgis_epoch_milliseconds_out_of_supported_range"
)
SALE_DATE_NULL_REASONS = (
    SALE_DATE_INVALID_REASON,
    SALE_DATE_OUT_OF_RANGE_REASON,
)
SALE_DATE_FIELD_NULL_POLICY = {
    "field": SALE_DATE_FIELD,
    "invalid_value_policy": "field_null_with_reason_and_raw_attribute_v1",
    "source_encoding": "esriFieldTypeDate_epoch_milliseconds_utc",
    "supported_date_max": SALE_DATE_MAX,
    "supported_date_min": SALE_DATE_MIN,
}
PRODUCTION_QUALITY_CONTRACT = {
    "bbox": {
        "latitude_max": 26.50,
        "latitude_min": 25.90,
        "longitude_max": -79.98,
        "longitude_min": -80.70,
    },
    "field_null_policy": {"sale_date_1": SALE_DATE_FIELD_NULL_POLICY},
    "folio_normalizer": "uppercase_alphanumeric_exactly_12_nonzero_v1",
    "maximum_duplicate_rows": 25_000,
    "maximum_rejected_rows": 200,
    "maximum_source_rows": 560_000,
    "minimum_accepted_rows": 530_000,
    "minimum_source_rows": 550_000,
    "mode": "current_generation",
    "normalizer_version": NORMALIZER_VERSION,
    "range_width": 20_000,
    "schema_version": "FloridaSignalBrowardParcelQualityContractV2",
    "source_layer_url": SOURCE_LAYER_URL,
    "stable_source_object_id_field": STABLE_SOURCE_OBJECT_ID_FIELD,
    "system_object_id_field": SYSTEM_OBJECT_ID_FIELD,
    "winner_rule": WINNER_RULE,
}
CANARY_QUALITY_CONTRACT = {
    **PRODUCTION_QUALITY_CONTRACT,
    "maximum_duplicate_rows": 24,
    "maximum_rejected_rows": 24,
    "maximum_source_rows": 25,
    "minimum_accepted_rows": 1,
    "minimum_source_rows": 1,
    "mode": "canary",
}
REQUIRED_FIELDS = {
    SYSTEM_OBJECT_ID_FIELD,
    STABLE_SOURCE_OBJECT_ID_FIELD,
    "FOLIO",
    "FOLIO_NUMBER",
    "PARCEL_TYP",
    "USE_CODE",
    "USE_TYPE",
    "MUNICIPALITY",
    "SITUS_STREET_NUMBER",
    "SITUS_STREET_NUMBER_END",
    "SITUS_STREET_DIRECTION",
    "SITUS_STREET_POST_DIR",
    "SITUS_STREET_NAME",
    "SITUS_STREET_TYPE",
    "SITUS_CITY",
    "SITUS_ZIP_CODE",
    "SITUS_UNIT_NUMBER",
    "SALE_DATE_1",
    "DEED_TYPE_1",
    "STAMP_AMOUNT_1",
    "SALE1_CIN",
}
OUT_FIELDS = ",".join(sorted(REQUIRED_FIELDS))
FOLIO_RE = re.compile(r"^[A-Z0-9]{12}$")
WRITE_APPROVAL = "I_APPROVE_BROWARD_PARCEL_STAGING_ONLY"
DEFAULT_BUCKET = "fl-signal-source-evidence"


class ParcelGenerationError(RuntimeError):
    """Fail-closed collector error."""


class CapturedJson(dict):
    """Parsed JSON that still carries the exact observed response bytes."""

    def __init__(
        self,
        payload: Mapping[str, Any],
        *,
        raw_body: bytes,
        request_receipt: Mapping[str, Any],
    ):
        super().__init__(payload)
        self.raw_body = raw_body
        self.request_receipt = dict(request_receipt)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def contract_sha256(contract: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(contract))


PRODUCTION_QUALITY_CONTRACT_SHA256 = contract_sha256(PRODUCTION_QUALITY_CONTRACT)
CANARY_QUALITY_CONTRACT_SHA256 = contract_sha256(CANARY_QUALITY_CONTRACT)


def hash_lines(values: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(str(value).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def create_durable_directory(
    path: Path,
    *,
    mode: int = 0o700,
    exist_ok: bool = False,
) -> None:
    """Create each missing directory and durably persist its parent entry."""

    path = Path(path)
    if path.exists():
        if exist_ok and path.is_dir():
            return
        raise FileExistsError(path)
    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        parent = cursor.parent
        if parent == cursor:
            raise ParcelGenerationError(
                f"no existing parent for evidence directory: {path}"
            )
        cursor = parent
    if not cursor.is_dir():
        raise ParcelGenerationError(
            f"evidence directory parent is not a directory: {cursor}"
        )
    try:
        for directory in reversed(missing):
            os.mkdir(directory, mode)
            fsync_directory(directory.parent)
    except FileExistsError:
        if not (exist_ok and path.is_dir()):
            raise


def write_once(path: Path, body: bytes) -> str:
    create_durable_directory(path.parent, exist_ok=True)
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise ParcelGenerationError(f"immutable evidence already exists: {path}") from exc
    fsync_directory(path.parent)
    return sha256_bytes(body)


def normalize_folio(value: Any) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"[^A-Za-z0-9]", "", str(value)).upper()
    if not FOLIO_RE.fullmatch(normalized) or normalized == "000000000000":
        return None
    return normalized


def integer(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ParcelGenerationError(f"{label} is boolean, not an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"-?[0-9]+(?:\.0+)?", value.strip()):
        return int(float(value.strip()))
    raise ParcelGenerationError(f"{label} is not an exact integer: {value!r}")


def optional_text(value: Any) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None


def optional_number(value: Any) -> float | int | None:
    if value is None or value == "":
        return None
    try:
        rendered = float(value)
    except (TypeError, ValueError) as exc:
        raise ParcelGenerationError(f"invalid numeric value: {value!r}") from exc
    if not math.isfinite(rendered):
        raise ParcelGenerationError(f"non-finite numeric value: {value!r}")
    return int(rendered) if rendered.is_integer() else rendered


def sale_date(value: Any) -> tuple[str | None, str | None]:
    """Normalize ArcGIS esriFieldTypeDate without guessing its numeric unit.

    ArcGIS feature JSON encodes this field as UTC epoch milliseconds. Source
    null remains null. A present value that is not a finite integral JSON
    number, or that is outside the supported ISO date range, is an explicit
    field-null decision; the exact source value remains in ``attributes``.
    """

    if value is None:
        return None, None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, SALE_DATE_INVALID_REASON
    if isinstance(value, float) and (
        not math.isfinite(value) or not value.is_integer()
    ):
        return None, SALE_DATE_INVALID_REASON
    epoch_milliseconds = int(value)
    if not (
        SALE_DATE_MIN_EPOCH_MS
        <= epoch_milliseconds
        <= SALE_DATE_MAX_EPOCH_MS
    ):
        return None, SALE_DATE_OUT_OF_RANGE_REASON
    try:
        normalized = (
            dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
            + dt.timedelta(milliseconds=epoch_milliseconds)
        ).date()
    except (OverflowError, ValueError):
        return None, SALE_DATE_OUT_OF_RANGE_REASON
    if not (SALE_DATE_MIN <= normalized.isoformat() <= SALE_DATE_MAX):
        return None, SALE_DATE_OUT_OF_RANGE_REASON
    return normalized.isoformat(), None


def build_address(attributes: Mapping[str, Any]) -> str | None:
    start = optional_text(attributes.get("SITUS_STREET_NUMBER"))
    end = optional_text(attributes.get("SITUS_STREET_NUMBER_END"))
    if start and end and end != start:
        number = f"{start}-{end}"
    else:
        number = start or end
    parts = [
        number,
        optional_text(attributes.get("SITUS_STREET_DIRECTION")),
        optional_text(attributes.get("SITUS_STREET_NAME")),
        optional_text(attributes.get("SITUS_STREET_TYPE")),
        optional_text(attributes.get("SITUS_STREET_POST_DIR")),
    ]
    address = " ".join(part for part in parts if part)
    unit = optional_text(attributes.get("SITUS_UNIT_NUMBER"))
    if unit:
        address = f"{address} UNIT {unit}".strip()
    return address or None


def validate_metadata(metadata: Mapping[str, Any]) -> str:
    if metadata.get("objectIdField") != SYSTEM_OBJECT_ID_FIELD:
        raise ParcelGenerationError(
            f"source objectIdField changed: {metadata.get('objectIdField')!r}"
        )
    if str(metadata.get("geometryType")) != "esriGeometryPolygon":
        raise ParcelGenerationError("source geometryType is not esriGeometryPolygon")
    fields = metadata.get("fields")
    if not isinstance(fields, list):
        raise ParcelGenerationError("source metadata has no fields array")
    by_name = {
        field.get("name"): field.get("type")
        for field in fields
        if isinstance(field, Mapping) and field.get("name")
    }
    missing = sorted(REQUIRED_FIELDS.difference(by_name))
    if missing:
        raise ParcelGenerationError(f"required source fields disappeared: {missing}")
    for name in (SYSTEM_OBJECT_ID_FIELD, STABLE_SOURCE_OBJECT_ID_FIELD):
        if by_name[name] not in {
            "esriFieldTypeOID",
            "esriFieldTypeInteger",
            "esriFieldTypeDouble",
        }:
            raise ParcelGenerationError(f"{name} has incompatible type {by_name[name]!r}")
    if by_name[SALE_DATE_FIELD] != "esriFieldTypeDate":
        raise ParcelGenerationError(
            f"{SALE_DATE_FIELD} has incompatible type {by_name[SALE_DATE_FIELD]!r}"
        )
    schema_projection = {
        "capabilities": metadata.get("capabilities"),
        "fields": sorted(
            ({"name": name, "type": field_type} for name, field_type in by_name.items()),
            key=lambda item: item["name"],
        ),
        "geometryType": metadata.get("geometryType"),
        "maxRecordCount": metadata.get("maxRecordCount"),
        "objectIdField": metadata.get("objectIdField"),
    }
    return sha256_bytes(canonical_json_bytes(schema_projection))


@dataclasses.dataclass(frozen=True)
class Observation:
    system_object_id: int
    source_object_id: int
    raw_folio: str | None
    folio_number_raw: str | None
    folio: str | None
    rejection_reason: str | None
    longitude: float | None
    latitude: float | None
    situs_address: str | None
    situs_city: str | None
    situs_zip_code: str | None
    parcel_type: str | None
    use_code: str | None
    use_type: str | None
    municipality: str | None
    sale_date_1: str | None
    field_null_reasons: Mapping[str, str]
    deed_type_1: str | None
    stamp_amount_1: float | int | None
    sale1_cin: str | None
    attributes: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def normalize_feature(feature: Mapping[str, Any]) -> Observation:
    attributes = feature.get("attributes")
    if not isinstance(attributes, Mapping):
        raise ParcelGenerationError("feature is missing attributes")
    system_oid = integer(attributes.get(SYSTEM_OBJECT_ID_FIELD), SYSTEM_OBJECT_ID_FIELD)
    source_oid = integer(attributes.get(STABLE_SOURCE_OBJECT_ID_FIELD), STABLE_SOURCE_OBJECT_ID_FIELD)
    if system_oid < 0 or source_oid < 0:
        raise ParcelGenerationError("source identities must be nonnegative")

    raw_folio = optional_text(attributes.get("FOLIO"))
    folio_number_raw = optional_text(attributes.get("FOLIO_NUMBER"))
    normalized_primary = normalize_folio(raw_folio)
    normalized_secondary = normalize_folio(folio_number_raw)
    normalized = normalized_primary or normalized_secondary
    rejection_reason: str | None = None
    if raw_folio is None and folio_number_raw is None:
        rejection_reason = "missing_folio"
    elif (
        (raw_folio is not None and normalized_primary is None)
        or (folio_number_raw is not None and normalized_secondary is None)
        or normalized is None
        or (
            normalized_primary is not None
            and normalized_secondary is not None
            and normalized_primary != normalized_secondary
        )
    ):
        rejection_reason = "bad_folio_format"

    centroid = feature.get("centroid")
    longitude: float | None = None
    latitude: float | None = None
    if rejection_reason is None:
        if (
            not isinstance(centroid, Mapping)
            or centroid.get("x") is None
            or centroid.get("y") is None
        ):
            rejection_reason = "missing_centroid"
        else:
            try:
                longitude = float(centroid["x"])
                latitude = float(centroid["y"])
            except (TypeError, ValueError, OverflowError):
                rejection_reason = "missing_centroid"
            else:
                if not math.isfinite(longitude) or not math.isfinite(latitude):
                    rejection_reason = "missing_centroid"
                elif not (
                    PRODUCTION_QUALITY_CONTRACT["bbox"]["longitude_min"] <= longitude
                    <= PRODUCTION_QUALITY_CONTRACT["bbox"]["longitude_max"]
                    and PRODUCTION_QUALITY_CONTRACT["bbox"]["latitude_min"] <= latitude
                    <= PRODUCTION_QUALITY_CONTRACT["bbox"]["latitude_max"]
                ):
                    rejection_reason = "out_of_bounds_centroid"

    if SALE_DATE_FIELD not in attributes:
        raise ParcelGenerationError(
            f"feature omitted required {SALE_DATE_FIELD} attribute"
        )
    parsed_sale_date, sale_date_null_reason = sale_date(attributes[SALE_DATE_FIELD])
    field_null_reasons = (
        {"sale_date_1": sale_date_null_reason}
        if sale_date_null_reason is not None
        else {}
    )
    parsed_stamp = optional_number(attributes.get("STAMP_AMOUNT_1"))

    return Observation(
        system_object_id=system_oid,
        source_object_id=source_oid,
        raw_folio=raw_folio,
        folio_number_raw=folio_number_raw,
        folio=normalized,
        rejection_reason=rejection_reason,
        longitude=longitude,
        latitude=latitude,
        situs_address=build_address(attributes),
        situs_city=optional_text(attributes.get("SITUS_CITY")),
        situs_zip_code=optional_text(attributes.get("SITUS_ZIP_CODE")),
        parcel_type=optional_text(attributes.get("PARCEL_TYP")),
        use_code=optional_text(attributes.get("USE_CODE")),
        use_type=optional_text(attributes.get("USE_TYPE")),
        municipality=optional_text(attributes.get("MUNICIPALITY")),
        sale_date_1=parsed_sale_date,
        field_null_reasons=field_null_reasons,
        deed_type_1=optional_text(attributes.get("DEED_TYPE_1")),
        stamp_amount_1=parsed_stamp,
        sale1_cin=optional_text(attributes.get("SALE1_CIN")),
        attributes=dict(attributes),
    )


@dataclasses.dataclass(frozen=True)
class RangeReceipt:
    range_start: int
    range_end: int
    rows_received: int
    rows_accepted: int
    rejected_missing_folio: int
    rejected_bad_folio_format: int
    rejected_missing_centroid: int
    rejected_out_of_bounds_centroid: int
    duplicates_within_or_across_ranges: int
    manifest_path: str
    manifest_sha256: str

    @property
    def rows_rejected(self) -> int:
        return (
            self.rejected_missing_folio
            + self.rejected_bad_folio_format
            + self.rejected_missing_centroid
            + self.rejected_out_of_bounds_centroid
        )

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self) | {"rows_rejected": self.rows_rejected}


@dataclasses.dataclass(frozen=True)
class Finalization:
    source_rows: int
    accepted_rows: int
    rejected_rows: int
    duplicate_rows: int
    rejection_counts: Mapping[str, int]
    field_null_rows: int
    field_null_counts: Mapping[str, int]
    folio_set_sha256: str
    source_object_id_set_sha256: str
    source_content_sha256: str
    winner_content_sha256: str
    range_receipts: Sequence[RangeReceipt]
    winners_path: str
    winners_sha256: str
    rejections_path: str
    rejections_sha256: str
    duplicates_path: str
    duplicates_sha256: str
    field_nulls_path: str
    field_nulls_sha256: str

    def as_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        value["range_receipts"] = [receipt.as_dict() for receipt in self.range_receipts]
        return value


class ObservationStore:
    """Single-generation SQLite index used to make global winners deterministic."""

    def __init__(self, path: Path):
        self.path = path
        self.connection = sqlite3.connect(str(path))
        self.connection.execute("pragma journal_mode = WAL")
        self.connection.execute("pragma synchronous = FULL")
        self.connection.executescript(
            """
            create table pages (
                page_index integer primary key,
                raw_sha256 text not null,
                row_count integer not null
            );
            create table observations (
                source_object_id integer primary key,
                system_object_id integer not null unique,
                page_index integer not null references pages(page_index),
                folio text,
                rejection_reason text,
                sale_date_1_null_reason text,
                longitude real,
                latitude real,
                mapped_json text not null,
                attributes_json text not null
            );
            """
        )

    def close(self) -> None:
        self.connection.close()

    def ingest_page(
        self,
        *,
        page_index: int,
        raw_sha256: str,
        observations: Sequence[Observation],
    ) -> str:
        existing = self.connection.execute(
            "select raw_sha256, row_count from pages where page_index = ?", (page_index,)
        ).fetchone()
        if existing:
            if existing == (raw_sha256, len(observations)):
                return "replayed"
            raise ParcelGenerationError(f"page {page_index} replay changed its evidence")
        try:
            with self.connection:
                self.connection.execute(
                    "insert into pages(page_index, raw_sha256, row_count) values (?, ?, ?)",
                    (page_index, raw_sha256, len(observations)),
                )
                self.connection.executemany(
                    """
                    insert into observations(
                        source_object_id, system_object_id, page_index, folio,
                        rejection_reason, sale_date_1_null_reason, longitude,
                        latitude, mapped_json, attributes_json
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            row.source_object_id,
                            row.system_object_id,
                            page_index,
                            row.folio,
                            row.rejection_reason,
                            row.field_null_reasons.get("sale_date_1"),
                            row.longitude,
                            row.latitude,
                            canonical_json_bytes(row.as_dict()).decode("utf-8"),
                            canonical_json_bytes(row.attributes).decode("utf-8"),
                        )
                        for row in observations
                    ],
                )
        except sqlite3.IntegrityError as exc:
            raise ParcelGenerationError(
                "source identity was duplicated or changed across pages"
            ) from exc
        return "inserted"

    def observations_for_page(self, page_index: int) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "select mapped_json from observations where page_index = ? order by system_object_id",
            (page_index,),
        )
        return [json.loads(row[0]) for row in rows]

    def progress(self) -> tuple[int, int]:
        pages = int(self.connection.execute("select count(*) from pages").fetchone()[0])
        rows = int(
            self.connection.execute("select count(*) from observations").fetchone()[0]
        )
        return pages, rows

    def finalize(
        self, evidence: "EvidenceBundle", range_width: int = 20_000
    ) -> Finalization:
        # Materialize only source identities and decisions in SQLite. Winner,
        # rejection and duplicate JSONL files are streamed in sorted order, so
        # a countywide run never builds a 532k-dictionary Python list.
        self.connection.executescript(
            """
            drop table if exists temp.decisions;
            create temp table decisions as
            with valid_ranked as (
                select source_object_id,
                       row_number() over (
                           partition by folio
                           order by source_object_id, system_object_id
                       ) as winner_rank
                from observations
                where rejection_reason is null
            )
            select
                o.source_object_id,
                o.system_object_id,
                o.folio,
                o.rejection_reason,
                o.sale_date_1_null_reason,
                o.mapped_json,
                case
                    when o.rejection_reason is not null then 'rejected'
                    when v.winner_rank = 1 then 'winner'
                    else 'duplicate'
                end as decision
            from observations o
            left join valid_ranked v using (source_object_id);
            create unique index decisions_source_idx on decisions(source_object_id);
            create index decisions_decision_folio_idx
                on decisions(decision, folio, source_object_id);
            """
        )
        source_rows = int(
            self.connection.execute("select count(*) from decisions").fetchone()[0]
        )
        accepted_rows = int(
            self.connection.execute(
                "select count(*) from decisions where decision = 'winner'"
            ).fetchone()[0]
        )
        duplicate_rows = int(
            self.connection.execute(
                "select count(*) from decisions where decision = 'duplicate'"
            ).fetchone()[0]
        )
        rejected_rows = int(
            self.connection.execute(
                "select count(*) from decisions where decision = 'rejected'"
            ).fetchone()[0]
        )
        rejection_counts = {
            reason: int(
                self.connection.execute(
                    "select count(*) from decisions where rejection_reason = ?", (reason,)
                ).fetchone()[0]
            )
            for reason in (
                "missing_folio",
                "bad_folio_format",
                "missing_centroid",
                "out_of_bounds_centroid",
            )
        }
        field_null_counts = {
            reason: int(
                self.connection.execute(
                    "select count(*) from decisions where sale_date_1_null_reason = ?",
                    (reason,),
                ).fetchone()[0]
            )
            for reason in SALE_DATE_NULL_REASONS
        }
        field_null_rows = int(
            self.connection.execute(
                "select count(*) from decisions where sale_date_1_null_reason is not null"
            ).fetchone()[0]
        )
        if field_null_rows != sum(field_null_counts.values()):
            raise ParcelGenerationError("field-null decisions contain an unknown reason")

        winners_path, winners_sha, written_winners = evidence.write_jsonl_iter(
            "manifests/winners.jsonl",
            (
                json.loads(row[0])
                for row in self.connection.execute(
                    "select mapped_json from decisions where decision = 'winner' order by folio"
                )
            ),
        )
        rejects_path, rejects_sha, written_rejections = evidence.write_jsonl_iter(
            "manifests/rejections.jsonl",
            (
                json.loads(row[0])
                for row in self.connection.execute(
                    """
                    select mapped_json from decisions where decision = 'rejected'
                    order by rejection_reason, source_object_id
                    """
                )
            ),
        )
        dupes_path, dupes_sha, written_duplicates = evidence.write_jsonl_iter(
            "manifests/duplicates.jsonl",
            (
                json.loads(row[0])
                for row in self.connection.execute(
                    """
                    select mapped_json from decisions where decision = 'duplicate'
                    order by folio, source_object_id
                    """
                )
            ),
        )
        field_nulls_path, field_nulls_sha, written_field_nulls = (
            evidence.write_jsonl_iter(
                "manifests/field-nulls.jsonl",
                (
                    json.loads(row[0])
                    for row in self.connection.execute(
                        """
                        select mapped_json from decisions
                        where sale_date_1_null_reason is not null
                        order by sale_date_1_null_reason, source_object_id
                        """
                    )
                ),
            )
        )
        if (written_winners, written_rejections, written_duplicates) != (
            accepted_rows,
            rejected_rows,
            duplicate_rows,
        ):
            raise ParcelGenerationError("streamed decision manifests changed row counts")
        if written_field_nulls != field_null_rows:
            raise ParcelGenerationError("streamed field-null manifest changed row counts")

        source_bounds = self.connection.execute(
            "select min(source_object_id), max(source_object_id) from decisions"
        ).fetchone()
        if source_bounds[0] is None or source_bounds[1] is None:
            raise ParcelGenerationError("generation contains no source observations")
        range_min = (int(source_bounds[0]) // range_width) * range_width
        range_max = ((int(source_bounds[1]) // range_width) + 1) * range_width - 1
        range_receipts: list[RangeReceipt] = []
        for range_start in range(range_min, range_max + 1, range_width):
            range_end = range_start + range_width - 1
            summary = self.connection.execute(
                """
                select
                    count(*),
                    coalesce(sum(decision = 'winner'), 0),
                    coalesce(sum(decision = 'duplicate'), 0),
                    coalesce(sum(rejection_reason = 'missing_folio'), 0),
                    coalesce(sum(rejection_reason = 'bad_folio_format'), 0),
                    coalesce(sum(rejection_reason = 'missing_centroid'), 0),
                    coalesce(sum(rejection_reason = 'out_of_bounds_centroid'), 0)
                from decisions
                where source_object_id between ? and ?
                """,
                (range_start, range_end),
            ).fetchone()
            rows_received, accepted, duplicate_count = map(int, summary[:3])
            range_rejections = dict(
                zip(rejection_counts, (int(value) for value in summary[3:]))
            )
            manifest = {
                "range_end": range_end,
                "range_start": range_start,
                "row_source_object_ids": [
                    int(row[0])
                    for row in self.connection.execute(
                        """
                        select source_object_id from decisions
                        where source_object_id between ? and ?
                        order by source_object_id
                        """,
                        (range_start, range_end),
                    )
                ],
                "rows_accepted": accepted,
                "rows_duplicate": duplicate_count,
                "rows_received": rows_received,
                "rows_rejected": sum(range_rejections.values()),
            }
            manifest_path, manifest_sha = evidence.write_json(
                f"manifests/range-{range_start:09d}-{range_end:09d}.json", manifest
            )
            range_receipts.append(
                RangeReceipt(
                    range_start=range_start,
                    range_end=range_end,
                    rows_received=rows_received,
                    rows_accepted=accepted,
                    rejected_missing_folio=range_rejections["missing_folio"],
                    rejected_bad_folio_format=range_rejections["bad_folio_format"],
                    rejected_missing_centroid=range_rejections["missing_centroid"],
                    rejected_out_of_bounds_centroid=range_rejections[
                        "out_of_bounds_centroid"
                    ],
                    duplicates_within_or_across_ranges=duplicate_count,
                    manifest_path=manifest_path,
                    manifest_sha256=manifest_sha,
                )
            )

        return Finalization(
            source_rows=source_rows,
            accepted_rows=accepted_rows,
            rejected_rows=rejected_rows,
            duplicate_rows=duplicate_rows,
            rejection_counts=rejection_counts,
            field_null_rows=field_null_rows,
            field_null_counts=field_null_counts,
            folio_set_sha256=hash_lines(
                str(row[0])
                for row in self.connection.execute(
                    "select folio from decisions where decision = 'winner' order by folio"
                )
            ),
            source_object_id_set_sha256=hash_lines(
                str(row[0])
                for row in self.connection.execute(
                    "select source_object_id from decisions order by source_object_id"
                )
            ),
            source_content_sha256=hash_lines(
                str(row[0])
                for row in self.connection.execute(
                    "select mapped_json from decisions order by source_object_id"
                )
            ),
            winner_content_sha256=winners_sha,
            range_receipts=range_receipts,
            winners_path=winners_path,
            winners_sha256=winners_sha,
            rejections_path=rejects_path,
            rejections_sha256=rejects_sha,
            duplicates_path=dupes_path,
            duplicates_sha256=dupes_sha,
            field_nulls_path=field_nulls_path,
            field_nulls_sha256=field_nulls_sha,
        )


class EvidenceBundle:
    def __init__(self, root: Path, run_id: str):
        try:
            parsed_run_id = uuid.UUID(run_id)
        except (ValueError, AttributeError) as exc:
            raise ParcelGenerationError("run_id must be a lowercase UUID") from exc
        if str(parsed_run_id) != run_id:
            raise ParcelGenerationError("run_id must be a lowercase UUID")
        self.root = root / run_id
        try:
            create_durable_directory(self.root)
        except FileExistsError as exc:
            raise ParcelGenerationError(f"run evidence already exists: {run_id}") from exc
        self.objects: list[dict[str, Any]] = []

    def write_bytes(self, relative_path: str, body: bytes, media_type: str) -> tuple[str, str]:
        sha = write_once(self.root / relative_path, body)
        self.objects.append(
            {
                "bytes": len(body),
                "media_type": media_type,
                "path": relative_path,
                "sha256": sha,
            }
        )
        return relative_path, sha

    def write_json(self, relative_path: str, value: Any) -> tuple[str, str]:
        return self.write_bytes(relative_path, canonical_json_bytes(value) + b"\n", "application/json")

    def write_jsonl(self, relative_path: str, rows: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
        path, sha, _ = self.write_jsonl_iter(relative_path, iter(rows))
        return path, sha

    def write_jsonl_iter(
        self, relative_path: str, rows: Iterable[Mapping[str, Any]]
    ) -> tuple[str, str, int]:
        path = self.root / relative_path
        create_durable_directory(path.parent, exist_ok=True)
        digest = hashlib.sha256()
        byte_count = 0
        row_count = 0
        try:
            descriptor = os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(descriptor, "wb") as handle:
                for row in rows:
                    encoded = canonical_json_bytes(row) + b"\n"
                    handle.write(encoded)
                    digest.update(encoded)
                    byte_count += len(encoded)
                    row_count += 1
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError as exc:
            raise ParcelGenerationError(f"immutable evidence already exists: {path}") from exc
        fsync_directory(path.parent)
        sha = digest.hexdigest()
        self.objects.append(
            {
                "bytes": byte_count,
                "media_type": "application/x-ndjson",
                "path": relative_path,
                "sha256": sha,
            }
        )
        return relative_path, sha, row_count

    def capture_json(self, relative_path: str, value: Any) -> tuple[str, str]:
        return self.write_json(f"raw/{relative_path}", value)

    def capture_source_json(
        self, relative_path: str, value: Mapping[str, Any]
    ) -> tuple[str, str]:
        path, sha = self.capture_source_body(relative_path, value)
        self.capture_source_request_receipt(relative_path, value, sha)
        return path, sha

    def capture_source_body(
        self, relative_path: str, value: Mapping[str, Any]
    ) -> tuple[str, str]:
        if isinstance(value, CapturedJson):
            return self.write_bytes(
                f"raw/{relative_path}", value.raw_body, "application/json"
            )
        return self.capture_json(relative_path, value)

    def capture_source_request_receipt(
        self,
        relative_path: str,
        value: Mapping[str, Any],
        response_sha256: str,
    ) -> None:
        if isinstance(value, CapturedJson):
            self.write_json(
                f"raw/{relative_path}.request.json",
                value.request_receipt | {"response_sha256": response_sha256},
            )

    def finish_manifest(self, context: Mapping[str, Any]) -> tuple[str, str]:
        manifest = {
            "context": dict(context),
            "created_at": utc_now(),
            "objects": sorted(self.objects, key=lambda item: item["path"]),
            "schema_version": "FloridaSignalImmutableEvidenceManifestV1",
        }
        return self.write_json("manifest.json", manifest)

    def finish_failure_manifest(self) -> dict[str, Any]:
        objects = sorted(
            (dict(item) for item in self.objects),
            key=lambda item: (
                str(item["path"]),
                str(item["sha256"]),
                int(item["bytes"]),
                str(item["media_type"]),
            ),
        )
        paths = [str(item["path"]) for item in objects]
        if len(paths) != len(set(paths)):
            raise ParcelGenerationError(
                "failure evidence manifest contains duplicate immutable paths"
            )
        manifest = {
            "object_count": len(objects),
            "objects": objects,
            "run_id": self.root.name,
            "schema_version": FAILURE_EVIDENCE_MANIFEST_SCHEMA,
        }
        body = canonical_json_bytes(manifest) + b"\n"
        path, sha256 = self.write_bytes(
            "failure-manifest.json",
            body,
            "application/json",
        )
        return {
            "bytes": len(body),
            "object_count": len(objects),
            "path": path,
            "schema_version": FAILURE_EVIDENCE_MANIFEST_SCHEMA,
            "sha256": sha256,
        }


class Source:
    def metadata(self) -> Mapping[str, Any]:
        raise NotImplementedError

    def item_metadata(self) -> Mapping[str, Any]:
        raise NotImplementedError

    def object_ids(self, label: str) -> Mapping[str, Any]:
        raise NotImplementedError

    def page(self, page_index: int, object_ids: Sequence[int]) -> Mapping[str, Any]:
        raise NotImplementedError


class FixtureSource(Source):
    def __init__(self, root: Path):
        self.root = root

    def _load(self, name: str) -> Mapping[str, Any]:
        path = self.root / name
        try:
            raw_body = path.read_bytes()
            value = json.loads(raw_body)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise ParcelGenerationError(f"fixture cannot be read: {path}") from exc
        if not isinstance(value, Mapping):
            raise ParcelGenerationError(f"fixture must be a JSON object: {path}")
        return CapturedJson(
            value,
            raw_body=raw_body,
            request_receipt={
                "fixture": name,
                "method": "FILE",
                "observed_at": utc_now(),
            },
        )

    def metadata(self) -> Mapping[str, Any]:
        return self._load("metadata.json")

    def item_metadata(self) -> Mapping[str, Any]:
        return self._load("item-metadata.json")

    def object_ids(self, label: str) -> Mapping[str, Any]:
        return self._load(f"object-ids-{label}.json")

    def page(self, page_index: int, object_ids: Sequence[int]) -> Mapping[str, Any]:
        del object_ids
        return self._load(f"page-{page_index:04d}.json")


class ArcGISSource(Source):
    def __init__(
        self, *, timeout_seconds: float = 60.0, max_bytes: int = 96 * 1024 * 1024
    ):
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes

    def _json(self, url: str, params: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        encoded = urllib.parse.urlencode(params or {"f": "json"}).encode("ascii")
        request = urllib.request.Request(
            url,
            data=encoded if params else None,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "FloridaSignalParcelGeneration/1.0",
            },
            method="POST" if params else "GET",
        )
        observed_at = utc_now()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                if response.geturl() != request.full_url:
                    raise ParcelGenerationError(
                        f"source redirected away from its pinned URL: {request.full_url}"
                    )
                body = response.read(self.max_bytes + 1)
                status = response.status
                if status != 200:
                    raise ParcelGenerationError(
                        f"source returned unexpected HTTP status {status} for {url}"
                    )
                response_headers = {
                    key.lower(): value
                    for key, value in response.headers.items()
                    if key.lower() in {"content-type", "etag", "last-modified"}
                }
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ParcelGenerationError(f"source request failed for {url}: {exc}") from exc
        if len(body) > self.max_bytes:
            raise ParcelGenerationError(f"source response exceeded {self.max_bytes} bytes")
        try:
            value = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ParcelGenerationError(f"source returned invalid JSON for {url}") from exc
        if not isinstance(value, Mapping) or value.get("error"):
            raise ParcelGenerationError(f"source returned an ArcGIS error for {url}: {value}")
        return CapturedJson(
            value,
            raw_body=body,
            request_receipt={
                "method": "POST" if params else "GET",
                "observed_at": observed_at,
                "request_body_sha256": sha256_bytes(encoded) if params else None,
                "request_parameters": dict(params) if params else None,
                "response_headers": response_headers,
                "status": status,
                "url": url,
            },
        )

    def metadata(self) -> Mapping[str, Any]:
        return self._json(f"{SOURCE_LAYER_URL}?f=pjson")

    def item_metadata(self) -> Mapping[str, Any]:
        return self._json(f"{SOURCE_ITEM_URL}?f=json")

    def object_ids(self, label: str) -> Mapping[str, Any]:
        del label
        return self._json(
            f"{SOURCE_LAYER_URL}/query",
            {"f": "json", "returnIdsOnly": "true", "where": "1=1"},
        )

    def page(self, page_index: int, object_ids: Sequence[int]) -> Mapping[str, Any]:
        del page_index
        return self._json(
            f"{SOURCE_LAYER_URL}/query",
            {
                "f": "json",
                "objectIds": ",".join(str(value) for value in object_ids),
                "orderByFields": f"{SYSTEM_OBJECT_ID_FIELD} ASC",
                "outFields": OUT_FIELDS,
                "outSR": "4326",
                "returnCentroid": "true",
                "returnGeometry": "false",
            },
        )


def parse_object_ids(payload: Mapping[str, Any]) -> list[int]:
    field_name = payload.get("objectIdFieldName")
    if field_name not in (None, SYSTEM_OBJECT_ID_FIELD):
        raise ParcelGenerationError(f"object ID response field changed: {field_name!r}")
    values = payload.get("objectIds")
    if not isinstance(values, list):
        raise ParcelGenerationError("object ID response has no objectIds array")
    parsed = sorted(integer(value, SYSTEM_OBJECT_ID_FIELD) for value in values)
    if len(parsed) != len(set(parsed)):
        raise ParcelGenerationError("object ID response contains duplicates")
    return parsed


def chunks(values: Sequence[int], size: int) -> Iterator[list[int]]:
    for offset in range(0, len(values), size):
        yield list(values[offset : offset + size])


def validate_page(payload: Mapping[str, Any], expected_ids: Sequence[int]) -> list[Observation]:
    features = payload.get("features")
    if not isinstance(features, list):
        raise ParcelGenerationError("page response has no features array")
    observations = [normalize_feature(feature) for feature in features]
    actual_ids = sorted(row.system_object_id for row in observations)
    if actual_ids != sorted(expected_ids):
        missing = sorted(set(expected_ids).difference(actual_ids))[:10]
        extra = sorted(set(actual_ids).difference(expected_ids))[:10]
        raise ParcelGenerationError(
            f"page object identity mismatch; missing={missing}, extra={extra}"
        )
    return observations


def quality_gate(mode: str, finalization: Finalization) -> list[str]:
    contract = CANARY_QUALITY_CONTRACT if mode == "canary" else PRODUCTION_QUALITY_CONTRACT
    failures: list[str] = []
    if not (
        contract["minimum_source_rows"]
        <= finalization.source_rows
        <= contract["maximum_source_rows"]
    ):
        failures.append("source row count outside reviewed contract")
    if finalization.accepted_rows < contract["minimum_accepted_rows"]:
        failures.append("accepted row count below reviewed contract")
    if finalization.rejected_rows > contract["maximum_rejected_rows"]:
        failures.append("rejected row count above reviewed contract")
    if finalization.duplicate_rows > contract["maximum_duplicate_rows"]:
        failures.append("duplicate row count above reviewed contract")
    if finalization.source_rows != (
        finalization.accepted_rows + finalization.rejected_rows + finalization.duplicate_rows
    ):
        failures.append("source accounting does not reconcile")
    if finalization.field_null_rows != sum(finalization.field_null_counts.values()):
        failures.append("field-null accounting does not reconcile")
    if not 0 <= finalization.field_null_rows <= finalization.source_rows:
        failures.append("field-null row count exceeds source observations")
    return failures


class SupabaseStagingSink:
    """Narrow staging-only Supabase client; there is deliberately no promote method."""

    def __init__(self, *, url: str, service_key: str, bucket: str = DEFAULT_BUCKET):
        self.url = url.rstrip("/")
        self.service_key = service_key
        self.bucket = bucket

    @classmethod
    def from_environment(cls, bucket: str) -> "SupabaseStagingSink":
        if os.environ.get("FL_SIGNAL_PARCEL_WRITE_APPROVAL") != WRITE_APPROVAL:
            raise ParcelGenerationError("exact staging-only write approval is absent")
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise ParcelGenerationError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
        parsed = urllib.parse.urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ParcelGenerationError("SUPABASE_URL must be a credential-free HTTPS origin")
        return cls(url=url, service_key=key, bucket=bucket)

    def _request(
        self,
        *,
        path: str,
        method: str,
        body: bytes | None = None,
        content_type: str = "application/json",
        accept: str = "application/json",
        extra_headers: Mapping[str, str] | None = None,
        timeout_seconds: float = 90.0,
    ) -> Any:
        headers = {
            "Accept": accept,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": content_type,
            "apikey": self.service_key,
        }
        headers.update(extra_headers or {})
        request = urllib.request.Request(
            f"{self.url}{path}",
            data=body,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                response_body = response.read(8 * 1024 * 1024 + 1)
        except urllib.error.HTTPError as exc:
            safe_body = exc.read(2048).decode("utf-8", errors="replace")
            raise ParcelGenerationError(
                f"Supabase staging request failed ({exc.code}) at {path}: {safe_body}"
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ParcelGenerationError(
                f"Supabase staging request failed at {path}: {exc}"
            ) from exc
        if len(response_body) > 8 * 1024 * 1024:
            raise ParcelGenerationError("Supabase response exceeded safe limit")
        if not response_body:
            return None
        try:
            return json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise ParcelGenerationError("Supabase returned invalid JSON") from exc

    def verify_private_bucket(self) -> None:
        result = self._request(path=f"/storage/v1/bucket/{self.bucket}", method="GET")
        if not isinstance(result, Mapping) or result.get("public") is not False:
            raise ParcelGenerationError(f"evidence bucket {self.bucket!r} is absent or public")

    def rpc(
        self,
        function: str,
        payload: Mapping[str, Any],
        *,
        timeout_seconds: float = 90.0,
    ) -> Any:
        return self._request(
            path=f"/rest/v1/rpc/{function}",
            method="POST",
            body=canonical_json_bytes(payload),
            timeout_seconds=timeout_seconds,
        )

    def _download_digest(self, object_key: str, maximum_bytes: int) -> tuple[int, str]:
        quoted_key = urllib.parse.quote(object_key, safe="/")
        url = (
            f"{self.url}/storage/v1/object/authenticated/"
            f"{self.bucket}/{quoted_key}"
        )
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Accept": "application/octet-stream",
                "Authorization": f"Bearer {self.service_key}",
                "apikey": self.service_key,
            },
        )
        digest = hashlib.sha256()
        observed_bytes = 0
        try:
            with urllib.request.urlopen(request, timeout=300.0) as response:
                if response.geturl() != request.full_url:
                    raise ParcelGenerationError(
                        "private evidence download redirected away from its pinned object URL"
                    )
                if response.status != 200:
                    raise ParcelGenerationError(
                        f"private evidence download returned HTTP {response.status}"
                    )
                while True:
                    chunk = response.read(min(1024 * 1024, maximum_bytes + 1 - observed_bytes))
                    if not chunk:
                        break
                    observed_bytes += len(chunk)
                    if observed_bytes > maximum_bytes:
                        raise ParcelGenerationError(
                            "private evidence download exceeded uploaded byte count"
                        )
                    digest.update(chunk)
        except urllib.error.HTTPError as exc:
            raise ParcelGenerationError(
                f"private evidence download failed ({exc.code}) for {object_key}"
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ParcelGenerationError(
                f"private evidence download failed for {object_key}: {exc}"
            ) from exc
        return observed_bytes, digest.hexdigest()

    def _object_info(self, object_key: str) -> dict[str, Any]:
        quoted_key = urllib.parse.quote(object_key, safe="/")
        result = self._request(
            path=f"/storage/v1/object/info/{self.bucket}/{quoted_key}",
            method="GET",
        )
        if not isinstance(result, Mapping):
            raise ParcelGenerationError(
                f"private evidence object info is unavailable for {object_key}"
            )
        object_id = optional_text(result.get("id"))
        updated_at = optional_text(result.get("updated_at"))
        metadata = result.get("metadata")
        if not object_id or not updated_at or not isinstance(metadata, Mapping):
            raise ParcelGenerationError(
                f"private evidence object info is incomplete for {object_key}"
            )
        try:
            if str(uuid.UUID(object_id)) != object_id:
                raise ValueError
        except ValueError as exc:
            raise ParcelGenerationError(
                f"private evidence object ID is invalid for {object_key}"
            ) from exc
        raw_size = metadata.get("size", metadata.get("contentLength"))
        size = integer(raw_size, "Storage object size")
        if size < 0:
            raise ParcelGenerationError("Storage object size cannot be negative")
        return {
            "storage_metadata_size": size,
            "storage_object_id": object_id,
            "storage_updated_at": updated_at,
        }

    def upload_once(
        self, object_key: str, body: bytes, media_type: str
    ) -> dict[str, Any]:
        quoted_key = urllib.parse.quote(object_key, safe="/")
        self._request(
            path=f"/storage/v1/object/{self.bucket}/{quoted_key}",
            method="POST",
            body=body,
            content_type=media_type,
            extra_headers={"x-upsert": "false"},
        )
        expected_sha256 = sha256_bytes(body)
        info_before = self._object_info(object_key)
        observed_bytes, observed_sha256 = self._download_digest(object_key, len(body))
        info_after = self._object_info(object_key)
        if (
            info_before != info_after
            or info_after["storage_metadata_size"] != len(body)
            or observed_bytes != len(body)
            or observed_sha256 != expected_sha256
        ):
            raise ParcelGenerationError(
                f"private evidence version-fenced round-trip verification failed for {object_key}"
            )
        return {
            **info_after,
            "bytes": observed_bytes,
            "object_key": object_key,
            "sha256": observed_sha256,
            "verification_method": "private_storage_roundtrip_sha256_v1",
        }


def evidence_purpose(relative_path: str) -> str:
    if relative_path.startswith("raw/page-") and relative_path.endswith(".json"):
        return "raw_page"
    if relative_path == "manifest.json":
        return "generation_manifest"
    if relative_path.startswith("manifests/range-"):
        return "range_manifest"
    if relative_path == "manifests/rejections.jsonl":
        return "rejection_manifest"
    if relative_path == "manifests/duplicates.jsonl":
        return "duplicate_manifest"
    if relative_path == "manifests/field-nulls.jsonl":
        return "field_null_manifest"
    return "supporting_evidence"


def collect_generation(
    *,
    source: Source,
    evidence_root: Path,
    run_id: str,
    mode: str,
    page_size: int,
    canary_rows: int,
    sink: SupabaseStagingSink | None = None,
) -> dict[str, Any]:
    if mode not in {"canary", "current_generation"}:
        raise ParcelGenerationError(f"unsupported mode: {mode}")
    if not 1 <= page_size <= 2_000:
        raise ParcelGenerationError("page_size must be between 1 and 2000")
    if mode == "canary" and not 1 <= canary_rows <= 25:
        raise ParcelGenerationError("canary_rows must be between 1 and 25")

    evidence = EvidenceBundle(evidence_root, run_id)
    store = ObservationStore(evidence.root / "work.sqlite")
    started_at = utc_now()
    sink_started = False
    failure_stage = "metadata_fetch"
    active_page_index: int | None = None
    active_raw_page_path: str | None = None
    active_raw_page_sha256: str | None = None
    selected_source_rows: int | None = None
    raw_pages_captured = 0
    raw_rows_captured = 0
    finalization: Finalization | None = None
    try:
        metadata = source.metadata()
        failure_stage = "metadata_capture_and_validation"
        evidence.capture_source_json("source-metadata.json", metadata)
        source_schema_sha256 = validate_metadata(metadata)
        failure_stage = "item_metadata_fetch"
        item_metadata = source.item_metadata()
        failure_stage = "item_metadata_capture_and_validation"
        evidence.capture_source_json("source-item-metadata.json", item_metadata)
        service_item_id = optional_text(metadata.get("serviceItemId"))
        item_id = optional_text(item_metadata.get("id"))
        if service_item_id != SOURCE_ITEM_ID or item_id != SOURCE_ITEM_ID:
            raise ParcelGenerationError(
                "ArcGIS layer and item metadata no longer match the pinned service item"
            )

        failure_stage = "source_object_ids_start"
        start_payload = source.object_ids("start")
        evidence.capture_source_json("object-ids-start.json", start_payload)
        universe_ids = parse_object_ids(start_payload)
        selected_ids = universe_ids[:canary_rows] if mode == "canary" else universe_ids
        if not selected_ids:
            raise ParcelGenerationError("source returned no object IDs")
        selected_source_rows = len(selected_ids)
        system_object_id_set_sha256 = hash_lines(str(value) for value in selected_ids)
        page_descriptors: list[dict[str, Any]] = []
        for page_index, expected_ids in enumerate(chunks(selected_ids, page_size)):
            active_page_index = page_index
            active_raw_page_path = None
            active_raw_page_sha256 = None
            failure_stage = "page_fetch"
            payload = source.page(page_index, expected_ids)
            failure_stage = "raw_page_capture"
            page_path, page_sha = evidence.capture_source_body(
                f"page-{page_index:06d}.json", payload
            )
            active_raw_page_path = page_path
            active_raw_page_sha256 = page_sha
            raw_pages_captured += 1
            raw_features = payload.get("features")
            if isinstance(raw_features, list):
                raw_rows_captured += len(raw_features)
            evidence.capture_source_request_receipt(
                f"page-{page_index:06d}.json",
                payload,
                page_sha,
            )
            failure_stage = "page_normalization"
            observations = validate_page(payload, expected_ids)
            failure_stage = "page_index_commit"
            store.ingest_page(
                page_index=page_index, raw_sha256=page_sha, observations=observations
            )
            page_descriptors.append(
                {
                    "page_index": page_index,
                    "raw_path": page_path,
                    "raw_sha256": page_sha,
                    "row_count": len(observations),
                    "system_object_id_max": max(expected_ids),
                    "system_object_id_min": min(expected_ids),
                }
            )

        active_page_index = None
        active_raw_page_path = None
        active_raw_page_sha256 = None
        failure_stage = "source_object_ids_end"
        end_payload = source.object_ids("end")
        evidence.capture_source_json("object-ids-end.json", end_payload)
        end_universe_ids = parse_object_ids(end_payload)
        if universe_ids != end_universe_ids:
            raise ParcelGenerationError("source object-ID universe changed during collection")

        failure_stage = "deterministic_finalization"
        finalization = store.finalize(evidence)
        failure_stage = "quality_gate"
        gate_failures = quality_gate(mode, finalization)
        if gate_failures:
            raise ParcelGenerationError("; ".join(gate_failures))

        contract = CANARY_QUALITY_CONTRACT if mode == "canary" else PRODUCTION_QUALITY_CONTRACT
        quality_sha = contract_sha256(contract)
        manifest_context = {
            "accepted_rows": finalization.accepted_rows,
            "canary_rows": canary_rows if mode == "canary" else None,
            "collector": "broward_parcel_generation.py",
            "duplicate_rows": finalization.duplicate_rows,
            "field_null_counts": dict(finalization.field_null_counts),
            "field_null_rows": finalization.field_null_rows,
            "folio_set_sha256": finalization.folio_set_sha256,
            "mode": mode,
            "normalizer_version": NORMALIZER_VERSION,
            "quality_contract_sha256": quality_sha,
            "rejected_rows": finalization.rejected_rows,
            "run_id": run_id,
            "source_content_sha256": finalization.source_content_sha256,
            "source_layer_url": SOURCE_LAYER_URL,
            "source_object_id_set_sha256": finalization.source_object_id_set_sha256,
            "source_rows": finalization.source_rows,
            "source_schema_sha256": source_schema_sha256,
            "system_object_id_set_sha256": system_object_id_set_sha256,
            "source_universe_count": len(universe_ids),
            "winner_rule": WINNER_RULE,
        }
        failure_stage = "generation_manifest"
        manifest_path, manifest_sha = evidence.finish_manifest(manifest_context)
        receipt: dict[str, Any] = {
            **manifest_context,
            **finalization.as_dict(),
            "completed_at": utc_now(),
            "database_destination": (
                "public.broward_parcel_geography_stage" if sink is not None else None
            ),
            "dry_run": sink is None,
            "manifest_path": manifest_path,
            "manifest_sha256": manifest_sha,
            "page_count": len(page_descriptors),
            "page_descriptors": page_descriptors,
            "promotion_authorized": False,
            "promotion_eligible": False,
            "promotion_performed": False,
            "quality_gate_passed": True,
            "source_item_modified": item_metadata.get("modified"),
            "started_at": started_at,
            "status": "canary_complete" if mode == "canary" else "dry_run_complete",
        }

        if sink is not None:
            failure_stage = "private_evidence_upload"
            sink.verify_private_bucket()
            object_prefix = f"broward-parcel-generations/{run_id}"
            # Upload immutable evidence and read every object back before making a
            # generation visible to the database. The begin RPC binds these
            # round-trip hashes and sizes to the exact immutable Storage rows.
            verified_evidence: list[dict[str, Any]] = []
            for item in sorted(evidence.objects, key=lambda entry: entry["path"]):
                body = (evidence.root / item["path"]).read_bytes()
                verified = sink.upload_once(
                    f"{object_prefix}/{item['path']}", body, str(item["media_type"])
                )
                if (
                    verified["bytes"] != item["bytes"]
                    or verified["sha256"] != item["sha256"]
                ):
                    raise ParcelGenerationError(
                        "Storage round-trip receipt differs from local evidence manifest"
                    )
                verified_evidence.append(
                    verified
                    | {
                        "purpose": evidence_purpose(str(item["path"])),
                        "relative_path": item["path"],
                    }
                )
            # Set before the RPC so an ambiguous timeout can still attempt the
            # idempotent failure boundary if the database committed begin.
            sink_started = True
            failure_stage = "database_generation_begin"
            sink.rpc(
                "fs_begin_broward_parcel_generation",
                {
                    "p_evidence_objects": verified_evidence,
                    "p_generation_id": run_id,
                    "p_mode": mode,
                    "p_quality_contract_sha256": quality_sha,
                    "p_source_layer_url": SOURCE_LAYER_URL,
                    "p_source_reported_count": finalization.source_rows,
                    "p_source_schema_sha256": source_schema_sha256,
                    "p_source_universe_count": len(universe_ids),
                    "p_source_vintage": item_metadata,
                    "p_ranges": [
                        item.as_dict()
                        | {
                            "manifest_object_key": (
                                f"{object_prefix}/{item.manifest_path}"
                            )
                        }
                        for item in finalization.range_receipts
                    ],
                },
            )
            for descriptor in page_descriptors:
                page_index = int(descriptor["page_index"])
                active_page_index = page_index
                failure_stage = "database_page_staging"
                sink.rpc(
                    "fs_stage_broward_parcel_page",
                    {
                        "p_generation_id": run_id,
                        "p_observations": store.observations_for_page(page_index),
                        "p_page_index": page_index,
                        "p_raw_object_key": f"{object_prefix}/{descriptor['raw_path']}",
                        "p_raw_sha256": descriptor["raw_sha256"],
                        "p_system_object_id_max": descriptor["system_object_id_max"],
                        "p_system_object_id_min": descriptor["system_object_id_min"],
                    },
                )
            active_page_index = None
            failure_stage = "database_finalization"
            database_receipt = sink.rpc(
                "fs_finalize_broward_parcel_generation",
                {
                    "p_duplicate_manifest_key": f"{object_prefix}/{finalization.duplicates_path}",
                    "p_duplicate_manifest_sha256": finalization.duplicates_sha256,
                    "p_generation_id": run_id,
                    "p_manifest_key": f"{object_prefix}/{manifest_path}",
                    "p_manifest_sha256": manifest_sha,
                    "p_range_manifests": [
                        {
                            key: value
                            for key, value in item.as_dict().items()
                            if key != "manifest_path"
                        }
                        | {
                            "manifest_object_key": (
                                f"{object_prefix}/{item.manifest_path}"
                            )
                        }
                        for item in finalization.range_receipts
                    ],
                    "p_rejection_manifest_key": f"{object_prefix}/{finalization.rejections_path}",
                    "p_rejection_manifest_sha256": finalization.rejections_sha256,
                    "p_source_object_id_set_sha256": finalization.source_object_id_set_sha256,
                    "p_system_object_id_set_sha256": system_object_id_set_sha256,
                },
                timeout_seconds=1_800.0,
            )
            if not isinstance(database_receipt, Mapping):
                raise ParcelGenerationError("database finalizer returned no JSON object")
            database_source_content_sha256 = database_receipt.get(
                "source_content_sha256"
            )
            if not isinstance(database_source_content_sha256, str) or not re.fullmatch(
                r"[0-9a-f]{64}", database_source_content_sha256
            ):
                raise ParcelGenerationError(
                    "database finalizer omitted its independently recomputed content hash"
                )
            expected_database_status = (
                "canary_complete" if mode == "canary" else "ready"
            )
            expected_database_values = {
                "duplicate_rows": finalization.duplicate_rows,
                "folio_set_sha256": finalization.folio_set_sha256,
                "rejected_rows": finalization.rejected_rows,
                "rows_accepted": finalization.accepted_rows,
                "rows_received": finalization.source_rows,
                "sale_date_1_field_null_rows": finalization.field_null_rows,
                "source_object_id_set_sha256": (
                    finalization.source_object_id_set_sha256
                ),
                "status": expected_database_status,
                "system_object_id_set_sha256": system_object_id_set_sha256,
            }
            if any(
                database_receipt.get(key) != value
                for key, value in expected_database_values.items()
            ):
                raise ParcelGenerationError(
                    "database finalizer receipt differs from local deterministic receipt"
                )
            receipt["database_receipt"] = database_receipt
            receipt["database_source_content_sha256"] = (
                database_source_content_sha256
            )
            receipt["promotion_eligible"] = bool(
                database_receipt.get("promotion_eligible")
            )
            receipt["status"] = expected_database_status
            receipt["storage_prefix"] = object_prefix

        failure_stage = "terminal_receipt_write"
        receipt_path, receipt_sha = evidence.write_json("receipt.json", receipt)
        returned_receipt = receipt | {
            "receipt_path": receipt_path,
            "receipt_sha256": receipt_sha,
        }
        if sink is not None:
            failure_stage = "terminal_receipt_upload"
            receipt_object_key = f"{object_prefix}/{receipt_path}"
            terminal_storage_receipt = sink.upload_once(
                receipt_object_key,
                (evidence.root / receipt_path).read_bytes(),
                "application/json",
            )
            returned_receipt["receipt_object_key"] = receipt_object_key
            returned_receipt["receipt_storage_verification"] = terminal_storage_receipt
        return returned_receipt
    except Exception as exc:
        try:
            indexed_pages, indexed_rows = store.progress()
        except Exception:
            indexed_pages, indexed_rows = None, None
        raw_rows_not_indexed = (
            raw_rows_captured - indexed_rows
            if indexed_rows is not None and raw_rows_captured >= indexed_rows
            else None
        )
        row_partition_complete = bool(
            selected_source_rows is not None
            and indexed_rows == selected_source_rows
            and raw_rows_captured == indexed_rows
            and finalization is not None
        )
        try:
            failure_evidence_manifest = evidence.finish_failure_manifest()
        except Exception as manifest_exc:
            raise ParcelGenerationError(
                "collector failed and its terminal evidence manifest could not be "
                f"durably written: {type(exc).__name__}: {exc}; "
                f"manifest error: {type(manifest_exc).__name__}: {manifest_exc}"
            ) from manifest_exc
        failure = {
            "completed_at": utc_now(),
            "evidence_manifest": failure_evidence_manifest,
            "error_class": type(exc).__name__,
            "error_message": str(exc),
            "failure_stage": failure_stage,
            "mode": mode,
            "normalizer_version": NORMALIZER_VERSION,
            "page_index": active_page_index,
            "promotion_eligible": False,
            "promotion_performed": False,
            "raw_page_path": active_raw_page_path,
            "raw_page_sha256": active_raw_page_sha256,
            "reason_code": (
                "ROW_NORMALIZATION_FAILURE"
                if failure_stage == "page_normalization"
                else "COLLECTOR_OR_CONTRACT_FAILURE"
            ),
            "run_id": run_id,
            "schema_version": "FloridaSignalBrowardParcelFailureReceiptV2",
            "source_accounting": {
                "indexed_pages": indexed_pages,
                "indexed_rows": indexed_rows,
                "raw_pages_captured": raw_pages_captured,
                "raw_rows_captured": raw_rows_captured,
                "raw_rows_not_indexed": raw_rows_not_indexed,
                "row_partition_complete": row_partition_complete,
                "selected_source_rows": selected_source_rows,
                "winner_rows": (
                    finalization.accepted_rows if finalization is not None else None
                ),
                "rejected_rows": (
                    finalization.rejected_rows if finalization is not None else None
                ),
                "duplicate_rows": (
                    finalization.duplicate_rows if finalization is not None else None
                ),
            },
            "started_at": started_at,
            "status": "failed",
        }
        try:
            failure_path, failure_sha = evidence.write_json("failure-receipt.json", failure)
        except Exception as receipt_exc:
            raise ParcelGenerationError(
                "collector failed and its terminal failure receipt could not be "
                f"durably written: {type(exc).__name__}: {exc}; "
                f"receipt error: {type(receipt_exc).__name__}: {receipt_exc}"
            ) from receipt_exc
        delivery_error: Exception | None = None
        if (
            sink is not None
            and sink_started
        ):
            try:
                failure_key = f"broward-parcel-generations/{run_id}/{failure_path}"
                failure_storage_receipt = sink.upload_once(
                    failure_key,
                    (evidence.root / failure_path).read_bytes(),
                    "application/json",
                )
                sink.rpc(
                    "fs_fail_broward_parcel_generation",
                    {
                        "p_failure_receipt": failure
                        | {
                            "failure_object_bytes": failure_storage_receipt["bytes"],
                            "failure_object_key": failure_key,
                            "failure_object_sha256": failure_sha,
                            "storage_metadata_size": failure_storage_receipt[
                                "storage_metadata_size"
                            ],
                            "storage_object_id": failure_storage_receipt[
                                "storage_object_id"
                            ],
                            "storage_updated_at": failure_storage_receipt[
                                "storage_updated_at"
                            ],
                            "verification_method": failure_storage_receipt[
                                "verification_method"
                            ],
                        },
                        "p_generation_id": run_id,
                    },
                )
            except Exception as delivery_exc:
                delivery_error = delivery_exc
        message = (
            f"{type(exc).__name__}: {exc}; durable failure receipt "
            f"{failure_path} sha256={failure_sha}"
        )
        if delivery_error is not None:
            message += (
                "; database terminal failure delivery also failed: "
                f"{type(delivery_error).__name__}: {delivery_error}"
            )
        raise ParcelGenerationError(message) from exc
    finally:
        store.close()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--bucket", choices=(DEFAULT_BUCKET,), default=DEFAULT_BUCKET)
    parser.add_argument("--canary-rows", type=int, default=25)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--fixture-dir", type=Path)
    parser.add_argument(
        "--mode", choices=("canary", "current-generation"), default="canary"
    )
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--write-supabase", action="store_true")
    args = parser.parse_args(argv)
    if bool(args.fixture_dir) == bool(args.allow_network):
        parser.error("choose exactly one of --fixture-dir or --allow-network")
    if args.fixture_dir and args.write_supabase:
        parser.error("fixture input cannot be written to Supabase")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    run_id = args.run_id or str(uuid.uuid4())
    mode = args.mode.replace("-", "_")
    source: Source = FixtureSource(args.fixture_dir) if args.fixture_dir else ArcGISSource()
    try:
        sink = (
            SupabaseStagingSink.from_environment(args.bucket)
            if args.write_supabase
            else None
        )
        receipt = collect_generation(
            source=source,
            evidence_root=args.evidence_root,
            run_id=run_id,
            mode=mode,
            page_size=args.page_size,
            canary_rows=args.canary_rows,
            sink=sink,
        )
    except ParcelGenerationError as exc:
        print(f"Broward parcel generation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
