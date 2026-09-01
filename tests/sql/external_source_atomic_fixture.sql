\set ON_ERROR_STOP on

create schema extensions;
create extension pgcrypto with schema extensions;
create schema storage;
create schema cron;
create schema net;
create schema vault;

create role anon nologin;
create role authenticated nologin;
create role service_role nologin bypassrls;

-- Minimal disposable implementations of the extension-owned objects used by
-- the schedule cutover. They execute the migration and its owner functions;
-- no network request or host scheduler is involved in this test database.
create table cron.job (
  jobid bigint generated always as identity primary key,
  jobname text not null unique,
  schedule text not null,
  command text not null,
  active boolean not null default true
);

create or replace function cron.schedule(
  job_name text,
  job_schedule text,
  job_command text
)
returns bigint
language plpgsql
as $$
declare
  v_jobid bigint;
begin
  insert into cron.job (jobname, schedule, command)
  values (job_name, job_schedule, job_command)
  on conflict (jobname) do update set
    schedule = excluded.schedule,
    command = excluded.command,
    active = true
  returning jobid into v_jobid;
  return v_jobid;
end
$$;

create or replace function cron.unschedule(job_id bigint)
returns boolean
language plpgsql
as $$
declare
  v_deleted bigint;
begin
  delete from cron.job where jobid = job_id;
  get diagnostics v_deleted = row_count;
  return v_deleted = 1;
end
$$;

create table net.http_requests (
  request_id bigint generated always as identity primary key,
  url text not null,
  body jsonb not null,
  params jsonb not null,
  headers jsonb not null,
  timeout_milliseconds integer not null
);

create or replace function net.http_post(
  url text,
  body jsonb default '{}'::jsonb,
  params jsonb default '{}'::jsonb,
  headers jsonb default '{}'::jsonb,
  timeout_milliseconds integer default 1000
)
returns bigint
language plpgsql
as $$
declare
  v_request_id bigint;
begin
  insert into net.http_requests (
    url, body, params, headers, timeout_milliseconds
  ) values (
    $1, $2, $3, $4, $5
  ) returning request_id into v_request_id;
  return v_request_id;
end
$$;

create table vault.decrypted_secrets (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  name text not null unique,
  decrypted_secret text not null
);

insert into vault.decrypted_secrets (name, decrypted_secret) values
  ('fl_signal_functions_base_url',
   'https://fixture-project.supabase.co/functions/v1'),
  ('fl_signal_external_source_sync_key',
   'fixture-only-key-at-least-32-characters-long');

grant usage on schema public, storage, extensions to service_role;
grant execute on function extensions.digest(bytea, text) to service_role;

create table storage.objects (
  bucket_id text not null,
  name text not null,
  primary key (bucket_id, name)
);
grant select on storage.objects to service_role;

create table public.fdep_erp (
  layer_id smallint not null,
  objectid integer not null,
  permit_id text,
  application_id text,
  project_id integer,
  project_name text,
  applicant_name text,
  applicant_company text,
  permit_type text,
  permit_status text,
  defined_status text,
  division text,
  permitting_program text,
  district text,
  office_abbrev text,
  location_id text,
  location_name text,
  street_address text,
  city text,
  state text,
  zip5 text,
  zip4 text,
  received_date date,
  agency_action text,
  agency_action_date date,
  documents_url text,
  lat double precision,
  lon double precision,
  raw jsonb,
  first_fetched_at timestamptz not null default now(),
  last_fetched_at timestamptz not null default now(),
  primary key (layer_id, objectid)
);

create table public.faa_oeaaa (
  asn text primary key,
  case_id bigint,
  case_type text,
  year integer,
  date_entered date,
  date_completed date,
  expiration_date date,
  received_date timestamptz,
  status_code text,
  structure_type text,
  structure_description text,
  agl_height integer,
  agl_height_det integer,
  amsl_height integer,
  sponsor text,
  sponsor_city text,
  sponsor_state text,
  nearest_airport text,
  nearest_city text,
  nearest_state text,
  lat double precision,
  lon double precision,
  in_broward boolean generated always as (
    lat >= 25.94 and lat <= 26.35 and lon >= -80.5 and lon <= -80.05
  ) stored,
  raw jsonb,
  first_fetched_at timestamptz not null default now(),
  last_fetched_at timestamptz not null default now()
);

grant select, insert, update on public.fdep_erp, public.faa_oeaaa
  to service_role;

create table public.external_source_run_receipts (
  id bigint generated always as identity primary key,
  run_id uuid not null unique,
  source_id text not null check (source_id in ('fdep_erp', 'faa_oeaaa')),
  collector_name text not null,
  collector_version text not null,
  parser_version text not null,
  normalizer_version text not null,
  status text not null check (status in ('ok', 'empty', 'source_wait', 'partial', 'failed')),
  reason_code text,
  reason_detail text,
  started_at timestamptz not null,
  observed_at timestamptz not null,
  completed_at timestamptz not null,
  attempted_event_from timestamptz,
  attempted_event_through timestamptz,
  event_through timestamptz,
  pages_attempted integer not null default 0,
  pages_succeeded integer not null default 0,
  responses_observed integer not null default 0,
  rows_observed integer not null default 0,
  rows_accepted integer not null default 0,
  rows_inserted integer not null default 0,
  rows_updated integer not null default 0,
  rows_unchanged integer not null default 0,
  rows_rejected integer not null default 0,
  schema_contract_sha256 text not null check (schema_contract_sha256 ~ '^[0-9a-f]{64}$'),
  source_schema_sha256 text check (
    source_schema_sha256 is null or source_schema_sha256 ~ '^[0-9a-f]{64}$'
  ),
  raw_manifest_sha256 text not null check (raw_manifest_sha256 ~ '^[0-9a-f]{64}$'),
  raw_manifest_object_key text not null,
  outcomes jsonb not null default '[]'::jsonb,
  source_metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  check (pages_succeeded <= pages_attempted),
  check (rows_observed = rows_accepted + rows_rejected),
  check (rows_accepted = rows_inserted + rows_updated + rows_unchanged),
  check (status not in ('ok', 'empty', 'partial') or source_schema_sha256 is not null)
);

alter table public.external_source_run_receipts enable row level security;
alter table public.external_source_run_receipts force row level security;
revoke all on public.external_source_run_receipts
  from public, anon, authenticated, service_role;
grant select, insert on public.external_source_run_receipts to service_role;
grant usage, select on sequence public.external_source_run_receipts_id_seq
  to service_role;

create or replace function public.test_assert(p_condition boolean, p_message text)
returns void
language plpgsql
as $$
begin
  if p_condition is not true then
    raise exception 'assertion failed: %', p_message;
  end if;
end
$$;
grant execute on function public.test_assert(boolean, text) to service_role;
