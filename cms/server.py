#!/usr/bin/env python3
"""The Data Wire: multi-market, source-gated editorial CMS starter."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse


ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DATA_WIRE_DB_PATH", str(ROOT / "data" / "data_wire.sqlite")))
PDMR_DB_PATH = Path(os.getenv(
    "FL_SIGNAL_PDMR_DB_PATH",
    str(ROOT.parent / "_source_copies" / "florida-signal" / "data" / "pdmr" / "florida_signal_v1.sqlite"),
))
PDMR_CANDIDATE_SCRIPT = Path(os.getenv(
    "FL_SIGNAL_PDMR_CANDIDATE_SCRIPT",
    str(ROOT.parent / "_source_copies" / "florida-signal" / "scripts" / "nominate_pdmr_candidates.py"),
))
PROJECT_STATE_PATH = Path(os.getenv(
    "FL_SIGNAL_PROJECT_STATE_PATH",
    str(ROOT.parent / "_source_copies" / "florida-signal" / "data" / "reference" / "florida_signal_project_state.json"),
))
ADMIN_TOKEN = os.getenv("DATA_WIRE_ADMIN_TOKEN", "").strip()
MAX_BODY = 1_000_000

# Signal review queue lives in Supabase, not the local SQLite store. The service-role key is read
# from the environment only and is NEVER sent to
# the browser: every queue read and write is proxied through this loopback server.
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://jrjewmzkyluxdywyusrw.supabase.co").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
REVIEW_STATUSES = {"NEW", "REVIEWING", "HOLD", "APPROVED", "REJECTED", "NEEDS_MORE_REPORTING"}
REVIEW_DESTINATIONS = {
    "live_signals_map", "signals_page", "daily_intel_brief", "neighborhood_page", "broward_record",
}
BRIEF_EDITION_DAYS = {"unscheduled", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
SCORE_REASON_VALUES = {"computed", "not_applicable", "no_detector_for_family", "detector_error", "insufficient_evidence"}
WRITING_STYLES = {"ap_florida_signal", "ap_straight_news"}
HEADLINE_MODES = {"compelling_precise", "straight_news", "analysis_explainer"}
JARGON_MODES = {"plain_english", "industry_with_definitions"}
REQUIRED_ETHICS_RULES = {
    "attribute_material_claims", "label_uncertainty", "avoid_sensationalism",
    "seek_response_when_criticized", "disclose_conflicts", "no_invented_context",
}
SOURCE_STAGE_ORDER = {
    # Discovery order is descriptive metadata, never proof and never a publication score.
    "decisions": 1,
    "formation": 2,
    "capital": 3,
    "regulatory": 4,
    "execution": 5,
    "record": 0,
}
MAX_REVIEW_PAGE = 20
PIPELINE_LABELS = {
    "florida-dataroom.timer": "Refresh Data Room",
    "florida-health.timer": "Check source health",
    "florida-gisowner.timer": "Parcel + owner join",
    "florida-enrich.timer": "Enrich permits",
    "florida-intake.timer": "Permit intake",
    "florida-sunbiz.timer": "Sunbiz corpus",
    "florida-sunbiz-deeds.timer": "Entity exact-match pass",
    "florida-backup.timer": "Production backup",
    "florida-offsite-backup.timer": "Offsite backup",
    "florida-signals-shadow.timer": "Candidate shadow run",
    "florida-parity-audit.timer": "Data parity audit",
    "florida-legistar.timer": "Meetings + agendas",
    "florida-freshness-alert.timer": "Freshness alert",
    "florida-healthreport.timer": "Health report",
    "florida-broward.timer": "Broward verified pull",
    "florida-clerk-catchup.timer": "Broward catch-up",
    "florida-gisrefresh.timer": "County GIS refresh",
    "florida-sunbiz-quarterly.timer": "Sunbiz full refresh",
}


def bounded_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, parsed))


def review_queue_path(params: dict[str, list[str]]) -> tuple[str, int, int, str]:
    """Build the bounded, indexed review-queue query used by the local desk."""
    status = (params.get("status", ["NEW"])[0] or "NEW").upper()
    if status not in REVIEW_STATUSES and status != "ALL":
        status = "NEW"
    readiness = (params.get("readiness", ["ready"])[0] or "ready").lower()
    if readiness not in {"ready", "blocked", "all"}:
        readiness = "ready"
    limit = bounded_int(params.get("limit", [1])[0], 1, 1, MAX_REVIEW_PAGE)
    offset = bounded_int(params.get("offset", [0])[0], 0, 0, 1_000_000)
    query = [
        "signal_review_queue?select=*",
        "order=source_record_date.desc,amount.desc.nullslast",
        f"limit={limit}",
        f"offset={offset}",
    ]
    if status != "ALL":
        query.append(f"review_status=eq.{quote(status)}")
    if readiness == "ready":
        query.append("evidence_ready=eq.true")
    elif readiness == "blocked":
        query.append("evidence_ready=eq.false")
    return "&".join(query), limit, offset, readiness


def attach_investigation_context(item: dict[str, Any]) -> dict[str, Any]:
    """Attach navigation context for any source family without changing evidence."""
    packet = item.get("evidence_packet")
    records = packet.get("records", []) if isinstance(packet, dict) else []
    permit = next((record for record in records if isinstance(record, dict)
                   and record.get("source_table") in {"permits", "accela_details"}
                   and record.get("source_record_id")), None)
    if not permit:
        source = next((record for record in records if isinstance(record, dict)), {})
        lat = source.get("lat") if isinstance(source, dict) else None
        lon = source.get("lon") if isinstance(source, dict) else None
        join = packet.get("join", {}) if isinstance(packet, dict) else {}
        item["investigation"] = {
            "status": "located" if lat is not None and lon is not None else "partial",
            "address": source.get("address") if isinstance(source, dict) else None,
            "folio": (source.get("folio") or source.get("parcel_id") if isinstance(source, dict) else None)
                     or join.get("canonical_folio") or item.get("verified_parcel_id"),
            "lat": lat, "lon": lon,
            "note": "Source context only; this does not add evidence to the packet",
        }
        return item
    permit_number = str(permit.get("source_record_id"))[:120]
    code, rows = supabase_request(
        "permits?select=permit_number,address,lat,lon,parcel_id_verified"
        f"&permit_number=eq.{quote(permit_number, safe='')}&limit=1"
    )
    source = (rows or [None])[0] if code < 400 and isinstance(rows, list) else None
    if not source:
        item["investigation"] = {
            "status": "partial", "permit_number": permit_number,
            "address": permit.get("address"), "note": "Coordinates unavailable",
        }
        return item
    item["investigation"] = {
        "status": "located" if source.get("lat") is not None and source.get("lon") is not None else "partial",
        "permit_number": permit_number,
        "address": source.get("address") or permit.get("address"),
        "folio": source.get("parcel_id_verified") or item.get("verified_parcel_id"),
        "lat": source.get("lat"), "lon": source.get("lon"),
        "note": "Navigation context only; these links do not add evidence to the packet",
    }
    return item


def public_json(url: str) -> dict[str, Any]:
    """Read a Florida Signal public API document with an explicit timeout."""
    import urllib.request

    request = urllib.request.Request(url, headers={"User-Agent": "FloridaSignalDataWire/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode())
            return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError):
        return {}


def load_project_state_manifest() -> tuple[int, dict[str, Any]]:
    """Read durable project state from Git without treating it as live health."""
    path = PROJECT_STATE_PATH.expanduser()
    unavailable = {
        "error": "Canonical project state is unavailable",
        "status": "UNKNOWN",
        "generated_at": now_iso(),
        "contract": "No project state was inferred because the tracked manifest could not be verified.",
    }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 503, unavailable
    required = {
        "schema_version", "state_contract", "current_mode", "now", "next",
        "active_research", "blocked_claims", "production_pipeline_registry",
        "sensor_status", "latest_material_decision", "verified_at",
    }
    if not isinstance(payload, dict) or not required.issubset(payload):
        return 503, unavailable
    if not isinstance(payload.get("production_pipeline_registry"), list):
        return 503, unavailable
    return 200, payload


def project_state_payload() -> tuple[int, dict[str, Any]]:
    """Combine canonical project state with independent, fail-closed live health."""
    code, state = load_project_state_manifest()
    if code != 200:
        return code, state

    health = public_json("https://api.thefloridasignal.com/api/data-health")
    health_rows = {
        str(row.get("id")): row for row in health.get("sources", [])
        if isinstance(row, dict) and row.get("id")
    } if isinstance(health, dict) else {}
    operational_health = []
    for component in state.get("production_pipeline_registry", []):
        if not isinstance(component, dict):
            continue
        health_source = component.get("health_source")
        health_source = health_source if isinstance(health_source, dict) else {}
        source_id = health_source.get("id") if health_source.get("type") == "public_data_health" else None
        receipt = health_rows.get(str(source_id), {}) if source_id else {}
        operational_health.append({
            "id": component.get("id"),
            "label": component.get("label"),
            "deployment_status": component.get("deployment_status"),
            "status": str(receipt.get("status") or "UNKNOWN").upper(),
            "event_through": receipt.get("event_through"),
            "system_time": receipt.get("system_time"),
            "detail": receipt.get("detail") or (
                "Live health source unavailable; no status inferred."
                if source_id else "No live health contract is configured; operational health is UNKNOWN."
            ),
            "health_source": (
                f"https://api.thefloridasignal.com/api/data-health#{source_id}"
                if source_id else None
            ),
            "authority": component.get("authority"),
            "touch_policy": component.get("touch_policy"),
        })

    return 200, {
        "project_state": state,
        "operational_health": operational_health,
        "live_health_generated_at": health.get("generated_at") if isinstance(health, dict) else None,
        "live_health_errors": health.get("errors", []) if isinstance(health, dict) else [],
        "generated_at": now_iso(),
        "contract": (
            "Project state comes from the tracked Git manifest. Operational health comes from "
            "independent live receipts; missing receipts remain UNKNOWN and never inherit a manifest status."
        ),
    }


def pdmr_intent_payload(
    limit: int = 6, offset: int = 0, search: str = "",
) -> tuple[int, dict[str, Any]]:
    """Read the local LauderBuild evidence mirror without mutating or promoting records."""
    bounded_limit = bounded_int(limit, 6, 1, 100)
    bounded_offset = bounded_int(offset, 0, 0, 1_000_000)
    search = re.sub(r"[\x00-\x1f\x7f]", "", str(search or "")).strip()[:180]
    path = PDMR_DB_PATH.expanduser()
    unavailable = {
        "status": "unavailable",
        "items": [],
        "generated_at": now_iso(),
        "contract": "No PDMR state was inferred because the read-only evidence database is unavailable.",
    }
    if not path.is_file():
        return 503, unavailable

    source = "fort_lauderdale_lauderbuild_planning"
    event_type = "planning_preapplication"
    recent_since = (datetime.now(timezone.utc).date() - timedelta(days=7)).isoformat()
    def normalized(value: Any) -> str:
        return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())

    match = re.match(r"^(id|folio|addr|owner|project)\s*:\s*(.+)$", search, re.I) if search else None
    prefix = match.group(1).lower() if match else ""
    needle = (match.group(2) if match else search).strip()
    where_sql = "source=? and event_type=?"
    where_params: list[Any] = [source, event_type]
    if search:
        if prefix == "id":
            where_sql += " and upper(coalesce(source_record_id,''))=upper(?)"
            where_params.append(needle)
        elif prefix == "folio":
            where_sql += " and fs_norm(json_extract(payload_json,'$.fields.folio'))=?"
            where_params.append(normalized(needle))
        elif prefix in {"addr", "owner", "project"}:
            column = {"addr": "address", "owner": "owner_name", "project": "project_name"}[prefix]
            where_sql += f" and instr(upper(coalesce({column},'')),upper(?))>0"
            where_params.append(needle)
        else:
            where_sql += """ and instr(upper(
                coalesce(source_record_id,'') || ' ' || coalesce(address,'') || ' ' ||
                coalesce(owner_name,'') || ' ' || coalesce(project_name,'') || ' ' ||
                coalesce(summary,'') || ' ' ||
                coalesce(json_extract(payload_json,'$.fields.folio'),'') || ' ' ||
                coalesce(json_extract(payload_json,'$.fields.development_type'),'')
            ),upper(?))>0"""
            where_params.append(needle)
    try:
        connection_uri = path.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(connection_uri, uri=True, timeout=5) as db:
            db.row_factory = sqlite3.Row
            db.create_function("fs_norm", 1, normalized)
            db.execute("pragma query_only=on")
            if db.execute("pragma query_only").fetchone()[0] != 1:
                raise sqlite3.OperationalError("read-only guard unavailable")
            table_exists = db.execute(
                "select 1 from sqlite_master where type='table' and name='parcel_events'"
            ).fetchone()
            if not table_exists:
                raise sqlite3.OperationalError("parcel_events table unavailable")
            summary = db.execute(
                """
                select count(*) as record_count,
                       sum(case when event_date >= ? then 1 else 0 end) as recent_count,
                       max(event_date) as newest_event,
                       max(last_seen_at) as last_collected
                from parcel_events
                where source=? and event_type=?
                """,
                (recent_since, source, event_type),
            ).fetchone()
            matched_count = int(summary["record_count"] or 0)
            if search:
                matched_count = int(db.execute(
                    f"select count(*) from parcel_events where {where_sql}",
                    where_params,
                ).fetchone()[0])
            rows = db.execute(
                f"""
                select source_record_id, event_date, address, owner_name, project_name, summary,
                       source_url, source_record_hash, detector_version, first_seen_at, last_seen_at,
                       payload_json
                from parcel_events
                where {where_sql}
                order by event_date desc, source_record_id desc
                limit ? offset ?
                """,
                (*where_params, bounded_limit, bounded_offset),
            ).fetchall()
    except (OSError, sqlite3.Error):
        return 503, unavailable

    items = []
    for row in rows:
        try:
            evidence = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            evidence = {}
        fields = evidence.get("fields") if isinstance(evidence, dict) else {}
        fields = fields if isinstance(fields, dict) else {}
        source_url = str(row["source_url"] or "")
        if not source_url.startswith("https://aca-prod.accela.com/FTL/"):
            source_url = ""
        items.append({
            "source_record_id": row["source_record_id"],
            "event_date": row["event_date"],
            "record_status": fields.get("status"),
            "address": row["address"],
            "owner_name": row["owner_name"],
            "folio": fields.get("folio") or None,
            "project_name": row["project_name"],
            "project_description": row["summary"],
            "development_stage": fields.get("development_stage") or None,
            "development_type": fields.get("development_type") or None,
            "units_text": fields.get("units_text") or None,
            "parking_spaces": fields.get("parking_spaces") or None,
            "staff_questions": fields.get("staff_questions") or None,
            "source_url": source_url,
            "source_record_hash": row["source_record_hash"],
            "detector_version": row["detector_version"],
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
            "editorial_state": "source_record_only",
        })
    return 200, {
        "status": "available",
        "source": "Fort Lauderdale LauderBuild",
        "lane": "planning_intent",
        "record_count": int(summary["record_count"] or 0),
        "recent_count": int(summary["recent_count"] or 0),
        "recent_since": recent_since,
        "newest_event": summary["newest_event"],
        "last_collected": summary["last_collected"],
        "items": items,
        "matched_count": matched_count,
        "limit": bounded_limit,
        "offset": bounded_offset,
        "has_more": bounded_offset + len(items) < matched_count,
        "search": search or None,
        "generated_at": now_iso(),
        "contract": "Public pre-application source records only. Collection does not nominate a Candidate, verify a Signal or publish a claim.",
    }


def pdmr_shadow_candidate_payload(limit: int = 8) -> tuple[int, dict[str, Any]]:
    """Run the bounded read-only PDMR shadow detector; never pass an output path."""
    bounded_limit = bounded_int(limit, 8, 1, 20)
    unavailable = {
        "mode": "unavailable", "items": [], "generated_at": now_iso(),
        "contract": "No Candidate state was inferred because the local shadow detector is unavailable.",
        "publication_effect": "none",
    }
    if not PDMR_CANDIDATE_SCRIPT.is_file() or not PDMR_DB_PATH.is_file():
        return 503, unavailable
    command = [
        sys.executable, str(PDMR_CANDIDATE_SCRIPT),
        "--db", str(PDMR_DB_PATH),
        "--as-of", datetime.now(timezone.utc).date().isoformat(),
        "--limit", str(bounded_limit),
    ]
    try:
        result = subprocess.run(
            command, check=True, capture_output=True, text=True, timeout=10,
        )
        payload = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return 503, unavailable
    if not isinstance(payload, dict) or payload.get("mode") != "shadow" or not isinstance(payload.get("items"), list):
        return 503, unavailable
    payload["contract"] = (
        "Read-only shadow Candidates. Shortlisting starts Brief evidence review; "
        "it does not approve, publish, schedule or send anything."
    )
    return 200, payload


def early_intel_payload() -> dict[str, Any]:
    """Show the whole intelligence funnel; do not imply that every lane has a detector yet."""
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        meeting_future = pool.submit(public_json, "https://api.thefloridasignal.com/api/meetings")
        health_future = pool.submit(public_json, "https://api.thefloridasignal.com/api/data-health")
        meetings = meeting_future.result()
        health = health_future.result()

    meeting_rows = meetings.get("meetings", []) if isinstance(meetings, dict) else []
    government = [row for row in meeting_rows if isinstance(row, dict) and row.get("category") == "government"]
    agendas = [row for row in government if row.get("agenda_available") is True]
    next_meeting = government[0] if government else {}
    sources = {
        str(source.get("id")): source for source in health.get("sources", [])
        if isinstance(source, dict) and source.get("id")
    }
    preliminary = sources.get("clerk-preliminary", {})
    official_clerk = sources.get("broward", {})
    sunbiz = sources.get("sunbiz", {})
    private_sunbiz_code, private_sunbiz_rows = supabase_request(
        "sunbiz_entities?select=fetched_at,date_filed,source,match_type"
        "&source=eq.sunbiz-sftp-corpus&order=fetched_at.desc.nullslast&limit=1"
    )
    def status_from_clock(value: Any, current_hours: int, delayed_hours: int) -> str:
        if not value:
            return "unavailable"
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            current = datetime.fromisoformat(now_iso().replace("Z", "+00:00"))
            if current.tzinfo is None:
                current = current.replace(tzinfo=timezone.utc)
            age_hours = (current.astimezone(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 3600
        except (TypeError, ValueError):
            return "unavailable"
        if age_hours <= current_hours:
            return "current"
        if age_hours <= delayed_hours:
            return "delayed"
        return "stale"

    if private_sunbiz_code < 400 and isinstance(private_sunbiz_rows, list) and private_sunbiz_rows:
        latest_sunbiz = private_sunbiz_rows[0]
        sunbiz = {
            "status": status_from_clock(latest_sunbiz.get("fetched_at"), 72, 336),
            "system_time": latest_sunbiz.get("fetched_at"),
            "event_through": latest_sunbiz.get("date_filed"), "private": True,
        }
    fdep = sources.get("fdep", {})
    faa = sources.get("faa", {})
    permits = sources.get("permits", {})
    pdmr_code, pdmr = pdmr_intent_payload(limit=1)
    pdmr = pdmr if pdmr_code == 200 else {}
    pdmr_receipt = ({
        "status": status_from_clock(pdmr.get("last_collected"), 72, 168),
        "event_through": pdmr.get("newest_event"),
        "system_time": pdmr.get("last_collected"),
    } if pdmr and int(pdmr.get("record_count") or 0) > 0 else ({"status": "unverified"} if pdmr else {}))
    meeting_receipt = ({
        "status": status_from_clock(meetings.get("updated_at"), 24, 72),
        "event_through": next_meeting.get("date"),
        "system_time": meetings.get("updated_at"),
    } if isinstance(meetings, dict) and meetings.get("updated_at") else {})

    def receipt_status(receipt: dict[str, Any], default: str = "unavailable") -> str:
        value = str(receipt.get("status") or default).lower()
        return value if value in {"current", "delayed", "stale", "suppressed", "error", "unavailable", "unverified"} else default

    def combined_status(*receipts: dict[str, Any]) -> str:
        statuses = [receipt_status(receipt) for receipt in receipts if receipt]
        if not statuses:
            return "unavailable"
        for value in ("error", "unavailable", "stale", "suppressed", "delayed", "unverified"):
            if value in statuses:
                return value
        return "current"

    def connection_state(*receipts: dict[str, Any]) -> str:
        statuses = [receipt_status(receipt) for receipt in receipts if receipt]
        return "connected" if any(value not in {"error", "unavailable", "suppressed"} for value in statuses) else "unavailable"

    lanes = [
        {
            "phase": "01 · Planning intent", "label": "PDMR planning intent + agenda packets",
            "status": combined_status(pdmr_receipt, meeting_receipt),
            "connection": connection_state(pdmr_receipt, meeting_receipt),
            "automation": "mixed" if pdmr_receipt and meeting_receipt else "manual" if pdmr_receipt else "automated" if meeting_receipt else "none",
            "event_through": pdmr.get("newest_event") or next_meeting.get("date"),
            "system_time": pdmr.get("last_collected") or meetings.get("updated_at"),
            "headline": ((f"PDMR reaches {pdmr.get('newest_event')} · {len(agendas)} posted agenda(s)"
                          if pdmr else f"{len(agendas)} posted agenda(s) among {len(government)} upcoming government meetings")
                         if government or pdmr else "Planning-intent sources unavailable"),
            "note": "Earliest built lane in the current desk. PDMR portal dates precede the matched formal applications, but first-public timing remains unresolved; agenda timing varies by project.",
            "href": "/#planning-intent",
        },
        {
            "phase": "02 · Formation", "label": "Companies + principals",
            "status": receipt_status(sunbiz),
            "connection": connection_state(sunbiz), "automation": "automated",
            "event_through": sunbiz.get("event_through"), "system_time": sunbiz.get("system_time"),
            "headline": (("Sunbiz exact-match resolver has private rows · " + receipt_status(sunbiz)) if sunbiz.get("private")
                         else "Sunbiz exact-match lane is current" if sunbiz.get("status") == "current"
                         else "Sunbiz has no usable public event clock"),
            "note": "Only exact entity matches may connect a company, officer or registered agent. Resolver rows remain private and source-linked.",
            "href": "/data.html",
        },
        {
            "phase": "03 · Capital", "label": "Ownership, deeds, debt + liens",
            "status": combined_status(official_clerk, preliminary),
            "connection": connection_state(official_clerk, preliminary), "automation": "automated",
            "event_through": preliminary.get("event_through") or official_clerk.get("event_through"),
            "system_time": preliminary.get("system_time"),
            "headline": ("Preliminary Clerk reaches " + str(preliminary.get("event_through"))
                         if preliminary else "Verified Clerk reaches " + str(official_clerk.get("event_through") or "unknown")),
            "note": "Same-day preliminary records are clues only. Verified Clerk, party, legal and parcel records are the evidence lane.",
            "href": "/data.html?search=instrument:",
        },
        {
            "phase": "04 · Regulatory", "label": "Environmental + airspace",
            "status": combined_status(fdep, faa),
            "connection": connection_state(fdep, faa), "automation": "automated",
            "event_through": max(str(fdep.get("event_through") or ""), str(faa.get("event_through") or "")) or None,
            "system_time": max(str(fdep.get("system_time") or ""), str(faa.get("system_time") or "")) or None,
            "headline": f"FDEP through {fdep.get('event_through') or 'unknown'} · FAA through {faa.get('event_through') or 'unknown'}",
            "note": "Wetland, stormwater, environmental and obstruction/crane filings can surface work before a municipal building permit.",
            "href": "/data.html",
        },
        {
            "phase": "05 · Execution", "label": "Applications, permits + inspections",
            "status": receipt_status(permits),
            "connection": connection_state(permits), "automation": "automated",
            "event_through": permits.get("event_through"), "system_time": permits.get("system_time"),
            "headline": "Permit applications through " + str(permits.get("event_through") or "unknown"),
            "note": "Later-stage confirmation and workflow detail—not the definition of a Signal and not the only candidate source.",
            "href": "/data.html?search=permit:",
        },
    ]
    summary = {}
    for lane in lanes:
        status = str(lane.get("status") or "unavailable")
        summary[status] = summary.get(status, 0) + 1
    return {
        "lanes": lanes, "summary": summary, "generated_at": now_iso(),
        "contract": "These are monitored source lanes, not five complete candidate detectors. Evidence and event clocks remain source-specific.",
    }


def agenda_relevance(item: dict[str, Any]) -> str:
    """Describe the reporting value of an agenda item without asserting an impact."""
    terms = {str(term).lower() for term in (item.get("watch_terms") or [])}
    title = str(item.get("title") or "").lower()
    if "development" in terms or any(word in title for word in ("rezoning", "site plan", "land use", "flex unit")):
        return "May change entitlement, density, design, allowed use or the approval path for a site."
    if "infrastructure" in terms or any(word in title for word in ("water", "sewer", "airport", "transit", "road")):
        return "May unlock, constrain or redirect development through public infrastructure and capital spending."
    if "cra" in terms:
        return "May direct redevelopment policy, planning work or public investment within a CRA."
    if "property" in terms or any(word in title for word in ("lease", "sale", "acquisition", "easement")):
        return "May change control, use or financing of land or public property."
    return "Matched the desk's development watch terms and needs a source-level significance check."


def agenda_watch_payload() -> tuple[int, dict[str, Any]]:
    """Return actionable Legistar items and attachment links for private reporting review."""
    meetings = public_json("https://api.thefloridasignal.com/api/meetings")
    meeting_rows = meetings.get("meetings", []) if isinstance(meetings, dict) else []
    upcoming = []
    for meeting in meeting_rows:
        if not isinstance(meeting, dict) or meeting.get("category") != "government":
            continue
        details_url = meeting.get("details_url") if public_url(meeting.get("details_url")) else None
        agenda_url = meeting.get("agenda_url") if public_url(meeting.get("agenda_url")) else None
        upcoming.append({
            "government_name": "City of Fort Lauderdale",
            "body_name": str(meeting.get("title") or "Government meeting")[:240],
            "event_date": meeting.get("date"), "event_time": meeting.get("time"),
            "starts_at": meeting.get("starts_at"), "location": meeting.get("location"),
            "agenda_available": meeting.get("agenda_available") is True,
            "agenda_url": agenda_url, "details_url": details_url,
            "watch_url": meeting.get("watch_url") if public_url(meeting.get("watch_url")) else None,
            "ical_url": meeting.get("ical_url") if public_url(meeting.get("ical_url")) else None,
            "source": str(meeting.get("source") or "Official government calendar")[:160],
        })
        if len(upcoming) >= 8:
            break
    select = (
        "item_id,event_id,agenda_number,title,matter_file,matter_type,matter_status,"
        "action_name,action_text,passed_flag_name,attachments,watch_terms,source_url,"
        "first_seen_at,last_seen_at,"
        "legistar_events(event_date,event_time,location,body_name,agenda_url)"
    )
    code, rows = supabase_request(
        "legistar_event_items?select=" + quote(select, safe=",()")
        + "&watch_match=eq.true&order=first_seen_at.desc&limit=500"
    )
    if code >= 400 or not isinstance(rows, list):
        return 502, rows if isinstance(rows, dict) else {"error": "Agenda watch unavailable"}
    useful = []
    attachment_total = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = re.sub(r"\s+", " ", str(row.get("title") or "")).strip()
        attachments = row.get("attachments") if isinstance(row.get("attachments"), list) else []
        if (not row.get("matter_file") and not attachments) or title.upper().startswith("NOTICES:"):
            continue
        public_attachments = []
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            url = attachment.get("MatterAttachmentHyperlink")
            if not public_url(url) or attachment.get("MatterAttachmentShowOnInternetPage") is False:
                continue
            public_attachments.append({
                "name": str(attachment.get("MatterAttachmentName") or attachment.get("MatterAttachmentFileName") or "Attachment")[:240],
                "url": str(url),
                "filename": str(attachment.get("MatterAttachmentFileName") or "")[:240],
                "modified_at": attachment.get("MatterAttachmentLastModifiedUtc"),
            })
        event = row.get("legistar_events") if isinstance(row.get("legistar_events"), dict) else {}
        attachment_total += len(public_attachments)
        useful.append({
            "item_id": row.get("item_id"), "event_id": row.get("event_id"),
            "government_name": "City of Fort Lauderdale",
            "agenda_number": row.get("agenda_number"), "title": title,
            "matter_file": row.get("matter_file"), "matter_type": row.get("matter_type"),
            "matter_status": row.get("matter_status"), "action_name": row.get("action_name"),
            "action_text": row.get("action_text"), "passed_flag_name": row.get("passed_flag_name"),
            "watch_terms": row.get("watch_terms") or [], "source_url": row.get("source_url"),
            "first_seen_at": row.get("first_seen_at"), "last_seen_at": row.get("last_seen_at"),
            "event_date": event.get("event_date"), "event_time": event.get("event_time"),
            "location": event.get("location"), "body_name": event.get("body_name"),
            "agenda_url": event.get("agenda_url"), "attachments": public_attachments,
            "why_developers_care": agenda_relevance(row),
            "what_next": (str(row.get("action_text") or row.get("action_name") or "")[:500]
                          or "Open the staff memo and attachments; identify the site, parties, recommendation, conditions and next hearing."),
            "stakeholder_test": "Identify who benefits, who bears costs or risk, staff's stated basis, supporters, opponents, public comments, alternatives and enforceable conditions.",
            "verification": "private reporting lead — cite the exact item and attachment before making a claim",
        })
    useful.sort(key=lambda item: (str(item.get("event_date") or ""), str(item.get("first_seen_at") or "")), reverse=True)
    event_dates = sorted(str(item.get("event_date")) for item in useful if item.get("event_date"))
    observed_times = sorted(str(item.get("last_seen_at")) for item in useful if item.get("last_seen_at"))
    public_bodies = sorted({str(item.get("body_name")) for item in useful if item.get("body_name")})
    return 200, {
        "items": useful, "matched_rows": len(rows), "actionable_rows": len(useful),
        "public_attachments": attachment_total, "generated_at": now_iso(),
        "government_entities": ["City of Fort Lauderdale"], "public_bodies": public_bodies,
        "upcoming_meetings": upcoming, "calendar_url": meetings.get("calendar_url"),
        "calendar_observed_through": meetings.get("updated_at"),
        "event_start": event_dates[0] if event_dates else None,
        "event_through": event_dates[-1] if event_dates else None,
        "item_index_observed_through": observed_times[-1] if observed_times else None,
        "contract": "Watch terms nominate leads. They do not establish impact, ideology, support, opposition or outcome.",
    }


def sunbiz_entities_payload(params: dict[str, list[str]]) -> tuple[int, dict[str, Any]]:
    """Read private resolved Sunbiz rows without exposing the service key or bypassing the desk."""
    limit = bounded_int(params.get("limit", [25])[0], 25, 1, 100)
    offset = bounded_int(params.get("offset", [0])[0], 0, 0, 1_000_000)
    search = re.sub(r"[^A-Za-z0-9]", "", str(params.get("search", [""])[0])).upper()[:160]
    select = (
        "search_name,matched_name,doc_number,status,filing_type,date_filed,principal_address,"
        "registered_agent,officers,match_type,notes,fetched_at,source"
    )
    query = (
        "sunbiz_entities?select=" + quote(select, safe=",")
        + "&source=eq.sunbiz-sftp-corpus"
        + "&order=fetched_at.desc.nullslast"
        + f"&limit={limit + 1}&offset={offset}"
    )
    if search:
        query += "&search_name_norm=eq." + quote(search, safe="")
    code, rows = supabase_request(query)
    if code >= 400 or not isinstance(rows, list):
        payload = rows if isinstance(rows, dict) else {"error": "Sunbiz resolver rows unavailable"}
        return 502, payload
    has_more = len(rows) > limit
    return 200, {
        "items": rows[:limit], "limit": limit, "offset": offset, "has_more": has_more,
        "search": search or None, "generated_at": now_iso(),
        "contract": "Private exact-match resolver output from the local Sunbiz SFTP corpus; no fuzzy identity claim is added.",
    }


def pipeline_schedule() -> tuple[int, dict[str, Any]]:
    """Read the production host's timer schedule without running or changing a job."""
    command = [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "florida",
        "systemctl list-timers --all --no-pager --output=json",
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=8)
        raw = json.loads(result.stdout)
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError) as error:
        return 502, {
            "error": "Production schedule is temporarily unreachable",
            "detail": type(error).__name__,
            "contract": "No timer status was inferred from a failed connection",
        }
    jobs = []
    for row in raw if isinstance(raw, list) else []:
        unit = str(row.get("unit") or "")
        next_us = int(row.get("next") or 0)
        last_us = int(row.get("last") or 0)
        if not unit.startswith("florida-") or next_us <= 0:
            continue
        jobs.append({
            "unit": unit,
            "label": PIPELINE_LABELS.get(unit, unit.removeprefix("florida-").removesuffix(".timer").replace("-", " ").title()),
            "next_at": datetime.fromtimestamp(next_us / 1_000_000, timezone.utc).isoformat(),
            "last_at": datetime.fromtimestamp(last_us / 1_000_000, timezone.utc).isoformat() if last_us > 0 else None,
        })
    jobs.sort(key=lambda job: job["next_at"])
    return 200, {
        "jobs": jobs,
        "generated_at": now_iso(),
        "timezone": "Times render in this device's local time",
        "contract": "A timer proves scheduling only. Source health and event coverage prove usable data.",
    }


def signal_machine_payload() -> dict[str, Any]:
    """Describe the real cross-source control plane without pretending missing detectors exist."""
    lanes = [
        {"id": "decisions", "label": "PDMR + agenda packets · early discovery", "discovery_order": 1,
         "default_multiplier": 1.50, "health": "source_reporting", "coverage": "shadow_ranked",
         "freshness": "see_source_receipt", "note": "LauderBuild PDMRs have a deterministic local shadow Candidate detector; production queue writes remain disconnected."},
        {"id": "formation", "label": "Entity formation · Sunbiz", "discovery_order": 2,
         "default_multiplier": 1.35, "health": "source_reporting", "coverage": "detector_gap",
         "freshness": "see_source_receipt", "note": "Exact-match resolver is private; fuzzy identity claims remain prohibited."},
        {"id": "capital", "label": "Capital events · deeds, debt + liens", "discovery_order": 3,
         "default_multiplier": 1.20, "health": "source_reporting", "coverage": "partial_join_only",
         "freshness": "see_source_receipt", "note": "Clerk and parcel evidence exist; verified joins remain sparse and source-specific."},
        {"id": "regulatory", "label": "Regulatory filings · FDEP + FAA", "discovery_order": 4,
         "default_multiplier": 1.10, "health": "source_reporting", "coverage": "detector_gap",
         "freshness": "see_source_receipt", "note": "Feeds are searchable; Candidate detectors are not integrated."},
        {"id": "execution", "label": "Execution · permits + inspections", "discovery_order": 5,
         "default_multiplier": 1.00, "health": "source_reporting", "coverage": "shadow_ranked",
         "freshness": "see_source_receipt", "note": "v2.6 deterministic scorer runs in shadow; this is the only reproducible ranked family."},
    ]
    stages = [
        {"id": "collect", "label": "Collect", "owner": "Timers + source-specific collectors", "status": "source_dependent", "may": "Write immutable source rows and receipts; check each source's health and freshness separately"},
        {"id": "normalize", "label": "Normalize + join", "owner": "Deterministic normalization/provenance rules", "status": "partial", "may": "Normalize fields and create source-qualified joins; weak identity links remain quarantined"},
        {"id": "detect", "label": "Nominate Candidates", "owner": "Deterministic source-family detectors", "status": "partial", "may": "Permits and local PDMR shadow rules only; other families remain unscored and must show a reason"},
        {"id": "rank", "label": "Rank", "owner": "Signal Machine v2.6 shadow scorer", "status": "shadow", "may": "Rank eligible Candidates; no model calls and no publication"},
        {"id": "cross_check", "label": "AI consistency check", "owner": "Advisory model review over the same evidence packet", "status": "not_connected", "may": "May raise flags, find contradictions or lower confidence; cannot add sources, corroborate, score, promote or publish"},
        {"id": "decide", "label": "Decide", "owner": "Human desk editor", "status": "required", "may": "Approve Candidate as Signal and approve final Brief module"},
        {"id": "send", "label": "Send", "owner": "Mailchimp sender after explicit approval", "status": "not_connected", "may": "Send only an approved immutable edition artifact"},
    ]
    return {
        "machine": "Florida Signal Machine",
        "baseline": "v2.6 deterministic shadow scorer",
        "lanes": lanes,
        "stages": stages,
        "score_contract": {
            "axes": ["evidence_confidence", "editorial_importance", "recency", "early_stage_priority"],
            "axis_status": {
                "evidence_confidence": {"implemented": True, "families": ["decisions"], "scope": "local PDMR shadow only"},
                "editorial_importance": {"implemented": True, "families": ["decisions", "execution"]},
                "recency": {"implemented": True, "families": ["decisions", "execution"]},
                "early_stage_priority": {"implemented": True, "families": ["decisions"], "scope": "local PDMR shadow only"},
            },
            "rule": "Axes remain separate. Early-stage priority may order equally supported Candidates but cannot rescue weak evidence.",
            "multiplier_scope": "Preview multipliers are bounded from 1.00x to 2.00x and affect triage-order simulations only.",
            "missing_reason_values": ["computed", "not_applicable", "no_detector_for_family", "detector_error", "insufficient_evidence"],
            "public_gate": "Record → Candidate → human-verified Signal → reported Story/Brief",
        },
        "activation": {
            "status": "blocked",
            "blocked_by": ["no replay corpus", "no backtest harness", "no measured false-merge rate", "cross-source detectors incomplete"],
            "endpoint_exists": False,
        },
        "generated_at": now_iso(),
    }


def supabase_request(path: str, method: str = "GET", body: Any = None, prefer: str = "") -> tuple[int, Any]:
    """Call PostgREST with the service-role key. Returns (status, parsed-or-text)."""
    import urllib.error
    import urllib.request

    if not SUPABASE_SERVICE_KEY:
        return 503, {"error": "SUPABASE_SERVICE_ROLE_KEY is not set in this shell; queue is read-only"}
    request = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
    )
    request.add_header("apikey", SUPABASE_SERVICE_KEY)
    request.add_header("Authorization", f"Bearer {SUPABASE_SERVICE_KEY}")
    request.add_header("Content-Type", "application/json")
    if prefer:
        request.add_header("Prefer", prefer)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode()
            return response.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as error:
        return error.code, {"error": error.read().decode()[:400]}
    except OSError as error:
        return 502, {"error": str(error)[:200]}
MARKET_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")
CITY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,59}$")
COUNTY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,79}$")
STATUS_PUBLIC = {"approved", "published"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def public_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:90] or "wire-item"


def list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        values = value
    elif isinstance(value, str):
        values = value.split(",")
    else:
        values = []
    cleaned: list[str] = []
    for item in values:
        text = re.sub(r"\s+", " ", str(item)).strip()
        if text and text.lower() not in {entry.lower() for entry in cleaned}:
            cleaned.append(text[:100])
    return cleaned[:30]


def json_array(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value[:100]
    if isinstance(value, str) and value.strip():
        try:
            loaded = json.loads(value)
            return loaded[:100] if isinstance(loaded, list) else []
        except json.JSONDecodeError:
            return []
    return []


def market_value(value: Any) -> str:
    market = str(value or "broward").strip().lower()
    if not MARKET_RE.fullmatch(market):
        raise ValueError("Invalid market key")
    return market


def city_value(value: Any) -> str:
    city = str(value or "").strip().lower()
    if not city or not CITY_RE.fullmatch(city):
        raise ValueError("A valid city key is required")
    return city


def county_value(value: Any) -> str:
    county = str(value or "").strip().lower()
    if not county or not COUNTY_RE.fullmatch(county):
        raise ValueError("A valid county key is required")
    return county


def ensure_city_scoped_story_slugs(db: sqlite3.Connection) -> None:
    """Upgrade the early market-wide slug constraint without losing draft rows."""
    row = db.execute("select sql from sqlite_master where type='table' and name='stories'").fetchone()
    table_sql = str(row[0] if row else "")
    normalized = re.sub(r"\s+", "", table_sql.lower())
    if "unique(market,slug)" not in normalized:
        return
    migration_sql = re.sub(r"create\s+table\s+stories", "create table stories_city_migration", table_sql, count=1, flags=re.IGNORECASE)
    migration_sql = re.sub(r"unique\s*\(\s*market\s*,\s*slug\s*\)", "unique(market, city, slug)", migration_sql, count=1, flags=re.IGNORECASE)
    columns = [row[1] for row in db.execute("pragma table_info(stories)")]
    quoted = ",".join('"' + column.replace('"', '""') + '"' for column in columns)
    db.execute(migration_sql)
    db.execute(f"insert into stories_city_migration ({quoted}) select {quoted} from stories")
    db.execute("drop table stories")
    db.execute("alter table stories_city_migration rename to stories")


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as db:
        db.executescript(
            """
            create table if not exists stories (
              id text primary key,
              market text not null,
              county text not null,
              city text not null,
              slug text not null,
              headline text not null,
              dek text not null default '',
              body text not null default '',
              byline text not null default 'Florida Signal Desk',
              writing_style text not null default 'ap_florida_signal',
              headline_mode text not null default 'compelling_precise',
              jargon_mode text not null default 'plain_english',
              ethics_rules_json text not null default '[]',
              event_date text,
              source_url text not null default '',
              source_title text not null default '',
              source_published_at text,
              source_hash text,
              topic_tags text not null default '[]',
              geography_tags text not null default '[]',
              entity_tags text not null default '[]',
              audience_tags text not null default '[]',
              urgency_tags text not null default '[]',
              neighborhood text,
              zip text,
              lat real,
              lon real,
              hero_image text,
              verification_status text not null default 'needs_verification',
              current_trigger text,
              project_identity_basis text,
              claim_slots text not null default '[]',
              unresolved_issues text,
              validator_status text not null default 'pending',
              approval_history text not null default '[]',
              publication_history text not null default '[]',
              status text not null default 'draft',
              claims_status text not null default 'pending',
              tags_status text not null default 'pending',
              editor_name text,
              editor_note text,
              approved_at text,
              created_at text not null,
              updated_at text not null,
              unique(market, city, slug)
            );
            create index if not exists stories_market_status on stories(market, status, approved_at);
            create table if not exists agenda_recon (
              id text primary key,
              market text not null,
              county text not null,
              city text not null,
              meeting_title text not null,
              meeting_date text not null,
              item_number text not null,
              property_address text not null,
              folio text,
              applicant text,
              proposed_action text not null,
              source_url text not null,
              source_page integer,
              source_hash text,
              lat real,
              lon real,
              neighborhood text,
              zip text,
              editor_status text not null default 'draft',
              editor_name text,
              editor_note text,
              created_at text not null,
              updated_at text not null
            );
            create index if not exists agenda_market_status on agenda_recon(market, editor_status, meeting_date);
            create table if not exists brief_bank (
              id text primary key,
              market text not null,
              county text not null,
              city text not null,
              source_kind text not null,
              source_id text not null,
              source_url text not null,
              source_title text not null,
              event_date text,
              entity_name text,
              body_name text,
              why_it_matters text,
              evidence_json text not null default '{}',
              evidence_hash text not null default '',
              evidence_confidence real,
              evidence_confidence_reason text not null default 'not_applicable',
              gates_passed_json text not null default '[]',
              score_reasons_json text not null default '{}',
              scoring_profile_id text,
              stage text not null default 'needs_cross_check',
              cross_check_status text not null default 'not_started',
              assembly_status text not null default 'not_selected',
              edition_day text not null default 'unscheduled',
              target_date text,
              target_date_source text not null default 'unscheduled',
              candidate_id text,
              machine_version text,
              importance_score real,
              recency_score real,
              source_stage text not null default 'record',
              rules_fired_json text not null default '[]',
              added_by text,
              created_at text not null,
              updated_at text not null,
              unique(source_kind, source_id)
            );
            create index if not exists brief_bank_market_stage on brief_bank(market, stage, created_at desc);
            create table if not exists scoring_profiles (
              id text primary key,
              market text not null,
              name text not null,
              weights_json text not null,
              status text not null default 'draft',
              backtest_status text not null default 'not_run',
              rationale text not null default '',
              parent_profile_id text,
              created_by text,
              created_at text not null,
              updated_at text not null
            );
            create index if not exists scoring_profiles_market on scoring_profiles(market, created_at desc);
            create table if not exists audit_log (
              id integer primary key autoincrement,
              market text not null,
              object_type text not null,
              object_id text not null,
              action text not null,
              actor text,
              detail text not null default '{}',
              created_at text not null
            );
            """
        )
        story_columns = {row[1] for row in db.execute("pragma table_info(stories)")}
        if "city" not in story_columns:
            db.execute("alter table stories add column city text not null default 'fort-lauderdale'")
        if "county" not in story_columns:
            db.execute("alter table stories add column county text not null default 'broward-county'")
        if "writing_style" not in story_columns:
            db.execute("alter table stories add column writing_style text not null default 'ap_florida_signal'")
        if "headline_mode" not in story_columns:
            db.execute("alter table stories add column headline_mode text not null default 'compelling_precise'")
        if "jargon_mode" not in story_columns:
            db.execute("alter table stories add column jargon_mode text not null default 'plain_english'")
        if "ethics_rules_json" not in story_columns:
            db.execute("alter table stories add column ethics_rules_json text not null default '[]'")
        ensure_city_scoped_story_slugs(db)
        db.execute("create index if not exists stories_market_status on stories(market, status, approved_at)")
        db.execute("create index if not exists stories_market_city_status on stories(market, city, status, approved_at)")
        agenda_columns = {row[1] for row in db.execute("pragma table_info(agenda_recon)")}
        if "city" not in agenda_columns:
            db.execute("alter table agenda_recon add column city text not null default 'fort-lauderdale'")
        if "county" not in agenda_columns:
            db.execute("alter table agenda_recon add column county text not null default 'broward-county'")
        db.execute("create index if not exists agenda_market_city_status on agenda_recon(market, city, editor_status, meeting_date)")
        db.execute("create index if not exists brief_bank_market_stage on brief_bank(market, stage, created_at desc)")
        brief_columns = {row[1] for row in db.execute("pragma table_info(brief_bank)")}
        if "edition_day" not in brief_columns:
            db.execute("alter table brief_bank add column edition_day text not null default 'unscheduled'")
        if "target_date" not in brief_columns:
            db.execute("alter table brief_bank add column target_date text")
        if "target_date_source" not in brief_columns:
            db.execute("alter table brief_bank add column target_date_source text not null default 'unscheduled'")
        if "candidate_id" not in brief_columns:
            db.execute("alter table brief_bank add column candidate_id text")
        if "machine_version" not in brief_columns:
            db.execute("alter table brief_bank add column machine_version text")
        if "importance_score" not in brief_columns:
            db.execute("alter table brief_bank add column importance_score real")
        if "recency_score" not in brief_columns:
            db.execute("alter table brief_bank add column recency_score real")
        if "source_stage" not in brief_columns:
            db.execute("alter table brief_bank add column source_stage text not null default 'record'")
        if "rules_fired_json" not in brief_columns:
            db.execute("alter table brief_bank add column rules_fired_json text not null default '[]'")
        if "evidence_hash" not in brief_columns:
            db.execute("alter table brief_bank add column evidence_hash text not null default ''")
        if "evidence_confidence" not in brief_columns:
            db.execute("alter table brief_bank add column evidence_confidence real")
        if "evidence_confidence_reason" not in brief_columns:
            db.execute("alter table brief_bank add column evidence_confidence_reason text not null default 'not_applicable'")
        if "gates_passed_json" not in brief_columns:
            db.execute("alter table brief_bank add column gates_passed_json text not null default '[]'")
        if "score_reasons_json" not in brief_columns:
            db.execute("alter table brief_bank add column score_reasons_json text not null default '{}'")
        if "scoring_profile_id" not in brief_columns:
            db.execute("alter table brief_bank add column scoring_profile_id text")
        profile_columns = {row[1] for row in db.execute("pragma table_info(scoring_profiles)")}
        if "rationale" not in profile_columns:
            db.execute("alter table scoring_profiles add column rationale text not null default ''")
        if "parent_profile_id" not in profile_columns:
            db.execute("alter table scoring_profiles add column parent_profile_id text")
        db.commit()


def row_dict(cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> dict[str, Any]:
    return {description[0]: row[index] for index, description in enumerate(cursor.description)}


def story_json(row: sqlite3.Row | dict[str, Any], *, public: bool = False) -> dict[str, Any]:
    item = dict(row)
    for key in ("topic_tags", "geography_tags", "entity_tags", "audience_tags", "urgency_tags", "claim_slots", "approval_history", "publication_history", "ethics_rules_json"):
        try:
            item[key] = json.loads(item.get(key) or "[]")
        except json.JSONDecodeError:
            item[key] = []
    item["ethics_rules"] = item.pop("ethics_rules_json", [])
    item["title"] = item["headline"]
    item["summary"] = item["dek"]
    item["published_at"] = item.get("approved_at")
    item["review_status"] = item["status"]
    item["wire_approved_at"] = item.get("approved_at")
    item["source_links"] = [item["source_url"]] if item.get("source_url") else []
    item["tags"] = list(dict.fromkeys(
        [f"market:{item.get('market')}", f"county:{item.get('county')}", f"city:{item.get('city')}"]
        + ([f"neighborhood:{slugify(str(item.get('neighborhood')))}"] if item.get("neighborhood") else [])
        + ([f"zip:{item.get('zip')}"] if item.get("zip") else [])
        + item["topic_tags"] + item["geography_tags"] + item["entity_tags"] + item["audience_tags"] + item["urgency_tags"]
    ))
    if public:
        for key in ("editor_note", "unresolved_issues"):
            item.pop(key, None)
    return item


def brief_bank_json(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    try:
        item["evidence"] = json.loads(item.pop("evidence_json", "{}") or "{}")
    except json.JSONDecodeError:
        item["evidence"] = {}
    try:
        item["rules_fired"] = json.loads(item.pop("rules_fired_json", "[]") or "[]")
    except json.JSONDecodeError:
        item["rules_fired"] = []
    try:
        item["gates_passed"] = json.loads(item.pop("gates_passed_json", "[]") or "[]")
    except json.JSONDecodeError:
        item["gates_passed"] = []
    try:
        item["score_reasons"] = json.loads(item.pop("score_reasons_json", "{}") or "{}")
    except json.JSONDecodeError:
        item["score_reasons"] = {}
    item["source_stage_order"] = SOURCE_STAGE_ORDER.get(str(item.get("source_stage") or "record"), 0)
    return item


def story_blocks(item: dict[str, Any]) -> list[str]:
    blocks: list[str] = []
    try:
        county_value(item.get("county"))
    except ValueError:
        blocks.append("A county is required")
    try:
        city_value(item.get("city"))
    except ValueError:
        blocks.append("A city is required")
    required = (("headline", "Headline"), ("dek", "Summary"), ("body", "Story body"), ("event_date", "Event date"), ("source_title", "Source title"))
    for key, label in required:
        if not str(item.get(key) or "").strip():
            blocks.append(f"{label} is required")
    if not public_url(item.get("source_url")):
        blocks.append("A public HTTP(S) source URL is required")
    if not list_value(item.get("topic_tags")):
        blocks.append("At least one topic tag is required")
    if not list_value(item.get("geography_tags")):
        blocks.append("At least one geography tag is required")
    if str(item.get("claims_status")) != "passed":
        blocks.append("Claims check must pass")
    if str(item.get("verification_status")) != "verified":
        blocks.append("Story Packet must be VERIFIED; needs-verification items cannot publish")
    if not str(item.get("current_trigger") or "").strip():
        blocks.append("A dated current trigger is required")
    if not str(item.get("project_identity_basis") or "").strip():
        blocks.append("Project identity basis is required, even when it is a single record")
    claim_slots = json_array(item.get("claim_slots"))
    if not claim_slots:
        blocks.append("At least one source-bound claim slot is required")
    elif any(not isinstance(slot, dict) or not str(slot.get("claim") or "").strip() or not public_url(slot.get("source_url")) for slot in claim_slots):
        blocks.append("Every claim slot requires claim text and a public source URL")
    if str(item.get("validator_status")) != "passed":
        blocks.append("Claim-slot editor attestation must pass")
    if str(item.get("tags_status")) != "passed":
        blocks.append("Taxonomy check must pass")
    if str(item.get("writing_style") or "") not in WRITING_STYLES:
        blocks.append("An approved AP-style writing profile is required")
    if str(item.get("headline_mode") or "") not in HEADLINE_MODES:
        blocks.append("An approved headline mode is required")
    if str(item.get("jargon_mode") or "") not in JARGON_MODES:
        blocks.append("A jargon/plain-language rule is required")
    ethics_rules = set(list_value(item.get("ethics_rules") or item.get("ethics_rules_json")))
    missing_ethics = sorted(REQUIRED_ETHICS_RULES - ethics_rules)
    if missing_ethics:
        blocks.append("Editorial ethics checklist is incomplete: " + ", ".join(missing_ethics))
    if not str(item.get("editor_name") or "").strip():
        blocks.append("A named human editor is required")
    return blocks


def agenda_blocks(item: dict[str, Any]) -> list[str]:
    blocks: list[str] = []
    try:
        county_value(item.get("county"))
    except ValueError:
        blocks.append("A county is required")
    try:
        city_value(item.get("city"))
    except ValueError:
        blocks.append("A city is required")
    for key, label in (("meeting_title", "Meeting title"), ("meeting_date", "Meeting date"), ("item_number", "Item number"), ("property_address", "Property address"), ("proposed_action", "Proposed action")):
        if not str(item.get(key) or "").strip():
            blocks.append(f"{label} is required")
    if not public_url(item.get("source_url")):
        blocks.append("An official public packet URL is required")
    if not isinstance(item.get("source_page"), int) or int(item["source_page"]) < 1:
        blocks.append("A cited source page is required")
    if not isinstance(item.get("lat"), (int, float)) or not isinstance(item.get("lon"), (int, float)):
        blocks.append("Defensible coordinates are required")
    if not str(item.get("editor_name") or "").strip():
        blocks.append("A named human editor is required")
    return blocks


class Handler(SimpleHTTPRequestHandler):
    server_version = "TheDataWire/1.0"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def reply(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def query_market(self) -> str:
        return market_value(parse_qs(urlparse(self.path).query).get("market", ["broward"])[0])

    def query_city(self) -> str:
        return city_value(parse_qs(urlparse(self.path).query).get("city", ["fort-lauderdale"])[0])

    def authorized(self) -> bool:
        return bool(ADMIN_TOKEN) and self.headers.get("Authorization", "") == f"Bearer {ADMIN_TOKEN}"

    def require_admin(self) -> bool:
        if self.authorized():
            return True
        self.reply({"error": "Admin authorization required"}, HTTPStatus.UNAUTHORIZED)
        return False

    def read_json(self) -> dict[str, Any] | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length < 2 or length > MAX_BODY:
            self.reply({"error": "Invalid request body"}, HTTPStatus.BAD_REQUEST)
            return None
        try:
            payload = json.loads(self.rfile.read(length).decode())
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.reply({"error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
            return None
        if not isinstance(payload, dict):
            self.reply({"error": "JSON object required"}, HTTPStatus.BAD_REQUEST)
            return None
        return payload

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route == "/api/local-session":
            # Convenience for the local editorial desk only: requires explicit env opt-in
            # and a loopback client. Never enabled in production deployments.
            if os.getenv("DATA_WIRE_LOCAL_AUTOUNLOCK") == "1" and ADMIN_TOKEN and self.client_address[0] == "127.0.0.1":
                self.reply({"token": ADMIN_TOKEN, "market": "broward"})
            else:
                self.reply({"error": "Not available"}, HTTPStatus.NOT_FOUND)
            return
        if route == "/api/health":
            self.reply({"ok": True, "service": "the-data-wire", "at": now_iso(), "admin_writes_enabled": bool(ADMIN_TOKEN)})
            return
        if route == "/api/admin/signal-machine":
            if not self.require_admin():
                return
            self.reply(signal_machine_payload())
            return
        if route == "/api/admin/scoring-profiles":
            if not self.require_admin():
                return
            market = self.query_market()
            with sqlite3.connect(DB_PATH) as db:
                db.row_factory = sqlite3.Row
                rows = db.execute(
                    "select * from scoring_profiles where market=? order by created_at desc limit 50",
                    (market,),
                ).fetchall()
            profiles = []
            for row in rows:
                item = dict(row)
                try:
                    item["weights"] = json.loads(item.pop("weights_json", "{}") or "{}")
                except json.JSONDecodeError:
                    item["weights"] = {}
                profiles.append(item)
            self.reply({"market": market, "profiles": profiles, "active_production_profile_id": None,
                        "contract": "Draft profiles never affect production ranking until an external backtest and explicit activation gate exist."})
            return
        if route == "/api/wire/packets":
            market = self.query_market()
            city = self.query_city()
            with sqlite3.connect(DB_PATH) as db:
                db.row_factory = sqlite3.Row
                rows = db.execute("select * from stories where market=? and city=? and status in ('approved','published') order by approved_at desc", (market, city)).fetchall()
            packets = [story_json(row, public=True) for row in rows if not story_blocks(story_json(row))]
            self.reply({"market": market, "city": city, "packets": packets, "generated_at": now_iso(), "gate": "approved source-linked packets only"})
            return
        if route == "/api/agenda-recon":
            market = self.query_market()
            city = self.query_city()
            with sqlite3.connect(DB_PATH) as db:
                db.row_factory = sqlite3.Row
                rows = db.execute("select * from agenda_recon where market=? and city=? and editor_status='cleared' order by meeting_date, item_number", (market, city)).fetchall()
            items = [dict(row) for row in rows if not agenda_blocks(dict(row))]
            self.reply({"market": market, "city": city, "items": items, "generated_at": now_iso(), "gate": "editor-cleared cited properties only"})
            return
        if route == "/api/admin/stories":
            if not self.require_admin():
                return
            market = self.query_market()
            with sqlite3.connect(DB_PATH) as db:
                db.row_factory = sqlite3.Row
                rows = db.execute("select * from stories where market=? order by updated_at desc", (market,)).fetchall()
            self.reply({"market": market, "stories": [story_json(row) for row in rows]})
            return
        if route == "/api/admin/brief-bank":
            if not self.require_admin():
                return
            market = self.query_market()
            with sqlite3.connect(DB_PATH) as db:
                db.row_factory = sqlite3.Row
                total = db.execute("select count(*) from brief_bank where market=?", (market,)).fetchone()[0]
                rows = db.execute(
                    "select * from brief_bank where market=? order by created_at desc limit 250",
                    (market,),
                ).fetchall()
            self.reply({
                "market": market, "items": [brief_bank_json(row) for row in rows], "total": total,
                "truncated": total > len(rows),
                "generated_at": now_iso(),
                "contract": "Private selection bank only. AI consistency check, assembly, approval, scheduling and sending are separate gated stages.",
            })
            return
        if route == "/api/admin/review-summary":
            if not self.require_admin():
                return
            code, data = supabase_request(
                "signal_review_queue?select=queue_id,review_status,evidence_ready,source_record_date,amount"
                "&order=source_record_date.desc&limit=1000"
            )
            if code >= 400:
                self.reply(data if isinstance(data, dict) else {"error": "queue summary unavailable"},
                           HTTPStatus.BAD_GATEWAY)
                return
            items = data or []
            status_counts = {status: 0 for status in sorted(REVIEW_STATUSES)}
            ready = 0
            blocked = 0
            for item in items:
                status = str(item.get("review_status") or "").upper()
                if status in status_counts:
                    status_counts[status] += 1
                if item.get("evidence_ready") is True:
                    ready += 1
                else:
                    blocked += 1
            self.reply({
                "total": len(items),
                "ready": ready,
                "blocked": blocked,
                "status_counts": status_counts,
                "newest_event": (items[0].get("source_record_date") if items else None),
                "generated_at": now_iso(),
                "contract": "ready means a non-empty evidence packet exists; blocked candidates cannot be approved",
            })
            return
        if route == "/api/admin/pipeline-schedule":
            if not self.require_admin():
                return
            code, payload = pipeline_schedule()
            self.reply(payload, HTTPStatus.OK if code == 200 else HTTPStatus.BAD_GATEWAY)
            return
        if route == "/api/admin/pdmr-intent":
            if not self.require_admin():
                return
            params = parse_qs(urlparse(self.path).query)
            limit = bounded_int(params.get("limit", [6])[0], 6, 1, 100)
            offset = bounded_int(params.get("offset", [0])[0], 0, 0, 1_000_000)
            search = params.get("search", [""])[0]
            code, payload = pdmr_intent_payload(limit, offset, search)
            self.reply(payload, HTTPStatus.OK if code == 200 else HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if route == "/api/admin/pdmr-candidates":
            if not self.require_admin():
                return
            params = parse_qs(urlparse(self.path).query)
            limit = bounded_int(params.get("limit", [8])[0], 8, 1, 20)
            code, payload = pdmr_shadow_candidate_payload(limit)
            self.reply(payload, HTTPStatus.OK if code == 200 else HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if route == "/api/admin/early-intel":
            if not self.require_admin():
                return
            self.reply(early_intel_payload())
            return
        if route == "/api/admin/project-state":
            if not self.require_admin():
                return
            code, payload = project_state_payload()
            self.reply(payload, HTTPStatus.OK if code == 200 else HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if route == "/api/admin/agenda-watch":
            if not self.require_admin():
                return
            code, payload = agenda_watch_payload()
            self.reply(payload, HTTPStatus.OK if code == 200 else HTTPStatus.BAD_GATEWAY)
            return
        if route == "/api/admin/sunbiz-entities":
            if not self.require_admin():
                return
            code, payload = sunbiz_entities_payload(parse_qs(urlparse(self.path).query))
            self.reply(payload, HTTPStatus.OK if code == 200 else HTTPStatus.BAD_GATEWAY)
            return
        if route == "/api/admin/review-queue":
            if not self.require_admin():
                return
            params = parse_qs(urlparse(self.path).query)
            query, limit, offset, readiness = review_queue_path(params)
            code, data = supabase_request(query)
            if code >= 400:
                self.reply(data if isinstance(data, dict) else {"error": "queue unavailable"},
                           HTTPStatus.BAD_GATEWAY)
                return
            items = [attach_investigation_context(dict(item)) for item in (data or [])]
            self.reply({"items": items, "limit": limit, "offset": offset,
                        "has_more": len(items) == limit, "readiness": readiness,
                        "generated_at": now_iso(),
                        "gate": "editorial queue — approval requires evidence and records a decision; it publishes nothing"})
            return
        if route == "/":
            self.path = "/home.html"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if not self.require_admin():
            return
        route = urlparse(self.path).path
        payload = self.read_json()
        if payload is None:
            return
        if route == "/api/admin/scoring-profiles":
            try:
                market = market_value(payload.get("market"))
            except ValueError as error:
                self.reply({"error": str(error)}, HTTPStatus.UNPROCESSABLE_ENTITY)
                return
            name = str(payload.get("name") or "").strip()[:120]
            rationale = str(payload.get("rationale") or "").strip()[:1000]
            parent_profile_id = str(payload.get("parent_profile_id") or "").strip()[:120] or None
            created_by = str(payload.get("created_by") or "editor").strip()[:120]
            raw_weights = payload.get("weights") if isinstance(payload.get("weights"), dict) else {}
            if not name:
                self.reply({"error": "Profile name is required"}, HTTPStatus.UNPROCESSABLE_ENTITY)
                return
            if not rationale:
                self.reply({"error": "A short reason for this experiment is required"}, HTTPStatus.UNPROCESSABLE_ENTITY)
                return
            weights: dict[str, float] = {}
            for stage in SOURCE_STAGE_ORDER:
                if stage == "record":
                    continue
                value = raw_weights.get(stage)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 1 or value > 2:
                    self.reply({"error": f"{stage} multiplier must be between 1.00 and 2.00"}, HTTPStatus.UNPROCESSABLE_ENTITY)
                    return
                weights[stage] = round(float(value), 2)
            created = now_iso()
            profile_id = hashlib.sha256(f"{market}:{name}:{created}".encode()).hexdigest()[:20]
            with sqlite3.connect(DB_PATH) as db:
                db.execute(
                    "insert into scoring_profiles (id,market,name,weights_json,status,backtest_status,rationale,parent_profile_id,created_by,created_at,updated_at) values (?,?,?,?,?,?,?,?,?,?,?)",
                    (profile_id, market, name, json.dumps(weights), "draft", "not_run", rationale, parent_profile_id, created_by, created, created),
                )
                db.execute(
                    "insert into audit_log (market,object_type,object_id,action,actor,detail,created_at) values (?,?,?,?,?,?,?)",
                    (market, "scoring_profile", profile_id, "draft_created", created_by,
                     json.dumps({"weights": weights, "rationale": rationale,
                                 "parent_profile_id": parent_profile_id, "production_effect": False}), created),
                )
                db.commit()
            self.reply({
                "ok": True, "id": profile_id, "status": "draft", "backtest_status": "not_run", "weights": weights,
                "note": "Draft saved for simulation only. It does not change Signal Machine ranking.",
            }, HTTPStatus.CREATED)
            return
        review_action = re.fullmatch(r"/api/admin/review-queue/(?P<qid>\d{1,12})", route)
        if review_action:
            patch: dict[str, Any] = {}
            status = str(payload.get("review_status", "")).upper().strip()
            if status:
                if status not in REVIEW_STATUSES:
                    self.reply({"error": f"Unknown review status: {status}"}, HTTPStatus.BAD_REQUEST)
                    return
                if status in {"APPROVED", "REJECTED"} and payload.get("confirmation") != "reviewed-evidence":
                    self.reply({"error": "Confirm that you reviewed the evidence before recording this decision"},
                               HTTPStatus.CONFLICT)
                    return
                if status == "APPROVED":
                    check_code, check_data = supabase_request(
                        "signal_review_queue?select=queue_id,evidence_ready,evidence_hash,receipt_status"
                        f"&queue_id=eq.{review_action.group('qid')}&limit=1"
                    )
                    item = (check_data or [None])[0] if check_code < 400 else None
                    if not item or item.get("evidence_ready") is not True or not item.get("evidence_hash"):
                        self.reply({"error": "Approval blocked: this candidate does not have a complete evidence receipt"},
                                   HTTPStatus.CONFLICT)
                        return
                patch["review_status"] = status
                # A decision is stamped; it is not a publish action.
                if status in {"APPROVED", "REJECTED", "HOLD", "NEEDS_MORE_REPORTING"}:
                    patch["decided_at"] = now_iso()
                    patch["decided_by"] = str(payload.get("decided_by", "editor"))[:120]
            if "destinations" in payload:
                chosen = [str(d) for d in list_value(payload.get("destinations"))]
                unknown = sorted(set(chosen) - REVIEW_DESTINATIONS)
                if unknown:
                    self.reply({"error": f"Unknown destination(s): {', '.join(unknown)}"},
                               HTTPStatus.BAD_REQUEST)
                    return
                patch["destinations"] = chosen
            for field, limit in (("editor_headline", 300), ("editor_summary", 2000),
                                 ("editor_notes", 4000), ("assigned_reviewer", 120)):
                if field in payload:
                    patch[field] = str(payload.get(field) or "")[:limit] or None
            if not patch:
                self.reply({"error": "Nothing to update"}, HTTPStatus.BAD_REQUEST)
                return
            code, data = supabase_request(
                f"signal_review_queue?queue_id=eq.{review_action.group('qid')}",
                method="PATCH", body=patch, prefer="return=representation")
            if code >= 400:
                self.reply(data if isinstance(data, dict) else {"error": "update failed"},
                           HTTPStatus.BAD_GATEWAY)
                return
            item = (data or [None])[0]
            self.reply({"ok": True, "item": item,
                        "note": "Editorial decision recorded. Nothing has been published."})
            return
        if route == "/api/admin/stories":
            try:
                market = market_value(payload.get("market"))
                county = county_value(payload.get("county"))
                city = city_value(payload.get("city"))
            except ValueError as error:
                self.reply({"error": str(error)}, HTTPStatus.UNPROCESSABLE_ENTITY)
                return
            headline = str(payload.get("headline") or "").strip()
            if not headline:
                self.reply({"error": "Headline is required"}, HTTPStatus.UNPROCESSABLE_ENTITY)
                return
            story_id = str(payload.get("id") or hashlib.sha256(f"{market}:{city}:{headline}:{now_iso()}".encode()).hexdigest()[:16])
            slug = slugify(str(payload.get("slug") or headline))
            source_url = str(payload.get("source_url") or "").strip()
            source_hash = hashlib.sha256(source_url.encode()).hexdigest() if source_url else None
            created = now_iso()
            geography_tags = list_value(payload.get("geography_tags"))
            geography_tags.extend([f"county:{county}", f"city:{city}"])
            neighborhood = str(payload.get("neighborhood") or "").strip()[:160] or None
            zip_code = str(payload.get("zip") or "").strip()[:10] or None
            if neighborhood:
                geography_tags.append(f"neighborhood:{slugify(neighborhood)}")
            if zip_code:
                geography_tags.append(f"zip:{zip_code}")
            geography_tags = list(dict.fromkeys(geography_tags))[:30]
            writing_style = str(payload.get("writing_style") or "ap_florida_signal").strip().lower()
            headline_mode = str(payload.get("headline_mode") or "compelling_precise").strip().lower()
            jargon_mode = str(payload.get("jargon_mode") or "plain_english").strip().lower()
            ethics_rules = set(list_value(payload.get("ethics_rules")))
            if writing_style not in WRITING_STYLES or headline_mode not in HEADLINE_MODES or jargon_mode not in JARGON_MODES:
                self.reply({"error": "Unknown Brief writing profile"}, HTTPStatus.UNPROCESSABLE_ENTITY)
                return
            missing_ethics = sorted(REQUIRED_ETHICS_RULES - ethics_rules)
            if missing_ethics:
                self.reply({"error": "Required editorial ethics rules are missing: " + ", ".join(missing_ethics)}, HTTPStatus.UNPROCESSABLE_ENTITY)
                return
            values = {
                "id": story_id, "market": market, "county": county, "city": city, "slug": slug, "headline": headline,
                "dek": str(payload.get("dek") or payload.get("summary") or "").strip()[:1000],
                "body": str(payload.get("body") or "").strip()[:100000], "byline": str(payload.get("byline") or "Florida Signal Desk").strip()[:120],
                "writing_style": writing_style, "headline_mode": headline_mode, "jargon_mode": jargon_mode,
                "ethics_rules_json": json.dumps(sorted(ethics_rules)),
                "event_date": str(payload.get("event_date") or "").strip()[:40] or None, "source_url": source_url,
                "source_title": str(payload.get("source_title") or "").strip()[:500], "source_published_at": str(payload.get("source_published_at") or "").strip()[:40] or None,
                "source_hash": source_hash, "topic_tags": json.dumps(list_value(payload.get("topic_tags"))), "geography_tags": json.dumps(geography_tags),
                "entity_tags": json.dumps(list_value(payload.get("entity_tags"))), "audience_tags": json.dumps(list_value(payload.get("audience_tags"))), "urgency_tags": json.dumps(list_value(payload.get("urgency_tags"))),
                "neighborhood": neighborhood, "zip": zip_code,
                "lat": payload.get("lat") if isinstance(payload.get("lat"), (int, float)) else None, "lon": payload.get("lon") if isinstance(payload.get("lon"), (int, float)) else None,
                "hero_image": str(payload.get("hero_image") or "").strip()[:1000] if public_url(payload.get("hero_image")) else None,
                "verification_status": str(payload.get("verification_status") or "needs_verification"),
                "current_trigger": str(payload.get("current_trigger") or "").strip()[:2000] or None,
                "project_identity_basis": str(payload.get("project_identity_basis") or "").strip()[:1000] or None,
                "claim_slots": json.dumps(json_array(payload.get("claim_slots"))),
                "unresolved_issues": str(payload.get("unresolved_issues") or "").strip()[:5000] or None,
                "validator_status": str(payload.get("validator_status") or "pending"),
                "approval_history": "[]", "publication_history": "[]",
                "status": "draft", "claims_status": str(payload.get("claims_status") or "pending"), "tags_status": str(payload.get("tags_status") or "pending"),
                "editor_name": str(payload.get("editor_name") or "").strip()[:120] or None, "editor_note": str(payload.get("editor_note") or "").strip()[:2000] or None,
                "approved_at": None, "created_at": created, "updated_at": created,
            }
            columns = ",".join(values)
            placeholders = ",".join("?" for _ in values)
            try:
                with sqlite3.connect(DB_PATH) as db:
                    db.execute(f"insert into stories ({columns}) values ({placeholders})", tuple(values.values()))
                    db.execute("insert into audit_log (market,object_type,object_id,action,actor,detail,created_at) values (?,?,?,?,?,?,?)", (market, "story", story_id, "draft_created", values["editor_name"], "{}", created))
                    db.commit()
            except sqlite3.IntegrityError:
                self.reply({"error": "That market already has a story with this slug"}, HTTPStatus.CONFLICT)
                return
            self.reply({"ok": True, "id": story_id, "status": "draft", "blocks": story_blocks({**values, "topic_tags": list_value(payload.get("topic_tags")), "geography_tags": geography_tags})}, HTTPStatus.CREATED)
            return
        if route == "/api/admin/brief-bank":
            try:
                market = market_value(payload.get("market"))
                county = county_value(payload.get("county"))
                city = city_value(payload.get("city"))
            except ValueError as error:
                self.reply({"error": str(error)}, HTTPStatus.UNPROCESSABLE_ENTITY)
                return
            source_kind = str(payload.get("source_kind") or "").strip().lower()[:80]
            source_id = str(payload.get("source_id") or "").strip()[:240]
            source_url = str(payload.get("source_url") or "").strip()
            source_title = str(payload.get("source_title") or "").strip()[:1000]
            if not source_kind or not source_id or not source_title:
                self.reply({"error": "Source kind, stable source ID and title are required"}, HTTPStatus.UNPROCESSABLE_ENTITY)
                return
            if not public_url(source_url):
                self.reply({"error": "A direct public source URL is required"}, HTTPStatus.UNPROCESSABLE_ENTITY)
                return
            evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
            evidence_text = json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))
            if len(evidence_text.encode()) > 250_000:
                self.reply({"error": "Evidence snapshot is too large"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return
            evidence_hash = hashlib.sha256(evidence_text.encode()).hexdigest()
            item_id = hashlib.sha256(f"{source_kind}:{source_id}".encode()).hexdigest()[:20]
            edition_day = str(payload.get("edition_day") or "unscheduled").strip().lower()
            if edition_day not in BRIEF_EDITION_DAYS:
                self.reply({"error": "Edition day must be Unscheduled or a weekday"}, HTTPStatus.UNPROCESSABLE_ENTITY)
                return
            target_date = str(payload.get("target_date") or "").strip()[:10] or None
            target_date_source = "unscheduled"
            if target_date:
                try:
                    parsed_target_date = datetime.strptime(target_date, "%Y-%m-%d")
                except ValueError:
                    self.reply({"error": "Target date must use YYYY-MM-DD"}, HTTPStatus.UNPROCESSABLE_ENTITY)
                    return
                # The exact date is authoritative. Derive its weekday so the two edition
                # controls can never silently disagree.
                edition_day = parsed_target_date.strftime("%A").lower()
                target_date_source = "explicit_date"
            elif edition_day != "unscheduled":
                weekdays = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                            "friday": 4, "saturday": 5, "sunday": 6}
                today = datetime.now().date()
                delta = (weekdays[edition_day] - today.weekday()) % 7
                target_date = (today + timedelta(days=delta)).isoformat()
                target_date_source = "weekday_default"
            source_stage = str(payload.get("source_stage") or "record").strip().lower()
            if source_stage not in SOURCE_STAGE_ORDER:
                self.reply({"error": "Unknown source stage"}, HTTPStatus.UNPROCESSABLE_ENTITY)
                return
            importance_score = payload.get("importance_score")
            recency_score = payload.get("recency_score")
            importance_score = float(importance_score) if isinstance(importance_score, (int, float)) else None
            recency_score = float(recency_score) if isinstance(recency_score, (int, float)) else None
            evidence_confidence = payload.get("evidence_confidence")
            evidence_confidence = float(evidence_confidence) if isinstance(evidence_confidence, (int, float)) else None
            if evidence_confidence is not None and not 0 <= evidence_confidence <= 1:
                self.reply({"error": "Evidence confidence must be between 0 and 1"}, HTTPStatus.UNPROCESSABLE_ENTITY)
                return
            evidence_confidence_reason = str(payload.get("evidence_confidence_reason") or "").strip().lower()
            if not evidence_confidence_reason:
                evidence_confidence_reason = "computed" if evidence_confidence is not None else "no_detector_for_family"
            if evidence_confidence_reason not in SCORE_REASON_VALUES:
                self.reply({"error": "Unknown evidence confidence reason"}, HTTPStatus.UNPROCESSABLE_ENTITY)
                return
            rules_fired = list_value(payload.get("rules_fired"))
            gates_passed = list_value(payload.get("gates_passed"))
            raw_score_reasons = payload.get("score_reasons") if isinstance(payload.get("score_reasons"), dict) else {}
            score_reasons: dict[str, str] = {}
            for axis in ("evidence_confidence", "editorial_importance", "recency", "early_stage_priority"):
                reason = str(raw_score_reasons.get(axis) or "").strip().lower()
                if not reason:
                    if axis == "evidence_confidence":
                        reason = evidence_confidence_reason
                    elif axis == "editorial_importance" and importance_score is not None:
                        reason = "computed"
                    elif axis == "recency" and recency_score is not None:
                        reason = "computed"
                    else:
                        reason = "no_detector_for_family"
                if reason not in SCORE_REASON_VALUES:
                    self.reply({"error": f"Unknown score reason for {axis}"}, HTTPStatus.UNPROCESSABLE_ENTITY)
                    return
                score_reasons[axis] = reason
            created = now_iso()
            values = (
                item_id, market, county, city, source_kind, source_id, source_url, source_title,
                str(payload.get("event_date") or "").strip()[:40] or None,
                str(payload.get("entity_name") or "").strip()[:240] or None,
                str(payload.get("body_name") or "").strip()[:240] or None,
                str(payload.get("why_it_matters") or "").strip()[:4000] or None,
                evidence_text, evidence_hash, evidence_confidence, evidence_confidence_reason,
                json.dumps(gates_passed), json.dumps(score_reasons),
                str(payload.get("scoring_profile_id") or "").strip()[:120] or None,
                "needs_cross_check", "not_started", "not_selected", edition_day, target_date, target_date_source,
                str(payload.get("candidate_id") or "").strip()[:240] or None,
                str(payload.get("machine_version") or "").strip()[:80] or None,
                importance_score, recency_score, source_stage, json.dumps(rules_fired),
                str(payload.get("added_by") or "editor").strip()[:120], created, created,
            )
            with sqlite3.connect(DB_PATH) as db:
                db.row_factory = sqlite3.Row
                existing = db.execute("select id from brief_bank where source_kind=? and source_id=?", (source_kind, source_id)).fetchone()
                inserted = existing is None
                db.execute(
                    """insert into brief_bank (
                    id,market,county,city,source_kind,source_id,source_url,source_title,event_date,
                    entity_name,body_name,why_it_matters,evidence_json,evidence_hash,evidence_confidence,
                    evidence_confidence_reason,gates_passed_json,score_reasons_json,scoring_profile_id,stage,cross_check_status,
                    assembly_status,edition_day,target_date,target_date_source,candidate_id,machine_version,importance_score,
                    recency_score,source_stage,rules_fired_json,added_by,created_at,updated_at
                    ) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    on conflict(source_kind,source_id) do update set
                      source_url=excluded.source_url,source_title=excluded.source_title,event_date=excluded.event_date,
                      entity_name=excluded.entity_name,body_name=excluded.body_name,why_it_matters=excluded.why_it_matters,
                      evidence_json=excluded.evidence_json,evidence_hash=excluded.evidence_hash,
                      evidence_confidence=excluded.evidence_confidence,
                      evidence_confidence_reason=excluded.evidence_confidence_reason,
                      gates_passed_json=excluded.gates_passed_json,score_reasons_json=excluded.score_reasons_json,
                      scoring_profile_id=excluded.scoring_profile_id,edition_day=excluded.edition_day,
                      target_date_source=excluded.target_date_source,
                      target_date=excluded.target_date,candidate_id=excluded.candidate_id,
                      machine_version=excluded.machine_version,importance_score=excluded.importance_score,
                      recency_score=excluded.recency_score,source_stage=excluded.source_stage,
                      rules_fired_json=excluded.rules_fired_json,updated_at=excluded.updated_at""",
                    values,
                )
                row = db.execute("select * from brief_bank where source_kind=? and source_id=?", (source_kind, source_id)).fetchone()
                db.execute(
                    "insert into audit_log (market,object_type,object_id,action,actor,detail,created_at) values (?,?,?,?,?,?,?)",
                    (market, "brief_bank", item_id, "queued_for_consistency_check" if inserted else "edition_slot_updated", values[31],
                     json.dumps({"source_kind": source_kind, "source_id": source_id, "edition_day": edition_day,
                                 "target_date": target_date, "evidence_hash": evidence_hash}), created),
                )
                db.commit()
            self.reply({
                "ok": True, "created": inserted, "item": brief_bank_json(row),
                "note": ("Added to Brief bank for evidence and consistency checks. Nothing was published or sent."
                         if inserted else "Brief bank edition slot updated. Nothing was duplicated or sent."),
            }, HTTPStatus.CREATED if inserted else HTTPStatus.OK)
            return
        story_action = re.fullmatch(r"/api/admin/stories/([a-zA-Z0-9_-]+)/(?P<action>approve|hold)", route)
        if story_action:
            story_id = story_action.group(1)
            action = story_action.group("action")
            with sqlite3.connect(DB_PATH) as db:
                db.row_factory = sqlite3.Row
                row = db.execute("select * from stories where id=?", (story_id,)).fetchone()
                if not row:
                    self.reply({"error": "Story not found"}, HTTPStatus.NOT_FOUND)
                    return
                item = story_json(row)
                item["claims_status"] = str(payload.get("claims_status") or item["claims_status"])
                item["tags_status"] = str(payload.get("tags_status") or item["tags_status"])
                item["verification_status"] = str(payload.get("verification_status") or item["verification_status"])
                item["validator_status"] = str(payload.get("validator_status") or item["validator_status"])
                item["editor_name"] = str(payload.get("editor_name") or item.get("editor_name") or "").strip()
                blocks = story_blocks(item) if action == "approve" else []
                if blocks:
                    self.reply({"error": "Publish gate blocked", "blocks": blocks}, HTTPStatus.UNPROCESSABLE_ENTITY)
                    return
                status = "approved" if action == "approve" else "hold"
                approved_at = now_iso() if status == "approved" else None
                history = json_array(item.get("approval_history"))
                history.append({"action": action, "actor": item["editor_name"], "at": now_iso()})
                db.execute("update stories set status=?,claims_status=?,tags_status=?,verification_status=?,validator_status=?,editor_name=?,editor_note=?,approved_at=?,approval_history=?,updated_at=? where id=?", (status, item["claims_status"], item["tags_status"], item["verification_status"], item["validator_status"], item["editor_name"], str(payload.get("editor_note") or item.get("editor_note") or "")[:2000], approved_at, json.dumps(history), now_iso(), story_id))
                db.execute("insert into audit_log (market,object_type,object_id,action,actor,detail,created_at) values (?,?,?,?,?,?,?)", (item["market"], "story", story_id, action, item["editor_name"], json.dumps({"blocks": blocks}), now_iso()))
                db.commit()
            self.reply({"ok": True, "id": story_id, "status": status, "approved_at": approved_at})
            return
        if route == "/api/admin/agenda-recon":
            try:
                market = market_value(payload.get("market"))
                county = county_value(payload.get("county"))
                city = city_value(payload.get("city"))
            except ValueError as error:
                self.reply({"error": str(error)}, HTTPStatus.UNPROCESSABLE_ENTITY)
                return
            identity = ":".join(str(payload.get(key) or "") for key in ("meeting_date", "item_number", "property_address"))
            item_id = str(payload.get("id") or hashlib.sha256(f"{market}:{city}:{identity}".encode()).hexdigest()[:16])
            created = now_iso()
            fields = {
                "id": item_id, "market": market, "county": county, "city": city, "meeting_title": str(payload.get("meeting_title") or "").strip(), "meeting_date": str(payload.get("meeting_date") or "").strip(),
                "item_number": str(payload.get("item_number") or "").strip(), "property_address": str(payload.get("property_address") or "").strip(), "folio": str(payload.get("folio") or "").strip() or None,
                "applicant": str(payload.get("applicant") or "").strip() or None, "proposed_action": str(payload.get("proposed_action") or "").strip(), "source_url": str(payload.get("source_url") or "").strip(),
                "source_page": payload.get("source_page") if isinstance(payload.get("source_page"), int) else None, "source_hash": hashlib.sha256(str(payload.get("source_url") or "").encode()).hexdigest() if payload.get("source_url") else None,
                "lat": payload.get("lat") if isinstance(payload.get("lat"), (int, float)) else None, "lon": payload.get("lon") if isinstance(payload.get("lon"), (int, float)) else None,
                "neighborhood": str(payload.get("neighborhood") or "").strip() or None, "zip": str(payload.get("zip") or "").strip() or None,
                "editor_status": "draft", "editor_name": str(payload.get("editor_name") or "").strip() or None, "editor_note": str(payload.get("editor_note") or "").strip() or None,
                "created_at": created, "updated_at": created,
            }
            columns = ",".join(fields); placeholders = ",".join("?" for _ in fields)
            with sqlite3.connect(DB_PATH) as db:
                db.execute(f"insert into agenda_recon ({columns}) values ({placeholders})", tuple(fields.values()))
                db.commit()
            self.reply({"ok": True, "id": item_id, "status": "draft", "blocks": agenda_blocks(fields)}, HTTPStatus.CREATED)
            return
        agenda_action = re.fullmatch(r"/api/admin/agenda-recon/([a-zA-Z0-9_-]+)/clear", route)
        if agenda_action:
            item_id = agenda_action.group(1)
            with sqlite3.connect(DB_PATH) as db:
                db.row_factory = sqlite3.Row
                row = db.execute("select * from agenda_recon where id=?", (item_id,)).fetchone()
                if not row:
                    self.reply({"error": "Agenda item not found"}, HTTPStatus.NOT_FOUND)
                    return
                item = dict(row); item["editor_name"] = str(payload.get("editor_name") or item.get("editor_name") or "").strip()
                blocks = agenda_blocks(item)
                if blocks:
                    self.reply({"error": "Agenda gate blocked", "blocks": blocks}, HTTPStatus.UNPROCESSABLE_ENTITY)
                    return
                db.execute("update agenda_recon set editor_status='cleared',editor_name=?,editor_note=?,updated_at=? where id=?", (item["editor_name"], str(payload.get("editor_note") or item.get("editor_note") or "")[:2000], now_iso(), item_id))
                db.execute("insert into audit_log (market,object_type,object_id,action,actor,detail,created_at) values (?,?,?,?,?,?,?)", (item["market"], "agenda_recon", item_id, "cleared", item["editor_name"], "{}", now_iso()))
                db.commit()
            self.reply({"ok": True, "id": item_id, "status": "cleared"})
            return
        self.reply({"error": "Not found"}, HTTPStatus.NOT_FOUND)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8788)
    args = parser.parse_args()
    init_db()
    print(f"The Data Wire running at http://{args.host}:{args.port}")
    if not ADMIN_TOKEN:
        print("Read-only: set DATA_WIRE_ADMIN_TOKEN to enable editorial writes")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
