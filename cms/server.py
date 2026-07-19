#!/usr/bin/env python3
"""The Data Wire: multi-market, source-gated editorial CMS starter."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DATA_WIRE_DB_PATH", str(ROOT / "data" / "data_wire.sqlite")))
ADMIN_TOKEN = os.getenv("DATA_WIRE_ADMIN_TOKEN", "").strip()
MAX_BODY = 1_000_000
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
        ensure_city_scoped_story_slugs(db)
        db.execute("create index if not exists stories_market_status on stories(market, status, approved_at)")
        db.execute("create index if not exists stories_market_city_status on stories(market, city, status, approved_at)")
        agenda_columns = {row[1] for row in db.execute("pragma table_info(agenda_recon)")}
        if "city" not in agenda_columns:
            db.execute("alter table agenda_recon add column city text not null default 'fort-lauderdale'")
        if "county" not in agenda_columns:
            db.execute("alter table agenda_recon add column county text not null default 'broward-county'")
        db.execute("create index if not exists agenda_market_city_status on agenda_recon(market, city, editor_status, meeting_date)")
        db.commit()


def row_dict(cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> dict[str, Any]:
    return {description[0]: row[index] for index, description in enumerate(cursor.description)}


def story_json(row: sqlite3.Row | dict[str, Any], *, public: bool = False) -> dict[str, Any]:
    item = dict(row)
    for key in ("topic_tags", "geography_tags", "entity_tags", "audience_tags", "urgency_tags", "claim_slots", "approval_history", "publication_history"):
        try:
            item[key] = json.loads(item.get(key) or "[]")
        except json.JSONDecodeError:
            item[key] = []
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
        blocks.append("Claim-slot validator must pass")
    if str(item.get("tags_status")) != "passed":
        blocks.append("Taxonomy check must pass")
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
            # Convenience for Andy's local desk only: requires explicit env opt-in
            # and a loopback client. Never enabled in production deployments.
            if os.getenv("DATA_WIRE_LOCAL_AUTOUNLOCK") == "1" and ADMIN_TOKEN and self.client_address[0] == "127.0.0.1":
                self.reply({"token": ADMIN_TOKEN, "market": "broward"})
            else:
                self.reply({"error": "Not available"}, HTTPStatus.NOT_FOUND)
            return
        if route == "/api/health":
            self.reply({"ok": True, "service": "the-data-wire", "at": now_iso(), "admin_writes_enabled": bool(ADMIN_TOKEN)})
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
        if route == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if not self.require_admin():
            return
        route = urlparse(self.path).path
        payload = self.read_json()
        if payload is None:
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
            values = {
                "id": story_id, "market": market, "county": county, "city": city, "slug": slug, "headline": headline,
                "dek": str(payload.get("dek") or payload.get("summary") or "").strip()[:1000],
                "body": str(payload.get("body") or "").strip()[:100000], "byline": str(payload.get("byline") or "Florida Signal Desk").strip()[:120],
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
