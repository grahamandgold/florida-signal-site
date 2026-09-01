import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "20260831235900_sfwmd_pending_erp_private_mirror.sql"
SERVICE = ROOT / "ops" / "droplet" / "florida-sfwmd-pending-erp.service"
TIMER = ROOT / "ops" / "droplet" / "florida-sfwmd-pending-erp.timer"
ENVIRONMENT = ROOT / "ops" / "droplet" / "florida-sfwmd-pending-erp.env.example"
ALERT_ENVIRONMENT = (
    ROOT / "ops" / "droplet" / "florida-sfwmd-pending-erp-alert.env.example"
)
BACKUP_ENVIRONMENT = (
    ROOT / "ops" / "droplet" / "florida-sfwmd-pending-erp-backup.env.example"
)
TIMER_SERVICE = ROOT / "ops" / "droplet" / "florida-sfwmd-pending-erp-timer.service"
PRODUCTION = ROOT / "ops" / "droplet" / "sfwmd_pending_erp_production.py"
ALERT_SERVICE = ROOT / "ops" / "droplet" / "florida-sfwmd-pending-erp-alert@.service"
BACKUP_SERVICE = ROOT / "ops" / "droplet" / "florida-sfwmd-pending-erp-backup.service"
SERVER_SPEC = importlib.util.spec_from_file_location("sfwmd_desk_server", ROOT / "cms" / "server.py")
server = importlib.util.module_from_spec(SERVER_SPEC)
assert SERVER_SPEC.loader is not None
SERVER_SPEC.loader.exec_module(server)


class SfwmdDeploymentContractTests(unittest.TestCase):
    def test_private_mirror_is_rls_forced_invoker_only_and_bounded(self):
        sql = MIGRATION.read_text(encoding="utf-8").lower()
        for table in (
            "sfwmd_pending_erp_runs",
            "sfwmd_pending_erp_records",
            "sfwmd_pending_erp_versions",
            "sfwmd_pending_erp_state",
        ):
            self.assertIn(f"alter table public.{table} enable row level security", sql)
            self.assertIn(f"alter table public.{table} force row level security", sql)
        self.assertIn("security invoker", sql)
        self.assertIn("to service_role", sql)
        self.assertIn("from public, anon, authenticated", sql)
        self.assertIn("pg_catalog.jsonb_array_length(p_rows)", sql)
        self.assertIn("v_row_count > 500", sql)
        self.assertIn("rows_observed between 0 and 2000", sql)
        self.assertIn("idempotent_replay", sql)
        self.assertIn("immutable", sql)
        self.assertNotIn("grant select on table public.sfwmd_pending_erp_records to anon", sql)
        self.assertNotIn("signal_review_queue", sql)

    def test_private_mirror_migration_refuses_poison_and_postflights_exact_acls(self):
        sql = MIGRATION.read_text(encoding="utf-8").lower()
        first_create = sql.index("create table public.sfwmd_pending_erp_runs")
        preflight = sql.index("refusing preexisting or partial sfwmd mirror namespace")
        table_acl_scrub = sql.index("default privileges can grant a custom role")
        first_table_grant = sql.index(
            "grant select, insert on table public.sfwmd_pending_erp_runs to service_role"
        )
        function_acl_scrub = sql.index("create function grants execute to public")
        function_grant = sql.index(
            "grant execute on function public.fs_commit_sfwmd_pending_erp_run"
        )
        postflight = sql.index("sfwmd table/rls postflight failed")

        self.assertLess(preflight, first_create)
        self.assertLess(table_acl_scrub, first_table_grant)
        self.assertLess(function_acl_scrub, function_grant)
        self.assertGreater(postflight, function_grant)
        self.assertNotIn("create table if not exists public.sfwmd_pending_erp_", sql)
        self.assertNotIn("create or replace function public.fs_sfwmd_", sql)
        self.assertNotIn(
            "create or replace function public.fs_commit_sfwmd_pending_erp_run", sql
        )
        self.assertNotIn("drop trigger if exists sfwmd_pending_erp_", sql)
        for catalog_contract in (
            "pg_catalog.pg_class",
            "pg_catalog.pg_proc",
            "pg_catalog.pg_type",
            "pg_catalog.pg_policy",
            "pg_catalog.left(pg_catalog.lower(routine.proname), 9) = 'fs_sfwmd_'",
            "pg_catalog.aclexplode",
            "pg_catalog.acldefault('r'",
            "pg_catalog.acldefault('f'",
            "pg_catalog.pg_get_userbyid",
            "pg_catalog.oidvectortypes",
            "privilege.grantee <> object.relowner",
            "privilege.grantee <> routine.proowner",
            "privilege.grantee not in (object.relowner, service_oid)",
            "privilege.grantee not in (routine.proowner, service_oid)",
            "role.rolbypassrls",
            "pg_catalog.has_schema_privilege",
            "pg_catalog.has_table_privilege",
            "pg_catalog.has_function_privilege",
            "extensions.digest(bytea,text)",
            "sfwmd table acl postflight found an arbitrary grantee",
            "sfwmd function acl postflight found an arbitrary grantee",
            "sfwmd service_role table privilege matrix is not exact",
            "sfwmd service_role function privilege matrix is not exact",
            "sfwmd security invoker routine definition postflight failed",
            "anonymous role has effective sfwmd table access",
            "anonymous role has effective sfwmd function access",
            "anonymous role can create objects in the sfwmd rpc schema",
            "routine.proconfig is distinct from array['search_path=\"\"']::text[]",
        ):
            self.assertIn(catalog_contract, sql)
        self.assertIn(
            "revoke all privileges on function %s from %i", sql
        )
        self.assertIn(
            "revoke all privileges on table public.%i from %i", sql
        )
        self.assertIn(
            "from public, anon, authenticated, service_role", sql
        )

    def test_schedule_is_daily_nonpersistent_and_both_gates_default_off(self):
        service = SERVICE.read_text(encoding="utf-8")
        timer = TIMER.read_text(encoding="utf-8")
        environment = ENVIRONMENT.read_text(encoding="utf-8")
        self.assertIn("FLORIDA_SIGNAL_SFWMD_ENABLED=0", service)
        self.assertIn("FLORIDA_SIGNAL_SFWMD_MIRROR_ENABLED=0", service)
        self.assertIn("FLORIDA_SIGNAL_SFWMD_ENABLED=0", environment)
        self.assertIn("FLORIDA_SIGNAL_SFWMD_MIRROR_ENABLED=0", environment)
        self.assertEqual(timer.count("OnCalendar="), 1)
        self.assertIn("Persistent=false", timer)
        self.assertIn("--page-size 2000", service)
        self.assertNotIn("backfill", service.lower())

    def test_timer_provenance_alert_and_backup_units_are_independently_gated(self):
        service = SERVICE.read_text(encoding="utf-8")
        timer = TIMER.read_text(encoding="utf-8")
        timer_service = TIMER_SERVICE.read_text(encoding="utf-8")
        alert_service = ALERT_SERVICE.read_text(encoding="utf-8")
        backup_service = BACKUP_SERVICE.read_text(encoding="utf-8")
        environment = ENVIRONMENT.read_text(encoding="utf-8")
        alert_environment = ALERT_ENVIRONMENT.read_text(encoding="utf-8")
        backup_environment = BACKUP_ENVIRONMENT.read_text(encoding="utf-8")
        production = PRODUCTION.read_text(encoding="utf-8")
        self.assertIn("Unit=florida-sfwmd-pending-erp-timer.service", timer)
        self.assertIn("RefuseManualStart=yes", timer_service)
        self.assertIn(" timer-run ", timer_service)
        self.assertIn(" scheduled-run --invocation-kind manual_service ", service)
        self.assertIn("OnFailure=florida-sfwmd-pending-erp-alert@%n.service", service)
        self.assertIn("OnFailure=florida-sfwmd-pending-erp-alert@%n.service", timer_service)
        self.assertIn("sfwmd_pending_erp_alert.py", alert_service)
        self.assertIn("FLORIDA_SIGNAL_SFWMD_ALERT_ENABLED=0", alert_service)
        self.assertIn("sfwmd_pending_erp_backup.py", backup_service)
        self.assertIn("FLORIDA_SIGNAL_SFWMD_BACKUP_ENABLED=0", backup_service)
        self.assertIn("florida-sfwmd-pending-erp-alert.env", alert_service)
        self.assertIn("florida-sfwmd-pending-erp-backup.env", backup_service)
        self.assertNotIn("ALERT_WEBHOOK", environment)
        self.assertNotIn("RESTIC_", environment)
        self.assertIn("FLORIDA_SIGNAL_SFWMD_ALERT_ENABLED=0", alert_environment)
        self.assertIn("FLORIDA_SIGNAL_SFWMD_BACKUP_ENABLED=0", backup_environment)
        self.assertIn('os.environ.get("TRIGGER_UNIT"', production)
        self.assertIn('os.environ.get("TRIGGER_TIMER_REALTIME_USEC"', production)
        self.assertIn('Path("/proc/self/cgroup")', production)
        self.assertIn('"runtime_cgroup_sha256"', production)

    def test_postgres_recomputes_every_digest_before_exact_replay(self):
        sql = MIGRATION.read_text(encoding="utf-8").lower()
        for contract in (
            "record_canonical", "record_sha256", "v_content_index_sha256",
            "v_ordered_rows_sha256", "v_computed_payload_sha256",
            "database-computed payload or index digest differs",
            "run id replay conflicts with immutable payload",
            "client monotonic classification differs",
            "database-computed progress classification differs",
        ):
            self.assertIn(contract, sql)
        self.assertIn("string_agg(", sql)
        self.assertIn("order by (item.value ->> 'identity_key') collate \"c\"", sql)
        self.assertIn("v_computed_payload_sha256 <> p_payload_sha256", sql)
        self.assertIn("v_content_index_sha256 <> p_receipt ->> 'source_content_index_sha256'", sql)
        self.assertIn('collate "c"', sql)
        self.assertLess(
            sql.index("database-computed payload or index digest differs"),
            sql.index("select * into v_existing"),
        )

    def test_reviewed_shadow_content_hash_is_exact_in_both_runbooks(self):
        expected = "84b79506efa274e50b342158992dcc33983212c403d44d38f1c7ca7443514459"
        wrong = "84b795b9"
        for path in (
            ROOT / "SFWMD_PENDING_ERP_SHADOW_RUNBOOK.md",
            ROOT / "SFWMD_PENDING_ERP_PRODUCTION_RUNBOOK.md",
        ):
            body = path.read_text(encoding="utf-8")
            self.assertIn(expected, body)
            self.assertNotIn(wrong, body)

    def test_desk_missing_receipt_is_unknown_and_not_connected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "receipts"
            with mock.patch.object(server, "SFWMD_RECEIPT_DIR", root), \
                    mock.patch.object(server, "SFWMD_LATEST_PATH", root / "latest.json"):
                receipt = server.sfwmd_source_receipt()
        self.assertEqual(receipt["status"], "UNKNOWN")
        self.assertEqual(receipt["connection_state"], "not_connected")
        self.assertFalse(receipt["natural_run"])

    def test_desk_accepts_only_hash_bound_natural_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "receipts"
            root.mkdir()
            run_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
            now = server.datetime.now(server.timezone.utc)
            local_now = now.astimezone(server.ZoneInfo("America/New_York"))
            slot = local_now.replace(hour=6, minute=17, second=0, microsecond=0)
            if local_now < slot:
                slot -= server.timedelta(days=1)
            scheduled = slot.astimezone(server.timezone.utc)
            created = scheduled + server.timedelta(seconds=30)
            started = scheduled + server.timedelta(minutes=1)
            completed_clock = scheduled + server.timedelta(minutes=5)
            iso = lambda value: value.isoformat(timespec="microseconds").replace("+00:00", "Z")
            completed = iso(completed_clock)
            trigger_usec = str(int(created.timestamp() * 1_000_000))
            cgroup_evidence = (
                "0::/system.slice/florida-sfwmd-pending-erp-timer.service\n"
            )
            import hashlib
            cgroup_sha = hashlib.sha256(cgroup_evidence.encode("utf-8")).hexdigest()
            canary_path = Path(directory) / f"{run_id}.json"
            canary = {
                "schema_version": "FloridaSignalSfwmdTimerCanaryV1",
                "run_id": run_id,
                "timer_unit": "florida-sfwmd-pending-erp.timer",
                "service_unit": "florida-sfwmd-pending-erp-timer.service",
                "systemd_invocation_id": "b" * 32,
                "trigger_timer_realtime_usec": trigger_usec,
                "runtime_cgroup_sha256": cgroup_sha,
                "runtime_cgroup_evidence": cgroup_evidence,
                "scheduled_for": iso(scheduled),
                "created_at": iso(created),
            }
            canary_body = (json.dumps(canary, sort_keys=True, separators=(",", ":")) + "\n").encode()
            canary_path.write_bytes(canary_body)
            canary_path.chmod(0o400)
            provenance = {
                "schema_version": "FloridaSignalSfwmdRunProvenanceV1",
                "natural_run": True,
                "invocation_kind": "systemd_timer",
                "verified": True,
                "timer_unit": "florida-sfwmd-pending-erp.timer",
                "service_unit": "florida-sfwmd-pending-erp-timer.service",
                "systemd_invocation_id": "b" * 32,
                "trigger_timer_realtime_usec": trigger_usec,
                "runtime_cgroup_sha256": cgroup_sha,
                "scheduled_for": iso(scheduled),
                "canary_path": str(canary_path),
                "canary_sha256": hashlib.sha256(canary_body).hexdigest(),
            }
            observation_order_key = f"{completed}|{completed}|{run_id}"
            counts = {
                "rows_observed": 0,
                "rows_accepted": 0,
                "rows_inserted": 0,
                "rows_updated": 0,
                "rows_unchanged": 0,
                "rows_retired": 0,
                "rows_rejected": 0,
            }
            empty_sha = hashlib.sha256(b"").hexdigest()
            database_payload_sha = hashlib.sha256((
                "FloridaSignalSfwmdPostgresPayloadV1\n"
                f"{run_id}\nempty\nempty\n{completed}\n{empty_sha}\n0\n{empty_sha}\n"
            ).encode("utf-8")).hexdigest()
            receipt = {
                "schema_version": "FloridaSignalSfwmdPendingErpProductionReceiptV1",
                "run_id": run_id,
                "natural_run": True,
                "provenance": provenance,
                "observation_order_key": observation_order_key,
                "status": "empty",
                "reason_code": None,
                "progress_status": "empty",
                "connection_state": "not_connected",
                "started_at": iso(started),
                "observed_at": completed,
                "completed_at": completed,
                "source_checked_at": completed,
                "source_modified_at": None,
                "source_modified_status": "UNKNOWN_NOT_EXPOSED",
                "event_through": None,
                "event_through_semantics": (
                    "maximum AppReceivedDate among included Fort Lauderdale shadow rows"
                ),
                "counts": counts,
                "source_content_index_sha256": empty_sha,
                "versions": {
                    "production_collector": "sfwmd-pending-erp-production/1.0.0",
                    "collector": "sfwmd-pending-erp-shadow/1.0.0",
                    "parser": "sfwmd-layer14-parser/1.0.0",
                    "normalizer": "sfwmd-layer14-normalizer/1.0.0",
                    "sqlite_schema": "FloridaSignalSfwmdSqliteV1",
                    "sqlite_migration_sha256": (
                        "a8f39dfe2d9dcff1ffe85cce16a5771a58138fa2cf6d1dcfc1e96c69a724d088"
                    ),
                },
                "evidence": {
                    "bundle_path": str(Path(directory) / "evidence"),
                    "bundle_manifest_sha256": "d" * 64,
                    "collection_receipt_sha256": "e" * 64,
                    "raw_manifest_sha256": "f" * 64,
                    "normalized_records_sha256": "1" * 64,
                },
                "mirror": {
                    "eligible": True,
                    "state": "pending",
                    "idempotency": "run_id_plus_database_computed_payload_sha256",
                    "digest_basis": "FloridaSignalSfwmdPostgresPayloadV1",
                    "row_count": 0,
                    "ordered_rows_sha256": empty_sha,
                    "database_payload_sha256": database_payload_sha,
                },
                "safety": {
                    "bounded_current_pending_snapshot_only": True,
                    "unrestricted_backfill": False,
                    "scoring": False,
                    "candidate_or_queue_write": False,
                    "publication": False,
                    "connected_label_allowed": False,
                },
            }
            receipt_path = root / f"{run_id}.json"
            body = (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode()
            receipt_path.write_bytes(body)
            pointer = {
                "schema_version": "FloridaSignalSfwmdPendingErpLatestV1",
                "run_id": run_id,
                "natural_run": True,
                "status": "empty",
                "progress_status": "empty",
                "connection_state": "not_connected",
                "observation_order_key": observation_order_key,
                "completed_at": completed,
                "event_through": None,
                "receipt_path": str(receipt_path),
                "receipt_sha256": hashlib.sha256(body).hexdigest(),
                "provenance_sha256": hashlib.sha256(
                    (json.dumps(provenance, sort_keys=True, separators=(",", ":")) + "\n").encode()
                ).hexdigest(),
                "counts": counts,
            }
            latest = root / "latest.json"
            latest.write_text(
                json.dumps(pointer, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            with mock.patch.object(server, "SFWMD_RECEIPT_DIR", root), \
                    mock.patch.object(server, "SFWMD_LATEST_PATH", latest):
                result = server.sfwmd_source_receipt()
                self.assertEqual(result["status"], "CURRENT")
                self.assertEqual(result["connection_state"], "not_connected")
                mutations = (
                    lambda value: value["safety"].__setitem__("scoring", True),
                    lambda value: value["counts"].__setitem__("rows_observed", 2001),
                    lambda value: value["mirror"].__setitem__("database_payload_sha256", "bad"),
                    lambda value: value["evidence"].__setitem__("unexpected", "field"),
                    lambda value: value["provenance"].__setitem__("invocation_kind", "direct"),
                    lambda value: value["provenance"].__setitem__(
                        "runtime_cgroup_sha256", "8" * 64
                    ),
                    lambda value: value["provenance"].__setitem__(
                        "trigger_timer_realtime_usec",
                        int(value["provenance"]["trigger_timer_realtime_usec"]),
                    ),
                    lambda value: value["versions"].__setitem__("collector", "unreviewed"),
                    lambda value: value.__setitem__("reason_code", "UNREVIEWED"),
                )
                for mutate in mutations:
                    candidate = json.loads(json.dumps(receipt))
                    candidate_pointer = json.loads(json.dumps(pointer))
                    mutate(candidate)
                    candidate_pointer["counts"] = candidate["counts"]
                    candidate_body = (
                        json.dumps(candidate, sort_keys=True, separators=(",", ":")) + "\n"
                    ).encode()
                    receipt_path.write_bytes(candidate_body)
                    candidate_pointer["receipt_sha256"] = hashlib.sha256(candidate_body).hexdigest()
                    candidate_pointer["provenance_sha256"] = hashlib.sha256(
                        (json.dumps(
                            candidate["provenance"], sort_keys=True, separators=(",", ":")
                        ) + "\n").encode()
                    ).hexdigest()
                    latest.write_text(
                        json.dumps(candidate_pointer, sort_keys=True, separators=(",", ":")) + "\n"
                    )
                    self.assertEqual(server.sfwmd_source_receipt()["status"], "UNKNOWN")
                for forged_progress in ("changed", "unchanged", "superseded"):
                    candidate = json.loads(json.dumps(receipt))
                    candidate_pointer = json.loads(json.dumps(pointer))
                    candidate["progress_status"] = forged_progress
                    candidate_pointer["progress_status"] = forged_progress
                    candidate["mirror"]["database_payload_sha256"] = hashlib.sha256((
                        "FloridaSignalSfwmdPostgresPayloadV1\n"
                        f"{run_id}\nempty\n{forged_progress}\n{completed}\n"
                        f"{empty_sha}\n0\n{empty_sha}\n"
                    ).encode("utf-8")).hexdigest()
                    candidate_body = (
                        json.dumps(candidate, sort_keys=True, separators=(",", ":")) + "\n"
                    ).encode()
                    receipt_path.write_bytes(candidate_body)
                    candidate_pointer["receipt_sha256"] = hashlib.sha256(
                        candidate_body
                    ).hexdigest()
                    latest.write_text(
                        json.dumps(
                            candidate_pointer, sort_keys=True, separators=(",", ":")
                        ) + "\n"
                    )
                    self.assertEqual(server.sfwmd_source_receipt()["status"], "UNKNOWN")
                overaccepted = json.loads(json.dumps(receipt))
                overaccepted_pointer = json.loads(json.dumps(pointer))
                overaccepted["status"] = "ok"
                overaccepted["progress_status"] = "unchanged"
                overaccepted["counts"].update({
                    "rows_observed": 1,
                    "rows_accepted": 2,
                    "rows_unchanged": 2,
                })
                overaccepted["source_content_index_sha256"] = "2" * 64
                overaccepted["mirror"]["row_count"] = 2
                overaccepted["mirror"]["ordered_rows_sha256"] = "3" * 64
                overaccepted["mirror"]["database_payload_sha256"] = hashlib.sha256((
                    "FloridaSignalSfwmdPostgresPayloadV1\n"
                    f"{run_id}\nok\nunchanged\n{completed}\n"
                    f"{'2' * 64}\n2\n{'3' * 64}\n"
                ).encode("utf-8")).hexdigest()
                for field in ("status", "progress_status", "counts"):
                    overaccepted_pointer[field] = overaccepted[field]
                overaccepted_body = (
                    json.dumps(
                        overaccepted, sort_keys=True, separators=(",", ":")
                    ) + "\n"
                ).encode()
                receipt_path.write_bytes(overaccepted_body)
                overaccepted_pointer["receipt_sha256"] = hashlib.sha256(
                    overaccepted_body
                ).hexdigest()
                latest.write_text(
                    json.dumps(
                        overaccepted_pointer, sort_keys=True, separators=(",", ":")
                    ) + "\n"
                )
                self.assertEqual(server.sfwmd_source_receipt()["status"], "UNKNOWN")
                future_receipt = json.loads(json.dumps(receipt))
                future_pointer = json.loads(json.dumps(pointer))
                future = "2999-01-01T00:00:00.000000Z"
                future_order = f"{completed}|{future}|{run_id}"
                future_receipt["completed_at"] = future
                future_receipt["observation_order_key"] = future_order
                future_pointer["completed_at"] = future
                future_pointer["observation_order_key"] = future_order
                future_body = (
                    json.dumps(future_receipt, sort_keys=True, separators=(",", ":")) + "\n"
                ).encode()
                receipt_path.write_bytes(future_body)
                future_pointer["receipt_sha256"] = hashlib.sha256(future_body).hexdigest()
                latest.write_text(
                    json.dumps(future_pointer, sort_keys=True, separators=(",", ":")) + "\n"
                )
                self.assertEqual(server.sfwmd_source_receipt()["status"], "UNKNOWN")
                receipt_path.write_bytes(body)
                latest.write_text(
                    json.dumps(pointer, sort_keys=True, separators=(",", ":")) + "\n"
                )
                receipt_path.write_bytes(body + b"tampered")
                rejected = server.sfwmd_source_receipt()
        self.assertEqual(rejected["status"], "UNKNOWN")

    def test_data_desk_copy_never_claims_connection(self):
        html = (ROOT / "cms" / "data.html").read_text(encoding="utf-8")
        self.assertIn('receiptId: "sfwmd-local"', html)
        self.assertIn("Not connected · health UNKNOWN", html)
        self.assertIn("Connection activation remains separately gated", (ROOT / "cms" / "server.py").read_text())


if __name__ == "__main__":
    unittest.main()
