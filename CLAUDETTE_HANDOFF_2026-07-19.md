# Florida Signal — Claudette session handoff
**Date:** Sunday, July 19, 2026 (launch day)
**Operator:** Andy · **Agent:** Claudette (Claude, Cowork)
**Repo state:** branch `claudette/launch-day`; pushed through commit `75c677e` (rounds 1–2). Round 3 changes are LOCAL ONLY (not yet pushed — Andy to say "push").

---

## What shipped today

### New data sources (live in Supabase `florida-signal-prod`)
| Source | Table | Rows (at build) | Refresh |
|---|---|---|---|
| FDEP Environmental Resource Permits (docks/seawalls/wetlands; layers 0+1, Broward bbox) | `fdep_erp` | 8,309 | Edge function `fdep-erp-sync`, pg_cron daily 09:20 UTC |
| FAA OE/AAA obstruction cases (state=FL, OE+NRA; cranes flagged) | `faa_oeaaa` | 7,053 (472 Broward, 142 cranes) | Edge function `faa-oeaaa-sync`, pg_cron daily 09:40 UTC |
| Broward Clerk PRELIMINARY same-day recordings (AcclaimWeb public search; ~3 days ahead of verified SFTP) | `broward_clerk_preliminary` | ingests via scheduled agent | Claude task noon + 7pm weekdays |

Both edge functions use a private `?key=` (custom auth, verify_jwt off). All new tables: RLS on, anon SELECT (public records). Anon read policies were also added to existing public-record tables (clerk docs/party/legal/link, foia_workflow_events, gis_enrichment, bcpa_*, accela_*, enrichment, land_sales, lp_licenses). `leads` and `tier3_briefs` remain locked.

### Diagnostics / fixes
- **Clerk feed "9 days behind" = source QA lag, not data loss.** SFTP publishes ~6–9 days behind; DB verified complete vs server (byte-level parse check passed). Droplet collector skips runs occasionally (one-bd-per-run design); Claude catch-up task (2:15pm weekdays) makes it self-healing.
- **`refresh_dashboard_cache` cron was `active=false` since Jul 11.** Ran once manually, re-armed at every 30 min (`cron.job` id 1).
- **Signals v2** — 250 rows Apr 26–29 was a pilot. A SHADOW scorer runs daily 05:45 on the droplet under a five-run editorial gate (see scheduled task `florida-shadow-run-review`; ledger + open PRs in repo docs). Run 5 completes Mon Jul 20 — after Andy's review, say "merge" on the open PRs.

### Product / desks
- **Data Desk** (`cms/data.html`): read-only intelligence viewer — feed-health cards, preset field views (Deeds/Mortgages/NOCs/Liens/Judgments/FDEP/Cranes/Top signals/Owner flips/Licenses), searchable explorer, cross-source case drawers (permit → Accela detail + owner resolution + GIS + signal score + workflow trail; instrument → parties + legal).
- **Data Wire CMS**: rebranded to the new Data Wire logo (navy/electric/wire-green on bright paper, Montserrat/Figtree, square corners). Local auto-unlock: `GET /api/local-session` (loopback + env opt-in only); token form hides when active.
- **Launchers:** `~/Applications/Florida Signal Desk.app` and `~/Applications/The Data Wire.app` (+ Desktop aliases, custom icon tiles). Both run `ops/launch_local.sh`.

### Site (public)
- **Brand:** Atlantic palette (navy `#082a54`, electric `#1767ff`), Montserrat headlines + Figtree body, new `lockup-2026` art everywhere; header lockup is live text (two-tone FLORIDA/SIGNAL + divider) so DEVELOPMENT INTELLIGENCE is legible at all sizes.
- **Copy:** CTA is now "Get Daily Intel Brief" (was 6:15 Brief) in all 18 spots; "What's moving." → "Our top signals."; mobile ticker line now rotates real high-value filings (was "Permit mirror synced…").
- **Diagram of the day** now genuinely rotates daily (7 diagrams, deterministic by date).
- **Mobile:** overflow fixed (root cause: `.section-head` flex min-content), micro-text floors, thumb-size taps. QA sweeps on home/graphics/neighborhoods/meetings show no horizontal scroll.
- **Record rows:** action toolbar no longer overlaps headlines (now flows below content).
- **Signup:** Mailchimp configured (`mailchimp_configured: true`); personalize panel styled + compact (collapsed by default; topics grid fixed at 2 columns).

### Automations (complete list)
| What | Where | When |
|---|---|---|
| FDEP sync | Supabase pg_cron → edge fn | daily 09:20 UTC |
| FAA sync | Supabase pg_cron → edge fn | daily 09:40 UTC |
| Dashboard cache rebuild | Supabase pg_cron | every 30 min |
| Permit mirror | droplet (existing) | ~every 30 min |
| Clerk SFTP verified ingest | droplet (existing) + Claude catch-up task | droplet ~9:30am; catch-up 2:15pm weekdays |
| Preliminary same-day recordings | Claude task (browser + Supabase) | noon + 7pm weekdays |
| Social PNG re-export | Claude task (Playwright, data-health gated) | 9:40pm daily |
| Shadow scorer + morning review | droplet timer + Claude task | 05:45 / 08:20 daily (gate ends Jul 20) |

**Claude-dependency note:** only the catch-up, same-day, and social-export tasks run through Claude on the Mac. Everything else survives without Claude. Port-to-droplet sprint is planned (droplet `florida-signal-runtime` is reachable via `ssh florida`).

---

## Not done yet (priority order)
1. **Push round 3 to GitHub** (this doc + visual fixes + auto-unlock + icons). Awaiting Andy's "push".
2. **Droplet migration sprint** (~half day): move Acclaim same-day scraper, clerk catch-up, social export to systemd timers; removes Mac/Claude dependence.
3. **Signals gate completion** (Jul 20): review run 5 report, merge open PRs, then schedule production scorer + surface Top-20 in Data Desk/site.
4. **RealAuction foreclosures** (easy win, distress signal, folio-exact).
5. **Remaining roadmap sources:** Broward BCS unsafe structures + contractor licenses (HIGH-RISK scrape — needs explicit go), Broward AGOL GIS/utility/CRA layers, municipal liens, city meeting-minutes text mining, deeper BCPA raw_json extraction, Sunbiz health metadata exposure.
6. **CMS production hosting** (always-on server, real auth, HTTPS, backups) — required before paid tiers.
7. **Mailchimp campaign work:** first Daily Intel Brief template + send flow (connector available in Claude).
8. **Visual QA backlog:** micro-text inside some meeting/diagram cards on mobile; full pass on storm/method/briefs/brand pages; regenerate 10 social PNGs with Atlantic brand (nightly task will do this at 9:40pm — verify first run).
9. **Multi-city Broward expansion** (coming-soon template exists; shared code pattern per AI_HANDOFF rules).

## Keys & private files (all outside the repo)
- Desk token: `~/.florida_signal_datawire_token`
- Mailchimp env: `~/.florida_signal_mailchimp_env`
- Supabase publishable key: public by design (RLS is the boundary). Service-role key never used client-side.
- Edge-function sync key: embedded in function code + pg_cron URLs (server-side only).

## The rules that still govern everything
Event dates over pull dates · state windows and caps · no source, no claim · preliminary ≠ verified (Acclaim rows carry `source='acclaimweb-public-search'` until the matching SFTP business date lands) · human editor gates all public briefs (Data Wire) · droplet is production, enrich additively, never delete.

---
## Addendum — Clerk catch-up migration closure (2026-07-19 ~13:15 EDT)

**DECISION LOG:** The verified Broward Clerk catch-up now runs on DigitalOcean through a GitHub-tracked systemd timer and dedicated Python virtual environment. The previous Claude-scheduled catch-up is disabled and retained only for rollback.

**Facts:** units + script installed on florida-signal-runtime, byte-identical to repo @ `dcbf6b4` (sha256 5c5f1b14… / e082d00a… / 447350bd…). Venv `/srv/grahamandgold/florida-signal/.venv-clerk-catchup` (Python 3.12.3, paramiko==5.0.0 pinned in ops/droplet/requirements-clerk-catchup.txt; no /home/andy/.local dependence). Unit hardened: User/Group=andy, WorkingDirectory, EnvironmentFile, NoNewPrivileges, PrivateTmp, ProtectSystem=full, ProtectHome=true, UMask=0027, TimeoutStartSec=900, Restart=no; timer Persistent=true + RandomizedDelaySec=120; next fire Mon 2026-07-20 ~14:11 EDT. Manual venv run: Result=success/exit 0, "Nothing to ingest; verified table matches server" (DB max business_date 2026-07-10 = server release; doc count 149,999 unchanged — no deletes/overwrites). Failure fixture (no env): systemd recorded exit-code/status=1. Journal contains zero secret strings. Install history disclosure: units first installed + manually run 12:59–13:00 EDT by operator via Codex (between shadow runs 4 and 5), one unit revision (User=andy) after first-start failure; hardened install from GitHub at ~13:12 EDT with operator authorization.

**SHADOW-GATE DISCLOSURE (for run-5 report):** An unrelated Clerk catch-up unit was installed and manually executed on the host between shadow runs 4 and 5. It uses disjoint schedules (14:10 vs 05:45), no shared locks (scorer: /tmp/florida-signals-shadow.lock), disjoint code paths and data outputs (scorer: SQLite/CSV, no EnvironmentFile). The change is disclosed; scorer evidence must NOT be described as occurring on an unchanged host.

**MASTER TO-DO:** Verify the next scheduled weekday Clerk catch-up (Mon 2026-07-20 ~14:11 EDT) and confirm the nightly health check reports its row-level result. Later: evaluate dedicated least-privilege service account; decide venv ownership pattern for other droplet jobs.

**RISK REGISTER:** (1) Service runs as the general `andy` production operator account (passwordless sudo on host); dedicated least-privilege account remains a future hardening item after full path/permission mapping. (2) RESOLVED: user-site paramiko dependence removed via pinned venv.

**Automation inventory changes:** Clerk SFTP catch-up → droplet systemd (production path); Claude task `broward-clerk-catchup-sync` DISABLED (emergency rollback only); nightly `regenerate-social-graphics` task now doubles as the Clerk health audit (alerts on timer inactive, failure, 3-day silence, or freshness lag).

**Status labels:** Acclaim: CURRENT DIGITALOCEAN EGRESS BLOCKED — alternative execution architecture unresolved. Social export: CURRENTLY MAC-LOCAL — server-side rendering migration not yet designed.

---
## Addendum — Acclaim preliminary pipeline off Claude (2026-07-19 pm)

**DECISION LOG:** The early Clerk pipeline uses twice-daily native Mac Acclaim collection with automatic missed-date backfill and later reconciliation against the authoritative Clerk SFTP feed. (Acclaim is Cloudflare-protected AND the DigitalOcean IP is blocked, so preliminary collection must run on the residential Mac via real Chrome; verified SFTP catch-up remains on the droplet.)

**Built (ops/mac/, GitHub-tracked):** acclaim_harvest.applescript (real-Chrome, Cloudflare-passing), acclaim_upsert.py (idempotent pre-filter insert, service role, preliminary label), acclaim_state.py (per-date state + backlog), acclaim_pull.sh (oldest-first backfill, resume, nonzero on fail, logs to ~/Library/Logs/florida-acclaim.log), com.floridasignal.acclaim.plist (LaunchAgent 12:00 + 19:00). Reconciliation: additive columns on broward_clerk_preliminary (verification_status, preliminary_first_seen_at, verified_business_date, verified_doc_type, reconciled_at, conflict_flag, conflict_note) + public.reconcile_clerk_preliminary() + pg_cron clerk-preliminary-reconcile daily 10:00 UTC.

**Proven 2026-07-19:** real July-13 records harvested through Chrome past Cloudflare; inserted to broward_clerk_preliminary labeled acclaimweb-public-search; re-run inserted 0 (idempotent); reconcile matched 1 → verified (official business date + doc type attached, first_seen + source preserved), flagged 1 date-conflict without merging; verified broward_clerk_records_doc untouched (149,963). LaunchAgent kickstart ran the backfill detached from Claude (weekends 0 records, weekdays backfilling oldest-first with state persisted).

**MASTER TO-DO:** Verify three independent scheduled Acclaim runs and one real preliminary-to-verified reconciliation (fixture proof done; awaiting an organic match when the SFTP feed catches up to a preliminary date).

**RISK REGISTER:** The preliminary Acclaim pipeline remains dependent on a powered-on Mac, logged-in user session, usable Chrome profile, and residential connection until a dedicated residential runner replaces it. (Also: first scheduled launch may prompt once for osascript→Chrome Automation permission.)

**Scheduling transition:** Claude task broward-sameday-recordings kept ENABLED as fallback until THREE independent successful LaunchAgent runs, then disable (not delete), label EMERGENCY ROLLBACK ONLY.

**Automation inventory delta:** Acclaim preliminary → native Mac LaunchAgent 12:00 + 19:00 (primary) + Claude task (active fallback); reconciliation → Supabase pg_cron 10:00 UTC; nightly health task now covers SFTP catch-up + Acclaim + social export.

**Status labels:** Acclaim: CURRENT DIGITALOCEAN EGRESS BLOCKED — runs on residential Mac (working). Social export: CURRENTLY MAC-LOCAL — server-side rendering migration not yet designed.

---
## Addendum — Acclaim completeness + authority checkpoint (2026-07-19 late)

### OPERATIONAL STATUS: **OPERATIONAL — COMPLETE DAILY COVERAGE** (proven on one heavy day; remaining backlog dates recollecting)

**Root cause of the "3-page halt" (resolved):** it was never a pagination bug. The Telerik grid's
default page size is **5 rows**; the harvester's 60-page safety cap therefore yielded exactly
60 × 5 = **300 rows** on every heavy date. The grid offers page sizes 25/50/100/150/200/250/**500**.
The harvester now sets **500** after each search, so a ~2,900-record day is **6 pages**.

**Pagination hardening (ops/mac/acclaim_harvest.applescript):** reads the displayed total and
computes expected pages; re-queries DOM after every AJAX refresh; advances via the **pager-scoped**
`.t-pager .t-arrow-next` (the date-picker has an identical arrow — previously ambiguous); waits for
the first row's instrument number to actually change (true AJAX completion, not a fixed sleep);
detects repeated pages and exits nonzero; honours a configurable cap but returns
`INCOMPLETE|pages|total|reason` when the cap is hit. Returns `OK|pages|total`, `EMPTY|0|0`, or
`INCOMPLETE|...`. `acclaim_pull.sh` marks a date **done only when** status=OK **and** rows ≥ displayed
total (or a verified EMPTY), otherwise records `incomplete`, sets a nonzero exit, and stops so the
next run resumes that date.

**Heavy-day proof — 2026-07-13:** Acclaim displayed **2,909 records / 6 pages**; processed **6/6
pages**; extracted **2,909 rows**; **2,909 unique instruments**; 0 duplicates; 0 malformed;
0 missing-field rows; first instrument `120977412`, last `120980320`; inserted **2,609 new**
(300 already present from the earlier partial run, correctly deduped); **rerun inserted 0**.
No result cap or partitioning required — full retrieval is possible via page size 500.

**Idempotency bug found and fixed during proof:** the existing-key pre-filter hit PostgREST's
1,000-row response cap, so a rerun attempted duplicate inserts (HTTP 409). `acclaim_upsert.py` now
pages the lookup with `Range` headers. Post-fix rerun: "all 2909 harvested rows already present".

**Phase 3 correction:** 2026-07-14/15/16/17 (300 rows each under the old cap) were reset to
`incomplete` in state and are being fully recollected oldest-first by the LaunchAgent; 07-11/07-12/
07-18 are verified 0-record weekend dates. Partially harvested dates are **not** marked complete.

### DECISION LOG
Temporarily approve `com.floridasignal.acclaim` as a sixth Florida Mac agent solely for twice-daily
preliminary Acclaim collection until a dedicated residential runner is deployed and verified.
(The five previously approved Florida Mac agents remain enabled and untouched.)

### MASTER TO-DO
Move the Acclaim LaunchAgent to a dedicated residential runner after three complete scheduled runs
and verified reconciliation.

### RISK REGISTER
The preliminary same-day pipeline remains dependent on the Mac, logged-in user session, Chrome,
Apple Events permissions, and complete Telerik pagination.

### Mac agent inventory (6)
1–5. Previously approved Florida Mac agents (Claude scheduled tasks) — unchanged, still enabled.
6. **`com.floridasignal.acclaim`** — LaunchAgent, `~/Library/LaunchAgents/`, twice daily 12:00 + 19:00,
   ExecStart `ops/mac/acclaim_pull.sh`, logs `~/Library/Logs/florida-acclaim.log`, state
   `~/Library/Application Support/FloridaSignal/acclaim_state.json`.
   Rollback: `launchctl bootout gui/$(id -u)/com.floridasignal.acclaim` + re-enable Claude task
   `broward-sameday-recordings` (kept ENABLED as fallback until three complete scheduled runs).

### Supabase source-of-truth
Live reconciliation objects are now tracked at `supabase/migrations/` (001 table+policy+indexes,
002 reconciliation columns+function+pg_cron, README inventory). Verified live-vs-GitHub: columns,
indexes, single SELECT policy, 0 triggers, cron `0 10 * * *` active invoking only
`reconcile_clerk_preliminary()`; tracked SQL contains **no** writes to authoritative
`broward_clerk_records_*` tables and **no** secrets. Rollback SQL documented, not executed.

### Phase 3 recollection result (verified 2026-07-19 14:06 EDT)
Every previously-partial date was fully recollected, each matching Acclaim's displayed total exactly:

| Record date | Rows | Displayed total | Pages | Status |
|---|---:|---:|---:|---|
| 2026-07-11 (Sat) | 0 | 0 | 0 | done (verified empty) |
| 2026-07-12 (Sun) | 0 | 0 | 0 | done (verified empty) |
| 2026-07-13 | 2,909 | 2,909 | 6/6 | done |
| 2026-07-14 | 3,007 | 3,007 | 7/7 | done |
| 2026-07-15 | 2,475 | 2,475 | 5/5 | done |
| 2026-07-16 | 2,877 | 2,877 | 6/6 | done |
| 2026-07-17 | 2,501 | 2,501 | 6/6 | done |
| 2026-07-18 (Sat) | 0 | 0 | 0 | done (verified empty) |
| 2026-07-19 (Sun, today) | 0 | — | 0 | **incomplete** — `grid_never_loaded`; correctly NOT marked complete |

DB totals: **13,769 preliminary rows** (= 2909+3007+2475+2877+2501, no duplicates), leading date
**2026-07-17 vs verified 2026-07-10 — a 7-day lead**. Authoritative `broward_clerk_records_doc`
unchanged at 149,963 throughout.

**One open item (honest):** today's date (Sunday 07-19) returns `grid_never_loaded` rather than a
verified `EMPTY`, so the runner refuses to mark it complete and exits nonzero — conservative and
correct per the rules, but it means a genuinely record-less current day stays in the backlog until
the empty state is confirmable. Empty-state detection for the current/no-result day is the single
remaining refinement; it does not affect completed-date integrity.

---
## Addendum — Acclaim empty-state fix + cleanup closure (2026-07-19 ~14:20 EDT)

### Empty-state detection (final refinement)
Acclaim's true zero-result signature is a **visible leaf element whose text is exactly
"No Results to Display"** (confirmed in the live DOM); `.t-status-text` matching `of 0` is accepted
as an equivalent signal. The harvester now resolves five distinct states in priority order:
**CF** (title matches Attention Required / Just a moment / Access denied) → **GRID** (a
`#SearchGridContainer` row containing a 7+ digit instrument) → **EMPTY** (positive signature above)
→ **WAIT** → timeout. `EMPTY|0|0` is returned **only** on positive detection; unresolved states
return `INCOMPLETE|0|0|<reason>` (`cloudflare_block`, `timeout_no_result_state`, `not_ready_*`) with a
nonzero exit. Emptiness is never inferred from absence.

**Tests:** empty 2026-07-19 → `EMPTY|0|0`, marked **done**, agent exit 0, backlog now `[]` ·
forced failure (invalid-route copy in /tmp) → `INCOMPLETE|0|0|not_ready_WAIT`, **0 rows written** ·
heavy 2026-07-13 regression → `OK|6|2909`, 2,909 rows. Commit `db5b483`.

**Sunday 2026-07-19 is a valid zero-record day** (Acclaim itself reported "No Results to Display";
07-11/07-12/07-18 behaved identically). It is not a scraper failure and is recorded as complete.

### ACTION LOG — cleanup (2026-07-19)
Deleted **verified manual test artifacts only**, total **1,463,735 bytes**:
`/tmp/fs_heavy.ndjson` (725,255) · `/tmp/fs_heavy.status` (26) · `/tmp/fs_acclaim_test.ndjson` (2,603) ·
`/tmp/fs_acclaim_test.log` (1,420) · `/tmp/fs_empty.status` (21) · `/tmp/fs_fail.status` (40) ·
`/tmp/fs_fail_harvest.applescript` (9,088) · `/tmp/fs_regress.ndjson` (725,255) · `/tmp/fs_regress.status` (27).
Each deletion is timestamped in `~/Library/Logs/florida-acclaim.log`.

**Verification basis:** 2026-07-13's rows are confirmed present in Supabase (2,909 unique instruments)
and a rerun of `acclaim_upsert.py` reported "all 2909 harvested rows already present" — nothing was
pending upload. **Confirmed NOT removed:** `acclaim_state.json` (1,956 B), `florida-acclaim.log`,
`florida-acclaim.launchd.log`, `~/.florida_signal_supabase_env` (all verified present after cleanup);
no incomplete/failed-run artifact existed or was touched.

### Retention policy (as implemented — deliberately minimal)
- **Log rotation only:** `florida-acclaim.log` rolls at **5 MB**, retaining **3** copies (`.1/.2/.3`).
- **Per-date NDJSON:** unchanged behaviour — deleted by `acclaim_pull.sh` only after a date reaches
  `done` (harvest OK/EMPTY **and** rows ≥ displayed total, i.e. verified Supabase insertion).
  Files for an incomplete/failed date are **retained** for retry.
- **No 7-day raw-file retention system was added.**

---
## Addendum — Live Signals Map audit (Phase 1) + safety stop (2026-07-19 late)

### DECISION LOG
The Live Signals Map is the first public integration target and the product spine for Florida Signal.
It will display curated, explainable Signals rather than raw source-record dumps.

### MASTER TO-DO
Connect mapped permit, Broward FAA, FDEP and selected geographically verified Clerk signals to the
website through one versioned Signal contract, then feed editorially meaningful Signals into the
candidate registry.

### VERIFIED ARCHITECTURE (behavior-checked, not inferred)
- **Public map:** `buildMap()` in `app.js` binds to `#full-map` (Neighborhoods `/fort-lauderdale/neighborhoods/#full-map`), `#home-map`, `#data-room-map`. Leaflet `L.map`, `preferCanvas:true`.
- **Marker source = permits ONLY.** `state.records` = **700** newest current-month geocoded permits (`permits` table, `lat/lon not null`, limit 700). FAA/FDEP/Clerk/preliminary appear **nowhere** on the map or in `app.js`.
- **"Layers" are permit color-codes, not sources:** `markerColor()` → Demolition `#ff6d3a`, Storm `#1767ff`, $500K+ `#071b32`, default `#00b8dc` — all computed from permit text/valuation.
- **No clustering.** `drawMarkers()` uses a plain `L.layerGroup` of `L.circleMarker`; no `markercluster`. Heat overlay exists (`L.heatLayer`).
- **Only filter = storm lens** (`activeMapRecords()`). No source / date-range / preliminary-vs-verified / municipality filters.
- **Signal Card = permit popup** (`mapPopup()`): permit_type, address, declared value, applied_date, permit_number, Street/Satellite/City-source links, Share, Add-to-report.
- **Row limits:** 700 mapped, 40 high-value, 24 search, 1000×N application-date counts. Publishable Supabase key + RLS.

### SOURCE DATA READINESS (verified counts + coordinates)
- **FAA `faa_oeaaa`:** 472 Broward, **142 Broward cranes**, all 472 with WGS84 lat/lon inside the Broward box (e.g. crane `26.0161,-80.2139`). ✅ map-ready.
- **FDEP `fdep_erp`:** **8,309**, all with WGS84 lat/lon inside the Broward box (e.g. `26.0826,-80.1163`). ✅ map-ready.
- **Preliminary Clerk `broward_clerk_preliminary`:** 13,769 rows — **NO coordinates or folio**; only names/instrument/doc_type/legal text. Cannot be mapped without a folio→parcel-centroid or address geocode join (not present). ⚠️ not directly map-ready.
- **Permits:** current map source, geocoded. ✅

### SAFETY STOP (Phase 7) — the editorial registries are the frozen scorer's ledger
`brief_candidate_registry` (0 rows) and `brief_publication_registry` (0 rows) are **not** blank generic
review queues. Their columns (`story_key, entity_key, module, folio_set, event_fingerprint, figures_hash,
source_fingerprint, times_seen, drop_reason, run_id` / publication delivery tracking) show they are the
**shadow scorer's fingerprint-based promotion + dedup + delivery ledger** — part of the weekly signal
packet pipeline that is **FROZEN under the five-run editorial gate (run 5 completes Mon 2026-07-20)**.
Writing map-derived signals into these tables would contaminate the scorer's ledger and risk the open
gate. Per Phase 7 and the scorer-frozen rule, I am stopping to explain before writing to them.

---
## Addendum — Live Signals Map + editorial queue (2026-07-19 evening)

### DECISION LOG
The Live Signals Map is the first public product spine for Florida Signal. Existing permit, FAA and
FDEP records are normalized into a shared Signal model (SignalV1) before display or editorial review.
Map-derived editorial candidates use a separate review queue (`map_signal_candidates`) and do NOT write
into the frozen shadow scorer registries. The Data Desk is the inspection surface. The Data Wire CMS is
the editorial review surface. No Signal publishes automatically.

### MASTER TO-DO
- Connect geographically verified Clerk events after a reliable parcel/address relationship exists
  (the deferred `fromClerk` resolver interface is already in place and manufactures no coordinates).
- Connect approved Signals to the Daily Intel Brief after the review flow is proven.
- Reconcile `map_signal_candidates` with the broader scorer architecture only after the five-run gate
  closes and the interface is explicitly reviewed.
- Build the click-to-approve Signal review UI in the Data Wire CMS (transitions currently service-role).

### RISK REGISTER (verified in this build)
- Raw source volume can overwhelm the map without bounded loading and clustering — mitigated: per-source
  caps (permits 700 / FAA 300 / FDEP 400), date-window filter, marker clustering.
- Poor geographic links can create misleading markers — mitigated: Clerk mapping deferred; a
  null-coordinate bug (`Number(null)===0` placing records at 0,0) was found by tests and fixed.
- Preliminary records can be misunderstood if not visibly labelled — mitigated: PRELIMINARY badge on
  every card; CONFLICT/NEEDS_REVIEW are never public-eligible.
- Generated wording can overstate filings — mitigated: deterministic evidence + mandatory caveats
  ("application", "filing", "does not prove work has started", "does NOT mean construction has started").

### What shipped
`signals.js` (SignalV1 model, permit/FAA/FDEP adapters + deferred Clerk resolver interface, eligibility
ruleset, deterministic intelligence pass, bounded read-only service); map integration in `app.js`
(clustered multi-source Signal layer, source/verification/date filters, legend, Signal Cards, Reset-view
control on every map, enlarged centered brand lockup linking to thefloridasignal.com for embeds);
`tests/signals.test.js` (45 assertions, all passing); `supabase/migrations/20260719_003_map_signal_candidates.sql`.

---
## Addendum — Complete bounded data discovery (2026-07-19 night)

### DECISION LOG
Florida Signal complete-data support means all eligible records are discoverable through bounded,
filterable retrieval. It does NOT mean loading entire source tables into the browser. The public map
displays curated Signals; the Data Room provides deeper record access; the Data Wire CMS controls
editorial review. Existing scoring logic must be inventoried and reconciled before new scoring rules
are introduced. Meeting agendas, packets, staff reports, minutes and exhibits are a core Signal source family.

### Complete counts (server-verified 2026-07-19)
| Source | Total | Geocoded | Eligible+geocoded |
|---|---:|---:|---:|
| Permits | 127,945 | 103,864 | **14,884** |
| FAA (Broward) | 472 | 472 | 472 (142 cranes) |
| FDEP | 8,309 | 8,309 | 8,309 |

The previous 700/300/400 fixed samples are retired. Retrieval is now viewport-bounded, date-filtered,
source-filtered, deterministically ordered, capped at 600 rows/request, debounced (420ms) on pan/zoom,
with stale-response cancellation via a sequence guard and dedupe by `signal_id`.

### Counts are now separated honestly
Readout distinguishes **in this view / loaded / match current filters / eligible across Broward**.
`count=exact` on `permits` times out (Postgres 57014, 127k rows), so counts use `count=planned`
(planner estimate) and are labelled **approx.** Row queries are exact.

### RISK REGISTER (verified)
- Fixed sample limits can falsely appear to represent complete coverage — retired; counts now labelled.
- A failed source request can falsely appear as zero records — mitigated: failures render as
  "Temporarily unavailable … this is a source error, not zero records" and never as 0.
- Raw full-table map loading can overwhelm browsers — mitigated: 600-row cap + clustering + bbox.

### MASTER TO-DO
- Complete reliable geographic linkage for selected Clerk records.
- Complete meeting-document ingestion after existing logic and municipality coverage are inventoried.
- Implement controlled source-health, reconciliation, Signal-refresh and publication-freshness loops.
- Finish CMS review UI actions (approve/hold/reject currently service-role).

---
## Addendum — Parcel authority import + Clerk linkage by document type (2026-07-19, late)

### DECISION LOG
Broward parcel/folio identifiers are canonical **12-character ALPHANUMERIC** strings (e.g. `484306BH0010`).
Letters and leading zeros are significant. **Digits-only normalization is prohibited** — it strips letters
and collapses distinct parcels (measured: 1,295 collision groups spanning 5,056 folios).
The prior **1,096 / 7.9%** linkage figure is **SUPERSEDED — PRESERVED FOR HISTORY**: it contained false
collisions. The corrected pre-import baseline was **737 exact matches (~5.0%)**.

### Import state (verified)
Official source count **554,358**. Loaded **404,082 parcels (72.9%)** into `broward_parcel_geography`.
Zero null coordinates. Zero duplicate source OBJECTIDs (rows = distinct OBJECTIDs at every check).
Import runs recorded in `broward_parcel_import_runs`; **1 run status=COMPLETE** (tail range only —
NOT whole-county coverage). Remaining offsets still need sweeping before a whole-county COMPLETE
can be claimed. **No recurring parcel schedule was created.**

### Clerk linkage by document type — STRUCTURAL LIMIT FOUND
| Doc type | Instruments | With valid folio | Mappable | Unique parcels |
|---|---:|---:|---:|---:|
| **D — deeds** | 15,487 | 15,137 | **7,903** | 7,592 |
| EAS — easements | 502 | 471 | 386 | 379 |
| TSD | 1,897 | 51 | 23 | 11 |
| NOT | 2,225 | 27 | 17 | 16 |
| **M — mortgages** | 10,357 | **0** | **0** | 0 |
| **LIE — liens** | 7,388 | **0** | **0** | 0 |
| **LP — lis pendens** | 1,281 | **0** | **0** | 0 |
| **FJ — final judgments** | 14,669 | **0** | **0** | 0 |
| AFF / CP / CPX / DC / CMV / FJX | 17,995 | 0 | 0 | 0 |

**Root cause:** the Clerk's `lgl-ver` (legal) file carries `parcel_id` almost exclusively for
**deed-type** instruments. Mortgages, liens, lis pendens and judgments have **no legal/parcel rows at
all** in the source. This is a **source-structure limitation, not a normalization or parcel-coverage
problem** — no amount of parcel geography fixes it.

### RISK REGISTER (verified)
- Digits-only folio normalization collapsed distinct alphanumeric parcels and produced false matches.
  **Persisted impact: NONE** — the rule existed only in read-only audit SQL (verified: 0 Clerk rows in
  `map_signal_candidates`, 0 reconciled preliminary rows, 0 conflict rows). No production correction needed.
- Mortgage/lien/lis-pendens mapping cannot be achieved through the Clerk legal file; it requires a
  separate verified relationship (e.g. instrument→instrument links in `broward_clerk_records_link`,
  or BCPA per-folio lookup). Unverified as of this checkpoint.

### MASTER TO-DO
- Finish sweeping remaining parcel offsets until whole-county page coverage is provably COMPLETE.
- Investigate `broward_clerk_records_link` as a verified path from mortgages/liens/LP to a deed's parcel.
- Audit Michigan and Florida parcel/folio normalization paths separately — identifier rules do not transfer.
- Stratified 50-record quality verification before any Clerk record becomes map-eligible.
