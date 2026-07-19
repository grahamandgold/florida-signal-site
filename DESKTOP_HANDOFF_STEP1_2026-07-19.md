# FLORIDA SIGNAL — STEP 1 HANDOFF (visual inspection + status)
**Sun July 19, 2026 · Claude/Cowork session · local branch `claudette/launch-day` → draft PR #1 (`codex/florida-signal-rebuild`)**
*No production changes. Nothing merged or deployed. Local CSS edits below are NOT pushed — Andy pushes.*

---

## ✅ COMPLETED THIS STEP — full visual inspection (desktop + mobile)

**Desktop @ 1280px — all 10 public pages: NO horizontal overflow.**
Home · Signals · Neighborhoods · Market Data (graphics) · Broward Record · Meetings · Storm · Method · Daily Intel Brief (briefs) · Brand.

**Mobile @ 390px — all 10 pages: NO horizontal overflow.**

**One real defect found and fixed (local CSS only, not pushed):**
Storm page `surface-report` share button overflowed to ~430px on mobile → constrained; re-audit shows offenders cleared.

**Residual (documented, not "fixed" — see issues below):** intentional sub-10px uppercase micro-labels remain on several pages by design.

---

## 📊 CURRENT DATA COUNTS (stated baseline — provided by Andy; live permit/GIS values drift nightly)

| Dataset | Count |
|---|---:|
| Permits | **127,945** |
| GIS-enriched records | **104,034** |
| FAA records (incl. 142 Broward cranes) | **7,053** |
| Mapped FDEP records | **8,309** |
| Official Clerk records | **149,963** |
| Early (preliminary) Clerk records | **13,769** |
| Permit geographic coverage | **nearly complete** |

*Independent verification of these vs live Supabase/site is STEP 2 — not performed yet, per task order.*

---

## ✅ COMPLETED EARLIER THIS SESSION (already in repo / PR #1)

- **Brand:** Atlantic navy `#082a54` + electric blue `#1767ff`, Montserrat headlines / Figtree body, new 2026 logo lockups across all pages + Data Wire CMS; new emblem on maps/cards/watermarks; **map legends** added (Application / $500K+ / Storm / Demolition).
- **Nav/IA:** single-source nav (Signals · Neighborhoods · Market Data · Broward Record · Meetings · More▾) with width governance + mobile menu; CTA **"Get Daily Intel Brief"**; hero credibility line; new `/signals/` page.
- **Copy:** "Our top signals" (was "What's moving"); ticker rotates real high-value filings.
- **Data Desk** (`cms/data.html`) internal viewer; **Data Wire CMS** reskinned + local auto-unlock.
- **Mailchimp** configured (`mailchimp_configured: true`); personalize panel compacted.
- **New sources live in Supabase:** FDEP ERP + FAA OE/AAA (edge functions + pg_cron); Broward **preliminary Clerk** pipeline.
- **Clerk SFTP catch-up → droplet systemd timer** (venv, hardened) — Claude task disabled, rollback-only.
- **Acclaim preliminary → native Mac LaunchAgent** `com.floridasignal.acclaim` (12:00 + 19:00), full-day pagination (page size 500), state/resume, positive empty-state detection, reconciliation function + pg_cron. 13,769 rows, backlog empty.
- Desktop launcher apps + icons; Supabase migrations tracked in `supabase/migrations/`.

---

## 🚧 NOT COMPLETED / REMAINS (priority order)

1. **PR #1 not merged, not deployed** — awaiting Andy. Live site alignment = STEP 2.
2. **Droplet migration of remaining Mac/Claude tasks** — plan = STEP 3 (Acclaim LaunchAgent, social-PNG export). Clerk catch-up already migrated.
3. **Signals v2 gate** — shadow run 5 completes Mon Jul 20 ~05:45; review + merge open PRs = STEP 4 evidence package.
4. **Social PNG re-export** — nightly task exists; first Atlantic-brand run not yet visually verified.
5. **CMS production hosting** (always-on, auth, HTTPS, backups) — required before paid tiers.
6. **Mailchimp first Daily Intel Brief** template + send flow.
7. Roadmap sources (RealAuction, BCS, AGOL, liens, minutes, deeper BCPA) — none started; explicit go needed.

---

## ⚠️ RESIDUAL ISSUES FOUND DURING INSPECTION

- **Micro-label typography:** intentional 7–9.5px uppercase eyebrows / date-window stamps / source clocks remain below the 10px readability floor on Storm (~29), Method (~28), Brand (~16), Signals/Broward/Briefs (~8 each). These are a **deliberate editorial style**, not breakage — flagged for Andy's call rather than overridden site-wide.
- **Small tap targets:** 6–11 sub-30px `<a>/<button>` elements per interior page (mostly share/report micro-controls). Not blocking; candidate for a global min-tap pass if desired.
- **Data-count drift:** live permit/GIS totals refresh nightly, so the baseline above will not match the live site to the exact digit at all times — reconcile in STEP 2.
- **No copy errors or broken links surfaced** in this pass (JS/JSON/link validation was clean in earlier checks).

---

## 🔑 STATE (verified this step)
Acclaim LaunchAgent **loaded/active, last exit 0, backlog empty**; official Clerk table **149,963 unchanged**; preliminary **13,769**. Log rotation (5 MB × 3) in place. Private creds outside repo (`~/.florida_signal_*`).

**NEXT:** awaiting Andy's confirmation to proceed to STEP 2 (production alignment audit — evidence only).
