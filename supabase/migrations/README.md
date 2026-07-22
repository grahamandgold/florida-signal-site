# Supabase migration inventory (project `jrjewmzkyluxdywyusrw` / florida-signal-prod)

Tracked, idempotent SQL mirroring live production. No secrets in this directory.

| File | Objects | Applied live |
|---|---|---|
| `20260719_001_broward_clerk_preliminary.sql` | table `broward_clerk_preliminary`, indexes `clerk_prelim_uniq` (partial, `instrument_number <> ''`), `clerk_prelim_date_idx`, `clerk_prelim_type_idx`; RLS on; policy `clerk_prelim_public_read` (SELECT, public) | 2026-07-19 |
| `20260719_002_clerk_preliminary_reconciliation.sql` | columns `verification_status`, `preliminary_first_seen_at`, `verified_business_date`, `verified_doc_type`, `reconciled_at`, `conflict_flag`, `conflict_note`; index `clerk_prelim_status_idx`; function `reconcile_clerk_preliminary()`; pg_cron `clerk-preliminary-reconcile` (`0 10 * * *`) | 2026-07-19 |

**Not tracked here (pre-existing / other work):** `fdep_erp`, `faa_oeaaa` tables + their edge functions and pg_cron jobs; `refresh_dashboard_cache`. Those remain as originally applied.

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
