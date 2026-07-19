-- 007 — Read-only exact linkage between Clerk instruments and official county parcels.
--
-- ONE linkage method is trusted: DIRECT_EXACT_FOLIO — the folio the Clerk publishes in the lgl-ver
-- legal file, normalised canonically and matched by exact string equality to the county parcel
-- layer. No fuzzy matching, no owner-name geocoding, no legal-description parsing.
--
-- Mortgages, liens, lis pendens and judgments are deliberately absent. The Clerk SFTP files carry
-- no parcel identifier for them, and broward_clerk_records_link does not reach a parcel-bearing
-- instrument for those categories (audited 2026-07-19: mortgages 1 of 10,357 inheritable, liens 0,
-- lis pendens 0, judgments 0). They are a separate future-source project.
create or replace view public.broward_property_transfer_links as
with legal as (
  -- The legal file can list one folio several times per instrument (one row per description line).
  select distinct on (l.instrument_number, public.fs_normalize_folio(l.parcel_id))
         l.instrument_number,
         public.fs_normalize_folio(l.parcel_id) as folio_canonical,
         l.parcel_id as folio_raw,
         l.legal_description
  from public.broward_clerk_records_legal l
  where public.fs_normalize_folio(l.parcel_id) is not null
  order by l.instrument_number, public.fs_normalize_folio(l.parcel_id), l.source_row_number
),
joined as (
  select d.instrument_number, d.doc_type_code, d.recording_date_iso::date as recording_date,
         d.consideration_amount, d.verified_flag, d.documentary_tax,
         lg.folio_canonical, lg.folio_raw, lg.legal_description,
         g.source_object_id, g.latitude, g.longitude,
         g.address, g.situs_city, g.situs_zip, g.property_type
  from public.broward_clerk_records_doc d
  join legal lg on lg.instrument_number = d.instrument_number
  left join public.broward_parcel_geography g on g.parcel_id_normalized = lg.folio_canonical
  where d.doc_type_code in ('D','EAS')
),
counted as (
  select j.*, count(*) filter (where j.source_object_id is not null)
           over (partition by j.instrument_number) as matched_parcel_count
  from joined j
)
select instrument_number, doc_type_code,
       case doc_type_code when 'D' then 'deed' when 'EAS' then 'easement' end as instrument_kind,
       recording_date, consideration_amount, documentary_tax, verified_flag,
       folio_canonical, folio_raw, legal_description,
       source_object_id, latitude, longitude, address, situs_city, situs_zip, property_type,
       matched_parcel_count,
       'DIRECT_EXACT_FOLIO'::text as linkage_method,
       case when source_object_id is null then 'UNRESOLVED'
            when matched_parcel_count > 1 then 'CONFLICT'
            else 'VERIFIED' end as verification_state,
       case when source_object_id is null then 'clerk folio not present in the official county parcel layer'
            when matched_parcel_count > 1 then 'instrument references more than one parcel; a single map point would misstate it'
            else null end as exclusion_reason,
       (source_object_id is not null and matched_parcel_count = 1) as map_eligible
from counted;

grant select on public.broward_property_transfer_links to anon;

-- The un-materialised join exceeds the interactive statement timeout (57014) when the map queries
-- it, so reads go through a materialised copy. NO schedule is attached — refresh is manual:
--   refresh materialized view concurrently public.broward_property_transfer_map;
drop materialized view if exists public.broward_property_transfer_map;
create materialized view public.broward_property_transfer_map as
select * from public.broward_property_transfer_links;

create unique index idx_ptm_unique     on public.broward_property_transfer_map (instrument_number, folio_canonical);
create index idx_ptm_type_date on public.broward_property_transfer_map (doc_type_code, recording_date desc);
create index idx_ptm_bbox      on public.broward_property_transfer_map (latitude, longitude) where map_eligible;
create index idx_ptm_folio     on public.broward_property_transfer_map (folio_canonical);
create index idx_ptm_instrument on public.broward_property_transfer_map (instrument_number);
create index idx_ptm_city      on public.broward_property_transfer_map (situs_city) where map_eligible;
create index idx_ptm_amount    on public.broward_property_transfer_map (consideration_amount desc nulls last) where map_eligible;

grant select on public.broward_property_transfer_map to anon;
