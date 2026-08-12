-- Restore the durable Record -> Candidate -> human-review loop.
--
-- This migration does four things and nothing publishes:
--   1. measures and hard-gates the deed/parcel materialized view by event time;
--   2. schedules its refresh independently of any chat or desktop session;
--   3. nominates a capped Transfer -> Permit Candidate from exact parcel joins; and
--   4. seals the source facts in an evidence packet for the existing private review queue.
--
-- Human APPROVE remains an editorial decision only. There is no publication or Mailchimp path.

create extension if not exists pgcrypto with schema extensions;

create schema if not exists internal;
revoke all on schema internal from public, anon, authenticated;

-- Count weekdays strictly after the older date through the newer date. This is used only for
-- freshness suppression; it is not an assertion about the Clerk's publication calendar.
create or replace function public.fs_business_days_between(older_date date, newer_date date)
returns integer
language sql
stable
set search_path = ''
as $$
  select case
    when older_date is null or newer_date is null then null
    when newer_date <= older_date then 0
    else count(*)::integer
  end
  from pg_catalog.generate_series(older_date + 1, newer_date, interval '1 day') day_value
  where extract(isodow from day_value) between 1 and 5
$$;

revoke all on function public.fs_business_days_between(date, date) from public;
grant execute on function public.fs_business_days_between(date, date) to anon, authenticated;

-- Public, aggregate-only state. No Candidate content, reviewer identity or notes are exposed.
create table if not exists public.editorial_pipeline_health (
  component       text primary key,
  status          text not null,
  event_through   date,
  source_through  date,
  system_time     timestamptz not null default now(),
  detail          text not null,
  metrics         jsonb not null default '{}'::jsonb,
  constraint editorial_pipeline_health_status_ck check
    (status in ('current','delayed','stale','suppressed','error','unavailable'))
);

alter table public.editorial_pipeline_health enable row level security;
drop policy if exists editorial_pipeline_health_public_read on public.editorial_pipeline_health;
create policy editorial_pipeline_health_public_read
  on public.editorial_pipeline_health for select to anon, authenticated using (true);
revoke all on public.editorial_pipeline_health from anon, authenticated;
grant select on public.editorial_pipeline_health to anon, authenticated;

-- The materialized snapshot may be read only when its event clock is close to the authoritative
-- ingested Clerk table. The source's own publication delay is reported separately.
create or replace view public.broward_property_transfer_freshness
with (security_invoker = true)
as
with source_clock as (
  select max(recording_date_iso) filter (where doc_type_code in ('D','EAS')) as source_event_through
  from public.broward_clerk_records_doc
), snapshot_clock as (
  select max(recording_date) as snapshot_event_through
  from public.broward_property_transfer_map
)
select
  source_event_through,
  snapshot_event_through,
  public.fs_business_days_between(snapshot_event_through, source_event_through) as snapshot_lag_business_days,
  public.fs_business_days_between(source_event_through, current_date) as source_age_business_days,
  coalesce(public.fs_business_days_between(snapshot_event_through, source_event_through) <= 2, false) as snapshot_is_current,
  coalesce(
    public.fs_business_days_between(snapshot_event_through, source_event_through) <= 2
    and public.fs_business_days_between(source_event_through, current_date) <= 2,
    false
  ) as editorial_ready
from source_clock cross join snapshot_clock;

revoke all on public.broward_property_transfer_freshness from anon, authenticated;
grant select on public.broward_property_transfer_freshness to anon, authenticated;

-- Public maps and modules use this gate instead of the raw snapshot. If the refresh falls behind,
-- it returns no rows rather than silently presenting old deeds as a current module.
create or replace view public.broward_property_transfer_current
with (security_invoker = true)
as
select snapshot.*
from public.broward_property_transfer_map snapshot
cross join public.broward_property_transfer_freshness freshness
where freshness.snapshot_is_current;

revoke all on public.broward_property_transfer_current from anon, authenticated;
grant select on public.broward_property_transfer_current to anon, authenticated;

-- Add versioned evidence fields to the existing private queue. Existing rows remain valid.
alter table public.signal_review_queue
  add column if not exists candidate_type text,
  add column if not exists detector_version text,
  add column if not exists nomination_reason text,
  add column if not exists evidence_packet jsonb not null default '{}'::jsonb,
  add column if not exists evidence_hash text,
  add column if not exists receipt_status text not null default 'PENDING';

do $$
begin
  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conname = 'signal_review_queue_receipt_status_ck'
      and conrelid = 'public.signal_review_queue'::regclass
  ) then
    alter table public.signal_review_queue
      add constraint signal_review_queue_receipt_status_ck
      check (receipt_status in ('PENDING','SEALED','FAILED'));
  end if;
end $$;

-- Exact parcel joins and the active review tray are the two high-frequency paths in this slice.
create index if not exists idx_permits_verified_parcel_applied
  on public.permits (parcel_id_verified, applied_date desc)
  where parcel_id_verified is not null and parcel_source is not null and coalesce(invalid, 0) = 0;

create index if not exists idx_review_active_priority
  on public.signal_review_queue (source_record_date desc, amount desc nulls last)
  where review_status in ('NEW','REVIEWING','HOLD','NEEDS_MORE_REPORTING');

-- Candidate source view. It groups related permit applications into one deed/parcel packet so a
-- project with structural and trade permits does not flood the review queue. The join is exact:
-- verified permit parcel == Clerk lgl-ver canonical folio == official county parcel.
create or replace view internal.transfer_permit_candidates_v1
with (security_invoker = true)
as
with normalized_permits as (
  select
    p.*,
    case when p.applied_date ~ '^\d{4}-\d{2}-\d{2}$' then p.applied_date::date end as permit_event_date
  from public.permits p
  where p.parcel_id_verified is not null
    and p.parcel_source is not null
    and p.applied_date >= to_char(current_date - 45, 'YYYY-MM-DD')
    and coalesce(p.invalid, 0) = 0
), matched as (
  select
    transfer.instrument_number,
    transfer.recording_date,
    transfer.consideration_amount,
    transfer.folio_canonical,
    transfer.address as transfer_address,
    transfer.latitude,
    transfer.longitude,
    transfer.linkage_method,
    permit.permit_number,
    permit.permit_event_date,
    permit.address as permit_address,
    permit.permit_type,
    permit.description,
    permit.work_type,
    permit.status as permit_status,
    permit.valuation as native_permit_valuation,
    permit.parcel_source,
    permit.last_seen_at
  from public.broward_property_transfer_current transfer
  join normalized_permits permit
    on permit.parcel_id_verified = transfer.folio_canonical
  cross join public.broward_property_transfer_freshness freshness
  where freshness.editorial_ready
    and transfer.doc_type_code = 'D'
    and transfer.map_eligible
    and transfer.verification_state = 'VERIFIED'
    and permit.permit_event_date between transfer.recording_date and transfer.recording_date + 365
    and (
      permit.valuation >= 250000
      or lower(concat_ws(' ', permit.permit_type, permit.description, permit.work_type)) ~
        '(demol|new[[:space:]]+(building|construction|residence|home|duplex|townhome)|major[[:space:]]+renovation|addition)'
    )
), grouped as (
  select
    instrument_number,
    recording_date,
    consideration_amount,
    folio_canonical,
    transfer_address,
    latitude,
    longitude,
    linkage_method,
    max(permit_event_date) as latest_permit_date,
    max(native_permit_valuation) as largest_native_permit_valuation,
    count(*)::integer as related_permit_count,
    (array_agg(
      permit_number order by native_permit_valuation desc nulls last, permit_event_date desc, permit_number
    ))[1] as primary_permit_number,
    jsonb_agg(
      jsonb_build_object(
        'source_table', 'permits',
        'source_record_id', permit_number,
        'event_date', permit_event_date,
        'address', permit_address,
        'permit_type', permit_type,
        'description', description,
        'work_type', work_type,
        'status', permit_status,
        'native_declared_value', native_permit_valuation,
        'parcel_source', parcel_source,
        'system_last_seen_at', last_seen_at
      ) order by native_permit_valuation desc nulls last, permit_event_date desc, permit_number
    ) as permit_records
  from matched
  group by instrument_number, recording_date, consideration_amount, folio_canonical,
           transfer_address, latitude, longitude, linkage_method
), packets as (
  select
    'candidate:transfer-permit:v1:' || instrument_number || ':' || folio_canonical as candidate_id,
    instrument_number,
    recording_date,
    consideration_amount,
    folio_canonical,
    transfer_address,
    latitude,
    longitude,
    latest_permit_date,
    largest_native_permit_valuation,
    related_permit_count,
    primary_permit_number,
    jsonb_build_object(
      'schema_version', 'EvidencePacketV1',
      'candidate_type', 'TRANSFER_THEN_PERMIT',
      'detector', jsonb_build_object('id', 'transfer-permit', 'version', 'v1'),
      'candidate_id', 'candidate:transfer-permit:v1:' || instrument_number || ':' || folio_canonical,
      'sealed_at', now(),
      'join', jsonb_build_object(
        'method', 'EXACT_CANONICAL_FOLIO',
        'canonical_folio', folio_canonical,
        'clerk_linkage_method', linkage_method,
        'rule', 'verified permit parcel equals Clerk lgl-ver folio and official county parcel'
      ),
      'records', jsonb_build_array(
        jsonb_build_object(
          'source_table', 'broward_clerk_records_doc',
          'source_record_id', instrument_number,
          'event_date', recording_date,
          'address', transfer_address,
          'stated_consideration', consideration_amount,
          'verification_state', 'VERIFIED'
        )
      ) || permit_records,
      'supported_claims', jsonb_build_array(
        'The Clerk recorded the identified deed on the stated date.',
        'Fort Lauderdale received the identified permit applications on the stated dates.',
        'The source records carry the same verified canonical parcel identifier.'
      ),
      'unknowns', jsonb_build_array(
        'Whether the deed was an arm''s-length transaction.',
        'Whether the deed parties and permit applicant are related.',
        'Whether any application was issued, whether work started, and the total project cost.'
      ),
      'freshness', (
        select to_jsonb(freshness) from public.broward_property_transfer_freshness freshness
      )
    ) as evidence_packet
  from grouped
)
select
  packets.*,
  encode(extensions.digest(evidence_packet::text, 'sha256'), 'hex') as evidence_hash
from packets
where not exists (
  select 1 from public.signal_review_queue queue where queue.signal_id = packets.candidate_id
);

revoke all on internal.transfer_permit_candidates_v1 from public, anon, authenticated;

create or replace function internal.refresh_property_transfer_snapshot()
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  freshness record;
  outcome jsonb;
begin
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtext('florida-signal:property-transfer-refresh'));
  refresh materialized view concurrently public.broward_property_transfer_map;

  select * into freshness from public.broward_property_transfer_freshness;
  outcome := jsonb_build_object(
    'snapshot_event_through', freshness.snapshot_event_through,
    'source_event_through', freshness.source_event_through,
    'snapshot_lag_business_days', freshness.snapshot_lag_business_days,
    'snapshot_is_current', freshness.snapshot_is_current
  );

  insert into public.editorial_pipeline_health
    (component, status, event_through, source_through, system_time, detail, metrics)
  values
    ('property-transfer-snapshot',
     case when freshness.snapshot_is_current then 'current' else 'stale' end,
     freshness.snapshot_event_through,
     freshness.source_event_through,
     now(),
     case when freshness.snapshot_is_current
       then 'Materialized deed/parcel snapshot refreshed and inside the two-business-day gate.'
       else 'Materialized deed/parcel snapshot remains outside the two-business-day gate; current modules are suppressed.'
     end,
     outcome)
  on conflict (component) do update set
    status = excluded.status,
    event_through = excluded.event_through,
    source_through = excluded.source_through,
    system_time = excluded.system_time,
    detail = excluded.detail,
    metrics = excluded.metrics;

  return outcome;
exception when others then
  insert into public.editorial_pipeline_health
    (component, status, system_time, detail, metrics)
  values
    ('property-transfer-snapshot', 'error', now(),
     'Property-transfer refresh failed; current modules remain freshness-gated.',
     jsonb_build_object('sqlstate', sqlstate, 'error', left(sqlerrm, 300)))
  on conflict (component) do update set
    status = excluded.status,
    system_time = excluded.system_time,
    detail = excluded.detail,
    metrics = excluded.metrics;
  return jsonb_build_object('ok', false, 'sqlstate', sqlstate, 'error', left(sqlerrm, 300));
end
$$;

create or replace function internal.enqueue_transfer_permit_candidates_v1(candidate_limit integer default 8)
returns integer
language plpgsql
security invoker
set search_path = ''
as $$
declare
  inserted_count integer := 0;
  freshness record;
begin
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtext('florida-signal:transfer-permit-v1'));
  select * into freshness from public.broward_property_transfer_freshness;

  if not coalesce(freshness.editorial_ready, false) then
    insert into public.editorial_pipeline_health
      (component, status, event_through, source_through, system_time, detail, metrics)
    values
      ('transfer-permit-v1', 'suppressed', freshness.snapshot_event_through,
       freshness.source_event_through, now(),
       'Candidate generation suppressed because the verified Clerk feed or transfer snapshot is outside the freshness gate.',
       to_jsonb(freshness))
    on conflict (component) do update set
      status = excluded.status,
      event_through = excluded.event_through,
      source_through = excluded.source_through,
      system_time = excluded.system_time,
      detail = excluded.detail,
      metrics = excluded.metrics;
    return 0;
  end if;

  insert into public.signal_review_queue (
    signal_id, signal_type, candidate_type, detector_version,
    source_table, source_record_id, source_record_date, layer,
    verified_parcel_id, latitude, longitude, amount,
    generated_headline, generated_summary, nomination_reason,
    evidence_packet, evidence_hash, receipt_status, review_status
  )
  select
    candidate_id,
    'TRANSFER_THEN_PERMIT',
    'TRANSFER_THEN_PERMIT',
    'v1',
    'broward_clerk_records_doc+permits',
    instrument_number || '+' || primary_permit_number,
    latest_permit_date,
    'development',
    folio_canonical,
    latitude,
    longitude,
    largest_native_permit_valuation,
    'Permit activity follows a recorded deed at ' || coalesce(transfer_address, 'parcel ' || folio_canonical),
    'Clerk instrument ' || instrument_number || ' was recorded ' || recording_date ||
      '; ' || related_permit_count || ' related Fort Lauderdale permit application' ||
      case when related_permit_count = 1 then ' was' else 's were' end ||
      ' filed afterward on the same verified parcel. Review the sealed records before making any public claim.',
    'Exact parcel join plus a substantial or development-type permit filing after a recorded deed.',
    evidence_packet,
    evidence_hash,
    'SEALED',
    'NEW'
  from internal.transfer_permit_candidates_v1
  order by latest_permit_date desc, largest_native_permit_valuation desc nulls last,
           consideration_amount desc nulls last, candidate_id
  limit greatest(0, least(coalesce(candidate_limit, 8), 25))
  on conflict (signal_id) do nothing;

  get diagnostics inserted_count = row_count;

  insert into public.editorial_pipeline_health
    (component, status, event_through, source_through, system_time, detail, metrics)
  values
    ('transfer-permit-v1', 'current', freshness.snapshot_event_through,
     freshness.source_event_through, now(),
     case when inserted_count = 0
       then 'Detector completed; no new exact-join Candidates were added.'
       else inserted_count || ' exact-join Candidate packet(s) added to the private human review queue.'
     end,
     jsonb_build_object('inserted_candidates', inserted_count, 'daily_cap', greatest(0, least(coalesce(candidate_limit, 8), 25))))
  on conflict (component) do update set
    status = excluded.status,
    event_through = excluded.event_through,
    source_through = excluded.source_through,
    system_time = excluded.system_time,
    detail = excluded.detail,
    metrics = excluded.metrics;

  return inserted_count;
end
$$;

revoke all on function internal.refresh_property_transfer_snapshot() from public, anon, authenticated;
revoke all on function internal.enqueue_transfer_permit_candidates_v1(integer) from public, anon, authenticated;

-- Durable schedules. They survive laptop sleep, Wi-Fi loss and chat/session termination.
select cron.unschedule('property-transfer-refresh')
where exists (select 1 from cron.job where jobname = 'property-transfer-refresh');
select cron.schedule(
  'property-transfer-refresh',
  '20 19 * * 1-5',
  $$set statement_timeout to '9min'; select internal.refresh_property_transfer_snapshot();$$
);

select cron.unschedule('transfer-permit-candidates-v1')
where exists (select 1 from cron.job where jobname = 'transfer-permit-candidates-v1');
select cron.schedule(
  'transfer-permit-candidates-v1',
  '30 3 * * *',
  $$set statement_timeout to '5min'; select internal.enqueue_transfer_permit_candidates_v1(8);$$
);

-- Seed health rows honestly. The first scheduled/manual run replaces these values.
insert into public.editorial_pipeline_health (component, status, detail)
values
  ('property-transfer-snapshot', 'unavailable', 'Awaiting the first durable refresh run.'),
  ('transfer-permit-v1', 'unavailable', 'Awaiting the first freshness-cleared detector run.')
on conflict (component) do nothing;

comment on view public.broward_property_transfer_current is
  'Freshness-gated deed/parcel snapshot. Returns zero rows when the materialized view trails the ingested authoritative Clerk table by more than two business days.';
comment on function internal.enqueue_transfer_permit_candidates_v1(integer) is
  'Creates capped, sealed Transfer -> Permit Candidates from exact parcel joins. It never publishes.';
