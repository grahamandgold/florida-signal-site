# Florida Signal system state — August 11, 2026

Verified from the public site, GitHub Pages, the public API, Supabase's public read surface, the production droplet, the repository and the Mac service registry. This document distinguishes deployed production from historical plans and private editorial infrastructure.

## Executive state

| Surface | State | Evidence / consequence |
|---|---|---|
| Static public site | Available | GitHub Pages serves the root and all 19 sitemap URLs over HTTPS. Two-clock Clerk commit `c74bf3b` is deployed from `main`. |
| Permit reader | Current enough to operate | The public mirror exposed records through August 10. `dashboard_cache` ID 1 refreshed August 11 at `03:00:00Z`. |
| Exact headline permit total | 133,221 | Timestamped `dashboard_cache.payload.stats.permits_total`; this recovery prefers it over the query planner estimate. |
| Exact mapped total | 110,346 | Timestamped `dashboard_cache.payload.stats.p_geo`. |
| Broward verified instrument total | 201,014 | The authoritative SFTP lane is verified through August 6. Its August 11 catch-up loaded 2,293 documents, 5,954 parties, 268 legal rows and 1,049 links with parse status `ok`. |
| Broward preliminary recordings | Current through August 11 | After Wi-Fi and Broward disclaimer recovery, the Mac AcclaimWeb lane collected all 2,056 August 11 rows. They remain explicitly preliminary until row-level SFTP reconciliation. |
| Public API | Available | `api.thefloridasignal.com` resolves to `142.93.253.188`, redirects HTTP to HTTPS and serves only `/api/` through nginx. `/api/health` reports Mailchimp configured and the private CMS not configured. |
| Briefs / Method / Broward Record | Repaired | The Leaflet-free initialization repair is on `main`; the production browser monitor covers these routes. |
| TLS and API persistence | Active | Let's Encrypt renewal is timer-managed; the systemd API service is enabled; subscriber/analytics SQLite is persistent and backed up before this deployment. |

## Automation truth

Florida Signal has multiple kinds of automation; they are not interchangeable.

| Automation | Actual state | Owns |
|---|---|---|
| Supabase database schedules | Active where independently observed | Public mirror/cache work. A fresh cache timestamp is evidence of a run, not proof that every source is current. |
| Acclaim Mac LaunchAgent | Loaded and caught up | Preliminary Clerk collection at 12:30 a.m., noon, 7 p.m. and 10:30 p.m. local, plus hourly and login catch-up. State is complete through August 11 with no backlog. It does not maintain or deploy the website. |
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
- Never collapse the Clerk clocks: AcclaimWeb is the early, preliminary lane; SFTP is the delayed, authoritative lane.
- Preserve Acclaim direct name, indirect name, document type, book/page and legal text even when a field is not yet used publicly.
- A fresh preliminary clock does not make the August 5 authoritative SFTP clock current or verified through August 10.
- No automated monitor may publish narrative claims or silently repair source data.

## Current production limits and follow-up

1. The authoritative Broward SFTP source is delayed at an August 6 recording-date clock while the separately labeled preliminary lane reaches August 11. Do not present the newer rows as verified until reconciliation matches instrument number and record date.
2. Sunbiz remains unverified because its public health/event clock is not exposed.
3. The private Data Wire is intentionally not attached to the public API. `/api/cms` fails closed to an approved-only empty response; do not expose the local shared-token starter publicly.
4. The NHC `CurrentStorms.json` origin returns HTTP 403 to the DigitalOcean host. The public client falls back to the official NHC URL and shows a source-check state if both attempts fail; do not translate an unavailable source into “no storm.”
5. A valid live subscriber was not fabricated for testing. Persistence and idempotency passed against an isolated temporary database, and a read-only Mailchimp audience check succeeded; the first real consented signup remains the final live write-path proof.
6. Reconcile or close older site pull requests so `main` remains the only production release path.
7. Audit each disabled Mac collector against the active server/database schedules before deciding whether it is retired or restored. Do not create a second Acclaim writer while `com.floridasignal.acclaim` is loaded.

## August 5 preliminary recovery

- The preserved full Acclaim export contained 2,446 unique instruments; the original interrupted run had inserted 1,250.
- The 1,196-row remainder matched the preserved full-file tail and all recorded batch checksums before insertion.
- The service-role upsert inserted exactly 1,196 new rows and skipped no unexpected instruments.
- `reconcile_clerk_preliminary()` then matched all 2,446 August 5 rows to the authoritative feed with 0 conflicts and 0 aged unmatched rows.
- The recovered rows retain 2,446 direct-name values, 2,213 indirect-name values and 290 legal-text values. Recovery did not update the authoritative tables.

## August 11 connectivity and mirror recovery

- The noon Mac run occurred while Wi-Fi was unavailable. It retained the cached August 5 verified
  floor and did not advance the Acclaim state. After connectivity returned, the verified SFTP lane
  advanced through August 6.
- Broward redirected the collector to its periodic disclaimer. The collector recorded
  `terms_acceptance_required` without clicking the legal acceptance control or losing backlog;
  after manual acceptance, the retry harvested and inserted exactly 2,056 August 11 rows.
- Database audit counts were 0 conflicts for August 5, 6, 7, 10 and 11. August 5 and 6 are verified;
  August 7, 10 and 11 remain preliminary pending their authoritative files.
- The public mirror had stopped because `/srv/grahamandgold/florida-signal/secrets` was `root:root`
  mode `0700`, preventing the `andy` pipeline account from traversing the `app/.env` symlink. The
  directory was repaired to `root:andy` mode `0710`; pipeline `.env` remains `andy:andy` `0600`,
  while `public-site.env` remains root-only `0600` and unreadable by `andy`.
- A forced mirror completed at 3:11 p.m. ET: 27 tables, 10,872 rows and 0 errors, with a new
  heartbeat. A systemd-tmpfiles rule now makes the directory contract durable, and the hourly site
  monitor fails when `supabase-sync` becomes stale or unavailable.
- The first live immediate-reconciliation call correctly failed the systemd service when the old
  function exceeded PostgREST's statement timeout. Pipeline migration 009 added matching
  normalized-instrument/date indexes, including a partial index limited to unverified preliminary
  rows, and fixed the function search path. The rerun completed successfully with
  `matched=0 conflicts=0 aged_unmatched=0`; the daily pg_cron fallback remains enabled.

## Public API production facts

- DNS: GoDaddy A record `api` -> `142.93.253.188`, observed with a 600-second TTL.
- Host checkout: `/srv/grahamandgold/florida-signal-site`, clean `main` at `c74bf3b` before this recovery release.
- Service: `florida-signal-public.service`, bound to `127.0.0.1:4173`, enabled with restart-on-failure.
- Boundary: nginx exposes `/api/` only; `/` returns 404; allowed browser origins are the root and `www` production domains.
- TLS: Let's Encrypt certificate for `api.thefloridasignal.com`, renewal timer enabled; renewal dry-run succeeded August 11.
- Secrets: parent directory `root:andy` mode `0710`; `public-site.env` remains root-owned mode `0600` and unreadable by `andy`; systemd environment files use `NAME=value`, not shell `export` statements.
- Durable local data: `/srv/grahamandgold/florida-signal/data/public-api/florida_signal_cms.sqlite`, owned by `andy`, directory mode `0700`, file mode `0600`.
- Pre-deploy backup: `/srv/grahamandgold/florida-signal/backups/public-api/florida_signal_cms.pre-api-dns-20260811T0430Z.sqlite`.
- Runtime backup: the prior unversioned site directory was preserved as `/srv/grahamandgold/florida-signal-site.pre-git-20260811T0430Z`.

## Release rule

Static-site repairs may merge only after unit tests and browser checks pass. API and collector changes require their own source/data reconciliation plus rollback instructions. The hourly monitor may report incidents but must not alter source data or publish a narrative repair. Human editorial approval remains mandatory for briefs and consequential narrative claims.
