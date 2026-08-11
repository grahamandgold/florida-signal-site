# Florida Signal system state — August 11, 2026

Verified from the public site, GitHub Pages, the public API, Supabase's public read surface, the production droplet, the repository and the Mac service registry. This document distinguishes deployed production from historical plans and private editorial infrastructure.

## Executive state

| Surface | State | Evidence / consequence |
|---|---|---|
| Static public site | Available | GitHub Pages serves the root and all 19 sitemap URLs over HTTPS. Reliability recovery commit `556da93` is deployed from `main`. |
| Permit reader | Current enough to operate | The public mirror exposed records through August 10. `dashboard_cache` ID 1 refreshed August 11 at `03:00:00Z`. |
| Exact headline permit total | 133,221 | Timestamped `dashboard_cache.payload.stats.permits_total`; this recovery prefers it over the query planner estimate. |
| Exact mapped total | 110,346 | Timestamped `dashboard_cache.payload.stats.p_geo`. |
| Broward instrument total | 198,721 | Latest published recording-date clock is August 5; treat that source as delayed until a newer successful load is proven. |
| Public API | Available | `api.thefloridasignal.com` resolves to `142.93.253.188`, redirects HTTP to HTTPS and serves only `/api/` through nginx. `/api/health` reports Mailchimp configured and the private CMS not configured. |
| Briefs / Method / Broward Record | Repaired | The Leaflet-free initialization repair is on `main`; the production browser monitor covers these routes. |
| TLS and API persistence | Active | Let's Encrypt renewal is timer-managed; the systemd API service is enabled; subscriber/analytics SQLite is persistent and backed up before this deployment. |

## Automation truth

Florida Signal has multiple kinds of automation; they are not interchangeable.

| Automation | Actual state | Owns |
|---|---|---|
| Supabase database schedules | Active where independently observed | Public mirror/cache work. A fresh cache timestamp is evidence of a run, not proof that every source is current. |
| Acclaim Mac LaunchAgent | Loaded | Preliminary Clerk collection only. It does not maintain or deploy the website. |
| Other Florida Signal Mac LaunchAgents | Disabled | Files exist for intake, enrichment, backups, audits and rendering, but the labels are disabled and must not be re-enabled as a group. |
| GitHub Pages | Deploys `main` | Static HTML, CSS, JavaScript and assets only. It cannot run the Python API. |
| Codex recurring site task | None found | No existing Codex automation was maintaining the public site. |
| Public site health workflow | Active on `main` | Verifies pull requests and `main`, checks production hourly, preserves browser evidence and opens/updates a GitHub incident on scheduled failure. |
| Droplet source timers | Active | The production host reports enabled schedules for intake, sync, Accela, enrichment, Broward, Sunbiz, backups, parity and health work. A running timer is not proof of source completeness; use the public event clocks below. |

Do not reactivate old jobs until the current always-on owner, inputs, outputs, idempotency and overlap with database/server schedules are documented. A disabled file is not a missed heartbeat; it is an inactive definition.

## Journalism and count contract

- Prefer a timestamped exact snapshot for a published total.
- If only a database planner estimate is available, prefix it with `≈`, label it as an estimate and warn that it must be verified before citation.
- Keep event clocks separate from pull, mirror, enrichment and cache clocks.
- Preserve source text and provenance; quarantine conflicts instead of selecting a convenient value.
- A fresh permit mirror does not make the August 5 Broward recording clock current.
- No automated monitor may publish narrative claims or silently repair source data.

## Current production limits and follow-up

1. Broward instruments remain stale at an August 5 recording-date clock; do not label that source current until a newer successful load is independently verified.
2. Sunbiz remains unverified because its public health/event clock is not exposed.
3. The private Data Wire is intentionally not attached to the public API. `/api/cms` fails closed to an approved-only empty response; do not expose the local shared-token starter publicly.
4. The NHC `CurrentStorms.json` origin returns HTTP 403 to the DigitalOcean host. The public client falls back to the official NHC URL and shows a source-check state if both attempts fail; do not translate an unavailable source into “no storm.”
5. A valid live subscriber was not fabricated for testing. Persistence and idempotency passed against an isolated temporary database, and a read-only Mailchimp audience check succeeded; the first real consented signup remains the final live write-path proof.
6. Reconcile or close older site pull requests so `main` remains the only production release path.
7. Audit each disabled Mac collector against the active server/database schedules before deciding whether it is retired or restored.

## Public API production facts

- DNS: GoDaddy A record `api` -> `142.93.253.188`, observed with a 600-second TTL.
- Host checkout: `/srv/grahamandgold/florida-signal-site`, clean `main` at `556da93` when deployed.
- Service: `florida-signal-public.service`, bound to `127.0.0.1:4173`, enabled with restart-on-failure.
- Boundary: nginx exposes `/api/` only; `/` returns 404; allowed browser origins are the root and `www` production domains.
- TLS: Let's Encrypt certificate for `api.thefloridasignal.com`, renewal timer enabled; renewal dry-run succeeded August 11.
- Secrets: `/srv/grahamandgold/florida-signal/secrets/public-site.env`, owned by root and mode `0600`; systemd environment files use `NAME=value`, not shell `export` statements.
- Durable local data: `/srv/grahamandgold/florida-signal/data/public-api/florida_signal_cms.sqlite`, owned by `andy`, directory mode `0700`, file mode `0600`.
- Pre-deploy backup: `/srv/grahamandgold/florida-signal/backups/public-api/florida_signal_cms.pre-api-dns-20260811T0430Z.sqlite`.
- Runtime backup: the prior unversioned site directory was preserved as `/srv/grahamandgold/florida-signal-site.pre-git-20260811T0430Z`.

## Release rule

Static-site repairs may merge only after unit tests and browser checks pass. API and collector changes require their own source/data reconciliation plus rollback instructions. The hourly monitor may report incidents but must not alter source data or publish a narrative repair. Human editorial approval remains mandatory for briefs and consequential narrative claims.
