-- A lag in the external verified Clerk publication window means "incomplete through today," not
-- "the older verified rows became false." Candidate packets may use those older rows as long as
-- the deed/parcel snapshot exactly tracks the ingested source and the source delay is disclosed.
create or replace view public.broward_property_transfer_freshness
with (security_invoker = true)
as
with source_clock as (
  select max(recording_date_iso) filter (where doc_type_code in ('D','EAS')) as source_event_through
  from public.broward_clerk_records_doc
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

revoke all on public.broward_property_transfer_freshness from anon, authenticated;
grant select on public.broward_property_transfer_freshness to anon, authenticated;

comment on column public.broward_property_transfer_freshness.editorial_ready is
  'True when the materialized snapshot is close enough to its ingested source for verified historical Candidate packets. source_is_current separately reports external feed delay.';

-- Tighten two legacy dependencies surfaced by the post-migration security advisor.
alter view public.broward_property_transfer_links set (security_invoker = true);
alter function public.fs_touch_review_queue() set search_path = '';
