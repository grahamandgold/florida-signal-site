-- Bound lock acquisition and work; failure rolls the whole migration back.
-- Do not raise API/role timeouts, refresh the snapshot, or rewrite any source clock.
set local lock_timeout = '500ms';
set local statement_timeout = '15s';

do $$
begin
  if md5(pg_get_viewdef('public.broward_property_transfer_freshness'::regclass, true))
       <> '1fb1d7ba39389b8f36f02f7c426942c2'
     or not coalesce((select reloptions @> array['security_invoker=true']
                      from pg_class where oid = 'public.broward_property_transfer_freshness'::regclass), false)
  then
    raise exception 'Health clock source definition changed; re-review before installing';
  end if;
end
$$;

-- No IF NOT EXISTS: an unexpected same-name index is drift, not success.
create index idx_clerk_prelim_fetched_at
  on public.broward_clerk_preliminary (fetched_at desc)
  where fetched_at is not null;
create index idx_brc_doc_transfer_recording_date
  on public.broward_clerk_records_doc (recording_date_iso desc)
  where doc_type_code in ('D','EAS');
create index idx_ptm_recording_date
  on public.broward_property_transfer_map (recording_date desc);

-- WHERE enables a bounded MAX index lookup. FILTER requires scanning the corpus.
-- Aggregate semantics still return one NULL clock for empty/all-null sources.
-- CREATE OR REPLACE retains the existing grants and column comments.
create or replace view public.broward_property_transfer_freshness
with (security_invoker = true)
as
with source_clock as (
  select max(recording_date_iso) as source_event_through
  from public.broward_clerk_records_doc
  where doc_type_code in ('D','EAS')
), snapshot_clock as (
  select max(recording_date) as snapshot_event_through
  from public.broward_property_transfer_map
)
select
  source_event_through,
  snapshot_event_through,
  public.fs_business_days_between(snapshot_event_through, source_event_through) as snapshot_lag_business_days,
  public.fs_business_days_between(source_event_through, current_date) as source_age_business_days,
  coalesce(public.fs_business_days_between(snapshot_event_through, source_event_through) <= 2, false) as snapshot_is_current,
  coalesce(public.fs_business_days_between(snapshot_event_through, source_event_through) <= 2, false) as editorial_ready,
  coalesce(public.fs_business_days_between(source_event_through, current_date) <= 2, false) as source_is_current
from source_clock cross join snapshot_clock;

