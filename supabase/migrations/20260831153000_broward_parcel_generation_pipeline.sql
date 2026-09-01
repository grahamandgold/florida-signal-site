-- Broward current-generation parcel collector integration.
--
-- CODE ONLY. Applying this migration requires a separate reviewed production
-- migration approval. It creates no historical backfill and performs no
-- promotion. Before application, retire the legacy direct-to-live Edge writer,
-- export its exact deployed source, and take the backup described in the
-- companion runbook.

begin;

-- ---------------------------------------------------------------------------
-- Immutable, migration-owned quality contracts
-- ---------------------------------------------------------------------------

create table public.broward_parcel_quality_contracts (
  quality_contract_sha256 text primary key
    check (quality_contract_sha256 ~ '^[0-9a-f]{64}$'),
  contract_name text not null unique check (btrim(contract_name) <> ''),
  run_mode text not null check (run_mode in ('canary', 'current_generation')),
  contract_body jsonb not null check (jsonb_typeof(contract_body) = 'object'),
  source_layer_url text not null,
  minimum_source_rows integer not null check (minimum_source_rows > 0),
  maximum_source_rows integer not null check (maximum_source_rows >= minimum_source_rows),
  minimum_accepted_rows integer not null check (minimum_accepted_rows > 0),
  maximum_rejected_rows integer not null check (maximum_rejected_rows >= 0),
  maximum_duplicate_rows integer not null check (maximum_duplicate_rows >= 0),
  coverage_longitude_min double precision not null,
  coverage_longitude_max double precision not null,
  coverage_latitude_min double precision not null,
  coverage_latitude_max double precision not null,
  winner_rule text not null,
  promotion_allowed boolean not null,
  created_at timestamptz not null default now(),
  constraint broward_parcel_quality_bbox check (
    coverage_longitude_min < coverage_longitude_max
    and coverage_latitude_min < coverage_latitude_max
  ),
  constraint broward_parcel_canary_never_promotes check (
    run_mode <> 'canary' or promotion_allowed = false
  )
);

insert into public.broward_parcel_quality_contracts (
  quality_contract_sha256,
  contract_name,
  run_mode,
  contract_body,
  source_layer_url,
  minimum_source_rows,
  maximum_source_rows,
  minimum_accepted_rows,
  maximum_rejected_rows,
  maximum_duplicate_rows,
  coverage_longitude_min,
  coverage_longitude_max,
  coverage_latitude_min,
  coverage_latitude_max,
  winner_rule,
  promotion_allowed
) values
  (
    '86345dd19823bc431ccfd5ac7ab26e81d8ba2c6584c46f5064097c116a01aaca',
    'broward-parcel-current-generation-v1',
    'current_generation',
    '{"bbox":{"latitude_max":26.5,"latitude_min":25.9,"longitude_max":-79.98,"longitude_min":-80.7},"folio_normalizer":"uppercase_alphanumeric_exactly_12_nonzero_v1","maximum_duplicate_rows":25000,"maximum_rejected_rows":200,"maximum_source_rows":560000,"minimum_accepted_rows":530000,"minimum_source_rows":550000,"mode":"current_generation","range_width":20000,"schema_version":"FloridaSignalBrowardParcelQualityContractV1","source_layer_url":"https://services.arcgis.com/JMAJrTsHNLrSsWf5/arcgis/rest/services/PARCEL_POLY_BCPA_TAXROLL/FeatureServer/0","stable_source_object_id_field":"OBJECTID","system_object_id_field":"OBJECTID_12","winner_rule":"minimum_numeric_OBJECTID_then_minimum_OBJECTID_12"}'::jsonb,
    'https://services.arcgis.com/JMAJrTsHNLrSsWf5/arcgis/rest/services/PARCEL_POLY_BCPA_TAXROLL/FeatureServer/0',
    550000,
    560000,
    530000,
    200,
    25000,
    -80.70,
    -79.98,
    25.90,
    26.50,
    'minimum_numeric_OBJECTID_then_minimum_OBJECTID_12',
    true
  ),
  (
    '1d02ba8236997c3fbdba1b01074b5cd21836d335ebd4086ee5bcc9565b02d253',
    'broward-parcel-canary-v1',
    'canary',
    '{"bbox":{"latitude_max":26.5,"latitude_min":25.9,"longitude_max":-79.98,"longitude_min":-80.7},"folio_normalizer":"uppercase_alphanumeric_exactly_12_nonzero_v1","maximum_duplicate_rows":24,"maximum_rejected_rows":24,"maximum_source_rows":25,"minimum_accepted_rows":1,"minimum_source_rows":1,"mode":"canary","range_width":20000,"schema_version":"FloridaSignalBrowardParcelQualityContractV1","source_layer_url":"https://services.arcgis.com/JMAJrTsHNLrSsWf5/arcgis/rest/services/PARCEL_POLY_BCPA_TAXROLL/FeatureServer/0","stable_source_object_id_field":"OBJECTID","system_object_id_field":"OBJECTID_12","winner_rule":"minimum_numeric_OBJECTID_then_minimum_OBJECTID_12"}'::jsonb,
    'https://services.arcgis.com/JMAJrTsHNLrSsWf5/arcgis/rest/services/PARCEL_POLY_BCPA_TAXROLL/FeatureServer/0',
    1,
    25,
    1,
    24,
    24,
    -80.70,
    -79.98,
    25.90,
    26.50,
    'minimum_numeric_OBJECTID_then_minimum_OBJECTID_12',
    false
  );

alter table public.broward_parcel_quality_contracts enable row level security;
alter table public.broward_parcel_quality_contracts force row level security;
revoke all on table public.broward_parcel_quality_contracts
  from public, anon, authenticated, service_role;
grant select on table public.broward_parcel_quality_contracts to service_role;

create or replace function public.fs_reject_broward_parcel_contract_mutation()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception using
    errcode = '55000',
    message = 'Broward parcel quality contracts are migration-owned and immutable';
end
$$;

revoke all on function public.fs_reject_broward_parcel_contract_mutation()
  from public, anon, authenticated, service_role;

create trigger broward_parcel_quality_contract_no_row_mutation
  before insert or update or delete on public.broward_parcel_quality_contracts
  for each row execute function public.fs_reject_broward_parcel_contract_mutation();
create trigger broward_parcel_quality_contract_no_truncate
  before truncate on public.broward_parcel_quality_contracts
  for each statement execute function public.fs_reject_broward_parcel_contract_mutation();

-- ---------------------------------------------------------------------------
-- Extend the foundation generation receipt without rewriting old evidence
-- ---------------------------------------------------------------------------

alter table public.broward_parcel_import_generations
  add column generation_protocol text not null default 'foundation_v0',
  add column run_mode text,
  add column source_universe_count integer,
  add column source_vintage_json jsonb,
  add column source_content_sha256 text,
  add column source_object_id_set_sha256 text,
  add column system_object_id_set_sha256 text,
  add column folio_set_sha256 text,
  add column rejection_manifest_sha256 text,
  add column rejection_manifest_object_key text,
  add column duplicate_manifest_sha256 text,
  add column duplicate_manifest_object_key text,
  add column promotion_eligible boolean not null default false;

alter table public.broward_parcel_import_generations
  drop constraint if exists broward_parcel_import_generations_status_check;
alter table public.broward_parcel_import_generations
  add constraint broward_parcel_import_generations_status_check
  check (status in (
    'staging', 'canary_complete', 'ready', 'failed', 'promoted', 'superseded'
  ));

alter table public.broward_parcel_import_generations
  drop constraint if exists broward_parcel_generation_promoted_clock;
alter table public.broward_parcel_import_generations
  add constraint broward_parcel_generation_promoted_clock check (
    (status in ('staging', 'canary_complete', 'ready', 'failed') and promoted_at is null)
    or (status in ('promoted', 'superseded') and promoted_at is not null)
  );

create unique index broward_parcel_one_staging_current_generation_idx
  on public.broward_parcel_import_generations ((run_mode))
  where generation_protocol = 'single_stream_v1'
    and run_mode = 'current_generation'
    and status = 'staging';

alter table public.broward_parcel_import_generations
  drop constraint if exists broward_parcel_generation_quality_contract_bounds;
alter table public.broward_parcel_import_generations
  add constraint broward_parcel_generation_quality_contract_bounds check (
    minimum_accepted_rows <= source_reported_count
    and (
      generation_protocol = 'single_stream_v1'
      or (
        max_rejected_rows <= source_reported_count
        and max_duplicate_folios <= source_reported_count
      )
    )
  );

alter table public.broward_parcel_import_generations
  add constraint broward_parcel_generation_protocol_check check (
    generation_protocol in ('foundation_v0', 'single_stream_v1')
  ),
  add constraint broward_parcel_generation_v1_fields_check check (
    generation_protocol <> 'single_stream_v1'
    or (
      run_mode in ('canary', 'current_generation')
      and source_universe_count is not null
      and source_universe_count >= source_reported_count
      and (
        run_mode <> 'current_generation'
        or source_universe_count = source_reported_count
      )
      and jsonb_typeof(source_vintage_json) = 'object'
    )
  ),
  add constraint broward_parcel_generation_v1_hashes_check check (
    generation_protocol <> 'single_stream_v1'
    or status = 'staging'
    or status = 'failed'
    or (
      source_content_sha256 ~ '^[0-9a-f]{64}$'
      and source_object_id_set_sha256 ~ '^[0-9a-f]{64}$'
      and system_object_id_set_sha256 ~ '^[0-9a-f]{64}$'
      and folio_set_sha256 ~ '^[0-9a-f]{64}$'
      and rejection_manifest_sha256 ~ '^[0-9a-f]{64}$'
      and duplicate_manifest_sha256 ~ '^[0-9a-f]{64}$'
    )
  ),
  add constraint broward_parcel_generation_canary_nonpromotable check (
    run_mode is distinct from 'canary'
    or (
      promotion_eligible = false
      and status not in ('ready', 'promoted', 'superseded')
    )
  );

create or replace function public.fs_validate_broward_parcel_generation_contract()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  c public.broward_parcel_quality_contracts%rowtype;
begin
  if new.generation_protocol <> 'single_stream_v1' then
    return new;
  end if;

  select * into c
  from public.broward_parcel_quality_contracts
  where quality_contract_sha256 = new.quality_contract_sha256;

  if not found then
    raise exception using errcode = '23514', message = 'unreviewed parcel quality contract';
  end if;
  if new.run_mode is distinct from c.run_mode
     or new.source_layer_url is distinct from c.source_layer_url
     or new.source_reported_count not between c.minimum_source_rows and c.maximum_source_rows
     or new.minimum_accepted_rows is distinct from c.minimum_accepted_rows
     or new.max_rejected_rows is distinct from c.maximum_rejected_rows
     or new.max_duplicate_folios is distinct from c.maximum_duplicate_rows then
    raise exception using
      errcode = '23514',
      message = 'parcel generation does not match its immutable quality contract';
  end if;
  if new.status = 'staging' and new.promotion_eligible then
    raise exception using
      errcode = '23514',
      message = 'a staging parcel generation cannot be promotion eligible';
  end if;
  if new.run_mode = 'canary' and (
    new.status not in ('staging', 'canary_complete', 'failed')
    or new.promotion_eligible
  ) then
    raise exception using
      errcode = '23514',
      message = 'a canary parcel generation is permanently non-promotable';
  end if;
  return new;
end
$$;

revoke all on function public.fs_validate_broward_parcel_generation_contract()
  from public, anon, authenticated, service_role;
create trigger broward_parcel_generation_contract_guard
  before insert or update on public.broward_parcel_import_generations
  for each row execute function public.fs_validate_broward_parcel_generation_contract();

-- Replace the foundation state guard so canary_complete is an immutable
-- terminal state while owner-only ready -> promoted remains unchanged.
create or replace function public.fs_guard_broward_parcel_generation_update()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  generation_owner text;
begin
  select pg_catalog.pg_get_userbyid(c.relowner)
    into generation_owner
  from pg_catalog.pg_class c
  where c.oid = 'public.broward_parcel_import_generations'::regclass;

  if tg_op = 'DELETE' then
    if old.status <> 'staging' then
      raise exception using errcode = '55000',
        message = 'terminal parcel generation receipts cannot be deleted';
    end if;
    return old;
  end if;

  if tg_op = 'INSERT' and new.status <> 'staging' then
    raise exception using errcode = '23514',
      message = 'new parcel generations must begin in staging state';
  end if;

  if tg_op = 'UPDATE' then
    if old.generation_id <> new.generation_id
       or old.source_name <> new.source_name
       or old.source_layer_url <> new.source_layer_url
       or old.source_dataset_vintage <> new.source_dataset_vintage
       or old.collector_version <> new.collector_version
       or old.parser_version <> new.parser_version
       or old.normalizer_version <> new.normalizer_version
       or old.coverage_oid_min <> new.coverage_oid_min
       or old.coverage_oid_max <> new.coverage_oid_max
       or old.expected_range_count <> new.expected_range_count
       or old.source_reported_count <> new.source_reported_count
       or old.minimum_accepted_rows <> new.minimum_accepted_rows
       or old.max_rejected_rows <> new.max_rejected_rows
       or old.max_duplicate_folios <> new.max_duplicate_folios
       or old.quality_contract_sha256 <> new.quality_contract_sha256
       or old.generation_protocol <> new.generation_protocol
       or old.run_mode is distinct from new.run_mode
       or old.source_universe_count is distinct from new.source_universe_count
       or old.source_vintage_json is distinct from new.source_vintage_json
       or old.started_at <> new.started_at
       or old.created_at <> new.created_at then
      raise exception using errcode = '23514',
        message = 'parcel generation identity and source bounds are immutable';
    end if;

    if old.status = 'staging'
       and new.status in ('staging', 'canary_complete', 'ready', 'failed') then
      return new;
    end if;

    if current_user = generation_owner
       and (
         (old.status = 'ready' and new.status = 'promoted')
         or (old.status = 'promoted' and new.status = 'superseded')
       )
       and (
         (to_jsonb(new) - array['status', 'promoted_at']::text[])
         = (to_jsonb(old) - array['status', 'promoted_at']::text[])
       ) then
      return new;
    end if;

    raise exception using errcode = '55000',
      message = 'terminal parcel generation receipts are immutable outside promotion';
  end if;
  return new;
end
$$;

-- ---------------------------------------------------------------------------
-- Immutable page receipts and all raw observations, before global dedupe
-- ---------------------------------------------------------------------------

create table public.broward_parcel_generation_pages (
  generation_id uuid not null
    references public.broward_parcel_import_generations(generation_id) on delete restrict,
  page_index integer not null check (page_index >= 0),
  system_object_id_min bigint not null check (system_object_id_min >= 0),
  system_object_id_max bigint not null check (system_object_id_max >= system_object_id_min),
  row_count integer not null check (row_count > 0 and row_count <= 2000),
  raw_sha256 text not null check (raw_sha256 ~ '^[0-9a-f]{64}$'),
  raw_object_key text not null check (
    btrim(raw_object_key) <> ''
    and position('?' in raw_object_key) = 0
    and position(E'\n' in raw_object_key) = 0
  ),
  observations_sha256 text not null check (observations_sha256 ~ '^[0-9a-f]{64}$'),
  observed_at timestamptz not null default now(),
  primary key (generation_id, page_index),
  unique (generation_id, system_object_id_min, system_object_id_max)
);

create table public.broward_parcel_generation_observations (
  generation_id uuid not null
    references public.broward_parcel_import_generations(generation_id) on delete restrict,
  source_object_id bigint not null check (source_object_id >= 0),
  system_object_id bigint not null check (system_object_id >= 0),
  page_index integer not null,
  raw_folio text,
  folio_number_raw text,
  longitude double precision,
  latitude double precision,
  situs_address text,
  situs_city text,
  situs_zip_code text,
  parcel_type text,
  use_code text,
  use_type text,
  municipality text,
  sale_date_1 date,
  deed_type_1 text,
  stamp_amount_1 numeric,
  sale1_cin text,
  source_attributes_json jsonb not null check (jsonb_typeof(source_attributes_json) = 'object'),
  observed_at timestamptz not null default now(),
  primary key (generation_id, source_object_id),
  unique (generation_id, system_object_id),
  foreign key (generation_id, page_index)
    references public.broward_parcel_generation_pages(generation_id, page_index)
  on delete restrict
);

-- The collector must download every just-uploaded private object and verify its
-- exact SHA-256/size. Begin then binds that round-trip receipt to the immutable
-- Storage row identity and Storage-owned size metadata. Later RPCs trust only
-- this append-only ledger, never a bare object name or caller-supplied hash.
create table public.broward_parcel_evidence_objects (
  generation_id uuid not null
    references public.broward_parcel_import_generations(generation_id) on delete restrict,
  object_key text not null check (
    btrim(object_key) <> ''
    and position('?' in object_key) = 0
    and position(E'\n' in object_key) = 0
  ),
  purpose text not null check (purpose in (
    'raw_page', 'generation_manifest', 'range_manifest',
    'rejection_manifest', 'duplicate_manifest', 'supporting_evidence',
    'failure_receipt'
  )),
  sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  bytes bigint not null check (bytes >= 0),
  storage_object_id uuid not null unique,
  storage_created_at timestamptz not null,
  storage_updated_at timestamptz not null,
  storage_metadata_size bigint not null check (storage_metadata_size >= 0),
  verification_method text not null
    check (verification_method = 'private_storage_roundtrip_sha256_v1'),
  attested_at timestamptz not null default now(),
  primary key (generation_id, object_key),
  constraint broward_parcel_evidence_size_matches_storage check (
    bytes = storage_metadata_size
  ),
  constraint broward_parcel_evidence_key_is_generation_bound check (
    object_key like (
      'broward-parcel-generations/' || generation_id::text || '/%'
    )
  )
);

create index broward_parcel_observations_folio_idx
  on public.broward_parcel_generation_observations (
    generation_id,
    public.fs_normalize_folio(coalesce(raw_folio, folio_number_raw)),
    source_object_id,
    system_object_id
  );

alter table public.broward_parcel_generation_pages enable row level security;
alter table public.broward_parcel_generation_pages force row level security;
alter table public.broward_parcel_generation_observations enable row level security;
alter table public.broward_parcel_generation_observations force row level security;
alter table public.broward_parcel_evidence_objects enable row level security;
alter table public.broward_parcel_evidence_objects force row level security;

revoke all on table public.broward_parcel_generation_pages
  from public, anon, authenticated, service_role;
revoke all on table public.broward_parcel_generation_observations
  from public, anon, authenticated, service_role;
revoke all on table public.broward_parcel_evidence_objects
  from public, anon, authenticated, service_role;

create or replace function public.fs_reject_broward_parcel_observation_mutation()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception using errcode = '55000',
    message = 'parcel page receipts and observations are append-only';
end
$$;

revoke all on function public.fs_reject_broward_parcel_observation_mutation()
  from public, anon, authenticated, service_role;
create trigger broward_parcel_pages_no_row_mutation
  before update or delete on public.broward_parcel_generation_pages
  for each row execute function public.fs_reject_broward_parcel_observation_mutation();
create trigger broward_parcel_pages_no_truncate
  before truncate on public.broward_parcel_generation_pages
  for each statement execute function public.fs_reject_broward_parcel_observation_mutation();
create trigger broward_parcel_observations_no_row_mutation
  before update or delete on public.broward_parcel_generation_observations
  for each row execute function public.fs_reject_broward_parcel_observation_mutation();
create trigger broward_parcel_observations_no_truncate
  before truncate on public.broward_parcel_generation_observations
  for each statement execute function public.fs_reject_broward_parcel_observation_mutation();
create trigger broward_parcel_evidence_no_row_mutation
  before update or delete on public.broward_parcel_evidence_objects
  for each row execute function public.fs_reject_broward_parcel_observation_mutation();
create trigger broward_parcel_evidence_no_truncate
  before truncate on public.broward_parcel_evidence_objects
  for each statement execute function public.fs_reject_broward_parcel_observation_mutation();

-- The collector gets no direct staging DML. The four exact, empty-search-path
-- SECURITY DEFINER RPCs below are the only write boundary, which also prevents
-- callers from bypassing the per-generation advisory-lock order.
revoke all on table public.broward_parcel_import_generations
  from service_role;
revoke all on table public.broward_parcel_generation_ranges
  from service_role;
revoke all on table public.broward_parcel_geography_stage
  from service_role;
revoke all on sequence public.broward_parcel_generation_ranges_range_id_seq
  from service_role;

revoke insert, update, delete, truncate
  on public.broward_parcel_geography
  from public, anon, authenticated;
revoke insert, update, delete, truncate
  on public.broward_parcel_geography
  from service_role;

-- ---------------------------------------------------------------------------
-- Narrow service-role staging RPCs
-- ---------------------------------------------------------------------------

create or replace function public.fs_begin_broward_parcel_generation(
  p_generation_id uuid,
  p_evidence_objects jsonb,
  p_mode text,
  p_quality_contract_sha256 text,
  p_source_layer_url text,
  p_source_reported_count integer,
  p_source_schema_sha256 text,
  p_source_universe_count integer,
  p_source_vintage jsonb,
  p_ranges jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  c public.broward_parcel_quality_contracts%rowtype;
  range_count integer;
  range_min bigint;
  range_max bigint;
  range_sum bigint;
  invalid_range_count bigint;
  topology_errors bigint;
  replay_ranges_match boolean;
  replay_evidence_match boolean;
  evidence_count integer;
  evidence_inserted integer;
  invalid_evidence_count bigint;
  existing public.broward_parcel_import_generations%rowtype;
begin
  if p_generation_id is null
     or p_source_reported_count is null
     or p_source_universe_count is null
     or p_source_schema_sha256 !~ '^[0-9a-f]{64}$'
     or jsonb_typeof(p_source_vintage) <> 'object'
     or jsonb_typeof(p_evidence_objects) <> 'array'
     or jsonb_typeof(p_ranges) <> 'array' then
    raise exception using errcode = '22023', message = 'invalid parcel generation begin payload';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtext('florida-signal:broward-parcel:' || p_generation_id::text)
  );

  select * into c
  from public.broward_parcel_quality_contracts
  where quality_contract_sha256 = p_quality_contract_sha256
    and run_mode = p_mode
    and source_layer_url = p_source_layer_url;
  if not found then
    raise exception using errcode = '23514', message = 'unreviewed parcel quality contract';
  end if;
  if p_source_reported_count not between c.minimum_source_rows and c.maximum_source_rows
     or p_source_universe_count < p_source_reported_count
     or (
       p_mode = 'current_generation'
       and p_source_universe_count <> p_source_reported_count
     ) then
    raise exception using errcode = '23514', message = 'parcel source count violates contract';
  end if;

  with supplied as (
    select
      (item->>'range_start')::bigint as oid_min,
      (item->>'range_end')::bigint as oid_max,
      (item->>'rows_received')::integer as expected_source_count
    from jsonb_array_elements(p_ranges) item
  )
  select
    count(*), min(oid_min), max(oid_max), sum(expected_source_count),
    count(*) filter (where
      oid_min is null
      or oid_min < 0
      or oid_max is null
      or oid_max <> oid_min + 19999
      or mod(oid_min, 20000) <> 0
      or expected_source_count is null
      or expected_source_count < 0
    )
    into range_count, range_min, range_max, range_sum, invalid_range_count
  from supplied;

  if range_count <= 0
     or invalid_range_count <> 0
     or range_sum is distinct from p_source_reported_count then
    raise exception using errcode = '23514', message = 'parcel range totals do not reconcile';
  end if;

  with supplied as (
    select
      (item->>'range_start')::bigint as oid_min,
      (item->>'range_end')::bigint as oid_max
    from jsonb_array_elements(p_ranges) item
  ), ordered as (
    select oid_min, oid_max, lag(oid_max) over (order by oid_min, oid_max) as prior_max
    from supplied
  )
  select count(*) into topology_errors
  from ordered
  where oid_max < oid_min
     or (prior_max is null and oid_min <> range_min)
     or (prior_max is not null and oid_min <> prior_max + 1);
  if topology_errors <> 0 then
    raise exception using errcode = '23514', message = 'parcel ranges are gapped or overlapping';
  end if;

  with supplied as (
    select *
    from jsonb_to_recordset(p_evidence_objects) as x(
      object_key text,
      relative_path text,
      purpose text,
      sha256 text,
      bytes bigint,
      storage_object_id uuid,
      storage_updated_at timestamptz,
      storage_metadata_size bigint,
      verification_method text
    )
  )
  select
    count(*),
    count(*) filter (where
      object_key is null
      or object_key !~ ('^broward-parcel-generations/' || p_generation_id::text || '/')
      or position('?' in object_key) <> 0
      or position(E'\n' in object_key) <> 0
      or relative_path is null
      or relative_path = ''
      or position('..' in relative_path) <> 0
      or left(relative_path, 1) = '/'
      or object_key <> ('broward-parcel-generations/' || p_generation_id::text || '/' || relative_path)
      or purpose is null
      or purpose not in (
        'raw_page', 'generation_manifest', 'range_manifest',
        'rejection_manifest', 'duplicate_manifest', 'supporting_evidence'
      )
      or sha256 is null
      or sha256 !~ '^[0-9a-f]{64}$'
      or bytes is null
      or bytes < 0
      or storage_object_id is null
      or storage_updated_at is null
      or storage_metadata_size is distinct from bytes
      or verification_method is null
      or verification_method <> 'private_storage_roundtrip_sha256_v1'
    )
    into evidence_count, invalid_evidence_count
  from supplied;
  if evidence_count <= 0
     or invalid_evidence_count <> 0
     or evidence_count <> (
       select count(distinct item->>'object_key')
       from jsonb_array_elements(p_evidence_objects) item
     )
     or 1 <> (
       select count(*) from jsonb_array_elements(p_evidence_objects) item
       where item->>'purpose' = 'generation_manifest'
     )
     or 1 <> (
       select count(*) from jsonb_array_elements(p_evidence_objects) item
       where item->>'purpose' = 'rejection_manifest'
     )
     or 1 <> (
       select count(*) from jsonb_array_elements(p_evidence_objects) item
       where item->>'purpose' = 'duplicate_manifest'
     )
     or 1 > (
       select count(*) from jsonb_array_elements(p_evidence_objects) item
       where item->>'purpose' = 'raw_page'
     )
     or range_count <> (
       select count(*) from jsonb_array_elements(p_evidence_objects) item
       where item->>'purpose' = 'range_manifest'
     ) then
    raise exception using errcode = '23514',
      message = 'parcel evidence inventory is incomplete or invalid';
  end if;

  if exists (
    select 1
    from jsonb_to_recordset(p_evidence_objects) as e(
      object_key text,
      purpose text,
      sha256 text,
      bytes bigint,
      storage_object_id uuid,
      storage_updated_at timestamptz,
      storage_metadata_size bigint
    )
    left join storage.objects o
      on o.id = e.storage_object_id
     and o.bucket_id = 'fl-signal-source-evidence'
     and o.name = e.object_key
     and o.updated_at = e.storage_updated_at
    left join storage.buckets b on b.id = o.bucket_id
    where o.id is null
       or b.public is distinct from false
       or case
         when coalesce(o.metadata->>'size', o.metadata->>'contentLength', '') ~ '^[0-9]+$'
           then coalesce(o.metadata->>'size', o.metadata->>'contentLength')::numeric
             is distinct from e.storage_metadata_size::numeric
         else true
       end
  ) then
    raise exception using errcode = '23514',
      message = 'private evidence object identity or Storage-owned size is unverified';
  end if;

  select * into existing
  from public.broward_parcel_import_generations
  where generation_id = p_generation_id;
  if found then
    with supplied as (
      select
        (item->>'range_start')::bigint as oid_min,
        (item->>'range_end')::bigint as oid_max,
        (item->>'rows_received')::integer as expected_source_count
      from jsonb_array_elements(p_ranges) item
    ), stored as (
      select oid_min, oid_max, expected_source_count
      from public.broward_parcel_generation_ranges
      where generation_id = p_generation_id
    )
    select not exists (
      (select oid_min, oid_max, expected_source_count from supplied
       except
       select oid_min, oid_max, expected_source_count from stored)
      union all
      (select oid_min, oid_max, expected_source_count from stored
       except
       select oid_min, oid_max, expected_source_count from supplied)
    ) into replay_ranges_match;

    with supplied as (
      select object_key, purpose, sha256, bytes, storage_object_id,
             storage_updated_at, storage_metadata_size, verification_method
      from jsonb_to_recordset(p_evidence_objects) as x(
        object_key text,
        purpose text,
        sha256 text,
        bytes bigint,
        storage_object_id uuid,
        storage_updated_at timestamptz,
        storage_metadata_size bigint,
        verification_method text
      )
    ), stored as (
      select object_key, purpose, sha256, bytes, storage_object_id,
             storage_updated_at, storage_metadata_size, verification_method
      from public.broward_parcel_evidence_objects
      where generation_id = p_generation_id
    )
    select not exists (
      (select * from supplied except select * from stored)
      union all
      (select * from stored except select * from supplied)
    ) and not exists (
      select 1
      from public.broward_parcel_evidence_objects e
      left join storage.objects o
        on o.id = e.storage_object_id
       and o.bucket_id = 'fl-signal-source-evidence'
       and o.name = e.object_key
       and o.updated_at = e.storage_updated_at
       and coalesce(o.metadata->>'size', o.metadata->>'contentLength', '') ~ '^[0-9]+$'
       and coalesce(o.metadata->>'size', o.metadata->>'contentLength')::numeric
         = e.storage_metadata_size::numeric
      where e.generation_id = p_generation_id
        and o.id is null
    ) into replay_evidence_match;

    if existing.generation_protocol = 'single_stream_v1'
       and existing.run_mode = p_mode
       and existing.quality_contract_sha256 = p_quality_contract_sha256
       and existing.source_layer_url = p_source_layer_url
       and existing.source_schema_sha256 = p_source_schema_sha256
       and existing.source_reported_count = p_source_reported_count
       and existing.source_universe_count = p_source_universe_count
       and existing.source_vintage_json = p_source_vintage
       and existing.coverage_oid_min = range_min
       and existing.coverage_oid_max = range_max
       and existing.expected_range_count = range_count
       and replay_ranges_match
       and replay_evidence_match then
      if existing.status = 'staging' then
        return jsonb_build_object('generation_id', p_generation_id, 'status', 'replayed');
      end if;
      raise exception using errcode = '55000',
        message = 'generation_id already has a terminal receipt';
    end if;
    raise exception using errcode = '23505', message = 'generation_id replay changed identity';
  end if;

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
    p_generation_id,
    p_source_layer_url,
    coalesce(nullif(p_source_vintage->>'modified', ''), 'observed-no-modified-clock'),
    'broward_parcel_generation.py/v1',
    'broward-parcel-arcgis-v1',
    'broward-folio-centroid-v1',
    range_min,
    range_max,
    range_count,
    p_source_reported_count,
    c.minimum_accepted_rows,
    c.maximum_rejected_rows,
    c.maximum_duplicate_rows,
    c.quality_contract_sha256,
    p_source_schema_sha256,
    'staging',
    now(),
    'single_stream_v1',
    p_mode,
    p_source_universe_count,
    p_source_vintage,
    false
  );

  insert into public.broward_parcel_generation_ranges (
    generation_id, oid_min, oid_max, expected_source_count, status
  )
  select
    p_generation_id,
    (item->>'range_start')::bigint,
    (item->>'range_end')::bigint,
    (item->>'rows_received')::integer,
    'pending'
  from jsonb_array_elements(p_ranges) item;

  insert into public.broward_parcel_evidence_objects (
    generation_id,
    object_key,
    purpose,
    sha256,
    bytes,
    storage_object_id,
    storage_created_at,
    storage_updated_at,
    storage_metadata_size,
    verification_method
  )
  select
    p_generation_id,
    e.object_key,
    e.purpose,
    e.sha256,
    e.bytes,
    o.id,
    o.created_at,
    o.updated_at,
    coalesce(o.metadata->>'size', o.metadata->>'contentLength')::bigint,
    e.verification_method
  from jsonb_to_recordset(p_evidence_objects) as e(
    object_key text,
    purpose text,
    sha256 text,
    bytes bigint,
    storage_object_id uuid,
    storage_updated_at timestamptz,
    storage_metadata_size bigint,
    verification_method text
  )
  join storage.objects o
    on o.id = e.storage_object_id
   and o.bucket_id = 'fl-signal-source-evidence'
   and o.name = e.object_key
   and o.updated_at = e.storage_updated_at
   and coalesce(o.metadata->>'size', o.metadata->>'contentLength', '') ~ '^[0-9]+$'
   and coalesce(o.metadata->>'size', o.metadata->>'contentLength')::numeric
     = e.storage_metadata_size::numeric;
  get diagnostics evidence_inserted = row_count;
  if evidence_inserted <> evidence_count then
    raise exception using errcode = '23514',
      message = 'parcel evidence ledger did not bind every verified object';
  end if;

  return jsonb_build_object(
    'generation_id', p_generation_id,
    'quality_contract_sha256', c.quality_contract_sha256,
    'range_count', range_count,
    'status', 'staging'
  );
end
$$;

create or replace function public.fs_stage_broward_parcel_page(
  p_generation_id uuid,
  p_page_index integer,
  p_system_object_id_min bigint,
  p_system_object_id_max bigint,
  p_raw_sha256 text,
  p_raw_object_key text,
  p_observations jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  g_status text;
  payload_sha text;
  payload_count integer;
  observed_system_object_id_min bigint;
  observed_system_object_id_max bigint;
  invalid_identity_count bigint;
  existing public.broward_parcel_generation_pages%rowtype;
begin
  if p_generation_id is null
     or p_page_index < 0
     or p_system_object_id_max < p_system_object_id_min
     or p_raw_sha256 !~ '^[0-9a-f]{64}$'
     or p_raw_object_key !~ ('^broward-parcel-generations/' || p_generation_id::text || '/')
     or position('?' in p_raw_object_key) <> 0
     or jsonb_typeof(p_observations) <> 'array' then
    raise exception using errcode = '22023', message = 'invalid parcel page payload';
  end if;
  payload_count := jsonb_array_length(p_observations);
  if payload_count not between 1 and 2000 then
    raise exception using errcode = '22023', message = 'parcel page size is outside contract';
  end if;
  select
    min(x.system_object_id),
    max(x.system_object_id),
    count(*) filter (where
      x.system_object_id is null
      or x.system_object_id < 0
      or x.source_object_id is null
      or x.source_object_id < 0
      or jsonb_typeof(x.attributes) <> 'object'
      or case
        when jsonb_typeof(x.attributes -> 'OBJECTID') = 'number'
          then (x.attributes ->> 'OBJECTID')::numeric <> x.source_object_id
        when jsonb_typeof(x.attributes -> 'OBJECTID') = 'string'
             and (x.attributes ->> 'OBJECTID') ~ '^[0-9]+(?:[.]0+)?$'
          then (x.attributes ->> 'OBJECTID')::numeric <> x.source_object_id
        else true
      end
      or case
        when jsonb_typeof(x.attributes -> 'OBJECTID_12') = 'number'
          then (x.attributes ->> 'OBJECTID_12')::numeric <> x.system_object_id
        when jsonb_typeof(x.attributes -> 'OBJECTID_12') = 'string'
             and (x.attributes ->> 'OBJECTID_12') ~ '^[0-9]+(?:[.]0+)?$'
          then (x.attributes ->> 'OBJECTID_12')::numeric <> x.system_object_id
        else true
      end
    )
    into observed_system_object_id_min, observed_system_object_id_max,
      invalid_identity_count
  from jsonb_to_recordset(p_observations) as x(
    system_object_id bigint,
    source_object_id bigint,
    attributes jsonb
  );
  if invalid_identity_count <> 0
     or observed_system_object_id_min is distinct from p_system_object_id_min
     or observed_system_object_id_max is distinct from p_system_object_id_max then
    raise exception using errcode = '23514',
      message = 'parcel page mapped identities do not match source attributes or bounds';
  end if;
  payload_sha := encode(
    extensions.digest(pg_catalog.convert_to(p_observations::text, 'UTF8'), 'sha256'), 'hex'
  );

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtext('florida-signal:broward-parcel:' || p_generation_id::text)
  );
  select status into g_status
  from public.broward_parcel_import_generations
  where generation_id = p_generation_id
  for update;
  if g_status is distinct from 'staging' then
    raise exception using errcode = '55000', message = 'parcel generation is not staging';
  end if;

  if not exists (
    select 1
    from public.broward_parcel_evidence_objects e
    join storage.objects o
      on o.id = e.storage_object_id
     and o.bucket_id = 'fl-signal-source-evidence'
     and o.name = e.object_key
     and o.updated_at = e.storage_updated_at
     and coalesce(o.metadata->>'size', o.metadata->>'contentLength', '') ~ '^[0-9]+$'
     and coalesce(o.metadata->>'size', o.metadata->>'contentLength')::numeric
       = e.storage_metadata_size::numeric
    where e.generation_id = p_generation_id
      and e.object_key = p_raw_object_key
      and e.purpose = 'raw_page'
      and e.sha256 = p_raw_sha256
      and e.bytes = e.storage_metadata_size
  ) then
    raise exception using errcode = '23514',
      message = 'private raw page object lacks an exact immutable evidence attestation';
  end if;

  select * into existing
  from public.broward_parcel_generation_pages
  where generation_id = p_generation_id and page_index = p_page_index;
  if found then
    if existing.raw_sha256 = p_raw_sha256
       and existing.raw_object_key = p_raw_object_key
       and existing.observations_sha256 = payload_sha
       and existing.row_count = payload_count
       and existing.system_object_id_min = p_system_object_id_min
       and existing.system_object_id_max = p_system_object_id_max then
      return jsonb_build_object('page_index', p_page_index, 'status', 'replayed');
    end if;
    raise exception using errcode = '23505', message = 'parcel page replay changed evidence';
  end if;

  insert into public.broward_parcel_generation_pages (
    generation_id, page_index, system_object_id_min, system_object_id_max,
    row_count, raw_sha256, raw_object_key, observations_sha256
  ) values (
    p_generation_id, p_page_index, p_system_object_id_min, p_system_object_id_max,
    payload_count, p_raw_sha256, p_raw_object_key, payload_sha
  );

  insert into public.broward_parcel_generation_observations (
    generation_id,
    source_object_id,
    system_object_id,
    page_index,
    raw_folio,
    folio_number_raw,
    longitude,
    latitude,
    situs_address,
    situs_city,
    situs_zip_code,
    parcel_type,
    use_code,
    use_type,
    municipality,
    sale_date_1,
    deed_type_1,
    stamp_amount_1,
    sale1_cin,
    source_attributes_json
  )
  select
    p_generation_id,
    x.source_object_id,
    x.system_object_id,
    p_page_index,
    x.raw_folio,
    x.folio_number_raw,
    x.longitude,
    x.latitude,
    x.situs_address,
    x.situs_city,
    x.situs_zip_code,
    x.parcel_type,
    x.use_code,
    x.use_type,
    x.municipality,
    x.sale_date_1::date,
    x.deed_type_1,
    x.stamp_amount_1,
    x.sale1_cin,
    x.attributes
  from jsonb_to_recordset(p_observations) as x(
    system_object_id bigint,
    source_object_id bigint,
    raw_folio text,
    folio_number_raw text,
    longitude double precision,
    latitude double precision,
    situs_address text,
    situs_city text,
    situs_zip_code text,
    parcel_type text,
    use_code text,
    use_type text,
    municipality text,
    sale_date_1 text,
    deed_type_1 text,
    stamp_amount_1 numeric,
    sale1_cin text,
    attributes jsonb
  );

  if (select count(*) from public.broward_parcel_generation_observations
      where generation_id = p_generation_id and page_index = p_page_index) <> payload_count then
    raise exception using errcode = '23514', message = 'parcel page observation count mismatch';
  end if;
  return jsonb_build_object(
    'observations_sha256', payload_sha,
    'page_index', p_page_index,
    'rows_staged', payload_count,
    'status', 'inserted'
  );
end
$$;

revoke all on function public.fs_begin_broward_parcel_generation(
  uuid, jsonb, text, text, text, integer, text, integer, jsonb, jsonb
) from public, anon, authenticated;
grant execute on function public.fs_begin_broward_parcel_generation(
  uuid, jsonb, text, text, text, integer, text, integer, jsonb, jsonb
) to service_role;
revoke all on function public.fs_stage_broward_parcel_page(
  uuid, integer, bigint, bigint, text, text, jsonb
) from public, anon, authenticated;
grant execute on function public.fs_stage_broward_parcel_page(
  uuid, integer, bigint, bigint, text, text, jsonb
) to service_role;

create or replace function public.fs_finalize_broward_parcel_generation(
  p_generation_id uuid,
  p_manifest_key text,
  p_manifest_sha256 text,
  p_rejection_manifest_key text,
  p_rejection_manifest_sha256 text,
  p_duplicate_manifest_key text,
  p_duplicate_manifest_sha256 text,
  p_source_object_id_set_sha256 text,
  p_system_object_id_set_sha256 text,
  p_range_manifests jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  g public.broward_parcel_import_generations%rowtype;
  c public.broward_parcel_quality_contracts%rowtype;
  raw_count bigint;
  page_count bigint;
  page_row_sum bigint;
  missing_page_count bigint;
  accepted_count bigint;
  duplicate_count bigint;
  rejected_count bigint;
  missing_folio_count bigint;
  bad_folio_count bigint;
  missing_centroid_count bigint;
  out_of_bounds_count bigint;
  range_count bigint;
  bad_range_count bigint;
  observed_source_object_hash text;
  observed_system_object_hash text;
  observed_folio_hash text;
  observed_source_content_hash text;
  terminal_status text;
begin
  if p_generation_id is null
     or p_manifest_sha256 !~ '^[0-9a-f]{64}$'
     or p_rejection_manifest_sha256 !~ '^[0-9a-f]{64}$'
     or p_duplicate_manifest_sha256 !~ '^[0-9a-f]{64}$'
     or p_source_object_id_set_sha256 !~ '^[0-9a-f]{64}$'
     or p_system_object_id_set_sha256 !~ '^[0-9a-f]{64}$'
     or jsonb_typeof(p_range_manifests) <> 'array' then
    raise exception using errcode = '22023', message = 'invalid parcel finalization payload';
  end if;
  if p_manifest_key !~ ('^broward-parcel-generations/' || p_generation_id::text || '/')
     or p_rejection_manifest_key !~ ('^broward-parcel-generations/' || p_generation_id::text || '/')
     or p_duplicate_manifest_key !~ ('^broward-parcel-generations/' || p_generation_id::text || '/')
     or position('?' in p_manifest_key) <> 0
     or position('?' in p_rejection_manifest_key) <> 0
     or position('?' in p_duplicate_manifest_key) <> 0 then
    raise exception using errcode = '22023', message = 'parcel manifest key escaped its run prefix';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtext('florida-signal:broward-parcel:' || p_generation_id::text)
  );
  -- Match the child-before-parent lock order used by the foundation promotion.
  lock table public.broward_parcel_generation_pages in share mode;
  lock table public.broward_parcel_generation_observations in share mode;
  lock table public.broward_parcel_generation_ranges in share row exclusive mode;
  lock table public.broward_parcel_geography_stage in share row exclusive mode;

  select * into g
  from public.broward_parcel_import_generations
  where generation_id = p_generation_id
  for update;
  if not found then
    raise exception using errcode = 'P0002', message = 'parcel generation not found';
  end if;
  if g.generation_protocol <> 'single_stream_v1' then
    raise exception using errcode = '23514', message = 'generation is not single-stream v1';
  end if;

  if g.status in ('canary_complete', 'ready') then
    if g.raw_manifest_sha256 = p_manifest_sha256
       and g.raw_manifest_object_key = p_manifest_key
       and g.rejection_manifest_sha256 = p_rejection_manifest_sha256
       and g.rejection_manifest_object_key = p_rejection_manifest_key
       and g.duplicate_manifest_sha256 = p_duplicate_manifest_sha256
       and g.duplicate_manifest_object_key = p_duplicate_manifest_key
       and g.source_object_id_set_sha256 = p_source_object_id_set_sha256
       and g.system_object_id_set_sha256 = p_system_object_id_set_sha256 then
      return jsonb_build_object(
        'duplicate_rows', g.duplicate_folios,
        'folio_set_sha256', g.folio_set_sha256,
        'generation_id', p_generation_id,
        'promotion_eligible', g.promotion_eligible,
        'rejected_rows', g.rows_rejected,
        'replayed', true,
        'rows_accepted', g.rows_accepted,
        'rows_received', g.rows_received,
        'source_content_sha256', g.source_content_sha256,
        'source_object_id_set_sha256', g.source_object_id_set_sha256,
        'system_object_id_set_sha256', g.system_object_id_set_sha256,
        'status', g.status
      );
    end if;
    raise exception using errcode = '23505', message = 'generation finalization replay changed evidence';
  end if;
  if g.status <> 'staging' then
    raise exception using errcode = '55000', message = 'parcel generation is not staging';
  end if;

  select * into c
  from public.broward_parcel_quality_contracts
  where quality_contract_sha256 = g.quality_contract_sha256
    and run_mode = g.run_mode;
  if not found then
    raise exception using errcode = '23514', message = 'quality contract disappeared';
  end if;

  if exists (
    select 1
    from (values
      (p_manifest_key, p_manifest_sha256, 'generation_manifest'::text),
      (p_rejection_manifest_key, p_rejection_manifest_sha256, 'rejection_manifest'::text),
      (p_duplicate_manifest_key, p_duplicate_manifest_sha256, 'duplicate_manifest'::text)
    ) required(name, sha256, purpose)
    where not exists (
      select 1
      from public.broward_parcel_evidence_objects e
      join storage.objects o
        on o.id = e.storage_object_id
       and o.bucket_id = 'fl-signal-source-evidence'
       and o.name = e.object_key
       and o.updated_at = e.storage_updated_at
       and coalesce(o.metadata->>'size', o.metadata->>'contentLength', '') ~ '^[0-9]+$'
       and coalesce(o.metadata->>'size', o.metadata->>'contentLength')::numeric
         = e.storage_metadata_size::numeric
      where e.generation_id = p_generation_id
        and e.object_key = required.name
        and e.sha256 = required.sha256
        and e.purpose = required.purpose
        and e.bytes = e.storage_metadata_size
    )
  ) then
    raise exception using errcode = '23514',
      message = 'private generation manifest lacks an exact immutable evidence attestation';
  end if;

  with supplied as (
    select *
    from jsonb_to_recordset(p_range_manifests) as x(
      range_start bigint,
      range_end bigint,
      rows_received integer,
      rows_accepted integer,
      rows_rejected integer,
      rejected_missing_folio integer,
      rejected_bad_folio_format integer,
      rejected_missing_centroid integer,
      rejected_out_of_bounds_centroid integer,
      duplicates_within_or_across_ranges integer,
      manifest_object_key text,
      manifest_sha256 text
    )
  )
  select count(*) into range_count from supplied;
  if range_count <> g.expected_range_count then
    raise exception using errcode = '23514', message = 'range manifest count mismatch';
  end if;

  if exists (
    with supplied as (
      select *
      from jsonb_to_recordset(p_range_manifests) as x(
        range_start bigint,
        range_end bigint,
        manifest_object_key text,
        manifest_sha256 text
      )
    )
    select 1 from supplied s
    where s.manifest_sha256 !~ '^[0-9a-f]{64}$'
       or s.manifest_object_key !~ (
         '^broward-parcel-generations/' || p_generation_id::text || '/'
       )
       or not exists (
         select 1
         from public.broward_parcel_evidence_objects e
         join storage.objects o
           on o.id = e.storage_object_id
          and o.bucket_id = 'fl-signal-source-evidence'
          and o.name = e.object_key
          and o.updated_at = e.storage_updated_at
          and coalesce(o.metadata->>'size', o.metadata->>'contentLength', '') ~ '^[0-9]+$'
          and coalesce(o.metadata->>'size', o.metadata->>'contentLength')::numeric
            = e.storage_metadata_size::numeric
         where e.generation_id = p_generation_id
           and e.object_key = s.manifest_object_key
           and e.sha256 = s.manifest_sha256
           and e.purpose = 'range_manifest'
           and e.bytes = e.storage_metadata_size
       )
  ) then
    raise exception using errcode = '23514', message = 'range manifest evidence is invalid or absent';
  end if;

  select count(*), coalesce(sum(row_count), 0),
         count(*) filter (where page_index <> expected_index)
    into page_count, page_row_sum, missing_page_count
  from (
    select page_index, row_count,
           row_number() over (order by page_index) - 1 as expected_index
    from public.broward_parcel_generation_pages
    where generation_id = p_generation_id
  ) pages;
  select count(*) into raw_count
  from public.broward_parcel_generation_observations
  where generation_id = p_generation_id;
  if page_count = 0
     or missing_page_count <> 0
     or page_row_sum <> raw_count
     or raw_count <> g.source_reported_count then
    raise exception using errcode = '23514',
      message = 'parcel page and source observation counts do not reconcile';
  end if;

  select count(*) into missing_page_count
  from public.broward_parcel_generation_pages p
  where p.generation_id = p_generation_id
    and (
      p.row_count <> (
        select count(*)
        from public.broward_parcel_generation_observations o
        where o.generation_id = p.generation_id and o.page_index = p.page_index
      )
      or p.system_object_id_min <> (
        select min(o.system_object_id)
        from public.broward_parcel_generation_observations o
        where o.generation_id = p.generation_id and o.page_index = p.page_index
      )
      or p.system_object_id_max <> (
        select max(o.system_object_id)
        from public.broward_parcel_generation_observations o
        where o.generation_id = p.generation_id and o.page_index = p.page_index
      )
    );
  if missing_page_count <> 0 then
    raise exception using errcode = '23514', message = 'parcel page identity bounds mismatch';
  end if;

  delete from public.broward_parcel_geography_stage
  where generation_id = p_generation_id;

  with classified as materialized (
    select
      o.*,
      public.fs_normalize_folio(o.raw_folio) as normalized_raw_folio,
      public.fs_normalize_folio(o.folio_number_raw) as normalized_folio_number,
      case
        when nullif(btrim(o.raw_folio), '') is null
         and nullif(btrim(o.folio_number_raw), '') is null
          then 'missing_folio'
        when (
          (nullif(btrim(o.raw_folio), '') is not null
            and public.fs_normalize_folio(o.raw_folio) is null)
          or (nullif(btrim(o.folio_number_raw), '') is not null
            and public.fs_normalize_folio(o.folio_number_raw) is null)
          or (
            public.fs_normalize_folio(o.raw_folio) is not null
            and public.fs_normalize_folio(o.folio_number_raw) is not null
            and public.fs_normalize_folio(o.raw_folio)
              <> public.fs_normalize_folio(o.folio_number_raw)
          )
        ) then 'bad_folio_format'
        when o.longitude is null or o.latitude is null then 'missing_centroid'
        when o.longitude not between c.coverage_longitude_min and c.coverage_longitude_max
          or o.latitude not between c.coverage_latitude_min and c.coverage_latitude_max
          then 'out_of_bounds_centroid'
        else null
      end as rejection_reason
    from public.broward_parcel_generation_observations o
    where o.generation_id = p_generation_id
  ), valid_ranked as materialized (
    select
      classified.*,
      coalesce(normalized_raw_folio, normalized_folio_number) as normalized_folio,
      row_number() over (
        partition by coalesce(normalized_raw_folio, normalized_folio_number)
        order by source_object_id, system_object_id
      ) as winner_rank
    from classified
    where rejection_reason is null
  )
  insert into public.broward_parcel_geography_stage (
    generation_id,
    parcel_id_normalized,
    parcel_id_raw,
    folio_number_raw,
    latitude,
    longitude,
    address,
    municipality,
    property_type,
    source_object_id,
    source_attributes_json,
    fetched_at,
    situs_city,
    situs_zip,
    sale_1_cin,
    sale_1_deed_type,
    sale_1_date,
    sale_1_stamp_amount
  )
  select
    p_generation_id,
    normalized_folio,
    coalesce(nullif(btrim(raw_folio), ''), folio_number_raw),
    folio_number_raw,
    latitude,
    longitude,
    situs_address,
    municipality,
    coalesce(use_type, parcel_type, use_code),
    source_object_id,
    source_attributes_json,
    observed_at,
    situs_city,
    situs_zip_code,
    sale1_cin,
    deed_type_1,
    sale_date_1,
    stamp_amount_1
  from valid_ranked
  where winner_rank = 1
  order by normalized_folio;

  with classified as materialized (
    select
      o.*,
      public.fs_normalize_folio(o.raw_folio) as normalized_raw_folio,
      public.fs_normalize_folio(o.folio_number_raw) as normalized_folio_number,
      case
        when nullif(btrim(o.raw_folio), '') is null
         and nullif(btrim(o.folio_number_raw), '') is null
          then 'missing_folio'
        when (
          (nullif(btrim(o.raw_folio), '') is not null
            and public.fs_normalize_folio(o.raw_folio) is null)
          or (nullif(btrim(o.folio_number_raw), '') is not null
            and public.fs_normalize_folio(o.folio_number_raw) is null)
          or (
            public.fs_normalize_folio(o.raw_folio) is not null
            and public.fs_normalize_folio(o.folio_number_raw) is not null
            and public.fs_normalize_folio(o.raw_folio)
              <> public.fs_normalize_folio(o.folio_number_raw)
          )
        ) then 'bad_folio_format'
        when o.longitude is null or o.latitude is null then 'missing_centroid'
        when o.longitude not between c.coverage_longitude_min and c.coverage_longitude_max
          or o.latitude not between c.coverage_latitude_min and c.coverage_latitude_max
          then 'out_of_bounds_centroid'
        else null
      end as rejection_reason
    from public.broward_parcel_generation_observations o
    where o.generation_id = p_generation_id
  ), valid_ranked as materialized (
    select
      classified.*,
      row_number() over (
        partition by coalesce(normalized_raw_folio, normalized_folio_number)
        order by source_object_id, system_object_id
      ) as winner_rank
    from classified
    where rejection_reason is null
  )
  select
    count(*) filter (where rejection_reason is not null),
    count(*) filter (where rejection_reason = 'missing_folio'),
    count(*) filter (where rejection_reason = 'bad_folio_format'),
    count(*) filter (where rejection_reason = 'missing_centroid'),
    count(*) filter (where rejection_reason = 'out_of_bounds_centroid')
  into
    rejected_count,
    missing_folio_count,
    bad_folio_count,
    missing_centroid_count,
    out_of_bounds_count
  from classified;

  select count(*) into accepted_count
  from public.broward_parcel_geography_stage
  where generation_id = p_generation_id;
  duplicate_count := raw_count - rejected_count - accepted_count;

  if raw_count <> accepted_count + rejected_count + duplicate_count
     or accepted_count < c.minimum_accepted_rows
     or rejected_count > c.maximum_rejected_rows
     or duplicate_count > c.maximum_duplicate_rows then
    raise exception using errcode = '23514', message = 'parcel generation failed fixed quality gate';
  end if;

  -- Attribute every loser to the stable OBJECTID range that supplied that raw
  -- row. This makes cross-range duplicate accounting global and invariant.
  with classified as materialized (
    select
      o.*,
      public.fs_normalize_folio(o.raw_folio) as normalized_raw_folio,
      public.fs_normalize_folio(o.folio_number_raw) as normalized_folio_number,
      case
        when nullif(btrim(o.raw_folio), '') is null
         and nullif(btrim(o.folio_number_raw), '') is null then 'missing_folio'
        when (
          (nullif(btrim(o.raw_folio), '') is not null
            and public.fs_normalize_folio(o.raw_folio) is null)
          or (nullif(btrim(o.folio_number_raw), '') is not null
            and public.fs_normalize_folio(o.folio_number_raw) is null)
          or (
            public.fs_normalize_folio(o.raw_folio) is not null
            and public.fs_normalize_folio(o.folio_number_raw) is not null
            and public.fs_normalize_folio(o.raw_folio)
              <> public.fs_normalize_folio(o.folio_number_raw)
          )
        ) then 'bad_folio_format'
        when o.longitude is null or o.latitude is null then 'missing_centroid'
        when o.longitude not between c.coverage_longitude_min and c.coverage_longitude_max
          or o.latitude not between c.coverage_latitude_min and c.coverage_latitude_max
          then 'out_of_bounds_centroid'
        else null
      end as rejection_reason
    from public.broward_parcel_generation_observations o
    where o.generation_id = p_generation_id
  ), valid_ranked as materialized (
    select
      source_object_id,
      row_number() over (
        partition by coalesce(normalized_raw_folio, normalized_folio_number)
        order by source_object_id, system_object_id
      ) as winner_rank
    from classified
    where rejection_reason is null
  ), classified_with_rank as (
    select c0.*, v.winner_rank
    from classified c0
    left join valid_ranked v using (source_object_id)
  ), summaries as (
    select
      r.range_id,
      count(o.source_object_id) as rows_received,
      count(*) filter (where o.rejection_reason is null and o.winner_rank = 1) as rows_accepted,
      count(*) filter (where o.rejection_reason is not null) as rows_rejected,
      count(*) filter (where o.rejection_reason = 'missing_folio') as rejected_missing_folio,
      count(*) filter (where o.rejection_reason = 'bad_folio_format') as rejected_bad_folio_format,
      count(*) filter (where o.rejection_reason = 'missing_centroid') as rejected_missing_centroid,
      count(*) filter (where o.rejection_reason = 'out_of_bounds_centroid') as rejected_out_of_bounds,
      count(*) filter (where o.rejection_reason is null and o.winner_rank > 1) as duplicate_folios
    from public.broward_parcel_generation_ranges r
    left join classified_with_rank o
      on o.source_object_id between r.oid_min and r.oid_max
    where r.generation_id = p_generation_id
    group by r.range_id
  ), supplied as (
    select *
    from jsonb_to_recordset(p_range_manifests) as x(
      range_start bigint,
      range_end bigint,
      rows_received integer,
      rows_accepted integer,
      rows_rejected integer,
      rejected_missing_folio integer,
      rejected_bad_folio_format integer,
      rejected_missing_centroid integer,
      rejected_out_of_bounds_centroid integer,
      duplicates_within_or_across_ranges integer,
      manifest_object_key text,
      manifest_sha256 text
    )
  )
  update public.broward_parcel_generation_ranges r
  set
    rows_received = s.rows_received,
    rows_accepted = s.rows_accepted,
    rows_rejected = s.rows_rejected,
    rejected_missing_folio = s.rejected_missing_folio,
    rejected_bad_folio_format = s.rejected_bad_folio_format,
    rejected_missing_centroid = s.rejected_missing_centroid,
    rejected_out_of_bounds = s.rejected_out_of_bounds,
    duplicate_folios = s.duplicate_folios,
    status = 'complete',
    attempts = 1,
    raw_manifest_sha256 = supplied.manifest_sha256,
    raw_manifest_object_key = supplied.manifest_object_key,
    started_at = g.started_at,
    completed_at = now()
  from summaries s, supplied
  where r.range_id = s.range_id
    and supplied.range_start = r.oid_min
    and supplied.range_end = r.oid_max
    and supplied.rows_received = s.rows_received
    and supplied.rows_accepted = s.rows_accepted
    and supplied.rows_rejected = s.rows_rejected
    and supplied.rejected_missing_folio = s.rejected_missing_folio
    and supplied.rejected_bad_folio_format = s.rejected_bad_folio_format
    and supplied.rejected_missing_centroid = s.rejected_missing_centroid
    and supplied.rejected_out_of_bounds_centroid = s.rejected_out_of_bounds
    and supplied.duplicates_within_or_across_ranges = s.duplicate_folios;

  get diagnostics range_count = row_count;
  if range_count <> g.expected_range_count then
    raise exception using errcode = '23514',
      message = 'range manifests do not match database-derived accounting';
  end if;

  select count(*) into bad_range_count
  from public.broward_parcel_generation_observations o
  where o.generation_id = p_generation_id
    and not exists (
      select 1
      from public.broward_parcel_generation_ranges r
      where r.generation_id = o.generation_id
        and o.source_object_id between r.oid_min and r.oid_max
    );
  if bad_range_count <> 0 then
    raise exception using errcode = '23514', message = 'observations escaped stable OBJECTID ranges';
  end if;

  select encode(
    extensions.digest(
      pg_catalog.convert_to(coalesce(string_agg(source_object_id::text || E'\n', ''
        order by source_object_id), ''), 'UTF8'
      ),
      'sha256'
    ),
    'hex'
  ) into observed_source_object_hash
  from public.broward_parcel_generation_observations
  where generation_id = p_generation_id;
  if observed_source_object_hash <> p_source_object_id_set_sha256 then
    raise exception using errcode = '23514', message = 'source OBJECTID set hash mismatch';
  end if;

  select encode(
    extensions.digest(
      pg_catalog.convert_to(coalesce(string_agg(system_object_id::text || E'\n', ''
        order by system_object_id), ''), 'UTF8'
      ),
      'sha256'
    ),
    'hex'
  ) into observed_system_object_hash
  from public.broward_parcel_generation_observations
  where generation_id = p_generation_id;
  if observed_system_object_hash <> p_system_object_id_set_sha256 then
    raise exception using errcode = '23514', message = 'system OBJECTID set hash mismatch';
  end if;

  -- This digest is database-owned. It is recomputed from the exact persisted
  -- observations and never accepted from the collector or Storage manifest.
  select encode(
    extensions.digest(
      pg_catalog.convert_to(coalesce(string_agg(
        encode(extensions.digest(pg_catalog.convert_to(
          jsonb_build_object(
            'attributes', source_attributes_json,
            'deed_type_1', deed_type_1,
            'folio_number_raw', folio_number_raw,
            'latitude', latitude,
            'longitude', longitude,
            'municipality', municipality,
            'parcel_type', parcel_type,
            'raw_folio', raw_folio,
            'sale1_cin', sale1_cin,
            'sale_date_1', sale_date_1,
            'situs_address', situs_address,
            'situs_city', situs_city,
            'situs_zip_code', situs_zip_code,
            'source_object_id', source_object_id,
            'stamp_amount_1', stamp_amount_1,
            'system_object_id', system_object_id,
            'use_code', use_code,
            'use_type', use_type
          )::text,
          'UTF8'
        ), 'sha256'), 'hex') || E'\n', '' order by source_object_id), ''), 'UTF8'
      ),
      'sha256'
    ),
    'hex'
  ) into observed_source_content_hash
  from public.broward_parcel_generation_observations
  where generation_id = p_generation_id;

  select encode(
    extensions.digest(
      pg_catalog.convert_to(coalesce(string_agg(parcel_id_normalized || E'\n', ''
        order by parcel_id_normalized), ''), 'UTF8'
      ),
      'sha256'
    ),
    'hex'
  ) into observed_folio_hash
  from public.broward_parcel_geography_stage
  where generation_id = p_generation_id;

  terminal_status := case when g.run_mode = 'canary'
    then 'canary_complete' else 'ready' end;
  update public.broward_parcel_import_generations
  set
    rows_received = raw_count,
    rows_accepted = accepted_count,
    rows_rejected = rejected_count,
    rejected_missing_folio = missing_folio_count,
    rejected_bad_folio_format = bad_folio_count,
    rejected_missing_centroid = missing_centroid_count,
    rejected_out_of_bounds = out_of_bounds_count,
    duplicate_folios = duplicate_count,
    source_content_sha256 = observed_source_content_hash,
    source_object_id_set_sha256 = observed_source_object_hash,
    system_object_id_set_sha256 = observed_system_object_hash,
    folio_set_sha256 = observed_folio_hash,
    rejection_manifest_sha256 = p_rejection_manifest_sha256,
    rejection_manifest_object_key = p_rejection_manifest_key,
    duplicate_manifest_sha256 = p_duplicate_manifest_sha256,
    duplicate_manifest_object_key = p_duplicate_manifest_key,
    raw_manifest_sha256 = p_manifest_sha256,
    raw_manifest_object_key = p_manifest_key,
    source_observed_at = now(),
    completed_at = now(),
    status = terminal_status,
    promotion_eligible = (g.run_mode = 'current_generation' and c.promotion_allowed)
  where generation_id = p_generation_id and status = 'staging';
  if not found then
    raise exception using errcode = '55000', message = 'generation state changed during finalization';
  end if;

  return jsonb_build_object(
    'duplicate_rows', duplicate_count,
    'folio_set_sha256', observed_folio_hash,
    'generation_id', p_generation_id,
    'promotion_eligible', (g.run_mode = 'current_generation' and c.promotion_allowed),
    'rejected_rows', rejected_count,
    'rows_accepted', accepted_count,
    'rows_received', raw_count,
    'source_content_sha256', observed_source_content_hash,
    'source_object_id_set_sha256', observed_source_object_hash,
    'status', terminal_status,
    'system_object_id_set_sha256', observed_system_object_hash
  );
end
$$;

create or replace function public.fs_fail_broward_parcel_generation(
  p_generation_id uuid,
  p_failure_receipt jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  receipt_sha text;
  receipt_key text;
  receipt_bytes bigint;
  reason text;
  old_status text;
  stored_object_id uuid;
  stored_created_at timestamptz;
  stored_updated_at timestamptz;
  stored_bytes bigint;
  expected_object_id uuid;
  expected_updated_at timestamptz;
  expected_storage_bytes bigint;
begin
  if p_generation_id is null or jsonb_typeof(p_failure_receipt) <> 'object' then
    raise exception using errcode = '22023', message = 'invalid parcel failure receipt';
  end if;
  receipt_sha := p_failure_receipt->>'failure_object_sha256';
  receipt_key := p_failure_receipt->>'failure_object_key';
  if coalesce(p_failure_receipt->>'failure_object_bytes', '') !~ '^[0-9]+$' then
    raise exception using errcode = '22023', message = 'failure receipt byte count is invalid';
  end if;
  receipt_bytes := (p_failure_receipt->>'failure_object_bytes')::bigint;
  if coalesce(p_failure_receipt->>'storage_object_id', '')
       !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
     or nullif(p_failure_receipt->>'storage_updated_at', '') is null
     or coalesce(p_failure_receipt->>'storage_metadata_size', '') !~ '^[0-9]+$' then
    raise exception using errcode = '22023',
      message = 'failure receipt Storage version fence is invalid';
  end if;
  expected_object_id := (p_failure_receipt->>'storage_object_id')::uuid;
  expected_updated_at := (p_failure_receipt->>'storage_updated_at')::timestamptz;
  expected_storage_bytes := (p_failure_receipt->>'storage_metadata_size')::bigint;
  reason := left(coalesce(p_failure_receipt->>'error_message', 'collector failed'), 2000);
  if receipt_sha !~ '^[0-9a-f]{64}$'
     or receipt_key !~ ('^broward-parcel-generations/' || p_generation_id::text || '/')
     or p_failure_receipt->>'verification_method'
       is distinct from 'private_storage_roundtrip_sha256_v1' then
    raise exception using errcode = '23514', message = 'private failure receipt is absent';
  end if;

  select
    o.id,
    o.created_at,
    o.updated_at,
    coalesce(o.metadata->>'size', o.metadata->>'contentLength')::bigint
    into stored_object_id, stored_created_at, stored_updated_at, stored_bytes
  from storage.objects o
  join storage.buckets b on b.id = o.bucket_id
  where o.bucket_id = 'fl-signal-source-evidence'
    and o.name = receipt_key
    and o.id = expected_object_id
    and o.updated_at = expected_updated_at
    and b.public = false
    and coalesce(o.metadata->>'size', o.metadata->>'contentLength', '') ~ '^[0-9]+$';
  if not found
     or stored_bytes is distinct from receipt_bytes
     or stored_bytes is distinct from expected_storage_bytes then
    raise exception using errcode = '23514',
      message = 'private failure receipt Storage identity or size is unverified';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtext('florida-signal:broward-parcel:' || p_generation_id::text)
  );
  select status into old_status
  from public.broward_parcel_import_generations
  where generation_id = p_generation_id
  for update;
  if old_status = 'failed' then
    if exists (
      select 1
      from public.broward_parcel_import_generations g
      join public.broward_parcel_evidence_objects e
        on e.generation_id = g.generation_id
      where g.generation_id = p_generation_id
        and g.raw_manifest_object_key = receipt_key
        and g.raw_manifest_sha256 = receipt_sha
        and e.object_key = receipt_key
        and e.purpose = 'failure_receipt'
        and e.sha256 = receipt_sha
        and e.bytes = receipt_bytes
        and e.storage_object_id = stored_object_id
        and e.storage_updated_at = stored_updated_at
    ) then
      return jsonb_build_object('generation_id', p_generation_id, 'status', 'replayed');
    end if;
    raise exception using errcode = '23505',
      message = 'failure receipt replay changed immutable evidence';
  end if;
  if old_status is distinct from 'staging' then
    raise exception using errcode = '55000', message = 'only a staging generation can fail';
  end if;

  insert into public.broward_parcel_evidence_objects (
    generation_id, object_key, purpose, sha256, bytes, storage_object_id,
    storage_created_at, storage_updated_at, storage_metadata_size,
    verification_method
  ) values (
    p_generation_id, receipt_key, 'failure_receipt', receipt_sha, receipt_bytes,
    stored_object_id, stored_created_at, stored_updated_at, stored_bytes,
    'private_storage_roundtrip_sha256_v1'
  ) on conflict (generation_id, object_key) do nothing;
  if not exists (
    select 1
    from public.broward_parcel_evidence_objects e
    where e.generation_id = p_generation_id
      and e.object_key = receipt_key
      and e.purpose = 'failure_receipt'
      and e.sha256 = receipt_sha
      and e.bytes = receipt_bytes
      and e.storage_object_id = stored_object_id
      and e.storage_updated_at = stored_updated_at
  ) then
    raise exception using errcode = '23505',
      message = 'failure receipt replay changed immutable evidence';
  end if;

  update public.broward_parcel_import_generations
  set
    status = 'failed',
    failure_reason = reason,
    raw_manifest_sha256 = receipt_sha,
    raw_manifest_object_key = receipt_key,
    source_observed_at = now(),
    completed_at = now(),
    promotion_eligible = false
  where generation_id = p_generation_id;
  return jsonb_build_object('generation_id', p_generation_id, 'status', 'failed');
end
$$;

revoke all on function public.fs_finalize_broward_parcel_generation(
  uuid, text, text, text, text, text, text, text, text, jsonb
) from public, anon, authenticated;
grant execute on function public.fs_finalize_broward_parcel_generation(
  uuid, text, text, text, text, text, text, text, text, jsonb
) to service_role;
revoke all on function public.fs_fail_broward_parcel_generation(uuid, jsonb)
  from public, anon, authenticated;
grant execute on function public.fs_fail_broward_parcel_generation(uuid, jsonb)
  to service_role;

-- ---------------------------------------------------------------------------
-- Owner-only preview, backup authorization, and atomic promotion wrapper
-- ---------------------------------------------------------------------------

create table public.broward_parcel_promotion_previews (
  generation_id uuid primary key
    references public.broward_parcel_import_generations(generation_id) on delete restrict,
  live_rows_before bigint not null check (live_rows_before >= 0),
  generation_rows bigint not null check (generation_rows >= 0),
  rows_added bigint not null check (rows_added >= 0),
  rows_removed bigint not null check (rows_removed >= 0),
  rows_changed bigint not null check (rows_changed >= 0),
  rows_unchanged bigint not null check (rows_unchanged >= 0),
  prior_folio_set_sha256 text not null check (prior_folio_set_sha256 ~ '^[0-9a-f]{64}$'),
  generation_folio_set_sha256 text not null
    check (generation_folio_set_sha256 ~ '^[0-9a-f]{64}$'),
  preview_sha256 text not null unique check (preview_sha256 ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now(),
  constraint broward_parcel_preview_partition check (
    generation_rows = rows_added + rows_changed + rows_unchanged
    and live_rows_before = rows_removed + rows_changed + rows_unchanged
  )
);

create table public.broward_parcel_promotion_authorizations (
  generation_id uuid primary key
    references public.broward_parcel_promotion_previews(generation_id) on delete restrict,
  preview_sha256 text not null check (preview_sha256 ~ '^[0-9a-f]{64}$'),
  backup_object_key text not null check (
    btrim(backup_object_key) <> ''
    and position('?' in backup_object_key) = 0
    and position(E'\n' in backup_object_key) = 0
  ),
  backup_sha256 text not null check (backup_sha256 ~ '^[0-9a-f]{64}$'),
  backup_bytes bigint not null check (backup_bytes > 0),
  backup_storage_object_id uuid not null unique,
  backup_storage_updated_at timestamptz not null,
  backup_verification_method text not null check (
    backup_verification_method = 'owner_private_storage_download_sha256_v1'
  ),
  approval_scope text not null
    check (approval_scope = 'current_generation_only_no_historical_backfill'),
  approved_at timestamptz not null default now(),
  approved_by text not null default current_user check (btrim(approved_by) <> ''),
  constraint broward_parcel_backup_key_binds_generation_and_hash check (
    backup_object_key like (
      'broward-parcel-backups/' || generation_id::text || '/%'
    )
    and position(backup_sha256 in backup_object_key) > 0
  )
);

alter table public.broward_parcel_promotion_previews enable row level security;
alter table public.broward_parcel_promotion_previews force row level security;
alter table public.broward_parcel_promotion_authorizations enable row level security;
alter table public.broward_parcel_promotion_authorizations force row level security;
revoke all on table public.broward_parcel_promotion_previews
  from public, anon, authenticated, service_role;
revoke all on table public.broward_parcel_promotion_authorizations
  from public, anon, authenticated, service_role;

create trigger broward_parcel_previews_no_row_mutation
  before update or delete on public.broward_parcel_promotion_previews
  for each row execute function public.fs_reject_broward_parcel_observation_mutation();
create trigger broward_parcel_previews_no_truncate
  before truncate on public.broward_parcel_promotion_previews
  for each statement execute function public.fs_reject_broward_parcel_observation_mutation();
create trigger broward_parcel_authorizations_no_row_mutation
  before update or delete on public.broward_parcel_promotion_authorizations
  for each row execute function public.fs_reject_broward_parcel_observation_mutation();
create trigger broward_parcel_authorizations_no_truncate
  before truncate on public.broward_parcel_promotion_authorizations
  for each statement execute function public.fs_reject_broward_parcel_observation_mutation();

create or replace function public.fs_preview_broward_parcel_generation(
  p_generation_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  g public.broward_parcel_import_generations%rowtype;
  live_rows_before bigint;
  generation_rows bigint;
  rows_added bigint;
  rows_removed bigint;
  rows_changed bigint;
  rows_unchanged bigint;
  prior_hash text;
  preview_hash text;
  preview_body jsonb;
  existing public.broward_parcel_promotion_previews%rowtype;
begin
  -- Freeze the exact live state whose add/remove/change effect is being
  -- previewed. Use the foundation's advisory/table order so a preview cannot
  -- race a promotion or form the reverse half of a lock cycle.
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtext('florida-signal:property-transfer-refresh')
  );
  lock table public.broward_parcel_generation_ranges in share mode;
  lock table public.broward_parcel_geography_stage in share mode;
  lock table public.broward_parcel_geography in share mode;

  select * into g
  from public.broward_parcel_import_generations
  where generation_id = p_generation_id
  for update;
  if not found then
    raise exception using errcode = 'P0002', message = 'parcel generation not found';
  end if;
  if g.status <> 'ready'
     or g.generation_protocol <> 'single_stream_v1'
     or g.run_mode <> 'current_generation'
     or not g.promotion_eligible then
    raise exception using errcode = '55000', message = 'generation is not preview eligible';
  end if;

  select count(*) into live_rows_before from public.broward_parcel_geography;
  select count(*) into generation_rows
  from public.broward_parcel_geography_stage where generation_id = p_generation_id;
  select count(*) into rows_added
  from public.broward_parcel_geography_stage s
  left join public.broward_parcel_geography l
    on l.parcel_id_normalized = s.parcel_id_normalized
  where s.generation_id = p_generation_id and l.parcel_id_normalized is null;
  select count(*) into rows_removed
  from public.broward_parcel_geography l
  left join public.broward_parcel_geography_stage s
    on s.generation_id = p_generation_id
   and s.parcel_id_normalized = l.parcel_id_normalized
  where s.parcel_id_normalized is null;
  select count(*) into rows_changed
  from public.broward_parcel_geography_stage s
  join public.broward_parcel_geography l
    on l.parcel_id_normalized = s.parcel_id_normalized
  where s.generation_id = p_generation_id
    and row(
      s.parcel_id_raw, s.folio_number_raw, s.latitude, s.longitude, s.address,
      s.municipality, s.property_type, s.geometry_source, s.source_object_id,
      s.location_precision, s.active_or_historical, s.source_attributes_json,
      s.situs_city, s.situs_zip, s.sale_1_cin, s.sale_1_deed_type,
      s.sale_1_date, s.sale_1_stamp_amount
    ) is distinct from row(
      l.parcel_id_raw, l.folio_number_raw, l.latitude, l.longitude, l.address,
      l.municipality, l.property_type, l.geometry_source, l.source_object_id,
      l.location_precision, l.active_or_historical, l.source_attributes_json,
      l.situs_city, l.situs_zip, l.sale_1_cin, l.sale_1_deed_type,
      l.sale_1_date, l.sale_1_stamp_amount
    );
  rows_unchanged := generation_rows - rows_added - rows_changed;

  select encode(
    extensions.digest(
      pg_catalog.convert_to(coalesce(string_agg(parcel_id_normalized || E'\n', ''
        order by parcel_id_normalized), ''), 'UTF8'
      ),
      'sha256'
    ),
    'hex'
  ) into prior_hash
  from public.broward_parcel_geography;

  preview_body := jsonb_build_object(
    'generation_folio_set_sha256', g.folio_set_sha256,
    'generation_id', p_generation_id,
    'generation_rows', generation_rows,
    'live_rows_before', live_rows_before,
    'prior_folio_set_sha256', prior_hash,
    'rows_added', rows_added,
    'rows_changed', rows_changed,
    'rows_removed', rows_removed,
    'rows_unchanged', rows_unchanged,
    'schema_version', 'FloridaSignalBrowardParcelPromotionPreviewV1'
  );
  preview_hash := encode(
    extensions.digest(pg_catalog.convert_to(preview_body::text, 'UTF8'), 'sha256'), 'hex'
  );

  select * into existing
  from public.broward_parcel_promotion_previews
  where generation_id = p_generation_id;
  if found then
    if existing.preview_sha256 = preview_hash then
      return preview_body || jsonb_build_object(
        'preview_sha256', preview_hash, 'status', 'replayed'
      );
    end if;
    raise exception using errcode = '23505', message = 'stored parcel preview differs';
  end if;

  insert into public.broward_parcel_promotion_previews (
    generation_id, live_rows_before, generation_rows, rows_added, rows_removed,
    rows_changed, rows_unchanged, prior_folio_set_sha256,
    generation_folio_set_sha256, preview_sha256
  ) values (
    p_generation_id, live_rows_before, generation_rows, rows_added, rows_removed,
    rows_changed, rows_unchanged, prior_hash, g.folio_set_sha256, preview_hash
  );
  return preview_body || jsonb_build_object(
    'preview_sha256', preview_hash,
    'status', 'previewed_not_authorized'
  );
end
$$;

revoke all on function public.fs_preview_broward_parcel_generation(uuid)
  from public, anon, authenticated, service_role;

-- Keep the already-reviewed atomic foundation intact behind a stricter
-- current-generation preview/backup wrapper.
alter function public.fs_promote_broward_parcel_generation(uuid)
  rename to fs_promote_broward_parcel_generation_foundation;
revoke all on function public.fs_promote_broward_parcel_generation_foundation(uuid)
  from public, anon, authenticated, service_role;

create function public.fs_promote_broward_parcel_generation(
  p_generation_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  g public.broward_parcel_import_generations%rowtype;
  p public.broward_parcel_promotion_previews%rowtype;
  a public.broward_parcel_promotion_authorizations%rowtype;
  current_live_rows bigint;
  current_rows_added bigint;
  current_rows_removed bigint;
  current_rows_changed bigint;
  current_rows_unchanged bigint;
  current_prior_hash text;
begin
  -- Acquire the foundation fence and table locks before the parent receipt.
  -- Re-acquisition inside the foundation function is transaction-local and
  -- safe; this closes the preview-to-promotion TOCTOU window.
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtext('florida-signal:property-transfer-refresh')
  );
  lock table public.broward_parcel_generation_ranges in share mode;
  lock table public.broward_parcel_geography_stage in share mode;
  lock table public.broward_parcel_geography in access exclusive mode;

  select * into g
  from public.broward_parcel_import_generations
  where generation_id = p_generation_id
  for update;
  if not found then
    raise exception using errcode = 'P0002', message = 'parcel generation not found';
  end if;
  if g.run_mode <> 'current_generation'
     or g.generation_protocol <> 'single_stream_v1'
     or g.status not in ('ready', 'promoted')
     or not g.promotion_eligible then
    raise exception using errcode = '55000',
      message = 'only a reviewed current generation may promote';
  end if;

  select * into p
  from public.broward_parcel_promotion_previews
  where generation_id = p_generation_id;
  if not found
     or p.generation_rows <> g.rows_accepted
     or p.generation_folio_set_sha256 <> g.folio_set_sha256 then
    raise exception using errcode = '23514', message = 'promotion preview is absent or stale';
  end if;

  select * into a
  from public.broward_parcel_promotion_authorizations
  where generation_id = p_generation_id;
  if not found
     or a.preview_sha256 <> p.preview_sha256
     or a.backup_sha256 !~ '^[0-9a-f]{64}$'
     or a.backup_bytes <= 0
     or a.backup_verification_method
       <> 'owner_private_storage_download_sha256_v1'
     or a.approval_scope <> 'current_generation_only_no_historical_backfill'
     or not exists (
       select 1
       from storage.buckets b
       join storage.objects o on o.bucket_id = b.id
       where b.id = 'fl-signal-source-evidence'
         and b.public = false
         and o.name = a.backup_object_key
         and o.id = a.backup_storage_object_id
         and o.updated_at = a.backup_storage_updated_at
         and coalesce(o.metadata->>'size', o.metadata->>'contentLength', '') ~ '^[0-9]+$'
         and coalesce(o.metadata->>'size', o.metadata->>'contentLength')::numeric
           = a.backup_bytes::numeric
     ) then
    raise exception using errcode = '42501',
      message = 'exact preview-bound backup authorization is absent';
  end if;

  if g.status = 'ready' then
    select count(*) into current_live_rows
    from public.broward_parcel_geography;
    select count(*) into current_rows_added
    from public.broward_parcel_geography_stage s
    left join public.broward_parcel_geography l
      on l.parcel_id_normalized = s.parcel_id_normalized
    where s.generation_id = p_generation_id
      and l.parcel_id_normalized is null;
    select count(*) into current_rows_removed
    from public.broward_parcel_geography l
    left join public.broward_parcel_geography_stage s
      on s.generation_id = p_generation_id
     and s.parcel_id_normalized = l.parcel_id_normalized
    where s.parcel_id_normalized is null;
    select count(*) into current_rows_changed
    from public.broward_parcel_geography_stage s
    join public.broward_parcel_geography l
      on l.parcel_id_normalized = s.parcel_id_normalized
    where s.generation_id = p_generation_id
      and row(
        s.parcel_id_raw, s.folio_number_raw, s.latitude, s.longitude, s.address,
        s.municipality, s.property_type, s.geometry_source, s.source_object_id,
        s.location_precision, s.active_or_historical, s.source_attributes_json,
        s.situs_city, s.situs_zip, s.sale_1_cin, s.sale_1_deed_type,
        s.sale_1_date, s.sale_1_stamp_amount
      ) is distinct from row(
        l.parcel_id_raw, l.folio_number_raw, l.latitude, l.longitude, l.address,
        l.municipality, l.property_type, l.geometry_source, l.source_object_id,
        l.location_precision, l.active_or_historical, l.source_attributes_json,
        l.situs_city, l.situs_zip, l.sale_1_cin, l.sale_1_deed_type,
        l.sale_1_date, l.sale_1_stamp_amount
      );
    current_rows_unchanged := g.rows_accepted
      - current_rows_added - current_rows_changed;
    select encode(
      extensions.digest(
        pg_catalog.convert_to(coalesce(string_agg(parcel_id_normalized || E'\n', ''
          order by parcel_id_normalized), ''), 'UTF8'
        ),
        'sha256'
      ),
      'hex'
    ) into current_prior_hash
    from public.broward_parcel_geography;

    if current_live_rows is distinct from p.live_rows_before
       or current_rows_added is distinct from p.rows_added
       or current_rows_removed is distinct from p.rows_removed
       or current_rows_changed is distinct from p.rows_changed
       or current_rows_unchanged is distinct from p.rows_unchanged
       or current_prior_hash is distinct from p.prior_folio_set_sha256 then
      raise exception using errcode = '55000',
        message = 'live parcel state changed after preview; create a new reviewed generation';
    end if;
  end if;

  return public.fs_promote_broward_parcel_generation_foundation(p_generation_id);
end
$$;

comment on function public.fs_promote_broward_parcel_generation(uuid) is
  'Owner-only atomic current-generation promotion. Requires immutable preview plus exact backup-bound no-historical-backfill authorization, then invokes the reviewed foundation gate.';
revoke all on function public.fs_promote_broward_parcel_generation(uuid)
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Private Desk/alert hook. UNKNOWN/STALE/PARITY_MISMATCH are explicit states.
-- ---------------------------------------------------------------------------

create view public.broward_parcel_pipeline_health
with (security_invoker = true)
as
with latest as (
  select g.*
  from public.broward_parcel_import_generations g
  where g.generation_protocol = 'single_stream_v1'
    and g.run_mode = 'current_generation'
  order by g.created_at desc, g.generation_id desc
  limit 1
), promoted as (
  select g.*
  from public.broward_parcel_import_generations g
  where g.status = 'promoted'
  order by g.promoted_at desc, g.generation_id desc
  limit 1
), live as (
  select count(*)::bigint as live_rows,
         count(distinct import_generation_id)::bigint as live_generation_count,
         max(fetched_at) as latest_fetched_at
  from public.broward_parcel_geography
)
select
  latest.generation_id as latest_run_id,
  latest.run_mode as latest_run_mode,
  latest.status as latest_run_status,
  latest.completed_at as latest_run_completed_at,
  latest.rows_received as latest_rows_attempted,
  latest.rows_accepted as latest_rows_written,
  latest.rows_rejected as latest_rows_rejected,
  latest.duplicate_folios as latest_duplicate_rows,
  promoted.generation_id as promoted_generation_id,
  promoted.source_observed_at as promoted_source_observed_at,
  promoted.rows_accepted as promoted_rows,
  live.live_rows,
  live.live_generation_count,
  live.latest_fetched_at,
  case
    when latest.generation_id is null then 'UNKNOWN'
    when latest.status = 'failed' then 'FAILED'
    when latest.status = 'staging'
      and latest.started_at < now() - interval '6 hours' then 'STALLED'
    when latest.status = 'staging' then 'RUNNING'
    when latest.status = 'ready' then 'AWAITING_REVIEWED_PROMOTION'
    when promoted.generation_id is null then 'NOT_CONNECTED'
    when live.live_rows <> promoted.rows_accepted
      or live.live_generation_count <> 1 then 'PARITY_MISMATCH'
    when promoted.source_observed_at < now() - interval '45 days' then 'STALE'
    else 'CURRENT'
  end as alert_state,
  case
    when latest.generation_id is null then 'No single-stream Broward parcel run receipt exists.'
    when latest.status = 'failed' then coalesce(latest.failure_reason, 'Latest collector run failed.')
    when latest.status = 'staging'
      and latest.started_at < now() - interval '6 hours'
      then 'Latest collector generation has remained staging for more than 6 hours.'
    when latest.status = 'staging' then 'A current-generation collection is in progress.'
    when latest.status = 'ready' then 'A ready generation awaits preview, backup and owner approval.'
    when promoted.generation_id is null then 'No current-generation snapshot has been promoted.'
    when live.live_rows <> promoted.rows_accepted
      or live.live_generation_count <> 1 then 'Live row count/generation differs from promoted receipt.'
    when promoted.source_observed_at < now() - interval '45 days'
      then 'Promoted parcel source observation is older than 45 days.'
    else null
  end as alert_detail
from (select 1) anchor
left join latest on true
left join promoted on true
cross join live;

create view public.broward_parcel_pipeline_alerts
with (security_invoker = true)
as
select *
from public.broward_parcel_pipeline_health
where alert_state not in ('CURRENT', 'RUNNING');

revoke all on table public.broward_parcel_pipeline_health
  from public, anon, authenticated, service_role;
revoke all on table public.broward_parcel_pipeline_alerts
  from public, anon, authenticated, service_role;
grant select on table public.broward_parcel_pipeline_health to service_role;
grant select on table public.broward_parcel_pipeline_alerts to service_role;
grant select on table public.broward_parcel_import_generations to service_role;
grant select on table public.broward_parcel_geography to service_role;

commit;

-- Deliberately absent: cron.schedule, historical date/range parameters, direct
-- live-table writes by a collector, service-role promotion, signal scoring,
-- publishing, or deletion of prior source evidence.
