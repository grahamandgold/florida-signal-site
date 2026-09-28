-- Apply as a new reviewed migration only if the installed repair needs rollback.
-- Retain source rows, materialized rows, clocks, grants, comments and migration history.
set local lock_timeout = '500ms';
set local statement_timeout = '15s';
do $$
begin
  if md5(pg_get_viewdef('public.broward_property_transfer_freshness'::regclass,true))
       <> '00d43006ad7f47db8afb11dd308f832a' then
    raise exception 'Health clock repair definition changed; re-review rollback';
  end if;
end
$$;
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

drop index public.idx_clerk_prelim_fetched_at;
drop index public.idx_brc_doc_transfer_recording_date;
drop index public.idx_ptm_recording_date;
