-- Florida Signal · countywide parcel-location authority (Phases 2–4)
-- Source: Broward County GIS (ArcGIS Online org _BCGIS), layer PARCEL_POLY_BCPA_TAXROLL/FeatureServer/0
--   https://services.arcgis.com/JMAJrTsHNLrSsWf5/arcgis/rest/services/PARCEL_POLY_BCPA_TAXROLL/FeatureServer/0
--   access: public · 554,358 parcel polygons · supportsReturningGeometryCentroid: true · outSR=4326 (WGS84)
-- ADDITIVE + ISOLATED: does not touch gis_enrichment (permit-derived) or the frozen scorer registries.
-- ROLLBACK: drop table broward_parcel_geography, broward_parcel_import_runs; drop function fs_normalize_folio(text);

create or replace function public.fs_normalize_folio(raw text)
returns text language sql immutable as $$
  select case when raw is null then null else (
    with cleaned as (select upper(regexp_replace(raw, '[^A-Za-z0-9]', '', 'g')) as v)
    select case
      when v = '' then null
      when v ~ '^0+$' then null          -- sentinel placeholders e.g. -000000000000
      when length(v) <> 12 then null     -- Broward folio is exactly 12 characters
      else v end from cleaned) end;
$$;
-- NOTE: Broward folios are ALPHANUMERIC (e.g. 484306BH0010 condo/special parcels).
-- 79% of gis_enrichment folios (18,144 of 22,853) contain letters. Stripping non-digits both
-- corrupts them AND creates false collisions, so we strip only formatting characters.

create table if not exists public.broward_parcel_geography (
  parcel_id_normalized text primary key,
  parcel_id_raw text not null,
  folio_number_raw text,
  latitude double precision not null,
  longitude double precision not null,
  address text, municipality text, property_type text,
  geometry_source text not null default 'esri_centroid_wgs84',
  source_name text not null default 'Broward County GIS — PARCEL_POLY_BCPA_TAXROLL',
  source_layer_url text not null default 'https://services.arcgis.com/JMAJrTsHNLrSsWf5/arcgis/rest/services/PARCEL_POLY_BCPA_TAXROLL/FeatureServer/0',
  source_object_id bigint, source_dataset_vintage text,
  location_precision text not null default 'parcel_centroid',
  active_or_historical text not null default 'active',
  source_attributes_json jsonb,
  fetched_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint parcel_geo_broward_bbox
    check (latitude between 25.90 and 26.50 and longitude between -80.70 and -79.98)
);
create index if not exists parcel_geo_latlon_idx on public.broward_parcel_geography (latitude, longitude);
create index if not exists parcel_geo_muni_idx on public.broward_parcel_geography (municipality);
create index if not exists parcel_geo_srcobj_idx on public.broward_parcel_geography (source_object_id);
alter table public.broward_parcel_geography enable row level security;
drop policy if exists parcel_geo_read on public.broward_parcel_geography;
create policy parcel_geo_read on public.broward_parcel_geography for select using (true);

create table if not exists public.broward_parcel_import_runs (
  run_id bigint generated always as identity primary key,
  started_at timestamptz not null default now(), completed_at timestamptz,
  source_url text not null, source_reported_count integer,
  pages_requested integer default 0, rows_received integer default 0,
  rows_accepted integer default 0, rows_rejected integer default 0,
  rejected_missing_folio integer default 0, rejected_bad_folio_format integer default 0,
  rejected_missing_centroid integer default 0, rejected_out_of_bounds integer default 0,
  duplicate_folios integer default 0, inserted_count integer default 0, updated_count integer default 0,
  failed_pages jsonb default '[]'::jsonb, source_metadata jsonb, failure_reason text,
  status text not null default 'RUNNING' check (status in ('RUNNING','COMPLETE','PARTIAL','FAILED'))
);
alter table public.broward_parcel_import_runs enable row level security;
drop policy if exists parcel_import_read on public.broward_parcel_import_runs;
create policy parcel_import_read on public.broward_parcel_import_runs for select using (true);
