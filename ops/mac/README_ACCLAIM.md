# Acclaim preliminary pipeline (native Mac — no Claude, no node)

**Purpose:** collect Broward Clerk recordings 2–4 business days AHEAD of the verified SFTP feed,
so Florida Signal isn't waiting on the delayed authoritative feed. Preliminary rows are later
reconciled to the verified feed and marked `verified`.

## Why native Mac (not the droplet)
Acclaim (officialrecords.broward.org) sits behind **Cloudflare**. Any non-browser client — plain
HTTP from the droplet OR from the Mac — gets a 403 "Attention Required" (proven 2026-07-19). The
only thing that passes is a **real, human-warmed Chrome** with a live `cf_clearance` cookie. The
DigitalOcean IP is additionally datacenter-blocked. So this pipeline drives the operator's real
Chrome via AppleScript on the residential Mac. `execute javascript` (Chrome → View → Developer →
"Allow JavaScript from Apple Events") must be enabled in the collector's Chrome profile; when it
is off, the job reports an action-required degraded state instead of a generic collector failure.

## Components (all in ops/mac/)
- `acclaim_harvest.applescript` — opens a dedicated Chrome window, passes Cloudflare, searches one
  record date, paginates the Telerik grid, writes NDJSON rows. Returns `OK` / `EMPTY` / errors nonzero.
- `acclaim_upsert.py` — pre-filters existing `(record_date, instrument_number)` then inserts new
  preliminary rows (service role; `source='acclaimweb-public-search'`). Idempotent; never touches verified tables.
- `acclaim_state.py` — persists per-date progress + backlog to
  `~/Library/Application Support/FloridaSignal/acclaim_state.json`. `last_completed_date` is
  coverage through a completed date; `last_event_date` advances only when that date contained
  source rows. An empty weekend therefore never fabricates a newer event clock.
- `acclaim_run_receipt.py` — validates one receipt per invocation, writes it to the local durable
  outbox at `~/Library/Application Support/FloridaSignal/acclaim_run_receipts/` first, then mirrors
  it idempotently to `broward_clerk_preliminary_run`. Pending receipts replay on the next run.
  Receipts distinguish `ok`, `empty`, `source_wait`, and `failed`, with run start/end/observation,
  attempted-through, event-through, verified-through, per-date outcomes, rows observed and rows new.
- `acclaim_pull.sh` — orchestrator/ExecStart. Computes missing dates AFTER the verified SFTP max,
  oldest-first, capped by `ACCLAIM_MAX_DATES` (8) and `ACCLAIM_MAX_PAGES` (40). After noon it also
  rechecks the current date on every run and reserves one target slot for it; exact-key upsert makes
  the forming-day refresh idempotent. Per-date state; resumes
  after gaps, prevents overlapping runs, and bounds hung browser automation. Transient Supabase
  reads retain the cached verified floor instead of rewinding. A Broward disclaimer redirect is
  reported as `source_wait`; so is Chrome's operator-controlled “Allow JavaScript from Apple
  Events” setting when disabled. In both cases, backlog and freshness warnings remain while the
  collector exits zero only when its durable run receipt is stored remotely. Technical automation,
  upsert, state or receipt failures exit nonzero; a failed remote receipt remains queued locally.
  Logs → `~/Library/Logs/florida-acclaim.log`.
- `com.floridasignal.acclaim.plist` — LaunchAgent at **00:30, 12:00, 19:00, and 22:30** local,
  plus an hourly retry and `RunAtLoad` catch-up, absolute paths, logs outside repo. Installed at
  `~/Library/LaunchAgents/`.

### Zero-result safety

An explicit empty Acclaim grid is not enough to close an unreleased weekday. The collector keeps
any weekday newer than the authoritative SFTP floor in its retry backlog, because Broward can show
“No Results to Display” before that date is released. Past weekends may close as zero; the current
day is always rechecked. This prevents a temporary source response from becoming a permanent data
gap. A waiting weekday does not block collection of a newer date that Broward has already exposed.

The target selector does not query the still-forming current day before noon. An `EMPTY`
current-day grid is never marked done; only an empty date strictly before today is final. This
prevents a pre-release visit from suppressing the later retry. A successful current-day pass also
does not suppress later hourly refreshes because recordings can be added throughout the day.

### Health-clock contract

The newest Clerk record is an **event clock**. The latest
`broward_clerk_preliminary_run.completed_at` is the **collector/system clock**. A successful poll
with no new rows advances only the run clock; it never rewrites source rows to manufacture
freshness. The Desk counts completed Florida business dates after `event_through`, excluding
weekends (and explicit Clerk holidays when supplied). A fresh Sunday `source_wait` with Friday
event coverage is therefore current, while a missed Monday post-noon release becomes delayed.

The receipt table is append-only to the collector: anonymous/authenticated users may read aggregate
run receipts; the service role may select and insert but not update or delete. Receipts contain no
party names, instruments, source HTML, browser cookies or secrets.

## Reconciliation (server-side, Supabase — off the Mac)
`public.reconcile_clerk_preliminary()` matches preliminary rows to `broward_clerk_records_doc` by
normalized instrument number + record date, sets `verification_status='verified'`, attaches
`verified_business_date`/`verified_doc_type`, preserves `preliminary_first_seen_at` + `source`, and
**flags date conflicts** (`conflict_flag`) instead of merging. pg_cron `clerk-preliminary-reconcile`
runs daily 10:00 UTC. Proven 2026-07-19: 1 match verified, 1 conflict flagged, verified table untouched.

## Operate
- Manual run:  `launchctl kickstart -k gui/$(id -u)/com.floridasignal.acclaim`
- Watch:       `tail -f ~/Library/Logs/florida-acclaim.log`  ·  state json above
- Schedule:    `launchctl print gui/$(id -u)/com.floridasignal.acclaim`

## Approval-gated activation order

This branch is inert until separately approved. Activate in this order, with a rollback check after
each step:

1. Apply `supabase/migrations/20260830233000_acclaim_run_receipts.sql`; verify RLS/grants and that no
   cron or trigger was created.
2. Deploy the collector/helper files to the exact tracked runtime path without changing the plist,
   timer cadence or Chrome profile.
3. Run one approved bounded kickstart. Require one matching local `.sent.json` and one remote row,
   with exact run ID/status/timestamps/counts and no source-row changes for an empty canary.
4. Deploy the site health adapter/Data Room UI only after the receipt readback passes. Verify event,
   attempted-through and run clocks render separately and that a missing receipt fails closed.
5. Observe at least two normal scheduled runs before closing the release. Roll back the site first,
   then collector; keep the receipt table as harmless evidence unless its separately reviewed
   rollback is approved.

Migration, production file deployment, service invocation/restart and site deployment are separate
owner approvals. None is authorized by editing or testing this branch.

## Rollback
`launchctl bootout gui/$(id -u)/com.floridasignal.acclaim` then re-enable the Claude task
`broward-sameday-recordings` (Scheduled sidebar). The Claude task is disabled/rollback-only after
multiple independent successful LaunchAgent runs; do not enable both writers during normal service.

## Requirements / limits
Needs Andy's Mac powered on + logged in, a usable Chrome profile, and the residential connection.
A first scheduled launch may prompt once for Automation permission (osascript → control Chrome).
Secrets: `~/.florida_signal_supabase_env` (mode 600, SUPABASE_URL / SUPABASE_ANON_KEY /
SUPABASE_SERVICE_ROLE_KEY) — never in the repo.
