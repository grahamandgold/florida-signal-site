-- Owner-operated cron retains execution. Public dashboard reads are unchanged.
-- Verified caller: cron refresh_dashboard_cache, postgres, every three hours.
revoke execute on function public.refresh_dashboard_cache() from public, anon, authenticated;
grant execute on function public.refresh_dashboard_cache() to service_role;
