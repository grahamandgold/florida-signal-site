#!/usr/bin/env python3
"""Read-only SFWMD pending-ERP shadow collector.

This collector intentionally has no database, Supabase, queue, scoring, or
publication client. It reads the official SFWMD ArcGIS layer-14 contract and
writes one immutable-on-create local evidence bundle beneath an explicit
absolute output directory.

Network access is disabled unless ``--allow-network`` is supplied. Fixture
replay is the default development/test transport. Every run remains
``shadow_file_only`` and is never promotion eligible.
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
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence


LAYER_ID = 14
LAYER_NAME = "Pending Environmental Resource Applications (All Types)"
LAYER_URL = (
    "https://geoweb.sfwmd.gov/agsext1/rest/services/"
    "Regulation_ApplicationPermits/"
    "EnvironmentalResourceApplications_RegPermitting/MapServer/14"
)
QUERY_URL = f"{LAYER_URL}/query"
BOUNDARY_LAYER_ID = 44
BOUNDARY_LAYER_NAME = "Fort Lauderdale Municipal Boundary - Administrative Area"
BOUNDARY_LAYER_URL = (
    "https://gis.fortlauderdale.gov/arcgis/rest/services/"
    "GeneralPurpose/gisdata/MapServer/44"
)
BOUNDARY_QUERY_URL = f"{BOUNDARY_LAYER_URL}/query"
BOUNDARY_RECORD_NAME = "Fort Lauderdale"
BOUNDARY_RECORD_TYPE = "City"
BOUNDARY_LOCAL_FIPS = "12011"
BOUNDARY_WHERE = "NAME = 'Fort Lauderdale' AND TYPE = 'City'"
MAX_BOUNDARY_COMPONENTS = 32
BOUNDARY_FIELDS = (
    "OBJECTID",
    "NAME",
    "TYPE",
    "MUNIAREA",
    "LOCALFIPS",
    "Acres",
    "created_date",
    "last_edited_date",
    "GlobalID",
)
SOURCE_NATIVE_WKID = 2881
OUTPUT_WKID = 4326
SOURCE_TIME_ZONE = "America/New_York"
SOURCE_TIME_ZONE_WINDOWS = "Eastern Standard Time"
MAX_RECORD_COUNT = 2000
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_RETRIES = 3
DEFAULT_MAX_RESPONSE_BYTES = 64 * 1024 * 1024
COLLECTOR_VERSION = "sfwmd-pending-erp-shadow/1.0.0"
PARSER_VERSION = "sfwmd-layer14-parser/1.0.0"
NORMALIZER_VERSION = "sfwmd-layer14-normalizer/1.0.0"

EXPECTED_FIELDS = (
    "OBJECTID",
    "APP_NO",
    "PERMIT_NO",
    "APP_PERMIT_NO",
    "PROJECT_NAME",
    "MostRecentApp",
    "AppType",
    "AppTypeDesc",
    "PermitFamily",
    "PermitSubFamilyDesc",
    "PermitType",
    "ApplicantName",
    "ApplicantCompanyName",
    "FullNameOrCompany",
    "AppStatus",
    "PermitStatus",
    "LandUse",
    "ProjectAcres",
    "PermitAcres",
    "AppReceivedDate",
    "AppFinalActionDate",
    "LegalCompDate",
    "IssueDate",
    "PermitExpirationDate",
    "FullAddress",
    "City",
    "State",
    "PostalCode",
    "Link",
    "IsSWM",
    "IsTestData",
    "Shape",
    "GlobalID",
    "IsInPermitView",
    "Shape.STArea()",
    "Shape.STLength()",
)
QUERY_FIELDS = tuple(field for field in EXPECTED_FIELDS if field != "Shape")

EVENT_CLOCK_FIELDS = {
    "app_received_at": "AppReceivedDate",
    "legal_complete_at": "LegalCompDate",
    "app_final_action_at": "AppFinalActionDate",
    "issue_at": "IssueDate",
    "permit_expiration_at": "PermitExpirationDate",
}

SCHEMA_CONTRACT = {
    "schema_version": "FloridaSignalSfwmdLayer14ContractV1",
    "source_url": LAYER_URL,
    "layer_id": LAYER_ID,
    "layer_name": LAYER_NAME,
    "native_wkid": SOURCE_NATIVE_WKID,
    "query_output_wkid": OUTPUT_WKID,
    "max_record_count": MAX_RECORD_COUNT,
    "source_time_zone": SOURCE_TIME_ZONE,
    "source_time_zone_windows": SOURCE_TIME_ZONE_WINDOWS,
    "dates_in_unknown_timezone": False,
    "is_data_versioned": False,
    "historic_moment_supported": False,
    "business_identity": ["GlobalID", "APP_NO"],
    "paging_identity": "OBJECTID",
    "fields": list(EXPECTED_FIELDS),
    "query_fields": list(QUERY_FIELDS),
    "event_clocks": EVENT_CLOCK_FIELDS,
    "source_modified_clock": "UNKNOWN_NOT_EXPOSED",
    "scope": "official Fort Lauderdale boundary-component union intersection only",
    "boundary_query": BOUNDARY_WHERE,
    "boundary_output_crs": "EPSG:4326",
    "max_response_bytes": DEFAULT_MAX_RESPONSE_BYTES,
    "test_data_policy": "explicit IsTestData=true excluded",
    "mode": "shadow_file_only",
}

RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}
TRUE_VALUES = {True, 1, "1", "true", "t", "yes", "y"}
FALSE_VALUES = {False, 0, "0", "false", "f", "no", "n", "", None}
GLOBAL_ID_RE = re.compile(
    r"^\{?[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\}?$"
)


class CollectorError(RuntimeError):
    """Base class for a fail-closed collector error."""


class SourceContractError(CollectorError):
    """The official source no longer matches the pinned contract."""


class BoundaryContractError(CollectorError):
    """The spatial boundary evidence is absent or invalid."""


class FetchError(CollectorError):
    """A source request did not complete successfully."""

    def __init__(self, message: str, attempts: Sequence["FetchAttempt"]):
        super().__init__(message)
        self.attempts = list(attempts)


class SourceBudgetError(CollectorError):
    """The live source exceeded a fail-closed collection budget."""


@dataclasses.dataclass(frozen=True)
class FetchAttempt:
    status: int | None
    body: bytes
    error_class: str | None
    elapsed_ms: int
    observed_at: str | None = None


@dataclasses.dataclass(frozen=True)
class FetchResult:
    attempts: tuple[FetchAttempt, ...]

    @property
    def final(self) -> FetchAttempt:
        return self.attempts[-1]


class Transport(Protocol):
    def fetch(
        self,
        logical_name: str,
        url: str,
        params: Mapping[str, str],
    ) -> FetchResult:
        """Fetch one official resource and return all bounded attempts."""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        del request, fp, code, msg, headers, newurl
        return None


class NetworkTransport:
    """Bounded official-host transport with retry/timeout evidence."""

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        retries: int = DEFAULT_RETRIES,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        sleeper: Callable[[float], None] = time.sleep,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        if not 1 <= timeout_seconds <= 120:
            raise ValueError("timeout_seconds must be between 1 and 120")
        if not 0 <= retries <= 5:
            raise ValueError("retries must be between 0 and 5")
        if not 1 <= max_response_bytes <= 256 * 1024 * 1024:
            raise ValueError("max_response_bytes must be between 1 and 268435456")
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.max_response_bytes = max_response_bytes
        self.sleeper = sleeper
        self.opener = opener or urllib.request.build_opener(_NoRedirectHandler()).open

    def fetch(
        self,
        logical_name: str,
        url: str,
        params: Mapping[str, str],
    ) -> FetchResult:
        del logical_name
        if url not in {
            LAYER_URL,
            QUERY_URL,
            BOUNDARY_LAYER_URL,
            BOUNDARY_QUERY_URL,
        }:
            raise FetchError("refusing a non-contract source URL", [])

        encoded = urllib.parse.urlencode(sorted(params.items()))
        request = urllib.request.Request(
            f"{url}?{encoded}",
            headers={
                "Accept": "application/json",
                "User-Agent": f"FloridaSignal/{COLLECTOR_VERSION}",
            },
        )
        attempts: list[FetchAttempt] = []

        for attempt_index in range(self.retries + 1):
            started = time.monotonic()
            try:
                with self.opener(request, timeout=self.timeout_seconds) as response:
                    body = response.read(self.max_response_bytes + 1)
                    status = int(getattr(response, "status", response.getcode()))
                elapsed = round((time.monotonic() - started) * 1000)
                if len(body) > self.max_response_bytes:
                    attempts.append(
                        FetchAttempt(
                            status,
                            body[: self.max_response_bytes],
                            "ResponseTooLarge",
                            elapsed,
                            observed_at=iso_utc(utc_now()),
                        )
                    )
                    raise FetchError(
                        f"source response exceeded {self.max_response_bytes} bytes",
                        attempts,
                    )
                attempts.append(
                    FetchAttempt(
                        status,
                        body,
                        None,
                        elapsed,
                        observed_at=iso_utc(utc_now()),
                    )
                )
                if status in RETRYABLE_HTTP_STATUSES and attempt_index < self.retries:
                    self.sleeper(min(0.5 * (2**attempt_index), 4.0))
                    continue
                if not 200 <= status < 300:
                    raise FetchError(f"source returned HTTP {status}", attempts)
                return FetchResult(tuple(attempts))
            except urllib.error.HTTPError as exc:
                try:
                    body = exc.read(self.max_response_bytes + 1)
                except Exception:
                    body = b""
                elapsed = round((time.monotonic() - started) * 1000)
                if len(body) > self.max_response_bytes:
                    attempts.append(
                        FetchAttempt(
                            exc.code,
                            body[: self.max_response_bytes],
                            "ResponseTooLarge",
                            elapsed,
                            observed_at=iso_utc(utc_now()),
                        )
                    )
                    raise FetchError(
                        f"source error response exceeded {self.max_response_bytes} bytes",
                        attempts,
                    ) from None
                attempts.append(
                    FetchAttempt(
                        exc.code,
                        body,
                        "HTTPError",
                        elapsed,
                        observed_at=iso_utc(utc_now()),
                    )
                )
                if exc.code in RETRYABLE_HTTP_STATUSES and attempt_index < self.retries:
                    self.sleeper(min(0.5 * (2**attempt_index), 4.0))
                    continue
                raise FetchError(f"source returned HTTP {exc.code}", attempts) from None
            except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
                elapsed = round((time.monotonic() - started) * 1000)
                attempts.append(
                    FetchAttempt(
                        None,
                        b"",
                        type(exc).__name__,
                        elapsed,
                        observed_at=iso_utc(utc_now()),
                    )
                )
                if attempt_index < self.retries:
                    self.sleeper(min(0.5 * (2**attempt_index), 4.0))
                    continue
                raise FetchError(
                    f"source transport failed after {len(attempts)} attempt(s)",
                    attempts,
                ) from None

        raise AssertionError("unreachable retry loop")


class FixtureTransport:
    """Offline transport whose logical response files are explicit fixtures."""

    def __init__(self, fixture_dir: Path) -> None:
        self.fixture_dir = fixture_dir
        self.calls: list[tuple[str, str, dict[str, str]]] = []

    def fetch(
        self,
        logical_name: str,
        url: str,
        params: Mapping[str, str],
    ) -> FetchResult:
        self.calls.append((logical_name, url, dict(params)))
        path = self.fixture_dir / f"{logical_name}.json"
        if not path.is_file():
            raise FetchError(f"missing fixture response: {path.name}", [])
        return FetchResult(
            (
                FetchAttempt(
                    200,
                    path.read_bytes(),
                    None,
                    0,
                    observed_at=iso_utc(utc_now()),
                ),
            )
        )


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


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_utc(value: dt.datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("clock must be timezone-aware")
    return value.astimezone(dt.timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def epoch_millis_to_iso(value: Any, *, field: str) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SourceContractError(f"{field} must be epoch milliseconds or null")
    if not math.isfinite(float(value)):
        raise SourceContractError(f"{field} must be finite epoch milliseconds")
    try:
        parsed = dt.datetime.fromtimestamp(float(value) / 1000, tz=dt.timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise SourceContractError(f"{field} is outside the supported date range") from exc
    return iso_utc(parsed)


def parse_test_flag(value: Any) -> bool:
    comparable = value.strip().lower() if isinstance(value, str) else value
    if comparable in TRUE_VALUES:
        return True
    if comparable in FALSE_VALUES:
        return False
    raise SourceContractError("IsTestData contains an unknown value")


def normalize_global_id(value: Any) -> str:
    if not isinstance(value, str) or not GLOBAL_ID_RE.fullmatch(value.strip()):
        raise SourceContractError("GlobalID is missing or invalid")
    return str(uuid.UUID(value.strip().strip("{}")))


def normalize_app_no(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceContractError("APP_NO is missing or invalid")
    candidate = value.strip()
    if len(candidate) > 128 or any(ord(char) < 32 for char in candidate):
        raise SourceContractError("APP_NO is outside the accepted text contract")
    return candidate


def _wkid(value: Any) -> int | None:
    if not isinstance(value, Mapping):
        return None
    wkid = value.get("latestWkid", value.get("wkid"))
    return int(wkid) if isinstance(wkid, (int, float)) else None


def _supports(capabilities: Mapping[str, Any], key: str) -> bool:
    return capabilities.get(key) is True


def _query_formats(metadata: Mapping[str, Any]) -> set[str]:
    value = metadata.get("supportedQueryFormats", "")
    if not isinstance(value, str):
        return set()
    return {part.strip().lower() for part in value.split(",") if part.strip()}


def validate_layer_metadata(metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, Mapping):
        raise SourceContractError("layer metadata is not a JSON object")
    if metadata.get("error"):
        raise SourceContractError("layer metadata returned an ArcGIS error")
    if metadata.get("id") != LAYER_ID:
        raise SourceContractError("official layer id drifted from 14")
    if metadata.get("name") != LAYER_NAME:
        raise SourceContractError("official pending-layer name drifted")
    if metadata.get("geometryType") != "esriGeometryPolygon":
        raise SourceContractError("official layer geometry is no longer polygon")
    if metadata.get("maxRecordCount") != MAX_RECORD_COUNT:
        raise SourceContractError("official layer maxRecordCount drifted from 2000")
    if "json" not in _query_formats(metadata):
        raise SourceContractError("official layer no longer declares JSON query support")
    fields = metadata.get("fields")
    if not isinstance(fields, list) or not all(isinstance(row, Mapping) for row in fields):
        raise SourceContractError("official layer field metadata is missing")
    field_names = [row.get("name") for row in fields]
    missing = sorted(set(EXPECTED_FIELDS) - set(field_names))
    added = sorted(set(field_names) - set(EXPECTED_FIELDS))
    if missing or added or len(field_names) != len(set(field_names)):
        raise SourceContractError(
            f"official layer field contract drifted (missing={missing}, added={added})"
        )
    object_id_field = metadata.get("objectIdField") or metadata.get("objectIdFieldName")
    oid_fields = [
        row.get("name")
        for row in fields
        if row.get("type") == "esriFieldTypeOID"
    ]
    if object_id_field is None and oid_fields == ["OBJECTID"]:
        object_id_field = "OBJECTID"
    if object_id_field != "OBJECTID" or oid_fields != ["OBJECTID"]:
        raise SourceContractError("official layer OBJECTID contract drifted")
    global_field = next(row for row in fields if row.get("name") == "GlobalID")
    if global_field.get("type") != "esriFieldTypeGlobalID":
        raise SourceContractError("GlobalID is no longer a GlobalID field")

    native_wkid = _wkid(metadata.get("sourceSpatialReference"))
    if native_wkid is None:
        native_wkid = _wkid((metadata.get("extent") or {}).get("spatialReference"))
    if native_wkid != SOURCE_NATIVE_WKID:
        raise SourceContractError("official layer native spatial reference drifted")

    advanced = metadata.get("advancedQueryCapabilities") or {}
    if not isinstance(advanced, Mapping):
        raise SourceContractError("advanced query capabilities are missing")
    if not _supports(advanced, "supportsPagination"):
        raise SourceContractError("official layer no longer supports pagination")
    if not _supports(advanced, "supportsOrderBy"):
        raise SourceContractError("official layer no longer supports ordered queries")
    if advanced.get("supportsQueryWithHistoricMoment") is True:
        raise SourceContractError("historicMoment support changed; review snapshot contract")
    if metadata.get("isDataVersioned") is not False:
        raise SourceContractError("versioning contract changed; review collector")
    if metadata.get("datesInUnknownTimezone") is not False:
        raise SourceContractError("source date timezone contract changed")

    for key in ("dateFieldsTimeReference", "preferredTimeReference"):
        reference = metadata.get(key)
        if not isinstance(reference, Mapping):
            raise SourceContractError(f"{key} is missing")
        if reference.get("timeZone") != SOURCE_TIME_ZONE_WINDOWS:
            raise SourceContractError(f"{key} Windows timezone drifted")
        if reference.get("timeZoneIANA") != SOURCE_TIME_ZONE:
            raise SourceContractError(f"{key} IANA timezone drifted")
        if reference.get("respectsDaylightSaving") is not True:
            raise SourceContractError(f"{key} DST contract drifted")

    editing_info = metadata.get("editingInfo")
    if isinstance(editing_info, Mapping) and editing_info.get("lastEditDate") is not None:
        raise SourceContractError(
            "source now exposes lastEditDate; review before assigning a source clock"
        )

    schema_projection = {
        "id": metadata.get("id"),
        "name": metadata.get("name"),
        "geometryType": metadata.get("geometryType"),
        "objectIdField": object_id_field,
        "maxRecordCount": metadata.get("maxRecordCount"),
        "supportedQueryFormats": metadata.get("supportedQueryFormats"),
        "nativeWkid": native_wkid,
        "isDataVersioned": metadata.get("isDataVersioned"),
        "datesInUnknownTimezone": metadata.get("datesInUnknownTimezone"),
        "dateFieldsTimeReference": metadata.get("dateFieldsTimeReference"),
        "preferredTimeReference": metadata.get("preferredTimeReference"),
        "advancedQueryCapabilities": {
            "supportsPagination": advanced.get("supportsPagination"),
            "supportsOrderBy": advanced.get("supportsOrderBy"),
            "supportsQueryWithHistoricMoment": advanced.get(
                "supportsQueryWithHistoricMoment", False
            ),
        },
        "fields": [
            {"name": row.get("name"), "type": row.get("type")} for row in fields
        ],
    }
    return schema_projection


def validate_object_ids(payload: Any) -> list[int]:
    if not isinstance(payload, Mapping) or payload.get("error"):
        raise SourceContractError("object-id query returned an invalid response")
    if payload.get("objectIdFieldName") != "OBJECTID":
        raise SourceContractError("object-id response field drifted")
    values = payload.get("objectIds")
    if values is None:
        values = []
    if not isinstance(values, list):
        raise SourceContractError("object-id response is not a list")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise SourceContractError("object-id response contains a non-integer")
    if len(values) != len(set(values)):
        raise SourceContractError("object-id response contains duplicates")
    return sorted(values)


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


Point = tuple[float, float]
Ring = list[Point]
BoundaryComponents = list[list[Ring]]


def _point(value: Any) -> Point:
    if (
        not isinstance(value, list)
        or len(value) < 2
        or not _is_number(value[0])
        or not _is_number(value[1])
    ):
        raise BoundaryContractError("polygon contains an invalid coordinate")
    return float(value[0]), float(value[1])


def _ring(value: Any) -> Ring:
    if not isinstance(value, list) or len(value) < 4:
        raise BoundaryContractError("polygon ring must contain at least four coordinates")
    ring = [_point(point) for point in value]
    if ring[0] != ring[-1]:
        raise BoundaryContractError("polygon ring must be explicitly closed")
    if len(set(ring[:-1])) < 3:
        raise BoundaryContractError("polygon ring has fewer than three unique vertices")
    return ring


def _geojson_polygon_rings(geometry: Mapping[str, Any]) -> list[Ring]:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Polygon":
        if not isinstance(coordinates, list):
            raise BoundaryContractError("boundary Polygon coordinates are missing")
        return [_ring(ring) for ring in coordinates]
    if geometry_type == "MultiPolygon":
        if not isinstance(coordinates, list):
            raise BoundaryContractError("boundary MultiPolygon coordinates are missing")
        return [_ring(ring) for polygon in coordinates for ring in polygon]
    raise BoundaryContractError("boundary must contain only Polygon/MultiPolygon geometry")


def validate_boundary_layer_metadata(metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, Mapping) or metadata.get("error"):
        raise BoundaryContractError("official city boundary metadata is invalid")
    if metadata.get("id") != BOUNDARY_LAYER_ID:
        raise BoundaryContractError("official city boundary layer id drifted")
    if metadata.get("name") != BOUNDARY_LAYER_NAME:
        raise BoundaryContractError("official city boundary layer name drifted")
    if metadata.get("geometryType") != "esriGeometryPolygon":
        raise BoundaryContractError("official city boundary is no longer polygon data")
    if metadata.get("maxRecordCount") != 100000:
        raise BoundaryContractError("official city boundary transfer limit drifted")
    if "geojson" not in _query_formats(metadata):
        raise BoundaryContractError("official city boundary no longer declares GeoJSON")
    fields = metadata.get("fields")
    if not isinstance(fields, list) or not all(isinstance(row, Mapping) for row in fields):
        raise BoundaryContractError("official city boundary fields are missing")
    field_names = [row.get("name") for row in fields]
    missing = sorted(set(BOUNDARY_FIELDS) - set(field_names))
    if missing:
        raise BoundaryContractError(
            f"official city boundary field contract drifted (missing={missing})"
        )
    object_id_field = metadata.get("objectIdField") or metadata.get("objectIdFieldName")
    oid_fields = [
        row.get("name")
        for row in fields
        if row.get("type") == "esriFieldTypeOID"
    ]
    # This City service currently omits objectIdField/objectIdFieldName from
    # layer metadata even though its schema exposes one unambiguous OID field.
    # Accept that exact representation only; never guess among multiple or
    # differently named OID fields.
    if object_id_field is None and oid_fields == ["OBJECTID"]:
        object_id_field = "OBJECTID"
    if object_id_field != "OBJECTID" or oid_fields != ["OBJECTID"]:
        raise BoundaryContractError("official city boundary OBJECTID contract drifted")
    global_field = next(row for row in fields if row.get("name") == "GlobalID")
    if global_field.get("type") != "esriFieldTypeGlobalID":
        raise BoundaryContractError("official city boundary GlobalID contract drifted")
    advanced = metadata.get("advancedQueryCapabilities") or {}
    if not isinstance(advanced, Mapping) or not _supports(advanced, "supportsOrderBy"):
        raise BoundaryContractError("official city boundary no longer supports ordered queries")
    return {
        "id": metadata.get("id"),
        "name": metadata.get("name"),
        "geometryType": metadata.get("geometryType"),
        "objectIdField": object_id_field,
        "maxRecordCount": metadata.get("maxRecordCount"),
        "supportedQueryFormats": metadata.get("supportedQueryFormats"),
        "advancedQueryCapabilities": {
            "supportsOrderBy": advanced.get("supportsOrderBy"),
        },
        "fields": [
            {"name": row.get("name"), "type": row.get("type")} for row in fields
        ],
    }


def validate_boundary_feature(payload: Any) -> tuple[BoundaryComponents, dict[str, Any]]:
    if not isinstance(payload, Mapping) or payload.get("type") != "FeatureCollection":
        raise BoundaryContractError("official city boundary query did not return GeoJSON")
    crs = payload.get("crs")
    if (
        not isinstance(crs, Mapping)
        or crs.get("type") != "name"
        or not isinstance(crs.get("properties"), Mapping)
        or crs["properties"].get("name") != "EPSG:4326"
    ):
        raise BoundaryContractError("official city boundary query CRS is not EPSG:4326")
    features = payload.get("features")
    if (
        not isinstance(features, list)
        or not features
        or len(features) > MAX_BOUNDARY_COMPONENTS
    ):
        raise BoundaryContractError(
            "official city boundary query returned no components or an unsafe component count"
        )
    components: BoundaryComponents = []
    records: list[dict[str, Any]] = []
    seen_object_ids: set[int] = set()
    seen_global_ids: set[str] = set()
    for feature in features:
        if not isinstance(feature, Mapping):
            raise BoundaryContractError("official city boundary feature is invalid")
        properties = feature.get("properties")
        if not isinstance(properties, Mapping):
            raise BoundaryContractError("official city boundary properties are missing")
        try:
            canonical_json_bytes(dict(properties))
        except (TypeError, ValueError) as exc:
            raise BoundaryContractError(
                "official city boundary properties are not canonical JSON values"
            ) from exc
        if properties.get("NAME") != BOUNDARY_RECORD_NAME:
            raise BoundaryContractError("official city boundary NAME does not match exactly")
        if properties.get("TYPE") != BOUNDARY_RECORD_TYPE:
            raise BoundaryContractError("official city boundary TYPE does not match exactly")
        if properties.get("LOCALFIPS") != BOUNDARY_LOCAL_FIPS:
            raise BoundaryContractError("official city boundary LOCALFIPS drifted")
        object_id = properties.get("OBJECTID")
        if isinstance(object_id, bool) or not isinstance(object_id, int):
            raise BoundaryContractError("official city boundary OBJECTID is invalid")
        try:
            global_id = normalize_global_id(properties.get("GlobalID"))
        except SourceContractError as exc:
            raise BoundaryContractError("official city boundary GlobalID is invalid") from exc
        if object_id in seen_object_ids or global_id in seen_global_ids:
            raise BoundaryContractError("official city boundary component identity is duplicated")
        seen_object_ids.add(object_id)
        seen_global_ids.add(global_id)
        geometry = feature.get("geometry")
        if not isinstance(geometry, Mapping):
            raise BoundaryContractError("official city boundary geometry is missing")
        component_rings = _geojson_polygon_rings(geometry)
        components.append(component_rings)
        records.append(
            {
                "object_id": object_id,
                "global_id": global_id,
                "municipal_area": properties.get("MUNIAREA"),
                "acres": properties.get("Acres"),
                "created_date": properties.get("created_date"),
                "last_edited_date": properties.get("last_edited_date"),
                "ring_count": len(component_rings),
            }
        )
    records.sort(key=lambda row: row["object_id"])
    return components, {
        "name": BOUNDARY_RECORD_NAME,
        "type": BOUNDARY_RECORD_TYPE,
        "local_fips": BOUNDARY_LOCAL_FIPS,
        "record_count": len(records),
        "object_ids": [row["object_id"] for row in records],
        "global_ids": [row["global_id"] for row in records],
        "components": records,
    }


def _point_on_segment(point: Point, start: Point, end: Point, eps: float = 1e-10) -> bool:
    cross = (point[1] - start[1]) * (end[0] - start[0]) - (
        point[0] - start[0]
    ) * (end[1] - start[1])
    if abs(cross) > eps:
        return False
    dot = (point[0] - start[0]) * (end[0] - start[0]) + (
        point[1] - start[1]
    ) * (end[1] - start[1])
    if dot < -eps:
        return False
    length_squared = (end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2
    return dot <= length_squared + eps


def point_in_rings(point: Point, rings: Sequence[Ring]) -> bool:
    inside = False
    x, y = point
    for ring in rings:
        ring_inside = False
        for index in range(len(ring) - 1):
            start, end = ring[index], ring[index + 1]
            if _point_on_segment(point, start, end):
                return True
            if (start[1] > y) != (end[1] > y):
                crossing_x = (end[0] - start[0]) * (y - start[1]) / (
                    end[1] - start[1]
                ) + start[0]
                if x < crossing_x:
                    ring_inside = not ring_inside
        if ring_inside:
            inside = not inside
    return inside


def _orientation(a: Point, b: Point, c: Point) -> int:
    value = (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (
        c[1] - b[1]
    )
    if abs(value) < 1e-10:
        return 0
    return 1 if value > 0 else 2


def segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    o1, o2 = _orientation(a, b, c), _orientation(a, b, d)
    o3, o4 = _orientation(c, d, a), _orientation(c, d, b)
    if o1 != o2 and o3 != o4:
        return True
    return (
        (o1 == 0 and _point_on_segment(c, a, b))
        or (o2 == 0 and _point_on_segment(d, a, b))
        or (o3 == 0 and _point_on_segment(a, c, d))
        or (o4 == 0 and _point_on_segment(b, c, d))
    )


def rings_bbox(rings: Sequence[Ring]) -> tuple[float, float, float, float]:
    points = [point for ring in rings for point in ring]
    if not points:
        raise SourceContractError("polygon has no coordinates")
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def bboxes_intersect(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> bool:
    return not (
        left[2] < right[0]
        or right[2] < left[0]
        or left[3] < right[1]
        or right[3] < left[1]
    )


def polygon_intersects(
    source_rings: Sequence[Ring],
    boundary_rings: Sequence[Ring],
    boundary_bbox: tuple[float, float, float, float] | None = None,
) -> bool:
    effective_boundary_bbox = boundary_bbox or rings_bbox(boundary_rings)
    if not bboxes_intersect(rings_bbox(source_rings), effective_boundary_bbox):
        return False
    if any(point_in_rings(point, boundary_rings) for ring in source_rings for point in ring[:-1]):
        return True
    if any(point_in_rings(point, source_rings) for ring in boundary_rings for point in ring[:-1]):
        return True
    for source_ring in source_rings:
        for boundary_ring in boundary_rings:
            for source_index in range(len(source_ring) - 1):
                for boundary_index in range(len(boundary_ring) - 1):
                    if segments_intersect(
                        source_ring[source_index],
                        source_ring[source_index + 1],
                        boundary_ring[boundary_index],
                        boundary_ring[boundary_index + 1],
                    ):
                        return True
    return False


def polygon_intersects_boundary_components(
    source_rings: Sequence[Ring],
    boundary_components: Sequence[Sequence[Ring]],
    boundary_bboxes: Sequence[tuple[float, float, float, float]] | None = None,
) -> bool:
    """Apply union semantics across separately published city components.

    Flattening overlapping official components into one parity ring set can
    create false holes. Each component therefore retains its own polygon/hole
    parity and a source feature is in scope when it intersects any component.
    """
    if boundary_bboxes is not None and len(boundary_bboxes) != len(boundary_components):
        raise ValueError("boundary component bbox count does not match components")
    for index, component in enumerate(boundary_components):
        component_bbox = boundary_bboxes[index] if boundary_bboxes is not None else None
        if polygon_intersects(source_rings, component, component_bbox):
            return True
    return False


def source_geometry_rings(geometry: Any) -> list[Ring]:
    if not isinstance(geometry, Mapping) or not isinstance(geometry.get("rings"), list):
        raise SourceContractError("source feature lacks polygon rings")
    try:
        rings = [_ring(ring) for ring in geometry["rings"]]
    except BoundaryContractError as exc:
        raise SourceContractError(str(exc)) from exc
    if not rings:
        raise SourceContractError("source feature polygon is empty")
    return rings


def validate_page(payload: Any, requested_ids: Sequence[int]) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping) or payload.get("error"):
        raise SourceContractError("feature page returned an invalid response")
    if payload.get("geometryType") != "esriGeometryPolygon":
        raise SourceContractError("feature page geometry type drifted")
    if _wkid(payload.get("spatialReference")) != OUTPUT_WKID:
        raise SourceContractError("feature page was not returned in WKID 4326")
    if payload.get("exceededTransferLimit") is True:
        raise SourceContractError("feature page exceeded the transfer limit")
    fields = payload.get("fields")
    if not isinstance(fields, list) or not all(isinstance(row, Mapping) for row in fields):
        raise SourceContractError("feature page field contract is missing")
    page_field_names = tuple(row.get("name") for row in fields)
    if page_field_names != QUERY_FIELDS:
        raise SourceContractError("feature page field contract drifted")
    features = payload.get("features")
    if not isinstance(features, list):
        raise SourceContractError("feature page lacks a feature list")
    if not all(isinstance(feature, Mapping) for feature in features):
        raise SourceContractError("feature page contains an invalid feature")
    actual_ids: list[int] = []
    copied: list[dict[str, Any]] = []
    for feature in features:
        attributes = feature.get("attributes")
        if not isinstance(attributes, Mapping):
            raise SourceContractError("feature attributes are missing")
        if set(attributes) != set(QUERY_FIELDS):
            raise SourceContractError("feature attribute contract drifted")
        object_id = attributes.get("OBJECTID")
        if isinstance(object_id, bool) or not isinstance(object_id, int):
            raise SourceContractError("feature OBJECTID is invalid")
        actual_ids.append(object_id)
        copied.append(dict(feature))
    if actual_ids != sorted(actual_ids):
        raise SourceContractError("feature page is not ordered by OBJECTID")
    if actual_ids != list(requested_ids):
        raise SourceContractError("feature page does not exactly match requested OBJECTIDs")
    return copied


class EvidenceBundle:
    """Write one new run directory; never overwrite an existing run."""

    def __init__(self, output_root: Path, run_id: str) -> None:
        if not output_root.is_absolute():
            raise CollectorError("--output-dir must be an explicit absolute path")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", run_id):
            raise CollectorError("run_id contains unsafe characters")
        output_root.mkdir(parents=True, exist_ok=True)
        self.run_dir = output_root / run_id
        self.run_dir.mkdir(mode=0o700)
        self.raw_dir = self.run_dir / "raw"
        self.raw_dir.mkdir(mode=0o700)
        self.raw_entries: list[dict[str, Any]] = []

    @staticmethod
    def _write_private_create_only(path: Path, body: bytes) -> None:
        with path.open("xb") as handle:
            handle.write(body)
        os.chmod(path, 0o600)

    def capture(
        self,
        logical_name: str,
        url: str,
        params: Mapping[str, str],
        attempts: Sequence[FetchAttempt],
    ) -> None:
        if not attempts:
            self.raw_entries.append(
                {
                    "logical_name": logical_name,
                    "source_url": url,
                    "request_params": dict(sorted(params.items())),
                    "attempt": 0,
                    "observed_at": iso_utc(utc_now()),
                    "http_status": None,
                    "error_class": "NO_RESPONSE",
                    "elapsed_ms": 0,
                    "bytes": 0,
                    "sha256": sha256_bytes(b""),
                    "object_path": None,
                }
            )
            return
        for attempt_number, attempt in enumerate(attempts, start=1):
            suffix = "json" if attempt.body else "empty"
            filename = f"{logical_name}.attempt-{attempt_number:02d}.{suffix}"
            path = self.raw_dir / filename
            self._write_private_create_only(path, attempt.body)
            self.raw_entries.append(
                {
                    "logical_name": logical_name,
                    "source_url": url,
                    "request_params": dict(sorted(params.items())),
                    "attempt": attempt_number,
                    "observed_at": attempt.observed_at or iso_utc(utc_now()),
                    "http_status": attempt.status,
                    "error_class": attempt.error_class,
                    "elapsed_ms": attempt.elapsed_ms,
                    "bytes": len(attempt.body),
                    "sha256": sha256_bytes(attempt.body),
                    "truncated": attempt.error_class == "ResponseTooLarge",
                    "object_path": f"raw/{filename}",
                }
            )

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

    def finalize_raw_manifest(self) -> tuple[Path, str]:
        return self.write_json(
            "raw-manifest.json",
            {
                "schema_version": "FloridaSignalRawResponseManifestV1",
                "responses": self.raw_entries,
            },
        )


def decode_json(result: FetchResult, *, label: str) -> Any:
    try:
        return json.loads(result.final.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceContractError(f"{label} is not valid JSON") from exc


def fetch_and_capture(
    *,
    transport: Transport,
    bundle: EvidenceBundle,
    logical_name: str,
    url: str,
    params: Mapping[str, str],
) -> Any:
    try:
        result = transport.fetch(logical_name, url, params)
    except FetchError as exc:
        bundle.capture(logical_name, url, params, exc.attempts)
        raise
    bundle.capture(logical_name, url, params, result.attempts)
    return decode_json(result, label=logical_name)


def _event_clock_maxima(records: Sequence[Mapping[str, Any]]) -> dict[str, str | None]:
    maxima: dict[str, str | None] = {}
    for normalized_name in EVENT_CLOCK_FIELDS:
        values = [
            row["event_clocks"].get(normalized_name)
            for row in records
            if row["event_clocks"].get(normalized_name)
        ]
        maxima[normalized_name] = max(values) if values else None
    return maxima


def normalize_feature(
    feature: Mapping[str, Any],
    *,
    observed_at: str,
    boundary_components: Sequence[Sequence[Ring]],
    boundary_bboxes: Sequence[tuple[float, float, float, float]],
    boundary_sha256: str,
) -> tuple[str, dict[str, Any] | None, str | None]:
    attributes = feature.get("attributes")
    if not isinstance(attributes, Mapping):
        return "rejected", None, "missing_attributes"
    try:
        is_test = parse_test_flag(attributes.get("IsTestData"))
        if is_test:
            return "test_excluded", None, None
        object_id = attributes.get("OBJECTID")
        if isinstance(object_id, bool) or not isinstance(object_id, int):
            raise SourceContractError("OBJECTID is invalid")
        global_id = normalize_global_id(attributes.get("GlobalID"))
        app_no = normalize_app_no(attributes.get("APP_NO"))
        source_rings = source_geometry_rings(feature.get("geometry"))
        intersects = polygon_intersects_boundary_components(
            source_rings,
            boundary_components,
            boundary_bboxes,
        )
        if not intersects:
            return "outside_boundary", None, None
        event_clocks = {
            normalized: epoch_millis_to_iso(attributes.get(source), field=source)
            for normalized, source in EVENT_CLOCK_FIELDS.items()
        }
    except SourceContractError as exc:
        return "rejected", None, str(exc)

    try:
        source_content_sha = sha256_bytes(
            canonical_json_bytes(
                {
                    "schema_version": "FloridaSignalSfwmdSourceContentV1",
                    "attributes": {
                        key: value for key, value in attributes.items() if key != "OBJECTID"
                    },
                    "geometry": feature.get("geometry"),
                }
            )
        )
    except (TypeError, ValueError):
        return "rejected", None, "source feature contains non-canonical JSON values"

    record = {
        "schema_version": "FloridaSignalSfwmdPendingErpShadowRowV1",
        "identity": {"global_id": global_id, "app_no": app_no},
        "identity_key": f"{global_id}|{app_no}",
        "source": {
            "agency": "South Florida Water Management District",
            "layer_id": LAYER_ID,
            "layer_name": LAYER_NAME,
            "object_id": object_id,
            "pending_population_membership": True,
            "app_status": attributes.get("AppStatus"),
        },
        "scope": {
            "jurisdiction": "City of Fort Lauderdale",
            "basis": "official_boundary_polygon_intersection",
            "boundary_sha256": boundary_sha256,
            "mailing_city_used_for_scope": False,
        },
        "clocks": {
            "observed_at": observed_at,
            "source_modified_at": None,
            "source_modified_status": "UNKNOWN_NOT_EXPOSED",
            "source_time_zone": SOURCE_TIME_ZONE,
        },
        "event_clocks": event_clocks,
        "attributes": dict(attributes),
        "geometry": feature.get("geometry"),
        "source_content_sha256": source_content_sha,
    }
    return "included", record, None


def make_run_id(now: dt.datetime | None = None) -> str:
    instant = now or utc_now()
    return f"sfwmd-shadow-{instant.astimezone(dt.timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:12]}"


def run_collection(
    *,
    output_root: Path,
    transport: Transport,
    page_size: int = MAX_RECORD_COUNT,
    run_id: str | None = None,
    clock: Callable[[], dt.datetime] = utc_now,
) -> tuple[Path, dict[str, Any]]:
    if not 1 <= page_size <= MAX_RECORD_COUNT:
        raise CollectorError("page_size must be between 1 and 2000")
    run_id = run_id or make_run_id(clock())
    bundle = EvidenceBundle(output_root, run_id)
    started_at = iso_utc(clock())
    schema_contract_sha = sha256_bytes(canonical_json_bytes(SCHEMA_CONTRACT))
    boundary_sha = None
    boundary_source_schema_sha = None
    boundary_reference_sha = None
    boundary_record: dict[str, Any] | None = None
    source_schema_sha = None
    rows: list[dict[str, Any]] = []
    rejection_reasons: dict[str, int] = {}
    app_status_counts_observed: dict[str, int] = {}
    app_status_counts_in_scope: dict[str, int] = {}
    counts = {
        "rows_observed": 0,
        "rows_shadow_included": 0,
        "rows_test_excluded": 0,
        "rows_outside_boundary": 0,
        "rows_rejected": 0,
        "duplicate_identities": 0,
        "pages_expected": 0,
        "pages_succeeded": 0,
    }
    start_ids: list[int] = []
    end_ids: list[int] = []
    terminal_error: str | None = None

    try:
        boundary_metadata = fetch_and_capture(
            transport=transport,
            bundle=bundle,
            logical_name="boundary-layer-metadata",
            url=BOUNDARY_LAYER_URL,
            params={"f": "json"},
        )
        boundary_schema_projection = validate_boundary_layer_metadata(boundary_metadata)
        boundary_source_schema_sha = sha256_bytes(
            canonical_json_bytes(boundary_schema_projection)
        )
        boundary_params = {
            "f": "geojson",
            "where": BOUNDARY_WHERE,
            "outFields": ",".join(BOUNDARY_FIELDS),
            "returnGeometry": "true",
            "outSR": str(OUTPUT_WKID),
            "orderByFields": "OBJECTID ASC",
        }
        boundary_payload = fetch_and_capture(
            transport=transport,
            bundle=bundle,
            logical_name="boundary-fort-lauderdale",
            url=BOUNDARY_QUERY_URL,
            params=boundary_params,
        )
        boundary_sha = bundle.raw_entries[-1]["sha256"]
        boundary_components, boundary_record = validate_boundary_feature(boundary_payload)
        boundary_bboxes = [rings_bbox(component) for component in boundary_components]
        _, boundary_reference_sha = bundle.write_json(
            "boundary-reference.json",
            {
                "schema_version": "FloridaSignalBoundaryReferenceV1",
                "source_url": BOUNDARY_LAYER_URL,
                "source_agency": "City of Fort Lauderdale",
                "layer_id": BOUNDARY_LAYER_ID,
                "layer_name": BOUNDARY_LAYER_NAME,
                "query_where": boundary_params["where"],
                "jurisdiction": "City of Fort Lauderdale",
                "spatial_reference_wkid": OUTPUT_WKID,
                "record": boundary_record,
                "boundary_sha256": boundary_sha,
                "source_schema_sha256": boundary_source_schema_sha,
            },
        )

        metadata = fetch_and_capture(
            transport=transport,
            bundle=bundle,
            logical_name="layer-metadata",
            url=LAYER_URL,
            params={"f": "json"},
        )
        schema_projection = validate_layer_metadata(metadata)
        source_schema_sha = sha256_bytes(canonical_json_bytes(schema_projection))

        ids_params = {"f": "json", "where": "1=1", "returnIdsOnly": "true"}
        start_payload = fetch_and_capture(
            transport=transport,
            bundle=bundle,
            logical_name="object-ids-start",
            url=QUERY_URL,
            params=ids_params,
        )
        start_ids = validate_object_ids(start_payload)
        if len(start_ids) > MAX_RECORD_COUNT:
            raise SourceBudgetError(
                f"source returned {len(start_ids)} object ids; maximum is {MAX_RECORD_COUNT}"
            )
        chunks = [
            start_ids[index : index + page_size]
            for index in range(0, len(start_ids), page_size)
        ]
        counts["pages_expected"] = len(chunks)

        features: list[dict[str, Any]] = []
        for page_number, object_ids in enumerate(chunks, start=1):
            if len(object_ids) == 1:
                page_where = f"OBJECTID = {object_ids[0]}"
            else:
                page_where = (
                    f"OBJECTID >= {object_ids[0]} AND OBJECTID <= {object_ids[-1]}"
                )
            page_params = {
                "f": "json",
                "where": page_where,
                "outFields": "*",
                "returnGeometry": "true",
                "returnZ": "false",
                "returnM": "false",
                "outSR": str(OUTPUT_WKID),
                "orderByFields": "OBJECTID ASC",
                "resultOffset": "0",
                "resultRecordCount": str(len(object_ids)),
            }
            page_payload = fetch_and_capture(
                transport=transport,
                bundle=bundle,
                logical_name=f"page-{page_number:04d}",
                url=QUERY_URL,
                params=page_params,
            )
            page_features = validate_page(page_payload, object_ids)
            if len(features) + len(page_features) > MAX_RECORD_COUNT:
                raise SourceBudgetError(
                    f"feature pagination exceeded the {MAX_RECORD_COUNT}-row run budget"
                )
            features.extend(page_features)
            counts["pages_succeeded"] += 1

        end_payload = fetch_and_capture(
            transport=transport,
            bundle=bundle,
            logical_name="object-ids-end",
            url=QUERY_URL,
            params=ids_params,
        )
        end_ids = validate_object_ids(end_payload)
        if len(end_ids) > MAX_RECORD_COUNT:
            raise SourceBudgetError(
                f"end object-id set exceeded the {MAX_RECORD_COUNT}-row run budget"
            )
        counts["rows_observed"] = len(features)

        observed_clock = iso_utc(clock())
        seen_identities: set[str] = set()
        for feature in features:
            feature_attributes = feature.get("attributes")
            if isinstance(feature_attributes, Mapping):
                raw_status = feature_attributes.get("AppStatus")
                status_key = "<NULL>" if raw_status is None else str(raw_status)
                app_status_counts_observed[status_key] = (
                    app_status_counts_observed.get(status_key, 0) + 1
                )
            category, record, reason = normalize_feature(
                feature,
                observed_at=observed_clock,
                boundary_components=boundary_components,
                boundary_bboxes=boundary_bboxes,
                boundary_sha256=boundary_sha,
            )
            if category == "included" and record is not None:
                if record["identity_key"] in seen_identities:
                    counts["duplicate_identities"] += 1
                    counts["rows_rejected"] += 1
                    rejection_reasons["duplicate_business_identity"] = (
                        rejection_reasons.get("duplicate_business_identity", 0) + 1
                    )
                    continue
                seen_identities.add(record["identity_key"])
                rows.append(record)
                counts["rows_shadow_included"] += 1
                in_scope_status = record["source"].get("app_status")
                in_scope_status_key = (
                    "<NULL>" if in_scope_status is None else str(in_scope_status)
                )
                app_status_counts_in_scope[in_scope_status_key] = (
                    app_status_counts_in_scope.get(in_scope_status_key, 0) + 1
                )
            elif category == "test_excluded":
                counts["rows_test_excluded"] += 1
            elif category == "outside_boundary":
                counts["rows_outside_boundary"] += 1
            else:
                counts["rows_rejected"] += 1
                safe_reason = reason or "unknown_rejection"
                rejection_reasons[safe_reason] = rejection_reasons.get(safe_reason, 0) + 1

        rows.sort(key=lambda row: row["source"]["object_id"])
    except (CollectorError, OSError) as exc:
        terminal_error = f"{type(exc).__name__}: {exc}"

    records_path, records_sha = bundle.write_jsonl("shadow-records.jsonl", rows)
    del records_path
    content_index = sorted(
        [
            {
                "identity_key": row["identity_key"],
                "source_content_sha256": row["source_content_sha256"],
            }
            for row in rows
        ],
        key=lambda item: item["identity_key"],
    )
    _, content_index_sha = bundle.write_jsonl(
        "shadow-content-index.jsonl", content_index
    )
    raw_manifest_path, raw_manifest_sha = bundle.finalize_raw_manifest()
    del raw_manifest_path
    finished_at = iso_utc(clock())

    identity_stable = start_ids == end_ids if start_ids or end_ids else terminal_error is None
    accounting_ok = counts["rows_observed"] == (
        counts["rows_shadow_included"]
        + counts["rows_test_excluded"]
        + counts["rows_outside_boundary"]
        + counts["rows_rejected"]
    )
    source_count_parity = counts["rows_observed"] == len(start_ids)
    if terminal_error and terminal_error.startswith("SourceBudgetError:"):
        status = "failed"
        reason_code = "SOURCE_ROW_BUDGET_EXCEEDED"
    elif terminal_error:
        status = "failed"
        reason_code = "COLLECTOR_OR_CONTRACT_FAILURE"
    elif not identity_stable:
        status = "partial"
        reason_code = "SOURCE_OBJECT_ID_SET_CHANGED_DURING_RUN"
    elif counts["rows_rejected"] or not accounting_ok or not source_count_parity:
        status = "partial"
        reason_code = "ROW_QUALITY_OR_ACCOUNTING_FAILURE"
    elif counts["rows_observed"] == 0:
        status = "empty"
        reason_code = None
    else:
        status = "ok"
        reason_code = None

    receipt = {
        "schema_version": "FloridaSignalSfwmdPendingErpShadowReceiptV1",
        "run_id": run_id,
        "mode": "shadow_file_only",
        "dry_run": True,
        "status": status,
        "reason_code": reason_code,
        "terminal_error": terminal_error,
        "source": {
            "agency": "South Florida Water Management District",
            "url": LAYER_URL,
            "layer_id": LAYER_ID,
            "layer_name": LAYER_NAME,
            "population": "pending environmental resource applications (all types)",
            "native_wkid": SOURCE_NATIVE_WKID,
            "query_output_wkid": OUTPUT_WKID,
            "is_data_versioned": False,
            "historic_moment_supported": False,
        },
        "versions": {
            "collector": COLLECTOR_VERSION,
            "parser": PARSER_VERSION,
            "normalizer": NORMALIZER_VERSION,
        },
        "clocks": {
            "run_started_at": started_at,
            "observed_at": finished_at,
            "source_checked_at": finished_at,
            "source_modified_at": None,
            "source_modified_status": "UNKNOWN_NOT_EXPOSED",
            "source_time_zone": SOURCE_TIME_ZONE,
        },
        "event_clock_maxima": _event_clock_maxima(rows),
        "event_through": _event_clock_maxima(rows).get("app_received_at"),
        "event_through_semantics": "maximum AppReceivedDate among included Fort Lauderdale shadow rows",
        "scope": {
            "jurisdiction": "City of Fort Lauderdale",
            "basis": "official_boundary_polygon_intersection",
            "mailing_city_used_for_scope": False,
            "boundary_source_url": BOUNDARY_LAYER_URL,
            "boundary_layer_id": BOUNDARY_LAYER_ID,
            "boundary_layer_name": BOUNDARY_LAYER_NAME,
            "boundary_record": boundary_record,
            "boundary_sha256": boundary_sha,
            "boundary_source_schema_sha256": boundary_source_schema_sha,
        },
        "counts": counts,
        "app_status_counts_observed": dict(sorted(app_status_counts_observed.items())),
        "app_status_counts_in_scope": dict(sorted(app_status_counts_in_scope.items())),
        "app_status_policy": "retained_verbatim_layer_membership_defines_pending_no_allowlist",
        "rejection_reasons": dict(sorted(rejection_reasons.items())),
        "pagination": {
            "method": "frozen_OBJECTID_set_range_pages_in_ASC_order",
            "page_size": page_size,
            "object_ids_start_count": len(start_ids),
            "object_ids_end_count": len(end_ids),
            "object_ids_stable": identity_stable,
            "object_ids_start_sha256": sha256_bytes(canonical_json_bytes(start_ids)),
            "object_ids_end_sha256": sha256_bytes(canonical_json_bytes(end_ids)),
        },
        "hashes": {
            "schema_contract_sha256": schema_contract_sha,
            "source_schema_sha256": source_schema_sha,
            "raw_manifest_sha256": raw_manifest_sha,
            "shadow_records_sha256": records_sha,
            "source_content_index_sha256": content_index_sha,
            "boundary_reference_sha256": boundary_reference_sha,
        },
        "quality": {
            "accounting_identity_passed": accounting_ok,
            "source_count_parity_passed": source_count_parity,
            "business_identity_unique": counts["duplicate_identities"] == 0,
            "source_object_id_set_stable": identity_stable,
            "all_pages_succeeded": counts["pages_succeeded"] == counts["pages_expected"],
            "schema_contract_passed": source_schema_sha is not None,
        },
        "safety": {
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
        },
    }
    _, receipt_sha = bundle.write_json("receipt.json", receipt)
    bundle.write_json(
        "bundle-manifest.json",
        {
            "schema_version": "FloridaSignalSfwmdShadowBundleManifestV1",
            "run_id": run_id,
            "receipt_sha256": receipt_sha,
            "raw_manifest_sha256": raw_manifest_sha,
            "shadow_records_sha256": records_sha,
            "source_content_index_sha256": content_index_sha,
            "boundary_sha256": boundary_sha,
            "boundary_source_schema_sha256": boundary_source_schema_sha,
            "boundary_reference_sha256": boundary_reference_sha,
            "schema_contract_sha256": schema_contract_sha,
            "promotion_eligible": False,
        },
    )
    return bundle.run_dir, receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Explicit absolute root for the new shadow evidence bundle.",
    )
    transport = parser.add_mutually_exclusive_group(required=True)
    transport.add_argument(
        "--fixture-dir",
        type=Path,
        help="Replay explicit offline JSON responses; performs no network access.",
    )
    transport.add_argument(
        "--allow-network",
        action="store_true",
        help="Explicitly allow GETs to the pinned official SFWMD URLs only.",
    )
    parser.add_argument("--page-size", type=int, default=MAX_RECORD_COUNT)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    parser.add_argument(
        "--max-response-bytes",
        type=int,
        default=DEFAULT_MAX_RESPONSE_BYTES,
        help="Fail closed when one official response exceeds this byte ceiling.",
    )
    parser.add_argument("--run-id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.output_dir.is_absolute():
        print("FATAL: --output-dir must be an explicit absolute path", file=sys.stderr)
        return 64
    try:
        if args.fixture_dir:
            source_transport: Transport = FixtureTransport(args.fixture_dir)
        else:
            source_transport = NetworkTransport(
                timeout_seconds=args.timeout_seconds,
                retries=args.retries,
                max_response_bytes=args.max_response_bytes,
            )
    except ValueError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 64
    try:
        run_dir, receipt = run_collection(
            output_root=args.output_dir,
            transport=source_transport,
            page_size=args.page_size,
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
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["status"] in {"ok", "empty"} else 65


if __name__ == "__main__":
    raise SystemExit(main())
