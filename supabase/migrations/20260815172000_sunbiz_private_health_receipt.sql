-- Publish only a sanitized freshness receipt for the private exact-match Sunbiz corpus.
-- Entity rows remain RLS-protected; the public health endpoint never needs raw access.

create or replace function internal.refresh_sunbiz_health()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  exact_row_count bigint;
  latest_fetch timestamptz;
  freshness_status text;
  outcome jsonb;
begin
  select count(*)::bigint, max(fetched_at)
    into exact_row_count, latest_fetch
  from public.sunbiz_entities;

  freshness_status := case
    when latest_fetch is null then 'unavailable'
    when latest_fetch >= now() - interval '30 hours' then 'current'
    when latest_fetch >= now() - interval '54 hours' then 'delayed'
    else 'stale'
  end;

  outcome := jsonb_build_object(
    'exact_rows', exact_row_count,
    'latest_fetched_at', latest_fetch,
    'matching_policy', 'exact-only',
    'raw_rows_public', false
  );

  insert into public.editorial_pipeline_health
    (component, status, event_through, source_through, system_time, detail, metrics)
  values
    ('sunbiz-exact-resolver', freshness_status, null, latest_fetch::date,
     coalesce(latest_fetch, now()),
     case when latest_fetch is null
       then 'No private Sunbiz exact-match receipt is available.'
       else 'Private exact-match Sunbiz resolver refreshed; raw entity rows remain private.'
     end,
     outcome)
  on conflict (component) do update set
    status = excluded.status,
    event_through = excluded.event_through,
    source_through = excluded.source_through,
    system_time = excluded.system_time,
    detail = excluded.detail,
    metrics = excluded.metrics;

  return outcome;
exception when others then
  insert into public.editorial_pipeline_health
    (component, status, system_time, detail, metrics)
  values
    ('sunbiz-exact-resolver', 'error', now(),
     'Sunbiz health receipt refresh failed; private entity rows remain protected.',
     jsonb_build_object('sqlstate', sqlstate, 'error', left(sqlerrm, 300)))
  on conflict (component) do update set
    status = excluded.status,
    system_time = excluded.system_time,
    detail = excluded.detail,
    metrics = excluded.metrics;
  return jsonb_build_object('ok', false, 'sqlstate', sqlstate, 'error', left(sqlerrm, 300));
end
$$;

revoke all on function internal.refresh_sunbiz_health() from public, anon, authenticated;

select cron.unschedule('sunbiz-health-receipt')
where exists (select 1 from cron.job where jobname = 'sunbiz-health-receipt');
select cron.schedule(
  'sunbiz-health-receipt',
  '5 4 * * *',
  $$select internal.refresh_sunbiz_health();$$
);

select internal.refresh_sunbiz_health();

comment on function internal.refresh_sunbiz_health() is
  'Writes aggregate-only Sunbiz freshness to editorial_pipeline_health. Raw private entity rows are never exposed.';
