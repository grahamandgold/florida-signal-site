\set ON_ERROR_STOP on

-- Applying the schedule migration is intentionally inert until its owner-only
-- activation function is called.
select public.test_assert(
  (select count(*) = 0 from cron.job),
  'schedule migration must be default-off'
);
select public.test_assert(
  (select relrowsecurity and relforcerowsecurity
   from pg_class
   where oid = 'public.external_source_collector_dispatches'::regclass),
  'dispatch ledger must have forced RLS'
);
select public.test_assert(
  (select relrowsecurity and relforcerowsecurity
   from pg_class
   where oid = 'public.external_source_run_alerts'::regclass),
  'alert ledger must have forced RLS'
);
select public.test_assert(
  not has_function_privilege(
    'service_role', 'public.fs_dispatch_external_source(text,text)', 'execute'
  ),
  'service_role must not execute the owner-only dispatcher'
);
select public.test_assert(
  not has_sequence_privilege(
    'service_role',
    'public.external_source_collector_dispatches_id_seq',
    'usage'
  ) and not has_sequence_privilege(
    'service_role',
    'public.external_source_collector_dispatches_id_seq',
    'select'
  ),
  'read-only dispatch access must not grant service_role sequence privileges'
);
select public.test_assert(
  not has_sequence_privilege(
    'service_role',
    'public.external_source_run_alerts_id_seq',
    'usage'
  ) and not has_sequence_privilege(
    'service_role',
    'public.external_source_run_alerts_id_seq',
    'select'
  ),
  'read-only alert access must not grant service_role sequence privileges'
);
select public.test_assert(
  not has_function_privilege(
    'anon', 'public.fs_activate_external_source_schedules()', 'execute'
  ),
  'anon must not execute schedule activation'
);

-- Disable removes a legacy collector command without disturbing unrelated
-- jobs, then activation installs only the four reviewed schedules.
insert into cron.job (jobname, schedule, command) values
  ('unrelated-fixture', '5 5 * * *', 'select 1;'),
  ('legacy-fdep-fixture', '0 0 * * *',
   'select net.http_post(url := ''https://example.invalid/fdep-erp-sync'');');
select public.fs_disable_external_source_schedules();
select public.test_assert(
  exists (select 1 from cron.job where jobname = 'unrelated-fixture'),
  'disable must preserve unrelated cron jobs'
);
select public.test_assert(
  not exists (select 1 from cron.job where jobname = 'legacy-fdep-fixture'),
  'disable must remove a legacy collector command'
);

select public.fs_activate_external_source_schedules();
select public.test_assert(
  (
    select count(*) = 4
    from cron.job
    where (jobname, schedule, command) in (
      ('fdep-erp-daily', '20 9 * * *',
       'select public.fs_dispatch_external_source(''fdep_erp'');'),
      ('faa-oeaaa-daily', '40 9 * * *',
       'select public.fs_dispatch_external_source(''faa_oeaaa'');'),
      ('faa-oeaaa-retry', '10 10,11 * * *',
       'select public.fs_dispatch_external_source(''faa_oeaaa'');'),
      ('fl-signal-external-source-health', '0 12 * * *',
       'select public.fs_check_external_source_health();')
    )
  ),
  'activation must preserve the reviewed schedules and commands exactly'
);
select public.test_assert(
  not exists (
    select 1 from cron.job
    where command ilike '%http%'
       or command ilike '%vault%'
       or command ilike '%x-florida-signal-sync-key%'
       or command ilike '%fixture-only-key%'
  ),
  'cron commands must contain no URL or credential material'
);

-- Before a natural dispatcher fires, the watchdog records missing_dispatch.
select public.fs_check_external_source_health(now());
select public.test_assert(
  (
    select count(*) = 2
    from public.external_source_run_alerts
    where reason_code = 'missing_dispatch' and resolved_at is null
  ),
  'watchdog must distinguish a missing scheduled dispatch'
);

select public.fs_dispatch_external_source('fdep_erp');
select public.fs_dispatch_external_source('faa_oeaaa');
select public.test_assert(
  (
    select count(*) = 2
    from public.external_source_collector_dispatches
    where dispatch_kind = 'scheduled'
  ),
  'dispatch must durably record both scheduled requests'
);
select public.test_assert(
  not exists (
    select 1
    from public.external_source_collector_dispatches d
    join net.http_requests r on r.request_id = d.request_id
    where r.url is distinct from
      'https://fixture-project.supabase.co/functions/v1/'
      || case d.source_id
           when 'fdep_erp' then 'fdep-erp-sync'
           else 'faa-oeaaa-sync'
         end
      || '?dispatch_id=' || d.dispatch_id::text
       or r.headers ->> 'x-florida-signal-sync-key'
          is distinct from 'fixture-only-key-at-least-32-characters-long'
       or r.timeout_milliseconds <> 130000
  ),
  'dispatcher must correlate request UUIDs while keeping the key in headers'
);

-- A healthy receipt carrying a different UUID must not satisfy the natural
-- dispatch. This proves the watchdog does not accept an unrelated manual run.
insert into public.external_source_run_receipts (
  run_id, source_id, collector_name, collector_version, parser_version,
  normalizer_version, status, started_at, observed_at, completed_at,
  pages_attempted, pages_succeeded, responses_observed, rows_observed,
  rows_accepted, rows_inserted, rows_updated, rows_unchanged, rows_rejected,
  schema_contract_sha256, source_schema_sha256, raw_manifest_sha256,
  raw_manifest_object_key, source_metadata
) values (
  '77777777-7777-7777-7777-777777777777', 'fdep_erp', 'fixture', 'v1', 'v1',
  'v1', 'empty', now(), now(), now(), 0, 0, 0, 0, 0, 0, 0, 0, 0,
  repeat('a', 64), repeat('b', 64), repeat('c', 64),
  'fixture/unrelated-manifest.json',
  jsonb_build_object('dispatch_id', pg_catalog.gen_random_uuid()::text)
);
select public.fs_check_external_source_health(now() + interval '1 minute');
select public.test_assert(
  (
    select count(*) = 2
    from public.external_source_run_alerts
    where reason_code = 'missing_receipt' and resolved_at is null
  ),
  'watchdog must require the exact scheduled dispatch UUID'
);

-- Matching terminal receipts resolve both durable alerts.
insert into public.external_source_run_receipts (
  run_id, source_id, collector_name, collector_version, parser_version,
  normalizer_version, status, started_at, observed_at, completed_at,
  pages_attempted, pages_succeeded, responses_observed, rows_observed,
  rows_accepted, rows_inserted, rows_updated, rows_unchanged, rows_rejected,
  schema_contract_sha256, source_schema_sha256, raw_manifest_sha256,
  raw_manifest_object_key, source_metadata
)
select
  case source_id
    when 'fdep_erp' then '88888888-8888-8888-8888-888888888888'::uuid
    else '99999999-9999-9999-9999-999999999999'::uuid
  end,
  source_id, 'fixture', 'v1', 'v1', 'v1', 'empty',
  dispatched_at + interval '1 second',
  dispatched_at + interval '2 seconds',
  dispatched_at + interval '3 seconds',
  0, 0, 0, 0, 0, 0, 0, 0, 0,
  repeat('d', 64), repeat('e', 64), repeat('f', 64),
  'fixture/' || source_id || '-manifest.json',
  jsonb_build_object('dispatch_id', dispatch_id::text)
from public.external_source_collector_dispatches;
select public.fs_check_external_source_health(now() + interval '5 minutes');
select public.test_assert(
  (
    select count(*) = 2
    from public.external_source_run_alerts
    where resolved_at is not null
  ),
  'matching healthy receipts must resolve both durable alerts'
);

select public.fs_disable_external_source_schedules();
select public.test_assert(
  not exists (
    select 1 from cron.job
    where jobname in (
      'fdep-erp-daily', 'faa-oeaaa-daily', 'faa-oeaaa-retry',
      'fl-signal-external-source-health'
    )
  ),
  'rollback must remove all four tracked schedules'
);
select public.test_assert(
  exists (select 1 from cron.job where jobname = 'unrelated-fixture'),
  'rollback must still preserve unrelated cron jobs'
);

select 'external_source_schedule_assertions_passed' as result;
