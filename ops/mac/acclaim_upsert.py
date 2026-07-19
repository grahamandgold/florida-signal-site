#!/usr/bin/env python3
"""Upsert harvested Acclaim NDJSON into broward_clerk_preliminary.
Idempotent: ON CONFLICT (record_date, instrument_number) DO NOTHING.
Preliminary label: source='acclaimweb-public-search'. Never touches verified tables.
Reads SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (or falls back to publishable, which RLS
allows for INSERT only if a policy exists — service role preferred) from env.
Usage: acclaim_upsert.py /tmp/acclaim_out.ndjson
"""
import json, os, sys, urllib.request

SB = os.environ.get("SUPABASE_URL", "https://jrjewmzkyluxdywyusrw.supabase.co").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY") or ""
if not KEY:
    sys.exit("FATAL: no SUPABASE_SERVICE_ROLE_KEY in env")

path = sys.argv[1]
rows = []
seen = set()
with open(path) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if not r.get("record_date") or not r.get("instrument_number"):
            continue
        k = (r["record_date"], r["instrument_number"])
        if k in seen:
            continue
        seen.add(k)
        r["source"] = "acclaimweb-public-search"
        rows.append(r)

if not rows:
    print("no rows to upsert")
    sys.exit(0)

def sb_headers():
    return {"apikey": KEY, "Authorization": "Bearer " + KEY, "Content-Type": "application/json"}

# Pre-filter existing (record_date, instrument_number) so re-runs never duplicate and never
# depend on a conflict target. The partial unique index still guards against races.
existing = set()
PAGE = 1000  # PostgREST caps rows per response; page through with Range headers.
for rd in sorted({r["record_date"] for r in rows}):
    offset = 0
    while True:
        url = (SB + "/rest/v1/broward_clerk_preliminary?select=instrument_number"
               "&record_date=eq." + rd + "&order=instrument_number")
        req = urllib.request.Request(url, headers=sb_headers())
        req.add_header("Range-Unit", "items")
        req.add_header("Range", "%d-%d" % (offset, offset + PAGE - 1))
        with urllib.request.urlopen(req, timeout=60) as resp:
            batch = json.loads(resp.read())
        for e in batch:
            existing.add((rd, str(e["instrument_number"])))
        if len(batch) < PAGE:
            break
        offset += PAGE

fresh = [r for r in rows if (r["record_date"], r["instrument_number"]) not in existing]
if not fresh:
    print("all %d harvested rows already present; nothing new" % len(rows))
    sys.exit(0)

inserted = 0
for i in range(0, len(fresh), 400):
    chunk = fresh[i:i + 400]
    req = urllib.request.Request(
        SB + "/rest/v1/broward_clerk_preliminary",
        method="POST", data=json.dumps(chunk).encode(), headers=sb_headers())
    req.add_header("Prefer", "return=minimal")
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status not in (200, 201, 204):
            sys.exit("FATAL: insert HTTP %s" % resp.status)
    inserted += len(chunk)

print("inserted %d new preliminary rows (%d harvested, %d already present)"
      % (inserted, len(rows), len(rows) - len(fresh)))
