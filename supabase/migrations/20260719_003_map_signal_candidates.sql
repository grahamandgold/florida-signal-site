-- Florida Signal · map-derived editorial review queue (SignalV1)
-- Idempotent. Mirrors live definitions in project jrjewmzkyluxdywyusrw as of 2026-07-19.
-- ISOLATION: intentionally separate from brief_candidate_registry / brief_publication_registry,
-- which belong to the FROZEN shadow-scorer workflow and the open five-run gate.
-- No FK, no trigger, no shared key space, no delivery tracking. Additive. Reversible: DROP TABLE.
create table if not exists public.map_signal_candidates (
  queue_id bigint generated always as identity primary key,
  signal_id text not null,
  signal_version text not null default 'SignalV1',
  source_name text not null,
  source_record_id text not null,
  source_table text,
  source_record_url text,
  source_record_date date,
  proposed_headline text,
  proposed_summary text,
  why_it_matters text,
  what_to_watch text,
  caveat text,
  evidence_summary text,
  verification_status text not null default 'PRELIMINARY',
  editorial_priority integer not null default 0,
  review_status text not null default 'NEW',
  assigned_to text,
  hold_reason text,
  rejection_reason text,
  editor_notes text,
  publication_destinations text[] not null default '{}',
  latitude double precision,
  longitude double precision,
  municipality text,
  map_context jsonb,
  evidence_ref jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  reviewed_at timestamptz,
  constraint map_signal_candidates_review_status_ck
    check (review_status in ('NEW','REVIEWING','HOLD','APPROVED','REJECTED','NEEDS_MORE_REPORTING')),
  constraint map_signal_candidates_verification_ck
    check (verification_status in ('PRELIMINARY','VERIFIED','CONFLICT','NEEDS_REVIEW'))
);
comment on table public.map_signal_candidates is
  'Editorial review queue for map-derived SignalV1 candidates. ISOLATED from the frozen shadow-scorer registries. Nothing publishes automatically; APPROVED only marks a Signal publication-ready for a named destination.';
create unique index if not exists map_signal_candidates_signal_uniq on public.map_signal_candidates (signal_id);
create index if not exists map_signal_candidates_review_idx on public.map_signal_candidates (review_status, editorial_priority desc);
create index if not exists map_signal_candidates_created_idx on public.map_signal_candidates (created_at desc);
alter table public.map_signal_candidates enable row level security;
drop policy if exists map_signal_candidates_read on public.map_signal_candidates;
create policy map_signal_candidates_read on public.map_signal_candidates for select using (true);

-- ROLLBACK (documented, NOT executed):
--   drop table if exists public.map_signal_candidates;
