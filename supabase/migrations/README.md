# Supabase migration inventory (project `jrjewmzkyluxdywyusrw` / florida-signal-prod)

Tracked, idempotent SQL mirroring live production. No secrets in this directory.

| File | Objects | Applied live |
|---|---|---|
| `20260719_001_broward_clerk_preliminary.sql` | table `broward_clerk_preliminary`, indexes `clerk_prelim_uniq` (partial, `instrument_number <> ''`), `clerk_prelim_date_idx`, `clerk_prelim_type_idx`; RLS on; policy `clerk_prelim_public_read` (SELECT, public) | 2026-07-19 |
| `20260719_002_clerk_preliminary_reconciliation.sql` | columns `verification_status`, `preliminary_first_seen_at`, `verified_business_date`, `verified_doc_type`, `reconciled_at`, `conflict_flag`, `conflict_note`; index `clerk_prelim_status_idx`; function `reconcile_clerk_preliminary()`; pg_cron `clerk-preliminary-reconcile` (`0 10 * * *`) | 2026-07-19 |
| `20260811235116_restore_editorial_loop.sql` | freshness-gated transfer view, aggregate pipeline health, sealed evidence fields, exact Transfer → Permit detector, refresh + Candidate pg_cron jobs | 2026-08-11 |
| `20260811235949_label_source_delay_without_blocking_verified_candidates.sql` | separates snapshot lag from the external Clerk release delay; hardens legacy transfer view and queue trigger search path | 2026-08-11 |
| `20260812000230_index_health_event_clocks.sql` | partial FDEP event/fetch indexes for bounded public health probes | 2026-08-11 |
| `20260815172000_sunbiz_private_health_receipt.sql` | aggregate-only Sunbiz freshness receipt and daily post-ingest refresh; raw entity rows stay private | 2026-08-15 |
| `20260830233000_acclaim_run_receipts.sql` | append-only `broward_clerk_preliminary_run` receipts separating event, attempted-source and system clocks; public read, service-role insert only; no schedule | **2026-08-31 — applied remotely as `20260831005904 acclaim_run_receipts`** |
| `20260831052701_source_run_ledgers_and_parcel_generations.sql` | private append-only FDEP/FAA terminal run receipts; generation-bound Broward parcel range/staging receipts and locked atomic promotion gate; no collector, schedule, or promotion | **2026-08-31 — applied; empty/default-off** |
| `20260901012400_external_source_atomic_commit.sql` | private RLS-forced recoverable stage plus service-role-only SECURITY INVOKER RPC that commits FDEP/FAA source rows and one immutable receipt atomically | **NO — exact production privilege approval required; safely orders after live `20260831220548`** |
| `20260901012500_external_source_collector_cron_cutover.sql` | private dispatch/alert ledgers, owner-only Vault-backed dispatcher, daily watchdog, and owner-only disable/activate functions preserving existing FDEP/FAA cadence | **NO — default-off; applying it alone does not change cron** |

**Pre-existing / other work:** `fdep_erp`, `faa_oeaaa` tables and primary
pg_cron jobs; `refresh_dashboard_cache`. The exact deployed FDEP/FAA version-1
sources were exported and hashed before tracked atomic replacements were added
under `supabase/functions/`; those replacements are not deployed until the
second migration receives exact privilege approval. The FAA transient retry
schedule added on 2026-08-15 is recorded in the operations handoff.

## 20260831052701 — source receipts + parcel generations

- `external_source_run_receipts` is private and append-only. It accepts only
  FDEP ERP and FAA OE/AAA terminal receipts, separates run/observation/attempted
  event/real-world event clocks, reconciles every row count, and binds schema
  plus private raw-manifest hashes. Client roles receive no access;
  `service_role` receives only receipt `SELECT`/`INSERT`.
- `broward_parcel_import_generations`,
  `broward_parcel_generation_ranges`, and
  `broward_parcel_geography_stage` prevent ranges or rows from different
  dataset vintages from satisfying one countywide import.
- `fs_promote_broward_parcel_generation(uuid)` is revoked from every Data API
  role. It atomically replaces the live countywide table only after exact
  range topology, raw-count accounting, per-range staged OBJECTID membership,
  reviewed rejection/duplicate-collapse bounds, unique folios/object IDs,
  normalized raw folios, and Broward bbox checks pass. The dependent
  `broward_property_transfer_map` is refreshed in the same transaction.
- The existing unbound parcel import/range ledgers remain historical evidence
  and cannot satisfy this gate.
- The exact deployed `fdep-erp-sync`, `faa-oeaaa-sync`, and
  `broward-parcel-sync` sources/configuration must be exported and hashed before
  any collector integration. The migration contains no invented Edge source,
  cron, runtime parcel grant, or live promotion.

See `SOURCE_RUN_LEDGER_AND_PARCEL_PROMOTION_RUNBOOK.md` for the approval-gated
operator sequence and recovery boundary.

## 20260901012400 — atomic FDEP/FAA collector commit (pending)

- `external_source_run_stage` is private, RLS-forced, recoverable staging.
  Only `service_role` receives row privileges; client roles receive none.
- `fs_commit_external_source_run(text, uuid, jsonb, jsonb)` is
  `SECURITY INVOKER`, has an empty search path, is executable only by
  `service_role`, serializes count classification by source, validates the
  exact source/run/status-bound private Storage manifest plus every referenced
  raw object, computes the canonical manifest hash in the database, and
  commits source rows plus the immutable receipt in one transaction. The
  immutable receipt retains the canonical manifest under
  `source_metadata.raw_manifest`. The trusted service-role collector supplies
  per-object content hashes; the RPC validates their format, run prefix, and
  Storage existence but does not download and re-hash Storage bytes.
- Tracked Edge replacements persist immutable raw responses and a private
  manifest, stage a complete run, and call only the atomic RPC. They read
  `FL_SIGNAL_SYNC_KEY` from Edge Function secrets and fail closed if it is
  unset or still the rejected placeholder.
- Every external request is bounded by a per-request and overall deadline with
  reserved failure-receipt time. The exact terminal payload is retained in the
  private manifest; ambiguous RPC responses retry the same payload and read the
  immutable receipt back instead of attempting a contradictory failure.
- The corrected FDEP replacement uses distinct layer-0 and layer-1 source
  contracts and a bounded 90-day default. It does not repair older malformed
  layer-0 normalized columns; that history requires a separately previewed,
  explicitly approved repair. The corrected FAA path omits the stored
  generated `in_broward` column from staging, classification, inserts and
  updates so PostgreSQL remains its sole owner. Its version-4 XML parser uses
  the official `caseId`, decodes XML entities, admits only a validated
  `caseList` envelope, and fails closed on error HTML, malformed XML or schema
  drift instead of misreporting those responses as an empty run. Parser v4
  admits the audited live OE entity population under a finite 4,096-reference
  ceiling and recognizes five additional official fields as raw-only evidence.
- Production application/deployment is blocked until the operator explicitly
  approves the service-role staging DML and RPC EXECUTE privilege. No collector
  canary may precede that approval.

## 20260901012500 — secret-safe schedule cutover (pending/default-off)

- Creates private dispatch and durable alert ledgers plus owner-only
  `SECURITY INVOKER` dispatch, health-check, disable and activation functions.
- `service_role` receives read-only table access to those ledgers and no
  identity-sequence privilege; only the owner functions create ledger rows.
- Dispatch resolves only the names `fl_signal_functions_base_url` and
  `fl_signal_external_source_sync_key` from Vault at execution time. Neither
  secret value nor the project URL is present in Git or `cron.job.command`.
- Activation preserves FDEP `20 9 * * *`, FAA `40 9 * * *`, FAA retry
  `10 10,11 * * *`, and installs the receipt watchdog at `0 12 * * *` UTC.
- Each scheduled dispatch receives a UUID that is carried into the collector's
  terminal receipt. The watchdog accepts only that exact correlation; a manual
  or unrelated same-day receipt cannot mask a missing natural run.
- The watchdog persists private database alerts; it does not itself send an
  external email/page/chat notification.
- Applying the migration does not alter any cron job. An owner must first call
  the disable function, deploy and canary both collectors, then explicitly call
  the activation function. The same disable function is the rollback boundary.

## 2026-08-11 — durable editorial loop

- `property-transfer-refresh`: `20 19 * * 1-5` UTC; refreshes the deed/parcel snapshot and
  records its source-relative event lag.
- `transfer-permit-candidates-v1`: `30 3 * * *` UTC; adds no more than eight unqueued,
  exact-folio Candidate packets per run.
- `broward_property_transfer_current` returns no rows when the materialized snapshot trails
  the ingested verified Clerk table by more than two business days.
- External Clerk publication delay is disclosed separately. It does not turn older verified
  rows into false rows.
- Candidate packets are private, hash-sealed and idempotent by stable Candidate ID. No database
  job publishes a story or sends a newsletter.

See `EDITORIAL_LOOP_RUNBOOK.md` at the repository root for operation and recovery.

**Authority guarantees**
- `reconcile_clerk_preliminary()` UPDATEs only `broward_clerk_preliminary`; the authoritative
  `broward_clerk_records_*` tables are read-only inputs. Verified rows can never be overwritten by preliminary values.
- pg_cron job `clerk-preliminary-reconcile` invokes only that one function.
- Writes to the preliminary table require the service role (RLS grants public SELECT only).
- No triggers exist on the preliminary table.
- Rollback SQL is documented at the bottom of `002` and has **not** been executed.

## 20260719_004 — countywide parcel authority (Phases 2–5)
| Object | Purpose |
|---|---|
| `broward_parcel_geography` | Countywide parcel centroids (WGS84) from Broward County GIS `PARCEL_POLY_BCPA_TAXROLL/FeatureServer/0` (org `_BCGIS`, public, 554,358 parcels). PK `parcel_id_normalized`. Broward bbox CHECK. RLS read. **Separate from `gis_enrichment`** (permit-derived) to preserve provenance. |
| `broward_parcel_import_runs` | Import audit: pages/rows/rejections by reason, failed pages, COMPLETE/PARTIAL/FAILED. A partial run can never record COMPLETE. |
| `fs_normalize_folio(text)` | Canonical folio normalization. |

**Edge function `broward-parcel-sync`** — DEPLOYED, **no schedule created** (one-time/resumable; `?offset=&pages=`, `?probe=1` for read-only inspection).

### Folio rule (binding)
Broward folios are **canonical 12-character ALPHANUMERIC** identifiers (`484306BH0010`). Letters and
leading zeros are significant. Normalization = trim → uppercase → strip only non-alphanumerics →
reject blank / all-zero sentinel / length ≠ 12. **Digits-only normalization is prohibited**: it strips
letters and collapses distinct parcels (measured: 1,295 collision groups spanning 5,056 folios).

### Rollback
```sql
drop table if exists public.broward_parcel_geography;
drop table if exists public.broward_parcel_import_runs;
drop function if exists public.fs_normalize_folio(text);
-- edge function: delete via Supabase dashboard (no schedule exists to remove)
```
