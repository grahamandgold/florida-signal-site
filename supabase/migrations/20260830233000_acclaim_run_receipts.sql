-- Durable, source-scoped run receipts for the native-Mac Acclaim collector.
-- CODE ONLY: applying this migration is a separate production approval.

create table if not exists public.broward_clerk_preliminary_run (
  id bigint generated always as identity primary key,
  run_id uuid not null unique,
  collector text not null default 'acclaim-mac-launchagent',
  status text not null check (status in ('ok', 'empty', 'source_wait', 'failed')),
  started_at timestamptz not null,
  completed_at timestamptz not null,
  observed_at timestamptz not null,
  attempted_from date,
  attempted_through date,
  event_through date,
  verified_through date,
  dates_attempted integer not null default 0 check (dates_attempted >= 0),
  rows_observed integer not null default 0 check (rows_observed >= 0),
  rows_new integer not null default 0 check (rows_new >= 0),
  reason text,
  outcomes jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  constraint clerk_prelim_run_time_order check (
    started_at <= observed_at and observed_at <= completed_at
  ),
  constraint clerk_prelim_run_attempt_order check (
    attempted_from is null or attempted_through is null or attempted_from <= attempted_through
  ),
  constraint clerk_prelim_run_event_bound check (
    event_through is null or attempted_through is null or event_through <= attempted_through
  ),
  constraint clerk_prelim_run_count_bound check (rows_new <= rows_observed),
  constraint clerk_prelim_run_outcomes_array check (jsonb_typeof(outcomes) = 'array')
);

comment on table public.broward_clerk_preliminary_run is
  'Append-only Acclaim collector run receipts. Event coverage, attempted coverage and system/run time are separate clocks; an unchanged or empty poll still produces a receipt.';
comment on column public.broward_clerk_preliminary_run.event_through is
  'Newest real-world record_date with one or more observed source rows; never advanced by an empty poll.';
comment on column public.broward_clerk_preliminary_run.attempted_through is
  'Newest source date queried during this run, including explicit empty and source-wait outcomes.';
comment on column public.broward_clerk_preliminary_run.observed_at is
  'UTC time of the final source response represented by this receipt.';

create index if not exists clerk_prelim_run_completed_idx
  on public.broward_clerk_preliminary_run (completed_at desc);

alter table public.broward_clerk_preliminary_run enable row level security;

revoke all on table public.broward_clerk_preliminary_run from anon, authenticated;
grant usage on schema public to anon, authenticated, service_role;
grant select on table public.broward_clerk_preliminary_run to anon, authenticated;
revoke update, delete, truncate, references, trigger
  on table public.broward_clerk_preliminary_run from service_role;
grant select, insert on table public.broward_clerk_preliminary_run to service_role;
grant usage, select on sequence public.broward_clerk_preliminary_run_id_seq to service_role;

drop policy if exists clerk_prelim_run_public_read on public.broward_clerk_preliminary_run;
create policy clerk_prelim_run_public_read
  on public.broward_clerk_preliminary_run
  for select
  to anon, authenticated
  using (true);

-- Rollback (approval-gated; removes only run receipts, never preliminary or verified records):
-- drop table if exists public.broward_clerk_preliminary_run;
