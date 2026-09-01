-- Secret-safe FDEP/FAA collector scheduling and durable source-health alerts.
-- Reordered after the live 20260901052118 PDMR event-ledger migration.
--
-- Applying this migration creates only private schedule infrastructure. It
-- does not alter cron.job. The owner-only activation function is invoked only
-- after the atomic migration, secret installation, reviewed Edge deployments
-- and one-source-at-a-time canaries are complete. The owner-only disable
-- function is the exact pre-deployment and rollback boundary.
--
-- No secret value, project URL or retired query credential is stored here or
-- in cron.job.command. Missing prerequisites abort this migration before any
-- existing FDEP/FAA job is unscheduled merely by applying the migration.

create table if not exists public.external_source_collector_dispatches (
  id bigint generated always as identity primary key,
  dispatch_id uuid not null unique default pg_catalog.gen_random_uuid(),
  source_id text not null check (source_id in ('fdep_erp', 'faa_oeaaa')),
  request_id bigint not null unique,
  dispatched_at timestamptz not null default now(),
  dispatch_kind text not null default 'scheduled'
    check (dispatch_kind in ('scheduled', 'manual_canary'))
);

create index if not exists external_source_collector_dispatch_source_time_idx
  on public.external_source_collector_dispatches (source_id, dispatched_at desc);

alter table public.external_source_collector_dispatches enable row level security;
alter table public.external_source_collector_dispatches force row level security;
revoke all on table public.external_source_collector_dispatches
  from public, anon, authenticated, service_role;
grant select on table public.external_source_collector_dispatches to service_role;
revoke all on sequence public.external_source_collector_dispatches_id_seq
  from public, anon, authenticated, service_role;

create table if not exists public.external_source_run_alerts (
  id bigint generated always as identity primary key,
  source_id text not null check (source_id in ('fdep_erp', 'faa_oeaaa')),
  alert_date date not null,
  reason_code text not null check (
    reason_code in (
      'missing_dispatch', 'missing_receipt', 'terminal_source_wait',
      'terminal_partial', 'terminal_failed'
    )
  ),
  receipt_run_id uuid,
  receipt_status text,
  checked_at timestamptz not null,
  details jsonb not null default '{}'::jsonb
    check (jsonb_typeof(details) = 'object'),
  created_at timestamptz not null default now(),
  resolved_at timestamptz,
  unique (source_id, alert_date)
);

create index if not exists external_source_run_alerts_open_idx
  on public.external_source_run_alerts (source_id, checked_at desc)
  where resolved_at is null;

alter table public.external_source_run_alerts enable row level security;
alter table public.external_source_run_alerts force row level security;
revoke all on table public.external_source_run_alerts
  from public, anon, authenticated, service_role;
grant select on table public.external_source_run_alerts to service_role;
revoke all on sequence public.external_source_run_alerts_id_seq
  from public, anon, authenticated, service_role;

create or replace function public.fs_dispatch_external_source(
  p_source_id text,
  p_dispatch_kind text default 'scheduled'
)
returns bigint
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_base_url text;
  v_sync_key text;
  v_slug text;
  v_dispatch_id uuid := pg_catalog.gen_random_uuid();
  v_request_id bigint;
begin
  if p_source_id = 'fdep_erp' then
    v_slug := 'fdep-erp-sync';
  elsif p_source_id = 'faa_oeaaa' then
    v_slug := 'faa-oeaaa-sync';
  else
    raise exception using errcode = '22023', message = 'unsupported external source';
  end if;
  if p_dispatch_kind not in ('scheduled', 'manual_canary') then
    raise exception using errcode = '22023', message = 'unsupported dispatch kind';
  end if;

  select decrypted_secret into strict v_base_url
  from vault.decrypted_secrets
  where name = 'fl_signal_functions_base_url';
  select decrypted_secret into strict v_sync_key
  from vault.decrypted_secrets
  where name = 'fl_signal_external_source_sync_key';

  if v_base_url !~ '^https://[a-z0-9-]+[.]supabase[.]co/functions/v1/?$'
     or position('?' in v_base_url) <> 0
     or pg_catalog.length(v_sync_key) < 32
     or v_sync_key = '__FL_SIGNAL_SYNC_KEY_INJECT_AT_DEPLOY__' then
    raise exception using errcode = '22023', message = 'collector dispatch Vault configuration is invalid';
  end if;

  select net.http_post(
    url := pg_catalog.rtrim(v_base_url, '/') || '/' || v_slug
      || '?dispatch_id=' || v_dispatch_id::text,
    headers := pg_catalog.jsonb_build_object(
      'Content-Type', 'application/json',
      'x-florida-signal-sync-key', v_sync_key
    ),
    body := '{}'::jsonb,
    timeout_milliseconds := 130000
  ) into v_request_id;

  insert into public.external_source_collector_dispatches (
    dispatch_id, source_id, request_id, dispatch_kind
  ) values (
    v_dispatch_id, p_source_id, v_request_id, p_dispatch_kind
  );
  return v_request_id;
end
$$;

comment on function public.fs_dispatch_external_source(text, text) is
  'Owner-only pg_net dispatcher. Resolves secret values from Vault at execution time; cron stores no URL or credential.';

revoke all on function public.fs_dispatch_external_source(text, text)
  from public, anon, authenticated, service_role;

create or replace function public.fs_check_external_source_health(
  p_checked_at timestamptz default now()
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_source_id text;
  v_day date := (p_checked_at at time zone 'UTC')::date;
  v_day_start timestamptz := (
    ((p_checked_at at time zone 'UTC')::date)::timestamp at time zone 'UTC'
  );
  v_dispatch_id uuid;
  v_request_id bigint;
  v_dispatched_at timestamptz;
  v_run_id uuid;
  v_status text;
  v_completed_at timestamptz;
  v_reason text;
  v_open_alerts integer;
begin
  foreach v_source_id in array array['fdep_erp', 'faa_oeaaa'] loop
    v_run_id := null;
    v_status := null;
    v_completed_at := null;
    v_dispatch_id := null;
    v_request_id := null;
    v_dispatched_at := null;

    select dispatch_id, request_id, dispatched_at
      into v_dispatch_id, v_request_id, v_dispatched_at
    from public.external_source_collector_dispatches
    where source_id = v_source_id
      and dispatch_kind = 'scheduled'
      and dispatched_at >= v_day_start
      and dispatched_at <= p_checked_at
    order by dispatched_at desc, id desc
    limit 1;

    if v_dispatch_id is null then
      v_reason := 'missing_dispatch';
    else
      select run_id, status, completed_at
        into v_run_id, v_status, v_completed_at
      from public.external_source_run_receipts
      where source_id = v_source_id
        and source_metadata ->> 'dispatch_id' = v_dispatch_id::text
        and started_at >= v_dispatched_at
        and completed_at >= v_dispatched_at
        and completed_at <= p_checked_at
      order by completed_at desc, id desc
      limit 1;

      if v_run_id is null then
        v_reason := 'missing_receipt';
      elsif v_status in ('ok', 'empty') then
        update public.external_source_run_alerts
        set resolved_at = p_checked_at,
            checked_at = p_checked_at,
            details = details || pg_catalog.jsonb_build_object(
              'resolved_by_dispatch_id', v_dispatch_id,
              'resolved_by_run_id', v_run_id,
              'resolved_by_status', v_status
            )
        where source_id = v_source_id and resolved_at is null;
        continue;
      else
        v_reason := 'terminal_' || v_status;
      end if;
    end if;

    insert into public.external_source_run_alerts (
      source_id, alert_date, reason_code, receipt_run_id, receipt_status,
      checked_at, details, resolved_at
    ) values (
      v_source_id, v_day, v_reason, v_run_id, v_status, p_checked_at,
      pg_catalog.jsonb_build_object(
        'day_start_utc', v_day_start,
        'dispatch_id', v_dispatch_id,
        'dispatch_request_id', v_request_id,
        'dispatched_at', v_dispatched_at,
        'latest_completed_at', v_completed_at
      ),
      null
    )
    on conflict (source_id, alert_date) do update set
      reason_code = excluded.reason_code,
      receipt_run_id = excluded.receipt_run_id,
      receipt_status = excluded.receipt_status,
      checked_at = excluded.checked_at,
      details = excluded.details,
      resolved_at = null;
  end loop;

  select count(*) into v_open_alerts
  from public.external_source_run_alerts
  where resolved_at is null;
  return pg_catalog.jsonb_build_object(
    'checked_at', p_checked_at,
    'open_alerts', v_open_alerts
  );
end
$$;

comment on function public.fs_check_external_source_health(timestamptz) is
  'Owner-only daily watchdog. Requires exact scheduled-dispatch UUID correlation, opens a durable alert for missing or attention-state evidence, and resolves prior alerts after a healthy matching receipt.';

revoke all on function public.fs_check_external_source_health(timestamptz)
  from public, anon, authenticated, service_role;

create or replace function public.fs_disable_external_source_schedules()
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_job record;
  v_removed integer := 0;
begin
  if pg_catalog.to_regnamespace('cron') is null then
    raise exception using errcode = '55000', message = 'pg_cron is unavailable';
  end if;
  for v_job in
    select jobid
    from cron.job
    where jobname in (
      'fdep-erp-daily', 'faa-oeaaa-daily', 'faa-oeaaa-retry',
      'fl-signal-external-source-health'
    )
       or command ilike '%fdep-erp-sync%'
       or command ilike '%faa-oeaaa-sync%'
  loop
    perform cron.unschedule(v_job.jobid);
    v_removed := v_removed + 1;
  end loop;
  return pg_catalog.jsonb_build_object('disabled_jobs', v_removed);
end
$$;

comment on function public.fs_disable_external_source_schedules() is
  'Owner-only pre-deployment and rollback boundary. Removes tracked and legacy FDEP/FAA jobs without touching unrelated cron jobs.';

revoke all on function public.fs_disable_external_source_schedules()
  from public, anon, authenticated, service_role;

create or replace function public.fs_activate_external_source_schedules()
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_base_url text;
  v_sync_key text;
  v_job record;
begin
  if pg_catalog.to_regnamespace('cron') is null
     or pg_catalog.to_regnamespace('net') is null
     or pg_catalog.to_regnamespace('vault') is null
     or pg_catalog.to_regprocedure('cron.schedule(text,text,text)') is null
     or pg_catalog.to_regprocedure('cron.unschedule(bigint)') is null
     or pg_catalog.to_regprocedure(
       'net.http_post(text,jsonb,jsonb,jsonb,integer)'
     ) is null
     or pg_catalog.to_regclass('vault.decrypted_secrets') is null then
    raise exception using
      errcode = '55000',
      message = 'exact pg_cron, pg_net and Vault contracts must exist before collector scheduling';
  end if;
  if pg_catalog.to_regprocedure(
    'public.fs_commit_external_source_run(text,uuid,jsonb,jsonb)'
  ) is null then
    raise exception using
      errcode = '55000',
      message = 'atomic external-source commit RPC is not installed';
  end if;

  select decrypted_secret into strict v_base_url
  from vault.decrypted_secrets
  where name = 'fl_signal_functions_base_url';
  select decrypted_secret into strict v_sync_key
  from vault.decrypted_secrets
  where name = 'fl_signal_external_source_sync_key';
  if v_base_url !~ '^https://[a-z0-9-]+[.]supabase[.]co/functions/v1/?$'
     or position('?' in v_base_url) <> 0
     or pg_catalog.length(v_sync_key) < 32
     or v_sync_key = '__FL_SIGNAL_SYNC_KEY_INJECT_AT_DEPLOY__' then
    raise exception using errcode = '22023', message = 'collector scheduling Vault configuration is invalid';
  end if;

  -- Repeat the disable loop inside this transaction so activation is
  -- idempotent and cannot leave a legacy query-key job alongside a new job.
  for v_job in
    select jobid
    from cron.job
    where jobname in (
      'fdep-erp-daily', 'faa-oeaaa-daily', 'faa-oeaaa-retry',
      'fl-signal-external-source-health'
    )
       or command ilike '%fdep-erp-sync%'
       or command ilike '%faa-oeaaa-sync%'
  loop
    perform cron.unschedule(v_job.jobid);
  end loop;

  perform cron.schedule(
    'fdep-erp-daily',
    '20 9 * * *',
    $job$select public.fs_dispatch_external_source('fdep_erp');$job$
  );
  perform cron.schedule(
    'faa-oeaaa-daily',
    '40 9 * * *',
    $job$select public.fs_dispatch_external_source('faa_oeaaa');$job$
  );
  perform cron.schedule(
    'faa-oeaaa-retry',
    '10 10,11 * * *',
    $job$select public.fs_dispatch_external_source('faa_oeaaa');$job$
  );
  perform cron.schedule(
    'fl-signal-external-source-health',
    '0 12 * * *',
    $job$select public.fs_check_external_source_health();$job$
  );

  if (
    select count(*)
    from cron.job
    where (jobname, schedule) in (
      ('fdep-erp-daily', '20 9 * * *'),
      ('faa-oeaaa-daily', '40 9 * * *'),
      ('faa-oeaaa-retry', '10 10,11 * * *'),
      ('fl-signal-external-source-health', '0 12 * * *')
    )
  ) <> 4 then
    raise exception using errcode = '55000', message = 'collector schedule verification failed';
  end if;
  if exists (
    select 1
    from cron.job
    where jobname in ('fdep-erp-daily', 'faa-oeaaa-daily', 'faa-oeaaa-retry')
      and (
        command ilike '%http%'
        or command ilike '%vault%'
        or command ilike '%key=%'
        or command ilike '%x-florida-signal-sync-key%'
      )
  ) then
    raise exception using errcode = '23514', message = 'cron command contains a URL or credential reference';
  end if;
  return pg_catalog.jsonb_build_object(
    'activated', true,
    'fdep_schedule', '20 9 * * *',
    'faa_primary_schedule', '40 9 * * *',
    'faa_retry_schedule', '10 10,11 * * *',
    'health_schedule', '0 12 * * *'
  );
end
$$;

comment on function public.fs_activate_external_source_schedules() is
  'Owner-only fail-closed schedule activation after deploy/canary approval. Cron commands call owner-only dispatchers and contain no URL or credential.';

revoke all on function public.fs_activate_external_source_schedules()
  from public, anon, authenticated, service_role;

-- Default-off proof: applying this migration itself must not create or alter
-- a cron job. Only an explicit owner call to fs_disable... or fs_activate...
-- changes the existing schedule state.
