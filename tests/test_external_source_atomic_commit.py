from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/20260831090000_external_source_atomic_commit.sql"
FDEP = ROOT / "supabase/functions/fdep-erp-sync/index.ts"
FAA = ROOT / "supabase/functions/faa-oeaaa-sync/index.ts"


class ExternalSourceAtomicCommitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text()
        cls.fdep = FDEP.read_text()
        cls.faa = FAA.read_text()

    def test_stage_is_private_and_forced_rls(self):
        self.assertIn("external_source_run_stage force row level security", self.sql)
        self.assertRegex(
            self.sql,
            r"revoke all on table public\.external_source_run_stage\s+from public, anon, authenticated, service_role",
        )
        self.assertNotRegex(self.sql, r"grant .*external_source_run_stage.*(?:anon|authenticated)")

    def test_commit_rpc_is_invoker_only(self):
        self.assertIn("security invoker", self.sql.lower())
        self.assertNotIn("security definer", self.sql.lower())
        self.assertRegex(
            self.sql,
            r"grant execute on function public\.fs_commit_external_source_run\(text, uuid, jsonb, jsonb\)\s+to service_role",
        )
        self.assertRegex(
            self.sql,
            r"revoke all on function public\.fs_commit_external_source_run\(text, uuid, jsonb, jsonb\)\s+from public, anon, authenticated, service_role",
        )

    def test_source_wide_lock_serializes_accounting(self):
        self.assertIn("'florida-signal:external-source:' || p_source_id", self.sql)
        self.assertIn("pg_catalog.hashtextextended", self.sql)
        source_lock = self.sql.index("'florida-signal:external-source:' || p_source_id")
        classify = self.sql.index("count(*) filter (where e.layer_id is null)")
        self.assertLess(source_lock, classify)

    def test_manifest_is_run_bound_and_database_hashed(self):
        self.assertIn("p_source_id || '/' || p_run_id::text", self.sql)
        self.assertIn("'/failure-manifest.json'", self.sql)
        self.assertIn("'/manifest.json'", self.sql)
        self.assertIn("extensions.digest", self.sql)
        self.assertIn("'raw_manifest', p_manifest", self.sql)
        self.assertIn("a manifest-referenced raw evidence object does not exist", self.sql)
        self.assertIn("idempotent replay payload differs", self.sql)
        self.assertIn("receipt contains unknown fields", self.sql)
        self.assertIn("v_expected_receipt := pg_catalog.jsonb_build_object", self.sql)
        for field in (
            "collector_version",
            "parser_version",
            "normalizer_version",
            "attempted_event_from",
            "event_through",
            "schema_contract_sha256",
            "source_schema_sha256",
            "outcomes",
            "source_metadata",
        ):
            self.assertIn(f"'{field}'", self.sql)
        self.assertRegex(
            self.sql,
            re.compile(
                r"to_jsonb\(v_existing\) - array\[.*?'rows_inserted'.*?'created_at'.*?"
                r"is distinct from v_expected_receipt",
                re.S,
            ),
        )
        self.assertNotIn("p_receipt ->> 'raw_manifest_sha256'", self.sql)

    def test_privilege_preflight_checks_every_required_privilege(self):
        for table in ("public.fdep_erp", "public.faa_oeaaa"):
            for privilege in ("select", "insert", "update"):
                self.assertIn(
                    f"has_table_privilege('service_role', '{table}', '{privilege}')",
                    self.sql,
                )
        for privilege in ("select", "insert"):
            self.assertIn(
                "has_table_privilege(\n"
                f"       'service_role', 'public.external_source_run_receipts', '{privilege}'",
                self.sql,
            )
        self.assertIn(
            "has_table_privilege(\n       'service_role', 'storage.objects', 'select'",
            self.sql,
        )

    def test_source_rows_and_receipt_share_one_rpc_transaction(self):
        fdep_upsert = self.sql.index("insert into public.fdep_erp")
        faa_upsert = self.sql.index("insert into public.faa_oeaaa")
        receipt = self.sql.index("insert into public.external_source_run_receipts")
        cleanup = self.sql.index("delete from public.external_source_run_stage", receipt)
        self.assertLess(fdep_upsert, receipt)
        self.assertLess(faa_upsert, receipt)
        self.assertLess(receipt, cleanup)
        self.assertIn("private raw-evidence manifest does not exist", self.sql)

    def test_failed_run_discards_staged_prefix_before_receipt(self):
        self.assertRegex(
            self.sql,
            re.compile(
                r"if v_status = 'failed'.*?delete from public\.external_source_run_stage.*?v_stage_count := 0",
                re.S,
            ),
        )

    def test_collectors_use_stage_manifest_and_rpc_not_direct_source_rest(self):
        for source in (self.fdep, self.faa):
            self.assertIn("/rest/v1/external_source_run_stage", source)
            self.assertIn("/rest/v1/rpc/fs_commit_external_source_run", source)
            self.assertIn("/storage/v1/object/", source)
            self.assertIn('"x-upsert": "false"', source)
            self.assertIn("p_manifest: manifest", source)
            self.assertNotIn("/rest/v1/fdep_erp", source)
            self.assertNotIn("/rest/v1/faa_oeaaa", source)

    def test_query_secret_is_env_only_and_fails_closed(self):
        for source in (self.fdep, self.faa):
            self.assertIn('Deno.env.get("FL_SIGNAL_SYNC_KEY")', source)
            self.assertIn("__FL_SIGNAL_SYNC_KEY_INJECT_AT_DEPLOY__", source)
            self.assertIn("collector authentication is not configured", source)
            self.assertNotRegex(source, r"const SYNC_KEY = \"[^\"]+\"")

    def test_faa_bounds_lookback_and_raw_response_size(self):
        self.assertIn("MAX_LOOKBACK_DAYS = 370", self.faa)
        self.assertIn("lookbackDays > MAX_LOOKBACK_DAYS", self.faa)
        self.assertIn("MAX_YEAR_REQUESTS = 2", self.faa)
        self.assertIn("lastYear - firstYear + 1 > MAX_YEAR_REQUESTS", self.faa)
        self.assertIn("MAX_RAW_RESPONSE_BYTES", self.faa)
        self.assertIn("rawBytes > MAX_RAW_RESPONSE_BYTES", self.faa)
        for source in (self.fdep, self.faa):
            self.assertIn("MAX_TOTAL_RAW_BYTES", source)
            self.assertIn("totalRawBytes > MAX_TOTAL_RAW_BYTES", source)

    def test_typescript_parses_with_node_type_stripping(self):
        for path in (FDEP, FAA):
            subprocess.run(
                ["node", "--experimental-strip-types", "--check", str(path)],
                check=True,
                capture_output=True,
                text=True,
            )


if __name__ == "__main__":
    unittest.main()
