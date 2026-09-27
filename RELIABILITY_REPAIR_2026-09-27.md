# September 27 reliability repair

This change repairs health reporting and the existing public/CMS approval boundary.
It does not establish that the separate production newsroom, model-review pipeline,
or newsletter delivery is ready. Installing code, successfully querying a source,
and producing an approved brief are separate outcomes.

## Database repairs

The two migrations in this change are already applied to the connected production
project. Do not reapply old migration files or reset migration history.

- `repair_health_query_ordering` adds a partial index with the exact
  `received_date DESC NULLS LAST` ordering used by the deployed FDEP health read.
  A measured full index scan and sort took about 10 seconds and the public read
  timed out. The same query used the new index in approximately 2.5 milliseconds.
  Existing indexes and source rows remain intact.
- `keep_sunbiz_health_truthful` counts only `EXACT` matches from the authoritative
  corpus, separately reports unmatched/nonexact rows, and follows the existing
  freshness manifest's 36-hour stale boundary. Its owner-only aggregate refresh
  now runs hourly at minute 5. It does not run a collector or model job.

The first scheduled hourly Sunbiz health refresh succeeded. Anonymous reads still
see zero raw entity rows under RLS, and cannot execute the internal refresh.

## Application repairs

- Reconcile `server.py` with the existing PDMR health hotfix branch, preserving
  hash-bound collector receipts and four-table parity validation. This carries
  forward existing source-clock distinctions without importing unrelated CMS UI
  branches.
- Read independent health sources concurrently using one bounded process pool.
  A refresh has a seven-second read deadline; an HTTP caller waits at most eight
  seconds. Requests share one refresh. Slow reads remain explicit errors, and
  completed independent reads remain usable.
- Cached responses include sample age, serving time, and cache status. An expired
  snapshot served during a slow/failed refresh labels current source status
  `unavailable` and preserves its previous status/clocks separately. It cannot
  clear a source incident using an old green snapshot.
- Read FAA/FDEP status from the existing sanitized terminal receipt table.
  Missing receipts remain unavailable; failed runs and aging receipts remain
  visible. No raw receipt or private entity access is added.
- Expire saved Sunbiz and daily detector success labels at read time. The private
  CMS no longer treats any stored Sunbiz row as proof of current exact matching.
- Require an affirmative approval state and a valid approval timestamp in both
  public story adapters. An old approval timestamp cannot override a hold/draft
  state. The tracker fallback also requires explicit eligibility.
- Block unresolved issues in CMS approval and public story normalization.
- Bound scheduled monitor HTTP requests without relaxing its health assertions.

## Verification and installation

Run `npm run test:unit` and the existing browser workflow. Focused tests cover
concurrent/cold/expired health snapshots, receipt aging, failed source reads,
Sunbiz exact matching, held story rejection, and a disposable SQLite/HTTP CMS
flow from draft through authorized approval and back to hold.

These tests use fixture content and never send newsletter campaigns or write
production editorial records. They do not replace the separate production
newsroom's four actual model reviews or the owner's final approval.

The cloud coding workspace has no production SSH identity or Mac checkout.
Database changes were verified live; application installation requires the
existing authenticated host deployment path. Follow
[`ops/droplet/README_PUBLIC_API.md`](ops/droplet/README_PUBLIC_API.md): inspect the
real checkout and incoming diff, preserve dirty work, back up durable SQLite,
require a tested fast-forward, then restart and verify the HTTPS boundary.
Do not replace a newer private desktop/backend with this repository's older CMS.

After installation, verify `/api/data-health` contains terminal FAA/FDEP clocks,
honest Sunbiz status, current PDMR parity evidence, and no unexpected read errors.
Verify `/api/cms` remains approved-only. Do not enable publication or send merely
because a health check or code test passed.

The Supabase CLI migration-file step was blocked by automatic approval because
of an unsolicited telemetry connection. Authenticated Supabase migrations were
used instead; tracked filenames match the returned applied migration versions.
