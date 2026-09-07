-- Private, idempotent product mirror for the bounded SFWMD Pending ERP lane.
--
-- The DigitalOcean SQLite database remains canonical. This migration is a
-- separately approved deployment prerequisite: it does not schedule a fetch,
-- expose rows publicly, score anything, or write the editorial queue.

-- This is an admission migration, not a schema reconciler. Refuse any partial,
-- pre-created, case-variant, or otherwise poisoned namespace before the first
-- write. Supabase migration history supplies one-time execution; a replay must
-- fail rather than silently inherit unreviewed definitions, policies, or ACLs.
do $$
begin
  if exists (
    select 1
    from pg_catalog.pg_class object
    join pg_catalog.pg_namespace namespace on namespace.oid = object.relnamespace
    where namespace.nspname = 'public'
      and pg_catalog.left(pg_catalog.lower(object.relname), 18) = 'sfwmd_pending_erp_'
  ) or exists (
    select 1
    from pg_catalog.pg_proc routine
    join pg_catalog.pg_namespace namespace on namespace.oid = routine.pronamespace
    where namespace.nspname = 'public'
      and (
        pg_catalog.left(pg_catalog.lower(routine.proname), 9) = 'fs_sfwmd_'
        or pg_catalog.lower(routine.proname) = 'fs_commit_sfwmd_pending_erp_run'
      )
  ) or exists (
    select 1
    from pg_catalog.pg_type object
    join pg_catalog.pg_namespace namespace on namespace.oid = object.typnamespace
    where namespace.nspname = 'public'
      and pg_catalog.left(pg_catalog.lower(object.typname), 18) = 'sfwmd_pending_erp_'
  ) then
    raise exception using
      errcode = '55000',
      message = 'refusing preexisting or partial SFWMD mirror namespace';
  end if;
end
$$;

create table public.sfwmd_pending_erp_runs (
  run_id uuid primary key,
  payload_sha256 text not null unique check (payload_sha256 ~ '^[0-9a-f]{64}$'),
  status text not null check (status in ('ok', 'empty', 'partial', 'failed')),
  progress_status text not null check (progress_status in ('changed', 'unchanged', 'empty', 'uncommitted', 'superseded')),
  natural_run boolean not null,
  observed_at timestamptz not null,
  completed_at timestamptz not null,
  event_through timestamptz,
  rows_observed integer not null check (rows_observed between 0 and 2000),
  rows_accepted integer not null check (rows_accepted between 0 and 500),
  rows_inserted integer not null check (rows_inserted >= 0),
  rows_updated integer not null check (rows_updated >= 0),
  rows_unchanged integer not null check (rows_unchanged >= 0),
  rows_retired integer not null check (rows_retired >= 0),
  rows_rejected integer not null check (rows_rejected >= 0),
  observation_order_key text not null,
  provenance_sha256 text not null check (provenance_sha256 ~ '^[0-9a-f]{64}$'),
  receipt jsonb not null check (jsonb_typeof(receipt) = 'object'),
  created_at timestamptz not null default now(),
  check (observed_at <= completed_at),
  check (rows_accepted = rows_inserted + rows_updated + rows_unchanged),
  check (status not in ('partial', 'failed') or (rows_accepted = 0 and rows_inserted = 0 and rows_updated = 0 and rows_retired = 0)),
  check (progress_status <> 'superseded' or (rows_accepted = 0 and rows_retired = 0))
);

create table public.sfwmd_pending_erp_records (
  identity_key text primary key check (btrim(identity_key) <> ''),
  global_id uuid not null,
  app_no text not null check (btrim(app_no) <> ''),
  source_object_id bigint not null,
  source_content_sha256 text not null check (source_content_sha256 ~ '^[0-9a-f]{64}$'),
  record jsonb not null check (jsonb_typeof(record) = 'object'),
  event_received_at timestamptz,
  first_seen_at timestamptz not null,
  last_seen_at timestamptz not null,
  last_changed_at timestamptz not null,
  is_current boolean not null default true,
  retired_at timestamptz,
  last_run_id uuid not null references public.sfwmd_pending_erp_runs(run_id),
  check ((is_current and retired_at is null) or not is_current),
  unique (global_id, app_no)
);

create table public.sfwmd_pending_erp_versions (
  identity_key text not null,
  source_content_sha256 text not null check (source_content_sha256 ~ '^[0-9a-f]{64}$'),
  record jsonb not null check (jsonb_typeof(record) = 'object'),
  first_observed_at timestamptz not null,
  first_run_id uuid not null references public.sfwmd_pending_erp_runs(run_id),
  primary key (identity_key, source_content_sha256)
);

create table public.sfwmd_pending_erp_state (
  singleton integer primary key check (singleton = 1),
  latest_snapshot_order_key text,
  latest_snapshot_run_id uuid references public.sfwmd_pending_erp_runs(run_id),
  latest_natural_order_key text,
  latest_natural_run_id uuid references public.sfwmd_pending_erp_runs(run_id),
  updated_at timestamptz,
  check ((latest_snapshot_order_key is null) = (latest_snapshot_run_id is null)),
  check ((latest_natural_order_key is null) = (latest_natural_run_id is null))
);

insert into public.sfwmd_pending_erp_state (singleton) values (1)
on conflict (singleton) do nothing;

create index sfwmd_pending_erp_records_current_idx
  on public.sfwmd_pending_erp_records (is_current, event_received_at desc, app_no);
create index sfwmd_pending_erp_runs_completed_idx
  on public.sfwmd_pending_erp_runs (completed_at desc);

alter table public.sfwmd_pending_erp_runs enable row level security;
alter table public.sfwmd_pending_erp_runs force row level security;
alter table public.sfwmd_pending_erp_records enable row level security;
alter table public.sfwmd_pending_erp_records force row level security;
alter table public.sfwmd_pending_erp_versions enable row level security;
alter table public.sfwmd_pending_erp_versions force row level security;
alter table public.sfwmd_pending_erp_state enable row level security;
alter table public.sfwmd_pending_erp_state force row level security;

-- Default privileges can grant a custom role directly even on a newly created
-- table. Remove every non-owner ACL entry before installing the reviewed
-- service_role matrix; do not assume the four standard Supabase roles are the
-- only possible grantees.
do $$
declare
  acl_entry record;
begin
  for acl_entry in
    select distinct object.relname, object.relowner, privilege.grantee
    from pg_catalog.pg_class object
    join pg_catalog.pg_namespace namespace on namespace.oid = object.relnamespace
    cross join lateral pg_catalog.aclexplode(
      coalesce(
        object.relacl,
        pg_catalog.acldefault('r', object.relowner)
      )
    ) privilege
    where namespace.nspname = 'public'
      and object.relname in (
        'sfwmd_pending_erp_runs',
        'sfwmd_pending_erp_records',
        'sfwmd_pending_erp_versions',
        'sfwmd_pending_erp_state'
      )
      and privilege.grantee <> object.relowner
  loop
    if acl_entry.grantee = 0 then
      execute pg_catalog.format(
        'revoke all privileges on table public.%I from public',
        acl_entry.relname
      );
    else
      execute pg_catalog.format(
        'revoke all privileges on table public.%I from %I',
        acl_entry.relname,
        pg_catalog.pg_get_userbyid(acl_entry.grantee)
      );
    end if;
  end loop;
end
$$;

revoke all on table public.sfwmd_pending_erp_runs from public, anon, authenticated, service_role;
revoke all on table public.sfwmd_pending_erp_records from public, anon, authenticated, service_role;
revoke all on table public.sfwmd_pending_erp_versions from public, anon, authenticated, service_role;
revoke all on table public.sfwmd_pending_erp_state from public, anon, authenticated, service_role;
grant select, insert on table public.sfwmd_pending_erp_runs to service_role;
grant select, insert, update on table public.sfwmd_pending_erp_records to service_role;
grant select, insert on table public.sfwmd_pending_erp_versions to service_role;
grant select, update on table public.sfwmd_pending_erp_state to service_role;

create function public.fs_sfwmd_receipt_immutable()
returns trigger language plpgsql security invoker set search_path = '' as $$
begin
  raise exception using errcode = '55000', message = 'SFWMD receipts and versions are immutable';
end
$$;

create trigger sfwmd_pending_erp_runs_immutable
before update or delete on public.sfwmd_pending_erp_runs
for each row execute function public.fs_sfwmd_receipt_immutable();
create trigger sfwmd_pending_erp_versions_immutable
before update or delete on public.sfwmd_pending_erp_versions
for each row execute function public.fs_sfwmd_receipt_immutable();

create function public.fs_sfwmd_canonical_jsonb(p_value jsonb)
returns text
language plpgsql
immutable
strict
security invoker
set search_path = ''
as $$
declare
  v_result text;
begin
  case pg_catalog.jsonb_typeof(p_value)
    when 'object' then
      select '{' || coalesce(pg_catalog.string_agg(
        pg_catalog.to_jsonb(item.key)::text || ':' ||
          public.fs_sfwmd_canonical_jsonb(item.value),
        ',' order by item.key collate "C"
      ), '') || '}' into v_result
      from pg_catalog.jsonb_each(p_value) item(key,value);
    when 'array' then
      select '[' || coalesce(pg_catalog.string_agg(
        public.fs_sfwmd_canonical_jsonb(item.value),
        ',' order by item.ordinality
      ), '') || ']' into v_result
      from pg_catalog.jsonb_array_elements(p_value) with ordinality item(value,ordinality);
    else
      v_result := p_value::text;
  end case;
  return v_result;
end
$$;

create function public.fs_commit_sfwmd_pending_erp_run(
  p_run_id uuid,
  p_payload_sha256 text,
  p_receipt jsonb,
  p_rows jsonb
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_existing public.sfwmd_pending_erp_runs%rowtype;
  v_row jsonb;
  v_status text;
  v_observed_at timestamptz;
  v_inserted integer := 0;
  v_updated integer := 0;
  v_unchanged integer := 0;
  v_retired integer := 0;
  v_prior_hash text;
  v_prior_current boolean;
  v_content_index_sha256 text;
  v_ordered_rows_sha256 text;
  v_computed_payload_sha256 text;
  v_payload_basis text;
  v_row_count integer;
  v_rows_observed integer;
  v_rows_accepted integer;
  v_rows_rejected integer;
  v_observation_order_key text;
  v_latest_snapshot_order_key text;
  v_latest_natural_order_key text;
  v_snapshot_advances boolean := false;
  v_natural_latest_advances boolean := false;
  v_expected_progress text;
  v_trigger_at timestamptz;
  v_event_through text;
begin
  if p_run_id is null or p_payload_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception using errcode = '22023', message = 'valid run id and payload sha256 are required';
  end if;
  if jsonb_typeof(p_receipt) is distinct from 'object'
     or jsonb_typeof(p_rows) is distinct from 'array'
     or jsonb_typeof(p_receipt -> 'provenance') is distinct from 'object'
     or jsonb_typeof(p_receipt -> 'counts') is distinct from 'object'
     or jsonb_typeof(p_receipt -> 'versions') is distinct from 'object'
     or jsonb_typeof(p_receipt -> 'evidence') is distinct from 'object'
     or jsonb_typeof(p_receipt -> 'mirror') is distinct from 'object'
     or jsonb_typeof(p_receipt -> 'safety') is distinct from 'object' then
    raise exception using errcode = '22023', message = 'receipt object and rows array are required';
  end if;
  if (select count(*) from pg_catalog.jsonb_object_keys(p_receipt)) <> 23
     or p_receipt - array[
    'schema_version','run_id','natural_run','provenance','observation_order_key',
    'status','reason_code','progress_status',
    'connection_state','started_at','observed_at','completed_at','source_checked_at',
    'source_modified_at','source_modified_status','event_through',
    'event_through_semantics','counts','source_content_index_sha256','versions',
    'evidence','mirror','safety'
  ]::text[] <> '{}'::jsonb then
    raise exception using errcode = '23514', message = 'receipt contains unknown fields';
  end if;
  if p_receipt ->> 'schema_version' is distinct from 'FloridaSignalSfwmdPendingErpProductionReceiptV1'
     or p_receipt ->> 'run_id' is distinct from p_run_id::text
     or p_receipt ->> 'connection_state' is distinct from 'not_connected'
     or coalesce((p_receipt ->> 'natural_run')::boolean, false) is false
     or p_receipt #>> '{safety,unrestricted_backfill}' is distinct from 'false'
     or p_receipt #>> '{safety,scoring}' is distinct from 'false'
     or p_receipt #>> '{safety,candidate_or_queue_write}' is distinct from 'false'
     or p_receipt #>> '{safety,publication}' is distinct from 'false'
     or p_receipt #>> '{safety,connected_label_allowed}' is distinct from 'false'
     or p_receipt #>> '{safety,bounded_current_pending_snapshot_only}' is distinct from 'true'
     or p_receipt #>> '{provenance,invocation_kind}' is distinct from 'systemd_timer'
     or p_receipt #>> '{provenance,schema_version}' is distinct from 'FloridaSignalSfwmdRunProvenanceV1'
     or p_receipt #>> '{provenance,verified}' is distinct from 'true'
     or p_receipt #>> '{provenance,natural_run}' is distinct from 'true'
     or p_receipt #>> '{provenance,timer_unit}' is distinct from 'florida-sfwmd-pending-erp.timer'
     or p_receipt #>> '{provenance,service_unit}' is distinct from 'florida-sfwmd-pending-erp-timer.service'
     or coalesce(p_receipt #>> '{provenance,systemd_invocation_id}','') !~ '^[0-9a-f]{32}$'
     or coalesce(p_receipt #>> '{provenance,trigger_timer_realtime_usec}','') !~ '^[0-9]{1,20}$'
     or coalesce((p_receipt #>> '{provenance,trigger_timer_realtime_usec}')::numeric, -1)
          not between 0 and 32503680000000000
     or coalesce(p_receipt #>> '{provenance,runtime_cgroup_sha256}','') !~ '^[0-9a-f]{64}$'
     or coalesce(p_receipt #>> '{provenance,canary_sha256}','') !~ '^[0-9a-f]{64}$'
     or coalesce(p_receipt #>> '{provenance,canary_path}','') !~ ('/' || p_run_id::text || '\.json$')
     or p_receipt #>> '{mirror,eligible}' is distinct from 'true'
     or p_receipt #>> '{mirror,state}' is distinct from 'pending'
     or p_receipt #>> '{mirror,idempotency}' is distinct from 'run_id_plus_database_computed_payload_sha256'
     or p_receipt #>> '{mirror,digest_basis}' is distinct from 'FloridaSignalSfwmdPostgresPayloadV1'
     or coalesce(p_receipt #>> '{mirror,ordered_rows_sha256}','') !~ '^[0-9a-f]{64}$'
     or coalesce(p_receipt #>> '{mirror,database_payload_sha256}','') !~ '^[0-9a-f]{64}$'
     or coalesce(p_receipt ->> 'source_content_index_sha256','') !~ '^[0-9a-f]{64}$' then
    raise exception using errcode = '23514', message = 'receipt identity or safety state is invalid';
  end if;
  v_status := p_receipt ->> 'status';
  if v_status is null or v_status not in ('ok', 'empty', 'partial', 'failed') then
    raise exception using errcode = '22023', message = 'unsupported terminal status';
  end if;
  if (v_status in ('partial', 'failed') and coalesce(p_receipt ->> 'progress_status','') <> 'uncommitted')
     or (v_status in ('ok', 'empty') and coalesce(p_receipt ->> 'progress_status','') not in ('changed', 'unchanged', 'empty', 'superseded')) then
    raise exception using errcode = '23514', message = 'terminal and progress statuses disagree';
  end if;
  if (p_receipt -> 'provenance') - array[
       'schema_version','natural_run','invocation_kind','verified','timer_unit',
       'service_unit','systemd_invocation_id','trigger_timer_realtime_usec',
       'runtime_cgroup_sha256','scheduled_for','canary_path','canary_sha256'
     ]::text[] <> '{}'::jsonb
     or (select count(*) from pg_catalog.jsonb_object_keys(p_receipt -> 'provenance')) <> 12
     or (p_receipt -> 'mirror') - array[
       'eligible','state','idempotency','digest_basis','row_count',
       'ordered_rows_sha256','database_payload_sha256'
     ]::text[] <> '{}'::jsonb
     or (select count(*) from pg_catalog.jsonb_object_keys(p_receipt -> 'mirror')) <> 7
     or (p_receipt -> 'safety') - array[
       'bounded_current_pending_snapshot_only','unrestricted_backfill','scoring',
       'candidate_or_queue_write','publication','connected_label_allowed'
     ]::text[] <> '{}'::jsonb
     or (select count(*) from pg_catalog.jsonb_object_keys(p_receipt -> 'safety')) <> 6
     or (p_receipt -> 'counts') - array[
       'rows_observed','rows_accepted','rows_inserted','rows_updated',
       'rows_unchanged','rows_retired','rows_rejected'
     ]::text[] <> '{}'::jsonb
     or (select count(*) from pg_catalog.jsonb_object_keys(p_receipt -> 'counts')) <> 7
     or (p_receipt -> 'versions') - array[
       'production_collector','collector','parser','normalizer',
       'sqlite_schema','sqlite_migration_sha256'
     ]::text[] <> '{}'::jsonb
     or (select count(*) from pg_catalog.jsonb_object_keys(p_receipt -> 'versions')) <> 6
     or (p_receipt -> 'evidence') - array[
       'bundle_path','bundle_manifest_sha256','collection_receipt_sha256',
       'raw_manifest_sha256','normalized_records_sha256'
     ]::text[] <> '{}'::jsonb
     or (select count(*) from pg_catalog.jsonb_object_keys(p_receipt -> 'evidence')) <> 5 then
    raise exception using errcode = '23514', message = 'nested receipt contract contains unknown fields';
  end if;
  if pg_catalog.jsonb_typeof(p_receipt -> 'natural_run') is distinct from 'boolean'
     or pg_catalog.jsonb_typeof(p_receipt #> '{provenance,natural_run}') is distinct from 'boolean'
     or pg_catalog.jsonb_typeof(p_receipt #> '{provenance,verified}') is distinct from 'boolean'
     or pg_catalog.jsonb_typeof(p_receipt #> '{mirror,eligible}') is distinct from 'boolean'
     or exists (
       select 1 from pg_catalog.jsonb_each(p_receipt -> 'safety') item(key,value)
       where pg_catalog.jsonb_typeof(item.value) <> 'boolean'
     )
     or exists (
       select 1 from pg_catalog.jsonb_each(p_receipt -> 'evidence') item(key,value)
       where pg_catalog.jsonb_typeof(item.value) <> 'string'
     )
     or exists (
       select 1 from pg_catalog.jsonb_each(
         (p_receipt -> 'provenance') - array['natural_run','verified']::text[]
       ) item(key,value)
       where pg_catalog.jsonb_typeof(item.value) <> 'string'
     )
     or exists (
       select 1 from pg_catalog.jsonb_each(p_receipt -> 'versions') item(key,value)
       where pg_catalog.jsonb_typeof(item.value) <> 'string'
     )
     or exists (
       select 1 from pg_catalog.jsonb_each(
         (p_receipt -> 'mirror') - array['eligible','row_count']::text[]
       ) item(key,value)
       where pg_catalog.jsonb_typeof(item.value) <> 'string'
     )
     or pg_catalog.jsonb_typeof(p_receipt #> '{mirror,row_count}') is distinct from 'number'
     or (p_receipt #> '{mirror,row_count}')::text !~ '^[0-9]+$'
     or exists (
       select 1 from pg_catalog.jsonb_each(p_receipt -> 'counts') item(key,value)
       where pg_catalog.jsonb_typeof(item.value) <> 'number'
          or item.value::text !~ '^[0-9]+$'
     ) then
    raise exception using errcode = '23514', message = 'receipt booleans and counts must use exact JSON types';
  end if;
  v_trigger_at := pg_catalog.to_timestamp(
    ((p_receipt #>> '{provenance,trigger_timer_realtime_usec}')::numeric / 1000000)::double precision
  );
  if p_receipt #>> '{versions,sqlite_schema}' is distinct from 'FloridaSignalSfwmdSqliteV1'
     or p_receipt #>> '{versions,sqlite_migration_sha256}' is distinct from
          'a8f39dfe2d9dcff1ffe85cce16a5771a58138fa2cf6d1dcfc1e96c69a724d088'
     or p_receipt #>> '{versions,production_collector}' is distinct from 'sfwmd-pending-erp-production/1.0.0'
     or p_receipt #>> '{versions,collector}' is distinct from 'sfwmd-pending-erp-shadow/1.0.0'
     or p_receipt #>> '{versions,parser}' is distinct from 'sfwmd-layer14-parser/1.0.0'
     or p_receipt #>> '{versions,normalizer}' is distinct from 'sfwmd-layer14-normalizer/1.0.0'
     or coalesce(p_receipt #>> '{evidence,bundle_path}','') !~ '^/'
     or coalesce(p_receipt #>> '{evidence,bundle_manifest_sha256}','') !~ '^[0-9a-f]{64}$'
     or coalesce(p_receipt #>> '{evidence,collection_receipt_sha256}','') !~ '^[0-9a-f]{64}$'
     or coalesce(p_receipt #>> '{evidence,raw_manifest_sha256}','') !~ '^[0-9a-f]{64}$'
     or coalesce(p_receipt #>> '{evidence,normalized_records_sha256}','') !~ '^[0-9a-f]{64}$'
     or p_receipt ->> 'source_modified_at' is not null
     or p_receipt ->> 'source_modified_status' is distinct from 'UNKNOWN_NOT_EXPOSED'
     or p_receipt ->> 'event_through_semantics' is distinct from
          'maximum AppReceivedDate among included Fort Lauderdale shadow rows'
     or (v_status in ('ok','empty') and p_receipt -> 'reason_code' <> 'null'::jsonb)
     or (v_status = 'partial' and coalesce(p_receipt ->> 'reason_code','') not in (
          'SOURCE_OBJECT_ID_SET_CHANGED_DURING_RUN','ROW_QUALITY_OR_ACCOUNTING_FAILURE'
        ))
     or (v_status = 'failed' and coalesce(p_receipt ->> 'reason_code','') not in (
          'SOURCE_ROW_BUDGET_EXCEEDED','COLLECTOR_OR_CONTRACT_FAILURE'
        ))
     or coalesce(p_receipt ->> 'started_at','') !~
          '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$'
     or coalesce(p_receipt ->> 'observed_at','') !~
          '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$'
     or coalesce(p_receipt ->> 'completed_at','') !~
          '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$'
     or coalesce(p_receipt ->> 'source_checked_at','') !~
          '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$'
     or coalesce(p_receipt #>> '{provenance,scheduled_for}','') !~
          '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$'
     or (p_receipt ->> 'started_at')::timestamptz > (p_receipt ->> 'observed_at')::timestamptz
     or (p_receipt ->> 'observed_at')::timestamptz > (p_receipt ->> 'completed_at')::timestamptz
     or (p_receipt ->> 'source_checked_at')::timestamptz
          not between (p_receipt ->> 'started_at')::timestamptz and (p_receipt ->> 'completed_at')::timestamptz
     or (p_receipt #>> '{provenance,scheduled_for}')::timestamptz
          > (p_receipt ->> 'started_at')::timestamptz
     or v_trigger_at not between
          (p_receipt #>> '{provenance,scheduled_for}')::timestamptz
          and (p_receipt ->> 'started_at')::timestamptz
     or (p_receipt ->> 'started_at')::timestamptz
          > (p_receipt #>> '{provenance,scheduled_for}')::timestamptz + interval '15 minutes'
     or extract(hour from (
          (p_receipt #>> '{provenance,scheduled_for}')::timestamptz
          at time zone 'America/New_York'
        )) <> 6
     or extract(minute from (
          (p_receipt #>> '{provenance,scheduled_for}')::timestamptz
          at time zone 'America/New_York'
        )) <> 17
     or extract(second from (
          (p_receipt #>> '{provenance,scheduled_for}')::timestamptz
          at time zone 'America/New_York'
        )) <> 0
     or (p_receipt ->> 'completed_at')::timestamptz > now() + interval '5 minutes' then
    raise exception using errcode = '23514', message = 'receipt hashes, paths, or clocks are invalid';
  end if;
  if p_receipt ->> 'event_through' is not null and (
       p_receipt ->> 'event_through' !~
         '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$'
       or (p_receipt ->> 'event_through')::timestamptz
          > (p_receipt ->> 'observed_at')::timestamptz
     ) then
    raise exception using errcode = '23514', message = 'event-through clock is invalid';
  end if;
  v_row_count := pg_catalog.jsonb_array_length(p_rows);
  v_rows_observed := (p_receipt #>> '{counts,rows_observed}')::integer;
  v_rows_accepted := (p_receipt #>> '{counts,rows_accepted}')::integer;
  v_rows_rejected := (p_receipt #>> '{counts,rows_rejected}')::integer;
  if v_row_count > 500 then
    raise exception using errcode = '54000', message = 'SFWMD row batch exceeds 500-row safety cap';
  end if;
  if v_rows_observed not between 0 and 2000
     or v_rows_accepted not between 0 and 500
     or v_rows_rejected not between 0 and 2000
     or v_rows_accepted > v_rows_observed
     or v_rows_rejected > v_rows_observed
     or v_rows_accepted + v_rows_rejected > v_rows_observed
     or (p_receipt #>> '{counts,rows_inserted}')::integer not between 0 and 500
     or (p_receipt #>> '{counts,rows_updated}')::integer not between 0 and 500
     or (p_receipt #>> '{counts,rows_unchanged}')::integer not between 0 and 500
     or (p_receipt #>> '{counts,rows_retired}')::integer not between 0 and 500
     or coalesce((p_receipt #>> '{mirror,row_count}')::integer, -1) <> v_row_count
     or (p_receipt ->> 'progress_status' in ('changed','unchanged','empty')
         and v_rows_accepted <> v_row_count)
     or (p_receipt ->> 'progress_status' in ('uncommitted','superseded')
         and v_rows_accepted <> 0)
     or (v_status = 'ok' and v_rows_observed = 0)
     or (v_status = 'empty' and (
       v_rows_observed <> 0 or v_rows_accepted <> 0 or v_rows_rejected <> 0
       or v_row_count <> 0 or p_receipt ->> 'event_through' is not null
       or (p_receipt #>> '{counts,rows_inserted}')::integer <> 0
       or (p_receipt #>> '{counts,rows_updated}')::integer <> 0
       or (p_receipt #>> '{counts,rows_unchanged}')::integer <> 0
     )) then
    raise exception using errcode = '23514', message = 'receipt row counts exceed or contradict bounds';
  end if;
  if exists (
    select 1 from pg_catalog.jsonb_array_elements(p_rows) item(value)
    where jsonb_typeof(item.value) <> 'object'
       or item.value - array[
         'identity_key','global_id','app_no','source_object_id','source_content_sha256',
         'event_received_at','record','record_canonical','record_sha256',
         'source_content_canonical'
       ]::text[] <> '{}'::jsonb
       or (select count(*) from pg_catalog.jsonb_object_keys(item.value)) <> 10
       or pg_catalog.jsonb_typeof(item.value -> 'identity_key') <> 'string'
       or pg_catalog.jsonb_typeof(item.value -> 'global_id') <> 'string'
       or pg_catalog.jsonb_typeof(item.value -> 'app_no') <> 'string'
       or pg_catalog.jsonb_typeof(item.value -> 'source_object_id') <> 'number'
       or pg_catalog.jsonb_typeof(item.value -> 'source_content_sha256') <> 'string'
       or pg_catalog.jsonb_typeof(item.value -> 'record_canonical') <> 'string'
       or pg_catalog.jsonb_typeof(item.value -> 'record_sha256') <> 'string'
       or pg_catalog.jsonb_typeof(item.value -> 'source_content_canonical') <> 'string'
       or pg_catalog.jsonb_typeof(item.value -> 'event_received_at') not in ('string','null')
       or coalesce(item.value ->> 'identity_key','') = ''
       or coalesce(item.value ->> 'global_id','') !~
          '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
       or coalesce(item.value ->> 'app_no','') = ''
       or coalesce(item.value ->> 'source_object_id','') !~ '^[0-9]{1,19}$'
       or coalesce((item.value ->> 'source_object_id')::numeric, -1)
          not between 1 and 9223372036854775807
       or coalesce(item.value ->> 'source_content_sha256','') !~ '^[0-9a-f]{64}$'
       or coalesce(item.value ->> 'record_sha256','') !~ '^[0-9a-f]{64}$'
       or jsonb_typeof(item.value -> 'record') is distinct from 'object'
       or (item.value ->> 'record_canonical') is distinct from
          (public.fs_sfwmd_canonical_jsonb(item.value -> 'record') || chr(10))
       or pg_catalog.encode(
         extensions.digest(
           pg_catalog.convert_to(item.value ->> 'record_canonical', 'UTF8'), 'sha256'
         ), 'hex'
       ) is distinct from item.value ->> 'record_sha256'
       or (item.value ->> 'source_content_canonical') is distinct from
          (public.fs_sfwmd_canonical_jsonb(pg_catalog.jsonb_build_object(
            'schema_version','FloridaSignalSfwmdSourceContentV1',
            'attributes',(item.value #> '{record,attributes}') - 'OBJECTID',
            'geometry',item.value #> '{record,geometry}'
          )) || chr(10))
       or pg_catalog.encode(
         extensions.digest(
           pg_catalog.convert_to(item.value ->> 'source_content_canonical', 'UTF8'), 'sha256'
         ), 'hex'
       ) is distinct from item.value ->> 'source_content_sha256'
       or (item.value #>> '{record,identity_key}') is distinct from (item.value ->> 'identity_key')
       or (item.value #>> '{record,source_content_sha256}') is distinct from (item.value ->> 'source_content_sha256')
       or lower(item.value #>> '{record,identity,global_id}') is distinct from lower(item.value ->> 'global_id')
       or (item.value #>> '{record,identity,app_no}') is distinct from (item.value ->> 'app_no')
       or (item.value ->> 'identity_key') is distinct from
          (lower(item.value ->> 'global_id') || '|' || (item.value ->> 'app_no'))
       or (item.value #>> '{record,source,object_id}') is distinct from (item.value ->> 'source_object_id')
       or (item.value #> '{record,event_clocks,app_received_at}')
          is distinct from (item.value -> 'event_received_at')
       or ((item.value ->> 'event_received_at') is not null and
          (item.value ->> 'event_received_at') !~
            '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$')
  ) then
    raise exception using errcode = '23514', message = 'mirror row contract is invalid';
  end if;
  if (select count(*) from jsonb_array_elements(p_rows)) <>
     (select count(distinct item.value ->> 'identity_key') from jsonb_array_elements(p_rows) item(value)) then
    raise exception using errcode = '23505', message = 'duplicate SFWMD business identity';
  end if;

  select case when max((item.value ->> 'event_received_at')::timestamptz) is null
      then null
      else pg_catalog.to_char(
        max((item.value ->> 'event_received_at')::timestamptz) at time zone 'UTC',
        'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
      ) end
  into v_event_through
  from pg_catalog.jsonb_array_elements(p_rows) item(value)
  where item.value ->> 'event_received_at' is not null;
  if p_receipt ->> 'event_through' is distinct from v_event_through then
    raise exception using errcode = '23514', message = 'event-through does not match mirror rows';
  end if;

  select pg_catalog.encode(
    extensions.digest(
      pg_catalog.convert_to(
        coalesce(pg_catalog.string_agg(
          '{"identity_key":' || pg_catalog.to_json(item.value ->> 'identity_key')::text ||
          ',"source_content_sha256":' || pg_catalog.to_json(item.value ->> 'source_content_sha256')::text ||
          '}' || chr(10), '' order by (item.value ->> 'identity_key') collate "C"
        ), ''), 'UTF8'
      ), 'sha256'
    ), 'hex'
  ) into v_content_index_sha256
  from pg_catalog.jsonb_array_elements(p_rows) item(value);

  select pg_catalog.encode(
    extensions.digest(
      pg_catalog.convert_to(coalesce(pg_catalog.string_agg(
        item.value ->> 'record_canonical', ''
        order by (item.value ->> 'identity_key') collate "C"
      ), ''), 'UTF8'), 'sha256'
    ), 'hex'
  ) into v_ordered_rows_sha256
  from pg_catalog.jsonb_array_elements(p_rows) item(value);

  v_payload_basis := 'FloridaSignalSfwmdPostgresPayloadV1' || chr(10)
    || p_run_id::text || chr(10) || v_status || chr(10)
    || (p_receipt ->> 'progress_status') || chr(10)
    || (p_receipt ->> 'observed_at') || chr(10)
    || v_content_index_sha256 || chr(10) || v_row_count::text || chr(10)
    || v_ordered_rows_sha256 || chr(10);
  v_computed_payload_sha256 := pg_catalog.encode(
    extensions.digest(pg_catalog.convert_to(v_payload_basis, 'UTF8'), 'sha256'), 'hex'
  );
  if v_content_index_sha256 <> p_receipt ->> 'source_content_index_sha256'
     or v_ordered_rows_sha256 <> p_receipt #>> '{mirror,ordered_rows_sha256}'
     or v_computed_payload_sha256 <> p_payload_sha256
     or v_computed_payload_sha256 <> p_receipt #>> '{mirror,database_payload_sha256}'
     or p_receipt #>> '{mirror,digest_basis}' <> 'FloridaSignalSfwmdPostgresPayloadV1' then
    raise exception using errcode = '23514', message = 'database-computed payload or index digest differs';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('florida-signal:sfwmd-pending-erp', 0)
  );
  select * into v_existing from public.sfwmd_pending_erp_runs where run_id = p_run_id;
  if found then
    if v_existing.payload_sha256 <> p_payload_sha256 or v_existing.receipt is distinct from p_receipt then
      raise exception using errcode = '23505', message = 'run id replay conflicts with immutable payload';
    end if;
    return jsonb_build_object(
      'run_id', p_run_id, 'payload_sha256', p_payload_sha256,
      'status', v_existing.status, 'idempotent_replay', true
    );
  end if;

  v_observed_at := (p_receipt ->> 'observed_at')::timestamptz;
  v_observation_order_key := p_receipt ->> 'observation_order_key';
  if v_observation_order_key is distinct from (
       pg_catalog.to_char(
         (p_receipt ->> 'observed_at')::timestamptz at time zone 'UTC',
         'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
       ) || '|' || pg_catalog.to_char(
         (p_receipt ->> 'completed_at')::timestamptz at time zone 'UTC',
         'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
       )
       || '|' || p_run_id::text
     ) then
    raise exception using errcode = '23514', message = 'observation order key is not canonical';
  end if;
  select latest_snapshot_order_key,latest_natural_order_key
  into v_latest_snapshot_order_key,v_latest_natural_order_key
  from public.sfwmd_pending_erp_state where singleton=1 for update;
  if not found then
    raise exception using errcode = '55000', message = 'SFWMD mirror monotonic state is missing';
  end if;
  v_snapshot_advances := v_status in ('ok','empty') and (
    v_latest_snapshot_order_key is null or v_observation_order_key > v_latest_snapshot_order_key
  );
  v_natural_latest_advances := v_latest_natural_order_key is null
    or v_observation_order_key > v_latest_natural_order_key;
  if (v_snapshot_advances and p_receipt ->> 'progress_status' = 'superseded')
     or (not v_snapshot_advances and v_status in ('ok','empty')
         and p_receipt ->> 'progress_status' <> 'superseded') then
    raise exception using errcode = '23514', message = 'client monotonic classification differs';
  end if;

  if v_snapshot_advances then
    for v_row in select value from jsonb_array_elements(p_rows) item(value) loop
      select source_content_sha256, is_current into v_prior_hash, v_prior_current
      from public.sfwmd_pending_erp_records
      where identity_key = v_row ->> 'identity_key';
      if not found then
        v_inserted := v_inserted + 1;
      elsif v_prior_hash is distinct from v_row ->> 'source_content_sha256' or not v_prior_current then
        v_updated := v_updated + 1;
      else
        v_unchanged := v_unchanged + 1;
      end if;
    end loop;
    select count(*)::integer into v_retired
    from public.sfwmd_pending_erp_records current_row
    where current_row.is_current
      and not exists (
        select 1 from jsonb_array_elements(p_rows) item(value)
        where item.value ->> 'identity_key' = current_row.identity_key
      );
  end if;

  v_expected_progress := case
    when v_status in ('partial','failed') then 'uncommitted'
    when not v_snapshot_advances then 'superseded'
    when v_inserted > 0 or v_updated > 0 or v_retired > 0 then 'changed'
    when v_row_count = 0 then 'empty'
    else 'unchanged'
  end;
  if p_receipt ->> 'progress_status' <> v_expected_progress then
    raise exception using errcode = '23514', message = 'database-computed progress classification differs';
  end if;

  if coalesce((p_receipt #>> '{counts,rows_inserted}')::integer, -1) <> v_inserted
     or coalesce((p_receipt #>> '{counts,rows_updated}')::integer, -1) <> v_updated
     or coalesce((p_receipt #>> '{counts,rows_unchanged}')::integer, -1) <> v_unchanged
     or coalesce((p_receipt #>> '{counts,rows_retired}')::integer, -1) <> v_retired then
    raise exception using errcode = '23514', message = 'client and mirror classifications differ';
  end if;

  -- The receipt is inserted first so every row/version foreign key and the
  -- receipt become visible in the same transaction or none do.
  insert into public.sfwmd_pending_erp_runs (
    run_id,payload_sha256,status,progress_status,natural_run,observed_at,completed_at,
    event_through,rows_observed,rows_accepted,rows_inserted,rows_updated,
    rows_unchanged,rows_retired,rows_rejected,observation_order_key,
    provenance_sha256,receipt
  ) values (
    p_run_id,p_payload_sha256,v_status,p_receipt ->> 'progress_status',
    (p_receipt ->> 'natural_run')::boolean,v_observed_at,
    (p_receipt ->> 'completed_at')::timestamptz,nullif(p_receipt ->> 'event_through','')::timestamptz,
    (p_receipt #>> '{counts,rows_observed}')::integer,
    (p_receipt #>> '{counts,rows_accepted}')::integer,v_inserted,v_updated,
    v_unchanged,v_retired,(p_receipt #>> '{counts,rows_rejected}')::integer,
    v_observation_order_key,
    pg_catalog.encode(extensions.digest(
      pg_catalog.convert_to((p_receipt -> 'provenance')::text, 'UTF8'), 'sha256'
    ), 'hex'),p_receipt
  );

  if v_snapshot_advances then
    for v_row in select value from jsonb_array_elements(p_rows) item(value) loop
      insert into public.sfwmd_pending_erp_versions (
        identity_key,source_content_sha256,record,first_observed_at,first_run_id
      ) values (
        v_row ->> 'identity_key',v_row ->> 'source_content_sha256',v_row -> 'record',
        v_observed_at,p_run_id
      ) on conflict do nothing;
      insert into public.sfwmd_pending_erp_records (
        identity_key,global_id,app_no,source_object_id,source_content_sha256,record,
        event_received_at,first_seen_at,last_seen_at,last_changed_at,is_current,retired_at,last_run_id
      ) values (
        v_row ->> 'identity_key',(v_row ->> 'global_id')::uuid,v_row ->> 'app_no',
        (v_row ->> 'source_object_id')::bigint,v_row ->> 'source_content_sha256',v_row -> 'record',
        nullif(v_row ->> 'event_received_at','')::timestamptz,v_observed_at,v_observed_at,
        v_observed_at,true,null,p_run_id
      ) on conflict (identity_key) do update set
        global_id=excluded.global_id,app_no=excluded.app_no,source_object_id=excluded.source_object_id,
        source_content_sha256=excluded.source_content_sha256,record=excluded.record,
        event_received_at=excluded.event_received_at,last_seen_at=excluded.last_seen_at,
        last_changed_at=case when public.sfwmd_pending_erp_records.source_content_sha256 <> excluded.source_content_sha256
          or not public.sfwmd_pending_erp_records.is_current then excluded.last_changed_at
          else public.sfwmd_pending_erp_records.last_changed_at end,
        is_current=true,retired_at=null,last_run_id=excluded.last_run_id;
    end loop;
    update public.sfwmd_pending_erp_records current_row
    set is_current=false,retired_at=v_observed_at,last_run_id=p_run_id
    where current_row.is_current and not exists (
      select 1 from jsonb_array_elements(p_rows) item(value)
      where item.value ->> 'identity_key' = current_row.identity_key
    );
  end if;

  if v_snapshot_advances then
    update public.sfwmd_pending_erp_state
    set latest_snapshot_order_key=v_observation_order_key,
        latest_snapshot_run_id=p_run_id,updated_at=now()
    where singleton=1;
  end if;
  if v_natural_latest_advances then
    update public.sfwmd_pending_erp_state
    set latest_natural_order_key=v_observation_order_key,
        latest_natural_run_id=p_run_id,updated_at=now()
    where singleton=1;
  end if;

  return jsonb_build_object(
    'run_id', p_run_id, 'payload_sha256', p_payload_sha256,
    'status', v_status, 'idempotent_replay', false
  );
end
$$;

-- CREATE FUNCTION grants EXECUTE to PUBLIC by default and project-level
-- default privileges may name additional roles. Clear every non-owner routine
-- ACL, including custom roles, before granting the two required entry points.
do $$
declare
  acl_entry record;
begin
  for acl_entry in
    select distinct
      pg_catalog.format(
        '%I.%I(%s)',
        namespace.nspname,
        routine.proname,
        pg_catalog.oidvectortypes(routine.proargtypes)
      ) as signature,
      routine.proowner,
      privilege.grantee
    from pg_catalog.pg_proc routine
    join pg_catalog.pg_namespace namespace on namespace.oid = routine.pronamespace
    cross join lateral pg_catalog.aclexplode(
      coalesce(
        routine.proacl,
        pg_catalog.acldefault('f', routine.proowner)
      )
    ) privilege
    where namespace.nspname = 'public'
      and routine.proname in (
        'fs_sfwmd_receipt_immutable',
        'fs_sfwmd_canonical_jsonb',
        'fs_commit_sfwmd_pending_erp_run'
      )
      and privilege.grantee <> routine.proowner
  loop
    if acl_entry.grantee = 0 then
      execute pg_catalog.format(
        'revoke all privileges on function %s from public',
        acl_entry.signature
      );
    else
      execute pg_catalog.format(
        'revoke all privileges on function %s from %I',
        acl_entry.signature,
        pg_catalog.pg_get_userbyid(acl_entry.grantee)
      );
    end if;
  end loop;
end
$$;

revoke all on function public.fs_sfwmd_receipt_immutable()
  from public, anon, authenticated, service_role;
revoke all on function public.fs_sfwmd_canonical_jsonb(jsonb)
  from public, anon, authenticated, service_role;
revoke all on function public.fs_commit_sfwmd_pending_erp_run(uuid,text,jsonb,jsonb)
  from public, anon, authenticated, service_role;
grant execute on function public.fs_sfwmd_canonical_jsonb(jsonb) to service_role;
grant execute on function public.fs_commit_sfwmd_pending_erp_run(uuid,text,jsonb,jsonb)
  to service_role;

-- Fail the migration transaction unless the resulting catalog is exactly the
-- reviewed private shape. This catches event-trigger changes, unexpected
-- default privileges, policies, role inheritance effects, or an RLS setup that
-- would make the SECURITY INVOKER RPC unusable.
do $$
declare
  service_oid oid := 'service_role'::pg_catalog.regrole;
  anon_oid oid := 'anon'::pg_catalog.regrole;
  authenticated_oid oid := 'authenticated'::pg_catalog.regrole;
begin
  if exists (
    select 1
    from pg_catalog.pg_class object
    join pg_catalog.pg_namespace namespace on namespace.oid = object.relnamespace
    where namespace.nspname = 'public'
      and object.relname in (
        'sfwmd_pending_erp_runs',
        'sfwmd_pending_erp_records',
        'sfwmd_pending_erp_versions',
        'sfwmd_pending_erp_state'
      )
      and (
        object.relkind <> 'r'
        or object.relrowsecurity is not true
        or object.relforcerowsecurity is not true
      )
  ) or (
    select pg_catalog.count(*)
    from pg_catalog.pg_class object
    join pg_catalog.pg_namespace namespace on namespace.oid = object.relnamespace
    where namespace.nspname = 'public'
      and object.relname in (
        'sfwmd_pending_erp_runs',
        'sfwmd_pending_erp_records',
        'sfwmd_pending_erp_versions',
        'sfwmd_pending_erp_state'
      )
  ) <> 4 then
    raise exception using errcode = '55000', message = 'SFWMD table/RLS postflight failed';
  end if;
  if exists (
    select 1
    from pg_catalog.pg_policy policy
    where policy.polrelid in (
      'public.sfwmd_pending_erp_runs'::pg_catalog.regclass,
      'public.sfwmd_pending_erp_records'::pg_catalog.regclass,
      'public.sfwmd_pending_erp_versions'::pg_catalog.regclass,
      'public.sfwmd_pending_erp_state'::pg_catalog.regclass
    )
  ) then
    raise exception using errcode = '55000', message = 'SFWMD tables must have no RLS policies';
  end if;
  if not (
    select role.rolbypassrls
    from pg_catalog.pg_roles role
    where role.oid = service_oid
  ) then
    raise exception using errcode = '55000', message = 'service_role cannot traverse forced RLS';
  end if;
  if exists (
    select 1
    from pg_catalog.pg_class object
    join pg_catalog.pg_namespace namespace on namespace.oid = object.relnamespace
    cross join lateral pg_catalog.aclexplode(
      coalesce(object.relacl, pg_catalog.acldefault('r', object.relowner))
    ) privilege
    where namespace.nspname = 'public'
      and object.relname in (
        'sfwmd_pending_erp_runs',
        'sfwmd_pending_erp_records',
        'sfwmd_pending_erp_versions',
        'sfwmd_pending_erp_state'
      )
      and privilege.grantee not in (object.relowner, service_oid)
  ) then
    raise exception using errcode = '55000', message = 'SFWMD table ACL postflight found an arbitrary grantee';
  end if;
  if not (
    pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_runs', 'SELECT')
    and pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_runs', 'INSERT')
    and not pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_runs', 'UPDATE')
    and not pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_runs', 'DELETE')
    and not pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_runs', 'TRUNCATE')
    and not pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_runs', 'REFERENCES')
    and not pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_runs', 'TRIGGER')
    and pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_records', 'SELECT')
    and pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_records', 'INSERT')
    and pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_records', 'UPDATE')
    and not pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_records', 'DELETE')
    and not pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_records', 'TRUNCATE')
    and not pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_records', 'REFERENCES')
    and not pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_records', 'TRIGGER')
    and pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_versions', 'SELECT')
    and pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_versions', 'INSERT')
    and not pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_versions', 'UPDATE')
    and not pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_versions', 'DELETE')
    and not pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_versions', 'TRUNCATE')
    and not pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_versions', 'REFERENCES')
    and not pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_versions', 'TRIGGER')
    and pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_state', 'SELECT')
    and pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_state', 'UPDATE')
    and not pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_state', 'INSERT')
    and not pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_state', 'DELETE')
    and not pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_state', 'TRUNCATE')
    and not pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_state', 'REFERENCES')
    and not pg_catalog.has_table_privilege(service_oid, 'public.sfwmd_pending_erp_state', 'TRIGGER')
  ) then
    raise exception using errcode = '55000', message = 'SFWMD service_role table privilege matrix is not exact';
  end if;
  if exists (
    select 1
    from (
      values (anon_oid), (authenticated_oid)
    ) blocked_role(role_oid)
    cross join (
      values
        ('public.sfwmd_pending_erp_runs'),
        ('public.sfwmd_pending_erp_records'),
        ('public.sfwmd_pending_erp_versions'),
        ('public.sfwmd_pending_erp_state')
    ) protected_table(relation_name)
    cross join (
      values
        ('SELECT'), ('INSERT'), ('UPDATE'), ('DELETE'),
        ('TRUNCATE'), ('REFERENCES'), ('TRIGGER')
    ) table_privilege(privilege_name)
    where pg_catalog.has_table_privilege(
      blocked_role.role_oid,
      protected_table.relation_name,
      table_privilege.privilege_name
    )
  ) then
    raise exception using errcode = '55000', message = 'anonymous role has effective SFWMD table access';
  end if;
  if (
    select pg_catalog.count(*)
    from pg_catalog.pg_proc routine
    join pg_catalog.pg_namespace namespace on namespace.oid = routine.pronamespace
    where namespace.nspname = 'public'
      and (
        pg_catalog.left(pg_catalog.lower(routine.proname), 9) = 'fs_sfwmd_'
        or pg_catalog.lower(routine.proname) = 'fs_commit_sfwmd_pending_erp_run'
      )
  ) <> 3 then
    raise exception using errcode = '55000', message = 'SFWMD routine cardinality postflight failed';
  end if;
  if exists (
    select 1
    from pg_catalog.pg_proc routine
    join pg_catalog.pg_namespace namespace on namespace.oid = routine.pronamespace
    join pg_catalog.pg_language language on language.oid = routine.prolang
    where namespace.nspname = 'public'
      and routine.proname in (
        'fs_sfwmd_receipt_immutable',
        'fs_sfwmd_canonical_jsonb',
        'fs_commit_sfwmd_pending_erp_run'
      )
      and (
        routine.prokind <> 'f'
        or routine.prosecdef is not false
        or routine.proleakproof is not false
        or routine.proparallel <> 'u'
        or language.lanname <> 'plpgsql'
        or routine.proconfig is distinct from array['search_path=""']::text[]
        or not (
          (
            routine.proname = 'fs_sfwmd_receipt_immutable'
            and pg_catalog.oidvectortypes(routine.proargtypes) = ''
            and pg_catalog.format_type(routine.prorettype, null) = 'trigger'
            and routine.provolatile = 'v'
            and routine.proisstrict is false
          )
          or (
            routine.proname = 'fs_sfwmd_canonical_jsonb'
            and pg_catalog.oidvectortypes(routine.proargtypes) = 'jsonb'
            and pg_catalog.format_type(routine.prorettype, null) = 'text'
            and routine.provolatile = 'i'
            and routine.proisstrict is true
          )
          or (
            routine.proname = 'fs_commit_sfwmd_pending_erp_run'
            and pg_catalog.oidvectortypes(routine.proargtypes) = 'uuid, text, jsonb, jsonb'
            and pg_catalog.format_type(routine.prorettype, null) = 'jsonb'
            and routine.provolatile = 'v'
            and routine.proisstrict is false
          )
        )
      )
  ) then
    raise exception using errcode = '55000', message = 'SFWMD SECURITY INVOKER routine definition postflight failed';
  end if;
  if exists (
    select 1
    from pg_catalog.pg_proc routine
    join pg_catalog.pg_namespace namespace on namespace.oid = routine.pronamespace
    cross join lateral pg_catalog.aclexplode(
      coalesce(routine.proacl, pg_catalog.acldefault('f', routine.proowner))
    ) privilege
    where namespace.nspname = 'public'
      and routine.proname in (
        'fs_sfwmd_receipt_immutable',
        'fs_sfwmd_canonical_jsonb',
        'fs_commit_sfwmd_pending_erp_run'
      )
      and (
        privilege.grantee not in (routine.proowner, service_oid)
        or (
          routine.proname = 'fs_sfwmd_receipt_immutable'
          and privilege.grantee = service_oid
        )
      )
  ) then
    raise exception using errcode = '55000', message = 'SFWMD function ACL postflight found an arbitrary grantee';
  end if;
  if not (
    pg_catalog.has_schema_privilege(service_oid, 'public', 'USAGE')
    and pg_catalog.has_schema_privilege(service_oid, 'extensions', 'USAGE')
    and pg_catalog.has_function_privilege(
      service_oid,
      'extensions.digest(bytea,text)'::pg_catalog.regprocedure,
      'EXECUTE'
    )
    and pg_catalog.has_function_privilege(
      service_oid,
      'public.fs_sfwmd_canonical_jsonb(jsonb)'::pg_catalog.regprocedure,
      'EXECUTE'
    )
    and pg_catalog.has_function_privilege(
      service_oid,
      'public.fs_commit_sfwmd_pending_erp_run(uuid,text,jsonb,jsonb)'::pg_catalog.regprocedure,
      'EXECUTE'
    )
    and not pg_catalog.has_function_privilege(
      service_oid,
      'public.fs_sfwmd_receipt_immutable()'::pg_catalog.regprocedure,
      'EXECUTE'
    )
  ) then
    raise exception using errcode = '55000', message = 'SFWMD service_role function privilege matrix is not exact';
  end if;
  if exists (
    select 1
    from (
      values (anon_oid), (authenticated_oid)
    ) blocked_role(role_oid)
    cross join (
      values
        ('public.fs_sfwmd_receipt_immutable()'::pg_catalog.regprocedure),
        ('public.fs_sfwmd_canonical_jsonb(jsonb)'::pg_catalog.regprocedure),
        ('public.fs_commit_sfwmd_pending_erp_run(uuid,text,jsonb,jsonb)'::pg_catalog.regprocedure)
    ) protected_routine(routine_oid)
    where pg_catalog.has_function_privilege(
      blocked_role.role_oid,
      protected_routine.routine_oid,
      'EXECUTE'
    )
  ) then
    raise exception using errcode = '55000', message = 'anonymous role has effective SFWMD function access';
  end if;
  if pg_catalog.has_schema_privilege(anon_oid, 'public', 'CREATE')
     or pg_catalog.has_schema_privilege(authenticated_oid, 'public', 'CREATE') then
    raise exception using errcode = '55000', message = 'anonymous role can create objects in the SFWMD RPC schema';
  end if;
end
$$;

comment on function public.fs_commit_sfwmd_pending_erp_run(uuid,text,jsonb,jsonb) is
  'Private atomic/idempotent mirror of one already-durable canonical SFWMD run; never scores or publishes.';
