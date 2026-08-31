import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260831052701_source_run_ledgers_and_parcel_generations.sql"
)
RUNBOOK = ROOT / "SOURCE_RUN_LEDGER_AND_PARCEL_PROMOTION_RUNBOOK.md"


class SourceRunLedgerMigrationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8").lower()
        cls.runbook = RUNBOOK.read_text(encoding="utf-8").lower()

    def test_fdep_faa_receipts_have_explicit_terminal_contract(self):
        self.assertIn(
            "create table if not exists public.external_source_run_receipts",
            self.sql,
        )
        self.assertIn("source_id in ('fdep_erp', 'faa_oeaaa')", self.sql)
        self.assertIn(
            "status in ('ok', 'empty', 'source_wait', 'partial', 'failed')",
            self.sql,
        )
        for field in (
            "started_at",
            "observed_at",
            "completed_at",
            "attempted_event_from",
            "attempted_event_through",
            "event_through",
            "pages_attempted",
            "pages_succeeded",
            "rows_observed",
            "rows_accepted",
            "rows_inserted",
            "rows_updated",
            "rows_unchanged",
            "rows_rejected",
            "schema_contract_sha256",
            "source_schema_sha256",
            "raw_manifest_sha256",
            "raw_manifest_object_key",
        ):
            self.assertRegex(self.sql, rf"\b{field}\b")
        self.assertIn(
            "rows_observed = rows_accepted + rows_rejected", self.sql
        )
        self.assertIn(
            "rows_accepted = rows_inserted + rows_updated + rows_unchanged",
            self.sql,
        )
        self.assertIn("started_at <= observed_at", self.sql)
        self.assertIn("observed_at <= completed_at", self.sql)

    def test_receipts_are_private_least_privilege_and_append_only(self):
        self.assertIn(
            "alter table public.external_source_run_receipts enable row level security",
            self.sql,
        )
        self.assertIn(
            "alter table public.external_source_run_receipts force row level security",
            self.sql,
        )
        self.assertIn(
            "revoke all on table public.external_source_run_receipts\n  from public, anon, authenticated, service_role",
            self.sql,
        )
        self.assertIn(
            "grant select, insert on table public.external_source_run_receipts to service_role",
            self.sql,
        )
        self.assertNotRegex(
            self.sql,
            r"create\s+policy[^;]+external_source_run_receipts",
        )
        self.assertIn(
            "before update or delete on public.external_source_run_receipts",
            self.sql,
        )
        self.assertIn(
            "before truncate on public.external_source_run_receipts", self.sql
        )
        self.assertIn("external source run receipts are append-only", self.sql)

    def test_parcel_receipts_and_stage_are_generation_bound(self):
        self.assertIn(
            "alter function public.fs_normalize_folio(text) set search_path = pg_catalog",
            self.sql,
        )
        for table in (
            "public.broward_parcel_import_generations",
            "public.broward_parcel_generation_ranges",
            "public.broward_parcel_geography_stage",
        ):
            self.assertIn(f"create table if not exists {table}", self.sql)
            self.assertIn(f"alter table {table} enable row level security", self.sql)
            self.assertIn(f"alter table {table} force row level security", self.sql)
            self.assertIn(f"revoke all on table {table}", self.sql)

        self.assertGreaterEqual(
            self.sql.count(
                "references public.broward_parcel_import_generations(generation_id)"
            ),
            3,
        )
        self.assertIn(
            "unique (generation_id, oid_min, oid_max)", self.sql
        )
        self.assertIn(
            "primary key (generation_id, parcel_id_normalized)", self.sql
        )
        self.assertIn(
            "unique (generation_id, source_object_id)", self.sql
        )
        self.assertIn(
            "rows_received = rows_accepted + rows_rejected + duplicate_folios",
            self.sql,
        )
        for contract_field in (
            "minimum_accepted_rows",
            "max_rejected_rows",
            "max_duplicate_folios",
            "quality_contract_sha256",
        ):
            self.assertRegex(self.sql, rf"\b{contract_field}\b")
        self.assertIn(
            "parcel objectid ranges may not overlap within a generation",
            self.sql,
        )
        self.assertIn("parcel range generation binding is immutable", self.sql)
        self.assertIn("staged parcel generation binding is immutable", self.sql)

    def test_promotion_gate_fails_closed_and_replaces_atomically(self):
        self.assertIn(
            "create or replace function public.fs_promote_broward_parcel_generation",
            self.sql,
        )
        self.assertIn("security definer\nset search_path = ''", self.sql)
        self.assertIn(
            "revoke all on function public.fs_promote_broward_parcel_generation(uuid)\n  from public, anon, authenticated, service_role",
            self.sql,
        )
        for evidence in (
            "range_count <> g.expected_range_count",
            "topology_error_count <> 0",
            "range_oid_min <> g.coverage_oid_min",
            "range_oid_max <> g.coverage_oid_max",
            "sum_expected <> g.source_reported_count",
            "g.rows_rejected > g.max_rejected_rows",
            "g.duplicate_folios > g.max_duplicate_folios",
            "stage_unique_folios <> stage_count",
            "stage_unique_object_ids <> stage_count",
            "stage_invalid_folios <> 0",
            "stage_invalid_bbox <> 0",
            "stage_outside_coverage_count <> 0",
            "stage_range_mismatch_count <> 0",
            "live_user_trigger_count <> 0",
            "live_inbound_fk_count <> 0",
            "lock table public.broward_parcel_geography in access exclusive mode",
            "delete from public.broward_parcel_geography",
            "refresh materialized view public.broward_property_transfer_map",
            "import_generation_id",
            "live_generation_count <> 1",
            "current_user = generation_owner",
        ):
            self.assertIn(evidence, self.sql)
        self.assertNotIn("florida_signal.parcel_promotion_active", self.sql)

        child_lock_position = self.sql.index(
            "lock table public.broward_parcel_generation_ranges in share mode"
        )
        parent_lock_position = self.sql.index(
            "select * into g\n  from public.broward_parcel_import_generations"
        )
        live_lock_position = self.sql.index(
            "lock table public.broward_parcel_geography in access exclusive mode"
        )
        catalog_check_position = self.sql.index(
            "select count(*) into live_user_trigger_count"
        )
        self.assertLess(child_lock_position, parent_lock_position)
        self.assertLess(live_lock_position, catalog_check_position)

        delete_position = self.sql.index(
            "delete from public.broward_parcel_geography"
        )
        insert_position = self.sql.index(
            "insert into public.broward_parcel_geography ("
        )
        readback_position = self.sql.index(
            "select count(*), count(distinct import_generation_id)",
            insert_position,
        )
        self.assertLess(delete_position, insert_position)
        self.assertLess(insert_position, readback_position)

    def test_legacy_unbound_ledgers_are_not_promotion_inputs(self):
        self.assertIn(
            "legacy unbound parcel import log. historical evidence only",
            self.sql,
        )
        self.assertIn(
            "legacy unbound parcel range ledger. historical evidence only",
            self.sql,
        )
        function_sql = self.sql.split(
            "create or replace function public.fs_promote_broward_parcel_generation",
            1,
        )[1]
        self.assertNotIn("from public.broward_parcel_range_ledger", function_sql)
        self.assertNotIn("from public.broward_parcel_import_runs", function_sql)

    def test_migration_does_not_wire_collectors_schedules_or_live_execution(self):
        executable_sql = "\n".join(
            line for line in self.sql.splitlines() if not line.lstrip().startswith("--")
        )
        for forbidden in (
            "cron.schedule",
            "net.http_post",
            "create extension",
            "create or replace function public.fdep_erp_sync",
            "create or replace function public.faa_oeaaa_sync",
            "grant execute on function public.fs_promote_broward_parcel_generation",
        ):
            self.assertNotIn(forbidden, executable_sql)
        self.assertNotRegex(
            executable_sql,
            r"select\s+public\.fs_promote_broward_parcel_generation\s*\(",
        )

    def test_runbook_is_export_first_and_separates_approvals(self):
        for deployed_name in (
            "fdep-erp-sync",
            "faa-oeaaa-sync",
            "broward-parcel-sync",
        ):
            self.assertIn(deployed_name, self.runbook)
        self.assertIn("export-first prerequisite", self.runbook)
        self.assertIn("do not invent", self.runbook)
        self.assertIn("separate production approval", self.runbook)
        self.assertIn("nothing in this runbook authorizes", self.runbook)
        self.assertIn("transactional database rpc", self.runbook)
        self.assertIn("21,838 duplicate-folio source rows", self.runbook)
        self.assertIn("old direct-to-live parcel writer", self.runbook)
        self.assertRegex(
            self.runbook,
            r"do not\s+point the sql test at production",
        )


if __name__ == "__main__":
    unittest.main()
