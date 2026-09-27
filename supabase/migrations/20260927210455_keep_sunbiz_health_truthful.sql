SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '15s';

CREATE OR REPLACE FUNCTION internal.refresh_sunbiz_health()
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
  exact_row_count bigint;
  total_row_count bigint;
  nonexact_row_count bigint;
  unmatched_row_count bigint;
  recent_errors bigint;
  recent_successes bigint;
  latest_fetch timestamptz;
  freshness_status text;
  outcome jsonb;
BEGIN
  SELECT count(*) FILTER (WHERE match_type = 'EXACT'), count(*),
         count(*) FILTER (WHERE match_type NOT IN ('EXACT', 'NONE', 'ERROR')),
         count(*) FILTER (WHERE match_type = 'NONE'),
         count(*) FILTER (WHERE match_type = 'ERROR' AND fetched_at > now() - interval '24 hours'),
         count(*) FILTER (WHERE match_type <> 'ERROR' AND fetched_at > now() - interval '24 hours'),
         max(fetched_at) FILTER (WHERE match_type <> 'ERROR')
    INTO exact_row_count, total_row_count, nonexact_row_count, unmatched_row_count,
         recent_errors, recent_successes, latest_fetch
    FROM public.sunbiz_entities
   WHERE source = 'sunbiz-sftp-corpus';

  -- Match the authoritative freshness manifest's 36-hour stale boundary.
  freshness_status := CASE
    WHEN recent_errors > recent_successes THEN 'error'
    WHEN latest_fetch IS NULL THEN 'unavailable'
    WHEN latest_fetch >= now() - interval '30 hours' THEN 'current'
    WHEN latest_fetch >= now() - interval '36 hours' THEN 'delayed'
    ELSE 'stale'
  END;
  outcome := jsonb_build_object(
    'exact_rows', exact_row_count,
    'total_resolver_rows', total_row_count,
    'unmatched_rows', unmatched_row_count,
    'nonexact_rows_excluded', nonexact_row_count,
    'latest_fetched_at', latest_fetch,
    'health_evaluated_at', now(),
    'recent_error_rows', recent_errors,
    'matching_policy', 'exact-only',
    'raw_rows_public', false,
    'current_hours', 30,
    'stale_after_hours', 36
  );
  INSERT INTO public.editorial_pipeline_health
    (component, status, event_through, source_through, system_time, detail, metrics)
  VALUES
    ('sunbiz-exact-resolver', freshness_status, NULL, latest_fetch::date,
     coalesce(latest_fetch, now()),
     CASE
       WHEN freshness_status = 'unavailable' THEN 'No successful private Sunbiz resolver observation is available.'
       WHEN freshness_status = 'error' THEN 'Recent private Sunbiz resolver errors exceed successful observations.'
       WHEN freshness_status = 'stale' THEN 'Private Sunbiz resolver observation is older than 36 hours; raw entity rows remain private.'
       WHEN freshness_status = 'delayed' THEN 'Private Sunbiz resolver observation is older than 30 hours; raw entity rows remain private.'
       ELSE 'Private Sunbiz resolver observation is current; only EXACT matches are counted as exact; raw entity rows remain private.'
     END, outcome)
  ON CONFLICT (component) DO UPDATE SET
    status = excluded.status, event_through = excluded.event_through,
    source_through = excluded.source_through, system_time = excluded.system_time,
    detail = excluded.detail, metrics = excluded.metrics;
  RETURN outcome;
EXCEPTION WHEN OTHERS THEN
  -- Do not put raw exception text or private entity data in a public summary.
  UPDATE public.editorial_pipeline_health
     SET status = 'error',
         detail = 'Sunbiz health evaluation failed; previous source clocks are retained.',
         metrics = metrics || jsonb_build_object('health_evaluated_at', now(), 'sqlstate', sqlstate)
   WHERE component = 'sunbiz-exact-resolver';
  RETURN jsonb_build_object('ok', false, 'sqlstate', sqlstate);
END;
$function$;

REVOKE ALL ON FUNCTION internal.refresh_sunbiz_health() FROM PUBLIC, anon, authenticated, service_role;
COMMENT ON FUNCTION internal.refresh_sunbiz_health() IS
  'Owner-only aggregate Sunbiz health. Re-evaluates source age; counts only EXACT corpus matches; never exposes raw entities.';

-- This refreshes a tiny aggregate health receipt, never a collector or AI job.
SELECT cron.alter_job(jobid, schedule := '5 * * * *')
  FROM cron.job WHERE jobname = 'sunbiz-health-receipt';
SELECT internal.refresh_sunbiz_health();
