-- Default-off least-privilege gate for the utility-intake Desk mirror.
-- Applying this migration creates or replaces only this private, owner-invoked
-- function and its function-specific EXECUTE/comment metadata. The canonical
-- private schema is a prerequisite: application makes no schema-wide grant,
-- revoke, ownership, or creation change. public.permits grants, policies, RLS,
-- and rows remain untouched until a database owner supplies the exact approval
-- phrase in a separate transaction.

create or replace function private.fs_apply_utility_intake_anon_read_hardening(
  p_approval text
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $function$
declare
  v_select_policy_count integer;
  v_write_policy_count integer;
  v_column text;
  v_rls_enabled boolean;
  v_rls_forced boolean;
begin
  if p_approval is distinct from 'I_APPROVE_EXACT_UTILITY_INTAKE_ANON_READ_HARDENING' then
    raise exception 'exact utility-intake anon-read approval is required';
  end if;

  if pg_catalog.to_regclass('public.permits') is null then
    raise exception 'public.permits is absent';
  end if;

  select count(*)
    into v_select_policy_count
    from pg_catalog.pg_policies
   where schemaname = 'public'
     and tablename = 'permits'
     and policyname = 'anon_read_permits'
     and permissive = 'PERMISSIVE'
     and cmd = 'SELECT'
     and 'anon' = any (roles)
     and pg_catalog.regexp_replace(coalesce(qual, ''), '[[:space:]()]', '', 'g') = 'true'
     and with_check is null;

  select count(*)
    into v_write_policy_count
    from pg_catalog.pg_policies
   where schemaname = 'public'
     and tablename = 'permits'
     and 'anon' = any (roles)
     and cmd in ('ALL', 'INSERT', 'UPDATE', 'DELETE');

  if v_select_policy_count <> 1 or v_write_policy_count <> 0 then
    raise exception 'public.permits anon RLS policy contract is not exact';
  end if;

  -- The exact approved mutation: RLS remains forced and anon retains only
  -- SELECT. Revoke column-level write grants as well as table-level grants.
  execute 'alter table public.permits enable row level security';
  execute 'alter table public.permits force row level security';
  execute 'revoke all privileges on table public.permits from anon';
  for v_column in
    select a.attname
      from pg_catalog.pg_attribute a
     where a.attrelid = 'public.permits'::pg_catalog.regclass
       and a.attnum > 0
       and not a.attisdropped
  loop
    execute pg_catalog.format(
      'revoke insert (%1$I), update (%1$I), references (%1$I) on table public.permits from anon',
      v_column
    );
  end loop;
  execute 'grant select on table public.permits to anon';

  select c.relrowsecurity, c.relforcerowsecurity
    into v_rls_enabled, v_rls_forced
    from pg_catalog.pg_class c
    join pg_catalog.pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'public' and c.relname = 'permits';

  if not v_rls_enabled
     or not v_rls_forced
     or not pg_catalog.has_table_privilege('anon', 'public.permits', 'SELECT')
     or pg_catalog.has_table_privilege('anon', 'public.permits', 'INSERT')
     or pg_catalog.has_table_privilege('anon', 'public.permits', 'UPDATE')
     or pg_catalog.has_table_privilege('anon', 'public.permits', 'DELETE')
     or pg_catalog.has_table_privilege('anon', 'public.permits', 'TRUNCATE')
     or pg_catalog.has_table_privilege('anon', 'public.permits', 'REFERENCES')
     or pg_catalog.has_table_privilege('anon', 'public.permits', 'TRIGGER')
     or exists (
       select 1
         from information_schema.column_privileges
        where table_schema = 'public'
          and table_name = 'permits'
          and grantee = 'anon'
          and privilege_type <> 'SELECT'
     ) then
    raise exception 'public.permits anon grants did not converge to SELECT-only';
  end if;

  return pg_catalog.jsonb_build_object(
    'schema_version', 'FloridaSignalUtilityIntakeAnonGrantAttestationV1',
    'table', 'public.permits',
    'anon_select', true,
    'anon_write', false,
    'rls_enabled', v_rls_enabled,
    'rls_forced', v_rls_forced,
    'select_policy', 'anon_read_permits'
  );
end;
$function$;

revoke execute on function private.fs_apply_utility_intake_anon_read_hardening(text)
  from public, anon, authenticated, service_role;

comment on function private.fs_apply_utility_intake_anon_read_hardening(text) is
  'Default-off owner gate: exact approval hardens public.permits anon access to RLS-forced SELECT-only and returns an attestation.';
