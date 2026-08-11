# Florida Signal system state — August 11, 2026

Verified from the public site, GitHub Pages, Supabase's public read surface, the repository and the Mac service registry. This document distinguishes deployed production from code awaiting review.

## Executive state

| Surface | State | Evidence / consequence |
|---|---|---|
| Static public site | Available | GitHub Pages serves the root and all 19 sitemap URLs over HTTPS. Last deployed commit before this recovery is `7b85168` from July 22. |
| Permit reader | Current enough to operate | The public mirror exposed records through August 10. `dashboard_cache` ID 1 refreshed August 11 at `03:00:00Z`. |
| Exact headline permit total | 133,221 | Timestamped `dashboard_cache.payload.stats.permits_total`; this recovery prefers it over the query planner estimate. |
| Exact mapped total | 110,346 | Timestamped `dashboard_cache.payload.stats.p_geo`. |
| Broward instrument total | 198,721 | Latest published recording-date clock is August 5; treat that source as delayed until a newer successful load is proven. |
| Public API | Unavailable | `api.thefloridasignal.com` has no working DNS. Signup, CMS, meeting proxy, analytics and API health are therefore unavailable in production. |
| Briefs / Method / Broward Record | Broken in deployed build | Shared JavaScript evaluates `L.point` before page initialization even though these routes do not load Leaflet. They remain stuck at connecting states. |
| Recovery branch | Awaiting review | `codex/site-reliability-recovery` removes the global Leaflet dependency, makes count quality explicit and adds continuous browser verification. |

## Automation truth

Florida Signal has multiple kinds of automation; they are not interchangeable.

| Automation | Actual state | Owns |
|---|---|---|
| Supabase database schedules | Active where independently observed | Public mirror/cache work. A fresh cache timestamp is evidence of a run, not proof that every source is current. |
| Acclaim Mac LaunchAgent | Loaded | Preliminary Clerk collection only. It does not maintain or deploy the website. |
| Other Florida Signal Mac LaunchAgents | Disabled | Files exist for intake, enrichment, backups, audits and rendering, but the labels are disabled and must not be re-enabled as a group. |
| GitHub Pages | Deploys `main` | Static HTML, CSS, JavaScript and assets only. It cannot run the Python API. |
| Codex recurring site task | None found | No existing Codex automation was maintaining the public site. |
| Public site health workflow | Added in recovery branch | On merge, verifies pull requests and `main`, checks production hourly, preserves browser evidence and opens/updates a GitHub incident on scheduled failure. |

Do not reactivate old jobs until the current always-on owner, inputs, outputs, idempotency and overlap with database/server schedules are documented. A disabled file is not a missed heartbeat; it is an inactive definition.

## Journalism and count contract

- Prefer a timestamped exact snapshot for a published total.
- If only a database planner estimate is available, prefix it with `≈`, label it as an estimate and warn that it must be verified before citation.
- Keep event clocks separate from pull, mirror, enrichment and cache clocks.
- Preserve source text and provenance; quarantine conflicts instead of selecting a convenient value.
- A fresh permit mirror does not make the August 5 Broward recording clock current.
- No automated monitor may publish narrative claims or silently repair source data.

## Known production blockers

1. Review and merge the site reliability recovery.
2. Deploy `server.py` (or an equivalent API) on an always-on host.
3. Add DNS and TLS for `api.thefloridasignal.com` and verify `/api/health` externally.
4. Test subscription persistence/Mailchimp, meetings, CMS, analytics, storm and source-health requests end to end.
5. Reconcile or close the older site PRs so only one release path remains.
6. Audit each disabled collector against the active server/database schedules before deciding whether it is retired or restored.

## Release rule

Static-site repairs may merge only after unit tests and browser checks pass. API and collector changes require their own source/data reconciliation plus rollback instructions. Human editorial approval remains mandatory for briefs and consequential narrative claims.
