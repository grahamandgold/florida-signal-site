# Florida Signal — August 11 night handoff

**Current working authority for the next chat · recorded August 11–12, 2026**

Read this file first, then `SYSTEM_STATE_2026-08-11.md`, `EDITORIAL_LOOP_RUNBOOK.md`,
`LIVE_DATA_OPERATIONS_HANDOFF.md`, `cms/ADR-002-live-desk-evidence-first-workspace.md`, and
`AUTOMATION_AND_AGENT_INVENTORY_2026-08-11.md`. Older July handoffs are historical evidence, not current operating
instructions.

## One-minute state

- Production collection is operating. The authoritative Broward Clerk SFTP feed is source-delayed
  through August 6; the separate Acclaim preliminary lane reached August 11 and remains labeled
  preliminary until exact reconciliation.
- The native Mac LaunchAgent `com.floridasignal.acclaim` is the **only same-day Broward writer**.
  It is loaded, last exit is `0`, runs hourly, at login, and at 00:30, 12:00, 19:00 and 22:30 local.
  It inserted 2,056 August 11 rows at 15:10 local. The Claude duplicate is paused and retained only
  as a reversible emergency fallback.
- The private Data Wire has a new local Live Desk, real production-timer strip, exact Data Explorer
  search, an evidence-first Candidate review, a reporting Investigation Kit, an early-intelligence
  radar and a Legistar Agenda Watch. These are local branch changes and are not a claim that every
  source has a completed detector.
- Eight Transfer → Permit Candidates are evidence-ready in the private queue; 150 older queue rows
  remain blocked by the evidence gate. Approval records an editorial decision only; it does not
  publish.
- The public website still needs the separate mobile simplification/content-model implementation.
  Claude Design produced a concept, not production code. Treat every number in that concept as
  illustrative unless reconnected to a verified endpoint.
- No autonomous model publishes Florida Signal. Collectors and timers are deterministic jobs;
  Codex/Claude audits are review work. AI research produces leads, never evidence or publication.

## What changed tonight

### Same-day Broward recordings

The same-day path is intentionally independent of Claude:

1. `ops/mac/acclaim_pull.sh` obtains the verified SFTP floor, drives the official Acclaim public
   search in the logged-in Chrome session, and sends harvested rows to the preliminary table.
2. `ops/mac/acclaim_targets.py` now rechecks the current date on every post-noon run even after that
   date previously completed. Acclaim can add instruments during the day; a single completed pass
   is not treated as the final daily count.
3. `ops/mac/acclaim_upsert.py` pre-filters exact `(record_date, instrument_number)` keys, so hourly
   refreshes add only new instruments and do not duplicate or overwrite verified records.
4. A long offline backlog reserves one target slot for the current day while the remaining slots
   catch up oldest-first.
5. Before noon, the forming current day is still excluded. A current-day empty result is never
   final. State and raw source fields remain preserved.

The first forced refresh with this fix ran at 21:49 local and correctly targeted August 11. Broward
returned its recurring disclaimer, so the run exited as `SOURCE_WAIT` with no row or state damage.
The official Disclaimer page was opened in Chrome for a human acceptance; the hourly retry remains
armed. Do not describe the item clock as advanced until a later run reports `status=OK`.

Tests added in `ops/mac/test_acclaim_resilience.py` prove current-day refresh, backlog slot
reservation, past-date skipping, cached verified-floor recovery and hourly/login scheduling.

### Claude scheduled tasks

The scheduled-task audit found three historical tasks:

| Task | Disposition | Reason |
|---|---|---|
| `broward-sameday-recordings` | **Paused; do not delete** | Native LaunchAgent is proven primary and a second writer is unnecessary. Keep only for emergency rollback. |
| `florida-shadow-run-review` | **Paused** | Temporary July five-run gate; instructions say to end after run 5, but it continued daily with repeated errors/skips. |
| `regenerate-social-graphics` | **Paused until redesigned/replaced** | Repeatedly failed on its old environment and would regenerate obsolete July graphics. Health monitoring belongs in deterministic checks, not this stale design task. |

Pausing a Claude schedule never pauses the production droplet timers, Supabase jobs, GitHub monitor,
public API or the native Acclaim LaunchAgent.

The 21:40 graphics run started during this audit. It was stopped and the schedule was then verified
off. Before it stopped, it touched all ten tracked files under `social/graphic-desk/*.png`. Keep
those incidental binary changes out of the intended commit unless a deliberate visual/data review
approves them.

### Data Wire / Live Desk

Implemented through merged PR 10 from branch `codex/local-desk-auto-unlock`:

- `cms/home.html` is the Live Desk front door; the emblem/wordmark links home.
- `cms/desk-shell.js` and `cms/desk-shell.css` provide one shared navigation and a real “Next in
  pipeline” strip read from production systemd timers. A scheduled time is not presented as proof
  that a source advanced.
- `cms/server.py` adds read-only private endpoints for the timer schedule, early-intel source lanes
  and Agenda Watch. It never starts a production job.
- The early-intel order is decisions/agenda → company formation → capital/property → regulatory →
  permits/inspections. This keeps permits in their proper later-stage role.
- Agenda Watch reads exact Legistar item records and public attachment links, removes boilerplate,
  supplies neutral “why developers may care” language and requires stakeholder/both-sides follow-up.
  An item is a verification lead, not a Signal.
- `cms/review.html` shows one Candidate at a time, keeps the sealed evidence packet visible, separates
  supported facts from unknowns and hides final approve/reject controls in mobile field mode.
- Its Investigation Kit derives Street View, satellite, Maps and parcel links from the actual record.
  News, open-web, Sunbiz and Grok prompts are reporting aids only. Useful results must be opened,
  verified and attached with provenance.
- `cms/data.html` now uses exact indexed prefixes (`permit:`, `folio:`, `instrument:`, `addr:`,
  `license:`, `asn:`), avoiding the broad wildcard queries that caused timeouts.
- The Finder app at `/Users/gillfillan/Desktop/Florida Signal Data Wire.app` is generated from tracked
  source, code-signed, opens the Live Desk and uses the canonical Florida Signal emblem.
- Its updater strict-verifies the staged bundle, removes transient Finder metadata on placement and
  verifies the final Desktop signature without treating Finder's empty xattr as app corruption.

### Accuracy, schema and database gate

- The working content model is **Record → Candidate → Signal → Story/Brief**. Raw permits and machine
  joins are never called Signals publicly.
- The review queue now has a generated/indexed `evidence_ready` gate. The migration is
  `supabase/migrations/20260812010713_review_queue_evidence_readiness.sql` and is already applied to
  the production Supabase project.
- A server-side approval request requires a confirmation and recomputes evidence readiness. It
  records Gate 1 only and never publishes.
- Raw source text, original URLs/IDs, event clocks, system clocks, confidence, missing joins and
  disagreements remain visible. Missing data is not inferred.
- Private Legistar inventory observed tonight: 17 events, 486 event items, 45 watch matches and 242
  items carrying attachment arrays. This is a historical/private corpus, not proof that every
  upcoming public meeting currently has a posted agenda.
- Agenda Watch now prints its own coverage: the actionable item events currently span May 5–July 2,
  and the item index was last observed July 23. Its 267 public attachment links are therefore useful
  historical reporting material, not a claim of current upcoming-agenda coverage.
- Sunbiz currently lacks a dependable public event/system clock. Never label it current or claim an
  entity match without exact evidence.

### Product and design direction

- Mobile becomes a field instrument: Today, Near Me/Map, Search, Saved and Brief; full-screen map;
  compact freshness; one editor-cleared Signal; no automatic newsletter modal interrupting work.
- Desktop becomes a research workstation: broad map/results split, advanced filters, comparisons,
  evidence/timeline tools and persistent Field Brief.
- Public home becomes shorter and newsletter-led after proving value. Current permit cards should
  be labeled filings until they clear the Signal gate.
- Preserve diagrams, but each diagram answers one journalistic question, shows source/window/sample/
  verification and links to the evidence/table alternative.
- The canonical full-color Florida emblem is a signature. Never add an arrow, stretch it, merge it
  with an action icon or replace it with a decorative low-opacity legacy mark.
- The public byline/author identity remains role-based until explicitly changed. Do not add a
  personal name to public copy, metadata, screenshots or generated graphics.
- `CLAUDE_DESIGN_VISUAL_AUDIT_2026-08-11.md` records the completed Cowork/Chrome visual audit. Cowork
  used Claude Design's `design-critique`, `accessibility-review` and `ux-copy` plugin skills across
  all seven product views at desktop and narrow widths. It changed nothing during the audit.
- The resulting cleanup brief was completed in the existing Claude Design project. It edited the
  Design prototype only; it did not publish, export, schedule, add automation or touch production
  code. The exact canonical emblem was loaded from the repository asset and verified in the masthead
  and Field header. The final narrow-canvas proof exercised the mobile breakpoint.
- Audit P0s: broken emblem asset, colliding Candidate timeline, model identities exposed while Lab
  blind mode is on, illustrative data presented with live-looking clocks, and broken narrow layouts.
- Chrome was left narrow by the audit extension; that browser-window size is not a product change.
  The Design canvas itself reports 100% zoom after the audit handoff.

## Verification completed

- `python3 -m unittest ops/mac/test_acclaim_resilience.py` — 7 passing.
- `python3 -m unittest tests/test_cms_server.py` — 6 passing in the latest CMS run.
- Playwright `tests/browser/data-wire.spec.js` — 2 passing at desktop and 390-pixel checks in the
  latest browser run.
- Desktop app bundle identifier, code signature and Live Desk launch were verified after refresh.
- Production LaunchAgent check: `com.floridasignal.acclaim`, last exit `0`; August 11 insertion and
  subsequent hourly runs are present in `~/Library/Logs/florida-acclaim.log`.

PR 10 was squash-merged into `main` as `6ef7d39e1f8431a829f1a0332ddc631788ad37f1` after the local
checks. GitHub's **Public site health** workflow then passed its unit and browser jobs. That workflow
name describes the repository safety check; it did not publish the Claude prototype or expose the
loopback-only Data Wire runtime.

## Known gaps / next exact work

1. Translate the reviewed Claude Design concepts into production code deliberately; never copy its
   illustrative records, scores or clocks into the real desk.
2. Refresh the Desktop Data Wire app and rerun the Python/browser suite after production UI changes.
3. Review every future diff; stage only intended tracked work. Do **not** stage raw/untracked Broward text
   dumps, `FABLE_ANALYSIS_2026-07-20/`, `mailchimp/`, `output/` or `chunk_*.txt`.
4. Do not stage the ten social PNGs touched by the stopped 21:40 Claude run without a separate
   visual/data approval.
5. Treat the Claude Design file as a reviewed concept, not as a deployable artifact. Recheck security,
   responsive behavior and editorial gates in the real CMS implementation.
6. Then implement the public mobile/content-model P0: remove the 10-second signup modal, fix clipping
   and NHC visual failure, unify navigation, simplify repeated actions and relabel raw “signals.”
7. Add public privacy/correction routes and a real editor-cleared sample brief before paywall work.
8. Later build bounded multi-model research as an explicit graph with deterministic checks,
   independent review, durable state, stop rules and human gates. Never send database credentials or
   the unrestricted database to a model.

## Fast recovery commands

```sh
launchctl list | rg 'com\.floridasignal\.acclaim'
tail -80 "$HOME/Library/Logs/florida-acclaim.log"
launchctl print gui/$(id -u)/com.floridasignal.acclaim
python3 -m unittest ops/mac/test_acclaim_resilience.py
bash ops/launch_local.sh
curl -s http://127.0.0.1:8788/api/health
curl -s https://api.thefloridasignal.com/api/data-health
git status --short
```

Do not use a `file://.../cms/review.html` tab. Open the signed Desktop app or
`http://127.0.0.1:8788/`; loopback auto-unlock is deliberately unavailable to a file URL.
