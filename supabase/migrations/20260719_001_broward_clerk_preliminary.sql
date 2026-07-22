-- Florida Signal · Broward Clerk PRELIMINARY table (Acclaim public search)
-- Idempotent. Mirrors live definitions in project jrjewmzkyluxdywyusrw as of 2026-07-19.
-- Preliminary ≠ verified: rows stay 'preliminary' until reconciled to the authoritative SFTP feed.

create table if not exists public.broward_clerk_preliminary (
  id bigint generated always as identity primary key,
  record_date date not null,
  instrument_number text not null default '',
  doc_type text,
  first_direct_name text,
  first_indirect_name text,
  book_type text,
  book_page text,
  legal_snippet text,
  source text not null default 'acclaimweb-public-search',
  fetched_at timestamptz not null default now()
);

comment on table public.broward_clerk_preliminary is
  'PRELIMINARY same/next-day Broward recordings read from the Clerk''s public AcclaimWeb search (released ~3-4 days ahead of the QA''d SFTP files). Event date = record_date. Rows are unverified until the matching business_date arrives in broward_clerk_records_doc. Additive; reversible: DROP TABLE.';

create unique index if not exists clerk_prelim_uniq
  on public.broward_clerk_preliminary (record_date, instrument_number)
  where instrument_number <> '';
create index if not exists clerk_prelim_date_idx on public.broward_clerk_preliminary (record_date desc);
create index if not exists clerk_prelim_type_idx on public.broward_clerk_preliminary (doc_type);

alter table public.broward_clerk_preliminary enable row level security;

-- Public read only (public-record data). Writes require the service role, which bypasses RLS.
drop policy if exists clerk_prelim_public_read on public.broward_clerk_preliminary;
create policy clerk_prelim_public_read on public.broward_clerk_preliminary for select using (true);
