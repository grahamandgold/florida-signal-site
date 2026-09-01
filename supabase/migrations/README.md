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
| `20260831090000_external_source_atomic_commit.sql` | private RLS-forced recoverable stage plus service-role-only SECURITY INVOKER RPC that commits FDEP/FAA source rows and one immutable receipt atomically | **NO — exact production privilege approval required** |
| `20260831153000_broward_parcel_generation_pipeline.sql` | fixed parcel quality contracts; immutable page/observation evidence; global deterministic folio finalizer; preview/backup-bound atomic promotion wrapper; private Desk/alert health | **NO — code only; legacy writer retirement, backup, migration approval and canary required** |

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

## 20260831090000 — atomic FDEP/FAA collector commit (pending)

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
- Production application/deployment is blocked until the operator explicitly
  approves the service-role staging DML and RPC EXECUTE privilege. No collector
  canary may precede that approval.

## 20260831153000 — current-generation Broward parcel pipeline (pending)

- `broward_parcel_generation_pages` and
  `broward_parcel_generation_observations` preserve every current-source row
  before deduplication. The database finalizer applies one global winner rule:
  minimum numeric stable `OBJECTID`, then system `OBJECTID_12`.
- `broward_parcel_evidence_objects` is a private append-only ledger. The
  collector must download every uploaded object, recompute SHA-256/size, and
  fence that read with identical before/after object info before binding the
  receipt to the exact observed Storage object ID/update clock and
  Storage-owned byte count before page staging or finalization can proceed.
- The fixed migration-owned production contract admits 550,000–560,000 raw
  rows, requires at least 530,000 winners, and allows at most 200 rejects and
  25,000 duplicate source rows. The 1–25-row canary contract is permanently
  non-promotable.
- The service role may call four narrow staging/finalization RPCs; direct DML
  on staging or `broward_parcel_geography`, contract mutation and promotion
  are revoked.
- Promotion requires an immutable add/remove/change preview and an independently
  downloaded/hashed private backup whose exact Storage ID, update clock and byte
  count are bound into owner authorization before the existing atomic foundation
  is invoked.
- `broward_parcel_pipeline_health` and `_alerts` are private aggregate hooks
  for the server-side Desk and freshness alert. The tracked monthly systemd
  timer is default-off and additionally marker/env gated.

See `BROWARD_PARCEL_GENERATION_RUNBOOK.md`. Applying the migration, deploying
the collector, writing a canary, staging a full generation, authorizing a
promotion and enabling the timer are distinct approval gates.

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
| `broward_parcel_geography` | Countywide parcel centroids (WGS84) from Broward County GIS `PARCEL_POLY_BCPA_TAXROLL/FeatureServer/0`. The verified baseline reconciles 554,358 raw polygons minus 50 bbox rejects minus 21,838 duplicate-folio rows to exactly 532,470 unique live parcels; the difference is not unexplained missing coverage, but the snapshot is stale/unreceipted. PK `parcel_id_normalized`. Broward bbox CHECK. RLS read. **Separate from `gis_enrichment`** (permit-derived) to preserve provenance. |
| `broward_parcel_import_runs` | Import audit: pages/rows/rejections by reason, failed pages, COMPLETE/PARTIAL/FAILED. A partial run can never record COMPLETE. |
| `fs_normalize_folio(text)` | Canonical folio normalization. |

**Legacy Edge function `broward-parcel-sync` v5** — DEPLOYED, exported and
hashed, **no schedule created**. Its actual controls are `?stats=1`, `?batch=N`
and `?range=min-max`; older `?offset=&pages=` / `?probe=1` notes are wrong. It
writes range/page-local winners directly to the live table and cannot safely
perform a current refresh. Retire it before applying the current-generation
integration migration; never run it concurrently with the new collector.

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
