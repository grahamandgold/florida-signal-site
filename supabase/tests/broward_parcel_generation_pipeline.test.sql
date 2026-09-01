-- Run only against a disposable local Supabase/Postgres database after all
-- tracked migrations. This test performs no collector call and no promotion.

begin;

select plan(82);

select has_table('public', 'broward_parcel_quality_contracts', 'quality contract table exists');
select has_table('public', 'broward_parcel_generation_pages', 'page receipt table exists');
select has_table('public', 'broward_parcel_generation_observations', 'raw observation table exists');
select has_column('public', 'broward_parcel_generation_observations',
  'sale_date_1_null_reason', 'sale-date field-null reason is persisted');
select has_column('public', 'broward_parcel_import_generations',
  'failure_receipt_sha256', 'failed generation binds the receipt SHA-256');
select has_column('public', 'broward_parcel_import_generations',
  'failure_receipt_object_key', 'failed generation binds the receipt object key');
select has_column('public', 'broward_parcel_import_generations',
  'terminal_receipt_sha256', 'successful generation binds the receipt SHA-256');
select has_column('public', 'broward_parcel_import_generations',
  'terminal_receipt_object_key', 'successful generation binds the receipt object key');
select has_table('public', 'broward_parcel_evidence_objects', 'immutable evidence ledger exists');
select has_table('public', 'broward_parcel_promotion_previews', 'promotion preview table exists');
select has_table('public', 'broward_parcel_promotion_authorizations', 'promotion authorization table exists');
select has_view('public', 'broward_parcel_pipeline_health', 'private Desk health view exists');

select has_function('public', 'fs_begin_broward_parcel_generation',
  array['uuid','jsonb','text','text','text','integer','text','integer','jsonb','jsonb'],
  'begin RPC exists');
select has_function('public', 'fs_stage_broward_parcel_page',
  array['uuid','integer','bigint','bigint','text','text','jsonb'],
  'page RPC exists');
select has_function('public', 'fs_finalize_broward_parcel_generation',
  array['uuid','text','text','text','text','text','text','text','text','jsonb'],
  'finalize RPC exists');
select has_function('public', 'fs_commit_broward_parcel_generation_receipt',
  array['uuid','text','jsonb'], 'terminal receipt RPC exists');
select has_function('public', 'fs_fail_broward_parcel_generation',
  array['uuid','text','text','jsonb','jsonb'], 'exact-body dual-evidence failure RPC exists');
select hasnt_function('public', 'fs_fail_broward_parcel_generation',
  array['uuid','jsonb'], 'receipt-only failure RPC is absent');
select hasnt_function('public', 'fs_fail_broward_parcel_generation',
  array['uuid','jsonb','jsonb','jsonb'], 'unbound JSON-only failure RPC is absent');
select has_function('public', 'fs_broward_parcel_range_manifests_match',
  array['uuid','jsonb'], 'exact range-manifest replay matcher exists');
select has_function('public', 'fs_preview_broward_parcel_generation',
  array['uuid'], 'owner-only preview function exists');
select has_function('public', 'fs_promote_broward_parcel_generation',
  array['uuid'], 'preview/backup-bound promotion wrapper exists');

select is((select relrowsecurity from pg_class
  where oid='public.broward_parcel_quality_contracts'::regclass), true,
  'quality contracts have RLS');
select is((select relforcerowsecurity from pg_class
  where oid='public.broward_parcel_quality_contracts'::regclass), true,
  'quality contracts force RLS');
select is((select relrowsecurity from pg_class
  where oid='public.broward_parcel_generation_pages'::regclass), true,
  'page receipts have RLS');
select is((select relforcerowsecurity from pg_class
  where oid='public.broward_parcel_generation_pages'::regclass), true,
  'page receipts force RLS');
select is((select relforcerowsecurity from pg_class
  where oid='public.broward_parcel_generation_observations'::regclass), true,
  'observations force RLS');
select is((select relforcerowsecurity from pg_class
  where oid='public.broward_parcel_evidence_objects'::regclass), true,
  'evidence ledger forces RLS');

select ok(not has_table_privilege('service_role',
  'public.broward_parcel_generation_observations','insert'),
  'service role cannot bypass the observation RPC');
select ok(not has_table_privilege('service_role',
  'public.broward_parcel_generation_pages','insert'),
  'service role cannot bypass the page RPC');
select ok(not has_table_privilege('service_role',
  'public.broward_parcel_evidence_objects','insert'),
  'service role cannot bypass the immutable evidence binding');
select ok(not has_table_privilege('service_role',
  'public.broward_parcel_import_generations','insert'),
  'service role cannot insert generation receipts directly');
select ok(not has_table_privilege('service_role',
  'public.broward_parcel_import_generations','update'),
  'service role cannot update generation receipts directly');
select ok(not has_table_privilege('service_role',
  'public.broward_parcel_generation_ranges','insert'),
  'service role cannot insert range receipts directly');
select ok(not has_table_privilege('service_role',
  'public.broward_parcel_generation_ranges','update'),
  'service role cannot update range receipts directly');
select ok(not has_table_privilege('service_role',
  'public.broward_parcel_geography_stage','insert'),
  'service role cannot write parcel stage directly');
select ok(not has_table_privilege('service_role',
  'public.broward_parcel_geography_stage','delete'),
  'service role cannot delete parcel stage directly');
select ok(not has_table_privilege('service_role',
  'public.broward_parcel_geography','insert'),
  'service role cannot insert live parcels');
select ok(not has_table_privilege('service_role',
  'public.broward_parcel_geography','update'),
  'service role cannot update live parcels');
select ok(not has_table_privilege('service_role',
  'public.broward_parcel_geography','delete'),
  'service role cannot delete live parcels');
select ok(not has_table_privilege('service_role',
  'public.broward_parcel_geography','truncate'),
  'service role cannot truncate live parcels');
select ok(not has_function_privilege('service_role',
  'public.fs_promote_broward_parcel_generation(uuid)','execute'),
  'service role cannot promote parcels');
select ok(not has_function_privilege('service_role',
  'public.fs_broward_parcel_range_manifests_match(uuid,jsonb)','execute'),
  'service role cannot call the private replay matcher directly');

select ok(has_function_privilege('service_role',
  'public.fs_begin_broward_parcel_generation(uuid,jsonb,text,text,text,integer,text,integer,jsonb,jsonb)','execute'),
  'service role may call begin RPC');
select ok(has_function_privilege('service_role',
  'public.fs_stage_broward_parcel_page(uuid,integer,bigint,bigint,text,text,jsonb)','execute'),
  'service role may call page RPC');
select ok(has_function_privilege('service_role',
  'public.fs_finalize_broward_parcel_generation(uuid,text,text,text,text,text,text,text,text,jsonb)','execute'),
  'service role may call finalize RPC');
select ok(has_function_privilege('service_role',
  'public.fs_commit_broward_parcel_generation_receipt(uuid,text,jsonb)','execute'),
  'service role may bind a terminal receipt');
select ok(has_function_privilege('service_role',
  'public.fs_fail_broward_parcel_generation(uuid,text,text,jsonb,jsonb)','execute'),
  'service role may call failure RPC');
select is((select prosecdef from pg_proc where oid =
  'public.fs_begin_broward_parcel_generation(uuid,jsonb,text,text,text,integer,text,integer,jsonb,jsonb)'::regprocedure), true,
  'begin RPC is a narrow definer boundary');
select is((select prosecdef from pg_proc where oid =
  'public.fs_stage_broward_parcel_page(uuid,integer,bigint,bigint,text,text,jsonb)'::regprocedure), true,
  'page RPC is a narrow definer boundary');
select is((select prosecdef from pg_proc where oid =
  'public.fs_finalize_broward_parcel_generation(uuid,text,text,text,text,text,text,text,text,jsonb)'::regprocedure), true,
  'finalize RPC is a narrow definer boundary');
select is((select prosecdef from pg_proc where oid =
  'public.fs_commit_broward_parcel_generation_receipt(uuid,text,jsonb)'::regprocedure), true,
  'terminal receipt RPC is a narrow definer boundary');
select is((select prosecdef from pg_proc where oid =
  'public.fs_fail_broward_parcel_generation(uuid,text,text,jsonb,jsonb)'::regprocedure), true,
  'failure RPC is a narrow definer boundary');
select ok('search_path=' = any(coalesce((select proconfig from pg_proc where oid =
  'public.fs_begin_broward_parcel_generation(uuid,jsonb,text,text,text,integer,text,integer,jsonb,jsonb)'::regprocedure),array[]::text[])),
  'begin RPC has an empty search path');
select ok('search_path=' = any(coalesce((select proconfig from pg_proc where oid =
  'public.fs_stage_broward_parcel_page(uuid,integer,bigint,bigint,text,text,jsonb)'::regprocedure),array[]::text[])),
  'page RPC has an empty search path');
select ok('search_path=' = any(coalesce((select proconfig from pg_proc where oid =
  'public.fs_finalize_broward_parcel_generation(uuid,text,text,text,text,text,text,text,text,jsonb)'::regprocedure),array[]::text[])),
  'finalize RPC has an empty search path');
select ok('search_path=' = any(coalesce((select proconfig from pg_proc where oid =
  'public.fs_commit_broward_parcel_generation_receipt(uuid,text,jsonb)'::regprocedure),array[]::text[])),
  'terminal receipt RPC has an empty search path');
select ok('search_path=' = any(coalesce((select proconfig from pg_proc where oid =
  'public.fs_fail_broward_parcel_generation(uuid,text,text,jsonb,jsonb)'::regprocedure),array[]::text[])),
  'failure RPC has an empty search path');

select is((select promotion_allowed from public.broward_parcel_quality_contracts
  where run_mode='canary'), false, 'canary contract is permanently non-promotable');
select results_eq(
  $$select minimum_source_rows, maximum_source_rows, minimum_accepted_rows,
           maximum_rejected_rows, maximum_duplicate_rows
    from public.broward_parcel_quality_contracts
    where run_mode='current_generation'$$,
  $$values (550000,560000,530000,200,25000)$$,
  'production quality bounds are migration-owned constants'
);
select results_eq(
  $$select contract_body->>'normalizer_version',
           contract_body#>>'{field_null_policy,sale_date_1,source_encoding}',
           contract_body#>>'{field_null_policy,sale_date_1,invalid_value_policy}'
    from public.broward_parcel_quality_contracts
    where run_mode='current_generation'$$,
  $$values ('broward-folio-centroid-sale-date-v2',
            'esriFieldTypeDate_epoch_milliseconds_utc',
            'field_null_with_reason_and_raw_attribute_v1')$$,
  'sale-date unit and field-null policy are migration-owned constants'
);
select is((select prosecdef from pg_proc where oid =
  'public.fs_promote_broward_parcel_generation(uuid)'::regprocedure), true,
  'promotion wrapper is security definer');
select ok('search_path=' = any(coalesce((select proconfig from pg_proc where oid =
  'public.fs_promote_broward_parcel_generation(uuid)'::regprocedure),array[]::text[])),
  'promotion wrapper has an empty search path');
select ok('security_invoker=true' = any(coalesce((select reloptions from pg_class where oid =
  'public.broward_parcel_pipeline_health'::regclass),array[]::text[])),
  'Desk health view uses invoker security');
select ok(has_table_privilege('service_role',
  'public.broward_parcel_pipeline_health','select'),
  'service role may read aggregate Desk health');
select ok(not has_table_privilege('anon',
  'public.broward_parcel_pipeline_health','select'),
  'anon cannot read private parcel health');
select ok(not has_table_privilege('service_role',
  'public.broward_parcel_quality_contracts','insert'),
  'collector cannot alter quality contracts');
select has_column('public', 'broward_parcel_promotion_authorizations',
  'backup_storage_object_id', 'backup authorization binds exact Storage object identity');

insert into public.broward_parcel_import_generations (
  generation_id,
  source_layer_url,
  source_dataset_vintage,
  collector_version,
  parser_version,
  normalizer_version,
  coverage_oid_min,
  coverage_oid_max,
  expected_range_count,
  source_reported_count,
  minimum_accepted_rows,
  max_rejected_rows,
  max_duplicate_folios,
  quality_contract_sha256,
  source_schema_sha256,
  status,
  started_at,
  generation_protocol,
  run_mode,
  source_universe_count,
  source_vintage_json,
  promotion_eligible
) values (
  '22222222-2222-4222-8222-222222222222',
  'https://services.arcgis.com/JMAJrTsHNLrSsWf5/arcgis/rest/services/PARCEL_POLY_BCPA_TAXROLL/FeatureServer/0',
  'fixture',
  'fixture-collector',
  'fixture-parser',
  'broward-folio-centroid-sale-date-v2',
  0,
  19999,
  1,
  2,
  1,
  24,
  24,
  '31824f7c0a0ce627e955ae17f4b156f174f4ab9dea77245d64115958aa2f8575',
  repeat('b', 64),
  'staging',
  now(),
  'single_stream_v1',
  'canary',
  2,
  '{}'::jsonb,
  false
);

insert into public.broward_parcel_generation_ranges (
  generation_id,
  oid_min,
  oid_max,
  expected_source_count,
  rows_received,
  rows_accepted,
  rows_rejected,
  rejected_missing_folio,
  rejected_bad_folio_format,
  rejected_missing_centroid,
  rejected_out_of_bounds,
  duplicate_folios,
  status,
  attempts,
  raw_manifest_sha256,
  raw_manifest_object_key,
  started_at,
  completed_at
) values (
  '22222222-2222-4222-8222-222222222222',
  0,
  19999,
  2,
  2,
  2,
  0,
  0,
  0,
  0,
  0,
  0,
  'complete',
  1,
  repeat('a', 64),
  'broward-parcel-generations/22222222-2222-4222-8222-222222222222/manifests/range-000000000-000019999.json',
  now(),
  now()
);

create temporary table broward_parcel_range_manifest_fixture (
  payload jsonb not null
) on commit drop;

insert into broward_parcel_range_manifest_fixture (payload) values (
  jsonb_build_array(jsonb_build_object(
    'duplicates_within_or_across_ranges', 0,
    'manifest_object_key',
      'broward-parcel-generations/22222222-2222-4222-8222-222222222222/manifests/range-000000000-000019999.json',
    'manifest_sha256', repeat('a', 64),
    'range_end', 19999,
    'range_start', 0,
    'rejected_bad_folio_format', 0,
    'rejected_missing_centroid', 0,
    'rejected_missing_folio', 0,
    'rejected_out_of_bounds_centroid', 0,
    'rows_accepted', 2,
    'rows_received', 2,
    'rows_rejected', 0
  ))
);

select ok(public.fs_broward_parcel_range_manifests_match(
  '22222222-2222-4222-8222-222222222222', payload
), 'exact persisted range-manifest replay matches')
from broward_parcel_range_manifest_fixture;

select ok(not public.fs_broward_parcel_range_manifests_match(
  '22222222-2222-4222-8222-222222222222',
  jsonb_set(payload, '{0,rows_received}', '3'::jsonb)
), 'range-manifest replay rejects a changed count')
from broward_parcel_range_manifest_fixture;

select ok(not public.fs_broward_parcel_range_manifests_match(
  '22222222-2222-4222-8222-222222222222',
  jsonb_set(
    payload,
    '{0,manifest_object_key}',
    to_jsonb('broward-parcel-generations/22222222-2222-4222-8222-222222222222/manifests/changed.json'::text)
  )
), 'range-manifest replay rejects a changed object key')
from broward_parcel_range_manifest_fixture;

select ok(not public.fs_broward_parcel_range_manifests_match(
  '22222222-2222-4222-8222-222222222222',
  jsonb_set(payload, '{0,manifest_sha256}', to_jsonb(repeat('c', 64)))
), 'range-manifest replay rejects a changed SHA-256')
from broward_parcel_range_manifest_fixture;

select ok(not public.fs_broward_parcel_range_manifests_match(
  '22222222-2222-4222-8222-222222222222', '[]'::jsonb
), 'range-manifest replay rejects a missing persisted row');

select ok(not public.fs_broward_parcel_range_manifests_match(
  '22222222-2222-4222-8222-222222222222', payload || payload
), 'range-manifest replay rejects an extra row')
from broward_parcel_range_manifest_fixture;

select throws_ok(
  format(
    'select public.fs_broward_parcel_range_manifests_match(%L, %L::jsonb)',
    '22222222-2222-4222-8222-222222222222',
    payload #- '{0,rows_received}'
  ),
  '22023',
  'invalid parcel range manifest payload',
  'range-manifest replay rejects a missing property as malformed'
)
from broward_parcel_range_manifest_fixture;

select throws_ok(
  format(
    'select public.fs_broward_parcel_range_manifests_match(%L, %L::jsonb)',
    '22222222-2222-4222-8222-222222222222',
    jsonb_set(payload, '{0,unexpected}', '0'::jsonb)
  ),
  '22023',
  'invalid parcel range manifest payload',
  'range-manifest replay rejects an extra property as malformed'
)
from broward_parcel_range_manifest_fixture;

select throws_ok(
  format(
    'select public.fs_broward_parcel_range_manifests_match(%L, %L::jsonb)',
    '22222222-2222-4222-8222-222222222222',
    jsonb_set(payload, '{0,rows_received}', '"2"'::jsonb)
  ),
  '22023',
  'invalid parcel range manifest payload',
  'range-manifest replay rejects a string count as malformed'
)
from broward_parcel_range_manifest_fixture;

update public.broward_parcel_import_generations
set
  rows_received = 2,
  rows_accepted = 2,
  rows_rejected = 0,
  rejected_missing_folio = 0,
  rejected_bad_folio_format = 0,
  rejected_missing_centroid = 0,
  rejected_out_of_bounds = 0,
  duplicate_folios = 0,
  raw_manifest_sha256 = repeat('d', 64),
  raw_manifest_object_key =
    'broward-parcel-generations/22222222-2222-4222-8222-222222222222/manifest.json',
  rejection_manifest_sha256 = repeat('e', 64),
  rejection_manifest_object_key =
    'broward-parcel-generations/22222222-2222-4222-8222-222222222222/manifests/rejections.jsonl',
  duplicate_manifest_sha256 = repeat('f', 64),
  duplicate_manifest_object_key =
    'broward-parcel-generations/22222222-2222-4222-8222-222222222222/manifests/duplicates.jsonl',
  source_content_sha256 = repeat('3', 64),
  source_object_id_set_sha256 = repeat('1', 64),
  system_object_id_set_sha256 = repeat('2', 64),
  folio_set_sha256 = repeat('4', 64),
  source_observed_at = now(),
  completed_at = now(),
  status = 'validated',
  promotion_eligible = false
where generation_id = '22222222-2222-4222-8222-222222222222';

select is(
  (
    public.fs_finalize_broward_parcel_generation(
      '22222222-2222-4222-8222-222222222222',
      'broward-parcel-generations/22222222-2222-4222-8222-222222222222/manifest.json',
      repeat('d', 64),
      'broward-parcel-generations/22222222-2222-4222-8222-222222222222/manifests/rejections.jsonl',
      repeat('e', 64),
      'broward-parcel-generations/22222222-2222-4222-8222-222222222222/manifests/duplicates.jsonl',
      repeat('f', 64),
      repeat('1', 64),
      repeat('2', 64),
      payload
    )->>'replayed'
  )::boolean,
  true,
  'terminal finalizer accepts an exact persisted range-manifest replay'
)
from broward_parcel_range_manifest_fixture;

select throws_ok(
  format(
    $sql$
      select public.fs_finalize_broward_parcel_generation(
        '22222222-2222-4222-8222-222222222222',
        'broward-parcel-generations/22222222-2222-4222-8222-222222222222/manifest.json',
        repeat('d', 64),
        'broward-parcel-generations/22222222-2222-4222-8222-222222222222/manifests/rejections.jsonl',
        repeat('e', 64),
        'broward-parcel-generations/22222222-2222-4222-8222-222222222222/manifests/duplicates.jsonl',
        repeat('f', 64),
        repeat('1', 64),
        repeat('2', 64),
        %L::jsonb
      )
    $sql$,
    jsonb_set(payload, '{0,rows_received}', '3'::jsonb)
  ),
  '23505',
  'generation finalization replay changed evidence',
  'terminal finalizer rejects a changed range-manifest replay'
)
from broward_parcel_range_manifest_fixture;

insert into public.broward_parcel_import_generations (
  generation_id,
  source_layer_url,
  source_dataset_vintage,
  collector_version,
  parser_version,
  normalizer_version,
  coverage_oid_min,
  coverage_oid_max,
  expected_range_count,
  source_reported_count,
  minimum_accepted_rows,
  max_rejected_rows,
  max_duplicate_folios,
  quality_contract_sha256,
  source_schema_sha256,
  status,
  started_at,
  generation_protocol,
  run_mode,
  source_universe_count,
  source_vintage_json,
  promotion_eligible
) values (
  '33333333-3333-4333-8333-333333333333',
  'https://services.arcgis.com/JMAJrTsHNLrSsWf5/arcgis/rest/services/PARCEL_POLY_BCPA_TAXROLL/FeatureServer/0',
  'fixture',
  'fixture-collector',
  'fixture-parser',
  'broward-folio-centroid-sale-date-v2',
  0,
  559999,
  28,
  550000,
  530000,
  200,
  25000,
  '7f2742496d4792bdb1129c9744b330f97f6e3802ce092d8c76667fcbeea98288',
  repeat('b', 64),
  'staging',
  now(),
  'single_stream_v1',
  'current_generation',
  550000,
  '{}'::jsonb,
  false
);

update public.broward_parcel_import_generations
set
  rows_received = 550000,
  rows_accepted = 550000,
  rows_rejected = 0,
  rejected_missing_folio = 0,
  rejected_bad_folio_format = 0,
  rejected_missing_centroid = 0,
  rejected_out_of_bounds = 0,
  duplicate_folios = 0,
  source_content_sha256 = repeat('1', 64),
  source_object_id_set_sha256 = repeat('2', 64),
  system_object_id_set_sha256 = repeat('3', 64),
  folio_set_sha256 = repeat('4', 64),
  rejection_manifest_sha256 = repeat('5', 64),
  rejection_manifest_object_key =
    'broward-parcel-generations/33333333-3333-4333-8333-333333333333/manifests/rejections.jsonl',
  duplicate_manifest_sha256 = repeat('6', 64),
  duplicate_manifest_object_key =
    'broward-parcel-generations/33333333-3333-4333-8333-333333333333/manifests/duplicates.jsonl',
  raw_manifest_sha256 = repeat('7', 64),
  raw_manifest_object_key =
    'broward-parcel-generations/33333333-3333-4333-8333-333333333333/manifest.json',
  source_observed_at = now(),
  completed_at = now(),
  status = 'validated',
  promotion_eligible = false
where generation_id = '33333333-3333-4333-8333-333333333333';

select lives_ok(
  $$
    update public.broward_parcel_import_generations
    set
      status = 'failed',
      failure_reason = 'terminal receipt upload failed',
      raw_manifest_sha256 = repeat('8', 64),
      raw_manifest_object_key =
        'broward-parcel-generations/33333333-3333-4333-8333-333333333333/failure-manifest.json',
      failure_receipt_sha256 = repeat('9', 64),
      failure_receipt_object_key =
        'broward-parcel-generations/33333333-3333-4333-8333-333333333333/failure-receipt.json',
      source_observed_at = now(),
      completed_at = now(),
      promotion_eligible = false
    where generation_id = '33333333-3333-4333-8333-333333333333'
  $$,
  'an unpromoted validated generation can close as a durable failure'
);

select is(
  (select status from public.broward_parcel_import_generations
   where generation_id = '33333333-3333-4333-8333-333333333333'),
  'failed',
  'post-finalizer delivery failure cannot leave the generation ready'
);

select is(
  (select promotion_eligible from public.broward_parcel_import_generations
   where generation_id = '33333333-3333-4333-8333-333333333333'),
  false,
  'post-finalizer delivery failure clears promotion eligibility'
);

select * from finish();
rollback;
