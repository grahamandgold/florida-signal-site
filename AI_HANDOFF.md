# Florida Signal — AI Handoff

Last verified: August 30, 2026

> ## START HERE FIRST: `SYSTEM_STATE_2026-08-30.md`
> It records the current branch-only Newsroom/Data Room build, source clocks, Accela safeguards,
> tests and production gates. The August 11 handoffs remain historical. Use
> `EDITORIAL_LOOP_RUNBOOK.md` for the live Candidate schedules and recovery steps. The July
> checkpoint remains historical evidence, not current operational state.
>
> Two facts it exists to prevent you getting wrong:
> 1. The scorer and collectors are **not in this repository** — they are in `grahamandgold/florida-signal`.
> 2. The operator Mac runs **one** loaded collector LaunchAgent (Acclaim). The other plists on disk do **not** run.
>    Check with `launchctl list`, never `ls`.

## Product contract

Florida Signal is Broward-wide, source-first development intelligence launching city by city. Fort Lauderdale is the first live desk. The product turns public records into useful, place-specific signals without overstating coverage, inventing interpretation or hiding the source window.

The public site is not a raw database dump and The Data Wire is not an autonomous publisher. Automated systems can collect, normalize, classify, geocode and draft. A human editor clears consequential narrative claims and every public brief must retain its cited source.

## Read these first

1. `README.md` — local start, CMS access and operating links.
2. `EDITORIAL_LOOP_RUNBOOK.md` — current Candidate schedules, human gates and recovery steps.
3. `LIVE_DATA_OPERATIONS_HANDOFF.md` — historical source definitions and date rules.
4. `FLORIDA_SIGNAL_TAGGING_SYSTEM.md` — required city, county, neighborhood and topic fields.
5. `cms/README.md` — Data Wire schema, source gates and API contract.
6. `BRAND_KIT.md` and `SOCIAL_MEDIA_ASSET_GUIDE.md` — public visual and distribution rules.
7. `FLORIDA_SIGNAL_BUILD_REPORT.md` — implementation inventory and launch blockers.

## Non-negotiable data rules

- Use the underlying public event date for analysis: permit `applied_date`, instrument `recording_date_iso`, company application/registration date or scheduled meeting time.
- Pull, mirror, enrichment and publish times are freshness metadata only. A batch arrival never becomes the event date.
- Preserve the exact observed start and end date on every chart, map, ranking and share image.
- State sample caps. The newest 700 geocoded permits and a first-40 query are samples, not municipal totals.
- Do not call a source live/current when its public event span or source-health clock is absent or stale.
- Do not infer completed construction, storm damage, demand, ownership, contractor solicitation or causation from an application alone.
- Do not invent a neighborhood. Resolve it from the official City polygon; keep ZIP, corridor, municipality and county as separate fields.
- Every story/brief requires `city`; the current live value is `fort-lauderdale`. Public content URLs must stay under a city path.
- No source, no claim. Missing or uncertain facts are omitted, not filled with plausible text.

## Content object minimum

Every public content object should carry, even when not all fields are displayed:

- stable ID and canonical city-scoped URL;
- `city`, `county`, neighborhood/place and ZIP when resolved;
- content type and controlled topic tags;
- source name and direct public source URL;
- event date or event-date span;
- observed/system timestamp kept separately;
- coverage/sample note;
- verification status and editor state; and
- correction/history metadata after publication.

## System map

```text
Public sources
  -> collectors / public mirror
  -> normalized local datasets and Supabase-backed views
  -> enrichment (address, parcel, company, neighborhood, topic)
  -> source-health and editorial gates
  -> The Data Wire draft / approval queue
  -> city-scoped public site, maps, Data Room and share assets
  -> newsletter/social distribution with the same source window
```

The public site runs from `server.py` on port 4173. The private Data Wire runs from `cms/server.py` on port 8788. The Data Wire token belongs only in server environment/session storage. Never commit it or place it in public JavaScript.

## Data Room contract

The Data Room is investigation-first, not a gallery. Its order is:

1. live mapped filings and heat-density toggle;
2. **Now** — application pulse and work mix;
3. **Places** — neighborhoods, ZIPs, value and operator activity;
4. **Property** — Broward records, values and entity trails;
5. **Watch** — storm-relevant filings and meetings.

Every diagram has a visible date window, a direct destination to the underlying surface, Florida Signal branding, share/embed controls where appropriate and a Field Brief add action. The centered full-color emblem is branding; the document-plus icon is the report builder. Do not interchange them.

The public Data Room refreshes permits, meetings, storms and source health together. Manual refresh,
five-minute visible refresh and focus/visibility return all use the same deduplicated path. A failed
query is unavailable—not zero—and must not borrow a green state from another card. Preserve a last
good map through a later failed refresh while labeling the current source unavailable. Keep
preliminary and verified Clerk clocks separate.

## Private Newsroom discovery contract

The private Data Explorer starts with Preliminary Development Meeting Request (PDMR) planning
intent, then explicitly unconnected research sensors, ownership/capital, regulatory evidence and
permit execution. This order does not change the public map-first Data Room. PDMR is local/manual,
the studied records are public, and the frozen research roster does not mean access-locked records.
Connection, source health, automation mode and detector coverage are independent claims.

## Storm Watch contract

Storm Watch uses official NOAA/NHC material for weather context and clearly says Florida Signal is not an official warning service. Local permit classifications show recorded preparation/recovery-type applications; they do not prove storm damage, completed work or a forecast. When no named storm is active, the status is standby. Publisher-controlled activation can change the visual system and prominence, but it cannot change data definitions.

## Multi-city expansion

- One code pattern powers all cities; do not fork separate page logic.
- Fort Lauderdale is the only live desk in the public build.
- Other Broward municipalities use the shared coming-soon state with no dates or coverage promises.
- The CMS may prepare future markets, but Miami-Dade, Palm Beaches, Tampa Bay and Southwest Florida must not be promoted on the current public site.
- City selection is required on briefs and subscriber interests; Fort Lauderdale is preselected for the current desk.

## Safe implementation checklist

Before publishing any AI-assisted change:

- validate JavaScript, Python, JSON, SVG and local links;
- compare displayed values with their endpoint/dataset and retain zero days;
- confirm the event span and cap are visible;
- test desktop and a 390-pixel mobile viewport for overflow and readable contrast;
- test map popups, Street View/satellite links, share/embed and Field Brief actions;
- verify sponsor treatment cannot be confused with editorial content;
- confirm no private token, subscriber record or source credential entered the public bundle; and
- regenerate affected social exports only after the data refresh passes.

## Current production caveats

The August 30 work is pushed but not deployed. Planned early sensors remain unconnected; PDMR is
local/manual. Accela false-green/canary safeguards also remain branch-only. Supabase Edge-secret
rotation, database grant/RPC hardening and durable per-run receipts are production gates. See
`SYSTEM_STATE_2026-08-30.md` for the verified snapshot and explicit non-deployment boundary.



## 2026-07-19 addendum (Claudette)

- New Supabase sources: `fdep_erp`, `faa_oeaaa` (edge functions + pg_cron daily), `broward_clerk_preliminary` (AcclaimWeb same-day, PRELIMINARY until the verified SFTP business date lands — never present as verified).
- Internal Data Desk viewer at `cms/data.html`; Data Wire local auto-unlock via `/api/local-session` (loopback + `DATA_WIRE_LOCAL_AUTOUNLOCK=1` only — keep OFF in production).
- Brand: Atlantic palette + Montserrat/Figtree + `assets/lockup-2026-v2.png` / `assets/datawire-lockup.png`. Header lockup is live text; do not reintroduce the old PNG-only header.
- CTA copy is "Get Daily Intel Brief" site-wide. Diagram of the day rotates daily by date.
- `dashboard_cache` pg_cron re-armed at 30-minute cadence. Clerk SFTP verified-vs-source parity confirmed 2026-07-19.
- Full task/automation inventory and open work: `CLAUDETTE_HANDOFF_2026-07-19.md`.

## 2026-07-19 addendum (Drive offsite snapshot cleanup — verified)

Authorized permanent cleanup of eight obsolete full-size Google Shared Drive snapshot directories under `gdrive:08_Backups_and_Recovery/FL_Signal/01_DATABASE/snapshots/` (2026-07-10..16 and 2026-07-19). **Retained:** `latest/`, `snapshots/2026-07-18/`, `snapshots/2026-07-17/`, and archive `permits.sqlite.daily-20260703.gz`. Released **90,867,600,278** bytes. Jul 18 restore validation: SHA match + `PRAGMA quick_check=ok` (127,912 permits). **`RETENTION_MODE` remains `dry-run`** — permanent compressed retention policy still TODO. Droplet record: `/srv/grahamandgold/florida-signal/restore-tests/DRIVE_SNAPSHOT_CLEANUP_2026-07-19.md` and `START_HERE.md` (Drive mirror of START_HERE not claimed current). No timer/service/script/production-DB change for this cleanup.

## 2026-08-11 recovery and permanent automation

- Verified SFTP is through August 6; the newest run inserted 2,293 documents, 5,954 parties, 268
  legal rows and 1,049 links. Acclaim preliminary is through August 11 with 2,056 rows for that day.
- The Mac safely retained state while Wi-Fi was off. A periodic Broward disclaimer required human
  acceptance; after acceptance the retry completed with no backlog. The LaunchAgent now retries
  hourly in addition to its four calendar fires and `RunAtLoad`.
- `clerk_catchup.py` now runs `reconcile_clerk_preliminary()` after every authoritative run,
  including no-op runs. Daily pg_cron remains the fallback. Exact matches become verified;
  conflicts remain quarantined and source text is preserved. The first live RPC exposed the old
  function's full-scan timeout; migration 009 added normalized instrument/date indexes and a fixed
  search path. The service rerun succeeded with 0 conflicts and 0 aged unmatched rows.
- The public mirror outage was permissions drift on the shared secrets directory, not source data
  loss. Durable contract: directory `root:andy` `0710`, pipeline `.env` `andy:andy` `0600`, and
  `public-site.env` root-only `0600`. A tmpfiles rule restores the directory contract.
- The forced mirror completed with 27 tables, 10,872 rows and 0 errors. The hourly GitHub monitor
  now fails if `supabase-sync` is stale or unavailable.
