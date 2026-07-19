# Component preservation map — 2026-07-19

Source of truth for reuse: `prototypes/homepage-full-before-final-ia-2026-07-19.html` (SUPERSEDED — PRESERVED FOR HISTORY).

| Homepage element (pre-IA) | Source | Data dependency | Final destination | Home preview | Report builder | QA |
|---|---|---|---|---|---|---|
| Live status ticker (`.live-bar`) | index/app.js | permits mirror | ALL pages (unchanged) | yes | — | pass |
| Mobile live rail + cards | index 114 | permits/dashboard/meetings | Home + Signals | yes | — | pass |
| Mobile field test ("Our top signals") | index 151 | geolocation+permits | Home + Signals | yes | — | pass |
| Hero + record flipper | index 172 | permits/dashboard | Home (dek+credibility updated) | yes | — | pass |
| Signals feed + spyglass | index 264 | featured permits/CMS wire | **Signals page (full)**; Home keeps 4-row preview | preview | Add-to-Report intact | pass |
| Spyglass sponsor slot | index (removed from Home) | — | Sponsor inventory/page (pending) | no — LOGGED | — | pending |
| Intel section ("market moves on paper") | index 287 | dashboard_cache | Home; Market Data completion pending | yes | yes | pass |
| Map section (mint) | index 345 | permits geo | Home + Neighborhoods | yes | yes | pass |
| Broward tease | index 383 | clerk aggregates | Home → Broward record | yes | — | pass |
| Storm tease | index 411 | NHC + classifier | Home (teaser) → Storm page | yes | — | pass |
| Editorial credibility | NEW | — | Home | yes | — | pass |
| Brief signup + personalization | index 437 | Mailchimp queue | Home + briefs/ landing | yes | — | pass |
| Standards teaser | index 459 | — | Home → Method | yes | — | pass |
| Footer | index 468 | — | compact pass pending | yes | — | pending |

Nothing deleted. One relocation (spyglass sponsor slot) logged above for Andy's approval.
