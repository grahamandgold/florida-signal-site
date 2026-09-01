-- Florida Signal SFWMD Pending ERP local authority, version 1.
--
-- CODE ONLY. `install-schema` applies these statements under the shared writer
-- lock in one BEGIN IMMEDIATE transaction, records the reviewed migration file
-- SHA-256 plus an exact sqlite_master object-manifest SHA-256, validates every
-- object, and only then commits. Direct sqlite3 shell application is unsupported.

create table sfwmd_pending_erp_schema (
  singleton integer primary key check (singleton = 1),
  schema_version text not null check (schema_version = 'FloridaSignalSfwmdSqliteV1'),
  migration_sha256 text not null check (length(migration_sha256) = 64),
  object_manifest_sha256 text not null check (length(object_manifest_sha256) = 64),
  installed_at text not null
);

create table sfwmd_pending_erp_runs (
  run_id text primary key,
  status text not null check (status in ('ok', 'empty', 'partial', 'failed')),
  progress_status text not null
    check (progress_status in ('changed', 'unchanged', 'empty', 'uncommitted', 'canary', 'superseded')),
  natural_run integer not null check (natural_run in (0, 1)),
  started_at text not null,
  observed_at text not null,
  completed_at text not null,
  event_through text,
  rows_observed integer not null check (rows_observed >= 0),
  rows_accepted integer not null check (rows_accepted >= 0),
  rows_inserted integer not null check (rows_inserted >= 0),
  rows_updated integer not null check (rows_updated >= 0),
  rows_unchanged integer not null check (rows_unchanged >= 0),
  rows_retired integer not null check (rows_retired >= 0),
  rows_rejected integer not null check (rows_rejected >= 0),
  source_content_index_sha256 text,
  evidence_bundle_path text not null,
  evidence_manifest_sha256 text not null,
  collection_receipt_sha256 text not null,
  provenance_sha256 text not null,
  observation_order_key text not null,
  receipt_sha256 text not null unique,
  receipt_json text not null,
  created_at text not null,
  check (started_at <= observed_at and observed_at <= completed_at),
  check (rows_accepted = rows_inserted + rows_updated + rows_unchanged),
  check (status not in ('partial', 'failed') or (rows_inserted = 0 and rows_updated = 0 and rows_retired = 0)),
  check (progress_status not in ('canary', 'superseded') or (rows_accepted = 0 and rows_retired = 0)),
  check (length(evidence_manifest_sha256) = 64),
  check (length(collection_receipt_sha256) = 64),
  check (length(provenance_sha256) = 64),
  check (length(receipt_sha256) = 64),
  check (json_valid(receipt_json))
);

create index sfwmd_pending_erp_runs_completed_idx
  on sfwmd_pending_erp_runs (completed_at desc);

create table sfwmd_pending_erp_records (
  identity_key text primary key check (length(trim(identity_key)) > 0),
  global_id text not null,
  app_no text not null,
  source_object_id integer not null,
  source_content_sha256 text not null check (length(source_content_sha256) = 64),
  record_json text not null check (json_valid(record_json)),
  event_received_at text,
  first_seen_at text not null,
  last_seen_at text not null,
  last_changed_at text not null,
  is_current integer not null default 1 check (is_current in (0, 1)),
  retired_at text,
  last_run_id text not null references sfwmd_pending_erp_runs(run_id),
  check (first_seen_at <= last_seen_at),
  check ((is_current = 1 and retired_at is null) or is_current = 0),
  unique (global_id, app_no)
);

create index sfwmd_pending_erp_records_current_idx
  on sfwmd_pending_erp_records (is_current, event_received_at desc, app_no);

create table sfwmd_pending_erp_versions (
  identity_key text not null,
  source_content_sha256 text not null check (length(source_content_sha256) = 64),
  record_json text not null check (json_valid(record_json)),
  first_observed_at text not null,
  first_run_id text not null references sfwmd_pending_erp_runs(run_id),
  primary key (identity_key, source_content_sha256)
);

create table sfwmd_pending_erp_mirror_outbox (
  run_id text primary key references sfwmd_pending_erp_runs(run_id),
  payload_sha256 text not null check (length(payload_sha256) = 64),
  payload_json text not null check (json_valid(payload_json)),
  state text not null default 'pending' check (state in ('pending', 'sent')),
  attempts integer not null default 0 check (attempts >= 0),
  last_attempt_at text,
  sent_at text,
  remote_receipt_json text check (remote_receipt_json is null or json_valid(remote_receipt_json))
);

create index sfwmd_pending_erp_outbox_pending_idx
  on sfwmd_pending_erp_mirror_outbox (state, run_id);

create table sfwmd_pending_erp_state (
  singleton integer primary key check (singleton = 1),
  latest_snapshot_order_key text,
  latest_snapshot_run_id text references sfwmd_pending_erp_runs(run_id),
  latest_natural_order_key text,
  latest_natural_run_id text references sfwmd_pending_erp_runs(run_id),
  updated_at text,
  check ((latest_snapshot_order_key is null) = (latest_snapshot_run_id is null)),
  check ((latest_natural_order_key is null) = (latest_natural_run_id is null))
);

insert into sfwmd_pending_erp_state (singleton) values (1);

create trigger sfwmd_pending_erp_runs_no_update
before update on sfwmd_pending_erp_runs
begin
  select raise(abort, 'SFWMD run receipts are append-only');
end;

create trigger sfwmd_pending_erp_runs_no_delete
before delete on sfwmd_pending_erp_runs
begin
  select raise(abort, 'SFWMD run receipts are append-only');
end;

create trigger sfwmd_pending_erp_versions_no_update
before update on sfwmd_pending_erp_versions
begin
  select raise(abort, 'SFWMD source versions are append-only');
end;

create trigger sfwmd_pending_erp_versions_no_delete
before delete on sfwmd_pending_erp_versions
begin
  select raise(abort, 'SFWMD source versions are append-only');
end;

create trigger sfwmd_pending_erp_outbox_payload_no_update
before update of run_id,payload_sha256,payload_json on sfwmd_pending_erp_mirror_outbox
begin
  select raise(abort, 'SFWMD mirror payloads are immutable');
end;

create trigger sfwmd_pending_erp_outbox_no_delete
before delete on sfwmd_pending_erp_mirror_outbox
begin
  select raise(abort, 'SFWMD mirror receipts are durable');
end;
