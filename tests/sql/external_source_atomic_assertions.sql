\set ON_ERROR_STOP on

select public.test_assert(
  (select relrowsecurity and relforcerowsecurity
   from pg_class where oid = 'public.external_source_run_stage'::regclass),
  'stage must have forced RLS'
);
select public.test_assert(
  has_function_privilege(
    'service_role',
    'public.fs_commit_external_source_run(text,uuid,jsonb,jsonb)',
    'execute'
  ),
  'service_role must execute the atomic RPC'
);
select public.test_assert(
  not has_function_privilege(
    'anon',
    'public.fs_commit_external_source_run(text,uuid,jsonb,jsonb)',
    'execute'
  ),
  'anon must not execute the atomic RPC'
);

create temp table atomic_test_payloads (
  source_id text not null,
  run_id uuid primary key,
  receipt jsonb not null,
  manifest jsonb not null
);
grant select on atomic_test_payloads to service_role;

insert into storage.objects (bucket_id, name) values
  ('fl-signal-source-evidence', 'faa_oeaaa/11111111-1111-1111-1111-111111111111/oe-2026.xml'),
  ('fl-signal-source-evidence', 'faa_oeaaa/11111111-1111-1111-1111-111111111111/manifest.json');

insert into atomic_test_payloads values (
  'faa_oeaaa',
  '11111111-1111-1111-1111-111111111111',
  jsonb_build_object(
    'collector_name', 'faa-oeaaa-sync',
    'collector_version', 'fixture-v1',
    'parser_version', 'fixture-parser-v1',
    'normalizer_version', 'fixture-normalizer-v1',
    'status', 'ok',
    'reason_code', null,
    'reason_detail', null,
    'started_at', '2026-09-01T00:00:00.000Z',
    'observed_at', '2026-09-01T00:00:01.000Z',
    'completed_at', '2026-09-01T00:00:02.000Z',
    'attempted_event_from', '2026-08-31T00:00:00.000Z',
    'attempted_event_through', '2026-08-31T23:59:59.999Z',
    'event_through', '2026-08-31T12:00:00.000Z',
    'pages_attempted', 1,
    'pages_succeeded', 1,
    'responses_observed', 1,
    'rows_observed', 1,
    'rows_rejected', 0,
    'schema_contract_sha256', repeat('a', 64),
    'source_schema_sha256', repeat('b', 64),
    'raw_manifest_object_key', 'faa_oeaaa/11111111-1111-1111-1111-111111111111/manifest.json',
    'outcomes', '[]'::jsonb,
    'source_metadata', jsonb_build_object('fixture', true)
  ),
  jsonb_build_object(
    'manifest_version', 1,
    'source_id', 'faa_oeaaa',
    'run_id', '11111111-1111-1111-1111-111111111111',
    'started_at', '2026-09-01T00:00:00.000Z',
    'observed_at', '2026-09-01T00:00:01.000Z',
    'completed_at', '2026-09-01T00:00:02.000Z',
    'raw_objects', jsonb_build_array(jsonb_build_object(
      'key', 'faa_oeaaa/11111111-1111-1111-1111-111111111111/oe-2026.xml',
      'sha256', repeat('c', 64),
      'bytes', 100
    )),
    'pages_attempted', 1,
    'pages_succeeded', 1,
    'responses_observed', 1,
    'rows_observed', 1,
    'rows_staged', 1,
    'rows_rejected', 0,
    'outcomes', '[]'::jsonb
  )
);

update atomic_test_payloads
set manifest = manifest || jsonb_build_object('terminal_receipt', receipt)
where run_id = '11111111-1111-1111-1111-111111111111';

set role service_role;
insert into public.external_source_run_stage (source_id, run_id, row_key, row_data)
values (
  'faa_oeaaa',
  '11111111-1111-1111-1111-111111111111',
  '2026-ASO-1-OE',
  jsonb_build_object(
    'asn', '2026-ASO-1-OE', 'case_id', 1, 'case_type', 'OE', 'year', 2026,
    'date_entered', '2026-08-31', 'date_completed', null,
    'expiration_date', null, 'received_date', '2026-08-31T12:00:00Z',
    'status_code', 'WRK-Part77', 'structure_type', 'CRANE',
    'structure_description', 'Fixture', 'agl_height', 100,
    'agl_height_det', null, 'amsl_height', 120, 'sponsor', 'Fixture',
    'sponsor_city', 'Fort Lauderdale', 'sponsor_state', 'FL',
    'nearest_airport', 'FLL', 'nearest_city', 'Fort Lauderdale',
    'nearest_state', 'FL', 'lat', 26.12, 'lon', -80.14, 'raw', '{}'::jsonb
  )
);

select public.fs_commit_external_source_run(
  source_id, run_id, receipt, manifest
)
from atomic_test_payloads
where run_id = '11111111-1111-1111-1111-111111111111';

select public.test_assert(
  (select in_broward from public.faa_oeaaa where asn = '2026-ASO-1-OE'),
  'PostgreSQL must compute generated in_broward'
);
select public.test_assert(
  not exists (
    select 1 from public.external_source_run_stage
    where run_id = '11111111-1111-1111-1111-111111111111'
  ),
  'successful commit must clear stage'
);
select public.test_assert(
  (select rows_inserted = 1 and rows_updated = 0 and rows_unchanged = 0
   from public.external_source_run_receipts
   where run_id = '11111111-1111-1111-1111-111111111111'),
  'receipt must contain database-derived insert accounting'
);
select public.test_assert(
  (
    select (public.fs_commit_external_source_run(
      source_id, run_id, receipt, manifest
    ) ->> 'idempotent_replay')::boolean
    from atomic_test_payloads
    where run_id = '11111111-1111-1111-1111-111111111111'
  ),
  'exact replay must be idempotent'
);
reset role;

-- A receipt constraint failure occurs after the source upsert in function
-- order; the function statement must roll back the source write and retain the
-- pre-existing stage row for deterministic recovery.
insert into storage.objects (bucket_id, name) values
  ('fl-signal-source-evidence', 'faa_oeaaa/22222222-2222-2222-2222-222222222222/oe-2026.xml'),
  ('fl-signal-source-evidence', 'faa_oeaaa/22222222-2222-2222-2222-222222222222/manifest.json');
insert into atomic_test_payloads
select
  source_id,
  '22222222-2222-2222-2222-222222222222'::uuid,
  jsonb_set(
    jsonb_set(
      jsonb_set(receipt, '{raw_manifest_object_key}',
        to_jsonb('faa_oeaaa/22222222-2222-2222-2222-222222222222/manifest.json'::text)),
      '{schema_contract_sha256}', to_jsonb('invalid'::text)
    ),
    '{started_at}', to_jsonb('2026-09-01T00:01:00.000Z'::text)
  ) || jsonb_build_object(
    'observed_at', '2026-09-01T00:01:01.000Z',
    'completed_at', '2026-09-01T00:01:02.000Z'
  ),
  jsonb_set(
    jsonb_set(
      jsonb_set(manifest, '{run_id}', to_jsonb('22222222-2222-2222-2222-222222222222'::text)),
      '{raw_objects,0,key}', to_jsonb('faa_oeaaa/22222222-2222-2222-2222-222222222222/oe-2026.xml'::text)
    ),
    '{started_at}', to_jsonb('2026-09-01T00:01:00.000Z'::text)
  ) || jsonb_build_object(
    'observed_at', '2026-09-01T00:01:01.000Z',
    'completed_at', '2026-09-01T00:01:02.000Z'
  )
from atomic_test_payloads
where run_id = '11111111-1111-1111-1111-111111111111';

update atomic_test_payloads
set manifest = manifest || jsonb_build_object('terminal_receipt', receipt)
where run_id = '22222222-2222-2222-2222-222222222222';

set role service_role;
insert into public.external_source_run_stage (source_id, run_id, row_key, row_data)
values (
  'faa_oeaaa', '22222222-2222-2222-2222-222222222222', '2026-ASO-2-OE',
  jsonb_build_object(
    'asn', '2026-ASO-2-OE', 'case_id', 2, 'case_type', 'OE', 'year', 2026,
    'date_entered', '2026-08-31', 'date_completed', null,
    'expiration_date', null, 'received_date', '2026-08-31T12:01:00Z',
    'status_code', 'WRK-Part77', 'structure_type', 'CRANE',
    'structure_description', 'Rollback fixture', 'agl_height', 100,
    'agl_height_det', null, 'amsl_height', 120, 'sponsor', 'Fixture',
    'sponsor_city', 'Fort Lauderdale', 'sponsor_state', 'FL',
    'nearest_airport', 'FLL', 'nearest_city', 'Fort Lauderdale',
    'nearest_state', 'FL', 'lat', 26.12, 'lon', -80.14, 'raw', '{}'::jsonb
  )
);
do $$
begin
  perform public.fs_commit_external_source_run(
    source_id, run_id, receipt, manifest
  )
  from atomic_test_payloads
  where run_id = '22222222-2222-2222-2222-222222222222';
  raise exception 'expected receipt hash constraint failure';
exception
  when check_violation then null;
end
$$;
select public.test_assert(
  not exists (select 1 from public.faa_oeaaa where asn = '2026-ASO-2-OE'),
  'receipt failure must roll back source upsert'
);
select public.test_assert(
  exists (
    select 1 from public.external_source_run_stage
    where run_id = '22222222-2222-2222-2222-222222222222'
  ),
  'receipt failure must retain pre-existing stage for recovery'
);
select public.test_assert(
  not exists (
    select 1 from public.external_source_run_receipts
    where run_id = '22222222-2222-2222-2222-222222222222'
  ),
  'receipt failure must not leave a terminal row'
);
reset role;

-- Generated columns are never caller-owned: staging one must fail before any
-- source write.
insert into storage.objects (bucket_id, name) values
  ('fl-signal-source-evidence', 'faa_oeaaa/33333333-3333-3333-3333-333333333333/manifest.json');
set role service_role;
insert into public.external_source_run_stage (source_id, run_id, row_key, row_data)
values (
  'faa_oeaaa', '33333333-3333-3333-3333-333333333333', '2026-ASO-3-OE',
  jsonb_build_object('asn', '2026-ASO-3-OE', 'in_broward', false)
);
do $$
declare
  v_receipt jsonb := jsonb_build_object(
    'collector_name', 'faa-oeaaa-sync', 'collector_version', 'fixture-v1',
    'parser_version', 'fixture-v1', 'normalizer_version', 'fixture-v1',
    'status', 'ok', 'started_at', '2026-09-01T00:02:00.000Z',
    'observed_at', '2026-09-01T00:02:01.000Z',
    'completed_at', '2026-09-01T00:02:02.000Z',
    'pages_attempted', 0, 'pages_succeeded', 0, 'responses_observed', 0,
    'rows_observed', 1, 'rows_rejected', 0,
    'schema_contract_sha256', repeat('a', 64),
    'source_schema_sha256', repeat('b', 64),
    'raw_manifest_object_key', 'faa_oeaaa/33333333-3333-3333-3333-333333333333/manifest.json'
  );
  v_manifest jsonb := jsonb_build_object(
    'manifest_version', 1, 'source_id', 'faa_oeaaa',
    'run_id', '33333333-3333-3333-3333-333333333333',
    'started_at', '2026-09-01T00:02:00.000Z',
    'observed_at', '2026-09-01T00:02:01.000Z',
    'completed_at', '2026-09-01T00:02:02.000Z',
    'raw_objects', '[]'::jsonb, 'pages_attempted', 0,
    'pages_succeeded', 0, 'responses_observed', 0,
    'rows_observed', 1, 'rows_staged', 1, 'rows_rejected', 0,
    'outcomes', '[]'::jsonb
  );
begin
  v_manifest := v_manifest || jsonb_build_object('terminal_receipt', v_receipt);
  perform public.fs_commit_external_source_run(
    'faa_oeaaa',
    '33333333-3333-3333-3333-333333333333',
    v_receipt,
    v_manifest
  );
  raise exception 'expected generated-column contract rejection';
exception
  when check_violation then null;
end
$$;
select public.test_assert(
  not exists (select 1 from public.faa_oeaaa where asn = '2026-ASO-3-OE'),
  'generated-column injection must not write a source row'
);
reset role;

-- A failed terminal state discards a staged prefix and writes no source row.
insert into storage.objects (bucket_id, name) values
  ('fl-signal-source-evidence', 'faa_oeaaa/44444444-4444-4444-4444-444444444444/failure-manifest.json');
set role service_role;
insert into public.external_source_run_stage (source_id, run_id, row_key, row_data)
values (
  'faa_oeaaa', '44444444-4444-4444-4444-444444444444', 'discard-me',
  jsonb_build_object('asn', 'discard-me')
);
with payload as (
  select jsonb_build_object(
    'collector_name', 'faa-oeaaa-sync', 'collector_version', 'fixture-v1',
    'parser_version', 'fixture-v1', 'normalizer_version', 'fixture-v1',
    'status', 'failed', 'reason_code', 'collector_exception',
    'reason_detail', 'fixture failure',
    'started_at', '2026-09-01T00:03:00.000Z',
    'observed_at', '2026-09-01T00:03:01.000Z',
    'completed_at', '2026-09-01T00:03:02.000Z',
    'pages_attempted', 0, 'pages_succeeded', 0, 'responses_observed', 0,
    'rows_observed', 1, 'rows_rejected', 1,
    'schema_contract_sha256', repeat('a', 64),
    'source_schema_sha256', null,
    'raw_manifest_object_key', 'faa_oeaaa/44444444-4444-4444-4444-444444444444/failure-manifest.json'
  ) as receipt,
  jsonb_build_object(
    'manifest_version', 1, 'source_id', 'faa_oeaaa',
    'run_id', '44444444-4444-4444-4444-444444444444',
    'started_at', '2026-09-01T00:03:00.000Z',
    'observed_at', '2026-09-01T00:03:01.000Z',
    'completed_at', '2026-09-01T00:03:02.000Z',
    'raw_objects', '[]'::jsonb, 'pages_attempted', 0,
    'pages_succeeded', 0, 'responses_observed', 0,
    'rows_observed', 1, 'outcomes', '[]'::jsonb
  ) as manifest
)
select public.fs_commit_external_source_run(
  'faa_oeaaa',
  '44444444-4444-4444-4444-444444444444',
  receipt,
  manifest || jsonb_build_object('terminal_receipt', receipt)
)
from payload;
select public.test_assert(
  not exists (
    select 1 from public.external_source_run_stage
    where run_id = '44444444-4444-4444-4444-444444444444'
  ),
  'failed terminal commit must discard staged prefix'
);
select public.test_assert(
  (select status = 'failed' and rows_inserted = 0 and rows_updated = 0
   from public.external_source_run_receipts
   where run_id = '44444444-4444-4444-4444-444444444444'),
  'failed terminal receipt must record zero source writes'
);
reset role;

-- Exercise the distinct FDEP DML branch, including exact replay.
insert into storage.objects (bucket_id, name) values
  ('fl-signal-source-evidence', 'fdep_erp/55555555-5555-5555-5555-555555555555/layer-0-page-0.json'),
  ('fl-signal-source-evidence', 'fdep_erp/55555555-5555-5555-5555-555555555555/manifest.json');
insert into atomic_test_payloads values (
  'fdep_erp',
  '55555555-5555-5555-5555-555555555555',
  jsonb_build_object(
    'collector_name', 'fdep-erp-sync',
    'collector_version', 'fixture-v1',
    'parser_version', 'fixture-parser-v1',
    'normalizer_version', 'fixture-normalizer-v1',
    'status', 'ok',
    'reason_code', null,
    'reason_detail', null,
    'started_at', '2026-09-01T01:00:00.000Z',
    'observed_at', '2026-09-01T01:00:01.000Z',
    'completed_at', '2026-09-01T01:00:02.000Z',
    'attempted_event_from', '2026-08-31T00:00:00.000Z',
    'attempted_event_through', '2026-08-31T23:59:59.999Z',
    'event_through', '2026-08-31T13:00:00.000Z',
    'pages_attempted', 1,
    'pages_succeeded', 1,
    'responses_observed', 1,
    'rows_observed', 1,
    'rows_rejected', 0,
    'schema_contract_sha256', repeat('d', 64),
    'source_schema_sha256', repeat('e', 64),
    'raw_manifest_object_key',
      'fdep_erp/55555555-5555-5555-5555-555555555555/manifest.json',
    'outcomes', '[]'::jsonb,
    'source_metadata', jsonb_build_object('fixture', true)
  ),
  jsonb_build_object(
    'manifest_version', 1,
    'source_id', 'fdep_erp',
    'run_id', '55555555-5555-5555-5555-555555555555',
    'started_at', '2026-09-01T01:00:00.000Z',
    'observed_at', '2026-09-01T01:00:01.000Z',
    'completed_at', '2026-09-01T01:00:02.000Z',
    'raw_objects', jsonb_build_array(jsonb_build_object(
      'key', 'fdep_erp/55555555-5555-5555-5555-555555555555/layer-0-page-0.json',
      'sha256', repeat('f', 64),
      'bytes', 100
    )),
    'pages_attempted', 1,
    'pages_succeeded', 1,
    'responses_observed', 1,
    'rows_observed', 1,
    'rows_staged', 1,
    'rows_rejected', 0,
    'outcomes', '[]'::jsonb
  )
);
update atomic_test_payloads
set manifest = manifest || jsonb_build_object('terminal_receipt', receipt)
where run_id = '55555555-5555-5555-5555-555555555555';

set role service_role;
insert into public.external_source_run_stage (source_id, run_id, row_key, row_data)
values (
  'fdep_erp', '55555555-5555-5555-5555-555555555555', '0:5001',
  jsonb_build_object(
    'layer_id', 0, 'objectid', 5001, 'permit_id', 'ERP-FIXTURE-5001',
    'application_id', 'APP-5001', 'project_id', 5001,
    'project_name', 'FDEP fixture', 'applicant_name', 'Fixture Applicant',
    'applicant_company', 'Fixture LLC', 'permit_type', 'ERP',
    'permit_status', 'ACTIVE', 'defined_status', 'IN REVIEW',
    'division', 'Water Resource Management',
    'permitting_program', 'Environmental Resource Permitting',
    'district', 'Southeast', 'office_abbrev', 'SED',
    'location_id', 'LOC-5001', 'location_name', 'Fixture site',
    'street_address', '5001 Test Ave', 'city', 'Fort Lauderdale',
    'state', 'FL', 'zip5', '33301', 'zip4', null,
    'received_date', '2026-08-31', 'agency_action', null,
    'agency_action_date', null, 'documents_url', 'https://example.invalid/5001',
    'lat', 26.12, 'lon', -80.14, 'raw', '{}'::jsonb
  )
);
select public.fs_commit_external_source_run(source_id, run_id, receipt, manifest)
from atomic_test_payloads
where run_id = '55555555-5555-5555-5555-555555555555';
select public.test_assert(
  exists (
    select 1 from public.fdep_erp
    where layer_id = 0 and objectid = 5001 and permit_id = 'ERP-FIXTURE-5001'
  ),
  'FDEP commit must write the normalized source row'
);
select public.test_assert(
  (
    select (public.fs_commit_external_source_run(
      source_id, run_id, receipt, manifest
    ) ->> 'idempotent_replay')::boolean
    from atomic_test_payloads
    where run_id = '55555555-5555-5555-5555-555555555555'
  ),
  'FDEP exact replay must be idempotent'
);
select public.test_assert(
  (select rows_inserted = 1 and rows_updated = 0 and rows_unchanged = 0
   from public.external_source_run_receipts
   where run_id = '55555555-5555-5555-5555-555555555555'),
  'FDEP receipt must contain database-derived insert accounting'
);
reset role;

-- Force a terminal receipt constraint failure after the FDEP source upsert;
-- the transaction must roll back that distinct source branch as well.
insert into storage.objects (bucket_id, name) values
  ('fl-signal-source-evidence', 'fdep_erp/66666666-6666-6666-6666-666666666666/layer-0-page-0.json'),
  ('fl-signal-source-evidence', 'fdep_erp/66666666-6666-6666-6666-666666666666/manifest.json');
insert into atomic_test_payloads
select
  source_id,
  '66666666-6666-6666-6666-666666666666'::uuid,
  jsonb_set(
    jsonb_set(
      jsonb_set(receipt, '{raw_manifest_object_key}',
        to_jsonb('fdep_erp/66666666-6666-6666-6666-666666666666/manifest.json'::text)),
      '{schema_contract_sha256}', to_jsonb('invalid'::text)
    ),
    '{started_at}', to_jsonb('2026-09-01T01:01:00.000Z'::text)
  ) || jsonb_build_object(
    'observed_at', '2026-09-01T01:01:01.000Z',
    'completed_at', '2026-09-01T01:01:02.000Z'
  ),
  jsonb_set(
    jsonb_set(
      jsonb_set(manifest, '{run_id}',
        to_jsonb('66666666-6666-6666-6666-666666666666'::text)),
      '{raw_objects,0,key}',
        to_jsonb('fdep_erp/66666666-6666-6666-6666-666666666666/layer-0-page-0.json'::text)
    ),
    '{started_at}', to_jsonb('2026-09-01T01:01:00.000Z'::text)
  ) || jsonb_build_object(
    'observed_at', '2026-09-01T01:01:01.000Z',
    'completed_at', '2026-09-01T01:01:02.000Z'
  )
from atomic_test_payloads
where run_id = '55555555-5555-5555-5555-555555555555';
update atomic_test_payloads
set manifest = manifest || jsonb_build_object('terminal_receipt', receipt)
where run_id = '66666666-6666-6666-6666-666666666666';

set role service_role;
insert into public.external_source_run_stage (source_id, run_id, row_key, row_data)
values (
  'fdep_erp', '66666666-6666-6666-6666-666666666666', '0:5002',
  jsonb_build_object(
    'layer_id', 0, 'objectid', 5002, 'permit_id', 'ERP-FIXTURE-5002',
    'application_id', 'APP-5002', 'project_id', 5002,
    'project_name', 'FDEP rollback fixture', 'applicant_name', 'Fixture Applicant',
    'applicant_company', 'Fixture LLC', 'permit_type', 'ERP',
    'permit_status', 'ACTIVE', 'defined_status', 'IN REVIEW',
    'division', 'Water Resource Management',
    'permitting_program', 'Environmental Resource Permitting',
    'district', 'Southeast', 'office_abbrev', 'SED',
    'location_id', 'LOC-5002', 'location_name', 'Fixture rollback site',
    'street_address', '5002 Test Ave', 'city', 'Fort Lauderdale',
    'state', 'FL', 'zip5', '33301', 'zip4', null,
    'received_date', '2026-08-31', 'agency_action', null,
    'agency_action_date', null, 'documents_url', 'https://example.invalid/5002',
    'lat', 26.12, 'lon', -80.14, 'raw', '{}'::jsonb
  )
);
do $$
begin
  perform public.fs_commit_external_source_run(source_id, run_id, receipt, manifest)
  from atomic_test_payloads
  where run_id = '66666666-6666-6666-6666-666666666666';
  raise exception 'expected FDEP receipt hash constraint failure';
exception
  when check_violation then null;
end
$$;
select public.test_assert(
  not exists (select 1 from public.fdep_erp where layer_id = 0 and objectid = 5002),
  'FDEP receipt failure must roll back its source upsert'
);
select public.test_assert(
  exists (
    select 1 from public.external_source_run_stage
    where run_id = '66666666-6666-6666-6666-666666666666'
  ),
  'FDEP receipt failure must retain its staged row'
);
select public.test_assert(
  not exists (
    select 1 from public.external_source_run_receipts
    where run_id = '66666666-6666-6666-6666-666666666666'
  ),
  'FDEP receipt failure must not leave a terminal row'
);
reset role;

select 'external_source_atomic_assertions_passed' as result;
