# CORRECTION — local Mac corpus found
**2026-07-19 · supersedes the status line in `SCORING_EVIDENCE_PACKET_2026-07-19.md`**

**The status "READY FOR MULTI-MODEL REVIEW — SCORING EVIDENCE COMPLETE" was wrong and is
withdrawn.** I searched the connected folder, GitHub and Google Drive. I never searched the
operator's local filesystem. Andy asked whether I had. I had not. This is what was there.

**Revised status: PARTIAL — PRIOR SCORING WORK INCOMPLETE.**

---

## 1. Location

`~/ANDY_DIGITAL_HOME/06_GRAHAM_AND_GOLD/02_FLORIDA/`

| Path | Contents |
|---|---|
| `NOTES/` | **193 notes** rescued from Apple Notes / iCloud, YAML front-matter, `classification: PRESERVE` |
| `GROK_LAB_RECOVERED/` | `florida-signal-cloud`, `quarantine_unique`, `sanitized_copy_unique` |
| `AUDIT_NOTES/` | dashboard cache fix 2026-07-10 |
| `HISTORICAL_PRODUCTS/Florida_Signal_Desktop_2026-07-14/` | assets, dashboards |
| `downloads-florida-signal/` | earlier downloads |
| `florida-signal-machine-live.pdf` | rendered machine document |

Also on disk: eight `florida-signal-*` working copies under `~/Downloads`, and
`~/Desktop/Graham and Gold/02_Products/Florida Signal/dashboards`.

## 2. The find that matters

| Note | Title | Created | Lines |
|---|---|---|---:|
| N0013 | GROK SCORING: Florida Signal Engine — V1 | 2026-03-17 | 62 |
| **N0083** | **THE FLORIDA SIGNAL — INTELLIGENCE ENGINE v2.0** | 2026-03-27 | **1,361** |
| **N0089** | **MACHINE 2.1: REBUILD** | 2026-03-27 | **1,011** |
| N0017 | Canal Waterfront Pre-Signal Cluster (KEEP) | 2026-03-17 | 54 |
| N0086 | FILE 3 — APPROVED SIGNALS | 2026-03-27 | 14 (empty body) |

These **predate every Python detector** and are the origin of the Signal Machine. They are an
editorial specification, not code — and they contain the exact logic the earlier packet
reported as absent.

## 3. The v2.0 scoring model — 0 to 29

Five base dimensions, each 0–5 with a written anchor at every level:

| Dimension | Measures |
|---|---|
| **Sequence** | progression across development stages (demo → site clearing → utilities → structural → shell) |
| **Coordination** | shared owner / contractor / parcel / filing-window evidence of one coordinated effort |
| **Momentum** | recency and acceleration; 5 = same-day or ≤48h filing burst |
| **Relevance** | would developers, brokers, investors and attorneys act on it |
| **Scale and Value** | declared-value bands, under $25k → over $5M |

Two modifiers:

- **Neighborhood Modifier (0–2).** **+2 prime:** Fort Lauderdale Beach and barrier island,
  Las Olas Boulevard and corridor, downtown core including Flagler Heights east of the FEC,
  Coral Ridge, Bay Colony, Harbor Beach, Rio Vista, Idlewyld, Victoria Park east, and any
  Intracoastal or New River parcel with direct water frontage. **+1 transition corridor:**
  Flagler Village, Progresso, Sistrunk, FAT Village, South Middle River, Tarpon River,
  Sailboat Bend, or areas with active rezoning, CRA investment or documented upzoning.
- **Radius Context Modifier (0–2).** Nearby related activity — **conditionally applied: only
  when the base score is ≥ 15**, explicitly "to prevent context from rescuing a weak signal."

**Pattern Floor Rule:** Sequence + Coordination must total ≥ 4, or the candidate moves to
Watch regardless of total score — "a signal must demonstrate a pattern, not just a filing."

**Bands:** 0–11 Discard · 12–17 Watch · 18–23 Possible Publish · 24–29 Strong Publish.

**Step 5 — Historical Baseline Check** (every candidate scoring ≥ 12), five questions against
~24 months of history: prior same-type permits; whether volume is meaningfully higher (≈2× or
a shift to a higher-intensity type); first cluster after ≥12 months quiet; renewal/revision
detection where material scope change = value +25%, added phases, changed use, or new
structural work; and prior Signal coverage. "Routine repetition" or "Re-permit" forces
Watch/Discard **regardless of score**.

**Step 6 — Entity Intelligence:** entity reference-list match, entity-pattern match strength,
other active permits, plus a property-appraiser sale check — recent acquisition followed by
permit activity is flagged as a high-confidence development indicator.

**Step 7 — JOURNALISM INTEGRITY SCORE (5–25): a separate, independent gate.** "A high Signal
Score does not excuse weak journalism. A signal must pass both gates to publish."

Steps 8–11: publish gate · real-time verification · human review · tier ranking
(Lead / Secondary / Watchlist / Discard).

## 4. What this changes

| Concept | Earlier packet said | Actual |
|---|---|---|
| Neighborhood logic | "does not exist" | **Exists** — named prime and transition areas with weights |
| Historical context / rarity | "not implemented" | **Exists** — Step 5 baseline check with explicit thresholds |
| Corroboration | "introduced at v2.6" | **Predates it** — Coordination dimension + Entity Intelligence |
| Radius / cluster context | "absent" | **Exists** — with an explicit anti-rescue qualifying rule |
| Importance vs editorial separation | "a v2.6 innovation" | **Predates it** — Signal Score and Journalism Score, two gates |
| False-positive control | "penalties in v2.6" | **Predates it** — Pattern Floor Rule, hard exclusions, anti-rescue rule |

**The Python engine implements a narrower model than the written specification.** v2.6 has
gates, family weights, dedup, recency and editorial eligibility. It does **not** implement
Sequence / Coordination / Momentum / Relevance / Scale as scored dimensions, the neighborhood
modifier, the radius modifier, the pattern floor, the historical baseline check, or the
Journalism Integrity Score.

## 5. Honest status labels for this corpus

- **NOT SUPERSEDED** — no document supersedes it; the Python engine was built alongside it,
  not to replace it.
- **NOT IMPLEMENTED** — most of it has never been coded.
- **NOT TESTED** — no backtest, precision measurement or reviewed-edition record found yet.
- **UNVERIFIED AGAINST DATA** — whether Broward data can support Sequence and Coordination
  scoring at all is untested. Note the independently verified constraint: `accela_inspections`
  carries no outcomes, and `foia_workflow_events` is unindexed, so stage-sequence scoring may
  be harder than the spec assumes.

## 6. Not yet examined — named, not hidden

Of 193 notes, roughly 40 are scoring or machine relevant; **5 were opened**. Unread and
potentially material:

N0014 "Signal Machine — THE GROK DATA — DON'T ERASE" · N0015 Signal Machine Steps —
Operating System (V1) · N0016 "the efficient way (do this exactly)" · N0068 ALL SIGNALS ·
N0090 OUTPUTS MACHINE 2.1 · N0128 Phase 2 Weekly Signal Detection and Editor Packet ·
N0133 COMPLETE SYSTEM · N0207–N0210 WHAT FIELDS MATTER (Grok / ChatGPT / Gemini / Claude) ·
N0237–N0242 DATA-BIZ ASSESSMENTS + CLAUDE BIG COMBINED REPORT · N0252 TOP SIGNALS TO GO AFTER
NOW · N0253 Cross-Source Signal Thinking — Crossover Triggers · N0254 SCORING — TAG IDEAS ·
N0037 EDITOR'S NOTE PRE-SEND FACT-CHECK LIST · N0057 SIGNAL 1 OPERATOR TAKEAWAY ·
N0375 "Florida Signal — What's in this folder" (index) · all of `GROK_LAB_RECOVERED/`.

## 7. What this does to the v2.6 recommendation

**It does not overturn it, but it reframes it.** v2.6 remains the strongest *implemented and
reviewed* engine. The March specification is the strongest *designed* model, and it is richer
on exactly the axes the later work lacks — neighborhood, history, rarity and the separate
journalism gate.

The honest reading: **v2.6 is a subset of the intended machine, not a replacement for it.**
The multi-model review should be asked which parts of the March specification are supportable
by the verified data, not simply whether to keep v2.6.

## 8. Next step

Read the remaining ~35 scoring-relevant notes and `GROK_LAB_RECOVERED/` before any scoring
decision or multi-model packet is finalised. The packet as it stands is incomplete and would
mislead every reviewer who received it.
