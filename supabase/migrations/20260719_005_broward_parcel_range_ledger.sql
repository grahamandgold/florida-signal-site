-- 005 — Provable coverage ledger for the one-time countywide Broward parcel import.
-- Partitions the official source by OBJECTID range so completeness is verifiable: a COMPLETE
-- sub-run is not evidence of whole-county completion. NO schedule is attached.
create table if not exists public.broward_parcel_range_ledger (
  range_id                  bigserial primary key,
  oid_min                   bigint not null,
  oid_max                   bigint not null,          -- inclusive
  expected_source_count     integer,                  -- source returnCountOnly for this range
  rows_received             integer not null default 0,
  rows_accepted             integer not null default 0,
  rows_rejected             integer not null default 0,
  rejected_missing_folio    integer not null default 0,
  rejected_bad_folio_format integer not null default 0,
  rejected_missing_centroid integer not null default 0,
  rejected_out_of_bounds    integer not null default 0,
  duplicate_folios          integer not null default 0,
  status                    text not null default 'PENDING',
  attempts                  integer not null default 0,
  last_error                text,
  started_at                timestamptz,
  completed_at              timestamptz,
  constraint parcel_range_bounds check (oid_max >= oid_min),
  constraint parcel_range_status check (status in ('PENDING','IN_PROGRESS','COMPLETE','FAILED')),
  constraint parcel_range_unique unique (oid_min, oid_max)
);
create index if not exists idx_parcel_range_status on public.broward_parcel_range_ledger(status);
alter table public.broward_parcel_range_ledger enable row level security;
do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public'
                 and tablename='broward_parcel_range_ledger' and policyname='parcel_range_ledger_anon_read') then
    create policy parcel_range_ledger_anon_read on public.broward_parcel_range_ledger
      for select to anon using (true);
  end if;
end $$;

-- 110 disjoint ranges of 20,000 covering [0 .. 2,199,999]; the source span is [2 .. 2,185,857].
insert into public.broward_parcel_range_ledger (oid_min, oid_max)
select g, g + 19999 from generate_series(0, 2180000, 20000) as g
on conflict (oid_min, oid_max) do nothing;

comment on table public.broward_parcel_range_ledger is
  'Coverage ledger for the one-time Broward countywide parcel-centroid import. Whole-import COMPLETE requires: every range COMPLETE, zero gaps, zero overlaps, counts reconciled.';
