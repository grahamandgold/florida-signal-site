# Florida Signal — current system and product state

**Verified August 11, 2026 · replaces present-state claims in earlier dated handoffs**

Older handoffs remain historical evidence. This document is the current starting point for
pipeline, site, editorial, newsletter and automation work. Keep the public event clock
separate from every pull, sync, enrichment and publication clock.

## Executive state

- The production API resolves to `142.93.253.188`. `GET /api/health` is HTTP 200 with
  `mailchimp_configured:true` and `cms_configured:false`.
- Collection is mostly operating. The August 11 health manifest has no reported API errors;
  permits, the public mirror, the aggregate cache, preliminary Clerk and meetings are current.
- Broward's authoritative SFTP feed is delayed through August 6. The same-day preliminary
  Acclaim lane is current through August 11 and remains explicitly preliminary.
- The public CMS remains disconnected and the Brief publication registry remains empty, but the
  first durable editorial loop is now operating: eight exact Transfer → Permit Candidates are in
  the private review queue. None is a published Signal.
- The deed-to-parcel materialized view was refreshed from July 10 through August 6 and now exactly
  matches the ingested verified Clerk event window. A hard public view suppresses current modules
  whenever snapshot lag exceeds two business days.
- `sunbiz_entities` exists but has zero public rows. Exact entity/officer reporting is blocked;
  fuzzy identity writes remain prohibited.
- The public site remains too dense on mobile. Immediate local corrections are complete but
  are not deployed as of this document.

## Live source manifest

Verified from the production API at `2026-08-11T23:36:53Z`:

| Source | State | Event through | System time | Cadence / detail |
|---|---|---:|---:|---|
| Public mirror | current | varies by row | Aug 11 23:09 UTC | every 30 minutes; latest run 230 rows, 0 errors |
| Fort Lauderdale permits | current | Aug 10 | Aug 10 22:02 | nightly intake; mirror every 30 minutes |
| Aggregate dashboard | current | Aug 10 22:02 | Aug 11 21:00 | refresh after a successful aggregate build |
| Broward verified instruments | delayed | Aug 6 | Aug 11 18:10 | SFTP daily plus weekday catch-up; latest load 2,293 documents |
| Broward preliminary recordings | current, preliminary | Aug 11 | Aug 11 19:10 | 00:30, 12:00, 19:00 and 22:30 local |
| Meeting watch | current | scheduled events | Aug 11 23:28 | every 15 minutes; 20 upcoming rooms |
| Sunbiz | unverified | unknown | unknown | nightly raw ingest claimed; no public health timestamp |

FAA and FDEP contain live rows but are absent from `/api/data-health`; add their event and
system clocks before calling the health board complete.

## Data estate snapshot

Counts marked `est.` came from PostgreSQL planner statistics and can drift slightly.

| Dataset | Rows / coverage | Current use and condition |
|---|---:|---|
| Permits | 133,401 est.; event window Feb 2020–Aug 10, 2026 | core public record feed |
| Geocoded permits | 110,346 / 82.8% | roughly 23,000 records have no public map position |
| GIS/parcel-attached permits | 108,922 / 81.8% | exact parcel evidence when `parcel_id_verified` and `parcel_source` are present |
| Effective owner | 109,008 / 81.8% | provenance must remain visible |
| Native permit valuation | 16,122 / 12.1% | only this field may be called permit-declared value |
| Broward Clerk documents | 201,014 | authoritative, currently delayed through Aug 6 |
| Clerk parties | 527,143 est. | underused party dimension |
| Clerk legal rows | 24,754 | carries folio evidence for exact joins |
| Clerk link rows | 76,267 | unused instrument-to-instrument graph |
| Preliminary recordings | 30,970 | 24,230 reconciled; 6,740 open; 0 conflicts observed |
| County parcels | 531,525 est. | 110/110 import ranges complete; 0 failed or pending |
| Deed-to-parcel snapshot | 21,329 after Aug 11 refresh | event-through Aug 6; zero business-day lag behind the ingested verified Clerk table; public current view is hard-gated |
| FDEP ERP | 83,519 | ingested, underused, not on health board |
| FAA OE/AAA | 8,086 | ingested, underused, not on health board |
| Sunbiz entities | 0 | blocking company/officer/entity reporting |
| Meetings | 20 upcoming | fetched live, not persisted or joined historically |
| Signal review queue | 8 Transfer → Permit Candidates | private, `NEW`, hash-sealed; no publication action |
| Map candidates | 1 | dormant July example, not a working detector stream |
| Brief publication registry | 0 | no operating Brief product |

Raw retention is strong: permits retain `raw_json`, cleaning JSON and status history; Clerk
ingest retains unmapped source fields plus source-file SHA-256 and expected/observed counts;
parcel imports retain source attributes and vintage. Preserve this material. Do not discard
extra text because a current public field does not use it.

## Accuracy and editorial contract

1. **Record** — immutable normalized source row, raw text retained, direct source ID/URL,
   event and system clocks, preliminary/verified state.
2. **Candidate** — deterministic machine nomination from exact joins, thresholds or anomaly
   rules. Internal only; never publicly called a Signal.
3. **Signal** — editor-verified meaningful change: what changed, why it matters, proof,
   unknowns and what to watch next.
4. **Brief / Story** — contextual human reporting with timeline, evidence-to-claim map,
   publication/update/correction history and a publication-role approval.

No model may collect, deduplicate, join, assign confidence, suppress stale modules, publish,
send or correct. Models may draft from a sealed evidence packet; an unsupported-claim linter
and human gates remain mandatory.

Exact joins allowed: Clerk tables by instrument number; deed-to-parcel by the canonical
12-character folio only; permit-to-parcel only when the verified parcel and source are
present; preliminary-to-verified only when instrument and date agree. Address and party-name
similarity are search aids, not identity evidence. Conflicts are quarantined, never averaged
or guessed.

## Newsletter module readiness

### Runnable after basic freshness checks

- **Filed yesterday** — raw permit digest, collapsed; event date and direct filing receipt.
- **Preliminary watch** — same-day Clerk items, always labeled preliminary.
- **Rooms ahead** — verified official meeting links and times.
- **Waterfront and crane watch** — FDEP/FAA Candidates, reviewed before any Signal label.

### High-value modules after P0/P1 fixes

- transfer-then-permit and permit escalation timelines;
- instrument/financing chains from 76,267 Clerk link rows;
- party and operator dossiers from the 527,143-row party dimension plus exact Sunbiz matches;
- neighborhood baseline breaks from the 12-month aggregate history;
- meeting-to-parcel decision timelines after agendas are persisted and cited.

Every module needs a stale/empty fallback. A missing or stale Signal module collapses; it is
never padded with machine-written context. An honest Record-only edition is an acceptable
fallback, but sending remains a human decision until an explicit publication policy changes.

## Durable automation architecture

```text
hosted collectors / Mac-only Acclaim
        ↓ append-only raw records + run ledger
deterministic normalize / deduplicate / enrich
        ↓ exact joins, conflicts quarantined
deterministic detectors
        ↓ Candidate queue (unique IDs, capped daily)
evidence packet builder + receipt checker
        ↓
HUMAN GATE 1 — verify Candidate → Signal
        ↓
bounded AI draft from the sealed packet + claims linter
        ↓
HUMAN GATE 2 — approve Brief and edition
        ↓
deterministic module assembly / diagrams / suppression rules
        ↓
HUMAN GATE 3 — confirm audience and send
        ↓
freshness, lag, coverage, detector-yield and dead-letter monitoring
```

The database is shared state. Agents do not pass facts to one another in chat; they advance
versioned rows with unique IDs and lineage. Detectors read only Record tables, never their
own Candidate/Signal/Brief output, preventing self-reinforcing feedback loops. Hosted
systemd/pg_cron jobs own durable machine work; Claude/Codex tasks may prompt a human review
but must not be the only scheduler. Only the Cloudflare-protected Acclaim scrape is allowed
to depend on the residential Mac, and it must catch up oldest-first after sleep/offline time.

## Mailchimp aggregate state

Read-only aggregate inspection; no contact record was opened and no change was made:

| Audience | Contacts | Email subscribers | State |
|---|---:|---:|---|
| Broward Audience | 23 | 23 | website target; no campaign history observed |
| Ft. Lauderdale Signal | 21 | 20 | three March sends; active welcome automation |
| Michigan Data Center Tracker | 0 | 0 | unrelated draft audience |

The last Florida Signal campaign was sent March 23. The active welcome automation belongs to
the older Fort Lauderdale audience, not the Broward audience the website now targets.
Consolidation or re-pointing requires a separate reviewed change that preserves consent,
engagement history, deduplication and unsubscribe state. No audience/contact/campaign or
automation was changed during this audit.

## Analytics truth

The production SQLite store begins August 11. It contains 32 events: 16 page views across 16
session IDs and 16 source-health opens. Every page view was the Method route, a pattern highly
consistent with the automated audits run that day. Session IDs are not people. There is no
historical visitor count for the earlier public-preview period and no defensible audience
baseline yet.

## Local site corrections completed August 11

Not deployed as of this document:

- compact 65-pixel mobile header; redundant city control and decorative header emblem hidden;
- tagline made readable and fitted to the `FLORIDA SIGNAL` wordmark width;
- mobile map overlay reduced; key collapses by default; empty report launcher hidden;
- raw permits relabeled as filings, with address shown once and source fields preserved;
- public declared-value logic restricted to the permit's native `valuation`; enriched-only
  values cannot create high-value permit Signals;
- all production references to the withdrawn arrow-emblem assets removed;
- faint, filtered and rotated emblem watermarks removed from CSS; approved marks remain in
  readable identity/signature `<img>` placements;
- automatic ten-second newsletter modal disabled; manual preview remains at
  `?brief-preview=1`;
- brand and social documentation corrected;
- Signal/provenance regression suite expanded to 96 passing checks, including value provenance, emblem and
  timed-modal safeguards.

## Live truth-and-loop restoration completed August 11

- Applied three additive production migrations: durable editorial loop, source-delay separation
  and bounded FDEP health indexes.
- Refreshed `broward_property_transfer_map` to August 6: 21,329 rows and zero event-date lag
  relative to the ingested verified Clerk table.
- Added `broward_property_transfer_current`; it returns no rows if the snapshot trails the source
  by more than two business days.
- Added `property-transfer-refresh` (weekdays 19:20 UTC) and
  `transfer-permit-candidates-v1` (daily 03:30 UTC) in hosted pg_cron. Neither depends on a chat,
  laptop or Wi-Fi connection.
- The first detector grouped related permit applications by deed + exact canonical parcel,
  inserted eight private Candidates, and sealed every evidence packet with a verified SHA-256
  receipt. All eight recomputed successfully; Candidate IDs were unique.
- The first packet is the May 28 deed and August 10 $815,000 duplex application at 808 SW 8
  Terrace. The 1637 NE 5 Court packet groups eleven related trade/structural applications into one
  Candidate instead of eleven duplicate pseudo-stories.
- Production Clerk catch-up now paginates the complete run ledger and can recover ten missed
  business dates per run while retaining the newer parent-before-child, sanitized-error and
  reconciliation safeguards.
- Production `/api/data-health` now has no query errors and exposes separate clocks for verified
  Clerk, preliminary Clerk, permit enrichment, deed snapshot, FDEP, FAA and both editorial jobs.
  A timestamp parser defect that turned five-digit PostgreSQL fractions into midnight was fixed
  and regression-tested.
- Current live status: verified Clerk delayed through August 6; preliminary Clerk current through
  August 11; transfer snapshot current against the verified table; Sunbiz still unavailable.
- No Candidate was approved, no Story or Brief was published, and no Mailchimp send occurred.

Operating and recovery steps: `EDITORIAL_LOOP_RUNBOOK.md`.

## P0 — restore truth and restart the editorial loop

1. **Completed:** refresh and hard suppression gate for `broward_property_transfer_map`.
2. **Completed except Sunbiz rows:** FAA, FDEP, enrichment, snapshot and editorial clocks are on
   the live health board; Sunbiz is explicitly unavailable.
3. Observe enrichment for a full 24 hours; alert if ingest advances while enrichment/geocode/
   parcel lanes remain at zero.
4. Confirm Acclaim catch-up state and add a durable backlog alarm. Keep preliminary separate.
5. Populate `sunbiz_entities` from the authoritative corpus using exact matches only.
6. **First slice completed:** Transfer → Permit is capped at eight per run with grouped evidence
   packets and receipt checks. Do not publish from the queue automatically.
7. Connect the CMS and publish one real reviewed Brief before promising a mature daily product.
8. **Machine half completed:** refresh and Candidate jobs are durable pg_cron schedules. A
   recurring human review task still needs explicit scheduler inspection/approval.
9. Reconcile Mailchimp's two Florida audiences only after consent/history preservation is
   documented and approved; prove one genuine organic signup in both the private queue and
   intended audience without creating a synthetic contact.
10. Add bot/internal-traffic filtering, an aggregate analytics view and a written retention
    policy; collect 30 real days before setting conversion targets.

## Scheduled-task boundary

The audit listed scheduler history read-only and made no task change. The visible tasks
`Broward sameday recordings`, `Florida shadow run review` and `Regenerate social graphics`
still need a separate review of prompt, cadence, permissions, last success, duplicate work,
failure alerting and ownership. Scheduler history indicates the editorial chain ended as
one-shot reminders around July 26; recurring collectors continued, but Candidate review and
publication assembly did not.

## Required morning board after P0

Target under 15 minutes: verify one green/red health board; act only on red; review no more
than eight evidence packets; approve/hold/reject at Gate 1; read the assembled edition at
Gate 2; confirm the intended audience and count at Gate 3. Corrections are versioned and
annotated, never silently deleted.

## Deployed automation owners

Florida Signal has multiple kinds of automation; they are not interchangeable.

| Automation | Actual state | Owns |
|---|---|---|
| Supabase database schedules | Active where independently observed | Public mirror/cache work. A fresh cache timestamp is evidence of a run, not proof that every source is current. |
| Acclaim Mac LaunchAgent | Loaded and caught up | Preliminary Clerk collection at 12:30 a.m., noon, 7 p.m. and 10:30 p.m. local, plus hourly and login catch-up. State is complete through August 11 with no backlog. It does not maintain or deploy the website. |
| Other Florida Signal Mac LaunchAgents | Disabled | Files exist for intake, enrichment, backups, audits and rendering, but the labels are disabled and must not be re-enabled as a group. |
| GitHub Pages | Deploys `main` | Static HTML, CSS, JavaScript and assets only. It cannot run the Python API. |
| Codex recurring site task | None found | No existing Codex automation was maintaining the public site. |
| Public site health workflow | Active on `main` | Verifies pull requests and `main`, checks production hourly, preserves browser evidence and opens/updates a GitHub incident on scheduled failure. |
| Droplet source timers | Active | The production host reports enabled schedules for intake, sync, Accela, enrichment, Broward, Sunbiz, backups, parity and health work. A running timer is not proof of source completeness; use the public event clocks below. |

Do not reactivate old jobs until the current always-on owner, inputs, outputs, idempotency and overlap with database/server schedules are documented. A disabled file is not a missed heartbeat; it is an inactive definition.

## Current production limits and follow-up

1. The authoritative Broward SFTP source is delayed at an August 6 recording-date clock while the separately labeled preliminary lane reaches August 11. Do not present the newer rows as verified until reconciliation matches instrument number and record date.
2. Sunbiz remains unverified because its public health/event clock is not exposed.
3. The private Data Wire is intentionally not attached to the public API. `/api/cms` fails closed to an approved-only empty response; do not expose the local shared-token starter publicly.
4. The NHC `CurrentStorms.json` origin returns HTTP 403 to the DigitalOcean host. The public client falls back to the official NHC URL and shows a source-check state if both attempts fail; do not translate an unavailable source into “no storm.”
5. A valid live subscriber was not fabricated for testing. Persistence and idempotency passed against an isolated temporary database, and a read-only Mailchimp audience check succeeded; the first real consented signup remains the final live write-path proof.
6. Reconcile or close older site pull requests so `main` remains the only production release path.
7. Audit each disabled Mac collector against the active server/database schedules before deciding whether it is retired or restored. Do not create a second Acclaim writer while `com.floridasignal.acclaim` is loaded.

## August 5 preliminary recovery

- The preserved full Acclaim export contained 2,446 unique instruments; the original interrupted run had inserted 1,250.
- The 1,196-row remainder matched the preserved full-file tail and all recorded batch checksums before insertion.
- The service-role upsert inserted exactly 1,196 new rows and skipped no unexpected instruments.
- `reconcile_clerk_preliminary()` then matched all 2,446 August 5 rows to the authoritative feed with 0 conflicts and 0 aged unmatched rows.
- The recovered rows retain 2,446 direct-name values, 2,213 indirect-name values and 290 legal-text values. Recovery did not update the authoritative tables.

## August 11 connectivity and mirror recovery

- The noon Mac run occurred while Wi-Fi was unavailable. It retained the cached August 5 verified
  floor and did not advance the Acclaim state. After connectivity returned, the verified SFTP lane
  advanced through August 6.
- Broward redirected the collector to its periodic disclaimer. The collector recorded
  `terms_acceptance_required` without clicking the legal acceptance control or losing backlog;
  after manual acceptance, the retry harvested and inserted exactly 2,056 August 11 rows.
- Database audit counts were 0 conflicts for August 5, 6, 7, 10 and 11. August 5 and 6 are verified;
  August 7, 10 and 11 remain preliminary pending their authoritative files.
- The public mirror had stopped because `/srv/grahamandgold/florida-signal/secrets` was `root:root`
  mode `0700`, preventing the `andy` pipeline account from traversing the `app/.env` symlink. The
  directory was repaired to `root:andy` mode `0710`; pipeline `.env` remains `andy:andy` `0600`,
  while `public-site.env` remains root-only `0600` and unreadable by `andy`.
- A forced mirror completed at 3:11 p.m. ET: 27 tables, 10,872 rows and 0 errors, with a new
  heartbeat. A systemd-tmpfiles rule now makes the directory contract durable, and the hourly site
  monitor fails when `supabase-sync` becomes stale or unavailable.
- The first live immediate-reconciliation call correctly failed the systemd service when the old
  function exceeded PostgREST's statement timeout. Pipeline migration 009 added matching
  normalized-instrument/date indexes, including a partial index limited to unverified preliminary
  rows, and fixed the function search path. The rerun completed successfully with
  `matched=0 conflicts=0 aged_unmatched=0`; the daily pg_cron fallback remains enabled.

## Public API production facts

- DNS: GoDaddy A record `api` -> `142.93.253.188`, observed with a 600-second TTL.
- Host checkout: `/srv/grahamandgold/florida-signal-site`, clean `main` at `c74bf3b` before this recovery release.
- Service: `florida-signal-public.service`, bound to `127.0.0.1:4173`, enabled with restart-on-failure.
- Boundary: nginx exposes `/api/` only; `/` returns 404; allowed browser origins are the root and `www` production domains.
- TLS: Let's Encrypt certificate for `api.thefloridasignal.com`, renewal timer enabled; renewal dry-run succeeded August 11.
- Secrets: parent directory `root:andy` mode `0710`; `public-site.env` remains root-owned mode `0600` and unreadable by `andy`; systemd environment files use `NAME=value`, not shell `export` statements.
- Durable local data: `/srv/grahamandgold/florida-signal/data/public-api/florida_signal_cms.sqlite`, owned by `andy`, directory mode `0700`, file mode `0600`.
- Pre-deploy backup: `/srv/grahamandgold/florida-signal/backups/public-api/florida_signal_cms.pre-api-dns-20260811T0430Z.sqlite`.
- Runtime backup: the prior unversioned site directory was preserved as `/srv/grahamandgold/florida-signal-site.pre-git-20260811T0430Z`.

## Release rule

Static-site repairs may merge only after unit tests and browser checks pass. API and collector changes require their own source/data reconciliation plus rollback instructions. The hourly monitor may report incidents but must not alter source data or publish a narrative repair. Human editorial approval remains mandatory for briefs and consequential narrative claims.
