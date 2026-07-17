#!/usr/bin/env python3
"""Local Florida Signal preview + public-data integration service.

The public data itself is read in-browser from Supabase under RLS. This server
adds same-origin meeting/storm feeds, durable local email capture, an optional
server-side Mailchimp upsert, and an approved-only Florida Desk/CMS adapter.
"""

from __future__ import annotations

import base64
import json
import hashlib
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, time as clock_time, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlparse
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "florida_signal_cms.sqlite"
AGENDA_RECON_PATH = DATA_DIR / "agenda_recon.json"
SITE_MODE_PATH = DATA_DIR / "site_mode.json"
NHC_URL = "https://www.nhc.noaa.gov/CurrentStorms.json"
LEGISTAR_CALENDAR_URL = "https://fortlauderdale.legistar.com/Calendar.aspx"
FLTV_URL = "https://www.fortlauderdale.gov/government/departments-i-z/strategic-communications/fltv"
DRC_AGENDA_URL = "https://www.fortlauderdale.gov/Government/Departments/City-Clerks-Office/Advisory-Boards-Committees-and-Authorities-Agendas-and-Minutes/Development-Review-Committee"
DRC_DETAILS_URL = "https://www.fortlauderdale.gov/Government/Departments/Development-Services/Urban-Design-and-Planning/Development-Applications-Boards-and-Committees/Development-Review-Committee"
EDITORIAL_MEETING_CHECKED_AT = "2026-07-17T02:15:00-04:00"
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ZIP_RE = re.compile(r"^\d{5}(?:-\d{4})?$")
MAX_BODY = 4096
RATE_WINDOW_SECONDS = 60
RATE_LIMIT = 6
_rate_lock = threading.Lock()
_rate_hits: dict[str, list[float]] = {}
_nhc_lock = threading.Lock()
_nhc_cache: dict[str, Any] = {"at": 0.0, "payload": None}
_meeting_lock = threading.Lock()
_meeting_cache: dict[str, Any] = {"at": 0.0, "payload": None}
_cms_lock = threading.Lock()
_cms_cache: dict[str, Any] = {"at": 0.0, "payload": None}

CMS_BASE_URL = os.getenv("FLORIDA_SIGNAL_CMS_URL", "").strip().rstrip("/")
CMS_TOKEN = os.getenv("FLORIDA_SIGNAL_CMS_TOKEN", "").strip()
CMS_MARKET = re.sub(r"[^a-z0-9-]", "", os.getenv("FLORIDA_SIGNAL_CMS_MARKET", "broward").strip().lower()) or "broward"
STORM_MODE_OVERRIDE = os.getenv("FLORIDA_SIGNAL_STORM_MODE", "").strip().lower()
MAILCHIMP_API_KEY = os.getenv("MAILCHIMP_API_KEY", "").strip()
MAILCHIMP_SERVER_PREFIX = os.getenv("MAILCHIMP_SERVER_PREFIX", "us2").strip()
MAILCHIMP_AUDIENCE_ID = os.getenv("MAILCHIMP_AUDIENCE_ID", "123540d751").strip()
MAILCHIMP_ZIP_MERGE_TAG = os.getenv("MAILCHIMP_ZIP_MERGE_TAG", "WATCHZIP").strip()
SUPABASE_URL = (os.getenv("FLORIDA_SIGNAL_SUPABASE_URL", "").strip() or "https://jrjewmzkyluxdywyusrw.supabase.co").rstrip("/")
SUPABASE_PUBLISHABLE_KEY = os.getenv("FLORIDA_SIGNAL_SUPABASE_PUBLISHABLE_KEY", "").strip() or "sb_publishable_dEyBjKE_vcTj3YYx4p6XvA_xnkVW3Wb"
_health_lock = threading.Lock()
_health_cache: dict[str, Any] = {"at": 0.0, "payload": None}


class LegistarCalendarParser(HTMLParser):
    """Extract the public rows Legistar renders before its API exposes them."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[dict[str, Any]]] = []
        self.in_row = False
        self.in_cell = False
        self.row: list[dict[str, Any]] = []
        self.text: list[str] = []
        self.links: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "tr" and ("rgRow" in attributes.get("class", "") or "rgAltRow" in attributes.get("class", "")):
            self.in_row = True
            self.row = []
        elif self.in_row and tag == "td":
            self.in_cell = True
            self.text = []
            self.links = {}
        elif self.in_cell and tag == "a" and attributes.get("href"):
            element_id = attributes.get("id", "")
            href = urljoin(LEGISTAR_CALENDAR_URL, unescape(attributes["href"] or ""))
            if "hypMeetingDetail" in element_id:
                self.links["details"] = href
            elif "hypAgenda" in element_id:
                self.links["agenda"] = href
            elif "hypVideo" in element_id:
                self.links["video"] = href
            elif "hypiCal" in element_id:
                self.links["ical"] = href
        elif self.in_cell and tag == "br":
            self.text.append(" ")

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self.in_cell:
            value = re.sub(r"\s+", " ", unescape("".join(self.text))).strip()
            self.row.append({"text": value, "links": self.links.copy()})
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if self.row:
                self.rows.append(self.row)
            self.in_row = False


DRC_DATES_2026 = ("2026-07-28", "2026-08-11", "2026-08-25", "2026-09-08", "2026-09-22", "2026-10-13", "2026-10-27", "2026-11-10", "2026-11-24", "2026-12-08")
INDUSTRY_EVENTS_2026 = (
    {
        "title": "Tower Club Real Estate Luncheon · South Florida Advantage",
        "date": "2026-07-22",
        "time": "3:30 PM",
        "location": "Tower Club Fort Lauderdale · 100 SE 3rd Ave",
        "url": "https://calendar.rworld.com/events/meeting/9cb7b07a-71b5-4b22-bc26-e3876e115068",
        "source": "RWorld official calendar",
        "lat": 26.1216385,
        "lon": -80.1397718,
        "coordinate_source": "OpenStreetMap address match · 100 SE 3rd Ave",
    },
    {
        "title": "Meet the General Contractors 2026 · Palm Beach",
        "date": "2026-07-23",
        "time": "4:00 PM",
        "location": "Kravis Center · West Palm Beach",
        "url": "https://www.casf.org/events/2026/07/23/networking/meet-the-general-contractors-2026-palm-beach/",
        "source": "Construction Association of South Florida",
    },
    {
        "title": "Networking Breakfast · Suffolk upcoming projects",
        "date": "2026-08-05",
        "time": "7:30 AM",
        "location": "Wyndham Boca Raton · 1950 Glades Road",
        "url": "https://www.casf.org/events/2026/08/05/networking/networking-breakfast-suffolk/",
        "source": "Construction Association of South Florida",
    },
    {
        "title": "Networking Breakfast · Rycon upcoming projects",
        "date": "2026-08-26",
        "time": "7:30 AM",
        "location": "Courtyard by Marriott · 2440 W Cypress Creek Road · Fort Lauderdale",
        "url": "https://www.casf.org/events/2026/08/26/networking/networking-breakfast-rycon-construction/",
        "source": "Construction Association of South Florida",
        "lat": 26.2017165,
        "lon": -80.1799911,
        "coordinate_source": "OpenStreetMap address match · 2440 W Cypress Creek Road",
    },
)


def published_room_coordinates(location: str) -> dict[str, Any]:
    """Coordinates only for exact published addresses already checked against OSM."""
    value = location.lower()
    if "1300 west broward boulevard" in value:
        return {"lat": 26.1212783, "lon": -80.1585452, "coordinate_source": "OpenStreetMap address match · 1300 W Broward Blvd"}
    if "700 nw 19" in value or "700 northwest 19" in value:
        return {"lat": 26.1322010, "lon": -80.1670950, "coordinate_source": "OpenStreetMap address match · 700 NW 19 Ave"}
    return {}


def meeting_payload() -> dict[str, Any]:
    now = time.time()
    with _meeting_lock:
        if _meeting_cache["payload"] is not None and now - float(_meeting_cache["at"]) < 900:
            return _meeting_cache["payload"]
        now_et = datetime.now(ZoneInfo("America/New_York"))
        today = now_et.date()
        meetings: list[dict[str, Any]] = []
        partial = False
        try:
            request = urllib.request.Request(
                LEGISTAR_CALENDAR_URL,
                headers={"User-Agent": "FloridaSignalPreview/1.0 (public-meeting watch)"},
            )
            with urllib.request.urlopen(request, timeout=12) as response:
                parser = LegistarCalendarParser()
                parser.feed(response.read().decode("utf-8", errors="replace"))
            watched_bodies = ("commission", "planning and zoning", "redevelopment", "historic preservation")
            for cells in parser.rows:
                if len(cells) < 7:
                    continue
                title = cells[0]["text"]
                if not any(body in title.lower() for body in watched_bodies):
                    continue
                try:
                    event_date = datetime.strptime(cells[1]["text"], "%m/%d/%Y").date()
                except ValueError:
                    continue
                if event_date < today:
                    continue
                try:
                    start_clock = datetime.strptime(cells[3]["text"], "%I:%M %p").time()
                except ValueError:
                    start_clock = clock_time(23, 59)
                starts_at = datetime.combine(event_date, start_clock, tzinfo=ZoneInfo("America/New_York"))
                session_hours = 5 if "development review" in title.lower() else 4
                if now_et > starts_at + timedelta(hours=session_hours):
                    continue
                lifecycle = "in session window" if starts_at <= now_et else "scheduled"
                details_url = cells[5]["links"].get("details") or LEGISTAR_CALENDAR_URL
                agenda_url = cells[6]["links"].get("agenda")
                video_url = cells[10]["links"].get("video") if len(cells) > 10 else None
                if not video_url and ("commission" in title.lower() or "workshop" in title.lower()):
                    video_url = FLTV_URL
                meetings.append(
                    {
                        "title": title,
                        "date": event_date.isoformat(),
                        "time": cells[3]["text"],
                        "location": cells[4]["text"],
                        "details_url": details_url,
                        "agenda_url": agenda_url or details_url,
                        "agenda_available": bool(agenda_url),
                        "watch_url": video_url,
                        "ical_url": cells[2]["links"].get("ical"),
                        "source": "Fort Lauderdale Legistar",
                        "status": lifecycle,
                        "starts_at": starts_at.isoformat(),
                        "category": "government",
                        "link_label": "Agenda" if agenda_url else "Official calendar",
                        **published_room_coordinates(cells[4]["text"]),
                    }
                )
        except (urllib.error.URLError, TimeoutError):
            partial = True

        for date_text in DRC_DATES_2026:
            event_date = datetime.strptime(date_text, "%Y-%m-%d").date()
            if event_date < today:
                continue
            starts_at = datetime.combine(event_date, clock_time(9, 0), tzinfo=ZoneInfo("America/New_York"))
            if now_et > starts_at + timedelta(hours=5):
                continue
            meetings.append(
                {
                    "title": "Development Review Committee",
                    "date": date_text,
                    "time": "9:00 AM",
                    "location": "Development Services · 700 NW 19 Ave",
                    "details_url": DRC_DETAILS_URL,
                    "agenda_url": DRC_AGENDA_URL,
                    "agenda_available": False,
                    "watch_url": None,
                    "ical_url": None,
                    "source": "City published 2026 DRC schedule",
                    "status": "in session window" if starts_at <= now_et else "scheduled",
                    "starts_at": starts_at.isoformat(),
                    "category": "government",
                    "link_label": "Agenda source",
                    "lat": 26.1322010,
                    "lon": -80.1670950,
                    "coordinate_source": "OpenStreetMap address match · 700 NW 19 Ave",
                    "verified_at": EDITORIAL_MEETING_CHECKED_AT,
                    "refresh_mode": "source-cited editorial schedule",
                }
            )

        for industry_event in INDUSTRY_EVENTS_2026:
            event_date = datetime.strptime(industry_event["date"], "%Y-%m-%d").date()
            start_clock = datetime.strptime(industry_event["time"], "%I:%M %p").time()
            starts_at = datetime.combine(event_date, start_clock, tzinfo=ZoneInfo("America/New_York"))
            if now_et > starts_at + timedelta(hours=4):
                continue
            meetings.append(
                {
                    "title": industry_event["title"],
                    "date": industry_event["date"],
                    "time": industry_event["time"],
                    "location": industry_event["location"],
                    "details_url": industry_event["url"],
                    "agenda_url": industry_event["url"],
                    "agenda_available": False,
                    "watch_url": None,
                    "ical_url": None,
                    "source": industry_event["source"],
                    "status": "in session window" if starts_at <= now_et else "scheduled",
                    "starts_at": starts_at.isoformat(),
                    "category": "industry",
                    "link_label": "Event details",
                    "verified_at": EDITORIAL_MEETING_CHECKED_AT,
                    "refresh_mode": "source-cited editorial listing",
                    **({"lat": industry_event["lat"], "lon": industry_event["lon"], "coordinate_source": industry_event["coordinate_source"]} if "lat" in industry_event else {}),
                }
            )

        def sort_key(meeting: dict[str, Any]) -> tuple[str, str]:
            try:
                normalized_time = datetime.strptime(meeting["time"], "%I:%M %p").strftime("%H:%M")
            except ValueError:
                normalized_time = "23:59"
            return meeting["date"], normalized_time

        meetings.sort(key=sort_key)
        verified_at = datetime.now(timezone.utc).isoformat()
        for meeting in meetings:
            fingerprint = "|".join(
                [meeting["title"], meeting["date"], meeting.get("time", ""), meeting.get("agenda_url", ""), meeting["source"]]
            )
            meeting["source_hash"] = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]
            meeting.setdefault("verified_at", verified_at)
            meeting.setdefault("refresh_mode", "15-minute official-calendar check")
        payload = {
            "meetings": meetings[:20],
            "calendar_url": LEGISTAR_CALENDAR_URL,
            "updated_at": verified_at,
            "cache_seconds": 900,
            "partial": partial,
        }
        _meeting_cache.update({"at": now, "payload": payload})
        return payload


def is_public_http_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def supabase_public_rows(path: str) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        headers={"Accept": "application/json", "apikey": SUPABASE_PUBLISHABLE_KEY, "User-Agent": "FloridaSignalDataHealth/1.0"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read(2_000_000).decode("utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Supabase health response must be a list")
    return [row for row in payload if isinstance(row, dict)]


def parse_source_time(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def health_status(value: Any, current_hours: float, delayed_hours: float) -> str:
    parsed = parse_source_time(value)
    if not parsed:
        return "unavailable"
    age = max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds() / 3600)
    if age <= current_hours:
        return "current"
    if age <= delayed_hours:
        return "delayed"
    return "stale"


def data_health_payload() -> dict[str, Any]:
    now = time.time()
    with _health_lock:
        if _health_cache["payload"] is not None and now - float(_health_cache["at"]) < 60:
            return _health_cache["payload"]
        errors: list[str] = []
        sync: dict[str, Any] = {}
        latest_application: dict[str, Any] = {}
        latest_seen: dict[str, Any] = {}
        cache_row: dict[str, Any] = {}
        try:
            rows = supabase_public_rows("_meta_sync_runs?select=id,completed_at,rows_synced,tables_touched,errors&order=completed_at.desc&limit=1")
            sync = rows[0] if rows else {}
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as error:
            errors.append("sync:" + type(error).__name__)
        try:
            rows = supabase_public_rows("permits?select=applied_date,last_seen_at&applied_date=not.is.null&order=applied_date.desc.nullslast&limit=1")
            latest_application = rows[0] if rows else {}
            rows = supabase_public_rows("permits?select=applied_date,last_seen_at&last_seen_at=not.is.null&order=last_seen_at.desc.nullslast&limit=1")
            latest_seen = rows[0] if rows else {}
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as error:
            errors.append("permits:" + type(error).__name__)
        try:
            rows = supabase_public_rows("dashboard_cache?select=payload,updated_at&id=eq.1&limit=1")
            cache_row = rows[0] if rows else {}
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as error:
            errors.append("dashboard:" + type(error).__name__)
        stats = cache_row.get("payload", {}).get("stats", {}) if isinstance(cache_row.get("payload"), dict) else {}
        meetings = meeting_payload()
        source_rows = [
            {"id": "supabase-sync", "label": "Public mirror", "status": health_status(sync.get("completed_at"), 1.25, 3), "system_time": sync.get("completed_at"), "event_through": None, "cadence": "every 30 minutes", "detail": f"{sync.get('rows_synced', 0)} rows in latest run · {sync.get('errors', 0)} errors" if sync else "No sync run visible"},
            {"id": "permits", "label": "Permit applications", "status": health_status(latest_seen.get("last_seen_at"), 30, 54), "system_time": latest_seen.get("last_seen_at"), "event_through": latest_application.get("applied_date"), "cadence": "source intake nightly; mirror every 30 minutes", "detail": "Analysis uses applied_date; last_seen_at is freshness metadata"},
            {"id": "aggregate-cache", "label": "Aggregate dashboard", "status": health_status(cache_row.get("updated_at"), 26, 54), "system_time": cache_row.get("updated_at"), "event_through": stats.get("permits_fresh"), "cadence": "refresh after successful aggregate build", "detail": "Counts remain visibly stamped when this cache is delayed"},
            {"id": "broward", "label": "Broward instruments", "status": health_status(stats.get("broward_fresh"), 48, 96), "system_time": cache_row.get("updated_at"), "event_through": stats.get("broward_fresh"), "cadence": "daily at 9:30 AM", "detail": "Deeds, mortgages, liens, NOCs and recorded instruments"},
            {"id": "meetings", "label": "Meeting watch", "status": health_status(meetings.get("updated_at"), .5, 2), "system_time": meetings.get("updated_at"), "event_through": None, "cadence": "Legistar every 15 minutes; DRC and industry editorially checked", "detail": f"{len(meetings.get('meetings', []))} upcoming rooms · every row links to its public source"},
            {"id": "sunbiz", "label": "Sunbiz", "status": "unverified", "system_time": None, "event_through": None, "cadence": "raw ingest nightly at 11:30 PM; exact matching in enrichment", "detail": "Public health timestamp is not yet exposed; fuzzy writes remain off"},
        ]
        payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "sources": source_rows, "errors": errors, "contract": "Event date drives analysis; pull, sync and cache times only describe freshness."}
        _health_cache.update({"at": now, "payload": payload})
        return payload


def cms_request(path: str) -> dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "FloridaSignalPreview/1.0 (approved-public-content-adapter)",
    }
    if CMS_TOKEN:
        headers["Authorization"] = f"Bearer {CMS_TOKEN}"
    separator = "&" if "?" in path else "?"
    request = urllib.request.Request(f"{CMS_BASE_URL}{path}{separator}market={quote(CMS_MARKET)}", headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:
        raw = response.read(2_000_000)
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("CMS response must be an object")
    return payload


def normalized_source_links(item: dict[str, Any]) -> list[str]:
    links = item.get("source_links") or item.get("sources") or []
    if isinstance(links, str):
        links = [links]
    normalized = [str(link).strip() for link in links if is_public_http_url(link)]
    direct = item.get("source_url")
    if is_public_http_url(direct) and direct not in normalized:
        normalized.append(str(direct).strip())
    return normalized


def normalize_taxonomy_values(value: Any, namespace: str) -> list[str]:
    """Return stable machine tags while preserving a clean editorial vocabulary."""
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    tags: list[str] = []
    for raw in values:
        text = str(raw).strip().lower()
        if not text:
            continue
        if ":" in text:
            supplied_namespace, text = text.split(":", 1)
            namespace_value = re.sub(r"[^a-z0-9-]", "", supplied_namespace) or namespace
        else:
            namespace_value = namespace
        slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
        if slug:
            tags.append(f"{namespace_value}:{slug}")
    return list(dict.fromkeys(tags))


def normalized_story_taxonomy(item: dict[str, Any]) -> dict[str, list[str]]:
    taxonomy = {
        "topic": normalize_taxonomy_values(item.get("topic_tags") or item.get("tags"), "topic"),
        "geography": normalize_taxonomy_values(item.get("geography_tags") or item.get("places") or item.get("neighborhoods"), "geography"),
        "entity": normalize_taxonomy_values(item.get("entity_tags") or item.get("entities"), "entity"),
        "source": normalize_taxonomy_values(item.get("source_tags"), "source"),
        "audience": normalize_taxonomy_values(item.get("audience_tags"), "audience"),
        "urgency": normalize_taxonomy_values(item.get("urgency_tags") or item.get("urgency"), "urgency"),
    }
    if not taxonomy["source"]:
        taxonomy["source"] = ["source:florida-desk"]
    if not taxonomy["audience"]:
        taxonomy["audience"] = ["audience:development-intelligence"]
    return taxonomy


def normalize_wire_story(item: dict[str, Any], endpoint: str) -> dict[str, Any] | None:
    if item.get("internal_preview") is True or item.get("excluded") is True:
        return None
    review_status = str(item.get("review_status") or item.get("status") or "").lower()
    approved_at = item.get("wire_approved_at") or item.get("approved_at") or item.get("published_at")
    endpoint_path = endpoint.split("?", 1)[0]
    if endpoint_path == "/api/wire/packets" and not approved_at and review_status not in {"approved", "published", "cleared"}:
        return None
    if endpoint_path == "/api/tracker-feed.json" and item.get("tracker_eligible") is False:
        return None
    headline = str(item.get("headline") or item.get("title") or "").strip()
    summary = str(item.get("summary") or item.get("why_it_matters") or item.get("dek") or "").strip()
    sources = normalized_source_links(item)
    if not headline or not sources:
        return None
    meeting = item.get("meeting") if isinstance(item.get("meeting"), dict) else {}
    taxonomy = normalized_story_taxonomy(item)
    tags = list(dict.fromkeys(tag for values in taxonomy.values() for tag in values))
    topic_label = taxonomy["topic"][0].split(":", 1)[1].replace("-", " ").title() if taxonomy["topic"] else "Approved desk brief"
    return {
        "id": str(item.get("id") or item.get("packet_id") or hashlib.sha256((headline + sources[0]).encode()).hexdigest()[:16]),
        "title": headline,
        "summary": summary,
        "published_at": approved_at or item.get("generated_at") or item.get("updated_at"),
        "source": str(meeting.get("body") or item.get("municipality") or item.get("county") or "Florida Signal Desk"),
        "source_url": sources[0],
        "source_links": sources,
        "category": topic_label,
        "tags": tags,
        "taxonomy": taxonomy,
        "lat": item.get("lat"),
        "lon": item.get("lon"),
        "neighborhood": item.get("neighborhood"),
        "zip": item.get("zip"),
        "review_status": "approved",
        "slug": str(item.get("slug") or ""),
        "body": str(item.get("body") or item.get("story_body") or "")[:100000],
        "byline": str(item.get("byline") or "Florida Signal Desk")[:120],
        "event_date": item.get("event_date"),
        "updated_at": item.get("updated_at") or approved_at,
        "hero_image": item.get("hero_image") if is_public_http_url(item.get("hero_image")) else None,
    }


def cleared_recon_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    required = ("meeting_title", "meeting_date", "item_number", "property_address", "source_url")
    items: list[dict[str, Any]] = []
    for item in payload.get("items", []):
        if not isinstance(item, dict) or item.get("editor_status") != "cleared":
            continue
        if not all(item.get(field) for field in required) or not is_public_http_url(item.get("source_url")):
            continue
        if not isinstance(item.get("lat"), (int, float)) or not isinstance(item.get("lon"), (int, float)):
            continue
        items.append(item)
    return items


def cms_payload() -> dict[str, Any]:
    """Read only content already approved for public downstream distribution."""
    if not CMS_BASE_URL:
        return {
            "configured": False,
            "connected": False,
            "stories": [],
            "agenda_recon_items": [],
            "source_endpoint": None,
            "market": CMS_MARKET,
            "gate": "approved-only; internal desk queues are never queried",
        }
    now = time.time()
    with _cms_lock:
        if _cms_cache["payload"] is not None and now - float(_cms_cache["at"]) < 60:
            return _cms_cache["payload"]
        stories: list[dict[str, Any]] = []
        endpoint_used: str | None = None
        error_message: str | None = None
        for endpoint, key in (("/api/wire/packets", "packets"), ("/api/tracker-feed.json", "stories")):
            try:
                upstream = cms_request(endpoint)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as error:
                error_message = type(error).__name__
                continue
            candidates = upstream.get(key) or upstream.get("items") or []
            if not isinstance(candidates, list):
                continue
            stories = [story for story in (normalize_wire_story(item, endpoint) for item in candidates if isinstance(item, dict)) if story]
            endpoint_used = endpoint
            break

        recon_items: list[dict[str, Any]] = []
        try:
            recon_items = cleared_recon_items(cms_request("/api/agenda-recon"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
            pass

        payload = {
            "configured": True,
            "connected": endpoint_used is not None,
            "stories": stories[:12],
            "agenda_recon_items": recon_items,
            "source_endpoint": endpoint_used,
            "market": CMS_MARKET,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "gate": "WirePacket approved-only, then tracker-eligible fallback; never /api/stories",
            "error": None if endpoint_used else error_message or "No supported public endpoint",
        }
        _cms_cache.update({"at": now, "payload": payload})
        return payload


def agenda_recon_payload() -> dict[str, Any]:
    """Publish only source-backed agenda properties cleared for the public map."""
    meetings = meeting_payload()
    stored: dict[str, Any] = {"items": [], "updated_at": None}
    if AGENDA_RECON_PATH.exists():
        try:
            stored = json.loads(AGENDA_RECON_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            stored = {"items": [], "updated_at": None}
    items = cleared_recon_items(stored)
    remote_items = cms_payload().get("agenda_recon_items", []) if CMS_BASE_URL else []
    seen = {str(item.get("source_hash") or item.get("source_url")) for item in items}
    for item in remote_items:
        fingerprint = str(item.get("source_hash") or item.get("source_url"))
        if fingerprint not in seen:
            items.append(item)
            seen.add(fingerprint)
    published_packets = [meeting for meeting in meetings["meetings"] if meeting.get("agenda_available")]
    return {
        "rooms_watched": len(meetings["meetings"]),
        "packets_posted": len(published_packets),
        "properties_cleared": len(items),
        "items": items,
        "updated_at": stored.get("updated_at") or meetings["updated_at"],
        "rule": "Official packet + extracted address/folio + source link + coordinates + editor_status=cleared",
    }


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """
            create table if not exists brief_subscribers (
              id integer primary key autoincrement,
              email text not null unique collate nocase,
              zip_code text,
              source text not null default 'website',
              status text not null default 'active',
              created_at text not null,
              updated_at text not null
            )
            """
        )
        columns = {row[1] for row in connection.execute("pragma table_info(brief_subscribers)")}
        if "zip_code" not in columns:
            connection.execute("alter table brief_subscribers add column zip_code text")
        if "mailchimp_status" not in columns:
            connection.execute("alter table brief_subscribers add column mailchimp_status text not null default 'pending'")
        if "mailchimp_synced_at" not in columns:
            connection.execute("alter table brief_subscribers add column mailchimp_synced_at text")
        connection.execute(
            """
            create table if not exists analytics_events (
              id integer primary key autoincrement,
              event_name text not null,
              page_path text not null,
              session_id text,
              properties_json text not null default '{}',
              created_at text not null
            )
            """
        )
        connection.execute("create index if not exists analytics_events_name_at on analytics_events (event_name, created_at)")
        connection.commit()


def rate_allowed(ip: str) -> bool:
    now = time.time()
    with _rate_lock:
        hits = [hit for hit in _rate_hits.get(ip, []) if now - hit < RATE_WINDOW_SECONDS]
        if len(hits) >= RATE_LIMIT:
            _rate_hits[ip] = hits
            return False
        hits.append(now)
        _rate_hits[ip] = hits
        return True


def nhc_payload() -> dict[str, Any]:
    now = time.time()
    with _nhc_lock:
        if _nhc_cache["payload"] is not None and now - float(_nhc_cache["at"]) < 300:
            return _nhc_cache["payload"]
        request = urllib.request.Request(
            NHC_URL,
            headers={"User-Agent": "FloridaSignalPreview/1.0 (public-record intelligence)"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        _nhc_cache.update({"at": now, "payload": payload})
        return payload


def mailchimp_configured() -> bool:
    return bool(MAILCHIMP_API_KEY and MAILCHIMP_SERVER_PREFIX and MAILCHIMP_AUDIENCE_ID)


def mailchimp_upsert(email: str, zip_code: str) -> bool:
    """Upsert an explicitly consented signup without exposing credentials client-side."""
    if not mailchimp_configured():
        return False
    member_hash = hashlib.md5(email.encode("utf-8")).hexdigest()  # Mailchimp's documented member key.
    url = f"https://{MAILCHIMP_SERVER_PREFIX}.api.mailchimp.com/3.0/lists/{MAILCHIMP_AUDIENCE_ID}/members/{member_hash}"
    merge_fields = {MAILCHIMP_ZIP_MERGE_TAG: zip_code} if MAILCHIMP_ZIP_MERGE_TAG else {}
    body = json.dumps(
        {
            "email_address": email,
            "status_if_new": "subscribed",
            "merge_fields": merge_fields,
        }
    ).encode("utf-8")
    basic = base64.b64encode(f"florida-signal:{MAILCHIMP_API_KEY}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        url,
        data=body,
        method="PUT",
        headers={
            "Accept": "application/json",
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/json",
            "User-Agent": "FloridaSignalPreview/1.0 (consented-signup-upsert)",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError):
        return False


class FloridaSignalHandler(SimpleHTTPRequestHandler):
    server_version = "FloridaSignalPreview/1.0"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        if self.path.endswith((".html", ".js", ".css")) or self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def json_response(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        route = self.path.split("?", 1)[0]
        if route == "/api/health":
            self.json_response(
                {
                    "ok": True,
                    "service": "florida-signal-preview",
                    "at": datetime.now(timezone.utc).isoformat(),
                    "cms_configured": bool(CMS_BASE_URL),
                    "mailchimp_configured": mailchimp_configured(),
                }
            )
            return
        if route == "/api/data-health":
            try:
                self.json_response(data_health_payload())
            except Exception as error:  # Health reporting must fail closed, never invent green.
                self.json_response({"error": "Data health unavailable", "detail": type(error).__name__, "sources": []}, HTTPStatus.BAD_GATEWAY)
            return
        if route == "/api/storms":
            try:
                self.json_response(nhc_payload())
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
                self.json_response({"error": "NHC feed unavailable", "detail": str(error)}, HTTPStatus.BAD_GATEWAY)
            return
        if route == "/api/site-mode":
            payload: dict[str, Any] = {"storm_watch": "off", "headline": "Florida Signal Storm Watch", "editor_note": "", "updated_at": None}
            try:
                loaded = json.loads(SITE_MODE_PATH.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    payload.update(loaded)
            except (OSError, json.JSONDecodeError):
                pass
            if STORM_MODE_OVERRIDE in {"on", "off"}:
                payload["storm_watch"] = STORM_MODE_OVERRIDE
                payload["control_source"] = "environment"
            else:
                payload["control_source"] = "site-mode"
            self.json_response(payload)
            return
        if route == "/api/meetings":
            self.json_response(meeting_payload())
            return
        if route == "/api/agenda-recon":
            self.json_response(agenda_recon_payload())
            return
        if route == "/api/cms":
            self.json_response(cms_payload())
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        route = self.path.split("?", 1)[0]
        if route == "/api/events":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0
            if content_length <= 0 or content_length > 4096:
                self.json_response({"error": "Invalid event body"}, HTTPStatus.BAD_REQUEST)
                return
            try:
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self.json_response({"error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
                return
            event_name = str(payload.get("event", "")).strip().lower()
            page_path = str(payload.get("page", "/")).strip()[:300]
            session_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(payload.get("session_id", "")))[:80]
            if not re.fullmatch(r"[a-z0-9_]{2,64}", event_name) or not page_path.startswith("/"):
                self.json_response({"error": "Invalid event"}, HTTPStatus.UNPROCESSABLE_ENTITY)
                return
            allowed_keys = {"action", "placement", "record_type", "source", "mode", "device", "section", "result_count", "share_type", "page_name", "status"}
            incoming = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}
            properties: dict[str, Any] = {}
            for key, value in incoming.items():
                if key not in allowed_keys or not isinstance(value, (str, int, float, bool)):
                    continue
                properties[key] = value[:120] if isinstance(value, str) else value
            created_at = datetime.now(timezone.utc).isoformat()
            with sqlite3.connect(DB_PATH) as connection:
                connection.execute(
                    "insert into analytics_events (event_name, page_path, session_id, properties_json, created_at) values (?, ?, ?, ?, ?)",
                    (event_name, page_path, session_id or None, json.dumps(properties, separators=(",", ":")), created_at),
                )
                connection.commit()
            self.json_response({"ok": True}, HTTPStatus.CREATED)
            return
        if route != "/api/subscribe":
            self.json_response({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        if not rate_allowed(self.client_address[0]):
            self.json_response({"error": "Please wait a minute and try again."}, HTTPStatus.TOO_MANY_REQUESTS)
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length <= 0 or content_length > MAX_BODY:
            self.json_response({"error": "Invalid request body"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.json_response({"error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
            return
        email = str(payload.get("email", "")).strip().lower()
        zip_code = str(payload.get("zip", "")).strip()
        source = re.sub(r"[^a-zA-Z0-9_-]", "", str(payload.get("source", "website")))[:64] or "website"
        if len(email) > 254 or not EMAIL_RE.match(email):
            self.json_response({"error": "Enter a valid email address."}, HTTPStatus.UNPROCESSABLE_ENTITY)
            return
        if not ZIP_RE.match(zip_code):
            self.json_response({"error": "Enter a valid ZIP code."}, HTTPStatus.UNPROCESSABLE_ENTITY)
            return
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(DB_PATH) as connection:
            existing = connection.execute(
                "select id from brief_subscribers where email = ?", (email,)
            ).fetchone()
            if existing:
                connection.execute(
                    "update brief_subscribers set status = 'active', zip_code = ?, source = ?, updated_at = ? where id = ?",
                    (zip_code, source, now, existing[0]),
                )
            else:
                connection.execute(
                    "insert into brief_subscribers (email, zip_code, source, created_at, updated_at) values (?, ?, ?, ?, ?)",
                    (email, zip_code, source, now, now),
                )
            connection.commit()
        mailchimp_synced = mailchimp_upsert(email, zip_code)
        sync_status = "synced" if mailchimp_synced else ("pending" if mailchimp_configured() else "local_only")
        with sqlite3.connect(DB_PATH) as connection:
            connection.execute(
                "update brief_subscribers set mailchimp_status = ?, mailchimp_synced_at = ? where email = ?",
                (sync_status, now if mailchimp_synced else None, email),
            )
            connection.commit()
        self.json_response(
            {"ok": True, "existing": bool(existing), "mailchimp_synced": mailchimp_synced, "delivery": sync_status},
            HTTPStatus.OK if existing else HTTPStatus.CREATED,
        )

    def log_message(self, format_string: str, *args: Any) -> None:
        print("[%s] %s" % (self.log_date_time_string(), format_string % args), flush=True)


def main() -> None:
    init_db()
    server = ThreadingHTTPServer(("127.0.0.1", 4173), FloridaSignalHandler)
    print("Florida Signal preview: http://127.0.0.1:4173/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
