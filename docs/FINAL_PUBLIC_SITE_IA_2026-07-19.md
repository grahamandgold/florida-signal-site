# Final public-site IA — 2026-07-19 (in progress)

**Decision (logged):** Florida Signal uses a focused conversion-oriented homepage with the complete intelligence product preserved across dedicated interior pages in the same primary repository (`grahamandgold/florida-signal-site`; the brief's "florida-signal" name is a shorthand discrepancy, logged).

## Route map
| Final route | Status | Reused components / data |
|---|---|---|
| `/fort-lauderdale/` (Home) | RESTRUCTURED | hero + flipper, capped signals preview (4), intel, map, teasers, credibility (NEW), brief signup, standards, footer — all existing app.js live-data logic |
| `/fort-lauderdale/signals/` | NEW ROUTE (built from preserved home sections) | full signal feed (cap 40 via `data-page="signals"`), spyglass map, ticker, signup — same app.js |
| `/fort-lauderdale/neighborhoods/` | EXISTING | full map, search, rankings |
| `/fort-lauderdale/graphics/` (nav label: **Market data**) | EXISTING | Data Room; heading subtitle pass pending |
| `/fort-lauderdale/broward-record/` | EXISTING | joined-record page; FDEP/FAA surfacing pending |
| `/fort-lauderdale/meetings/` | EXISTING | calendar + rooms |
| `/fort-lauderdale/storm/` | EXISTING (nav: More) | NHC + hardening filings |
| `/fort-lauderdale/method/` | EXISTING (nav: More) | preliminary-vs-verified statement pending |
| `/fort-lauderdale/briefs/` (Daily Intel Brief) | EXISTING (nav: More) | landing polish pending |
| Sponsor page | PENDING | sponsor-slot components exist |
| `prototypes/homepage-full-before-final-ia-2026-07-19.html` | PRESERVED SNAPSHOT | SUPERSEDED banner |

No routes removed. No redirects required yet.

## Navigation (single source: `app.js initNavigation()`)
Primary: Live map (chip) · Signals · Neighborhoods · Market data · Broward record · Meetings · **More▾** (Storm, Method, Daily Intel Brief, Brand). Width governance: <1560 Broward record→More; <1340 Market data→More; <1120 Neighborhoods→More; ≤620 full-screen menu, More auto-expanded. CTA: **Get Daily Intel Brief**. Report builder: floating launcher (all pages) — unchanged.
