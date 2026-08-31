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
| `20260830233000_acclaim_run_receipts.sql` | append-only `broward_clerk_preliminary_run` receipts separating event, attempted-source and system clocks; public read, service-role insert only; no schedule | **NO — code-only, approval required** |
| `20260831052701_source_run_ledgers_and_parcel_generations.sql` | private append-only FDEP/FAA terminal run receipts; generation-bound Broward parcel range/staging receipts and locked atomic promotion gate; no collector, grant, schedule, or promotion | **NO — code-only, export-first + approval required** |

**Not tracked here (pre-existing / other work):** `fdep_erp`, `faa_oeaaa` tables + their edge functions and primary pg_cron jobs; `refresh_dashboard_cache`. The FAA transient retry schedule added on 2026-08-15 is recorded in the operations handoff. Those objects otherwise remain as originally applied.

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
