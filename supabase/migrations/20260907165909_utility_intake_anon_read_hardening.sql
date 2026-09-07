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
  v_anon_oid oid;
  v_permits_oid oid;
  v_select_policy_count integer;
  v_applicable_restrictive_select_policy_count integer;
  v_applicable_write_policy_count integer;
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

  select r.oid
    into v_anon_oid
    from pg_catalog.pg_roles r
   where r.rolname = 'anon'
     and not r.rolsuper
     and not r.rolbypassrls;
  if v_anon_oid is null then
    raise exception 'anon role is absent, superuser, or bypasses RLS';
  end if;
  v_permits_oid := 'public.permits'::pg_catalog.regclass;

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
    into v_applicable_write_policy_count
    from pg_catalog.pg_policies p
   where p.schemaname = 'public'
     and p.tablename = 'permits'
     and p.cmd in ('ALL', 'INSERT', 'UPDATE', 'DELETE')
     and exists (
       select 1
         from pg_catalog.unnest(p.roles) as policy_role(role_name)
        where policy_role.role_name = 'public'::pg_catalog.name
           or policy_role.role_name = 'anon'::pg_catalog.name
           or exists (
             select 1
               from pg_catalog.pg_roles inherited_role
              where inherited_role.rolname = policy_role.role_name
                and pg_catalog.pg_has_role(
                  v_anon_oid,
                  inherited_role.oid,
                  'MEMBER'
                )
           )
     );

  -- A permissive USING (true) policy is not sufficient by itself: every
  -- applicable restrictive SELECT policy is ANDed with the permissive result.
  -- Reject all such policies instead of returning an anon_select=true
  -- attestation for a role that can in fact see zero rows.
  select count(*)
    into v_applicable_restrictive_select_policy_count
    from pg_catalog.pg_policies p
   where p.schemaname = 'public'
     and p.tablename = 'permits'
     and p.cmd in ('ALL', 'SELECT')
     and p.permissive = 'RESTRICTIVE'
     and exists (
       select 1
         from pg_catalog.unnest(p.roles) as policy_role(role_name)
        where policy_role.role_name = 'public'::pg_catalog.name
           or policy_role.role_name = 'anon'::pg_catalog.name
           or exists (
             select 1
               from pg_catalog.pg_roles inherited_role
              where inherited_role.rolname = policy_role.role_name
                and pg_catalog.pg_has_role(
                  v_anon_oid,
                  inherited_role.oid,
                  'MEMBER'
                )
           )
     );

  if v_select_policy_count <> 1
     or v_applicable_restrictive_select_policy_count <> 0
     or v_applicable_write_policy_count <> 0 then
    raise exception 'public.permits effective anon RLS policy contract is not exact';
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
     or not pg_catalog.has_schema_privilege('anon', 'public', 'USAGE')
     or not pg_catalog.has_table_privilege('anon', 'public.permits', 'SELECT')
     or pg_catalog.has_table_privilege('anon', 'public.permits', 'INSERT')
     or pg_catalog.has_table_privilege('anon', 'public.permits', 'UPDATE')
     or pg_catalog.has_table_privilege('anon', 'public.permits', 'DELETE')
     or pg_catalog.has_table_privilege('anon', 'public.permits', 'TRUNCATE')
     or pg_catalog.has_table_privilege('anon', 'public.permits', 'REFERENCES')
     or pg_catalog.has_table_privilege('anon', 'public.permits', 'TRIGGER')
     or exists (
       select 1
         from pg_catalog.pg_roles reachable_role
        where (
          reachable_role.oid = v_anon_oid
          or pg_catalog.pg_has_role(v_anon_oid, reachable_role.oid, 'MEMBER')
        )
          and (
            pg_catalog.has_table_privilege(reachable_role.oid, v_permits_oid, 'INSERT')
            or pg_catalog.has_table_privilege(reachable_role.oid, v_permits_oid, 'UPDATE')
            or pg_catalog.has_table_privilege(reachable_role.oid, v_permits_oid, 'DELETE')
            or pg_catalog.has_table_privilege(reachable_role.oid, v_permits_oid, 'TRUNCATE')
            or pg_catalog.has_table_privilege(reachable_role.oid, v_permits_oid, 'REFERENCES')
            or pg_catalog.has_table_privilege(reachable_role.oid, v_permits_oid, 'TRIGGER')
          )
     )
     or exists (
       select 1
         from pg_catalog.pg_roles reachable_role
         cross join pg_catalog.pg_attribute a
        where (
          reachable_role.oid = v_anon_oid
          or pg_catalog.pg_has_role(v_anon_oid, reachable_role.oid, 'MEMBER')
        )
          and a.attrelid = v_permits_oid
          and a.attnum > 0
          and not a.attisdropped
          and (
            pg_catalog.has_column_privilege(
              reachable_role.oid, v_permits_oid, a.attnum, 'INSERT'
            )
            or pg_catalog.has_column_privilege(
              reachable_role.oid, v_permits_oid, a.attnum, 'UPDATE'
            )
            or pg_catalog.has_column_privilege(
              reachable_role.oid, v_permits_oid, a.attnum, 'REFERENCES'
            )
          )
     ) then
    raise exception 'public.permits effective anon grants did not converge to SELECT-only';
  end if;

  return pg_catalog.jsonb_build_object(
    'schema_version', 'FloridaSignalUtilityIntakeAnonGrantAttestationV2',
    'table', 'public.permits',
    'anon_select', true,
    'anon_write', false,
    'rls_enabled', v_rls_enabled,
    'rls_forced', v_rls_forced,
    'select_policy', 'anon_read_permits'
  );
end;
$function$;

-- CREATE OR REPLACE preserves an existing function ACL. Remove PUBLIC and
-- every arbitrary explicit grantee so migration application ends owner-only,
-- even if an earlier object was granted to a custom role.
do $function_acl$
declare
  v_function_oid oid := pg_catalog.to_regprocedure(
    'private.fs_apply_utility_intake_anon_read_hardening(text)'
  );
  v_owner_oid oid;
  v_grantee_name pg_catalog.name;
begin
  if v_function_oid is null then
    raise exception 'utility-intake hardening function is absent';
  end if;
  select p.proowner
    into v_owner_oid
    from pg_catalog.pg_proc p
   where p.oid = v_function_oid;

  execute 'revoke all privileges on function '
    || 'private.fs_apply_utility_intake_anon_read_hardening(text) from public';
  for v_grantee_name in
    select distinct r.rolname
      from pg_catalog.pg_proc p
      cross join lateral pg_catalog.aclexplode(
        coalesce(p.proacl, pg_catalog.acldefault('f', p.proowner))
      ) acl
      join pg_catalog.pg_roles r on r.oid = acl.grantee
     where p.oid = v_function_oid
       and acl.grantee <> p.proowner
  loop
    execute pg_catalog.format(
      'revoke all privileges on function private.fs_apply_utility_intake_anon_read_hardening(text) from %I',
      v_grantee_name
    );
  end loop;

  if exists (
    select 1
      from pg_catalog.pg_proc p
      cross join lateral pg_catalog.aclexplode(
        coalesce(p.proacl, pg_catalog.acldefault('f', p.proowner))
      ) acl
     where p.oid = v_function_oid
       and acl.grantee <> v_owner_oid
  ) then
    raise exception 'utility-intake hardening function ACL is not owner-only';
  end if;
end;
$function_acl$;

comment on function private.fs_apply_utility_intake_anon_read_hardening(text) is
  'Default-off owner gate: exact approval hardens public.permits anon access to RLS-forced SELECT-only and returns an attestation.';
