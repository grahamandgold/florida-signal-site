-- These builders are called by backend jobs. Public clients use get_dashboard().
-- Preserve owner-operated cache refresh and the service-role draft builder.
do $$
begin
  if (select md5(prosrc) from pg_proc where oid='public.brief_signals()'::regprocedure)
       is distinct from 'b3d46f42c797cfa46ba868b8dd11b3c2'
     or (select md5(prosrc) from pg_proc where oid='public.dashboard_payload()'::regprocedure)
       is distinct from 'ab2eb74c676cfcbfde0407674eb72cc4'
  then raise exception 'Internal summary definitions changed since caller review'; end if;
end $$;
revoke execute on function public.brief_signals() from public, anon, authenticated;
revoke execute on function public.dashboard_payload() from public, anon, authenticated;
grant execute on function public.brief_signals() to service_role;
grant execute on function public.dashboard_payload() to service_role;
do $$
declare routine regprocedure;
begin
  foreach routine in array array['public.brief_signals()'::regprocedure,'public.dashboard_payload()'::regprocedure] loop
    if has_function_privilege('anon',routine,'EXECUTE')
       or has_function_privilege('authenticated',routine,'EXECUTE')
       or not has_function_privilege('service_role',routine,'EXECUTE')
    then raise exception 'Internal summary privilege check failed'; end if;
  end loop;
  if not has_function_privilege('anon','public.get_dashboard()','EXECUTE')
     or not has_function_privilege('authenticated','public.get_dashboard()','EXECUTE')
     or public.get_dashboard() is null
  then raise exception 'Public cached dashboard must remain available'; end if;
end $$;
