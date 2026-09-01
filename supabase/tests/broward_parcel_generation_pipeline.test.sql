-- Run only against a disposable local Supabase/Postgres database after all
-- tracked migrations. This test performs no collector call and no promotion.

begin;

select plan(56);

select has_table('public', 'broward_parcel_quality_contracts', 'quality contract table exists');
select has_table('public', 'broward_parcel_generation_pages', 'page receipt table exists');
select has_table('public', 'broward_parcel_generation_observations', 'raw observation table exists');
select has_column('public', 'broward_parcel_generation_observations',
  'sale_date_1_null_reason', 'sale-date field-null reason is persisted');
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
select has_function('public', 'fs_fail_broward_parcel_generation',
  array['uuid','jsonb'], 'failure RPC exists');
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
  'public.fs_fail_broward_parcel_generation(uuid,jsonb)','execute'),
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
  'public.fs_fail_broward_parcel_generation(uuid,jsonb)'::regprocedure), true,
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
  'public.fs_fail_broward_parcel_generation(uuid,jsonb)'::regprocedure),array[]::text[])),
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

select * from finish();
rollback;
