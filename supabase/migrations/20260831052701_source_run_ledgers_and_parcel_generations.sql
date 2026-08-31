-- Durable FDEP/FAA source-run receipts and generation-safe Broward parcel promotion.
-- CODE ONLY: applying this migration, changing an Edge function, granting parcel-loader
-- access, or invoking the promotion function each require separate production approval.
--
-- Export-first prerequisite: the deployed fdep-erp-sync, faa-oeaaa-sync and
-- broward-parcel-sync Edge sources/configuration are not tracked in this repository.
-- Export and hash those exact deployed sources before adapting a collector to these
-- contracts. This migration deliberately creates no Edge source, schedule, or cron job.

-- ---------------------------------------------------------------------------
-- FDEP + FAA terminal run receipts
-- ---------------------------------------------------------------------------

create table if not exists public.external_source_run_receipts (
  id bigint generated always as identity primary key,
  run_id uuid not null unique,
  source_id text not null
    check (source_id in ('fdep_erp', 'faa_oeaaa')),
  collector_name text not null check (btrim(collector_name) <> ''),
  collector_version text not null check (btrim(collector_version) <> ''),
  parser_version text not null check (btrim(parser_version) <> ''),
  normalizer_version text not null check (btrim(normalizer_version) <> ''),
  status text not null
    check (status in ('ok', 'empty', 'source_wait', 'partial', 'failed')),
  reason_code text,
  reason_detail text,
  started_at timestamptz not null,
  observed_at timestamptz not null,
  completed_at timestamptz not null,
  attempted_event_from timestamptz,
  attempted_event_through timestamptz,
  event_through timestamptz,
  pages_attempted integer not null default 0 check (pages_attempted >= 0),
  pages_succeeded integer not null default 0 check (pages_succeeded >= 0),
  responses_observed integer not null default 0 check (responses_observed >= 0),
  rows_observed integer not null default 0 check (rows_observed >= 0),
  rows_accepted integer not null default 0 check (rows_accepted >= 0),
  rows_inserted integer not null default 0 check (rows_inserted >= 0),
  rows_updated integer not null default 0 check (rows_updated >= 0),
  rows_unchanged integer not null default 0 check (rows_unchanged >= 0),
  rows_rejected integer not null default 0 check (rows_rejected >= 0),
  schema_contract_sha256 text not null,
  source_schema_sha256 text,
  raw_manifest_sha256 text not null,
  raw_manifest_object_key text not null,
  outcomes jsonb not null default '[]'::jsonb,
  source_metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint external_source_run_time_order check (
    started_at <= observed_at and observed_at <= completed_at
  ),
  constraint external_source_run_attempt_order check (
    attempted_event_from is null
    or attempted_event_through is null
    or attempted_event_from <= attempted_event_through
  ),
  constraint external_source_run_event_bound check (
    event_through is null
    or attempted_event_through is null
    or event_through <= attempted_event_through
  ),
  constraint external_source_run_page_counts check (
    pages_succeeded <= pages_attempted
  ),
  constraint external_source_run_row_partition check (
    rows_observed = rows_accepted + rows_rejected
  ),
  constraint external_source_run_write_partition check (
    rows_accepted = rows_inserted + rows_updated + rows_unchanged
  ),
  constraint external_source_run_reason_required check (
    status in ('ok', 'empty')
    or (reason_code is not null and btrim(reason_code) <> '')
  ),
  constraint external_source_run_empty_semantics check (
    status <> 'empty'
    or (
      rows_observed = 0
      and rows_accepted = 0
      and rows_inserted = 0
      and rows_updated = 0
      and rows_unchanged = 0
      and rows_rejected = 0
    )
  ),
  constraint external_source_run_wait_semantics check (
    status <> 'source_wait'
    or (
      rows_observed = 0
      and rows_accepted = 0
      and rows_inserted = 0
      and rows_updated = 0
      and rows_unchanged = 0
      and rows_rejected = 0
    )
  ),
  constraint external_source_run_ok_has_no_rejections check (
    status <> 'ok' or rows_rejected = 0
  ),
  constraint external_source_run_failed_has_no_committed_writes check (
    status <> 'failed' or (rows_inserted = 0 and rows_updated = 0)
  ),
  constraint external_source_run_schema_hash check (
    source_schema_sha256 is null
    or source_schema_sha256 ~ '^[0-9a-f]{64}$'
  ),
  constraint external_source_run_schema_contract_hash check (
    schema_contract_sha256 ~ '^[0-9a-f]{64}$'
  ),
  constraint external_source_run_schema_hash_required check (
    status not in ('ok', 'empty', 'partial')
    or (
      source_schema_sha256 is not null
      and source_schema_sha256 ~ '^[0-9a-f]{64}$'
    )
  ),
  constraint external_source_run_manifest_hash check (
    raw_manifest_sha256 ~ '^[0-9a-f]{64}$'
  ),
  constraint external_source_run_manifest_key check (
    btrim(raw_manifest_object_key) <> ''
    and position('?' in raw_manifest_object_key) = 0
    and position(E'\n' in raw_manifest_object_key) = 0
  ),
  constraint external_source_run_outcomes_array check (
    jsonb_typeof(outcomes) = 'array'
  ),
  constraint external_source_run_metadata_object check (
    jsonb_typeof(source_metadata) = 'object'
  )
);

comment on table public.external_source_run_receipts is
  'Private append-only terminal receipts for the FDEP ERP and FAA OE/AAA collectors. Run, attempted-source and event clocks remain separate; empty and unchanged polls still receipt.';
comment on column public.external_source_run_receipts.observed_at is
  'System clock when the final source response or terminal source failure represented by this receipt was observed.';
comment on column public.external_source_run_receipts.event_through is
  'Newest real-world source event represented by accepted evidence; never advanced merely because a collector ran.';
comment on column public.external_source_run_receipts.schema_contract_sha256 is
  'Hash of the versioned parser/schema contract expected by this collector run, present even when the remote source cannot be observed.';
comment on column public.external_source_run_receipts.source_schema_sha256 is
  'Hash of the schema actually observed from the source; required for ok, empty and partial terminal receipts.';
comment on column public.external_source_run_receipts.raw_manifest_object_key is
  'Opaque key for a private immutable raw-evidence manifest. Never store a signed/public URL or query secret here.';

create index if not exists external_source_run_source_completed_idx
  on public.external_source_run_receipts (source_id, completed_at desc);
create index if not exists external_source_run_attention_idx
  on public.external_source_run_receipts (source_id, completed_at desc)
  where status in ('source_wait', 'partial', 'failed');

alter table public.external_source_run_receipts enable row level security;
alter table public.external_source_run_receipts force row level security;

-- Private by default. There is intentionally no anon/authenticated policy.
revoke all on table public.external_source_run_receipts
  from public, anon, authenticated, service_role;
grant usage on schema public to service_role;
grant select, insert on table public.external_source_run_receipts to service_role;

revoke all on sequence public.external_source_run_receipts_id_seq
  from public, anon, authenticated, service_role;
grant usage, select on sequence public.external_source_run_receipts_id_seq
  to service_role;

create or replace function public.fs_reject_external_source_receipt_mutation()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception using
    errcode = '55000',
    message = 'external source run receipts are append-only';
end
$$;

revoke all on function public.fs_reject_external_source_receipt_mutation()
  from public, anon, authenticated, service_role;

drop trigger if exists external_source_run_receipts_no_row_mutation
  on public.external_source_run_receipts;
create trigger external_source_run_receipts_no_row_mutation
  before update or delete on public.external_source_run_receipts
  for each row execute function public.fs_reject_external_source_receipt_mutation();

drop trigger if exists external_source_run_receipts_no_truncate
  on public.external_source_run_receipts;
create trigger external_source_run_receipts_no_truncate
  before truncate on public.external_source_run_receipts
  for each statement execute function public.fs_reject_external_source_receipt_mutation();

-- ---------------------------------------------------------------------------
-- Generation-bound Broward county parcel staging and receipts
-- ---------------------------------------------------------------------------

-- This pre-existing immutable helper is used by stage CHECK constraints and
-- the promotion gate. Its body resolves only PostgreSQL catalog built-ins;
-- pin the lookup path so caller-created objects cannot alter normalization.
alter function public.fs_normalize_folio(text) set search_path = pg_catalog;

create table if not exists public.broward_parcel_import_generations (
  generation_id uuid primary key,
  source_name text not null
    default 'Broward County GIS — PARCEL_POLY_BCPA_TAXROLL'
    check (btrim(source_name) <> ''),
  source_layer_url text not null
    check (btrim(source_layer_url) <> '' and position('?' in source_layer_url) = 0),
  source_dataset_vintage text not null check (btrim(source_dataset_vintage) <> ''),
  collector_version text not null check (btrim(collector_version) <> ''),
  parser_version text not null check (btrim(parser_version) <> ''),
  normalizer_version text not null check (btrim(normalizer_version) <> ''),
  coverage_oid_min bigint not null check (coverage_oid_min >= 0),
  coverage_oid_max bigint not null,
  expected_range_count integer not null check (expected_range_count > 0),
  source_reported_count integer not null check (source_reported_count > 0),
  minimum_accepted_rows integer not null check (minimum_accepted_rows > 0),
  max_rejected_rows integer not null check (max_rejected_rows >= 0),
  max_duplicate_folios integer not null check (max_duplicate_folios >= 0),
  quality_contract_sha256 text not null
    check (quality_contract_sha256 ~ '^[0-9a-f]{64}$'),
  rows_received integer not null default 0 check (rows_received >= 0),
  rows_accepted integer not null default 0 check (rows_accepted >= 0),
  rows_rejected integer not null default 0 check (rows_rejected >= 0),
  rejected_missing_folio integer not null default 0 check (rejected_missing_folio >= 0),
  rejected_bad_folio_format integer not null default 0 check (rejected_bad_folio_format >= 0),
  rejected_missing_centroid integer not null default 0 check (rejected_missing_centroid >= 0),
  rejected_out_of_bounds integer not null default 0 check (rejected_out_of_bounds >= 0),
  duplicate_folios integer not null default 0 check (duplicate_folios >= 0),
  source_schema_sha256 text,
  raw_manifest_sha256 text,
  raw_manifest_object_key text,
  status text not null default 'staging'
    check (status in ('staging', 'ready', 'failed', 'promoted', 'superseded')),
  failure_reason text,
  started_at timestamptz not null,
  source_observed_at timestamptz,
  completed_at timestamptz,
  promoted_at timestamptz,
  created_at timestamptz not null default now(),
  constraint broward_parcel_generation_oid_bounds check (
    coverage_oid_max >= coverage_oid_min
  ),
  constraint broward_parcel_generation_row_partition check (
    rows_received = rows_accepted + rows_rejected + duplicate_folios
  ),
  constraint broward_parcel_generation_rejection_partition check (
    rows_rejected = rejected_missing_folio
      + rejected_bad_folio_format
      + rejected_missing_centroid
      + rejected_out_of_bounds
  ),
  constraint broward_parcel_generation_quality_contract_bounds check (
    minimum_accepted_rows <= source_reported_count
    and max_rejected_rows <= source_reported_count
    and max_duplicate_folios <= source_reported_count
  ),
  constraint broward_parcel_generation_time_order check (
    source_observed_at is null
    or (
      started_at <= source_observed_at
      and (completed_at is null or source_observed_at <= completed_at)
    )
  ),
  constraint broward_parcel_generation_terminal_receipt check (
    status = 'staging'
    or (
      completed_at is not null
      and source_observed_at is not null
      and source_schema_sha256 is not null
      and source_schema_sha256 ~ '^[0-9a-f]{64}$'
      and raw_manifest_sha256 is not null
      and raw_manifest_sha256 ~ '^[0-9a-f]{64}$'
      and raw_manifest_object_key is not null
      and btrim(raw_manifest_object_key) <> ''
      and position('?' in raw_manifest_object_key) = 0
    )
  ),
  constraint broward_parcel_generation_failure_reason check (
    status <> 'failed'
    or (failure_reason is not null and btrim(failure_reason) <> '')
  ),
  constraint broward_parcel_generation_promoted_clock check (
    (status in ('staging', 'ready', 'failed') and promoted_at is null)
    or (status in ('promoted', 'superseded') and promoted_at is not null)
  )
);

create unique index if not exists broward_parcel_one_promoted_generation_idx
  on public.broward_parcel_import_generations ((status))
  where status = 'promoted';
create index if not exists broward_parcel_generation_created_idx
  on public.broward_parcel_import_generations (created_at desc);

create table if not exists public.broward_parcel_generation_ranges (
  range_id bigint generated always as identity primary key,
  generation_id uuid not null
    references public.broward_parcel_import_generations(generation_id)
    on delete restrict,
  oid_min bigint not null check (oid_min >= 0),
  oid_max bigint not null,
  expected_source_count integer check (expected_source_count >= 0),
  rows_received integer not null default 0 check (rows_received >= 0),
  rows_accepted integer not null default 0 check (rows_accepted >= 0),
  rows_rejected integer not null default 0 check (rows_rejected >= 0),
  rejected_missing_folio integer not null default 0 check (rejected_missing_folio >= 0),
  rejected_bad_folio_format integer not null default 0 check (rejected_bad_folio_format >= 0),
  rejected_missing_centroid integer not null default 0 check (rejected_missing_centroid >= 0),
  rejected_out_of_bounds integer not null default 0 check (rejected_out_of_bounds >= 0),
  duplicate_folios integer not null default 0 check (duplicate_folios >= 0),
  status text not null default 'pending'
    check (status in ('pending', 'in_progress', 'complete', 'failed')),
  attempts integer not null default 0 check (attempts >= 0),
  last_error text,
  raw_manifest_sha256 text,
  raw_manifest_object_key text,
  started_at timestamptz,
  completed_at timestamptz,
  constraint broward_parcel_generation_range_bounds check (oid_max >= oid_min),
  constraint broward_parcel_generation_range_unique
    unique (generation_id, oid_min, oid_max),
  constraint broward_parcel_generation_range_row_partition check (
    rows_received = rows_accepted + rows_rejected + duplicate_folios
  ),
  constraint broward_parcel_generation_range_rejection_partition check (
    rows_rejected = rejected_missing_folio
      + rejected_bad_folio_format
      + rejected_missing_centroid
      + rejected_out_of_bounds
  ),
  constraint broward_parcel_generation_range_complete_receipt check (
    status <> 'complete'
    or (
      expected_source_count is not null
      and rows_received = expected_source_count
      and completed_at is not null
      and raw_manifest_sha256 is not null
      and raw_manifest_sha256 ~ '^[0-9a-f]{64}$'
      and raw_manifest_object_key is not null
      and btrim(raw_manifest_object_key) <> ''
      and position('?' in raw_manifest_object_key) = 0
    )
  ),
  constraint broward_parcel_generation_range_time_order check (
    started_at is null or completed_at is null or started_at <= completed_at
  )
);

create index if not exists broward_parcel_generation_range_order_idx
  on public.broward_parcel_generation_ranges (generation_id, oid_min, oid_max);
create index if not exists broward_parcel_generation_range_status_idx
  on public.broward_parcel_generation_ranges (generation_id, status);

create table if not exists public.broward_parcel_geography_stage (
  generation_id uuid not null
    references public.broward_parcel_import_generations(generation_id)
    on delete restrict,
  parcel_id_normalized text not null,
  parcel_id_raw text not null,
  folio_number_raw text,
  latitude double precision not null,
  longitude double precision not null,
  address text,
  municipality text,
  property_type text,
  geometry_source text not null default 'esri_centroid_wgs84',
  source_object_id bigint not null check (source_object_id >= 0),
  location_precision text not null default 'parcel_centroid',
  active_or_historical text not null default 'active',
  source_attributes_json jsonb,
  fetched_at timestamptz not null,
  situs_city text,
  situs_zip text,
  sale_1_cin text,
  sale_1_deed_type text,
  sale_1_date date,
  sale_1_stamp_amount numeric,
  created_at timestamptz not null default now(),
  primary key (generation_id, parcel_id_normalized),
  constraint broward_parcel_stage_source_object_unique
    unique (generation_id, source_object_id),
  constraint broward_parcel_stage_folio_canonical check (
    public.fs_normalize_folio(parcel_id_normalized) is not null
    and public.fs_normalize_folio(parcel_id_normalized) = parcel_id_normalized
  ),
  constraint broward_parcel_stage_raw_folio_matches check (
    public.fs_normalize_folio(parcel_id_raw)
      is not distinct from parcel_id_normalized
    and (
      folio_number_raw is null
      or public.fs_normalize_folio(folio_number_raw)
        is not distinct from parcel_id_normalized
    )
  ),
  constraint broward_parcel_stage_bbox check (
    latitude between 25.90 and 26.50
    and longitude between -80.70 and -79.98
  )
);

create index if not exists broward_parcel_stage_generation_idx
  on public.broward_parcel_geography_stage (generation_id);

comment on table public.broward_parcel_import_generations is
  'Private generation receipt for one immutable Broward parcel source snapshot. A generation is not live merely because it is ready.';
comment on column public.broward_parcel_import_generations.duplicate_folios is
  'Raw source rows omitted by the quality-contract-hashed deterministic duplicate-folio winner rule; not distinct duplicate groups.';
comment on column public.broward_parcel_import_generations.quality_contract_sha256 is
  'Hash of the reviewed quality contract, including rejection ceilings, minimum accepted rows and deterministic duplicate-folio winner rule.';
comment on table public.broward_parcel_generation_ranges is
  'Generation-bound inclusive OBJECTID range receipts. Range rows from different source vintages can never satisfy one promotion.';
comment on table public.broward_parcel_geography_stage is
  'Private generation-bound parcel staging. Promotion replaces the live countywide table atomically only after the full gate passes.';

alter table public.broward_parcel_import_generations enable row level security;
alter table public.broward_parcel_import_generations force row level security;
alter table public.broward_parcel_generation_ranges enable row level security;
alter table public.broward_parcel_generation_ranges force row level security;
alter table public.broward_parcel_geography_stage enable row level security;
alter table public.broward_parcel_geography_stage force row level security;

-- No runtime role receives parcel staging or promotion access in this migration.
-- A later reviewed collector-integration migration may grant only the operations
-- proved necessary by the exported deployed collector.
revoke all on table public.broward_parcel_import_generations
  from public, anon, authenticated, service_role;
revoke all on table public.broward_parcel_generation_ranges
  from public, anon, authenticated, service_role;
revoke all on table public.broward_parcel_geography_stage
  from public, anon, authenticated, service_role;
revoke all on sequence public.broward_parcel_generation_ranges_range_id_seq
  from public, anon, authenticated, service_role;

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
      raise exception using
        errcode = '55000',
        message = 'terminal parcel generation receipts cannot be deleted';
    end if;
    return old;
  end if;

  if tg_op = 'INSERT' and new.status <> 'staging' then
    raise exception using
      errcode = '23514',
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
       or old.started_at <> new.started_at
       or old.created_at <> new.created_at then
      raise exception using
        errcode = '23514',
        message = 'parcel generation identity and source bounds are immutable';
    end if;

    if old.status = 'staging' and new.status in ('staging', 'ready', 'failed') then
      return new;
    end if;

    -- Only the table owner may make the two promotion-only transitions. The
    -- SECURITY DEFINER promotion gate is owned by that same migration role.
    -- Do not use a caller-settable custom GUC as an authorization token.
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

    raise exception using
      errcode = '55000',
      message = 'ready/promoted parcel generation receipts are immutable outside the promotion gate';
  end if;

  return new;
end
$$;

create or replace function public.fs_guard_broward_parcel_range_mutation()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  target_generation uuid;
  generation_status text;
begin
  if tg_op = 'UPDATE'
     and old.generation_id is distinct from new.generation_id then
    raise exception using
      errcode = '23514',
      message = 'parcel range generation binding is immutable';
  end if;

  target_generation := case when tg_op = 'DELETE'
    then old.generation_id else new.generation_id end;

  select g.status into generation_status
  from public.broward_parcel_import_generations g
  where g.generation_id = target_generation
  for update;

  if generation_status is null then
    raise exception using
      errcode = '23503',
      message = 'parcel range references an unknown generation';
  end if;
  if generation_status <> 'staging' then
    raise exception using
      errcode = '55000',
      message = 'parcel ranges are immutable after their generation leaves staging';
  end if;

  if tg_op in ('INSERT', 'UPDATE') and exists (
    select 1
    from public.broward_parcel_generation_ranges r
    where r.generation_id = new.generation_id
      and r.range_id <> coalesce(new.range_id, -1)
      and not (r.oid_max < new.oid_min or r.oid_min > new.oid_max)
  ) then
    raise exception using
      errcode = '23514',
      message = 'parcel OBJECTID ranges may not overlap within a generation';
  end if;

  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end
$$;

create or replace function public.fs_guard_broward_parcel_stage_mutation()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  target_generation uuid;
  generation_status text;
begin
  if tg_op = 'UPDATE'
     and old.generation_id is distinct from new.generation_id then
    raise exception using
      errcode = '23514',
      message = 'staged parcel generation binding is immutable';
  end if;

  target_generation := case when tg_op = 'DELETE'
    then old.generation_id else new.generation_id end;

  select g.status into generation_status
  from public.broward_parcel_import_generations g
  where g.generation_id = target_generation
  for update;

  if generation_status is null then
    raise exception using
      errcode = '23503',
      message = 'staged parcel references an unknown generation';
  end if;
  if generation_status <> 'staging' then
    raise exception using
      errcode = '55000',
      message = 'staged parcels are immutable after their generation leaves staging';
  end if;

  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end
$$;

revoke all on function public.fs_guard_broward_parcel_generation_update()
  from public, anon, authenticated, service_role;
revoke all on function public.fs_guard_broward_parcel_range_mutation()
  from public, anon, authenticated, service_role;
revoke all on function public.fs_guard_broward_parcel_stage_mutation()
  from public, anon, authenticated, service_role;

drop trigger if exists broward_parcel_generation_update_guard
  on public.broward_parcel_import_generations;
create trigger broward_parcel_generation_update_guard
  before insert or update or delete on public.broward_parcel_import_generations
  for each row execute function public.fs_guard_broward_parcel_generation_update();

drop trigger if exists broward_parcel_range_mutation_guard
  on public.broward_parcel_generation_ranges;
create trigger broward_parcel_range_mutation_guard
  before insert or update or delete on public.broward_parcel_generation_ranges
  for each row execute function public.fs_guard_broward_parcel_range_mutation();

drop trigger if exists broward_parcel_stage_mutation_guard
  on public.broward_parcel_geography_stage;
create trigger broward_parcel_stage_mutation_guard
  before insert or update or delete on public.broward_parcel_geography_stage
  for each row execute function public.fs_guard_broward_parcel_stage_mutation();

-- Mark the legacy unbound ledgers as historical. They remain readable evidence,
-- but cannot prove a promotable generation because they have no source-vintage FK.
comment on table public.broward_parcel_import_runs is
  'Legacy unbound parcel import log. Historical evidence only; not eligible to satisfy the generation promotion gate.';
comment on table public.broward_parcel_range_ledger is
  'Legacy unbound parcel range ledger. Historical evidence only; ranges from this table cannot satisfy generation promotion.';

alter table public.broward_parcel_geography
  add column if not exists import_generation_id uuid;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'broward_parcel_geography_generation_fk'
      and conrelid = 'public.broward_parcel_geography'::regclass
  ) then
    alter table public.broward_parcel_geography
      add constraint broward_parcel_geography_generation_fk
      foreign key (import_generation_id)
      references public.broward_parcel_import_generations(generation_id)
      on delete restrict
      not valid;
  end if;
end
$$;

create index if not exists broward_parcel_geography_generation_idx
  on public.broward_parcel_geography (import_generation_id);

create or replace function public.fs_promote_broward_parcel_generation(
  p_generation_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  g public.broward_parcel_import_generations%rowtype;
  range_count bigint;
  incomplete_range_count bigint;
  topology_error_count bigint;
  range_oid_min bigint;
  range_oid_max bigint;
  sum_expected bigint;
  sum_received bigint;
  sum_accepted bigint;
  sum_rejected bigint;
  sum_missing_folio bigint;
  sum_bad_folio bigint;
  sum_missing_centroid bigint;
  sum_out_of_bounds bigint;
  sum_duplicate_folios bigint;
  stage_count bigint;
  stage_unique_folios bigint;
  stage_unique_object_ids bigint;
  stage_invalid_folios bigint;
  stage_invalid_bbox bigint;
  stage_outside_coverage_count bigint;
  stage_range_mismatch_count bigint;
  live_user_trigger_count bigint;
  live_inbound_fk_count bigint;
  inserted_count bigint;
  live_count bigint;
  live_generation_count bigint;
  property_transfer_rows_refreshed bigint;
begin
  if p_generation_id is null then
    raise exception using errcode = '22004', message = 'generation_id is required';
  end if;

  -- Use the same transaction advisory lock as the scheduled materialized-view
  -- refresh, and acquire child-table locks before the parent row. Child DML
  -- obtains its table lock before its trigger locks the parent, so this order
  -- prevents a reverse-lock deadlock during promotion.
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtext('florida-signal:property-transfer-refresh')
  );
  lock table public.broward_parcel_generation_ranges in share mode;
  lock table public.broward_parcel_geography_stage in share mode;

  select * into g
  from public.broward_parcel_import_generations
  where generation_id = p_generation_id
  for update;

  if not found then
    raise exception using errcode = 'P0002', message = 'parcel generation not found';
  end if;

  if g.status = 'promoted' then
    select count(*), count(distinct import_generation_id)
      into live_count, live_generation_count
    from public.broward_parcel_geography;
    if live_count = g.rows_accepted
       and live_generation_count = 1
       and exists (
         select 1 from public.broward_parcel_geography
         where import_generation_id = p_generation_id
       )
       and not exists (
         select 1 from public.broward_parcel_geography
         where import_generation_id is distinct from p_generation_id
       ) then
      return jsonb_build_object(
        'generation_id', p_generation_id,
        'status', 'already_promoted',
        'rows_promoted', live_count
      );
    end if;
    raise exception using
      errcode = '23514',
      message = 'promoted generation does not match the live parcel table';
  end if;

  if g.status <> 'ready' then
    raise exception using
      errcode = '55000',
      message = 'parcel generation must be ready before promotion';
  end if;

  select
    count(*),
    count(*) filter (where
      status <> 'complete'
      or expected_source_count is null
      or expected_source_count <> rows_received
      or rows_received <> rows_accepted + rows_rejected + duplicate_folios
      or rows_rejected <> rejected_missing_folio
        + rejected_bad_folio_format
        + rejected_missing_centroid
        + rejected_out_of_bounds
      or raw_manifest_sha256 is null
      or raw_manifest_sha256 !~ '^[0-9a-f]{64}$'
      or raw_manifest_object_key is null
      or btrim(raw_manifest_object_key) = ''
      or position('?' in raw_manifest_object_key) <> 0
    ),
    min(oid_min), max(oid_max),
    coalesce(sum(expected_source_count), 0),
    coalesce(sum(rows_received), 0),
    coalesce(sum(rows_accepted), 0),
    coalesce(sum(rows_rejected), 0),
    coalesce(sum(rejected_missing_folio), 0),
    coalesce(sum(rejected_bad_folio_format), 0),
    coalesce(sum(rejected_missing_centroid), 0),
    coalesce(sum(rejected_out_of_bounds), 0),
    coalesce(sum(duplicate_folios), 0)
  into
    range_count, incomplete_range_count, range_oid_min, range_oid_max,
    sum_expected, sum_received, sum_accepted, sum_rejected,
    sum_missing_folio, sum_bad_folio, sum_missing_centroid,
    sum_out_of_bounds, sum_duplicate_folios
  from public.broward_parcel_generation_ranges
  where generation_id = p_generation_id;

  select count(*) into topology_error_count
  from (
    select
      oid_min,
      lag(oid_max) over (order by oid_min, oid_max) as previous_oid_max
    from public.broward_parcel_generation_ranges
    where generation_id = p_generation_id
  ) ordered_ranges
  where (previous_oid_max is null and oid_min <> g.coverage_oid_min)
     or (previous_oid_max is not null and oid_min <> previous_oid_max + 1);

  if range_count <> g.expected_range_count
     or incomplete_range_count <> 0
     or topology_error_count <> 0
     or range_oid_min <> g.coverage_oid_min
     or range_oid_max <> g.coverage_oid_max then
    raise exception using
      errcode = '23514',
      message = 'parcel generation range coverage is incomplete, gapped, or overlapping';
  end if;

  if sum_expected <> g.source_reported_count
     or sum_received <> g.rows_received
     or sum_accepted <> g.rows_accepted
     or sum_rejected <> g.rows_rejected
     or sum_missing_folio <> g.rejected_missing_folio
     or sum_bad_folio <> g.rejected_bad_folio_format
     or sum_missing_centroid <> g.rejected_missing_centroid
     or sum_out_of_bounds <> g.rejected_out_of_bounds
     or sum_duplicate_folios <> g.duplicate_folios then
    raise exception using
      errcode = '23514',
      message = 'parcel generation summary does not match its range receipts';
  end if;

  -- The verified county layer contains multi-polygon duplicate folios and a
  -- small number of invalid centroids. They may be omitted only when every raw
  -- row is accounted for and the reviewed quality contract's explicit bounds
  -- pass; silent loss or collector-selected thresholds remain impossible.
  if g.rows_received <> g.source_reported_count
     or g.rows_accepted < g.minimum_accepted_rows
     or g.rows_rejected > g.max_rejected_rows
     or g.duplicate_folios > g.max_duplicate_folios then
    raise exception using
      errcode = '23514',
      message = 'parcel generation violates its source or quality contract';
  end if;

  select
    count(*),
    count(distinct parcel_id_normalized),
    count(distinct source_object_id),
    count(*) filter (where
      public.fs_normalize_folio(parcel_id_normalized) is distinct from parcel_id_normalized
      or public.fs_normalize_folio(parcel_id_raw) is distinct from parcel_id_normalized
      or (
        folio_number_raw is not null
        and public.fs_normalize_folio(folio_number_raw)
          is distinct from parcel_id_normalized
      )
    ),
    count(*) filter (where
      latitude not between 25.90 and 26.50
      or longitude not between -80.70 and -79.98
    )
  into
    stage_count, stage_unique_folios, stage_unique_object_ids,
    stage_invalid_folios, stage_invalid_bbox
  from public.broward_parcel_geography_stage
  where generation_id = p_generation_id;

  select count(*) into stage_outside_coverage_count
  from public.broward_parcel_geography_stage s
  where s.generation_id = p_generation_id
    and (
      s.source_object_id < g.coverage_oid_min
      or s.source_object_id > g.coverage_oid_max
    );

  -- Reconcile the chosen staged winner rows back to the exact inclusive
  -- OBJECTID range receipt that claims each accepted source row. Disjoint range
  -- topology plus global source-OBJECTID uniqueness makes this a one-to-one
  -- membership proof without inventing a collector-side range identifier.
  select count(*) into stage_range_mismatch_count
  from public.broward_parcel_generation_ranges r
  where r.generation_id = p_generation_id
    and (
      select count(*)
      from public.broward_parcel_geography_stage s
      where s.generation_id = r.generation_id
        and s.source_object_id between r.oid_min and r.oid_max
    ) <> r.rows_accepted;

  if stage_count <> g.rows_accepted
     or stage_unique_folios <> stage_count
     or stage_unique_object_ids <> stage_count
     or stage_invalid_folios <> 0
     or stage_invalid_bbox <> 0
     or stage_outside_coverage_count <> 0
     or stage_range_mismatch_count <> 0 then
    raise exception using
      errcode = '23514',
      message = 'parcel staging count, range membership, identity, or bbox gate failed';
  end if;

  -- The ACCESS EXCLUSIVE lock closes the catalog-check TOCTOU window: no
  -- concurrent DDL can add/enable a trigger or inbound FK after inspection.
  lock table public.broward_parcel_geography in access exclusive mode;

  select count(*) into live_user_trigger_count
  from pg_catalog.pg_trigger
  where tgrelid = 'public.broward_parcel_geography'::regclass
    and not tgisinternal
    and tgenabled <> 'D';

  select count(*) into live_inbound_fk_count
  from pg_catalog.pg_constraint
  where contype = 'f'
    and confrelid = 'public.broward_parcel_geography'::regclass;

  if live_user_trigger_count <> 0 or live_inbound_fk_count <> 0 then
    raise exception using
      errcode = '55000',
      message = 'live parcel table has unreviewed triggers or inbound foreign keys';
  end if;

  update public.broward_parcel_import_generations
  set status = 'superseded'
  where status = 'promoted'
    and generation_id <> p_generation_id;

  delete from public.broward_parcel_geography;

  insert into public.broward_parcel_geography (
    parcel_id_normalized,
    parcel_id_raw,
    folio_number_raw,
    latitude,
    longitude,
    address,
    municipality,
    property_type,
    geometry_source,
    source_name,
    source_layer_url,
    source_object_id,
    source_dataset_vintage,
    location_precision,
    active_or_historical,
    source_attributes_json,
    fetched_at,
    created_at,
    updated_at,
    situs_city,
    situs_zip,
    sale_1_cin,
    sale_1_deed_type,
    sale_1_date,
    sale_1_stamp_amount,
    import_generation_id
  )
  select
    s.parcel_id_normalized,
    s.parcel_id_raw,
    s.folio_number_raw,
    s.latitude,
    s.longitude,
    s.address,
    s.municipality,
    s.property_type,
    s.geometry_source,
    g.source_name,
    g.source_layer_url,
    s.source_object_id,
    g.source_dataset_vintage,
    s.location_precision,
    s.active_or_historical,
    s.source_attributes_json,
    s.fetched_at,
    now(),
    now(),
    s.situs_city,
    s.situs_zip,
    s.sale_1_cin,
    s.sale_1_deed_type,
    s.sale_1_date,
    s.sale_1_stamp_amount,
    p_generation_id
  from public.broward_parcel_geography_stage s
  where s.generation_id = p_generation_id
  order by s.parcel_id_normalized;

  get diagnostics inserted_count = row_count;
  if inserted_count <> g.rows_accepted then
    raise exception using
      errcode = '23514',
      message = 'atomic parcel promotion inserted an unexpected row count';
  end if;

  select count(*), count(distinct import_generation_id)
    into live_count, live_generation_count
  from public.broward_parcel_geography;
  if live_count <> g.rows_accepted
     or live_generation_count <> 1
     or exists (
       select 1 from public.broward_parcel_geography
       where import_generation_id is distinct from p_generation_id
     ) then
    raise exception using
      errcode = '23514',
      message = 'live parcel generation readback failed';
  end if;

  -- The public deed/parcel snapshot and candidate detector read this
  -- materialized view. Refresh it inside the same transaction so no committed
  -- state can expose the previous parcel joins as current after promotion.
  refresh materialized view public.broward_property_transfer_map;
  select count(*) into property_transfer_rows_refreshed
  from public.broward_property_transfer_map;

  update public.broward_parcel_import_generations
  set status = 'promoted', promoted_at = now()
  where generation_id = p_generation_id
    and status = 'ready';

  if not found then
    raise exception using
      errcode = '55000',
      message = 'parcel generation state changed during promotion';
  end if;

  return jsonb_build_object(
    'generation_id', p_generation_id,
    'status', 'promoted',
    'source_dataset_vintage', g.source_dataset_vintage,
    'source_reported_count', g.source_reported_count,
    'rows_promoted', inserted_count,
    'property_transfer_rows_refreshed', property_transfer_rows_refreshed,
    'range_count', range_count,
    'rows_rejected', g.rows_rejected
  );
end
$$;

comment on function public.fs_promote_broward_parcel_generation(uuid) is
  'Approval-gated atomic parcel promotion. Refuses mixed generations, incomplete/gapped/overlapping ranges, range/stage drift, uncontracted source loss, duplicate staged folios/object IDs, invalid normalized folios and invalid Broward centroids; refreshes the dependent deed/parcel materialized view before commit.';

-- SECURITY DEFINER is required for the future single promotion boundary, so its
-- search_path is empty and every relation is schema-qualified. It is not callable
-- by any Data API role in this migration, including service_role.
revoke all on function public.fs_promote_broward_parcel_generation(uuid)
  from public, anon, authenticated, service_role;

-- No cron.schedule, net.http_post, Edge function, collector grant or live promotion
-- appears in this migration.

-- Schema-only rollback before any generation is promoted (separate approval):
--   drop function if exists public.fs_promote_broward_parcel_generation(uuid);
--   drop table if exists public.broward_parcel_geography_stage;
--   drop table if exists public.broward_parcel_generation_ranges;
--   alter table public.broward_parcel_geography
--     drop constraint if exists broward_parcel_geography_generation_fk;
--   alter table public.broward_parcel_geography
--     drop column if exists import_generation_id;
--   drop table if exists public.broward_parcel_import_generations;
--   drop table if exists public.external_source_run_receipts;
-- After promotion, restoring the prior live parcel generation requires its exact
-- pre-promotion backup; dropping schema objects cannot reconstruct replaced rows.
