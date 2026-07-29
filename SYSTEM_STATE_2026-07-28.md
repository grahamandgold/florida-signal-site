# Florida Signal — current system state

**Verified July 28, 2026 · Graham & Gold LLC**

This is the current operational and launch authority for Florida Signal. It supersedes
the current-state claims in handoffs dated July 23, 2026 or earlier. Older dated documents
remain useful historical evidence, but they do not describe today's branch, deployment,
pipeline, or backup state.

## Executive truth

- **Florida Signal is not approved for launch.** Do not merge, promote, publish, send a
  campaign, or change DNS without Andy's explicit approval.
- The website is nevertheless **publicly reachable through GitHub Pages** at
  `thefloridasignal.com`. Treat it as an unintended public preview, not an approved launch.
- The public static build responds successfully, but `api.thefloridasignal.com` has no DNS
  answer. API-backed health, subscriber, CMS, and agenda functions are therefore not a
  working production stack. `/api/health` on the static Pages host returns 404.
- `/fort-lauderdale/` currently permits indexing and the sitemap is public. A July 28 search
  audit found no indexed results, but absence from today's results is not a containment
  control.
- The core data pipeline is operating. Today's recurring Sunbiz fault was traced to a
  duplicate legacy Mac writer and permanently retired. Only the authoritative droplet
  SFTP-corpus resolver may write production Sunbiz cache results.
- The final production health rollup is **GREEN** with zero failed systemd units. The
  freshness watchdog now has bounded provider-specific retries and its manifest query has
  targeted timestamp indexes.
- The parcel matcher remains intentionally disabled. It is an optional retired folio
  enrichment lane, not a prerequisite for the geocoded product.
- The latest local and off-site backup artifacts exist. The strengthened full database
  `quick_check` passed on the 11,770,785,792-byte cold copy containing 130,029 permit rows.
  Its exact SHA-256 is recorded in the live backup state and remote manifest.

## Authority map

| Authority | Owns |
|---|---|
| `grahamandgold/florida-signal-site` | Public website, local Data Wire CMS, web adapters and site operations |
| `grahamandgold/florida-signal` | Collectors, scorer, Supabase schema, production services and backup tooling |
| DigitalOcean `florida-signal-runtime` | Production collectors, timers and backup execution |
| Supabase `florida-signal-prod` | Production database and public mirror |
| Graham & Gold Google Drive | Company documentation and off-site backup copies |
| Andy's Mac | Acclaim's residential/browser dependency only; not a general production runtime |

GitHub is code authority. The dated system-state document in this repository and the
Google Drive launch-truth document are documentation authorities. Chat transcripts and
downloaded repository copies are not authorities.

## Website and release state

| Item | Verified state |
|---|---|
| GitHub Pages | Public, HTTPS enforced, source `main` at commit `7b85168` |
| Root URL | HTTP 200 with a redirect into `/fort-lauderdale/` |
| Fort Lauderdale route | HTTP 200; indexable; present in the public sitemap |
| Production API hostname | No A or AAAA response on July 28 |
| PR #3 | Open, ready for review, mergeable/clean; not deployed |
| PR #4 | Open draft, conflicting/dirty; must not merge in its current state |
| Approved launch | **No** |
| CMS/Mailchimp production delivery | Not proven or approved live |

The current static build is a preview artifact, not a complete launch. A launch requires
an explicit exposure decision, a working and protected API, end-to-end subscription and
editorial tests, resolved release branches, and written approval.

## Pipeline state

- Permit collection, normalization, scoring, mirror sync and freshness heartbeat are
  production services on the droplet.
- Broward Clerk verified deeds remain authoritative. The Acclaim preliminary lane is a
  browser-dependent secondary feed and must degrade visibly when the upstream source gates
  access.
- Legistar freshness reflects the official upstream response; stale source data must not be
  relabeled as fresh.
- Sunbiz freshness now counts only `source='sunbiz-sftp-corpus'`. Legacy
  `sunbiz-web-search` error rows were removed and that writer is retired at the operating
  system and script levels.
- `florida-parcelmatch.timer` stays disabled. Re-enable it only after a documented product
  requirement and data contract justify doing so.

## Backup state and policy

- The production SQLite backup is cold-copied before upload.
- Every new source SHA must pass a bounded `PRAGMA quick_check` before it can be called a
  good off-site backup.
- A same-SHA upload may be skipped only when the prior integrity result is `ok` and the
  remote object's byte size matches.
- `latest/` advances daily. Immutable dated snapshots use the tiered policy: Sundays and
  the first day of the month. `SNAPSHOT_MODE=skip` is emergency containment only.
- Health is yellow for skipped/unknown integrity and red for failed integrity. Only
  `QUICK_CHECK=ok` is backup-green.
- Drive retention remains dry-run unless a separately approved deletion is performed.

## Current code work

- Engine recovery PR: `grahamandgold/florida-signal#80`, branch
  `codex/pipeline-recovery` (draft).
- Site recovery PR: `grahamandgold/florida-signal-site#4`, branch
  `codex/acclaim-recovery` (draft and currently conflicting).
- Product/mobile work: `grahamandgold/florida-signal-site#3`, branch
  `codex/methodology-mobile-stories` (open and mergeable).

No item above is approval to merge or deploy.

## Documentation rule

Use this file with [`REMAINING_WORK_REGISTER_2026-07-28.md`](REMAINING_WORK_REGISTER_2026-07-28.md)
for current decisions. Treat files with an earlier date as historical snapshots unless they
explicitly point here. Preserve those files rather than silently rewriting their history.

The exact first-five-minutes command map, evidence paths, prior traps, and known unknowns are
in the engine repository at `docs/OPERATIONS_DISCOVERY_MAP_2026-07-28.md`.
