-- 006 — The county layer publishes no SITE_ADDRESS field; situs address is stored as components.
-- It also publishes, per parcel, the most recent sale with the Clerk Instrument Number (CIN).
-- Those columns exist ONLY to cross-check the Clerk-instrument -> parcel linkage. They are not a
-- new data source and drive no product feature.
-- NOTE (verified 2026-07-19): the layer's MUNICIPALITY column is empty for all 554,358 records.
-- SITUS_CITY is a two-letter county code with no published lookup table; no label is inferred.
alter table public.broward_parcel_geography
  add column if not exists situs_city          text,
  add column if not exists situs_zip           text,
  add column if not exists sale_1_cin          text,
  add column if not exists sale_1_deed_type    text,
  add column if not exists sale_1_date         date,
  add column if not exists sale_1_stamp_amount numeric;

create index if not exists idx_parcel_sale_1_cin on public.broward_parcel_geography(sale_1_cin)
  where sale_1_cin is not null;

comment on column public.broward_parcel_geography.sale_1_cin is
  'BCPA-published Clerk Instrument Number for the most recent recorded sale. Verification cross-check only. Cannot corroborate the current Clerk holdings: BCPA sales end 2024-09-27, the Clerk feed begins 2026-04-23.';
