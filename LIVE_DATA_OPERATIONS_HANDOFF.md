# Florida Signal live data operations handoff

> **HISTORICAL OPERATIONS SNAPSHOT.** The health table and runtime claims below record the
> July 17–19 state. For current production, backup, parcel, Sunbiz, branch, and launch truth,
> use [`SYSTEM_STATE_2026-07-28.md`](SYSTEM_STATE_2026-07-28.md) and
> [`REMAINING_WORK_REGISTER_2026-07-28.md`](REMAINING_WORK_REGISTER_2026-07-28.md). For the
> current August state, use [`SYSTEM_STATE_2026-08-11.md`](SYSTEM_STATE_2026-08-11.md).
> The live durable Candidate schedules, freshness gate and recovery procedure are in
> [`EDITORIAL_LOOP_RUNBOOK.md`](EDITORIAL_LOOP_RUNBOOK.md). They supersede the July reminder-chain
> automation descriptions below.

> **August corrections:** public permit-declared value now means native `permits.valuation` only;
> `valuation_usd_clean` may carry enriched context and must not be labeled applicant-declared.
> The public API and Mailchimp signup integration are live. The Data Wire CMS remains disconnected
> from the public runtime, and no Candidate can publish or send automatically.

## August 15 recovery and first-send state

The Broward Acclaim disclaimer was accepted in the collector's real Chrome session on August 15.
The local LaunchAgent retains `RunAtLoad`, hourly recovery, and the four scheduled collection times,
so a sleeping/offline Mac resumes at login and keeps retrying when connectivity returns.

The collector's zero-result rule is now source-aware. A weekday newer than the authoritative SFTP
floor can no longer be marked complete merely because Acclaim briefly says `No Results to Display`.
It remains `source_wait` and retryable, while newer exposed dates continue to collect. Current-day
zeros also remain retryable; past weekends and dates already covered by the verified feed may close
as real zeros. The focused resilience suite contains 11 tests for this behavior.

Verified at 1:16 p.m. ET on August 15:

| Lane | State | Event/source through | Evidence |
|---|---|---:|---|
| Broward Acclaim preliminary | Current | Aug 14 | 2,217 Aug 14 rows inserted; Aug 13 remains `source_wait` instead of being falsely closed. |
| Broward SFTP verified | Source-delayed | Aug 11 | Latest authoritative load parsed successfully; its publication delay stays separate from collector health. |
| Permit applications | Current | Aug 14 | Event time remains `applied_date`. |
| Permit enrichment | Current | processing clock only | Enrichment time is not substituted for an event date. |
| FDEP ERP | Current | Aug 13 | Daily collector completed August 15. |
| FAA OE/AAA | Current | Aug 14 | A transient upstream 503 cleared on retry; durable retries now follow the primary daily run at 10:10 and 11:10 UTC. |
| Sunbiz exact resolver | Current/private | source receipt Aug 15 | 583 exact-match rows; only aggregate freshness is public and raw entity rows remain RLS-protected. |

The Sunbiz aggregate receipt refreshes at 04:05 UTC after the nightly private ingest. The public
health API uses that receipt instead of requiring anonymous access to private entity rows.

The local Florida Signal Newsroom is running on port 8788 with editorial writes enabled. Its first-
send queue has 175 Candidates: 25 have non-empty evidence packets, 150 are evidence-blocked, zero
are human-approved, and the Brief Bank is empty. Those 25 are evidence-ready Candidates—not finished
Signals or newsletter copy. No edition has been sent or published. A human still must confirm reader
importance, claims, unknowns, wording and edition placement before any first send.

**Market:** Broward County  
**Live city:** Fort Lauderdale  
**Publisher:** Graham & Gold LLC  
**Last local verification:** July 19, 2026 (see `CLAUDETTE_HANDOFF_2026-07-19.md`)

This document records the July 17 operating snapshot and the durable data rules. It is not the current health report. Read [`SYSTEM_STATE_2026-08-11.md`](SYSTEM_STATE_2026-08-11.md) for current deployment, data-clock and automation truth. The rules below continue to separate the date an event happened from the time Florida Signal collected, synchronized, enriched or published it.

## August 11 Clerk operating state

The Broward Clerk feed has two intentionally separate lanes:

| Lane | Evidence level | Event through | System observation | Operating meaning |
|---|---|---:|---:|---|
| AcclaimWeb public search | Preliminary | Aug 11 | Aug 11, 3:10 p.m. ET | 2,056 same-day rows and source text. Keep the `PRELIMINARY` label until reconciliation. |
| Clerk SFTP | Verified | Aug 6 | Aug 11, 2:11 p.m. ET | 2,293 authoritative documents in the newest run. Source publication is several days behind AcclaimWeb. |

The August 5 preliminary interruption was recovered from preserved source files: 2,446 unique
rows now reconcile to SFTP with 0 conflicts and 0 aged unmatched rows. The database preserved all
available direct/indirect names, document type, book/page and legal text; it did not discard fields
just because the current site does not render them.

## The non-negotiable date rule

Analysis uses the public event clock:

- permits: `applied_date`;
- recorded instruments: `recording_date_iso`;
- companies: application, filing or registration date;
- meetings: scheduled meeting time; and
- stories: the date of the cited event, plus a separate publication time.

Pull, synchronization, enrichment, snapshot and publication timestamps describe freshness only. A batch arrival must never become the event date. If the event date is absent, the item stays visibly undated or out of an event-date chart.

## Verified source health snapshot

The local `/api/data-health` endpoint returned this state on July 17, 2026 at 5:45 p.m. ET:

| Feed | Public status | Event data through | Last system observation | Expected cadence | What must happen next |
|---|---|---:|---:|---|---|
| Public mirror | Current | Varies by row | Jul 17, 5:30 p.m. ET | Every 30 minutes | Continue heartbeat monitoring; the latest observed run reported 859 rows and 0 errors. |
| Permit applications | Current | Jul 16 | Jul 16, 10:02 p.m. ET | Source intake nightly; mirror every 30 minutes | Continue nightly intake; analyze by `applied_date`. |
| Aggregate dashboard | Stale | Jul 10 | Jul 11, 5:20 p.m. ET | After each successful aggregate build | Rebuild only from verified inputs, then replace snapshot ID 1. |
| Broward instruments | Stale | Jul 7 | Jul 11, 5:20 p.m. ET | Daily at 9:30 a.m. | Restore the daily collector and verify the recording-date span before publishing new totals. |
| Meeting Watch | Current | Varies by meeting | Jul 17, 5:41 p.m. ET | Legistar every 15 minutes; DRC/industry editorial check | Continue source polling and keep every row linked to its public source. |
| Sunbiz | Unverified | Not exposed | Not exposed | Raw ingest nightly at 11:30 p.m.; exact-match enrichment | Expose a health timestamp before calling it current; fuzzy entity writes remain off. |

The site intentionally shows stale and unverified states instead of manufacturing freshness.

## What each public number means

| Surface / number | Definition | Query or input | Update behavior | Important limitation |
|---|---|---|---|---|
| `2,263 applications in 14 days` | Count of permit application rows in the current 14-calendar-day window | Paginated `permits.applied_date >= window start` | Recomputed in the browser whenever the page loads after the mirror changes | Zero-count dates are retained; it is an application count, not completed construction. |
| `700 newest mapped filings` | Current-month permit rows with latitude and longitude, ordered by application date/freshness | `permits`, `applied_date >= first of month`, non-null coordinates, limit 700 | Recomputed on page load | A capped geocoded sample, never a complete monthly total. |
| `54 storm-related filings` | Mapped sample records whose permit text matches roofs, windows, shutters, drainage, seawalls, generators and related hardening terms | Current mapped sample plus explicit classifier in `app.js` | Recomputed on page load | Applications, not completed installations, damage reports or a forecast. |
| Application Pulse | Daily counts for the 14-day application window | Same application-date query | Recomputed on page load; social image must be re-exported after a verified refresh | Uses `applied_date`, never batch time. |
| Work Mix / Diagram of the Day | Counts of mapped records classified into trade/work families | Current 700-record mapped sample | Recomputed on page load | Categories may overlap when one filing names multiple trades. |
| Place Lens | Mapped sample resolved to official City neighborhood polygons and Census ZIP areas | Permit coordinates + City ArcGIS neighborhood layer + Census TIGERweb | Recomputed when map data loads | Area values represent the displayed sample only. |
| High-value queue | First 40 current-month records with declared value of at least $100,000, ordered by application date and value | `permits.valuation_usd_clean >= 100000`, limit 40 | Recomputed on page load | Not a monthly total; values are applicant-declared where supplied. |
| Value Ladder, Operator Board, Records Desk, Company Lens | Enriched aggregate/property/operator/entity context | `dashboard_cache` snapshot ID 1 and its source tables | Changes only after a successful aggregate rebuild | Each card keeps its own observed span; stale values remain stamped stale. |
| Broward record totals | Deeds, mortgages, liens, NOCs and other recorded instruments | Broward collector / Supabase aggregate | Intended daily at 9:30 a.m. | Must be grouped by recording date and visibly state the covered recording span. |
| Meeting Watch | Upcoming public and industry rooms | Fort Lauderdale Legistar, DRC source, cited industry calendars | Legistar every 15 minutes; other sources editorially checked | No invented meetings, directions, stream links or agendas. A TV icon appears only for a verified stream URL. |
| Storm Watch | Official Atlantic outlook plus local hardening/recovery filing views | NHC/NOAA official products + classified local permit sample | Official products refresh while active; local records follow permit cadence | Florida Signal is not a warning service. Publisher controls red Storm Watch mode. |
| Approved briefs | Human-approved WirePackets for Fort Lauderdale | Private Data Wire CMS adapter | Appears only after city, source, claims, taxonomy and named-human gates pass | No CMS draft or needs-verification item is public. |

## Live Data Room behavior

`/fort-lauderdale/graphics/` now opens with:

1. the three current definitions above;
2. the interactive mapped-record view;
3. a real heat-density toggle;
4. a direct path to the full field map; and
5. four organized rooms: **Now**, **Places**, **Property**, and **Watch**.

Every diagram names its application or recording window, links to the underlying field surface, carries a centered full-color Florida Signal emblem, supports social sharing/embedding, and can be added to a Field Brief. The heat layer shows density inside the current mapped application sample; it is not a demand forecast or property valuation.

## Daily operating sequence

### After the nightly permit intake

1. Confirm the intake completed without schema or authentication errors.
2. Confirm the mirror heartbeat and row count in `/api/data-health`.
3. Query the newest and oldest `applied_date` values; do not infer coverage from `last_seen_at`.
4. Spot-check coordinates, neighborhood resolution and duplicate permit numbers.
5. Load Home, Live Map and Data Room; verify their printed application windows agree.
6. Re-export affected Graphic Desk social images only after the data check passes.

### After the Broward 9:30 a.m. job

1. Confirm deed, mortgage, lien, NOC and instrument collectors completed.
2. Verify the newest `recording_date_iso` and the observed recording-date span.
3. Rebuild the aggregate snapshot only when the source job is complete.
4. Confirm Broward Record and Data Room carry the new span and system observation separately.
5. If the job fails, leave the previous total stamped stale and alert the operator.

### AcclaimWeb same-day recordings

1. `com.floridasignal.acclaim` runs at 12:30 a.m., noon, 7 p.m. and 10:30 p.m. local, hourly and at login.
2. Before noon, the still-forming current day is not a target and must not appear in backlog state.
3. After noon, re-harvest the current date on every run even when an earlier pass completed; the
   source grid can grow during the day and the exact-key upsert inserts only new instruments.
4. Collect missing dates after the verified SFTP floor oldest-first, while reserving one target slot
   for the current day so an offline backlog cannot starve same-day intelligence.
5. A date is complete only when every page was read and the harvested count reaches the source total; a same-day empty result is not completion.
6. Upsert by `(record_date, instrument_number)`; never overwrite the authoritative SFTP tables.
7. Reconcile by normalized instrument number plus exact record date. The verified SFTP service does
   this immediately after every run, including a no-op run; daily pg_cron is the fallback. Flag date
   conflicts instead of merging them. Migration 009 indexes both normalized join keys and limits
   the preliminary index to still-unverified rows so archive growth does not exceed the API timeout.
8. Confirm `/api/data-health` exposes both `clerk-preliminary` and `broward`, with `preliminary` and `verified` evidence labels respectively.
9. Wi-Fi or power loss does not discard dates: state advances only on a complete source count, then
   the next hourly/login run recomputes gaps from the verified floor. A Broward disclaimer redirect
   requires one human acceptance in Chrome; the following retry resumes automatically.

### Meetings and agendas

1. Poll the Fort Lauderdale Legistar source every 15 minutes.
2. Editorially recheck DRC and industry listings against their public source.
3. Store agenda, details and stream URLs separately; show only verified links.
4. Agenda Recon output remains draft until the official packet, property identity, coordinates, citations and named-human approval clear.

### Sunbiz and entity resolution

1. Run the raw ingest at 11:30 p.m.
2. Join only exact/defensible entity identifiers in enrichment.
3. Keep fuzzy writes disabled.
4. Expose the source event span and health timestamp before publishing the feed as current.

### Storm operations

1. Official NHC/NOAA products remain the authority.
2. Set `FLORIDA_SIGNAL_STORM_MODE=on` or update `data/site_mode.json` only as a publisher decision.
3. Verify the red mode, official outlook/track, coordinates and timestamps against the official source.
4. Do not describe local hardening filings as damage, completed work or an official preparedness score.

## Commands and endpoints

Run the local public site:

```sh
python3 server.py --bind 127.0.0.1 --port 4173
```

Run the private local Data Wire starter:

```sh
DATA_WIRE_ADMIN_TOKEN='set-a-private-token' python3 cms/server.py --port 8788
```

Health checks:

```sh
curl -s http://127.0.0.1:4173/api/health
curl -s http://127.0.0.1:4173/api/data-health
curl -s http://127.0.0.1:4173/api/site-mode
curl -s http://127.0.0.1:8788/api/health
```

The Clerk contract check is:

```sh
curl -fsS https://api.thefloridasignal.com/api/data-health | jq -e '
  any(.sources[]; .id == "broward" and .verification == "verified") and
  any(.sources[]; .id == "clerk-preliminary" and .verification == "preliminary")
'
```

Regenerate the ten social graphics and their canonical share pages after a successful verified refresh:

```sh
node social/export_graphic_desk.cjs http://127.0.0.1:4173
```

Export selected diagrams:

```sh
FLORIDA_SIGNAL_EXPORT_SLUGS='application-pulse,trades-pulse' node social/export_graphic_desk.cjs
```

## Environment and secrets

Start from `.env.example`. Keep CMS admin tokens, Mailchimp API keys and any service-role database key server-side. The browser uses only a publishable Supabase key protected by RLS.

The production public API reports `mailchimp_configured: true`, and a read-only authenticated check
confirmed the configured Broward audience on August 11. The private Data Wire remains unconfigured
on the public host by design. Do not create a fake live subscriber to test the write path: isolated
tests prove persistence and idempotency, and the first real consented signup should provide the final
production write-path confirmation. Optional city/topic merge fields remain best-effort and must not
block durable local acceptance.

## Stop-the-line conditions

Do not silently publish or refresh a number when any of these is true:

- event date is missing or replaced by a pull timestamp;
- source span unexpectedly shrinks;
- a capped query is presented as a total;
- duplicate permits/entities inflate the result;
- a map point cannot be tied to a cited record;
- a meeting, stream or agenda URL is not verified;
- a Storm Watch statement could be mistaken for official safety guidance; or
- a source-health timestamp is absent but the label says live/current.

## Production work still required after the August 11 API deployment

- Continue monitoring the delayed verified SFTP clock and the separate same-day Acclaim clock; do not treat source release lag as proof that the collector failed. Treat a stale `supabase-sync` heartbeat as a real mirror incident.
- Continue monitoring the aggregate-only Sunbiz health receipt; do not expose private entity rows or imply a comprehensive event span from the exact-match subset.
- Deploy the Data Wire behind real user authentication with persistent Postgres/Supabase, backups and retained audit logs.
- Confirm the first real consented signup is both durable locally and accepted by Mailchimp; replay only explicit-consent rows if retry is needed.
- Define and document the retention policy for the persistent public API analytics SQLite database.
- Resolve the NHC host-level 403 with an official, server-supported NOAA delivery path; until then keep the client fallback and source-check state.


## 2026-07-19 additions (Claudette)

New feeds and their clocks:

| Feed | Event clock | Cadence | Notes |
|---|---|---|---|
| FDEP ERP (`fdep_erp`) | `received_date` | pg_cron daily 09:20 UTC via `fdep-erp-sync` | Broward bbox, layers 0+1; leading indicator ~5–6 weeks. |
| FAA OE/AAA (`faa_oeaaa`) | `date_entered` | pg_cron daily 09:40 UTC via `faa-oeaaa-sync` | state=FL stored, `in_broward` generated; cranes = `structure_type LIKE 'CRANE%'`. |
| Preliminary recordings (`broward_clerk_preliminary`) | `record_date` | Native Mac LaunchAgent at 00:30, 12:00, 19:00 and 22:30 local plus login catch-up | From Clerk's public AcclaimWeb search, usually days ahead of SFTP. PRELIMINARY until exact row-level reconciliation; preserve extra source text and label accordingly anywhere surfaced. |

Historical automation inventory is in `CLAUDETTE_HANDOFF_2026-07-19.md`. Current truth supersedes it: the same-day Clerk owner is the native Mac LaunchAgent, and the verified SFTP owner is the droplet schedule/catch-up. Do not enable the historical Claude same-day writer in parallel.

As of the August 11 night audit, `broward-sameday-recordings` is paused and retained only for
emergency rollback. The native LaunchAgent remains loaded and is the sole same-day writer.

Local ops: `ops/launch_local.sh` (or the Florida Signal Desk / The Data Wire apps) starts both servers with desk token, Mailchimp env, and local auto-unlock. Mailchimp is configured as of 2026-07-19 (`mailchimp_configured: true`).
