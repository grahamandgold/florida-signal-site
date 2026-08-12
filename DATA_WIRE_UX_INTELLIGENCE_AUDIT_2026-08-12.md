# The Data Wire — UX & Intelligence Architecture Audit

**Dated:** 2026-08-12
**Scope:** The Data Wire private editorial/data desk running locally on loopback (`/review.html`, `/data.html`, `/index.html`), plus a forward architecture addendum for source freshness, lineage, predictive intelligence, multi-model research, independent audit and defect handling.
**Method:** read-only browser session at a 1470 px viewport; every navigation surface clicked; measurements taken from the live DOM and network layer.
**Authorship:** Florida Signal desk. Role labels only — no personal names, initials, credentials, tokens, contacts or private identity appear in this document.

---

## Document conventions

| Tag | Meaning |
|---|---|
| **[OBSERVED]** | Directly clicked, measured, or captured from the running desk on 2026-08-12 |
| **[INFERRED]** | Derived from observed evidence; reasoning stated |
| **[UNKNOWN]** | Not accessible in this session; contract for resolving it is specified |

Observed facts are confined to **Part I**. Everything in **Part II** is a recommendation unless explicitly tagged.

### Read-only compliance statement

This audit approved, held, rejected, edited and saved nothing. No editorial form was submitted. No change was made to files (other than this document), databases, queues, settings, schedules, Mailchimp, contacts, campaigns or publishing state. One scripted query was auto-blocked for touching query-string data; it was not retried, and no desk token or credential was read, extracted or displayed. The status filter was changed for inspection and restored to `New`; the window size was restored.

---

# PART I — OBSERVED AUDIT

## 1. Headline finding

The Data Wire is three well-built products wearing three different mastheads, one of which has no interaction design.

The **Data Desk** and **Editorial Desk** are honest, calm and roughly five screens each. The **Signal Review** page is the problem, and the complaint that it "feels like a wall of text" understates it:

> **104,018 px tall · 156 screens · 158 candidate cards, all expanded · 791 buttons (158 of them "Approve") · 316 textareas · 790 checkboxes · 190 headings · 83,193 characters.** **[OBSERVED]**

Every card renders its full editorial form inline, with **Approve** as the dark filled primary and **no confirmation step**. For **150 of 158 cards there is no evidence packet at all** — the approval control is offered with nothing to verify against.

The tooling that would fix this already exists and is excellent. The evidence packet is the strongest editorial artifact in the system. It is collapsed by default, labelled "SEALED", buried beneath seven rows of machine metadata, and present on 8 of 158 cards.

---

## 2. Surface-by-surface

### 2.1 `/review.html` — Signal Review

**Masthead [OBSERVED]:** text-only "THE DATA WIRE" + "SIGNAL REVIEW". No logo image. Top-right: `STATUS` select and `RELOAD`.

**Three-step navigation [OBSERVED]** — identical on all three surfaces and the single best element in the product:

| 1 · Data Desk | 2 · Signal Review | 3 · Editorial Desk |
|---|---|---|
| Look. Every source, raw and read-only. | Decide. Approve, hold or reject candidates. | Write. Source-gated packets, cleared by a human. |

Verb plus promise per stage, current stage highlighted. Keep it.

**Banner [OBSERVED]:** "Approving a Signal records an editorial decision. It does not publish anything, anywhere. This queue is isolated from the shadow scorer registries."

**Card as rendered [OBSERVED]:**

```
[NEW]
Permit activity follows a recorded deed at 808 SW 8 TER
Clerk instrument 120889884 was recorded 2026-05-28; 1 related Fort Lauderdale
permit application was filed afterward on the same verified parcel. Review the
sealed records before making any public claim.

Candidate type               TRANSFER_THEN_PERMIT
Source record IDs            120889884+BLD-GEN-26080223
County parcel (folio)        504210410390
Latest event                 2026-08-10
Largest native permit value  $815,000
Detector                     v1
Located by                   Exact county folio match

> OPEN SEALED EVIDENCE PACKET · SEALED          (collapsed by default)

HEADLINE         [ editable input ]
SUMMARY          [ editable textarea ]
EDITOR NOTES     [ editable textarea ]
ASSIGN REVIEWER  [ input ]
[ ] Live Signals Map  [ ] Signals page  [ ] Daily Intel Brief
[ ] Neighborhood page [ ] Broward Record
[SAVE EDITS] [APPROVE] [HOLD] [NEEDS MORE REPORTING] [REJECT]
```

Correct in this card: "Largest **native** permit value" (native vs estimated distinction preserved), "Located by: Exact county folio match", canonical folio, event date labelled as event date.

Wrong: seven rows of machine metadata precede any evidence; `TRANSFER_THEN_PERMIT` and `v1` are raw enums shown to a human at decision time; and the three facts that actually decide the case — deed amount, permit amount, and the interval between them — are **not on the card**, only inside the sealed packet.

**Evidence packet, opened [OBSERVED]:**

```
Join receipt
EXACT_CANONICAL_FOLIO · 504210410390 · SHA-256 ed50206cf902793b...

Source records
  broward_clerk_records_doc · 120889884
  2026-05-28 · 808 SW 8 TER · $850,000
  permits · BLD-GEN-26080223
  2026-08-10 · 808 SW 8 TER · Structural Permit · $815,000
  808 SW 8 TERR - NMEW DUPLEX UNIT

Facts this packet supports
  - The Clerk recorded the identified deed on the stated date.
  - Fort Lauderdale received the identified permit applications on the stated dates.
  - The source records carry the same verified canonical parcel identifier.

What remains unknown
  - Whether the deed was an arm's-length transaction.
  - Whether the deed parties and permit applicant are related.
  - Whether any application was issued, whether work started, and the total project cost.
```

This structure is correct and rare: a cryptographic join receipt, both source records with event dates and amounts, the raw source string retained verbatim (the `NMEW` typo is the city's and belongs here), an explicit supported-facts list, and an explicit unknowns list.

**Four defects undermine it [OBSERVED]:**

| Defect | Measurement |
|---|---|
| Only 8 of 158 cards carry an evidence packet | 150 cards offer Approve with nothing to verify |
| Zero clickable source links inside the packet | `anchors in packet = 0` |
| Collapsed and labelled "SEALED" | reads as *restricted*, not *openable* |
| Positioned below seven metadata rows | evidence is last, not first |

**Density [OBSERVED]:**

| Metric | Value |
|---|---|
| Scroll height | 104,018 px (156 screens at the observed 667 px inner height) |
| Cards rendered | 158, all expanded |
| Buttons | 791 (158 Approve / 158 Hold / 158 Reject / 158 Needs-more / 158 Save / 1 Reload) |
| Textareas | 316 |
| Checkboxes | 790 |
| Headings | 190 |
| Body text | 83,193 characters |
| Links on page | 3 (the step tabs only) |
| Evidence packets | 8 |
| Distinct font sizes within one card | 9 — 9, 10, 10.5, 11, 11.5, 12, 13, 15, 16 px |
| Distinct text colours | 6 — none red, amber or green |

**Safety [OBSERVED]:** Approve is the only filled/dark button, repeated 158 times, with no confirmation. The Editorial Desk has a `Confirm decision` / `Cancel` pair; Signal Review does not. The more consequential surface carries the weaker guardrail.

**Accessibility [OBSERVED]:** evidence-packet `summary` elements expose in the accessibility tree as **generic**, not as disclosure controls. There is no skip link on this page, despite 791 focusable controls.

**Data path [OBSERVED]:** `GET http://127.0.0.1:8788/api/admin/review-queue?status=NEW` returns 200 — proxied through the local server rather than queried directly. Correct: the review queue has no anonymous read policy, so the privileged credential stays server-side.

**Status filter [OBSERVED]:** values are `NEW`, `REVIEWING`, `HOLD`, `NEEDS_MORE_REPORTING`, `APPROVED`, `REJECTED`, plus an **"All" option whose value is an empty string**. Setting the select programmatically did not refetch the list. **[INFERRED]** the filter requires `RELOAD`, and "All" likely emits `?status=`.

### 2.2 `/data.html` — Data Desk

3,548 px, five screens, calm and honest. This page is good.

**Masthead [OBSERVED]:** "INTERNAL · GRAHAM & GOLD LLC" / "Data Desk" / "Read-only intelligence viewer · Broward store" / `Public site ↗`. **The Data Wire wordmark does not appear anywhere on this page.**

**Hero [OBSERVED]:** "EVERY TABLE · EVERY SOURCE · ONE DESK" — "See the record. Then work the signal." — "Nothing here is public output. This desk reads the raw store under row-level security. Analysis uses public event dates; fetch stamps are freshness metadata only."

**Feed health [OBSERVED]** — subtitled "three clocks per feed: latest source event · last successful collection · row count":

| Feed | Latest source event | Last collection | Rows | Chip |
|---|---|---|---|---|
| Permit applications | 2026-08-10 | 2026-08-10 | ~133,221 | HEALTHY |
| Official Clerk recordings | 2026-08-06 | not recorded | ~201,014 | VERIFIED THROUGH 2026-08-06 — SOURCE QA LAG |
| Preliminary Clerk recordings | 2026-08-11 | 2026-08-11 | ~30,970 | PRELIMINARY / NOT YET VERIFIED |
| FAA obstruction cases | 2026-08-10 | 2026-08-11 | ~8,086 | HEALTHY |
| FDEP environmental permits | no rows | not recorded | ~85,846 | VALID EMPTY |
| County parcel authority | n/a — snapshot, not an event stream | not recorded | ~531,525 | COMPLETE / CURRENT |
| Permit GIS coverage | n/a — snapshot | 2026-08-11 | ~107,439 | HEALTHY |
| Sync health | n/a — snapshot | 2026-08-12 | ~4,071 | HEALTHY |
| Dashboard cache | n/a — snapshot | 2026-08-12 | ~1 | HEALTHY |

**"Get exact counts" [OBSERVED]** with the note: "Row counts are planner estimates by default. Exact counts are a full table scan and this database is IO-constrained, so they run only when you ask." Honest, performance-aware, and instructive.

**Quarantine section [OBSERVED]** — "NOT OPERATIONAL FEEDS — RETAINED, CLEARLY LABELLED":

- **Signals v2 (pilot)** · HISTORICAL · ~250 rows · "A 250-row scoring pilot that ran 26–29 April 2026. No collector is scheduled for it and none has failed."
- **Land sales (seed)** · **SYNTHETIC — DO NOT USE** · red border and red chip · ~19 rows · "Every row carries source='seed:dry-run' with sequential fabricated instrument numbers. It is NOT a public record source and must never reach the map, a brief, the CMS or an export."

This is the best pattern in the product and the only semantic use of red anywhere. The warning is repeated inside the table dropdown as `⚠ Land sales — SYNTHETIC seed:dry-run fixture, NOT public records`.

**Field views [OBSERVED]** — "one tap · preset queries over the store", 16 presets: Latest permits · Permit value $100K+ · Latest recordings · Deeds · Deeds·mapped to parcels · Deeds·NOT mappable · Easements·mapped · Mortgages (no parcel — not mappable) · NOCs · Liens · Judgments · FDEP latest · Cranes (FAA) · Top signals (Apr 2026 pilot — historical) · Owner flips · Licenses. Verified working: clicking "Deeds · mapped to parcels" switched the table, set an active state and loaded correctly.

**Table switcher [OBSERVED]** — 13 tables: Permits (Accela) · Clerk recordings · FDEP environmental (ERP) · FAA obstruction cases · Signals v2 (scored) · GIS parcel enrichment · BCPA property cards · Accela detail scrapes · Contractor licenses · ⚠ Land sales (synthetic) · Permit workflow events (FOIA) · Property transfers — deeds & easements mapped to parcels · Owner resolution.

> **Prior unknown resolved [OBSERVED]:** "Permit workflow events (FOIA)" identifies the previously unexplained ~2,410,033-row `foia_events` figure.

**Deeds view columns [OBSERVED]:** `RECORDED | KIND | INSTRUMENT # | STATED AMOUNT | FOLIO | SITUS ADDRESS | CITY CODE | VERIFICATION | MAP ELIGIBLE? | WHY EXCLUDED`. Rows dated 2026-08-06, VERIFIED, map-eligible true. Treating `VERIFICATION`, `MAP ELIGIBLE?` and `WHY EXCLUDED` as first-class columns is correct. One row showed a `$10` stated amount — a nominal deed, correctly displayed rather than suppressed.

> **[INFERRED]** these rows are dated 2026-08-06 while the public property-transfer snapshot was previously measured topping out at 2026-07-10 — suggesting the desk reads the live view while the public map reads a stale snapshot.

**`CITY CODE` renders raw two-letter codes [OBSERVED]** (`MM`, `DV`) with no label or lookup, so the column reads as noise.

#### Two defects on this page

**Search is entirely broken [OBSERVED].** Searching `808 SW 8` then pressing Refresh returned `Could not load: permits HTTP 500`. Retried with `808` (no spaces): identical 500. Captured request:

```
GET /rest/v1/permits
  ?select=permit_number,applied_date,permit_type,work_type,status,address,
          valuation,valuation_usd_clean,contractor_name,owner_name
  &order=applied_date.desc.nullslast&limit=25&offset=0
  &or=(permit_number.ilike.*808*,address.ilike.*808*,
       contractor_name.ilike.*808*,owner_name.ilike.*808*)
-> 500
```

**[INFERRED]** a statement timeout: four leading-wildcard `ILIKE` predicates OR'd across ~133,401 rows with an ordered sort and no trigram index, on a database the page itself describes as IO-constrained.

Two further problems in the same control: typing does not filter (results stayed on unrelated addresses until Refresh), and the commit control is labelled **"Refresh"**, not "Search", so nothing signals that the query must be committed.

**`[object Object] matching rows` [OBSERVED]** — a raw object string-concatenated into the result counter. Present on first load, persists across every table and every field view.

### 2.3 `/index.html` — Editorial Desk

3,519 px, five screens.

**Masthead [OBSERVED]:** the actual Data Wire lockup image plus "SOURCE-GATED EDITORIAL DESK". The only surface carrying the real mark. The lockup PNG is ~848 KB and renders on a visible light checkerboard box that reads as an unstyled placeholder.

**Best-in-product elements [OBSERVED]:**

- "Skip to editorial workspace" — the only skip link on any surface.
- Connection bar: "● BROWARD DESK CONNECTED · PRIVATE EDITORIAL API" with "Token stays in this tab · drafts never enter the public wire · local desk auto-unlocked."
- Hero: "HUMAN EDITOR REQUIRED" / "Build the record. Clear the signal." / "Nothing publishes from here by accident. Every packet needs a public source, a defensible taxonomy, passed claims checks, and the name of the editor who cleared it."
- Two-column layout with a proper empty state: "No stories yet · The market queue is empty. Create the first sourced draft when reporting is ready."
- `Confirm decision` / `Cancel` — a real two-step guard.
- Card top borders use a blue/amber/red three-segment accent — the only hint of a status palette.

**Highest-friction control [OBSERVED]:** the draft form carries 42 inputs, with required fields `HEADLINE*`, `SUMMARY / DEK*`, `STORY BODY*`, `PROJECT IDENTITY BASIS*` and:

```
CLAIM SLOTS (JSON) *
[ Paste a JSON array. Each object should pair one material claim
  with its source URL and exact document locator. ]
No unsupported prose: one claim per object, with a public source and
page, section, row or record locator.
```

A required, hand-authored JSON array in a plain textarea. The concept — a claim ledger where every assertion carries a locator — is correct and valuable. The implementation asks a human, mid-reporting, to hand-write valid JSON where one missing comma blocks the save, on the critical path to publishing anything.

Also observed: `VERIFICATION STATUS` select defaulting to "Needs verification", `CHANGE / TRIGGER`, `UNRESOLVED ISSUES`, and a geography field pre-filled `broward-county` with helper text "Hidden geography metadata; use the stable county key."

**Data path [OBSERVED]:** `/api/local-session` and `/api/admin/stories?market=broward` both return 200 through the local proxy.

### 2.4 Cross-surface

**Three surfaces, three mastheads [OBSERVED]:**

| Surface | Masthead | Logo image |
|---|---|---|
| `/review.html` | text "THE DATA WIRE" + "SIGNAL REVIEW" | no |
| `/data.html` | "INTERNAL · GRAHAM & GOLD LLC" + "Data Desk" | no — no Data Wire identity at all |
| `/index.html` | Data Wire lockup + "SOURCE-GATED EDITORIAL DESK" | yes |

**The logo is not a link on any surface [OBSERVED].** Verified on Review (brand text is not inside an anchor; only 3 anchors exist, all step tabs) and by full link enumeration on Data Desk (4 links: `Public site ↗` plus 3 tabs) and Editorial Desk (4 links: skip link plus 3 tabs). No breadcrumbs, no per-candidate permalinks, no deep links.

**Two different data paths [OBSERVED]:** Review and Editorial Desk proxy through `127.0.0.1:8788`; Data Desk queries the database directly from the browser. The proxy pattern is correct for privileged reads; the direct pattern is why Data Desk search inherits the database statement timeout.

**External font dependency [OBSERVED]:** all three surfaces load four Google Font families. On a loopback-only internal tool this is an avoidable, render-blocking external dependency that breaks offline.

**Responsive coverage [OBSERVED]:** only two media queries exist — `max-width: 720px` and `max-width: 620px`. Nothing is tuned below 620 px.

---

## 3. Ranked issue list

### P0

| # | Issue | Evidence |
|---|---|---|
| P0-1 | Review page is 104,018 px / 156 screens with 158 fully-expanded cards; no triage, pagination or collapse | measured |
| P0-2 | 158 unconfirmed "Approve" buttons styled as filled primary on one scroll surface | 791 buttons / 158 Approve |
| P0-3 | Search returns HTTP 500 for every query on the primary table | two queries, both 500 |
| P0-4 | 150 of 158 candidates have no evidence packet, yet Approve is offered | 8 packets / 158 cards |
| P0-5 | Evidence packet contains zero clickable source links | 0 anchors |
| P0-6 | Logo is not a Home link on any surface; Data Desk has no Data Wire identity | link enumeration |
| P0-7 | `[object Object] matching rows` on every table view | persistent |

### P1

| # | Issue |
|---|---|
| P1-1 | Search covers only 4 fields; no folio, instrument, neighborhood, date, status, value or source |
| P1-2 | Search does not fire on type; commit control is labelled "Refresh" |
| P1-3 | Evidence packet collapsed, labelled "SEALED", placed below seven metadata rows |
| P1-4 | No semantic status colour; HEALTHY and SOURCE QA LAG render identically |
| P1-5 | Nine font sizes in one card, including 9 px and 10 px |
| P1-6 | Evidence disclosure exposes as `generic` in the accessibility tree |
| P1-7 | No skip link on Review or Data Desk, with 791 focusable controls on Review |
| P1-8 | `CLAIM SLOTS (JSON)` is required hand-authored JSON |
| P1-9 | Raw enums surfaced to humans: `TRANSFER_THEN_PERMIT`, `v1`, `MM`/`DV` |
| P1-10 | Three different mastheads across three surfaces |
| P1-11 | Deed amount, permit amount and their interval are absent from the card face |

### P2

| # | Issue |
|---|---|
| P2-1 | ~848 KB masthead PNG on a visible checkerboard box |
| P2-2 | Google Fonts dependency on a loopback-only tool; breaks offline |
| P2-3 | Only two media queries; nothing below 620 px |
| P2-4 | "All" status option has an empty value **[INFERRED]** |
| P2-5 | Feed cards sit on "loading… / CHECKING" ~6 s with no skeleton |
| P2-6 | FDEP card reads "no rows" and "VALID EMPTY" beside "~85,846 rows" — self-contradictory |
| P2-7 | No per-candidate permalink |
| P2-8 | "Refresh" appears on all three surfaces meaning three different things |

---

## 4. Proposed IA and task journey (ADHD-first)

**Principles.** One decision on screen at a time. Evidence before controls. The default action is *skip*, not *approve*. Every screen answers "what do I do next?" in one sentence. Progress is always visible. Colour carries meaning and is used sparingly enough to keep it.

```
LIVE DESK  (new landing surface — one screen, no scroll)
   "6 feeds green · 1 lagging · 158 candidates waiting · 12 ready to decide"
   [ Start review ]   [ Look at data ]   [ Write a brief ]
        |
        v
TRIAGE  (one screen — scannable list, not forms)
   158 candidates sorted by decision-readiness
     8 have full evidence      -> "Start here (8)"
   150 need evidence first     -> quarantined, cannot be approved
        |
        v
DECIDE  (one candidate, full screen, evidence-first)
   "3 of 8"  ·  evidence OPEN by default  ·  decision bar pinned
   Approve requires a confirm step
        |
        v
WRITE  (Editorial Desk — reachable only from an approved Signal,
        pre-filled from that Signal's evidence packet)
```

**Highest-leverage change:** split the queue by *decision-readiness*, not by status. A candidate with no evidence packet is not a decision — it is a data task. Moving those out of the approval path reduces the operator's queue from 158 impossible decisions to 8 real ones.

### Desktop wireframe — Decide

```
+--------------------------------------------------------------------------+
| [# THE DATA WIRE]  Signal Review        <- Home      Locked · Broward     |  logo = Home
+----------------+----------------+----------------------------------------+
| 1 · Data Desk  | 2 · Signal Rev | 3 · Editorial Desk                     |  keep as-is
+--------------------------------------------------------------------------+
| Deciding 3 of 8 ready      [###.....]   |  150 more need evidence  ->     |  progress
+-------------------------------------------+------------------------------+
|  ● TRANSFER, THEN PERMIT                  |  DECIDE                       |
|  Permit activity follows a recorded deed  |                               |
|  808 SW 8 TER · Fort Lauderdale           |  What this claims:            |
|                                           |  A deed and a later permit    |
|  +-- THE EVIDENCE ---------- open ------+ |  sit on the SAME county       |
|  | May 28 -----------> Aug 10           | |  parcel. Nothing more.        |
|  | DEED                PERMIT           | |                               |
|  | $850,000            $815,000         | |  Facts supported     3        |
|  |                                      | |  Still unknown       3        |
|  | Clerk 120889884          [open]      | |  Join   EXACT FOLIO           |
|  | Permit BLD-GEN-26080223  [open]      | |                               |
|  | Folio 504210410390       [open]      | |  +-------------------------+  |
|  | receipt SHA-256 ed50206c   [copy]    | |  |       Approve           |  |
|  |                                      | |  +-------------------------+  |
|  | SUPPORTED                            | |   requires confirm            |
|  |  - Clerk recorded the deed           | |  [ Hold ] [ More reporting ]  |
|  |  - City received the application     | |  [ Reject ]                   |
|  |  - Same canonical parcel ID          | |  ---------------------------  |
|  |                                      | |  [ Skip — decide later ]      |  default
|  | NOT ESTABLISHED                      | |                               |
|  |  - Arm's-length? unknown             | |                               |
|  |  - Parties related? unknown          | |                               |
|  |  - Issued / built / cost? unknown    | |                               |
|  +--------------------------------------+ |                               |
|  > Editorial fields (collapsed)           |                               |
|  > Machine metadata (collapsed)           |                               |
+-------------------------------------------+------------------------------+
        <- Prev        Skip        Next ->        (j / k / s shortcuts)
```

### Mobile wireframe (~390 px) — review is reading, not deciding

```
+------------------------------+
| # THE DATA WIRE          =   |  logo = Home
+------------------------------+
| Signal Review · 3 of 8       |
| [###.....]                   |
+------------------------------+
| ● TRANSFER, THEN PERMIT      |
| Permit activity follows a    |
| recorded deed                |
| 808 SW 8 TER                 |
|                              |
| +- EVIDENCE ------ open ---+ |
| | May 28  DEED    $850,000 | |
| |    |                     | |
| | Aug 10  PERMIT  $815,000 | |
| | same parcel 504210410390 | |
| | 3 supported / 3 unknown  | |
| | [ Open all 3 sources ]   | |
| +--------------------------+ |
| > Facts supported            |
| > Not established            |
| > Machine metadata           |
|                              |
| +--------------------------+ |
| |   Flag for desk review   | |  safe, reversible
| +--------------------------+ |
| [ Skip ]        [ Next -> ]  |
| Approve / Reject are         |
| desktop-only.                |
+------------------------------+
| Board  Review  Data  Write   |
+------------------------------+
```

**Rule:** irreversible decisions (Approve / Reject) are desktop-only. Mobile permits read, skip and flag — one-way, reversible, safe one-handed.

---

## 5. Making the logo go Home

Ship one shared header partial across all three surfaces:

```html
<header class="dw-header">
  <a class="dw-brand" href="/" aria-label="The Data Wire — desk home">
    <img class="dw-brand__mark" src="/datawire-lockup.svg"
         alt="" width="180" height="34" decoding="async">
    <span class="dw-brand__desk">Signal Review</span>
  </a>
  <nav class="dw-steps" aria-label="Desk stages"> ... 1 / 2 / 3 ... </nav>
  <div class="dw-status">Broward desk connected</div>
</header>
```

```css
.dw-brand { display:inline-flex; align-items:center; gap:12px;
            text-decoration:none; color:inherit; padding:8px;
            border-radius:6px; min-height:44px; }
.dw-brand:hover { background: rgba(23,103,255,.06); }
.dw-brand:focus-visible { outline:2px solid #1767ff; outline-offset:2px; }
.dw-brand__desk { font-size:12px; letter-spacing:.14em;
                  text-transform:uppercase; color:#62708a; }
```

1. `/` is the desk home and resolves to the Live Desk — not a redirect into Review.
2. Mark plus wordmark sit inside the anchor; the desk label is inside but visually secondary, so the whole lockup is one 44 px target.
3. `alt=""` on the image because the accessible name comes from the anchor's `aria-label`.
4. The same partial ships on all three pages, restoring Data Wire identity to the Data Desk.
5. The brand still links Home on the current page.
6. `Public site ↗` stays visually distinct and clearly external.
7. Replace the ~848 KB PNG with an SVG and remove the checkerboard backing.

---

# PART II — ARCHITECTURE ADDENDUM

Everything below is a recommendation. Where it references live values, those come from Part I and remain tagged.

---

## 6. Source Freshness Board

### 6.1 The four clocks

The desk currently exposes two clocks ("latest source event" and "last successful collection") **[OBSERVED]**. Four are required, and they must never be substituted for one another.

| Clock | Definition | Authority |
|---|---|---|
| **Event time** | When the thing happened in the world, per the publishing agency: `applied_date`, `recording_date_iso`, meeting `starts_at`, FAA `date_entered` | The source agency. Drives all analysis. |
| **Pull time** | When we successfully retrieved the source artifact | The collector job |
| **Processing time** | When normalization, enrichment, joins and detectors last completed for that category | The processing job |
| **Publication time** | When a derived artifact became visible to a reader (public map, brief, snapshot refresh) | The publishing job |

**Binding rule:** a category is only "current" when **all four** clocks are within contract. A fresh pull over stale processing is not freshness — it is the failure mode that produced the observed 27-day gap between the desk's live deeds view (2026-08-06) and the public snapshot (2026-07-10) **[INFERRED, Part I §2.2]**.

### 6.2 Normalized inventory

`event_through` and `last_collection` values below are as observed on 2026-08-12; all `processing` and `publication` clocks are **[UNKNOWN]** because no such clock is currently exposed anywhere in the desk.

| # | Category | What it means | Event-through | Last collection | Processing | Publication | Coverage | Cadence | Lag | Verification | Owner / job | Status | Failure action |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **Public mirror / sync** | Droplet→store heartbeat | n/a snapshot | 2026-08-12 **[O]** | [UNKNOWN] | [UNKNOWN] | ~4,071 **[O]** | 30 min | — | n/a | sync job | HEALTHY **[O]** | Page if >2 cycles missed |
| 2 | **Permits** | City permit applications | 2026-08-10 **[O]** | 2026-08-10 **[O]** | [UNKNOWN] | [UNKNOWN] | ~133,221 **[O]** | nightly | 2 d | source-native | permit collector | HEALTHY **[O]** | Suppress permit modules >3 d |
| 3 | **Permit workflow (FOIA) events** | Permit lifecycle/status transitions | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | ~2.41 M **[O]** | [UNKNOWN] | [UNKNOWN] | source-native | [UNKNOWN] | **not on board** | Add to board |
| 4 | **Permit GIS / enrichment** | Parcels resolved *from* permits | n/a snapshot | 2026-08-11 **[O]** | [UNKNOWN] | [UNKNOWN] | ~107,439 **[O]** | continuous | — | derived | enrichment | HEALTHY **[O]** | Alert if 8 h delta = 0 |
| 5 | **Clerk — official verified** | QA'd county recordings | 2026-08-06 **[O]** | **not recorded** **[O]** | [UNKNOWN] | [UNKNOWN] | ~201,014 **[O]** | daily + weekday catch-up | 6 d | VERIFIED | clerk catch-up | **SOURCE QA LAG** **[O]** | Suppress deed modules >2 business d |
| 6 | **Clerk — preliminary** | Same-day public-search recordings | 2026-08-11 **[O]** | 2026-08-11 **[O]** | [UNKNOWN] | [UNKNOWN] | ~30,970 **[O]** | 4×/day | 1 d | **PRELIMINARY** | preliminary collector | HEALTHY **[O]** | Never present as verified |
| 7 | **Property-transfer snapshot** | Deed↔parcel join, materialized | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | ~15,946 | manual refresh | **known drift** | VERIFIED / CONFLICT / UNRESOLVED | none scheduled | **at risk** | Suppress if lag > source |
| 8 | **Parcel authority** | Countywide county parcel layer | n/a snapshot | **not recorded** **[O]** | [UNKNOWN] | [UNKNOWN] | ~531,525 **[O]** | one-time, complete | — | AUTHORITY | one-off import | COMPLETE **[O]** | Re-verify quarterly |
| 9 | **Clerk parties** | Grantor/grantee names + roles | inherits #5 | inherits #5 | [UNKNOWN] | [UNKNOWN] | ~527,143 | with #5 | 6 d | VERIFIED | clerk catch-up | **not on board** | Add to board |
| 10 | **Clerk legals** | Legal descriptions carrying folio | inherits #5 | inherits #5 | [UNKNOWN] | [UNKNOWN] | ~24,754 | with #5 | 6 d | VERIFIED | clerk catch-up | **not on board** | Add; this is the join key |
| 11 | **Clerk link graph** | Instrument→instrument relations | inherits #5 | inherits #5 | [UNKNOWN] | [UNKNOWN] | ~76,267 | with #5 | 6 d | VERIFIED | clerk catch-up | **not on board · unused** | Add to board |
| 12 | **FDEP environmental** | State environmental permits | **no rows** **[O]** | **not recorded** **[O]** | [UNKNOWN] | [UNKNOWN] | ~85,846 **[O]** | [UNKNOWN] | [UNKNOWN] | source-native | edge function | **VALID EMPTY** **[O]** | Resolve contradiction |
| 13 | **FAA obstruction** | Crane/structure filings | 2026-08-10 **[O]** | 2026-08-11 **[O]** | [UNKNOWN] | [UNKNOWN] | ~8,086 **[O]** | daily | 2 d | source-native | edge function | HEALTHY **[O]** | Alert >5 d |
| 14 | **Meetings** | Official calendars/agendas | live fetch | live fetch | [UNKNOWN] | [UNKNOWN] | not persisted | 15 min | — | source-native | API fetch | **not on board · not persisted** | Persist, then add |
| 15 | **Sunbiz entities** | Company/officer registry | **null** | **null** | [UNKNOWN] | [UNKNOWN] | **0 rows** | nightly | — | **unverified** | corpus job | **BLOCKING GAP** | Block all company claims |
| 16 | **BCPA property cards** | County property attributes | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | source-native | [UNKNOWN] | **not on board** | Add to board |
| 17 | **Contractor licences** | Licence registry | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | source-native | [UNKNOWN] | **not on board** | Add to board |
| 18 | **Owner resolution** | Owner normalization outputs | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | derived | [UNKNOWN] | **not on board** | Add; label derived |
| 19 | **Dashboard cache** | Aggregate snapshot | n/a snapshot | 2026-08-12 **[O]** | [UNKNOWN] | [UNKNOWN] | ~1 **[O]** | after build | — | derived | scheduled job | HEALTHY **[O]** | Never display if stale |
| 20 | **Detectors / editorial queue** | Candidate generation + review | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | n/a | 158 local **[O]** | [UNKNOWN] | [UNKNOWN] | CANDIDATE | detector jobs | **not on board** | Add: candidates/day, evidence-coverage % |
| 21 | **Analytics / newsletter** | Desk-side product telemetry | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | n/a | local API | **not on board** | Add aggregate only, never contact-level |
| 22 | **Signals v2 (pilot)** | Historical scoring pilot | 2026-04-29 **[O]** | none **[O]** | n/a | n/a | ~250 **[O]** | none | frozen | **HISTORICAL** | none | QUARANTINED **[O]** | Must never enter a claim |
| 23 | **Land sales (seed)** | Synthetic dry-run fixture | n/a | n/a | n/a | n/a | ~19 **[O]** | none | n/a | **SYNTHETIC** | none | **DO NOT USE** **[O]** | Hard-block from map/brief/CMS/export |

**Board goes from 9 cards to 23 categories, of which 11 are currently invisible to the operator.**

### 6.3 Required contract for the missing clocks

Do not invent clocks. Emit them.

```sql
create table feed_registry (
  feed_key            text primary key,
  display_name        text not null,
  category            text not null,     -- source | derived | snapshot | quarantined
  event_field         text,              -- null for true snapshots
  is_event_stream     boolean not null,
  owner_job           text not null,
  expected_cadence    interval,
  lag_warn            interval,
  lag_fail            interval,
  verification_model  text not null,     -- source-native | VERIFIED | PRELIMINARY | derived | SYNTHETIC | HISTORICAL
  failure_action      text not null,     -- exact suppression rule
  downstream_of       text[] default '{}'
);

create table feed_heartbeat (
  feed_key         text references feed_registry,
  observed_at      timestamptz not null default now(),
  event_through    date,          -- null only if is_event_stream = false
  last_pull_ok     timestamptz,
  last_process_ok  timestamptz,   -- NEW: closes the observed processing gap
  last_publish_ok  timestamptz,   -- NEW: closes the observed snapshot-drift gap
  row_count        bigint,
  count_method     text,          -- estimate | exact
  status           text,          -- healthy | lagging | failing | empty_valid | quarantined
  detail           text,
  primary key (feed_key, observed_at)
);
```

Rules: `not recorded` is a **failure to emit a heartbeat**, not a healthy state — three categories currently display it **[OBSERVED]**. A snapshot category sets `is_event_stream=false` and must render "snapshot — not an event stream" rather than a fake event date. Any category whose `last_process_ok` or `last_publish_ok` is null renders **amber**, never green.

### 6.4 Board UI

One compressed strip on the Live Desk, expandable to the full 23:

```
FEEDS  ●●●●●○●●●  17 green · 3 amber · 1 red · 2 quarantined     [ expand ]
       ^Clerk verified: 6 days behind — deed modules suppressed
```

Each row shows four clock chips (`event` / `pull` / `process` / `publish`), a lag bar against contract, verification badge, owner job, and the exact suppression rule that fires on failure.

---

## 7. How data connects — evidence & lineage map

### 7.1 Edge rules

Only these edges may be drawn. Every edge carries a method and a state.

| Edge | Key | Rule | State |
|---|---|---|---|
| **Permit → parcel** | `parcel_id_verified` + `parcel_source` | Exact only; never inferred from address | VERIFIED / ABSENT |
| **Parcel → deed** | canonical folio, exact string equality | 12-char alphanumeric; digits-only normalization prohibited | VERIFIED / CONFLICT / UNRESOLVED |
| **Deed → parties** | `instrument_number` | Natural key | VERIFIED |
| **Deed → deed / instrument chain** | Clerk link graph | Publisher-asserted; inherit the Clerk's own label, never reinterpret | VERIFIED (source-asserted) |
| **Parcel → neighborhood / ZIP / district** | point-in-polygon, official boundaries | State boundary vintage | DETERMINISTIC |
| **Parcel → baseline** | neighborhood trailing-12-month distribution | Suppress if n < 30 | DERIVED |
| **FAA / FDEP → parcel** | *proximity only* | Dashed edge, labelled "near — not the same record" | CONTEXT ONLY |
| **Meeting → parcel** | *extracted evidence only* | Requires an extracted, human-confirmed address/folio from agenda text | CONTEXT ONLY |
| **Party → company** | Sunbiz exact | **Currently impossible — registry is empty [OBSERVED]** | BLOCKED |

**Forbidden, permanently:** identity from address-string similarity; identity from owner/contractor name similarity; bridging two verified edges through an unverified middle node; upgrading a proximity edge to an identity edge.

### 7.2 Interactive map

```
        [ start: permit / address / parcel / entity ]
                          |
                   ( exact folio )
                          v
              +---------------------+
              |   PARCEL 5042104..  |  <- always the hub
              +---------------------+
             /          |            \
   (exact)  /     (point-in-poly)     \  (exact folio)
           v              v             v
   +-----------+   +-------------+   +-----------+
   | PERMITS 3 |   | NEIGHBORHOOD|   |  DEEDS 1  |
   +-----------+   |  + baseline |   +-----------+
                   +-------------+         |
                                     ( instrument )
                                           v
                                    +--------------+
                                    | PARTIES   2  |
                                    +--------------+
                                           |
                                     ( Clerk link )
                                           v
                                    +--------------+
                                    | CHAIN     0  |
                                    +--------------+

   - - - context, never identity - - -
   [ FAA: 1 case within 400 m — NOT linked to this parcel ]
   [ Meetings: none with extracted folio evidence ]

   ///// STOPPED /////
   [ COMPANY ] Cannot resolve: company registry is empty.
               This is a data gap, not an absence of connection.
```

**Design requirements.** Missing joins render as an explicit **STOPPED** node with a plain-language reason — never a silent gap and never a dotted "maybe". Context edges are visually distinct (dashed, grey, lower position) and carry the words "not linked". Every node shows its record ID, event date and verification badge, and every node is clickable to the source. The map opens at depth 1 and expands one ring per click — never a full graph dump. Node counts appear before expansion so the operator can predict the cost.

---

## 8. Predictive intelligence maturity ladder

### 8.1 The ladder

| Level | Name | Claim permitted | Gate to enter |
|---|---|---|---|
| **L0** | **Record** | "This was filed on this date." | Source + receipt |
| **L1** | **Descriptive change** | "Filings rose 18% vs the trailing 12-month median." | Baseline with n ≥ 30, stated window |
| **L2** | **Diagnostic correlation** | "This rise co-occurs with deed activity on the same parcels." | Both legs Tier-A joins; correlation stated as correlation |
| **L3** | **Leading indicator** | "This measure has historically preceded X by N days." | Backtested lead/lag on ≥ 12 months, published hit rate |
| **L4** | **Forecast** | "We expect X within N days, with confidence C." | Registered forecast record + scheduled scoring job |
| **L5** | **Outcome / backtest** | "We predicted X; here is what happened." | Scored outcome published, hit and miss alike |

**Absolute rule:** unbacktested model prose is **L2 at most**, is labelled *Hypothesis*, and may never use the words *predict*, *forecast*, *will* or *expected*. Nothing enters L4 without a row in the forecast register and a scoring job that will run whether the desk likes the answer or not.

### 8.2 Initial honest indicators

| Indicator | Measure | Data available today | Entry level |
|---|---|---|---|
| **Transfer-to-permit lag** | Days from deed recording to first permit on the same folio | Yes — both feeds, exact folio join | L1 now, L3 after 12-month backtest |
| **Permit-sequence escalation** | Ordered scope progression on one folio (demolition → structural → new build) | Yes — single source | L1 now, L3 credible |
| **Neighborhood filing momentum** | Count/value vs trailing-12-month distribution | Yes — 12 months cached | L1 now |
| **Contractor/operator concentration** | Distinct folios per party per neighborhood per 90 days | Partially — names normalize, entities do not resolve | L1 caveated; L2 blocked until company registry populated |
| **Clerk instrument / capital chains** | Chain depth and type sequence from the link graph | Yes — ~76,267 rows, currently unused | L1 now |
| **Meeting-to-decision flow** | Latency from agenda appearance to recorded outcome | No — meetings not persisted | Blocked |
| **FAA precursor** | Crane filing preceding permit on nearby parcels | Yes, as proximity only | L2 ceiling — proximity is not identity |
| **FDEP precursor** | Environmental permit preceding site work | Yes | L2 |

### 8.3 Forecast register

```sql
create table forecast_register (
  forecast_id        text primary key,
  indicator_key      text not null,
  subject_type       text not null,        -- parcel | neighborhood | party | citywide
  subject_id         text not null,
  statement          text not null,        -- plain-language, falsifiable
  horizon_days       int  not null,
  issued_at          timestamptz not null,
  resolves_at        timestamptz not null,
  model_id           text not null,
  model_version      text not null,
  training_window    daterange not null,
  evidence_window    daterange not null,
  baseline_method    text not null,        -- what it must beat
  baseline_value     numeric,
  point_estimate     numeric,
  ci_low             numeric,
  ci_high            numeric,
  confidence_label   text not null,        -- low | moderate | high, defined numerically
  known_confounders  text[] not null,      -- may not be empty
  issued_by_role     text not null,
  -- scoring, written only by the scoring job
  outcome_observed   numeric,
  outcome_at         timestamptz,
  scored_result      text,                 -- hit | miss | partial | void
  scoring_notes      text
);
```

**Publication rule:** a forecast may be published only if `known_confounders` is non-empty, `baseline_method` is populated, and `resolves_at` is in the future. The scored outcome is published on the same surface as the original forecast, with equal prominence, whether hit or miss. Calibration (predicted confidence vs realised hit rate) is published quarterly.

**Known confounders to name by default:** permit backlog changes at the agency; seasonality and hurricane-season effects; nominal `$10` deeds and intra-family transfers; source QA lag reclassifying preliminary records; and coverage gaps (roughly one in five permits currently has no verified parcel).

---

## 9. Multi-model intelligence lab

### 9.1 Safety boundary — non-negotiable

- Models receive a **sealed, minimized, read-only evidence packet**. No database connection, no service credential, no write path, no scheduler access.
- Packets are minimized to the records under examination. No bulk party exports, no contact data, no subscriber data, no credentials.
- Model output is **Research Leads and Hypotheses only**. A model can never set Signal or Brief status.
- Every output passes a **receipt checker** before a human sees it: each asserted claim must map to a record ID present in the input packet. Unmapped claims are stripped and flagged, not silently dropped.
- A **human gate** stands between every Lead and any Signal or Brief.
- Quarantined datasets (historical pilot, synthetic seed) are never included in a packet.

### 9.2 Roles

| Model | Role | Input | Output | Must never |
|---|---|---|---|---|
| **Claude** | Evidence reasoning, contradiction detection, timeline construction; and — in a separate lane — independent audit | Sealed packet only | Contradictions, timeline, unknowns, targeted follow-up questions | Grade its own proposals; approve; publish |
| **Gemini** | Document, table, image and PDF extraction (agendas, recorded instruments, site plans) | Document + extraction schema | Structured fields with page/line locators and per-field confidence | Assert identity across documents |
| **Grok** | Current-web and open-source research | Neutral entity/topic string | Web findings, **hard-separated** from official records, each with URL and retrieval timestamp | Be cited as a public record; enter an evidence packet as a source |
| **Codex** | Reproducible queries, detectors, tests, operational scripts | Schema + spec | Deterministic SQL/code plus tests | Run against production without review |

**Grok separation rule:** web research renders in a visually distinct panel labelled "Open-web context — not a public record", is never mixed into the Facts-supported list, and can never satisfy a claim slot.

### 9.3 Lab output schema

```json
{
  "lead_id": "lead_2026-08-12_0007",
  "packet_id": "pkt_504210410390_20260812",
  "packet_hash": "sha256:...",
  "runs": [
    { "model": "claude",  "version": "<pinned>", "prompt_version": "ev-reason-v3",
      "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "latency_ms": 0 }
  ],
  "agreements":    [{ "claim": "...", "models": ["claude","gemini"], "record_ids": ["..."] }],
  "disagreements": [{ "claim": "...", "positions": [{"model":"...","position":"...","record_ids":["..."]}] }],
  "citations":     [{ "record_id": "...", "source_table": "...", "event_date": "...", "url": "..." }],
  "web_context":   [{ "url": "...", "retrieved_at": "...", "claim": "...", "is_public_record": false }],
  "missing_evidence": ["Company registry empty — party identity unresolvable"],
  "exact_queries":    ["select ... -- deterministic, re-runnable"],
  "receipt_check":    { "passed": true, "unmapped_claims": [] },
  "status": "RESEARCH_LEAD",
  "human_gate": { "required": true, "decided_by_role": null, "decided_at": null }
}
```

**Blind protocol:** models analyse the same sealed packet independently and never see each other's output before submitting. **Disagreement is a first-class result** — it routes to the desk as "models disagree, here is exactly where", which is more useful than false consensus. Cost and version are recorded per run so any Lead can be reproduced or repriced.

---

## 10. Claude as independent auditor

**Separation of duties:** the model instance that proposes a Lead, drafts a Signal or writes code never audits that artifact. The audit lane runs as a distinct role with a distinct prompt and no authoring history in context.

### 10.1 Audit lanes

| Lane | Cadence | Checks | Fails when |
|---|---|---|---|
| **1 Freshness** | daily | All four clocks vs `feed_registry` contract | Any clock null or beyond `lag_fail` |
| **2 Schema / raw-normalized drift** | weekly | Normalized fields still reconcile to retained raw | Any field diverges without a version bump |
| **3 Duplicates / nulls** | daily | Natural-key duplicates; null rates vs trailing baseline | Duplicate on a natural key; null-rate step change |
| **4 Joins** | daily | VERIFIED / CONFLICT / UNRESOLVED distribution | Conflict rate moves >2σ; any conflict marked map-eligible |
| **5 Candidate claims** | per batch | Every claim maps to a record in its packet | Any unmapped claim |
| **6 Preliminary/verified labelling** | daily | No preliminary record rendered as verified anywhere | One instance |
| **7 Chart / count / search correctness** | weekly | Displayed figures recomputed independently; search returns 200 across all field types | Any mismatch; any non-200 |
| **8 UI / accessibility** | per release | Scroll height, control counts, font floor, skip links, focus order, disclosure roles, tap targets | Any P0 regression |
| **9 External context** | per Lead | Web findings never counted as records | One instance |
| **10 Model disagreement** | per Lead | Disagreements surfaced, not averaged away | A disagreement was silently resolved |
| **11 Prediction calibration** | quarterly | Predicted confidence vs realised hit rate | Calibration error beyond stated band |
| **12 Docs-vs-live drift** | monthly | Handoff docs vs observed production state | Any doc asserts a stale fact as current |
| **13 Operational failure** | daily | Job exit states, dead-letter depth, catch-up backlog | Any silent failure |

> Lane 12 has live precedent: prior documentation asserted a production hostname had no DNS answer, which independent checking disproved. Documentation drift is a real, recurring failure mode here.

### 10.2 Auditor powers and limits

**May:** read production read-only; recompute any displayed figure; file dated, evidence-backed issues; mark an artifact `DISPUTED`; block a release gate.

**May not:** rewrite a fact, edit a record, resolve its own finding, approve, publish, send, or alter schedules, Mailchimp state or publishing state.

```sql
create table audit_findings (
  finding_id     text primary key,
  filed_at       timestamptz not null,
  lane           text not null,
  severity       text not null,          -- P0 | P1 | P2
  subject        text not null,
  observed       text not null,          -- what was measured, with values
  expected       text not null,          -- contract violated
  evidence       jsonb not null,         -- queries, counts, screenshots, request/response
  reproduction   text not null,
  auditor_role   text not null,          -- never the authoring role
  status         text not null default 'OPEN',
  fix_ref        text,
  closed_by_role text,
  closed_at      timestamptz
);
```

A finding closes only when the Permanent-Fix Gate (§11) is fully satisfied — and never by the auditor that filed it.

---

## 11. Permanent-fix gate

Every defect must satisfy **all seven** before its finding closes:

1. **Reproducible failure** — exact steps, inputs and observed output recorded (e.g. *"search `808` on Permits → HTTP 500"* **[OBSERVED]**).
2. **Root cause** — the actual mechanism, stated (e.g. *"four leading-wildcard ILIKE predicates over ~133,401 rows with no trigram index → statement timeout"* **[INFERRED]**).
3. **Durable fix** in code, schema or process — not configuration cosmetics.
4. **Regression test** that fails before the fix and passes after, committed with it.
5. **Documentation update** in the same change.
6. **Monitoring / health signal** where the defect could silently recur.
7. **Before/after visual verification** for anything a human sees.

### Explicitly rejected patterns

| Rejected | Why | Required instead |
|---|---|---|
| **Raising the statement timeout** | Hides an unindexed full scan; fails again at scale | Exact-match routing plus proper indexes |
| **CSS hiding or clipping overflow** | Makes a layout defect invisible, not absent | Fix the layout constraint |
| **Static "updated daily" copy** | Fake freshness; the most dangerous patch in a journalism product | Render the real heartbeat, or render "unknown" |
| **Manually pasted source links** | Breaks silently and does not scale | Generate links from record IDs |
| **Catching an error and rendering an empty state** | Converts a failure into apparent emptiness | Distinguish *empty* from *failed* on screen |
| **Suppressing a console error** | Removes the signal, keeps the fault | Fix the cause |
| **Widening a card to hide clipping** | Moves the break to another viewport | Fix the sizing rule |
| **Rounding a wrong number until it looks right** | Fabrication | Fix the computation |

---

## 12. Sequenced roadmap with acceptance tests

### P0 — the desk must be usable and honest

| # | Action | Acceptance test |
|---|---|---|
| P0-A | Split the review queue by decision-readiness; render one card at a time | Review scroll height ≤ 3 screens; exactly one Approve control in the DOM at a time; candidates without an evidence packet are unapprovable |
| P0-B | Add a confirm step to Approve and Reject on every surface | Automated: dispatching a click on Approve without confirming performs no state change |
| P0-C | Fix search: exact-match routing (`folio:`, `instrument:`, `permit:`, `addr:`) plus trigram indexes before any fuzzy path | All field types return HTTP 200 in < 1 s; zero 500s across a 20-query suite; fuzzy search is behind an explicit "search all text (slow)" control |
| P0-D | Fix `[object Object] matching rows` | Counter shows a formatted integer or an explicit em dash; string `[object Object]` appears nowhere in the DOM |
| P0-E | Ship the shared header; logo links Home on all three surfaces | Click and keyboard-Enter from all three surfaces land on desk home; target ≥ 44 px; visible focus ring |
| P0-F | Open the evidence packet by default; make every record ID a working link | Zero packets render collapsed; every record ID resolves to a live source; `anchors in packet > 0` on every packet |
| P0-G | Generate an evidence packet for every candidate, or quarantine those without | `cards_with_packet == cards_in_approval_path`; the gap count is displayed, never hidden |
| P0-H | Emit `last_process_ok` and `last_publish_ok` heartbeats | Every category returns all four clocks; null renders amber, never green |

### P1 — the intelligence layer

| # | Action | Acceptance test |
|---|---|---|
| P1-A | Expand the freshness board from 9 to 23 categories | Every category in §6.2 appears with four clocks, owner job and failure action |
| P1-B | Build the lineage map (exact edges only) | Injected fixtures: a missing join renders STOPPED with a reason; a proximity edge can never be promoted to identity; address- and name-similarity edges are impossible to construct |
| P1-C | Ship indicators at L1 with published baselines | Each indicator states window, baseline and n; suppressed when n < 30 |
| P1-D | Stand up the multi-model lab with receipt checking | A claim absent from the packet is stripped and flagged; web findings never enter Facts-supported; every run records model, prompt version and cost |
| P1-E | Start audit lanes 1, 5, 6, 7, 13 | Findings filed with evidence; the authoring role cannot close its own finding |
| P1-F | Replace the JSON claim-slots textarea with a structured builder | An editor can add a claim with source and locator without typing a brace; malformed state is impossible |
| P1-G | Semantic status colour with non-colour equivalents | HEALTHY, LAGGING, FAILING, PRELIMINARY, SYNTHETIC each visually distinct with icon and text; passes a greyscale check |
| P1-H | Typography floor: no rendered text below 12 px | Zero computed `font-size` below 12 px across all three surfaces |

### P2 — depth and durability

| # | Action | Acceptance test |
|---|---|---|
| P2-A | Backtest indicators over ≥ 12 months; promote qualifying ones to L3 | Published hit rate and lead/lag distribution per indicator |
| P2-B | Open the forecast register; publish scored outcomes | Every L4 statement has a scored outcome published at equal prominence |
| P2-C | Persist meetings; add agenda-to-parcel extraction under explicit evidence rules | A meeting edge exists only with a human-confirmed extracted locator |
| P2-D | Self-host fonts; replace the masthead PNG with SVG | Desk renders correctly with external network blocked; masthead < 20 KB |
| P2-E | Mobile breakpoints below 620 px; decisions desktop-only | At 390 px: no horizontal scroll, no clipping, ≥ 44 px targets, Approve and Reject absent |
| P2-F | Per-candidate permalinks | Any candidate is linkable and deep-loads directly |
| P2-G | Remaining audit lanes (2, 3, 4, 8, 9, 10, 11, 12) on cadence | Each lane produces a dated report; failures block the release gate |

---

## 13. Unknowns and access limits

| # | Item | Detail |
|---|---|---|
| U-1 | **True 390 px rendering** | The resize tool reported success at 390×844 but the viewport remained 1470 px. All mobile findings are **[INFERRED]** from CSS: only two media queries exist (`720px`, `620px`), so nothing is tuned below 620 px. Clipping, tap targets and overflow at 390 px are unverified. |
| U-2 | **Console errors at page load** | Console tracking begins when first invoked, which was after load. No errors captured; load-time errors would have been missed. |
| U-3 | **Which key the Data Desk ships to the browser** | The Data Desk queries the database directly from the client, so a key is present in the page. It was deliberately not read; one scripted query was auto-blocked for touching query-string data and was not retried. **The operator should confirm it is the publishable anonymous key and not a privileged one.** Review and Editorial Desk correctly proxy through the local server. |
| U-4 | **Behaviour of Approve / Hold / Reject / Save / Confirm decision** | Not clicked, by instruction. Whether Review has any server-side confirmation is unverified. |
| U-5 | **Empty and error states of the review queue** | The queue held 158 NEW candidates; empty and failed states were not forced. |
| U-6 | **Whether the "All" status filter works** | Its option value is an empty string; a programmatic change did not refetch. **[INFERRED]** it requires RELOAD. |
| U-7 | **Whether feed history is retained** | Determines whether trend-delta and backtesting modules are honestly buildable. |
| U-8 | **Cards 9–158 in detail** | Cards 1–2 inspected visually; the remaining 156 programmatically (counts, structure, packet presence). |
| U-9 | **Contrast ratios** | Not measured. The 10 px muted grey on white is the first to check. |
| U-10 | **Processing and publication clocks for every category** | No such clock is exposed anywhere in the desk today. §6.3 specifies the exact contract required. |
| U-11 | **Cadence, owner job and coverage for 11 categories** | Permit workflow (FOIA) events, Clerk parties/legals/link graph, BCPA property cards, contractor licences, owner resolution, meetings, detectors/editorial jobs, analytics/newsletter — all absent from the board. |
| U-12 | **Print and export paths** | Not examined. |

---

## 14. The three things to do first

1. **Split the review queue by decision-readiness and render one card at a time.** This converts 158 impossible decisions into 8 real ones and 104,018 px into roughly three screens, addressing the wall-of-text problem, the safety problem and the cognitive-load problem in a single change.

2. **Fix search with exact-match routing before any fuzzy path.** Folio, instrument and permit lookups are indexed equality queries that return instantly and never time out. Today the desk's primary lookup returns HTTP 500 for every query.

3. **Open the evidence by default, make every record ID clickable, and wrap the logo in an anchor to a real desk home.** The evidence packet is already the best thing built here — it needs to be the first thing seen rather than the last thing found.

---

*Prepared by the Florida Signal desk. Read-only audit; no application code, database, queue, setting, schedule, Mailchimp state or publishing state was modified. This document is the sole file written.*
