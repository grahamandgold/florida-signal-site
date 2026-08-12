-- Make editorial decision-readiness a durable database fact rather than a UI guess.
-- A candidate can enter the approval path only after at least one source record has
-- been sealed into its evidence packet. The local desk and server both enforce this.

alter table public.signal_review_queue
  add column if not exists evidence_ready boolean
  generated always as (
    jsonb_typeof(evidence_packet) = 'object'
    and evidence_packet <> '{}'::jsonb
    and jsonb_array_length(coalesce(evidence_packet->'records', '[]'::jsonb)) > 0
  ) stored;

create index if not exists idx_review_status_evidence_priority
  on public.signal_review_queue (
    review_status,
    evidence_ready,
    source_record_date desc,
    amount desc nulls last
  );

comment on column public.signal_review_queue.evidence_ready is
  'Computed editorial gate: true only when the candidate carries a non-empty evidence packet with at least one source record.';
