-- Run only against a disposable local Supabase/Postgres test database after all
-- tracked migrations have been applied. The transaction rolls back every fixture.

begin;

select plan(42);

select has_table(
  'public', 'external_source_run_receipts',
  'FDEP/FAA terminal receipt table exists'
);
select has_table(
  'public', 'broward_parcel_import_generations',
  'parcel generation receipt table exists'
);
select has_table(
  'public', 'broward_parcel_generation_ranges',
  'generation-bound range table exists'
);
select has_table(
  'public', 'broward_parcel_geography_stage',
  'generation-bound parcel stage exists'
);
select has_function(
  'public', 'fs_promote_broward_parcel_generation', array['uuid'],
  'parcel promotion gate exists'
);
select ok(
  'search_path=pg_catalog' = any(
    coalesce(
      (select p.proconfig
       from pg_proc p
       where p.oid = 'public.fs_normalize_folio(text)'::regprocedure),
      array[]::text[]
    )
  ),
  'folio normalizer has an explicit pg_catalog-only search path'
);

select is(
  (select relrowsecurity from pg_class
   where oid = 'public.external_source_run_receipts'::regclass),
  true,
  'source receipts have RLS enabled'
);
select is(
  (select relforcerowsecurity from pg_class
   where oid = 'public.external_source_run_receipts'::regclass),
  true,
  'source receipts force RLS'
);
select is(
  (select relrowsecurity from pg_class
   where oid = 'public.broward_parcel_import_generations'::regclass),
  true,
  'parcel generations have RLS enabled'
);
select is(
  (select relforcerowsecurity from pg_class
   where oid = 'public.broward_parcel_import_generations'::regclass),
  true,
  'parcel generations force RLS'
);
select is(
  (select relrowsecurity from pg_class
   where oid = 'public.broward_parcel_generation_ranges'::regclass),
  true,
  'parcel ranges have RLS enabled'
);
select is(
  (select relforcerowsecurity from pg_class
   where oid = 'public.broward_parcel_generation_ranges'::regclass),
  true,
  'parcel ranges force RLS'
);
select is(
  (select relrowsecurity from pg_class
   where oid = 'public.broward_parcel_geography_stage'::regclass),
  true,
  'parcel staging has RLS enabled'
);
select is(
  (select relforcerowsecurity from pg_class
   where oid = 'public.broward_parcel_geography_stage'::regclass),
  true,
  'parcel staging forces RLS'
);

select ok(
  not has_table_privilege(
    'anon', 'public.external_source_run_receipts', 'select'
  ),
  'anon cannot read private source receipts'
);
select ok(
  not has_table_privilege(
    'authenticated', 'public.external_source_run_receipts', 'select'
  ),
  'authenticated cannot read private source receipts'
);
select ok(
  has_table_privilege(
    'service_role', 'public.external_source_run_receipts', 'insert'
  ),
  'service role can insert source receipts'
);
select ok(
  has_table_privilege(
    'service_role', 'public.external_source_run_receipts', 'select'
  ),
  'service role can read source receipts for idempotent verification'
);
select ok(
  not has_table_privilege(
    'service_role', 'public.external_source_run_receipts', 'update'
  ),
  'service role cannot update source receipts'
);
select ok(
  not has_table_privilege(
    'service_role', 'public.external_source_run_receipts', 'delete'
  ),
  'service role cannot delete source receipts'
);
select ok(
  not has_table_privilege(
    'service_role', 'public.broward_parcel_geography_stage', 'insert'
  ),
  'parcel staging remains disconnected from service role'
);
select ok(
  not has_function_privilege(
    'service_role',
    'public.fs_promote_broward_parcel_generation(uuid)',
    'execute'
  ),
  'parcel promotion remains disconnected from service role'
);

select lives_ok(
  $sql$
    insert into public.external_source_run_receipts (
      run_id, source_id, collector_name, collector_version,
      parser_version, normalizer_version, status,
      started_at, observed_at, completed_at,
      attempted_event_from, attempted_event_through, event_through,
      pages_attempted, pages_succeeded, responses_observed,
      rows_observed, rows_accepted, rows_inserted, rows_updated,
      rows_unchanged, rows_rejected, source_schema_sha256,
      schema_contract_sha256, raw_manifest_sha256, raw_manifest_object_key
    ) values (
      '11111111-1111-1111-1111-111111111111',
      'fdep_erp', 'fdep-erp-sync', 'exported-sha',
      'parser-v1', 'normalizer-v1', 'ok',
      '2026-08-31T09:20:00Z', '2026-08-31T09:20:10Z',
      '2026-08-31T09:20:12Z',
      '2026-08-30T00:00:00Z', '2026-08-31T00:00:00Z',
      '2026-08-30T00:00:00Z',
      1, 1, 1, 2, 2, 0, 0, 2, 0,
      repeat('a', 64), repeat('f', 64), repeat('b', 64),
      'fdep/11111111-1111-1111-1111-111111111111/manifest.json'
    )
  $sql$,
  'a reconciled source receipt is accepted'
);

select throws_ok(
  $sql$
    insert into public.external_source_run_receipts (
      run_id, source_id, collector_name, collector_version,
      parser_version, normalizer_version, status,
      started_at, observed_at, completed_at,
      rows_observed, rows_accepted, rows_unchanged, rows_rejected,
      schema_contract_sha256, source_schema_sha256,
      raw_manifest_sha256, raw_manifest_object_key
    ) values (
      '22222222-2222-2222-2222-222222222222',
      'faa_oeaaa', 'faa-oeaaa-sync', 'exported-sha',
      'parser-v1', 'normalizer-v1', 'ok',
      '2026-08-31T09:40:00Z', '2026-08-31T09:40:10Z',
      '2026-08-31T09:40:12Z',
      2, 1, 1, 0,
      repeat('f', 64), repeat('a', 64), repeat('b', 64),
      'faa/22222222-2222-2222-2222-222222222222/manifest.json'
    )
  $sql$,
  '23514',
  null,
  'unreconciled source row counts fail closed'
);

select throws_ok(
  $sql$
    update public.external_source_run_receipts
    set reason_detail = 'tamper'
    where run_id = '11111111-1111-1111-1111-111111111111'
  $sql$,
  '55000',
  'external source run receipts are append-only',
  'receipt rows cannot be mutated even by the table owner'
);

select lives_ok(
  $sql$
    insert into public.broward_parcel_import_generations (
      generation_id, source_layer_url, source_dataset_vintage,
      collector_version, parser_version, normalizer_version,
      coverage_oid_min, coverage_oid_max, expected_range_count,
      source_reported_count, minimum_accepted_rows,
      max_rejected_rows, max_duplicate_folios, quality_contract_sha256,
      started_at
    ) values (
      '33333333-3333-3333-3333-333333333333',
      'https://example.invalid/FeatureServer/0', 'fixture-v1',
      'collector-v1', 'parser-v1', 'normalizer-v1',
      0, 9, 1, 1, 1, 0, 0, repeat('9', 64),
      '2026-08-31T10:00:00Z'
    )
  $sql$,
  'a parcel generation starts in staging'
);

select lives_ok(
  $sql$
    insert into public.broward_parcel_generation_ranges (
      generation_id, oid_min, oid_max, expected_source_count,
      rows_received, rows_accepted, rows_rejected, status, attempts,
      raw_manifest_sha256, raw_manifest_object_key,
      started_at, completed_at
    ) values (
      '33333333-3333-3333-3333-333333333333',
      0, 9, 1, 1, 1, 0, 'complete', 1,
      repeat('c', 64),
      'parcel/33333333-3333-3333-3333-333333333333/0-9.json',
      '2026-08-31T10:00:01Z', '2026-08-31T10:00:02Z'
    )
  $sql$,
  'a complete generation-bound range is accepted'
);

select throws_ok(
  $sql$
    insert into public.broward_parcel_generation_ranges (
      generation_id, oid_min, oid_max
    ) values (
      '33333333-3333-3333-3333-333333333333', 5, 10
    )
  $sql$,
  '23514',
  'parcel OBJECTID ranges may not overlap within a generation',
  'overlapping OBJECTID ranges fail before promotion'
);

select lives_ok(
  $sql$
    insert into public.broward_parcel_geography_stage (
      generation_id, parcel_id_normalized, parcel_id_raw,
      folio_number_raw, latitude, longitude, source_object_id, fetched_at
    ) values (
      '33333333-3333-3333-3333-333333333333',
      '484306BH0010', '484306BH0010', '484306BH0010',
      26.10, -80.10, 2, '2026-08-31T10:00:02Z'
    )
  $sql$,
  'a canonical alphanumeric folio stages successfully'
);

select throws_ok(
  $sql$
    update public.broward_parcel_geography_stage
    set generation_id = '55555555-5555-5555-5555-555555555555'
    where generation_id = '33333333-3333-3333-3333-333333333333'
  $sql$,
  '23514',
  'staged parcel generation binding is immutable',
  'a staged row cannot be moved to another generation'
);

select throws_ok(
  $sql$
    insert into public.broward_parcel_geography_stage (
      generation_id, parcel_id_normalized, parcel_id_raw,
      folio_number_raw, latitude, longitude, source_object_id, fetched_at
    ) values (
      '33333333-3333-3333-3333-333333333333',
      '504212AA0001', '504212AA0001', '484306BH0010',
      26.11, -80.11, 3, '2026-08-31T10:00:03Z'
    )
  $sql$,
  '23514',
  null,
  'contradictory raw folio evidence fails closed'
);

select throws_ok(
  $sql$
    update public.broward_parcel_generation_ranges
    set generation_id = '55555555-5555-5555-5555-555555555555'
    where generation_id = '33333333-3333-3333-3333-333333333333'
  $sql$,
  '23514',
  'parcel range generation binding is immutable',
  'a range receipt cannot be moved to another generation'
);

select lives_ok(
  $sql$
    update public.broward_parcel_import_generations
    set status = 'ready',
        rows_received = 1,
        rows_accepted = 1,
        source_observed_at = '2026-08-31T10:00:03Z',
        completed_at = '2026-08-31T10:00:04Z',
        source_schema_sha256 = repeat('d', 64),
        raw_manifest_sha256 = repeat('e', 64),
        raw_manifest_object_key =
          'parcel/33333333-3333-3333-3333-333333333333/manifest.json'
    where generation_id = '33333333-3333-3333-3333-333333333333'
  $sql$,
  'a reconciled generation can become ready'
);

select is(
  (select p.proowner
   from pg_proc p
   where p.oid =
     'public.fs_promote_broward_parcel_generation(uuid)'::regprocedure),
  (select c.relowner
   from pg_class c
   where c.oid = 'public.broward_parcel_import_generations'::regclass),
  'promotion function and generation table have the same owner'
);

grant select, update on public.broward_parcel_import_generations to service_role;
set local role service_role;
select throws_ok(
  $sql$
    update public.broward_parcel_import_generations
    set status = 'promoted', promoted_at = now()
    where generation_id = '33333333-3333-3333-3333-333333333333'
  $sql$,
  '55000',
  'ready/promoted parcel generation receipts are immutable outside the promotion gate',
  'a non-owner cannot make a promotion-only state transition directly'
);
reset role;
revoke select, update on public.broward_parcel_import_generations from service_role;

select lives_ok(
  $sql$
    select public.fs_promote_broward_parcel_generation(
      '33333333-3333-3333-3333-333333333333'
    )
  $sql$,
  'a fully reconciled generation promotes successfully'
);

select is(
  (select status
   from public.broward_parcel_import_generations
   where generation_id = '33333333-3333-3333-3333-333333333333'),
  'promoted'::text,
  'successful promotion stamps the generation receipt'
);

select is(
  (select public.fs_promote_broward_parcel_generation(
    '33333333-3333-3333-3333-333333333333'
  ) ->> 'status'),
  'already_promoted'::text,
  'an exact promotion retry is idempotent'
);

select lives_ok(
  $sql$
    insert into public.broward_parcel_import_generations (
      generation_id, source_layer_url, source_dataset_vintage,
      collector_version, parser_version, normalizer_version,
      coverage_oid_min, coverage_oid_max, expected_range_count,
      source_reported_count, minimum_accepted_rows,
      max_rejected_rows, max_duplicate_folios, quality_contract_sha256,
      started_at
    ) values (
      '44444444-4444-4444-4444-444444444444',
      'https://example.invalid/FeatureServer/0', 'fixture-incomplete',
      'collector-v1', 'parser-v1', 'normalizer-v1',
      0, 9, 1, 1, 1, 0, 0, repeat('8', 64),
      '2026-08-31T10:01:00Z'
    )
  $sql$,
  'an independent incomplete generation can stage'
);

select lives_ok(
  $sql$
    update public.broward_parcel_import_generations
    set status = 'ready',
        source_observed_at = '2026-08-31T10:01:01Z',
        completed_at = '2026-08-31T10:01:02Z',
        source_schema_sha256 = repeat('d', 64),
        raw_manifest_sha256 = repeat('e', 64),
        raw_manifest_object_key =
          'parcel/44444444-4444-4444-4444-444444444444/manifest.json'
    where generation_id = '44444444-4444-4444-4444-444444444444'
  $sql$,
  'a terminal generation receipt may become ready before promotion validation'
);

select throws_ok(
  $sql$
    select public.fs_promote_broward_parcel_generation(
      '44444444-4444-4444-4444-444444444444'
    )
  $sql$,
  '23514',
  'parcel generation range coverage is incomplete, gapped, or overlapping',
  'promotion rejects a ready generation with missing ranges'
);

select is(
  (select count(*)
   from public.broward_parcel_geography
   where import_generation_id =
     '33333333-3333-3333-3333-333333333333'),
  1::bigint,
  'a rejected later promotion leaves the live promoted generation intact'
);

select * from finish();

rollback;
