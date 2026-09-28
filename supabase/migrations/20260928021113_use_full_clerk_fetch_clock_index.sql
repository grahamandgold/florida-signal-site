-- fetched_at is NOT NULL in production. PostgreSQL can remove the redundant
-- query predicate, making the earlier IS NOT NULL partial index unusable.
-- A full index covers the same existing rows and supports the exact API sort.
set local lock_timeout = '500ms';
set local statement_timeout = '15s';
do $$
begin
  if pg_get_indexdef(to_regclass('public.idx_clerk_prelim_fetched_at')) is distinct from
     'CREATE INDEX idx_clerk_prelim_fetched_at ON public.broward_clerk_preliminary USING btree (fetched_at DESC) WHERE (fetched_at IS NOT NULL)' then
    raise exception 'Clerk fetch index changed; re-review before replacing';
  end if;
end
$$;
drop index public.idx_clerk_prelim_fetched_at;
create index idx_clerk_prelim_fetched_at
  on public.broward_clerk_preliminary (fetched_at desc);

-- The prior guarded optimize_health_clock_reads rollback also removes this
-- replacement index and restores the original view without changing any rows.
