# FLORIDA SIGNAL — VERIFIED CHECKPOINT
**2026-07-19 · Graham & Gold LLC · every claim below was verified directly, not copied from chat**

> **START HERE.** If you are a new agent or a returning human, read §1 and §2 first. They tell
> you which authority owns what. Getting that wrong is the most common and most expensive error
> in this project.

Nothing was merged, deployed, published or scheduled to produce this document. No database
object, schedule, service or application behaviour was changed. No secrets appear here.

---

## 1. AUTHORITIES — who owns what

| Authority | Owns | Do not look here for |
|---|---|---|
| `grahamandgold/florida-signal-site` | public website, maps, SignalV1 adapters, Data Desk, Data Wire CMS | the scorer, collectors, detectors |
| `grahamandgold/florida-signal` | collectors, deterministic Signal Machine, scorer, shadow runs, detector specs, runtime scripts, ops docs | the public site |
| **DigitalOcean `florida-signal-runtime`** | **production runtime** — all timers and collectors | code authority (that is GitHub) |
| **Supabase `florida-signal-prod`** | **database authority** | code or documentation authority |
| **Google Drive (Graham & Gold Shared)** | **documentation authority** | code |
| Andy's Mac | ONE residential dependency (Acclaim) + the recovered scoring corpus | production authority — **it is not** |
| `archive-florida-signal-grok-demo`, `~/Downloads/florida-signal-*` (8 copies) | historical evidence only | anything current |

**The single most common orientation error:** looking for scoring work in the site repo. It is
not there. It is in `grahamandgold/florida-signal`.

---

## 2. VERIFIED CURRENT STATE (checked 2026-07-19 evening)

### GitHub

Three different HEADs get confused in this project, so they are named separately here.

| Item | Verified value |
|---|---|
| Site repo branch | `claudette/launch-day` |
| **Prior product-code HEAD** | **`8daad11`** — the last commit that changed application behaviour (map lockup asset versioning, overlay z-order, CSS consolidation). **This is the commit that describes what the site currently does.** It is stable and safe to cite. |
| **Current documentation HEAD** | **Deliberately not pinned here.** Every commit after `8daad11` on this branch is documentation-only. A document that records its own SHA is stale the instant it is committed — verify live with the command below. |
| **Remote PR #1 head** | Equal to the local documentation HEAD. Verified 0 unpushed and 0 uncommitted at the time of writing. |
| `origin/main` (site) | `ba45b46` — PR #1 has never been merged into it |
| PR #1 status | **OPEN · DRAFT · NOT MERGED** (verified via `gh pr view 1 --json mergedAt` → null) |
| Mergeability | `MERGEABLE` / `CLEAN` when last computed. **It cannot be merged because it is a DRAFT.** That is the only blocker — there is no conflict and no rebase is needed |
| Engine repo HEAD | `12f3d7b` on `main` |

```bash
# Verify the live documentation HEAD and PR state in one step:
cd "~/Documents/FL SIGNAL SITE BUILD" && git fetch origin -q \
  && echo "local  $(git rev-parse --short HEAD)" \
  && echo "remote $(git rev-parse --short origin/codex/florida-signal-rebuild)" \
  && echo "unpushed $(git rev-list --count origin/codex/florida-signal-rebuild..HEAD)" \
  && gh pr view 1 --json headRefOid,isDraft,state,mergedAt
```

> **Verification note (two corrections, preserved rather than overwritten).**
> 1. An earlier draft recorded the PR head as `8daad11`. That reading came from a `gh pr view`
>    issued in the same shell command as the push, before GitHub had recomputed the ref — an API
>    cache race, not a real divergence. Re-verified from three independent sources (local
>    `git rev-parse`, the `origin/` remote ref, and the GitHub API `headRefOid`), all agreeing.
> 2. A later draft pinned the documentation HEAD as `ce1493a`, which went stale on the next
>    documentation commit. **The lesson is recorded here on purpose: never pin this document's
>    own SHA.** Pin the product-code HEAD, which is stable, and verify the rest live.

### DigitalOcean — `florida-signal-runtime` (production)
**Deployed path `/srv/grahamandgold/florida-signal/app` is at `12f3d7b` on `main` — identical to
the engine repo HEAD. The droplet is current.**

12 active timers verified: `florida-parcelmatch` · `florida-dataroom` · `florida-gisowner` ·
`florida-health` · `florida-sync` · `florida-enrich` · `florida-intake` · `florida-sunbiz` ·
`florida-backup` · `florida-offsite-backup` · **`florida-signals-shadow`** · `florida-parity-audit`.

`florida-signals-shadow.timer` last fired 2026-07-19 05:45, next 2026-07-20 05:45 — **that is
shadow run 5 of 5.**

### Supabase — `florida-signal-prod`
| Measure | Verified |
|---|---:|
| Broward parcels | **532,470** |
| Range ledger COMPLETE / total | **110 / 110** |
| Deeds map-eligible (matview) | **10,235** |
| Easements map-eligible | **452** |
| Review queue rows / decided | 150 / **0** |
| `signals` (v1) | 10,574 |
| `signals_v2` | 250 |
| `land_sales` (**synthetic**) | 10 |
| Clerk official records | 149,963 |
| Permits | 127,945 |
| Active pg_cron jobs | 4 |

**This checkpoint performed NO writes to Supabase.**

### Mac — residential dependency
**Exactly ONE launch agent is loaded: `com.floridasignal.acclaim` (last exit 0).**
19 other `com.floridasignal.*` plists exist in `~/Library/LaunchAgents/` but are **NOT loaded**.
Their presence on disk is not evidence that they run. Anyone auditing agent count must use
`launchctl list`, not `ls`.

### Google Drive — documentation authority
Canonical documents located: `GRAHAM_AND_GOLD_START_HERE` (Google Doc, 2026-07-15) ·
`START_HERE_GRAHAM_AND_GOLD.md` · `GRAHAM_GOLD_SOURCE_OF_TRUTH.md` ·
`GRAHAM_GOLD_CANONICALITY_DECISION.md` · `FLORIDA_SIGNAL_AI_HANDOFF_2026-07-16_rev2_EOD.md` ·
`MAC_LOSS_RISK_REPORT.md` · `COMMAND_CENTER.md` · notification/alert runbooks.

Drive already uses the convention `SUPERSEDED — PRESERVED FOR HISTORY — <name>_<date>.md`.
**Keep using it. Do not delete superseded documents.**

**Drive holds NO scoring specification.** This is a confirmed negative, independently
corroborated by `docs/FLORIDA_SIGNAL_BRIEF_SPEC_v2.md`, which records that the original was
"confirmed absent from every document authority (repo, droplet, Drive — searched 2026-07-14/15)".

---

## 3. PARCEL AND PROPERTY STATE — verified

**Source:** Broward County GIS `PARCEL_POLY_BCPA_TAXROLL/FeatureServer/0` (public).

| Measure | Value |
|---|---:|
| Official source count | 554,358 |
| Ranges complete | 110 / 110, **0 gaps, 0 overlaps** |
| Rows received | 554,358 — exact match |
| Accepted | 539,213 |
| Rejected | 50 (centroid outside the Broward bbox; 3 ranges; 0.009%) |
| Duplicate folios collapsed | 21,838 |
| **Final unique parcels** | **532,470** |
| Numeric / alphanumeric folios | 482,572 / 49,898 |
| Address coverage | 524,214 (98.5%) |
| Municipality coverage | **0 — see below** |

`554,358 − 50 − 21,838 = 532,470.` Fully reconciled.

**Normalization rule (authoritative):** `upper(regexp_replace(raw,'[^A-Za-z0-9]','','g'))`, must
be exactly 12 characters, reject all-zero sentinels. Broward folios are **ALPHANUMERIC** —
letters and leading zeros are significant.

**Prior failure — preserved for history:** an earlier digits-only normalization corrupted
alphanumeric folios and produced false collisions, inflating a duplicate figure to 1,096 / 7.9%
when the correct baseline was 737 / 5.0%. **Persisted impact: NONE found.** `parcel_backfill`
looks digits-only (24,553 of 24,558) but that is a *coverage characteristic* of address and
spatial matching, not corruption — 95.9%/97.2%/80.5% of its folios by method verify exactly
against the official layer.

**Municipality limitation:** the county publishes `MUNICIPALITY` **empty for all 554,358 rows**.
The only city value is `SITUS_CITY`, a two-letter county code with no published lookup table.
No city label is guessed anywhere in the product.

### Linkage — verified
| | Deeds (`D`) | Easements (`EAS`) |
|---|---:|---:|
| Instruments | 15,487 | 502 |
| Mappable / match rate | 10,337 / 66.75% | 461 / 91.83% |
| **Map-eligible** | **10,235** | **452** |
| CONFLICT (multi-parcel) | 104 | 9 |
| UNRESOLVED (folio absent) | 4,805 | 11 |

**Mortgages, liens, lis pendens and judgments are NOT map-eligible and cannot be made so from
the current Clerk SFTP feed.** Verified: only deed-type instruments carry `parcel_id` in the
`lgl-ver` legal file, and `broward_clerk_records_link` does not reach a parcel-bearing
instrument (mortgages 1 of 10,357 inheritable, liens 0, lis pendens 0, judgments 0). This is a
source limitation, accepted by decision. Treat as a separate future-source project.

**`broward_property_transfer_map` is a MATERIALIZED VIEW with NO schedule. It does not refresh
itself.** New Clerk records will not appear on the map until someone runs
`refresh materialized view concurrently public.broward_property_transfer_map;`.

### Layer separation — do not collapse these
1. **SOURCE RECORD** — the Clerk instrument or county parcel row as published.
2. **VERIFIED CONNECTION** — exact canonical folio equality, `DIRECT_EXACT_FOLIO`, nothing else.
3. **SIGNALV1 ADAPTER OUTPUT** — a Signal object with safe wording and exclusion reasons.
4. **CMS CANDIDATE** — a row in `signal_review_queue`. **Approval records a decision; it publishes nothing.**
5. **PUBLICATION** — a separate human act that has not happened.

**The property adapter connects deeds and easements to parcels by folio. It does NOT connect
Sunbiz, media, or "every other source." No such relationship is implemented.**

---

## 4. PRODUCT STATE — verified this session

- **Brand:** new wordmark + Florida emblem lockup, `assets/lockup-2026-v2.png` (1800×248) and
  `lockup-2026-v2-light.png`. **The filename is versioned deliberately** — the previous asset
  was replaced under its old name and browsers served the stale file, producing a large white
  pill with a tiny logo on every map. Never replace a logo in place; bump the version.
- **All 8 maps verified** at 1456 and mobile: `home-map`, `signal-spotlight-map`,
  `mobile-field-map`, `full-map`, `data-room-map`, `meeting-spotlight-map`, `agenda-recon-map`,
  `storm-spotlight-map`. Badge 304×56 desktop / 178×36 mobile, inside map bounds, no legacy markup.
- **Map overlays hide entirely when a Signal card is open** (visibility + opacity, not fade).
- `.map-signal-control` now has **ONE authoritative CSS block** — previously five scattered rules
  plus ~29 dead declarations; a stale one outranked the live rule twice in one session.
- `html` and `body` both carry `overflow-x: clip` — previously only `body`, so pages scrolled
  ~6px sideways on mobile.
- **Map source families:** Development (permits/demolition/storm) · Property & Money
  (deeds, easements) · Environment (FDEP) · Skyline (FAA). **Government and Risk & Legal are
  declared "not connected yet" with the reason shown** — never presented as complete coverage.
- **Search:** address, folio, Clerk instrument, permit number, owner/party. A no-match states
  what was searched and that mortgages/liens/LP/judgments are not searchable, and why.
- **Per-request cap is 600 per source.** The readout says so explicitly when a source is capped.
- **Data Wire = LOOK → DECIDE → WRITE** (ADR-001): Data Desk (read-only, every source raw) →
  Signal Review (approve/hold/reject/needs-more-reporting) → Editorial Desk (source-gated packets).
  Shared stage navigation on all three surfaces.

**Known remaining product issues:** intentional sub-10px micro-labels on several interior pages
(editorial choice, flagged not fixed); some sub-30px tap targets on interior pages.

---

## 5. SCORING AND DETECTION — honest state

| Fact | Status |
|---|---|
| Legacy rules defined | **21** |
| Rules historically observed firing | **17** (verified by query) |
| Current engine | `detect_signals_v2.py` **`ENGINE_VERSION = "2.6.0"`**, deterministic, zero model calls |
| Version history | v2.1 → v2.6, all 2026-07-15, PRs #31–#38, each traceable to an observed failure |
| Shadow runs fired | **4** (07-16, 07-17, 07-18, 07-19 — artifacts verified on the droplet) |
| Shadow runs **reviewed** | **2** (07-16, 07-17). Runs 3 and 4 fired but are **UNREVIEWED** |
| Freeze | **ACTIVE.** Scorer logic frozen until all five runs are reviewed |
| Run 5 | fires 2026-07-20 05:45 ET |
| Historical backtest | **NONE has ever been run** |
| Prediction precision / false-positive rate | **UNKNOWN — never measured** |
| Strongest **implemented** model | **v2.6** |
| Strongest **designed** model | **March 2026 editorial specification (local Mac)** |
| Relationship | **v2.6 is a SUBSET of the intended machine, not a proven replacement** |

**F6/F7 ranking inversion (open, non-severe):** run 1 ranked `BLD-SHUT-26050659`, a condo
hurricane-shutter permit (importance 3.6), above `BLD-GEN-26070308`, a **$2,012,358** structural
application at Point of Americas Condo II (importance 3.1). Cause: the shutter permit inherited
its project group's stacked rules on a folio with $4.2k of history. Spec-legal, editorially
wrong. Deferred to post-run-5 by the freeze.

### Local scoring corpus — `~/ANDY_DIGITAL_HOME/06_GRAHAM_AND_GOLD/02_FLORIDA/`
**193 notes** (Apple Notes/iCloud rescue, `classification: PRESERVE`), plus `GROK_LAB_RECOVERED/`
(`florida-signal-cloud`, `quarantine_unique`, `sanitized_copy_unique`), `AUDIT_NOTES/`,
`HISTORICAL_PRODUCTS/Florida_Signal_Desktop_2026-07-14/`, `downloads-florida-signal/`,
`florida-signal-machine-live.pdf`.

Confirmed present and read:

| Note | Title | Created | Lines |
|---|---|---|---:|
| N0013 | GROK SCORING: Florida Signal Engine — V1 | 2026-03-17 | 62 |
| N0017 | Canal Waterfront Pre-Signal Cluster (KEEP) | 2026-03-17 | 54 |
| **N0083** | **INTELLIGENCE ENGINE v2.0** | 2026-03-27 | **1,361** |
| **N0089** | **MACHINE 2.1: REBUILD** | 2026-03-27 | **1,011** |
| N0086 | FILE 3 — APPROVED SIGNALS | 2026-03-27 | 14 (**body empty**) |
| **N0014** | **Signal Machine: THE GROK DATA — DON'T ERASE** | — | 92 |
| N0015 | Signal Machine Steps — Operating System (V1) | — | 221 |
| N0068 | ALL SIGNALS (worked examples) | — | 368 |
| N0090 | OUTPUTS MACHINE 2.1 (detection prompt) | — | 122 |
| **N0133** | **COMPLETE SYSTEM** | — | **2,827** |
| N0253 | Cross-Source Signal Thinking — Crossover Triggers | — | 203 |

**N0014 is materially important and was nearly missed.** It contains a hidden-signal taxonomy
("70–90% predictive when they appear"): sewer-cap / water-meter changeout after seawall permits
in canal zones · FAA crane filings >200 ft preceding vertical · soil borings / coastal
resilience review before foundation · utility capacity reservation as a unit-count clue ·
ROW paving/sidewalk after demolition · **NOC within 45 days of structural as "the single
strongest hidden confirmer"** · backflow installation. It also contains a **false-positive
taxonomy**: vesting bluff (HB 1389 rush filings), refi/appraisal inflation, zombie renovation
(high value, no follow-up after 90 days), fake value on PXA affidavits.

### March specification dimensions — implementation status

| Dimension | Status |
|---|---|
| Sequence (0–5) | **DESIGNED — NOT IMPLEMENTED** · likely **BLOCKED BY DATA** (see §6) |
| Coordination (0–5) | **PARTIALLY IMPLEMENTED** — v2.1 project grouping covers part |
| Momentum (0–5) | **PARTIALLY IMPLEMENTED** — v2.2 recency gate is binary, not 0–5 |
| Relevance (0–5) | **DESIGNED — NOT IMPLEMENTED** |
| Scale and Value (0–5) | **PARTIALLY IMPLEMENTED** — v2 value family + v2.5 $100k floor |
| Neighborhood Modifier (0–2) | **DESIGNED — NOT IMPLEMENTED** in the scorer; crude address-keyword approximation exists in `context_boosts.py` (inactive) |
| Radius Context Modifier (0–2) | **DESIGNED — NOT IMPLEMENTED** |
| Pattern Floor Rule | **DESIGNED — NOT IMPLEMENTED** |
| Historical Baseline Check | **DESIGNED — NOT IMPLEMENTED** |
| Entity Intelligence | **PARTIALLY IMPLEMENTED** — `seeded_developer_match` rule only |
| Journalism Integrity Score (5–25) | **DESIGNED — NOT IMPLEMENTED** |
| Human publication gate | **IMPLEMENTED** — CMS review queue; approval publishes nothing |

**All of the above: NOT TESTED. No backtest exists for any dimension.**

### STILL UNREAD — scoring evidence is NOT complete
Of ~40 scoring-relevant notes, **11 have been read**. Unread and potentially material:
N0016, N0037, N0057, N0128, N0207–N0210 (WHAT FIELDS MATTER — Grok/ChatGPT/Gemini/Claude),
N0237–N0242 (DATA-BIZ ASSESSMENTS + CLAUDE BIG COMBINED REPORT), N0252, N0254 (SCORING TAG
IDEAS), N0030, N0027, N0020, N0024–N0029, N0033–N0059 series, N0375 (folder index) — and the
entirety of `GROK_LAB_RECOVERED/`. **Do not tell any reviewer the scoring evidence is complete.**

---

## 6. SIGNAL TERMINOLOGY — proposed, scorer unchanged

- **SOURCE EVENT** — a factual source record or verified source change.
- **CORE SIGNAL** — a new, verified, potentially meaningful event passing deterministic
  eligibility and relationship requirements.
- **CONTEXTUAL SIGNAL** — a Core Signal evaluated against project, parcel, neighborhood
  baseline, geography, media, actor history and comparable activity.
- **PREDICTIVE HYPOTHESIS** — a forward-looking inference, separately labelled, **backtested**,
  with uncertainty and confirming/disconfirming conditions.
- **EDITORIAL PRIORITY** — a human-facing ranking for review and destination.

**Rules:** a Signal can exist without a score · a Signal can exist without publication · model
research does not prove a fact · scoring does not replace journalism verification ·
**Andy is the final editorial authority.**

**Data constraints that bound all of the above (independently verified):**
`accela_inspections` contains **no outcomes** — only `Pending` (50,274), `Scheduled` (651) and
null (91,213); zero pass, zero fail, zero completed dates. `accela_details` records
`finalized_date` on **71 of 92,510** permits. `foia_workflow_events` has 2.4M rows spanning
2002–2026 with a full review pipeline but **only a primary-key index** — every join is a 367 MB
sequential scan. BCPA tables cover **0.8%** of parcels. These constraints make Sequence scoring
and review-duration benchmarks harder than the March specification assumes.

---

## 7. SYNTHETIC AND HISTORICAL MATERIAL

### RISK REGISTER — ADD
> **Synthetic land-sale records contain realistic-looking prices and deed-like identifiers and
> may be mistaken for verified public records.**
> `land_sales` — 10 rows, all `source='seed:dry-run'`, sequential fake CINs 111900000001–010,
> prices $300k–$35M, none present in the Clerk feed. `land_sale_signals` — 59 rows scoring them.
> **CANDIDATE FOR ARCHIVE — DO NOT DELETE YET.**

**Exposure paths verified:**
| Path | Detail |
|---|---|
| **Supabase RLS** | `anon_read_land_sales` and `anon_read_land_sale_signals`, both `USING (true)` — **publicly readable with the anon key** |
| Data Desk | feed-health card + explorer preset in `cms/data.html` |
| Engine repo | `detect_sales_signals.py`, `enrich_land_sales.py`, `generate_digest.py`, `render_data_room_local.py`, `_dashboard_data.py`, `sync_to_supabase.py`, `generate_tech_updates.py`, `audit_supabase_parity.py` |
| Map / Signal Review / Editorial Desk / brief | **no path found** |
| Backtest | would be affected if a backtest ever reads `land_sales` |

**No-delete isolation plan (proposed, NOT executed, needs Andy's approval):** add `is_synthetic`
flag → **revoke the two anon policies** → filter every read path → relabel the Data Desk preset
→ never let either feed map, brief, CMS or Signal. Every step reversible; nothing deleted.

Other historical material — **preserve, do not surface**: `signals` (10,574) · `signals_v2` (250)
· `signals_v2_context` (200) · `tier3_briefs` (6) · `leads` (36) · recovered dashboards ·
8 duplicate `florida-signal-*` working copies in `~/Downloads`.

---

## 8. CONTRADICTIONS RESOLVED — superseded, preserved for history

| Claim | Correct as of 2026-07-19 | Status of old claim |
|---|---|---|
| Parcel import 72.9% / 404,082 rows | **COMPLETE — 532,470 / 110 ranges** | **Historically correct at the time**, superseded |
| Deeds mappable = 7,903 | **10,337 mappable / 10,235 map-eligible** | Historically correct pre-import |
| Duplicate folios 1,096 / 7.9% | **737 / 5.0%** | **WRONG** — digits-only normalization artefact |
| "No Brightline / neighborhood / rarity logic exists" | **Exists** — in `context_boosts.py` (address keywords, inactive) and in the March spec (designed) | **WRONG — incomplete search.** I audited the scorer and Supabase, not the whole corpus |
| "Scoring evidence COMPLETE" | **INCOMPLETE** — 193-note local corpus, ~29 scoring notes unread | **WRONG — the Mac was never searched** |
| 17 vs 21 rules | **21 defined, 17 observed firing** | Both partially right, now reconciled |
| Mac agent count from `ls` | **1 loaded** (`launchctl list`), 19 plists idle on disk | Misleading method |
| Acclaim location | **Mac LaunchAgent** — the one residential dependency | correct |
| Clerk catch-up location | **Droplet systemd** — migrated off the Mac | correct |
| Map logo asset | **`lockup-2026-v2.png`** — versioned filename | old unversioned name superseded |

---

## 9. IMMEDIATE NEXT CHECKPOINT

1. **2026-07-20 05:45 ET — shadow run 5 fires.** Then review runs **3, 4 and 5** (only 1 and 2
   are reviewed). Only after all five are reviewed does the freeze lift and F6/F7 tuning open.
2. **Read the ~29 unread scoring notes + `GROK_LAB_RECOVERED/`** before any multi-model scoring
   review is sent. The current packet would mislead every reviewer.
3. **Decide the synthetic-data isolation plan** (§7). The anon-read revocation is the single
   highest-value step.
4. Decide the `broward_property_transfer_map` refresh cadence (currently manual by design).

### Requires Andy's approval — nobody else
Merging PR #1 (it is a draft) · any deploy or publish · activating any detector or scorer ·
creating any schedule · lifting the scorer freeze · the synthetic-data isolation plan ·
revoking anon policies · restarting any service · any credential change.

### How to verify this state yourself
```
# site repo
cd "~/Documents/FL SIGNAL SITE BUILD" && git status -sb && gh pr view 1 --json isDraft,mergeable,state
# droplet
ssh florida 'systemctl list-timers --all | grep florida; git -C /srv/grahamandgold/florida-signal/app rev-parse --short HEAD'
# mac agents (use launchctl, NOT ls)
launchctl list | grep florida
# database
select count(*) from broward_parcel_geography;
select status, count(*) from broward_parcel_range_ledger group by 1;
```

### Rollback references
Parcel import: `drop table broward_parcel_geography, broward_parcel_import_runs, broward_parcel_range_ledger; drop function fs_normalize_folio(text);`
Shadow timer: `sudo systemctl disable --now florida-signals-shadow.timer` then remove the unit files — the run has no side effects beyond artifact files.
Site changes: unmerged on PR #1; reverting the branch reverts everything.

---

## 9b. DOCUMENTATION AUTHORITY — decision, risk, to-do (added 2026-07-19)

### DECISION LOG — ADD
> **The canonical Florida Signal AI handoff and verified operating checkpoint live in
> `00_Company_Admin` alongside `GRAHAM_AND_GOLD_START_HERE`. Backup and recovery folders
> preserve historical snapshots and are not the authority for current operating documentation.**

Canonical Drive location for this document:
`Graham & Gold Shared Drive / 00_Company_Admin / FLORIDA_SIGNAL_VERIFIED_CHECKPOINT_2026-07-19.md`

### RISK REGISTER — ADD
> **The prior authoritative Florida Signal AI handoff was stored inside a dated
> backup/recovery subtree, creating a risk of misclassification or loss during backup cleanup.**

Verified path of the prior handoff:
`Graham & Gold Shared Drive / 08_Backups_and_Recovery / Mac_Recovery_2026-07-12 /
04_RECOVERY_REPORTS_AND_MANIFESTS / FLORIDA_SIGNAL_AI_HANDOFF_2026-07-16_rev2_EOD.md`
It remains in place — not moved, renamed or deleted — with a companion supersession note
beside it pointing to this checkpoint.

### MASTER TO-DO — ADD
> **Audit the Shared Drive for other current authoritative documents stored only inside
> migration, backup, snapshot or recovery folders. Do not move anything until authority and
> dependencies are verified.**

---

## 10. DOCUMENTS SUPERSEDED BY THIS CHECKPOINT

- `DESKTOP_HANDOFF_STEP1_2026-07-19.md` — **SUPERSEDED — PRESERVED FOR HISTORY.** Reason:
  parcel counts and map status materially changed. Historically correct at the time.
- `SCORING_EVIDENCE_PACKET_2026-07-19.md` §5 and its status line — **SUPERSEDED — PRESERVED FOR
  HISTORY** by `SCORING_EVIDENCE_CORRECTION_2026-07-19.md`. Reason: the local Mac corpus was
  never searched, so "evidence complete" was wrong.
- `CLAUDETTE_HANDOFF_2026-07-19.md` parcel section — **superseded** by §3 above; the addendum
  in that file already records the completion.

Nothing has been deleted. All superseded documents remain in place.
