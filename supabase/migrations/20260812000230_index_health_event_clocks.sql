-- Health checks read event and system clocks independently. These partial indexes keep the
-- single-row clock probes inside PostgREST's short statement timeout without indexing nulls.
create index if not exists fdep_erp_received_date_health_idx
  on public.fdep_erp (received_date desc)
  where received_date is not null;

create index if not exists fdep_erp_last_fetched_health_idx
  on public.fdep_erp (last_fetched_at desc)
  where last_fetched_at is not null;
