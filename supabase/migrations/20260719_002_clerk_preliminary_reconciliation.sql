-- Florida Signal · Preliminary→Verified reconciliation
-- Idempotent. Mirrors live definitions in project jrjewmzkyluxdywyusrw as of 2026-07-19.
-- SAFETY: this function only ever UPDATEs public.broward_clerk_preliminary.
-- It never writes to broward_clerk_records_doc/party/legal/link/run (the authoritative feed),
-- which are read-only inputs here. Date disagreements are FLAGGED, never merged.

alter table public.broward_clerk_preliminary
  add column if not exists verification_status text not null default 'preliminary',
  add column if not exists preliminary_first_seen_at timestamptz not null default now(),
  add column if not exists verified_business_date date,
  add column if not exists verified_doc_type text,
  add column if not exists reconciled_at timestamptz,
  add column if not exists conflict_flag boolean not null default false,
  add column if not exists conflict_note text;

create index if not exists clerk_prelim_status_idx
  on public.broward_clerk_preliminary (verification_status);

create or replace function public.reconcile_clerk_preliminary()
returns table(matched integer, conflicts integer, aged_unmatched integer)
language plpgsql
as $$
declare m integer; c integer; a integer;
begin
  -- Confirmed matches: same normalized instrument AND same record date.
  with v as (
    select regexp_replace(instrument_number, '\D', '', 'g') as inst,
           recording_date_iso, business_date, doc_type_code
    from public.broward_clerk_records_doc
  )
  update public.broward_clerk_preliminary p
     set verification_status = 'verified',
         verified_business_date = v.business_date,
         verified_doc_type = v.doc_type_code,
         reconciled_at = now(),
         conflict_flag = false,
         conflict_note = null
    from v
   where p.verification_status <> 'verified'
     and regexp_replace(p.instrument_number, '\D', '', 'g') = v.inst
     and p.record_date = v.recording_date_iso;
  get diagnostics m = row_count;

  -- Conflicts: instrument matches a verified doc but the record date disagrees — flag, don't merge.
  with v as (
    select regexp_replace(instrument_number, '\D', '', 'g') as inst,
           recording_date_iso, business_date
    from public.broward_clerk_records_doc
  )
  update public.broward_clerk_preliminary p
     set conflict_flag = true,
         conflict_note = 'instrument matches verified on ' || v.recording_date_iso ||
                         ' but preliminary record_date=' || p.record_date
    from v
   where p.verification_status <> 'verified'
     and regexp_replace(p.instrument_number, '\D', '', 'g') = v.inst
     and p.record_date <> v.recording_date_iso;
  get diagnostics c = row_count;

  -- Aged unmatched: preliminary rows inside the verified feed's coverage that never matched.
  select count(*) into a
  from public.broward_clerk_preliminary p
  where p.verification_status = 'preliminary'
    and p.record_date <= (select max(business_date) from public.broward_clerk_records_run)
    and not p.conflict_flag;

  return query select m, c, a;
end;
$$;

-- Daily reconciliation at 10:00 UTC (after the droplet Clerk ingest lands new business dates).
select cron.unschedule('clerk-preliminary-reconcile')
  where exists (select 1 from cron.job where jobname = 'clerk-preliminary-reconcile');
select cron.schedule('clerk-preliminary-reconcile', '0 10 * * *',
  $$select public.reconcile_clerk_preliminary();$$);

-- ROLLBACK (documented, NOT executed):
--   select cron.unschedule('clerk-preliminary-reconcile');
--   drop function if exists public.reconcile_clerk_preliminary();
--   alter table public.broward_clerk_preliminary
--     drop column if exists verification_status,
--     drop column if exists preliminary_first_seen_at,
--     drop column if exists verified_business_date,
--     drop column if exists verified_doc_type,
--     drop column if exists reconciled_at,
--     drop column if exists conflict_flag,
--     drop column if exists conflict_note;
