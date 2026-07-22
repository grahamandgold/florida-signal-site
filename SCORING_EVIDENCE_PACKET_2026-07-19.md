# Florida Signal — Scoring Evidence Packet
**Prepared 2026-07-19 · read-only inventory · identical packet for Grok, Gemini, Claude and ChatGPT**

No detector was activated. No score was written. SignalV1 was not changed. Nothing was
scheduled, merged, deployed or published.

---

## 0. Where the work actually lives

The scoring work is **not** in the site repo. It is in a second repository:

| Repo | Role |
|---|---|
| `grahamandgold/florida-signal-site` | public site + SignalV1 map layer (this working folder) |
| **`grahamandgold/florida-signal`** | **the Signal Machine: detectors, scorer, shadow runs, ADRs, QA logs** |
| `grahamandgold/archive-florida-signal-grok-demo` | archived demo (not audited here) |

Anyone reviewing scoring who is shown only the site repo will conclude no scoring work
exists. That is the single most important orientation fact in this packet.

---

## 1. Scoring Evolution Matrix

| Artifact | Date | Ver | Purpose | Status |
|---|---|---|---|---|
| `scripts/detect_signals.py` (63 KB) | pre-2026-05 | v1 | 21 deterministic detectors + Anthropic verdict calls | **SUPERSEDED for ranking — PRESERVED FOR HISTORY** (ADR-007) |
| `signals` table (10,574 rows) | 2026-04-20 → 05-02 | v1 | v1 output; 17 of 21 rules observed firing | **HISTORICAL** |
| `business/SCORING_V2.md` (418 lines) | 2026-04-26 | v2.0 | Gates + family weights + dedup + top-N, with full before/after top-20 | **HISTORICAL — foundational** |
| `signals_v2` (250 rows) | 2026-04-26 → 04-29 | v2.0 | v2 pilot output, 65 permits | **PROTOTYPE** |
| `signals_v2_context` (200 rows) | 2026-04-26 | v2.0 | location/operator/media context scoring | **PROTOTYPE** |
| `docs/ADR-007_signal_scorer_port_vs_replace.md` | 2026-07-15 | — | Port vs replace decision | **APPROVED DESIGN** (option B) |
| `detect_signals_v2.py` v2.1 (PR #31) | 2026-07-15 | 2.1 | Project grouping + reweights | **CURRENTLY IMPLEMENTED** |
| v2.2 / v2.2.1 (PR #31/#32) | 2026-07-15 | 2.2 | Hard recency/edition gate; future-date fix | **CURRENTLY IMPLEMENTED** |
| v2.3 (PR #33/#34) | 2026-07-15 | 2.3 | Fresh in-memory rule evidence; widened intake | **CURRENTLY IMPLEMENTED** |
| v2.4 (PR #35) | 2026-07-15 | 2.4 | Final editorial eligibility gate; provenance | **CURRENTLY IMPLEMENTED** |
| v2.5 (PR #36) | 2026-07-15 | 2.5 | Verified-trigger partition (MAIN vs NEEDS VERIFICATION) | **CURRENTLY IMPLEMENTED** |
| v2.5.1 (PR #37) | 2026-07-15 | 2.5.1 | Admin filings as editorial-minor; importance floor 1.5 | **CURRENTLY IMPLEMENTED** |
| v2.6 (PR #38) | 2026-07-15 | **2.6.0** | Corroborated exemption; candidate-grade cluster annotation | **CURRENTLY IMPLEMENTED (shadow only)** |
| `docs/SHADOW_RUN_PLAN_2026-07.md` | 2026-07-15 | — | Activation scope, rollback, exit criteria | **APPROVED DESIGN — ACTIVE** |
| `docs/SHADOW_REVIEW_LEDGER_2026-07.md` | 2026-07-16 → | — | Five-run editorial review ledger | **IN PROGRESS — 2 of 5 reviewed** |
| `docs/SCORER_QA_LOG_2026-07-15.md` | 2026-07-15 | — | Seven directives, version history, risk register | **CURRENTLY IMPLEMENTED** |
| `land_sale_signals` (59 rows) | 2026-04-21 → 05-02 | — | Scores `land_sales` | **UNSAFE — scores synthetic data** |
| `land_sales` (10 rows) | 2026-04-21 | — | All rows `source='seed:dry-run'`, fake CINs | **UNSAFE — synthetic, unlabelled in UI** |
| `tier3_briefs` (6 rows) | 2026-04-25 → 05-02 | — | Brief generation experiment | **HISTORICAL** |
| `scripts/validate_signals_ai.py` | — | — | OpenAI/Grok independent review | **APPROVED DESIGN — post-hoc only, never a gate** |
| `scripts/context_boosts.py` | — | — | Context boosting (not audited in depth) | **UNKNOWN** |

**No CONFLICTING artifacts found.** Every superseded version is explicitly marked and the
supersession reason is recorded.

---

## 2. The 17-rule vs 21-rule question — resolved

**Both numbers are correct and they describe different things.**

- **21 rules are defined** in the legacy detector. `SCORING_V2.md` §1 states it directly:
  "flagged 2,471 distinct permits across 21 rules."
- **17 rules actually fired** in the `signals` table (verified by query).
- The 4 defined-but-never-fired rules are visible in the v2 family map:
  `tenant_improvement`, `multi_unit_signal`, `recent_notable_sale`,
  `mechanics_lien_stack`, `short_term_rental` (5 named; 17 + 5 = 22, so at least one
  name in the family map is an alias or was retired — **UNRESOLVED, see §7**).

### The 17 observed rules, with evidence

| Rule | Fires | Score range | Family (v2) |
|---|---:|---|---|
| `street_cluster` | 5,437 | 7–10 | cluster (weight 0.1 after v2.1) |
| `dormant_address_reawakens` | 2,901 | 9–10 | cluster (moved from lifecycle, 0.2) |
| `demolition_then_new_construction` | 917 | 10 | lifecycle (3.0 → 2.0 at v2.1) |
| `fresh_deed_permit` | 582 | 8–10 | crossref (1.0) |
| `stalled_project` | 213 | 8 | lifecycle (2.0) |
| `contractor_surge` | 121 | 7–10 | cluster (0.3) |
| `code_violation_origin` | 104 | 8–10 | crossref (1.0) |
| `llc_cluster` | 101 | 9–10 | cluster (0.3) |
| `high_value_commercial` | 49 | 8–10 | value (3.0) |
| `undervalued_sale` | 36 | 8–9 | crossref (1.0) |
| `site_assembly` | 33 | 10 | cluster (0.8) |
| `demo_land_play` | 31 | 8–10 | lifecycle (2.5) |
| `seeded_developer_match` | 19 | 9–10 | crossref (2.0) |
| `drc_review` | 16 | 8–10 | crossref (1.5) |
| `cra_project` | 6 | 9–10 | crossref (1.5) |
| `hcd_project` | 4 | 9–10 | crossref (1.5) |
| `high_fee_signal` | 4 | 6–10 | value (1.5) |

---

## 3. Strongest prior model — v2.6, on evidence

**v2.6 is the strongest prior model.** Not by preference; by four pieces of evidence.

1. **It is the only version with independent editorial review of live output.**
   Two scheduled shadow runs (2026-07-16, 2026-07-17) were reviewed item-by-item, and
   the reviewer recorded a findings register (F1–F8) including defects *against itself*.
   No other version has this.
2. **It survived a documented regression it did not previously catch.** The 1528 NW 1 Ave
   escape drove v2.5's value axis; the "bare major label" regression drove v2.6's
   corroboration requirement. Each fix is traceable to an observed failure.
3. **It is deterministic — zero model calls.** ADR-007 rejected the legacy path precisely
   because it embedded model verdicts in scoring, violating "SQL computes, model narrates."
   v2.6 keeps `rules_fired` lineage intact and is reproducible.
4. **It refuses to pad.** Run 1 produced MAIN=4, run 2 produced MAIN=2 and NV=0 on a quiet
   day. An engine that returns two items rather than ten invented ones is behaving
   correctly, and this was verified in production-shaped conditions.

**Counter-evidence, stated fairly:** v2.6 has known open defects. F6/F7 (a condo shutter
permit outranked a verified $2M structural application through inherited-rule stacking) is a
real ranking inversion, acknowledged and deferred to post-run-5 by the scorer freeze. Two
of five review runs are complete. It has never generated a published brief.

---

## 4. What each layer of v2.6 actually does

**Gates (v2.0, historical scorer label corrected):** A = consequential filed scope (demo/new-construction rules or literal
type/description match; this is **not** evidence of owner intent, approval or future development; `dormant_address_reawakens` deliberately excluded). B = economic
weight (value rules or raw valuation ≥ $500k). C = 2+ distinct rule families. On the
original dataset: 3,204 candidates → 2,402 passed (75%), 802 dropped (25%).

**Scoring:** `base = max(max value weights, max lifecycle weights)`, plus 0.5 per extra
value/lifecycle rule, plus cluster bonus capped at 1.0, crossref capped at 2.5, specialty
uncapped; minus routine (−1.0), sub-permit (−2.0), low-value (−0.5), standalone-minor (−0.75).

**Project grouping (v2.1):** groups **only** by Accela related-records or a shared TIER-1
verified folio. **Address similarity never groups.** Anchor is the major member.

**Recency (v2.2):** a hard gate, orthogonal to importance. Daily placement requires a new
verified event since the last run. Importance and recency are separate axes by design.

**Editorial eligibility (v2.4/2.5/2.5.1):** minors never appear standalone; MAIN requires a
VERIFIED trigger; name-match attachments go to a separate NEEDS VERIFICATION list;
declared valuation < $100k bars standalone entry to MAIN; importance floor 1.5 unless a
verified major trigger is corroborated.

**Corroboration (v2.6):** a major label alone is not evidence. Exemption requires a strong
deterministic rule, OR ≥ $100k declared valuation, OR a verified project link.

**False-positive controls:** sub-permit penalty (demoted 11 of the v1 top 20); cluster cap;
family-diversity Gate C; two-pass dedup; diversity filter (max 1 per dedup group, max 2 per
owner LLC, max 1 per street); no padding; NEEDS VERIFICATION containment.

---

## 5. What does NOT exist — verified absences

These were searched for and are **not present**. Any reviewer proposing logic that depends
on them is proposing new data collection, not new scoring.

| Requested concept | Finding |
|---|---|
| Brightline / rail / beach / downtown / corridor logic | **No table, no scorer logic.** 2 incidental keyword hits in each detector, neither geographic. |
| CRA / redevelopment area geography | Only the `cra_project` rule (6 fires). **No boundary data.** |
| Neighborhood logic | **No neighborhood or boundary table.** The county parcel layer publishes `MUNICIPALITY` **empty for all 554,358 rows**; `SITUS_CITY` is a 2-letter code with no published lookup. |
| Media / news context | **No media table.** `signals_v2_context.media_flag` exists (200 pilot rows) but has no source feed behind it. |
| Rarity / percentile logic | **Not implemented.** 27 combined hits for recency/corroboration in the scorer; zero rarity implementation. |
| Meeting events | Not detectable — no tables (stated in the v2.6 risk register). |
| Sourced news events | Not detectable — no tables (stated). |
| Raw-valuation change history | Not detectable — no per-field history (stated). |
| Inspection outcomes | `accela_inspections` results are only `Pending` (50,274), `Scheduled` (651), null (91,213). **Zero pass, zero fail, zero completed dates.** |
| Review-duration benchmarks | `foia_workflow_events` has 2.4M rows spanning 2002–2026 and a full review pipeline, but **only a primary-key index on `id`** — no index on `permit_number` or `event_date`. Every join is a 367 MB sequential scan. |
| Property enrichment | All five `bcpa_*` tables cover ~4,300 of 532,470 folios (**0.8%**) and overlap ~120 of 9,585 mapped deed parcels (**1.3%**). |

---

## 6. Safety issues a reviewer must weigh

1. **`land_sales` is synthetic** — 10 rows, `source='seed:dry-run'`, sequential fake CINs
   (111900000001–010), none present in the Clerk feed. `land_sale_signals` scores it. There
   is no visible marker outside the `source` field. **Highest accidental-publication risk.**
2. **Owner name-match is candidate-grade by design.** The NEEDS VERIFICATION list is the
   containment. The promotion workflow (NV → MAIN) **is not built**.
3. **Clerk legal `parcel_id` is often a zero placeholder**, so verified folio links stay
   sparse. Independently confirmed: only deed and easement instruments carry parcel IDs;
   mortgages, liens, lis pendens and judgments carry none, and the Clerk link table does
   not reach one (mortgages 1 of 10,357 inheritable; liens 0; LP 0; judgments 0).
4. **`parcel_backfill` used address matching** for 16,863 rows. 95.9% of its folios verify
   against the official county layer, so the data is sound, but address-derived linkage is
   not permitted as a public claim.
5. **Both signal generations are dormant** — `signals` max 2026-05-02, `signals_v2` max
   2026-04-29. Any ranking or confidence derived from them is stale by 78+ days.

---

## 7. Unresolved questions — identical for every reviewer

1. **Rule-count reconciliation.** 17 rules observed firing; 21 stated as defined; the v2
   family map names 5 never-fired rules (17 + 5 = 22). Is one an alias, or was one retired?
   *Resolvable by reading the detector source; not resolved in this packet.*
2. **F6/F7 rank inversion.** Should the CURRENT event's own permit type be weighted
   independently of inherited project rules? A condo shutter permit led MAIN over a
   verified $2M structural application.
3. **Sub-permit penalty calibration.** −2.0 is the single most impactful change. A genuine
   $5M MEP-only project would be wrongly suppressed. Escape hatch above an absolute floor?
4. **Quiet-day product policy.** MAIN=2 with NV=0 is honest. Is it publishable?
5. **NV → MAIN promotion workflow.** Not built. Who verifies, and what is the audit trail?
6. **Is v2.6 the base, or is a rewrite justified?** ADR-007 chose port-and-refactor
   because "v2 already encodes a season of tuning." Does the F6/F7 inversion change that?
7. **Detection vs prediction.** No backtest has ever been run. No lead-time, precision, or
   false-positive rate exists for any pattern. Should any prediction claim be made at all
   before a backtest exists?

---

## 8. What each reviewer should be asked

Give every model this same packet and these same seven questions. Ask each to state, with
reasoning: (a) whether v2.6 is the right base or a rewrite is justified; (b) how to resolve
F6/F7 without reintroducing v1's noise floor; (c) the minimum backtest that would justify
any predictive claim; (d) which of the verified absences in §5 must be closed first; and
(e) what they would refuse to build on this data.

---

## 9. Evidence queries and sources used

Supabase (read-only, `n_tup_ins/upd/del` unchanged on every audited table): rule enumeration
from `signals`; `rules_fired` unnest from `signals_v2`; folio-safety audit across
`parcel_backfill` / `owner_resolution` / `enrichment` / `gis_enrichment`; `parcel_backfill`
validity join against `broward_parcel_geography`; `TABLESAMPLE SYSTEM (1)` profile of
`foia_workflow_events`; BCPA overlap joins; `land_sales` provenance; `information_schema`
scan for media/geography tables.

Repo `grahamandgold/florida-signal` @ `12f3d7b`: `business/SCORING_V2.md`,
`docs/ADR-007_signal_scorer_port_vs_replace.md`, `docs/SHADOW_RUN_PLAN_2026-07.md`,
`docs/SHADOW_REVIEW_LEDGER_2026-07.md`, `docs/SCORER_QA_LOG_2026-07-15.md`,
`scripts/detect_signals_v2.py` (2,219 lines, `ENGINE_VERSION = "2.6.0"`),
`scripts/detect_signals.py`, `scripts/compute_signal_score.py`,
`deploy/tools/fs_signals_shadow.sh`, systemd unit templates.

**Not searched: Google Drive.** No Drive connector was available in this session. The QA log
records "Spec v2 export to Drive + repo (Andy holds the only copy)" as an open to-do, so
Drive may hold a spec version not represented here.

---

# ADDENDUM — Drive recovery + context_boosts audit (2026-07-19, later same day)

## A. Google Drive recovery — VERIFIED ABSENT, and independently corroborated

Drive was searched for every requested term (SCORING_V2, Signal Machine, v2.1–v2.6, context
boosts, neighborhood, Brightline, rail, beach, downtown, corridor, CRA, media context,
historical context, rarity, recency, corroboration, prediction, backtest, reviewed editions,
false positives, known good/bad Signals, prior definitions of "Signal").

**No scoring specification, detector spec, test report or shadow-run output exists in Drive.**

What Drive does hold (Florida Signal related, none scoring logic):

| Drive artifact | Date | Type | In GitHub? |
|---|---|---|---|
| `FLORIDA_SIGNAL_DROPLET_CODE_RESCUE_2026-07-10.tar.gz` (+ `.sha256`) | 2026-07-10 | code rescue archive | superset of repo |
| `FLORIDA_SIGNAL_CURRENT_STATE_CHECKPOINT_2026-07-12.md` | 2026-07-12 | status | no |
| `FLORIDA_SIGNAL_EMAIL_ALERT_AUDIT.md` / `_ALERT_RULES.md` / `_EMAIL_SCHEDULE.md` / `_NOTIFICATION_*` | 2026-07-12 | notification governance | no |
| `FLORIDA_SIGNAL_HEALTH_REPORT_OWNERSHIP_2026-07-12.md` | 2026-07-12 | ops | no |
| `2026-07-13/14 SUNBIZ_*` audits (xlsx + md) | 2026-07-13/14 | entity-matching audits | partly |
| `florida_signal_data_room_local.html`, `florida_signal_dashboard.html` | 2026-05 | rendered snapshots | generated |

**This is a confirmed negative, not a failed search.** `docs/FLORIDA_SIGNAL_BRIEF_SPEC_v2.md`
states in its own header that it was *"Reconstructed 2026-07-16 from traceable evidence after
the original chat-only copy was confirmed absent from every document authority (repo, droplet,
Drive — searched 2026-07-14/15)."* Today's independent search reproduces that result.

- **Drive-only scoring logic: NONE.**
- **Conflicts with GitHub: NONE.**
- **Conflicts with v2.6: NONE.**

## B. `scripts/context_boosts.py` — full audit (653 lines)

**Status: PROTOTYPE — NOT ACTIVE. Do not activate. Recommend PRESERVE + REWRITE, not port.**

| Dimension | Finding |
|---|---|
| Active? | **No.** Zero references in any `.command`, `.sh`, systemd unit or timer. Manual invocation only. |
| Inputs | Latest top-50 from `signals_v2`; `permits` (owner permit counts, 365-day lookback); `seed_developers` |
| Outputs | `signals_v2_context` — `location_score/flags`, `operator_score/flags`, `media_flag/note`, `context_score`, `composite_score`, recomputed top-50/20/5 ranks |
| Score model | `context = location (cap 1.0) + operator (cap 1.5) + 0.5 × media_flag`; `composite = v2_final_score + context`. v2 score preserved in `v2_final_score` — **additive and auditable** |
| **Location logic** | **Case-insensitive SUBSTRING MATCH on the raw address string.** Three token lists: waterfront (0.5) — ISLE, BAY COLONY, RIO VISTA, OCEAN DR, A1A, CAUSEWAY, NURMI, LAGO MAR…; corridor (0.3) — FEDERAL HWY, US-1, SUNRISE BLVD, LAS OLAS BLVD, ANDREWS AVE, 17 ST, SR 84…; downtown/Brightline (0.4) — ZIP 33301, DOWNTOWN, FLAGLER VILLAGE, HIMMARSHEE, **BRIGHTLINE**, NE/NW 1–2 ST, RIVERWALK |
| **Brightline/rail/beach** | **This is where that logic lives** — as address keyword tokens, NOT geography. There is no station coordinate, no distance calculation, no boundary polygon. |
| Operator logic | Permit count over trailing 365 days: 3–5 → 0.5, 6–10 → 1.0, 11+ → 1.5; +0.5 seed-developer match; +0.3 Sunbiz presence; capped 1.5 |
| **Media logic** | **PURE STUB.** `media_check()` returns `(0, None)` unconditionally. Schema wired, no API, no source. Documented future intent only. |
| Historical logic | None |
| Tests | **None.** |
| Known failures | **INSERT-not-UPSERT duplicate accumulation**, documented 2026-05-01 in `docs/SIGNAL_TABLE_CLEANUP_DECISION_2026-05-01.md`; fix deferred pending a decision on whether the writer survives at all |
| Reached `signals_v2_context`? | **Yes — 200 rows, all 2026-04-26.** |
| Reproducible? | Deterministic given the same DB state, but written against **SQLite**; the Supabase copies are migrated output, not live writes |

### Why rewrite rather than port
Substring matching on address strings is not geography. "CORAL WAY" is explicitly commented
as needing disambiguation from the Miami street of the same name; "OCEAN DR" and "HARBOR"
will collide across municipalities; a token list cannot express distance to the Brightline
station. **The concept is sound and worth keeping; the implementation is a keyword proxy that
should be replaced by real distance-to-feature once boundary/station geometry exists.** The
operator tier logic is the strongest part and is portable as-is.

**Correction to the main packet §5:** the earlier statement "no Brightline / rail / beach /
corridor / downtown logic exists" was scoped to the *scorer* and to *Supabase tables*. It is
accurate there, and inaccurate as a blanket claim: the logic exists in `context_boosts.py` as
address keyword tokens. There is still **no geographic data** — no station coordinates, no CRA
boundaries, no neighborhood polygons.

## C. Synthetic-data exposure — `land_sales`, `land_sale_signals`

**Exposure is live and public.** Verified read paths:

| Path | Detail |
|---|---|
| **Supabase RLS** | `anon_read_land_sales` and `anon_read_land_sale_signals`, both `USING (true)` — **readable by anyone holding the publishable anon key** |
| Data Desk (`cms/data.html`) | "Land sales" feed-health card (line 342) + `land_sales` explorer preset (line 523) |
| Engine repo | `detect_sales_signals.py`, `enrich_land_sales.py`, `generate_digest.py`, `render_data_room_local.py`, `_dashboard_data.py`, `sync_to_supabase.py`, `generate_tech_updates.py`, `audit_supabase_parity.py` |

All 10 rows carry `source='seed:dry-run'`, sequential fake CINs (111900000001–010), and none
of those CINs exists in the Clerk feed. Prices look real ($300k–$35M).

### No-delete isolation plan (proposed — NOT executed)
1. **Label at source, don't delete.** Add a `is_synthetic boolean` column defaulting to false;
   set true for `source LIKE 'seed:%'`. Rows preserved exactly; provenance becomes explicit.
2. **Revoke anon read** on both tables (drop the two `anon_read_*` policies). Service role and
   authenticated internal use continue. This is the single highest-value step.
3. **Filter at every read path**, not just the UI: `where coalesce(is_synthetic,false) = false`.
4. **Mark in the Data Desk** — rename the preset "Land sales (SEED — synthetic test data)"
   until step 1 lands, so an internal reader cannot mistake it.
5. **Never** let either table feed the map, a brief, the CMS queue, or any Signal.

Each step is reversible; none deletes or rewrites a row. **All require Andy's approval.**
