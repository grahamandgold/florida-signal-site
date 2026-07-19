-- 009 — Isolated editorial review queue.
-- Deliberately separate from brief_candidate_registry / brief_publication_registry (the frozen
-- shadow-scorer registries). Nothing here feeds the scorer and the scorer does not read this.
-- APPROVED records an editorial decision. It publishes nothing.
create table if not exists public.signal_review_queue (
  queue_id           bigserial primary key,
  signal_id          text not null unique,
  signal_type        text,
  source_table       text not null,
  source_record_id   text not null,
  source_record_date date,
  layer              text,
  verified_parcel_id text,
  latitude           double precision,
  longitude          double precision,
  amount             numeric,
  generated_headline text,
  generated_summary  text,
  editor_headline    text,
  editor_summary     text,
  editor_notes       text,
  assigned_reviewer  text,
  review_status      text not null default 'NEW',
  destinations       text[] not null default '{}',
  decided_at         timestamptz,
  decided_by         text,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  constraint review_status_values check (review_status in
    ('NEW','REVIEWING','HOLD','APPROVED','REJECTED','NEEDS_MORE_REPORTING')),
  constraint destination_values check (destinations <@ ARRAY[
    'live_signals_map','signals_page','daily_intel_brief','neighborhood_page','broward_record']::text[])
);
create index if not exists idx_review_status on public.signal_review_queue(review_status);
create index if not exists idx_review_date on public.signal_review_queue(source_record_date desc);

-- No anon policy: the queue is editorial and stays private. Service role only, proxied by the desk.
alter table public.signal_review_queue enable row level security;

create or replace function public.fs_touch_review_queue() returns trigger language plpgsql as $$
begin new.updated_at := now(); return new; end $$;
drop trigger if exists trg_touch_review_queue on public.signal_review_queue;
create trigger trg_touch_review_queue before update on public.signal_review_queue
  for each row execute function public.fs_touch_review_queue();
