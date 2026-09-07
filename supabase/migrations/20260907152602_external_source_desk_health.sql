-- Deliberately public operational metadata only. Raw receipts, object keys,
-- errors, source metadata, stage rows and dispatch credentials remain private.
create table public.external_source_desk_health (
 source_id text primary key check (source_id in ('fdep_erp','faa_oeaaa')),
 receipt_id bigint not null,
 run_id uuid not null,
 status text not null check (status in ('ok','empty','source_wait','partial','failed')),
 completed_at timestamptz not null,
 event_through timestamptz,
 rows_observed integer not null check (rows_observed >= 0),
 rows_accepted integer not null check (rows_accepted >= 0),
 rows_rejected integer not null check (rows_rejected >= 0)
);
alter table public.external_source_desk_health enable row level security;
revoke all on public.external_source_desk_health from public, anon, authenticated;
grant select on public.external_source_desk_health to anon, authenticated;
grant all on public.external_source_desk_health to service_role;
create policy desk_health_read on public.external_source_desk_health
 for select to anon, authenticated using (true);

create function public.refresh_external_source_desk_health()
returns trigger language plpgsql security invoker set search_path = '' as $$
begin
 insert into public.external_source_desk_health
  (source_id,receipt_id,run_id,status,completed_at,event_through,rows_observed,rows_accepted,rows_rejected)
 values
  (new.source_id,new.id,new.run_id,new.status,new.completed_at,new.event_through,new.rows_observed,new.rows_accepted,new.rows_rejected)
 on conflict (source_id) do update set
  receipt_id=excluded.receipt_id,run_id=excluded.run_id,status=excluded.status,
  completed_at=excluded.completed_at,event_through=excluded.event_through,
  rows_observed=excluded.rows_observed,rows_accepted=excluded.rows_accepted,rows_rejected=excluded.rows_rejected
 where (excluded.completed_at,excluded.receipt_id) >=
       (external_source_desk_health.completed_at,external_source_desk_health.receipt_id);
 return new;
end;
$$;
revoke all on function public.refresh_external_source_desk_health() from public, anon, authenticated;
grant execute on function public.refresh_external_source_desk_health() to service_role;
create trigger external_source_desk_health_refresh
 after insert on public.external_source_run_receipts
 for each row execute function public.refresh_external_source_desk_health();

insert into public.external_source_desk_health
 (source_id,receipt_id,run_id,status,completed_at,event_through,rows_observed,rows_accepted,rows_rejected)
select distinct on (source_id)
 source_id,id,run_id,status,completed_at,event_through,rows_observed,rows_accepted,rows_rejected
from public.external_source_run_receipts
order by source_id,completed_at desc,id desc;
