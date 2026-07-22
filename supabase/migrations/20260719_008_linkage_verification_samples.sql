-- 008 — Stratified audit sample of the Clerk-instrument -> county-parcel linkage.
-- Retained as evidence. No record classified CONFLICT or UNRESOLVED may be map-eligible.
create table if not exists public.broward_linkage_verification_samples (
  sample_id            bigserial primary key,
  stratum              text not null,
  instrument_number    text not null,
  doc_type_code        text,
  instrument_kind      text,
  recording_date       date,
  consideration_amount numeric,
  folio_raw            text,
  folio_canonical      text,
  source_object_id     bigint,
  latitude             double precision,
  longitude            double precision,
  address              text,
  situs_city           text,
  property_type        text,
  parties              text,
  matched_parcel_count integer,
  linkage_method       text,
  verification_result  text,
  note                 text,
  checked_at           timestamptz not null default now(),
  constraint verification_result_values check (verification_result in ('VERIFIED','CONFLICT','UNRESOLVED'))
);
alter table public.broward_linkage_verification_samples enable row level security;
do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public'
                 and tablename='broward_linkage_verification_samples' and policyname='linkage_samples_anon_read') then
    create policy linkage_samples_anon_read on public.broward_linkage_verification_samples
      for select to anon using (true);
  end if;
end $$;
