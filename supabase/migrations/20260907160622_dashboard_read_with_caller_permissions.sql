-- The public dashboard already has explicit read grants and SELECT policies.
-- Its read-only wrapper does not need the owner's elevated privileges.
do $$
begin
  if not exists (
    select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace
    join pg_language l on l.oid=p.prolang
    where n.nspname='public' and p.proname='get_dashboard' and p.pronargs=0
      and p.prorettype='jsonb'::regtype and l.lanname='sql'
      and btrim(regexp_replace(p.prosrc, '\s+', ' ', 'g')) =
          'select payload from public.dashboard_cache where id=1;'
  ) then raise exception 'Dashboard wrapper differs from the reviewed read-only definition'; end if;
end $$;

alter function public.get_dashboard() security invoker;

-- Exercise both public callers under their real grants and RLS policies.
set local role anon;
do $$
begin
  if public.get_dashboard() is null or public.get_dashboard() is distinct from
      (select payload from public.dashboard_cache where id=1)
  then raise exception 'Anonymous dashboard read parity failed'; end if;
end $$;
reset role;
set local role authenticated;
do $$
begin
  if public.get_dashboard() is null or public.get_dashboard() is distinct from
      (select payload from public.dashboard_cache where id=1)
  then raise exception 'Authenticated dashboard read parity failed'; end if;
end $$;
reset role;
