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
- The product boundary is now explicit: **public Florida Signal** is the reader/newsletter site;
  **Florida Signal Newsroom** is the private CMS and intelligence workspace. Live Desk is the
  Newsroom home, not a separate site.
- The private Newsroom now has a shared high-end shell, real production-timer strip, exact Data
  Explorer search, evidence-first Triage, a reporting Investigation Kit, an early-intelligence
  sequence, Legistar Agenda Watch and the gated Brief builder. These are real local pages backed by
  private endpoints, not a claim that every source has a completed detector.
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
- Agenda Watch now says its entity scope plainly: **City of Fort Lauderdale only**. The first section
  shows upcoming official-calendar rooms with date, time, location and whether an agenda is actually
  posted. Historical cards name the government body and expose the official agenda PDF, exact
  Legistar meeting item and packet-attachment count before the collapsed reporting checklist.
- The state-capitol/Florida Legislature lane is separate. No LegiScan connector or credential was
  found in this repository during the August 11 audit; locate and verify the existing API setup
  before adding bills, committees or Tallahassee actions to the Newsroom.
- `cms/review.html` shows one Candidate at a time, keeps the sealed evidence packet visible, separates
  supported facts from unknowns and hides final approve/reject controls in mobile field mode.
- Its Investigation Kit derives Street View, satellite, Maps and parcel links from the actual record.
  News, open-web, Sunbiz and Grok prompts are reporting aids only. Useful results must be opened,
  verified and attached with provenance.
- `cms/data.html` now uses exact indexed prefixes (`permit:`, `folio:`, `instrument:`, `addr:`,
  `license:`, `asn:`), avoiding the broad wildcard queries that caused timeouts.
- Data Explorer now starts with the complete source catalog above its table. The live connection
  audit reports 15 readable private datasets, zero empty and zero unavailable. The default table is
  same-day preliminary Clerk—not permits—and the catalog visibly separates decisions, companies,
  property/capital, environmental/airspace and execution sources.
- The Sunbiz resolver was not empty: service-role verification found 505 exact-match rows hidden by
  the intended anonymous RLS boundary. `/api/admin/sunbiz-entities` now proxies those rows only to
  the authenticated local Newsroom; the service key is never exposed and no fuzzy match is added.
- The Finder app at `/Users/gillfillan/Desktop/Florida Signal Data Wire.app` is generated from tracked
  source, code-signed, opens the Live Desk and uses the canonical Florida Signal emblem.
- Its updater strict-verifies the staged bundle, removes transient Finder metadata on placement and
  verifies the final Desktop signature without treating Finder's empty xattr as app corruption. It
  now also restarts an already-running Newsroom process after a bundle refresh so new backend routes
  cannot be paired with stale code held in memory.

### Newsroom implementation from the reviewed Claude Design

The reviewed concept has now been translated into the real private CMS on branch
`codex/newsroom-claude-design`. This is an implementation, not a visual mock:

- one `FLORIDA SIGNAL / NEWSROOM` shell and exact canonical emblem link every section back to Live
  Desk;
- the full-color emblem now has a compact light contrast field in the navy header, keeping the
  dark Florida silhouette legible without redrawing, recoloring or adding anything to the mark;
- the desktop Newsroom header is fixed to the viewport instead of relying on a sticky child trapped
  by the short shell container, so it remains coherent while long agenda/data views scroll;
- Live Desk leads with real queue/source counts, the strongest evidence-ready Candidate and the
  actual S1–S5 early-intelligence lanes;
- Agenda Watch is a dedicated page for real Legistar items, attachments, coverage windows and
  balanced reporting prompts;
- Brief, Data Explorer and Triage retain their existing APIs, security boundary and editorial
  gates while adopting the same navigation and responsive visual system;
- the source-status panel rejects null, zero and pre-2000 timestamps rather than manufacturing a
  1969 clock;
- all five Newsroom views fit a 390-pixel page viewport; the dense Explorer table remains an
  intentional internal horizontal scroller;
- the Live Desk sequence and source-status dialog also use an intermediate-width layout while the
  desktop sidebar is present. Stage names have reserved columns and source clocks reflow before
  they can overlap titles or descriptions;
- no Claude sample record, score, model identity or live-looking illustrative timestamp entered
  production code.

The public site was deliberately not reskinned in this branch. Its mobile simplification,
newsletter journey and field-tool redesign are the next separate product phase.

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
- Sunbiz has private exact-match resolver rows and a dependable resolver system clock. It still
  lacks a dependable public event clock because `date_filed` is not populated in those rows. Never
  infer that event clock or claim an entity connection beyond the exact private receipt.

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

### Signal Machine control plane and Brief bank · August 12 continuation

The private Newsroom now contains the implementation foundation for the cross-source Signal
Machine workflow described in `SIGNAL_MACHINE_INTEGRATION_2026-08-11.md`:

- Live Desk carries a permanent warning that only the permit/execution family is shadow-ranked.
  Agenda, Sunbiz, capital and regulatory sources may be readable while their Candidate detectors
  remain absent; source health is never presented as detector coverage.
- The visible responsibility chain names collectors, deterministic normalization, detector gaps,
  v2.6 shadow ranking, an unconnected same-evidence AI consistency check, the human editor and the
  unconnected Mailchimp sender. AI can only flag contradictions or lower confidence; it cannot add
  sources, corroborate, score, approve or publish.
- The discovery barometer uses bounded 1.00×–2.00× preview multipliers. Saving requires a name and
  rationale, creates only `status=draft / backtest_status=not_run`, writes an audit row and has no
  activation endpoint or production effect.
- Agenda Watch and evidence-ready Triage items can be saved to a weekday/date Brief bank. An exact
  date controls the weekday; a weekday-only choice resolves to its next occurrence. Stable source
  identity prevents duplicate rows while allowing an editor to change the edition slot.
- Every bank row keeps its direct source, immutable JSON snapshot hash, confidence value or explicit
  absence reason, passed gates, rules, source lane, machine/profile lineage and audit timestamps.
  The bank opens only an unverified module draft and cannot approve, publish, schedule or send.
- Agenda cards now say `Raw public record · not scored · not a Signal`; “send” language was replaced
  with “save” so the staging action cannot be mistaken for email delivery.
- Brief drafts now carry a stored writing profile: AP style, headline approach, jargon treatment
  and required ethics rules for attribution, uncertainty, anti-hype, right of reply, conflicts and
  no invented context. The default is `Catchy but precise`, not clickbait, and the role-based byline
  remains intact.

### Signal Machine live-runtime truth · August 12, 12:30 a.m. ET

- The production `florida-signals-shadow.timer` is active, daily at 5:45 a.m. ET; next fire was
  independently observed for August 12 at 5:45 a.m.
- The shadow wrapper explicitly uses `--since yesterday`. This is a calendar-date gate (yesterday
  through the run date), not a rolling 24-hour interval and not a historical trend window.
- The August 11 engine 2.7.0 artifact loaded 22,895 permit-anchored candidates and returned six
  MAIN items: demolition, structural, property-record and paving permits. This explains the weak
  editorial output; the machine is still permit/execution-first.
- Historical context is attached only after a current trigger and is limited to folio permit
  counts/value/date span, up to two sales, owner permit count, code cases and related permits. No
  neighborhood baseline, trajectory, seasonality, predictive trend or full cross-source history
  engine exists.
- The shadow job cannot publish or write production signal tables. The production signal writer
  remains paused/frozen.
- External Claude/Grok/Gemini reviews are not connected to runtime. A future advisory AI layer
  requires source-locked packets, citations, model/prompt/version receipts and a permanent human
  Candidate -> Signal gate.

### Newsletter-first launch decision package · August 12 evening

The founder identified a Sunday edition as the clearest way through product paralysis. A new
decision package is saved under
`deliverables/florida-signal-decision-package-2026-08-12/`:

- `MULTI_AI_PRODUCT_DECISION_PROMPT.md` — a source- and clock-qualified prompt for independent AI
  review, including founder runway, South Florida/self-employment goal, ghostwriter constraint,
  verified data inventory, machine limitations and a required decision format;
- `SUNDAY_NEWSLETTER_PILOT.md` — the initial recommendation; the four-model review below supersedes
  its 6:15 p.m. working time with a Sunday 7 a.m. ET send;
- `florida-signal-current-product-contact-sheet.png` — current desktop and 390-pixel mobile evidence
  for the private Live Desk/Data Explorer and public homepage/Data Room; and
- the six labeled source screenshots used to make the contact sheet.

The recommended modules are Lead Signal (or honestly labeled What We're Watching), Early Watch,
Paper Trail, Development Pulse and Week Ahead, followed by a compact receipts/corrections footer.
Do not promise daily until four real weekly editions establish production time, engagement and the
desk's ability to clear meaningful items without padding. Preserve the public data site as Explore
and source proof; simplify the first-time journey around the newsletter rather than rebuild the
whole site before Sunday.

The Mailchimp campaign-planning skill supported the email-first recurring weekly pilot, but its
account analytics connector was not authenticated in this session. No audience size, campaign
history or engagement benchmark was invented; the first four editions establish the baseline.

### Closed-loop agent future · saved August 12

`CLOSED_LOOP_AGENT_FUTURE_2026-08-12.md` preserves the user's longer-term direction from a set of
X screenshots: versioned intent, derived tasks, isolated parallel work, independent tests, docs,
human-gated release and monitoring that feeds evidence back into the next specification. The social
post's “Anthropic leak” claim is unverified and is not treated as product documentation.

The recommended Florida Signal starting point is three bounded loops—not seven unattended loops:
spec/task planning, isolated implementation/verification, and monitoring that creates a proposed
spec amendment. The canonical spec may never be silently rewritten. Release, destructive data/schema
changes, Candidate → Signal, scoring-profile activation, publication and Mailchimp send remain human
gates. The first proposed pilot is one non-permit Agenda Watch detector in shadow mode with replay
tests, durable receipts and no publishing authority.

Claude, Grok and Gemini were each shown the user's X screenshots and asked the same skeptical future-
architecture question. Their defensible consensus is recorded in the future document. Gemini's
unverified production-state claims and arbitrary suggested thresholds were explicitly rejected;
reviewer advice is never treated as system evidence.

The Live Desk working hierarchy was also changed after operator feedback: `Latest items to confirm`
now appears directly under the attention counts, sorted by source-event date and showing up to five
evidence-ready Candidates before the Record/Candidate/Signal/Story explainer, early-intelligence
sequence or Signal Machine protocols. The decision queue—not the operating manual—is the first job.

Claude, Grok and Gemini received the same architecture brief, literal implementation evidence and
the final desktop/mobile screenshots. Claude found five labeling inconsistencies plus one final
“complete” versus “present” evidence-packet overstatement; all were corrected. Grok and Gemini found
no remaining blocker, and Claude's last blocker was fixed to `Packet present · completeness not
assessed`. Codex rejected invented metrics or connector claims. The current branch is
`codex/brief-bank-signal-machine`; do not include the
unrelated touched `social/graphic-desk/*.png`, raw Broward files, `mailchimp/` or `output/` in its
commit.

## Verification completed

- `python3 -m unittest ops/mac/test_acclaim_resilience.py` — 7 passing.
- `python3 -m unittest tests/test_cms_server.py` — 10 passing in the latest CMS run.
- Playwright `tests/browser/data-wire.spec.js` — 5 passing against the signed Desktop app; it now
  covers all five Newsroom views, the canonical home link, the mobile decision restriction,
  source-clock sanity, 390-pixel page width, non-overlap at the 1,110-pixel sidebar viewport,
  persistent desktop-header behavior and the Agenda Watch entity/time/packet controls.
- Desktop app bundle identifier, code signature and Live Desk launch were verified after refresh.
- Production LaunchAgent check: `com.floridasignal.acclaim`, last exit `0`; August 11 insertion and
  subsequent hourly runs are present in `~/Library/Logs/florida-acclaim.log`.

PR 10 was squash-merged into `main` as `6ef7d39e1f8431a829f1a0332ddc631788ad37f1` after the local
checks. GitHub's **Public site health** workflow then passed its unit and browser jobs. That workflow
name describes the repository safety check; it did not publish the Claude prototype or expose the
loopback-only Data Wire runtime.

## Known gaps / next exact work

1. PR 13 was squash-merged into `main` as `e541a19d14e0c6403c46422c8a425eff37c522da`
   after its repository `verify` check passed. The signed Desktop app was refreshed from the same
   tracked CMS source.
2. Keep the public site and private Newsroom separate in navigation, deployment and documentation.
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

### Newsletter launch execution · August 13

ChatGPT, Grok Heavy, Claude Opus 5 High and Gemini Flash-Lite received the same blind launch brief.
All four independently chose the same path: a weekly Sunday newsletter plus a signup-first landing
page, with the dense public data site preserved as the research/explore layer. Their captured DOM
responses and the reconciled decision are saved in
`deliverables/florida-signal-decision-package-2026-08-12/`.

The models initially recommended a Sunday send, but the founder's later cadence decision supersedes
that recommendation. The initial working title was **The Monday Signal**. On August 15 it became the
**Florida Signal Brief** so a future daily cadence will not require a rebrand. It launches Monday
morning at an exact time to be confirmed after a test send and is bylined **Florida Signal Desk**.
Its modules are
Lead Signal, Record Watch, Week Ahead, Open Questions and Source
proof/corrections. If no Lead Signal clears, publish What We Checked and state why the Candidate did
not clear. Do not pad.

On August 15, the launch priority changed: root `/` now presents the signup-first newsletter landing
page. The full Florida Signal research homepage remains intact at `/fort-lauderdale/`; it was not
dismantled. `/newsletter/` redirects to the new root. The exact pre-switch state is preserved in the
pushed tag `full-site-v1-pre-newsletter-root-2026-08-15`, with recovery notes under
`archive/full-site-v1-2026-08-15/`. The landing continues to use `landing.css` and `landing.js`. A
one-column Mailchimp template remains at the legacy path `fort-lauderdale/brand/newsletter/sunday-brief.html`
but its reader-facing title and cadence now say Monday. The working issue and
LinkedIn approval copy are in `FOUNDING_EDITION_WORKING_DRAFT.md` and `LINKEDIN_LAUNCH_KIT.md`.

The separate `/newsletter/` page was then given the same skeptical premium-product brief in ChatGPT,
Claude, Grok and Gemini. Their consensus is saved in
`landing-review/MULTI_AI_PREMIUM_REVIEW_2026-08-13.md`. The page now removes the aerial and crane
photographs, reduces overlapping promises/modules, puts the complete signup in the first phone
viewport, uses two signup points, and keeps one actual desk diagram as product evidence. Its compact
masthead uses the exact approved `assets/mark-full-color.png` emblem, a two-tone `FLORIDA SIGNAL`
wordmark and one uninterrupted `DEVELOPMENT INTELLIGENCE` line; the former divider is gone. No arrow
or withdrawn emblem asset is used. The original public homepage remains untouched. Final evidence
is saved under `landing-review/final/`. After the August 15 phone-spacing refinement, at 390 x 844
the complete hero signup ends at 576 pixels,
the document is about 2,500 pixels tall, and there is no horizontal overflow, broken image or
browser console error. The focused newsletter browser suite has five passing checks covering the
first-screen conversion, mocked subscription payload, two-signup limit, Monday copy, privacy link,
preserved research-site link and the `/newsletter/` alias.

No LinkedIn profile field, invitation, message or post was changed. Read-only findings: 100
connections, 124 followers, two pending invitations, and only generic website/app vendor outreach
in the unread messages inspected. The Selene Oceanfront explainer remains the strongest visible
engagement proof at 27 reactions and one comment.

Live desk checks at the August 15 handoff: 175 new review Candidates, 25 with evidence packets,
150 blocked, 0 approved and 0 Brief-bank items. Meeting Watch reports 20 upcoming rooms overall;
the narrower Agenda Watch response lists eight watched upcoming meetings. The Aug. 10 808 SW 8
Terrace packet is the first reporting
Candidate, but its sealed source receipt still reports an Aug. 6 source clock. It is not a Signal
until the official Clerk and permit records are opened, relationships/status are reported and the
packet is reconciled against current data.
