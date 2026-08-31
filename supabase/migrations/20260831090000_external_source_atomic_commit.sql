-- Atomic staging + commit path for receipted FDEP ERP and FAA OE/AAA runs.
-- No public policy or elevated-privilege function is added. Collectors stage a
-- complete run and call one SECURITY INVOKER RPC after private raw evidence is
-- durable; source rows and the terminal receipt then commit together.

create table if not exists public.external_source_run_stage (
  source_id text not null check (source_id in ('fdep_erp', 'faa_oeaaa')),
  run_id uuid not null,
  row_key text not null check (btrim(row_key) <> ''),
  row_data jsonb not null check (jsonb_typeof(row_data) = 'object'),
  staged_at timestamptz not null default now(),
  primary key (source_id, run_id, row_key)
);

comment on table public.external_source_run_stage is
  'Private recoverable rows awaiting one atomic source-row plus terminal-receipt commit.';

create index if not exists external_source_run_stage_age_idx
  on public.external_source_run_stage (staged_at);

alter table public.external_source_run_stage enable row level security;
alter table public.external_source_run_stage force row level security;

revoke all on table public.external_source_run_stage
  from public, anon, authenticated, service_role;
grant select, insert, update, delete on table public.external_source_run_stage
  to service_role;

do $$
begin
  if not has_table_privilege('service_role', 'public.fdep_erp', 'select')
     or not has_table_privilege('service_role', 'public.fdep_erp', 'insert')
     or not has_table_privilege('service_role', 'public.fdep_erp', 'update')
     or not has_table_privilege('service_role', 'public.faa_oeaaa', 'select')
     or not has_table_privilege('service_role', 'public.faa_oeaaa', 'insert')
     or not has_table_privilege('service_role', 'public.faa_oeaaa', 'update')
     or not has_table_privilege(
       'service_role', 'public.external_source_run_receipts', 'select'
     )
     or not has_table_privilege(
       'service_role', 'public.external_source_run_receipts', 'insert'
     )
     or not has_table_privilege(
       'service_role', 'storage.objects', 'select'
     ) then
    raise exception using
      errcode = '42501',
      message = 'service_role lacks the minimum privileges for the invoker commit RPC';
  end if;
end
$$;

create or replace function public.fs_commit_external_source_run(
  p_source_id text,
  p_run_id uuid,
  p_receipt jsonb,
  p_manifest jsonb
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_existing public.external_source_run_receipts%rowtype;
  v_status text;
  v_manifest_key text;
  v_expected_manifest_key text;
  v_manifest_sha256 text;
  v_raw_prefix text;
  v_source_metadata jsonb;
  v_expected_receipt jsonb;
  v_stage_count bigint;
  v_rows_observed bigint;
  v_rows_rejected bigint;
  v_rows_inserted bigint := 0;
  v_rows_updated bigint := 0;
  v_rows_unchanged bigint := 0;
begin
  if p_source_id not in ('fdep_erp', 'faa_oeaaa') then
    raise exception using errcode = '22023', message = 'unsupported external source';
  end if;
  if p_run_id is null then
    raise exception using errcode = '22004', message = 'run_id is required';
  end if;
  if p_receipt is null or jsonb_typeof(p_receipt) <> 'object' then
    raise exception using errcode = '22023', message = 'receipt must be a JSON object';
  end if;
  if p_receipt - array[
    'collector_name', 'collector_version', 'parser_version',
    'normalizer_version', 'status', 'reason_code', 'reason_detail',
    'started_at', 'observed_at', 'completed_at', 'attempted_event_from',
    'attempted_event_through', 'event_through', 'pages_attempted',
    'pages_succeeded', 'responses_observed', 'rows_observed',
    'rows_rejected', 'schema_contract_sha256', 'source_schema_sha256',
    'raw_manifest_object_key', 'outcomes', 'source_metadata'
  ]::text[] <> '{}'::jsonb then
    raise exception using errcode = '23514', message = 'receipt contains unknown fields';
  end if;
  if p_manifest is null or jsonb_typeof(p_manifest) <> 'object' then
    raise exception using errcode = '22023', message = 'manifest must be a JSON object';
  end if;

  -- Source-wide serialization covers the read/classify/upsert sequence so two
  -- distinct runs cannot both claim that the same previously absent row was
  -- inserted. The run lock separately makes cross-source run-id collisions
  -- deterministic before the immutable receipt UNIQUE constraint is reached.
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      'florida-signal:external-source:' || p_source_id,
      0
    )
  );
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      'florida-signal:external-source-run:' || p_run_id::text,
      0
    )
  );

  v_status := p_receipt ->> 'status';
  if v_status is null
     or v_status not in ('ok', 'empty', 'source_wait', 'partial', 'failed') then
    raise exception using errcode = '22023', message = 'unsupported terminal status';
  end if;

  v_manifest_key := p_receipt ->> 'raw_manifest_object_key';
  v_expected_manifest_key := p_source_id || '/' || p_run_id::text
    || case when v_status = 'failed'
      then '/failure-manifest.json'
      else '/manifest.json'
    end;
  v_raw_prefix := p_source_id || '/' || p_run_id::text || '/';
  v_manifest_sha256 := pg_catalog.encode(
    extensions.digest(
      pg_catalog.convert_to(p_manifest::text, 'UTF8'),
      'sha256'
    ),
    'hex'
  );

  if v_manifest_key is distinct from v_expected_manifest_key then
    raise exception using
      errcode = '23514',
      message = 'private manifest key is not bound to source, run and status';
  end if;
  if p_manifest ->> 'source_id' is distinct from p_source_id
     or p_manifest ->> 'run_id' is distinct from p_run_id::text
     or p_manifest ->> 'manifest_version' is distinct from '1'
     or jsonb_typeof(p_manifest -> 'raw_objects') is distinct from 'array' then
    raise exception using
      errcode = '23514',
      message = 'manifest identity or raw object contract is invalid';
  end if;
  if p_manifest ->> 'started_at' is distinct from p_receipt ->> 'started_at'
     or p_manifest ->> 'observed_at' is distinct from p_receipt ->> 'observed_at'
     or p_manifest ->> 'completed_at' is distinct from p_receipt ->> 'completed_at'
     or coalesce((p_manifest ->> 'pages_attempted')::integer, -1)
       <> coalesce((p_receipt ->> 'pages_attempted')::integer, 0)
     or coalesce((p_manifest ->> 'pages_succeeded')::integer, -1)
       <> coalesce((p_receipt ->> 'pages_succeeded')::integer, 0)
     or coalesce((p_manifest ->> 'responses_observed')::integer, -1)
       <> coalesce((p_receipt ->> 'responses_observed')::integer, 0)
     or coalesce((p_manifest ->> 'rows_observed')::bigint, -1)
       <> coalesce((p_receipt ->> 'rows_observed')::bigint, 0)
     or coalesce(p_manifest -> 'outcomes', '[]'::jsonb)
       is distinct from coalesce(p_receipt -> 'outcomes', '[]'::jsonb) then
    raise exception using
      errcode = '23514',
      message = 'manifest header does not match the terminal receipt';
  end if;
  if (
    v_status <> 'failed'
    and pg_catalog.jsonb_array_length(p_manifest -> 'raw_objects')
      <> coalesce((p_receipt ->> 'responses_observed')::integer, 0)
  ) or (
    v_status = 'failed'
    and pg_catalog.jsonb_array_length(p_manifest -> 'raw_objects')
      > coalesce((p_receipt ->> 'responses_observed')::integer, 0)
  ) then
    raise exception using
      errcode = '23514',
      message = 'manifest raw object count is inconsistent with observed responses';
  end if;
  if exists (
    select 1
    from pg_catalog.jsonb_array_elements(p_manifest -> 'raw_objects')
      as raw_object(value)
    where pg_catalog.jsonb_typeof(raw_object.value) <> 'object'
       or raw_object.value ->> 'key' is null
       or pg_catalog.left(
         raw_object.value ->> 'key',
         pg_catalog.length(v_raw_prefix)
       )
         <> v_raw_prefix
       or raw_object.value ->> 'key' = v_manifest_key
       or position('?' in raw_object.value ->> 'key') <> 0
       or position(E'\n' in raw_object.value ->> 'key') <> 0
       or coalesce(raw_object.value ->> 'sha256', '') !~ '^[0-9a-f]{64}$'
       or coalesce(raw_object.value ->> 'bytes', '') !~ '^[0-9]+$'
  ) then
    raise exception using
      errcode = '23514',
      message = 'manifest contains an invalid raw object entry';
  end if;
  if (
    select count(*)
    from pg_catalog.jsonb_array_elements(p_manifest -> 'raw_objects')
      as raw_object(value)
  ) <> (
    select count(distinct raw_object.value ->> 'key')
    from pg_catalog.jsonb_array_elements(p_manifest -> 'raw_objects')
      as raw_object(value)
  ) then
    raise exception using
      errcode = '23514',
      message = 'manifest contains duplicate raw object keys';
  end if;
  if not exists (
    select 1 from storage.objects
    where bucket_id = 'fl-signal-source-evidence'
      and name = v_manifest_key
  ) then
    raise exception using
      errcode = '23503',
      message = 'private raw-evidence manifest does not exist';
  end if;
  if exists (
    select 1
    from pg_catalog.jsonb_array_elements(p_manifest -> 'raw_objects')
      as raw_object(value)
    where not exists (
      select 1
      from storage.objects stored
      where stored.bucket_id = 'fl-signal-source-evidence'
        and stored.name = raw_object.value ->> 'key'
    )
  ) then
    raise exception using
      errcode = '23503',
      message = 'a manifest-referenced raw evidence object does not exist';
  end if;

  v_source_metadata := coalesce(p_receipt -> 'source_metadata', '{}'::jsonb);
  if pg_catalog.jsonb_typeof(v_source_metadata) <> 'object' then
    raise exception using errcode = '23514', message = 'source_metadata must be an object';
  end if;
  -- Persist a database-owned canonical copy in the immutable receipt. Its
  -- digest is authoritative; the Storage object is the separately retained
  -- human-readable representation and every referenced raw object is checked.
  v_source_metadata := v_source_metadata || pg_catalog.jsonb_build_object(
    'raw_manifest', p_manifest,
    'raw_manifest_hash_basis', 'postgres-jsonb-text-v1'
  );

  -- Canonical caller-owned receipt projection. Database-derived write counts,
  -- the identity, and created_at are intentionally excluded. A retry is
  -- idempotent only when every other immutable field is identical.
  v_expected_receipt := pg_catalog.jsonb_build_object(
    'run_id', p_run_id,
    'source_id', p_source_id,
    'collector_name', p_receipt ->> 'collector_name',
    'collector_version', p_receipt ->> 'collector_version',
    'parser_version', p_receipt ->> 'parser_version',
    'normalizer_version', p_receipt ->> 'normalizer_version',
    'status', v_status,
    'reason_code', nullif(p_receipt ->> 'reason_code', ''),
    'reason_detail', nullif(p_receipt ->> 'reason_detail', ''),
    'started_at', (p_receipt ->> 'started_at')::timestamptz,
    'observed_at', (p_receipt ->> 'observed_at')::timestamptz,
    'completed_at', (p_receipt ->> 'completed_at')::timestamptz,
    'attempted_event_from',
      nullif(p_receipt ->> 'attempted_event_from', '')::timestamptz,
    'attempted_event_through',
      nullif(p_receipt ->> 'attempted_event_through', '')::timestamptz,
    'event_through', nullif(p_receipt ->> 'event_through', '')::timestamptz,
    'pages_attempted', coalesce((p_receipt ->> 'pages_attempted')::integer, 0),
    'pages_succeeded', coalesce((p_receipt ->> 'pages_succeeded')::integer, 0),
    'responses_observed',
      coalesce((p_receipt ->> 'responses_observed')::integer, 0),
    'rows_observed', coalesce((p_receipt ->> 'rows_observed')::integer, 0),
    'rows_rejected', coalesce((p_receipt ->> 'rows_rejected')::integer, 0),
    'schema_contract_sha256', p_receipt ->> 'schema_contract_sha256',
    'source_schema_sha256', nullif(p_receipt ->> 'source_schema_sha256', ''),
    'raw_manifest_sha256', v_manifest_sha256,
    'raw_manifest_object_key', v_manifest_key,
    'outcomes', coalesce(p_receipt -> 'outcomes', '[]'::jsonb),
    'source_metadata', v_source_metadata
  );

  select * into v_existing
  from public.external_source_run_receipts
  where run_id = p_run_id;

  if found then
    if v_existing.source_id <> p_source_id then
      raise exception using errcode = '23505', message = 'run_id belongs to another source';
    end if;
    if (
      to_jsonb(v_existing) - array[
        'id', 'rows_accepted', 'rows_inserted', 'rows_updated',
        'rows_unchanged', 'created_at'
      ]::text[]
    ) is distinct from v_expected_receipt then
      raise exception using errcode = '23514', message = 'idempotent replay payload differs';
    end if;
    if exists (
      select 1 from public.external_source_run_stage
      where source_id = p_source_id and run_id = p_run_id
    ) then
      raise exception using errcode = '55000', message = 'committed run has staged rows';
    end if;
    return jsonb_build_object(
      'run_id', v_existing.run_id,
      'source_id', v_existing.source_id,
      'status', v_existing.status,
      'rows_inserted', v_existing.rows_inserted,
      'rows_updated', v_existing.rows_updated,
      'rows_unchanged', v_existing.rows_unchanged,
      'idempotent_replay', true
    );
  end if;

  v_rows_observed := coalesce((p_receipt ->> 'rows_observed')::bigint, 0);
  v_rows_rejected := coalesce((p_receipt ->> 'rows_rejected')::bigint, 0);

  select count(*) into v_stage_count
  from public.external_source_run_stage
  where source_id = p_source_id and run_id = p_run_id;

  -- A staging/upload failure may leave a prefix of the run in the recoverable
  -- stage. A terminal failed receipt commits none of it; discard that prefix
  -- inside this same transaction before enforcing the accounting identity.
  if v_status = 'failed' and v_stage_count <> 0 then
    delete from public.external_source_run_stage
    where source_id = p_source_id and run_id = p_run_id;
    v_stage_count := 0;
  end if;

  if v_rows_observed <> v_stage_count + v_rows_rejected then
    raise exception using
      errcode = '23514',
      message = 'receipt rows_observed does not match staged plus rejected rows';
  end if;
  if v_status in ('empty', 'source_wait') and v_stage_count <> 0 then
    raise exception using
      errcode = '23514',
      message = 'non-committing terminal status cannot contain staged source rows';
  end if;
  if v_status <> 'failed' and (
    coalesce((p_manifest ->> 'rows_observed')::bigint, -1) <> v_rows_observed
    or coalesce((p_manifest ->> 'rows_staged')::bigint, -1) <> v_stage_count
    or coalesce((p_manifest ->> 'rows_rejected')::bigint, -1) <> v_rows_rejected
  ) then
    raise exception using
      errcode = '23514',
      message = 'manifest accounting does not match the staged run receipt';
  end if;

  if p_source_id = 'fdep_erp' then
    if exists (
      select 1
      from public.external_source_run_stage s
      cross join lateral jsonb_populate_record(null::public.fdep_erp, s.row_data) p
      where s.source_id = p_source_id and s.run_id = p_run_id
        and (
          s.row_data - array[
            'layer_id','objectid','permit_id','application_id','project_id',
            'project_name','applicant_name','applicant_company','permit_type',
            'permit_status','defined_status','division','permitting_program',
            'district','office_abbrev','location_id','location_name',
            'street_address','city','state','zip5','zip4','received_date',
            'agency_action','agency_action_date','documents_url','lat','lon','raw'
          ]::text[] <> '{}'::jsonb
          or p.layer_id is null
          or p.objectid is null
          or s.row_key <> p.layer_id::text || ':' || p.objectid::text
        )
    ) then
      raise exception using errcode = '23514', message = 'invalid staged FDEP row contract';
    end if;

    with parsed as materialized (
      select p.*
      from public.external_source_run_stage s
      cross join lateral jsonb_populate_record(null::public.fdep_erp, s.row_data) p
      where s.source_id = p_source_id and s.run_id = p_run_id
    )
    select
      count(*) filter (where e.layer_id is null),
      count(*) filter (
        where e.layer_id is not null
          and (to_jsonb(e) - array['first_fetched_at','last_fetched_at']::text[])
            is distinct from
              (to_jsonb(p) - array['first_fetched_at','last_fetched_at']::text[])
      ),
      count(*) filter (
        where e.layer_id is not null
          and (to_jsonb(e) - array['first_fetched_at','last_fetched_at']::text[])
            is not distinct from
              (to_jsonb(p) - array['first_fetched_at','last_fetched_at']::text[])
      )
    into v_rows_inserted, v_rows_updated, v_rows_unchanged
    from parsed p
    left join public.fdep_erp e
      on e.layer_id = p.layer_id and e.objectid = p.objectid;

    insert into public.fdep_erp (
      layer_id, objectid, permit_id, application_id, project_id, project_name,
      applicant_name, applicant_company, permit_type, permit_status,
      defined_status, division, permitting_program, district, office_abbrev,
      location_id, location_name, street_address, city, state, zip5, zip4,
      received_date, agency_action, agency_action_date, documents_url,
      lat, lon, raw, first_fetched_at, last_fetched_at
    )
    select
      p.layer_id, p.objectid, p.permit_id, p.application_id, p.project_id,
      p.project_name, p.applicant_name, p.applicant_company, p.permit_type,
      p.permit_status, p.defined_status, p.division, p.permitting_program,
      p.district, p.office_abbrev, p.location_id, p.location_name,
      p.street_address, p.city, p.state, p.zip5, p.zip4, p.received_date,
      p.agency_action, p.agency_action_date, p.documents_url, p.lat, p.lon,
      p.raw, now(), now()
    from public.external_source_run_stage s
    cross join lateral jsonb_populate_record(null::public.fdep_erp, s.row_data) p
    where s.source_id = p_source_id and s.run_id = p_run_id
    order by p.layer_id, p.objectid
    on conflict (layer_id, objectid) do update set
      permit_id = excluded.permit_id,
      application_id = excluded.application_id,
      project_id = excluded.project_id,
      project_name = excluded.project_name,
      applicant_name = excluded.applicant_name,
      applicant_company = excluded.applicant_company,
      permit_type = excluded.permit_type,
      permit_status = excluded.permit_status,
      defined_status = excluded.defined_status,
      division = excluded.division,
      permitting_program = excluded.permitting_program,
      district = excluded.district,
      office_abbrev = excluded.office_abbrev,
      location_id = excluded.location_id,
      location_name = excluded.location_name,
      street_address = excluded.street_address,
      city = excluded.city,
      state = excluded.state,
      zip5 = excluded.zip5,
      zip4 = excluded.zip4,
      received_date = excluded.received_date,
      agency_action = excluded.agency_action,
      agency_action_date = excluded.agency_action_date,
      documents_url = excluded.documents_url,
      lat = excluded.lat,
      lon = excluded.lon,
      raw = excluded.raw,
      last_fetched_at = excluded.last_fetched_at;

  elsif p_source_id = 'faa_oeaaa' then
    if exists (
      select 1
      from public.external_source_run_stage s
      cross join lateral jsonb_populate_record(null::public.faa_oeaaa, s.row_data) p
      where s.source_id = p_source_id and s.run_id = p_run_id
        and (
          s.row_data - array[
            'asn','case_id','case_type','year','date_entered','date_completed',
            'expiration_date','received_date','status_code','structure_type',
            'structure_description','agl_height','agl_height_det','amsl_height',
            'sponsor','sponsor_city','sponsor_state','nearest_airport',
            'nearest_city','nearest_state','lat','lon','in_broward','raw'
          ]::text[] <> '{}'::jsonb
          or p.asn is null
          or btrim(p.asn) = ''
          or s.row_key <> p.asn
        )
    ) then
      raise exception using errcode = '23514', message = 'invalid staged FAA row contract';
    end if;

    with parsed as materialized (
      select p.*
      from public.external_source_run_stage s
      cross join lateral jsonb_populate_record(null::public.faa_oeaaa, s.row_data) p
      where s.source_id = p_source_id and s.run_id = p_run_id
    )
    select
      count(*) filter (where e.asn is null),
      count(*) filter (
        where e.asn is not null
          and (to_jsonb(e) - array['first_fetched_at','last_fetched_at']::text[])
            is distinct from
              (to_jsonb(p) - array['first_fetched_at','last_fetched_at']::text[])
      ),
      count(*) filter (
        where e.asn is not null
          and (to_jsonb(e) - array['first_fetched_at','last_fetched_at']::text[])
            is not distinct from
              (to_jsonb(p) - array['first_fetched_at','last_fetched_at']::text[])
      )
    into v_rows_inserted, v_rows_updated, v_rows_unchanged
    from parsed p
    left join public.faa_oeaaa e on e.asn = p.asn;

    insert into public.faa_oeaaa (
      asn, case_id, case_type, year, date_entered, date_completed,
      expiration_date, received_date, status_code, structure_type,
      structure_description, agl_height, agl_height_det, amsl_height,
      sponsor, sponsor_city, sponsor_state, nearest_airport, nearest_city,
      nearest_state, lat, lon, in_broward, raw, first_fetched_at,
      last_fetched_at
    )
    select
      p.asn, p.case_id, p.case_type, p.year, p.date_entered,
      p.date_completed, p.expiration_date, p.received_date, p.status_code,
      p.structure_type, p.structure_description, p.agl_height,
      p.agl_height_det, p.amsl_height, p.sponsor, p.sponsor_city,
      p.sponsor_state, p.nearest_airport, p.nearest_city, p.nearest_state,
      p.lat, p.lon, p.in_broward, p.raw, now(), now()
    from public.external_source_run_stage s
    cross join lateral jsonb_populate_record(null::public.faa_oeaaa, s.row_data) p
    where s.source_id = p_source_id and s.run_id = p_run_id
    order by p.asn
    on conflict (asn) do update set
      case_id = excluded.case_id,
      case_type = excluded.case_type,
      year = excluded.year,
      date_entered = excluded.date_entered,
      date_completed = excluded.date_completed,
      expiration_date = excluded.expiration_date,
      received_date = excluded.received_date,
      status_code = excluded.status_code,
      structure_type = excluded.structure_type,
      structure_description = excluded.structure_description,
      agl_height = excluded.agl_height,
      agl_height_det = excluded.agl_height_det,
      amsl_height = excluded.amsl_height,
      sponsor = excluded.sponsor,
      sponsor_city = excluded.sponsor_city,
      sponsor_state = excluded.sponsor_state,
      nearest_airport = excluded.nearest_airport,
      nearest_city = excluded.nearest_city,
      nearest_state = excluded.nearest_state,
      lat = excluded.lat,
      lon = excluded.lon,
      in_broward = excluded.in_broward,
      raw = excluded.raw,
      last_fetched_at = excluded.last_fetched_at;
  end if;

  if v_rows_inserted + v_rows_updated + v_rows_unchanged <> v_stage_count then
    raise exception using errcode = '23514', message = 'source write accounting failed';
  end if;

  insert into public.external_source_run_receipts (
    run_id, source_id, collector_name, collector_version, parser_version,
    normalizer_version, status, reason_code, reason_detail, started_at,
    observed_at, completed_at, attempted_event_from,
    attempted_event_through, event_through, pages_attempted,
    pages_succeeded, responses_observed, rows_observed, rows_accepted,
    rows_inserted, rows_updated, rows_unchanged, rows_rejected,
    schema_contract_sha256, source_schema_sha256, raw_manifest_sha256,
    raw_manifest_object_key, outcomes, source_metadata
  ) values (
    p_run_id, p_source_id, p_receipt ->> 'collector_name',
    p_receipt ->> 'collector_version', p_receipt ->> 'parser_version',
    p_receipt ->> 'normalizer_version', v_status,
    nullif(p_receipt ->> 'reason_code', ''),
    nullif(p_receipt ->> 'reason_detail', ''),
    (p_receipt ->> 'started_at')::timestamptz,
    (p_receipt ->> 'observed_at')::timestamptz,
    (p_receipt ->> 'completed_at')::timestamptz,
    nullif(p_receipt ->> 'attempted_event_from', '')::timestamptz,
    nullif(p_receipt ->> 'attempted_event_through', '')::timestamptz,
    nullif(p_receipt ->> 'event_through', '')::timestamptz,
    coalesce((p_receipt ->> 'pages_attempted')::integer, 0),
    coalesce((p_receipt ->> 'pages_succeeded')::integer, 0),
    coalesce((p_receipt ->> 'responses_observed')::integer, 0),
    v_rows_observed, v_stage_count, v_rows_inserted, v_rows_updated,
    v_rows_unchanged, v_rows_rejected,
    p_receipt ->> 'schema_contract_sha256',
    nullif(p_receipt ->> 'source_schema_sha256', ''),
    v_manifest_sha256, v_manifest_key,
    coalesce(p_receipt -> 'outcomes', '[]'::jsonb),
    v_source_metadata
  );

  delete from public.external_source_run_stage
  where source_id = p_source_id and run_id = p_run_id;

  return jsonb_build_object(
    'run_id', p_run_id,
    'source_id', p_source_id,
    'status', v_status,
    'rows_accepted', v_stage_count,
    'rows_inserted', v_rows_inserted,
    'rows_updated', v_rows_updated,
    'rows_unchanged', v_rows_unchanged,
    'rows_rejected', v_rows_rejected,
    'idempotent_replay', false
  );
end
$$;

comment on column public.external_source_run_receipts.raw_manifest_sha256 is
  'Database-computed SHA-256 of source_metadata.raw_manifest using canonical PostgreSQL jsonb text (postgres-jsonb-text-v1).';

comment on function public.fs_commit_external_source_run(text, uuid, jsonb, jsonb) is
  'SECURITY INVOKER atomic source-row plus immutable-receipt commit. Serializes by source, validates an exact run-bound private Storage manifest and referenced objects, and retains a database-owned canonical manifest copy.';

revoke all on function public.fs_commit_external_source_run(text, uuid, jsonb, jsonb)
  from public, anon, authenticated, service_role;
grant execute on function public.fs_commit_external_source_run(text, uuid, jsonb, jsonb)
  to service_role;
