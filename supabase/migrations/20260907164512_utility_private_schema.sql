-- The approved utility owner gate requires this previously absent namespace.
-- It holds internal functions only and grants no API role access.
create schema private authorization postgres;
revoke all on schema private from public, anon, authenticated, service_role;
do $$
begin
  if has_schema_privilege('anon','private','USAGE')
     or has_schema_privilege('authenticated','private','USAGE')
     or has_schema_privilege('service_role','private','USAGE')
  then raise exception 'Utility private schema must remain owner-only'; end if;
end $$;
