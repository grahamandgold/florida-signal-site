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
  `~/Library/Application Support/FloridaSignal/acclaim_state.json`.
- `acclaim_pull.sh` — orchestrator/ExecStart. Computes missing dates AFTER the verified SFTP max,
  oldest-first, capped by `ACCLAIM_MAX_DATES` (8) and `ACCLAIM_MAX_PAGES` (40). Per-date state; resumes
  after gaps, prevents overlapping runs, and bounds hung browser automation. Transient Supabase
  reads retain the cached verified floor instead of rewinding. A Broward disclaimer redirect is
  reported as `source_wait`; so is Chrome's operator-controlled “Allow JavaScript from Apple
  Events” setting when disabled. In both cases, backlog and freshness warnings remain while the
  collector exits zero. Technical automation failures still exit nonzero.
  Logs → `~/Library/Logs/florida-acclaim.log`.
- `com.floridasignal.acclaim.plist` — LaunchAgent at **00:30, 12:00, 19:00, and 22:30** local,
  absolute paths, logs outside repo. Installed at `~/Library/LaunchAgents/`.

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

## Rollback
`launchctl bootout gui/$(id -u)/com.floridasignal.acclaim` then re-enable the Claude task
`broward-sameday-recordings` (Scheduled sidebar). The Claude task stays ENABLED as fallback until
THREE independent successful LaunchAgent runs, then becomes disabled/rollback-only (not deleted).

## Requirements / limits
Needs Andy's Mac powered on + logged in, a usable Chrome profile, and the residential connection.
A first scheduled launch may prompt once for Automation permission (osascript → control Chrome).
Secrets: `~/.florida_signal_supabase_env` (mode 600, SUPABASE_URL / SUPABASE_ANON_KEY /
SUPABASE_SERVICE_ROLE_KEY) — never in the repo.
