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
