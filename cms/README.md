# Florida Signal Newsroom — private CMS

Florida Signal is intentionally two separate sites:

1. **Public Florida Signal** is the reader product: reporting, diagrams, live public tools and the
   newsletter journey at `thefloridasignal.com`.
2. **Florida Signal Newsroom** is the private source-gated CMS and intelligence workspace served
   locally from `cms/`. It is not a public page or a second reader site.

The Newsroom powers Florida Signal and is designed to support additional market sites without
mixing their public feeds. **Live Desk is the Newsroom home**, not a third product.

It is a focused, clean-room port of the useful Michigan Intel Desk patterns:

- private draft queues never appear on a public endpoint;
- every story/brief carries both a `market` key and a required `city` key;
- source, claims, taxonomy and human-editor checks must all pass;
- the public site reads only city-scoped endpoints such as `/api/wire/packets?market=broward&city=fort-lauderdale` and `/api/agenda-recon?market=broward&city=fort-lauderdale`;
- Agenda Recon properties require a cited official source, coordinates and explicit clearance;
- newsletter/social candidates are downstream views of an approved packet, never separate unsourced copy.

The Michigan repository is not imported or modified. The Data Wire starts empty; it deliberately contains no sample story that could be mistaken for real reporting.

## Run locally

```bash
export DATA_WIRE_ADMIN_TOKEN='use-a-long-local-secret'
python3 cms/server.py --port 8788
```

Then run the public site with:

```bash
export FLORIDA_SIGNAL_CMS_URL='http://127.0.0.1:8788'
export FLORIDA_SIGNAL_CMS_MARKET='broward'
export FLORIDA_SIGNAL_CMS_CITY='fort-lauderdale'
python3 server.py --port 4173
```

Open `http://127.0.0.1:8788/` for the **Live Desk** home. The shared Newsroom shell links to:

- **Live Desk** — newest evidence-ready decisions first, followed by source/model protocols;
- **Agenda Watch** — public decisions, packets, attachments and early clues;
- **Brief** — build and clear a sourced newsletter edition;
- **Data Explorer** — exact record search and investigation;
- **Triage** — examine a Candidate's evidence and record the human decision.

The production-timer strip shows what is scheduled next. The schedule is
read-only and comes from the production host; a scheduled timer is never presented as proof that
the source advanced. Use Feed health for source-event, collection and row-count clocks.

The Live Desk sorts its first working list by `source_record_date DESC` (then amount) and shows up
to five `evidence_ready=true` Candidates immediately below the attention counts. Operating-model
explainers and Signal Machine controls follow the decision work. Raw Candidate summaries are labeled
as extracted assertions, not supported facts or verified Signals.

The interface is a production translation of the reviewed Claude Design direction. Claude's
illustrative records, scores, model labels and clocks were not copied. The real Newsroom reads the
existing private endpoints, preserves every human publication gate and uses the canonical emblem
from `assets/mark-full-color.png` without an arrow, crop or distortion.

On the navy Newsroom header, that full-color emblem sits on its own light contrast field. This is a
presentation treatment only: the emblem pixels, proportions and colors are unchanged, and the
header never substitutes an arrow or a newly drawn mark.

The shared shell and Live Desk include three responsive states: full workstation, sidebar-width
workstation and mobile. The middle state is required because a visible 248-pixel sidebar reduces
the content width before the mobile navigation breakpoint. Source-stage labels, descriptions and
independent clocks must reflow at that state; the browser regression suite checks the 1,110-pixel
viewport where those columns previously collided.

Data Explorer opens with a plain-English working discovery sequence before any record table.
Preliminary Development Meeting Request (PDMR) planning intent is the first built lane;
sewer/utility capacity, engineering intake, assemblage +
new LLC, lobbyist registration and SFWMD research lanes remain visible but explicitly unconnected.
A code-only query-only SQLite shadow view can classify exact `ENG-CR`, `ENG-OAA`, `ROW-SEW`,
`ROW-WTR` and `PLB-SEWCP-WT` families already stored in a supplied database; that artifact does
not connect those lanes or change Desk status.
Connected ownership/capital, regulatory and execution sources follow; permits remain later-stage
evidence, not the page's identity. Each catalog option performs a real read check and reports
availability separately from source health and refresh mode: `current/delayed/stale`,
`automated/manual/snapshot`, `Connected · empty`, `Unavailable`, or `health unknown`. Checks run sequentially and
safe reads receive one bounded retry for transient 5xx responses so concurrent probes cannot make
healthy Clerk, FAA or Accela sources look unavailable. The default record view is the same-day
bounded PDMR evidence table. Preliminary Clerk remains clearly separated from verified Clerk
records, and Accela detail/GIS enrichment do not borrow the permit application's health receipt.

The browser stores the admin token only in the local session. Do not put it in public JavaScript,
a screenshot or a committed file.

Do not open `cms/review.html` as a `file://` URL. Direct file pages cannot call the
loopback-only `/api/local-session` endpoint and will prompt for a token. For the normal local
workflow, run `bash ops/launch_local.sh`, then open
`http://127.0.0.1:8788/review.html`; the launcher enables auto-unlock only for requests arriving
from `127.0.0.1` and never prints the token.

The Finder app is refreshed from the tracked source with
`bash ops/update_datawire_desktop_app.sh`. The updater validates the bundle identifier, stages and
signs a complete copy, and restores the prior app if verification fails. Its local editorial
SQLite data remains in Application Support and is not replaced with the app bundle. The launcher
reads durable project state, the private PDMR evidence database and the read-only PDMR Candidate
script from a verified snapshot inside the generated app. This avoids macOS privacy failures when
a Finder-launched app is denied Documents access. Re-run the updater after a local PDMR collection
to refresh the snapshot. `FL_SIGNAL_SITE_REPO` and `FL_SIGNAL_SOURCE_ROOT` select the source at
build time; `FL_SIGNAL_SOURCE_ROOT` and the three specific `FL_SIGNAL_*_PATH` variables may still
override the bundled paths when launching from an environment that can read another checkout.

### If the desk says Locked

The lock is deliberate Newsroom authentication. It does **not** mean that PDMR records are locked;
those records are public. Use the exact value you supplied as `DATA_WIRE_ADMIN_TOKEN` when starting the server:

1. Choose market `broward`.
2. Paste the token into **Private desk token**.
3. Choose **Open desk**.

If the token is rejected, stop the CMS process, export a new long private token, restart `cms/server.py`, then paste that new value. The public site does not need or receive the admin token.

## Public endpoints

- `GET /api/health`
- `GET /api/wire/packets?market=broward&city=fort-lauderdale`
- `GET /api/agenda-recon?market=broward&city=fort-lauderdale`

## Private endpoints

Send `Authorization: Bearer $DATA_WIRE_ADMIN_TOKEN`.

- `GET /api/admin/stories?market=broward`
- `GET /api/admin/review-queue?status=NEW`
- `GET /api/admin/review-summary`
- `GET /api/admin/pipeline-schedule` — read-only upcoming production timers; it never starts a job
- `GET /api/admin/project-state` — durable tracked state plus independent live source receipts;
  legacy “locked PDMR” language is clarified as a frozen study roster, never access control
- `GET /api/admin/pdmr-intent` — bounded, paged, read-only local PDMR evidence with fielded search
- `GET /api/admin/pdmr-candidates` — bounded local shadow ranking with no production writes
- `GET /api/admin/sunbiz-entities` — bounded private exact-match resolver; raw rows stay server-side
- `GET /api/admin/early-intel` — source-specific clocks across decisions, companies, capital,
  regulatory filings and execution; monitored lanes are not misrepresented as completed detectors
- `GET /api/admin/agenda-watch` — private, filtered Legistar item/attachment leads with source links,
  neutral relevance language, an explicit stakeholder reporting checklist, and separate event-span
  and item-index-observation clocks so historical packets cannot look current. Its coverage is
  explicitly **City of Fort Lauderdale only**. It also carries the official upcoming city calendar
  with date, time, place and agenda-posted state; historical packet items expose the government
  body, official agenda PDF, exact meeting item and attachment list before the reporting notes.
- `GET /api/admin/signal-machine` — honest control-plane contract. It separates source health,
  detector coverage and freshness; permit/execution and local PDMR are shadow-ranked, while PDMR
  remains disconnected from the production queue.
- `GET /api/admin/brief-bank?market=broward` — private edition selections with resolved target date,
  source receipt, SHA-256 evidence snapshot, score/gate reasons and machine/profile lineage.
- `POST /api/admin/brief-bank` — saves or reslots one stable source item. It never approves,
  publishes, schedules or sends.
- `GET /api/admin/scoring-profiles?market=broward` — draft simulation profiles. The active
  production profile is explicitly `null` because no activation path exists.
- `POST /api/admin/scoring-profiles` — records a named, rationale-backed 1.00×–2.00× multiplier
  experiment with `status=draft` and `backtest_status=not_run`; it has zero production effect.
- `POST /api/admin/review-queue/{queue_id}` — records APPROVE/HOLD/REJECT/NEEDS_MORE_REPORTING;
  it never publishes
- `POST /api/admin/stories`
- `POST /api/admin/stories/{id}/approve`
- `POST /api/admin/stories/{id}/hold`
- `POST /api/admin/agenda-recon`
- `POST /api/admin/agenda-recon/{id}/clear`

## Approval contract

The Signal Review page opens a hash-sealed evidence packet for each Candidate. Transfer →
Permit packets show the exact canonical-folio receipt, the deed and grouped permit source
records, the facts those records support, and explicit unknowns. A Candidate is not a Signal.
`APPROVED` records Gate 1 only; a separate complete Story Packet still has to pass the claims,
source, taxonomy and named-publication-role checks below.

Each reviewable Candidate also has an **Investigation Kit**. It derives Street View, satellite,
Maps and internal parcel links from the exact permit coordinates returned by the server. News and
External Sunbiz links and the copied Grok research brief are reporting aids only. They do not modify the
sealed evidence packet. Grok is instructed to separate confirmed records, reported claims,
possible connections and unknowns; every useful result must still be opened, checked and attached
with provenance before it can support publication. The private Newsroom now reads the resolver's
exact-match Sunbiz rows through `/api/admin/sunbiz-entities`; the service-role key never enters the
browser and fuzzy identity writes remain prohibited. Public anonymous reads remain intentionally
blocked even though the resolver table contains rows.

Data Explorer search is exact and indexed. Use prefixes such as `permit:`, `folio:`, `instrument:`,
`addr:`, `license:` and `asn:`. Broad leading-wildcard search is intentionally excluded because it
previously caused database timeouts.

A brief cannot publish until it is a complete **VERIFIED Story Packet**: required city, headline, dek, body, event date, dated current trigger, defensible project identity, public source URL/title, at least one source-bound claim slot, topic and geography tags, `claims_status: passed`, `validator_status: passed`, `tags_status: passed`, and a named human editor. Needs-verification packets remain private. The CMS computes a source hash and records approval history.

Agenda Watch cards are raw public records. They are labeled `not scored · not a Signal` and can be
saved to the Brief bank for a weekday/date without becoming a Candidate or receiving a fabricated
score. Brief-bank dates cannot disagree: an exact date determines the weekday, while a weekday-only
selection resolves to its next calendar occurrence. Loading a bank item opens an unverified draft;
the AI consistency-check stage is optional, currently unconnected and can never add evidence or
clear a claim.

Every Brief draft also stores a visible writing profile. The defaults are AP style plus the Florida
Signal house voice, `Catchy but precise` headlines and plain-English acronym translation. The
required ethics checklist covers attribution, uncertainty/preliminary labels, anti-sensationalism,
right of reply when criticism is material, conflict disclosure and a ban on invented context,
quotes, motives or connections. These settings guide writing; they never weaken source, claim,
identity or human-approval gates. Public bylines remain role-based until explicitly changed.

An agenda-property item cannot publish until it has a required city, official packet URL, meeting title/date, item number, property address, coordinates, proposed action, source page and a named human editor.

## Production work still required

- deploy behind authentication and HTTPS;
- move SQLite to private persistent Postgres/Supabase;
- configure backups and audit-log retention;
- connect the official agenda/record collectors to the private draft API;
- connect the separate Florida Legislature/LegiScan API lane after its credential and source
  contract are located and verified. State-capitol bills are not Fort Lauderdale Legistar records
  and must never be implied by the local Agenda Watch coverage;
- add a user/role provider instead of a shared admin token;
- keep all AI output in draft status until a human passes the source and claims gates.
