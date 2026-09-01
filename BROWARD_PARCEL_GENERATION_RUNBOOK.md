# Broward parcel current-generation collector

**Code state (2026-08-31):** local package only. The foundation migration is
already applied in production, but
`20260831153000_broward_parcel_generation_pipeline.sql`, this collector, and
its disabled monthly timer are not deployed or running. Nothing in this
document is evidence of a production run.

**Read-only development evidence:** file-only run
`8f1d3a2c-5b74-4f20-9d62-6e0a8c731b45` observed the unchanged 554,358-row
source universe on 2026-08-31, attempted exactly 25 rows, produced 23 winners,
0 rejects and 2 duplicate rows, and remained non-promotable. Receipt SHA-256:
`5a0ea8d85b6262d277b37e360aaf8455807b1bfac3c868e41be9a4ee61a25a06`.
It made no Supabase or production write.

**Preserved failed development evidence:** file-only current-generation run
`dac445a3-81e1-450d-afc0-60dd4398a507` captured 16 immutable 500-row pages
(8,000 raw rows) before normalization failed; its SQLite index contains the 15
previously committed pages (7,500 rows). `page-000015.json` preserves source
`OBJECTID=7599`, system `OBJECTID_12=7690`, folio `484202000300`, and
`SALE_DATE_1=-84758400000`. The layer metadata declares that field
`esriFieldTypeDate`, so the value is UTC epoch **milliseconds** and represents
`1967-04-26`; the old magnitude heuristic mistakenly treated it as seconds and
raised `ValueError: year -716 is out of range`. The failed receipt remains
non-promotable with SHA-256
`ebca750accd5d118ab50a1929a5e079835d7b21c711dc9c75dadafc786f00157`.
Do not delete, rewrite, or reuse this run directory. No Supabase or production
write was made.

This package replaces the unsafe direct-to-live parcel refresh with one
current-source stream:

1. freeze the ArcGIS system-OBJECTID set;
2. save every metadata response and raw page immutably;
3. stage every source observation under one generation UUID;
4. choose one winner per normalized folio globally by the smallest numeric
   stable `OBJECTID`, then `OBJECTID_12`;
5. account for every rejection and duplicate, including duplicates whose rows
   land in different 20,000-`OBJECTID` ranges;
6. finish as a non-promotable canary or a reviewable current generation; and
7. promote only through the owner-only preview, backup and atomic foundation
   wrapper.

There is no date/range/backfill argument and the collector has no promotion
method. Grok, Claude, service-role code and the Desk cannot promote it.

## Baseline interpretation

The last verified snapshot reconciles exactly:

```text
554,358 raw source polygons
-    50 rejected out-of-bounds centroids
-21,838 duplicate-folio source rows
=532,470 unique live parcels
```

The 532,470-versus-554,358 difference is therefore **not unexplained missing
coverage**. The problem is that the snapshot is stale and has no immutable
current-generation receipt. The old range ledger also undercounted 6,743
cross-page/range duplicates, so it remains historical evidence and cannot be
used for promotion.

## Fixed contracts

| Mode | Source rows | Minimum winners | Maximum rejects | Maximum duplicate rows | Promotion |
|---|---:|---:|---:|---:|---|
| `canary` | 1–25 | 1 | 24 | 24 | Never |
| `current_generation` | 550,000–560,000 | 530,000 | 200 | 25,000 | Preview only after finalization |

The migration owns these values. The collector supplies only the matching
SHA-256; it cannot widen the thresholds based on what it just observed.

`SALE_DATE_1` has a separate reviewed field-null contract; it never changes
the source-row winner/rejection/duplicate partition. Every finite integral
numeric value is interpreted as ArcGIS UTC epoch milliseconds, including valid
negative values before 1970. Supported ISO dates are `0001-01-01` through
`9999-12-31`. A present non-integral/non-numeric value becomes a null field
with reason `invalid_arcgis_epoch_milliseconds`; an integral value outside that
range becomes a null field with reason
`arcgis_epoch_milliseconds_out_of_supported_range`. The unmodified raw
attribute remains in source evidence and the mapped observation, and every
such decision appears in `manifests/field-nulls.jsonl`. Source null remains
null without a reason. Omission of the requested `SALE_DATE_1` attribute is
schema/response drift and fails the generation rather than impersonating a
source null. The database staging RPC independently verifies the same unit,
date, and reason outcome.

Every failed run is also locally terminal and auditable. Before writing
`failure-receipt.json`, the collector writes `failure-manifest.json` with a
canonical, path-sorted snapshot of every immutable `EvidenceBundle` object
created so far. The receipt binds the manifest's relative path, SHA-256, byte
count, schema version and object count. This includes partial capture: if a
raw page is durable but writing its request receipt fails, that raw page and
its exact captured-row accounting are still sealed into the failure manifest.
The manifest has no observation-time field, so identical immutable inputs
produce identical manifest bytes; it never rewrites or silently repairs an
earlier object.

## Required production prerequisites

Stop before any deployment unless all are satisfied:

- Export and hash the exact deployed `broward-parcel-sync` v5 and
  `broward-parcel-fill` v1 sources/configuration. Preserve the known exports;
  do not reconstruct them from notes.
- Prove no `pg_cron`, systemd, external caller, or operator path will keep
  invoking either legacy direct-to-live writer.
- Take a schema backup and a full live `broward_parcel_geography` backup with
  count, normalized-folio set hash, source-OBJECTID set hash and SHA-256.
- Confirm the private Storage bucket `fl-signal-source-evidence` exists and is
  not public.
- Independently prove the service role can upload and read private evidence
  objects and that `storage.objects.metadata` exposes an exact numeric `size`
  or `contentLength` (the preflight pattern in
  `20260831090000_external_source_atomic_commit.sql` is a useful reference);
  the parcel migration itself grants no Storage privilege.
- Confirm `extensions.pgcrypto`/`extensions.digest`, the applied foundation
  migration, and the dependent `broward_property_transfer_map` exist.
- Confirm `florida-freshness-alert.service` exists before installing the unit;
  it is the systemd `OnFailure` target.
- Review every live-table trigger, inbound foreign key and intentional grant.
- Obtain exact approval to apply the integration migration, including its four
  service-role-only staging RPCs and revocation of direct service-role staging
  and live-table DML.

Apply the migration only after the legacy writer is stopped. Applying it while
that writer is active will intentionally make the legacy writer fail.

## Tests and file-only canary

Run the deterministic suite without network or secrets:

```bash
python3 -m unittest tests.test_broward_parcel_generation
python3 -m unittest tests.test_source_run_ledger_migration
```

When a disposable local Supabase stack is available:

```bash
supabase test db
```

Run the checked-in seven-row fixture canary. Replace the placeholder with a
new lowercase UUID:

```bash
python3 ops/droplet/broward_parcel_generation.py \
  --fixture-dir tests/fixtures/broward_parcel_generation \
  --mode canary --canary-rows 7 --page-size 4 \
  --run-id '<new-lowercase-uuid>' \
  --evidence-root ./work/broward-parcel-canaries
```

Expected accounting is 7 attempted, 2 winners, 4 rejected and 1 duplicate.
The duplicate crosses the 19,999/20,000 range boundary. The receipt must say
`canary_complete`, `dry_run: true`, `promotion_eligible: false`, and
`promotion_performed: false`.

After code review, a 25-row current-source canary is still file-only by
default:

```bash
python3 ops/droplet/broward_parcel_generation.py \
  --allow-network --mode canary --canary-rows 25 \
  --run-id '<new-lowercase-uuid>' \
  --evidence-root ./work/broward-parcel-canaries
```

Its start/end full system-OBJECTID sets must match. Inspect metadata, pages,
SQLite index, winner/rejection/duplicate/field-null/range manifests and the
terminal receipt. A source change during the pull is a failed canary, never an
empty or successful run.

## Approved staging sequence

After the migration is applied, a database canary adds `--write-supabase`.
The environment must already contain `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY`, and the exact bounded gate:

```text
FL_SIGNAL_PARCEL_WRITE_APPROVAL=I_APPROVE_BROWARD_PARCEL_STAGING_ONLY
```

Fixture input is prohibited from writing to Supabase. A source canary ends in
`canary_complete`; database constraints permanently prohibit it from becoming
ready or promoted.

Only after that canary is independently reconciled should an operator run one
new `current-generation` UUID. It collects the entire current source. It does
not reuse the July rows and does not accept a historical range/date:

```bash
python3 ops/droplet/broward_parcel_generation.py \
  --allow-network --mode current-generation --write-supabase \
  --run-id '<approved-new-generation-uuid>' \
  --evidence-root /var/lib/florida-signal/broward-parcel-generations
```

The service role can call only four empty-search-path, staging-only RPCs. At
upload time the collector downloads every private object, recomputes SHA-256
and byte count between two identical object-info observations. `begin` requires
that observed object ID, update clock and Storage-owned size to still match and
binds them in the append-only ledger. Page/finalize/failure RPCs reject
bare names, replaced objects or mismatched ledger entries. The finalizer also
recomputes a database-owned content digest from every persisted observation;
it does not accept that digest from the collector. Finalization compares the
entire supplied range-manifest array in both directions with the persisted
range ledger, including every count, range bound, object key and SHA-256;
changed, missing, extra or malformed entries cannot replay a terminal receipt.
It
cannot directly write generation/range/page/observation/stage tables, write
`broward_parcel_geography`, alter the fixed contracts, insert a
preview/authorization, or execute promotion.

## Preview, size report, backup and promotion

As database owner, produce the immutable preview; this still does not promote:

```sql
select public.fs_preview_broward_parcel_generation(
  '<approved-new-generation-uuid>'::uuid
);
```

Report `live_rows_before`, `generation_rows`, `rows_added`, `rows_removed`,
`rows_changed`, `rows_unchanged`, the two folio-set hashes and
`preview_sha256`. Unexpected movement blocks promotion. Never turn that result
into an unrestricted historical repair.

Take a new exact live backup immediately after the preview, upload it to the
private evidence bucket, download it again, and independently verify its
SHA-256 and byte count. Query the Storage object ID/update clock immediately
before and after that download and require both observations to be identical;
those observed literals form the version fence below. The immutable object key must
start `broward-parcel-backups/<generation-uuid>/` and contain that exact
SHA-256. Only after a human explicitly approves that exact preview and backup
may the database owner insert one row:

```sql
insert into public.broward_parcel_promotion_authorizations (
  generation_id,
  preview_sha256,
  backup_object_key,
  backup_sha256,
  backup_bytes,
  backup_storage_object_id,
  backup_storage_updated_at,
  backup_verification_method,
  approval_scope
) select
  '<approved-new-generation-uuid>'::uuid,
  '<exact-preview-sha256>',
  'broward-parcel-backups/<approved-new-generation-uuid>/live-<exact-backup-sha256>.csv.gz',
  '<exact-backup-sha256>',
  <exact-downloaded-byte-count>,
  '<identical-before-and-after-storage-object-id>'::uuid,
  '<identical-before-and-after-storage-updated-at>'::timestamptz,
  'owner_private_storage_download_sha256_v1',
  'current_generation_only_no_historical_backfill'
from storage.objects o
join storage.buckets b on b.id = o.bucket_id
where o.bucket_id = 'fl-signal-source-evidence'
  and b.public = false
  and o.name = 'broward-parcel-backups/<approved-new-generation-uuid>/live-<exact-backup-sha256>.csv.gz'
  and o.id = '<identical-before-and-after-storage-object-id>'::uuid
  and o.updated_at = '<identical-before-and-after-storage-updated-at>'::timestamptz
  and coalesce(o.metadata->>'size', o.metadata->>'contentLength', '') ~ '^[0-9]+$'
  and coalesce(o.metadata->>'size', o.metadata->>'contentLength')::numeric
    = <exact-downloaded-byte-count>;
```

Require this statement to insert exactly one row. The wrapper verifies the
same private object ID, update clock and Storage-owned size still exist and
that the live row set exactly matches the immutable preview, then invokes the
foundation function in one transaction. If live state changed, a new
generation and preview are required:

```sql
select public.fs_promote_broward_parcel_generation(
  '<approved-new-generation-uuid>'::uuid
);
```

Verify live count, one non-null generation ID, folio and source-OBJECTID
uniqueness, bbox, set hashes, transfer-map refresh and
`broward_parcel_pipeline_health.alert_state = 'CURRENT'`. Preserve the returned
JSON as the operator receipt. Restore only from the exact backup if readback
fails; never reconstruct the old live table from the legacy range ledger.

## Monthly timer and natural-run evidence

The tracked timer is monthly on day 2 at 05:20 UTC with up to 30 minutes of
jitter. It is **default off** in three independent ways:

1. installation does not enable the timer;
2. the service requires the absent marker
   `/etc/florida-signal/enable-broward-parcel-generation`; and
3. the exact staging-only environment approval is required.

The service uses a dedicated nonblocking `flock`. It does not share the
property-transfer database lock, avoiding the old reverse-lock/deadlock risk;
database finalization and promotion retain a consistent child-before-parent
lock order. Do not enable this timer alongside `florida-gisrefresh.timer` or
either legacy parcel writer.

After one manual full generation and promotion passes, install the units but
leave the timer disabled. Before installation, create
`/var/lib/florida-signal/broward-parcel-generations` as `andy:andy` mode `0750`,
install the service/timer as root-owned mode `0644`, run `systemd-analyze
verify` on both units, and confirm the service remains skipped while the marker
is absent. Under a separate enablement approval, create the marker, enable the
timer and preserve evidence from the next natural scheduled run. Verify:

```bash
systemctl is-enabled florida-broward-parcel-generation.timer
systemctl list-timers --all florida-broward-parcel-generation.timer
systemctl show florida-broward-parcel-generation.service \
  -p Result -p ExecMainStatus -p ExecMainExitTimestamp
journalctl -u florida-broward-parcel-generation.service --since '-45 days'
```

A nonzero collector exit triggers `florida-freshness-alert.service`; failed
runs retain immutable local/Storage evidence and a failed database receipt when
staging had begun. Unexpected normalization errors first write and `fsync` a
mode-`0600` terminal local failure receipt (including captured-versus-indexed
source accounting, active raw page SHA-256, original error type/message, and
`promotion_eligible: false`); a failure to deliver that receipt to Storage or
the database is reported separately and never erases the durable local receipt.
The private `broward_parcel_pipeline_alerts` view reports
`UNKNOWN`, `FAILED`, `STALLED` (staging longer than six hours),
`NOT_CONNECTED`, `PARITY_MISMATCH`, `STALE` (older than 45 days), or
`AWAITING_REVIEWED_PROMOTION`; `RUNNING` is visible health but is not emitted as
an alert. The Desk server may read the aggregate view with its server-side
service role; no key or raw evidence reaches the browser.
