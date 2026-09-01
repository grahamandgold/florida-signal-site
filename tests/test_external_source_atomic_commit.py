from pathlib import Path
import json
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/20260901173100_external_source_atomic_commit.sql"
SCHEDULE_MIGRATION = ROOT / "supabase/migrations/20260901173200_external_source_collector_cron_cutover.sql"
FDEP = ROOT / "supabase/functions/fdep-erp-sync/index.ts"
FDEP_NORMALIZER = ROOT / "supabase/functions/fdep-erp-sync/normalize.ts"
FAA = ROOT / "supabase/functions/faa-oeaaa-sync/index.ts"
FAA_PARSER = ROOT / "supabase/functions/faa-oeaaa-sync/parser.ts"
FAA_DENO = ROOT / "supabase/functions/faa-oeaaa-sync/deno.json"
FDEP_FIXTURE = ROOT / "tests/fixtures/fdep_layer_normalization.json"
FAA_FIXTURES = ROOT / "tests/fixtures"


class ExternalSourceAtomicCommitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text()
        cls.fdep = FDEP.read_text()
        cls.faa = FAA.read_text()
        cls.schedule_sql = SCHEDULE_MIGRATION.read_text()

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
        self.assertIn("p_manifest -> 'terminal_receipt' is distinct from p_receipt", self.sql)
        self.assertIn("manifest terminal receipt does not match", self.sql)
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
        for schema in ("public", "storage", "extensions"):
            self.assertIn(
                f"has_schema_privilege('service_role', '{schema}', 'usage')",
                self.sql,
            )
        self.assertIn("has_sequence_privilege(", self.sql)
        self.assertIn("'extensions.digest(bytea,text)', 'execute'", self.sql)

    def test_migration_versions_follow_live_history(self):
        live_latest = 20260901052118
        self.assertGreater(int(MIGRATION.name.split("_", 1)[0]), live_latest)
        self.assertGreater(
            int(SCHEDULE_MIGRATION.name.split("_", 1)[0]),
            int(MIGRATION.name.split("_", 1)[0]),
        )
        self.assertFalse((MIGRATION.parent / "20260831090000_external_source_atomic_commit.sql").exists())

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
            self.assertIn("collector database connection is not configured", source)
            self.assertIn('"Cache-Control": "no-store"', source)
            self.assertIn('"X-Content-Type-Options": "nosniff"', source)
            self.assertNotRegex(source, r"const SYNC_KEY = \"[^\"]+\"")

    def test_sync_secret_is_header_only_and_never_read_from_url(self):
        for source in (self.fdep, self.faa):
            self.assertIn('SYNC_KEY_HEADER = "x-florida-signal-sync-key"', source)
            self.assertIn("request.headers.get(SYNC_KEY_HEADER)", source)
            self.assertNotIn('url.searchParams.get("key")', source)

    def test_collectors_bound_every_fetch_and_recover_ambiguous_commit(self):
        for source in (self.fdep, self.faa):
            self.assertEqual(source.count("await fetch("), 1)
            self.assertIn("async function fetchBounded(", source)
            self.assertIn("OVERALL_RUN_BUDGET_MS = 115_000", source)
            self.assertIn("FAILURE_RECEIPT_RESERVE_MS = 20_000", source)
            self.assertIn("COMMIT_ATTEMPTS = 3", source)
            self.assertIn("async function readCommittedReceipt(", source)
            self.assertIn("/rest/v1/external_source_run_receipts?", source)
            self.assertIn("recovered_after_ambiguous_response: true", source)
            self.assertIn("manifest.terminal_receipt = terminalReceipt", source)
            self.assertIn('"source_metadata",', source)
            self.assertIn("canonicalJson(retainedManifest) !== canonicalJson(expectedManifest)", source)
            self.assertIn("canonicalJson(expectedReceipt)", source)
            self.assertIn("retained payload is not the attempted terminal commit", source)
            self.assertIn('url.searchParams.get("dispatch_id")', source)
            self.assertIn('dispatch_id: dispatchId', source)
            self.assertIn('commit_state: "unknown"', source)
            self.assertIn("do not write a contradictory failure receipt", source)
            unknown_guard = source.index("if (error instanceof CommitStateUnknownError)")
            failure_manifest = source.index("failure-manifest.json", unknown_guard)
            self.assertLess(unknown_guard, failure_manifest)

    def test_fdep_pagination_fails_closed_on_zero_progress(self):
        self.assertIn("payload.exceededTransferLimit && features.length === 0", self.fdep)
        self.assertIn("pagination made no progress while more rows were reported", self.fdep)
        self.assertIn("payload.exceededTransferLimit && rows.size === identitiesBeforePage", self.fdep)
        self.assertIn("pagination produced no new identities while more rows were reported", self.fdep)
        unsafe_break = "if (!payload.exceededTransferLimit || features.length === 0) break"
        self.assertNotIn(unsafe_break, self.fdep)

    def test_schedule_cutover_is_secret_safe_and_default_off(self):
        sql = self.schedule_sql
        for table in (
            "external_source_collector_dispatches",
            "external_source_run_alerts",
        ):
            self.assertIn(f"alter table public.{table} force row level security", sql)
            self.assertRegex(
                sql,
                rf"revoke all on table public\.{table}\s+from public, anon, authenticated, service_role",
            )
        for function in (
            "fs_dispatch_external_source",
            "fs_check_external_source_health",
            "fs_disable_external_source_schedules",
            "fs_activate_external_source_schedules",
        ):
            self.assertIn(f"function public.{function}", sql)
        self.assertNotIn("security definer", sql.lower())
        self.assertNotIn("select cron.schedule(", sql.lower())
        self.assertIn("perform cron.schedule(", sql.lower())
        self.assertIn("20 9 * * *", sql)
        self.assertIn("40 9 * * *", sql)
        self.assertIn("10 10,11 * * *", sql)
        self.assertIn("0 12 * * *", sql)
        self.assertIn("fl_signal_functions_base_url", sql)
        self.assertIn("fl_signal_external_source_sync_key", sql)
        self.assertIn("cron.schedule(text,text,text)", sql)
        self.assertIn("cron.unschedule(bigint)", sql)
        self.assertIn("net.http_post(text,jsonb,jsonb,jsonb,integer)", sql)
        self.assertIn("vault.decrypted_secrets", sql)
        self.assertIn("dispatch_id uuid not null unique", sql)
        self.assertIn("'?dispatch_id=' || v_dispatch_id::text", sql)
        self.assertIn("dispatch_kind = 'scheduled'", sql)
        self.assertIn("source_metadata ->> 'dispatch_id' = v_dispatch_id::text", sql)
        self.assertIn("'missing_dispatch'", sql)
        self.assertNotIn("jrjewmzkyluxdywyusrw", sql)
        self.assertNotRegex(sql, r"https://[a-z0-9-]+\.supabase\.co/functions/v1")
        self.assertNotRegex(
            sql,
            r"grant\s+(?:usage|select|usage,\s*select).*"
            r"external_source_(?:collector_dispatches|run_alerts)_id_seq",
        )
        self.assertIn(
            "$job$select public.fs_dispatch_external_source('fdep_erp');$job$",
            sql,
        )
        self.assertIn(
            "$job$select public.fs_dispatch_external_source('faa_oeaaa');$job$",
            sql,
        )
        self.assertIn("command ilike '%key=%'", sql)
        self.assertIn("'missing_receipt'", sql)

    def test_disposable_postgres_harness_executes_real_migration(self):
        runner = (ROOT / "tests/run_external_source_atomic_postgres.sh").read_text()
        assertions = (ROOT / "tests/sql/external_source_atomic_assertions.sql").read_text()
        schedule_assertions = (
            ROOT / "tests/sql/external_source_schedule_assertions.sql"
        ).read_text()
        self.assertIn("postgres:17-alpine", runner)
        self.assertIn("FL_SIGNAL_TEST_DATABASE_URL", runner)
        self.assertIn("FL_SIGNAL_DISPOSABLE_TEST_CONFIRM", runner)
        self.assertIn("fl_signal_atomic_test", runner)
        self.assertIn("locally managed fallback requires PostgreSQL 17 tools", runner)
        self.assertIn("hosted/linked Supabase endpoints", runner)
        self.assertIn("target is not an empty disposable PostgreSQL database", runner)
        self.assertIn(str(MIGRATION.relative_to(ROOT)), runner)
        self.assertIn(str(SCHEDULE_MIGRATION.relative_to(ROOT)), runner)
        self.assertIn("external_source_schedule_assertions.sql", runner)
        self.assertIn("fs_commit_external_source_run", assertions)
        self.assertIn("generated in_broward", assertions)
        self.assertIn("receipt failure must roll back source upsert", assertions)
        self.assertIn("exact replay must be idempotent", assertions)
        self.assertIn("failed terminal commit must discard staged prefix", assertions)
        self.assertIn("FDEP exact replay must be idempotent", assertions)
        self.assertIn("FDEP receipt failure must roll back", assertions)
        self.assertIn("schedule migration must be default-off", schedule_assertions)
        self.assertIn("watchdog must require the exact scheduled dispatch UUID", schedule_assertions)
        self.assertIn("rollback must still preserve unrelated cron jobs", schedule_assertions)
        self.assertIn(
            "read-only dispatch access must not grant service_role sequence privileges",
            schedule_assertions,
        )
        self.assertIn(
            "read-only alert access must not grant service_role sequence privileges",
            schedule_assertions,
        )

    def test_fdep_layer_specific_normalizer_fixture(self):
        script = f"""
          import assert from "node:assert/strict";
          import fs from "node:fs";
          import {{ assertLayerSchema, layerDateWhere, layerReceivedDateField, layerSourceContract, mapFeature, resolveSince }} from {json.dumps(FDEP_NORMALIZER.as_uri())};
          const fixture = JSON.parse(fs.readFileSync({json.dumps(str(FDEP_FIXTURE))}, "utf8"));
          const sourceContract = layerSourceContract();
          for (const [name, sample] of Object.entries(fixture)) {{
            const layer = Number(name.slice(-1));
            const row = mapFeature(layer, sample.feature);
            const {{ raw, ...normalized }} = row;
            assert.deepEqual(normalized, sample.expected);
            assert.deepEqual(raw, sample.feature.attributes);
            assertLayerSchema(layer, {{ fields: sourceContract[String(layer)].map((field) => ({{ name: field }})) }});
          }}
          const incomplete = sourceContract["0"].filter((name) => name !== "RECEIVE_DATE");
          assert.throws(
            () => assertLayerSchema(0, {{ fields: incomplete.map((name) => ({{ name }})) }}),
            /layer 0 source schema missing: RECEIVE_DATE/,
          );
          assert.equal(layerReceivedDateField(0), "RECEIVE_DATE");
          assert.equal(layerReceivedDateField(1), "RECEIVED_DATE");
          assert.throws(() => layerReceivedDateField(2), /unsupported FDEP layer 2/);
          assert.equal(
            layerDateWhere(0, "2026-06-02", "2026-08-31"),
            "RECEIVE_DATE >= DATE '2026-06-02' AND RECEIVE_DATE < DATE '2026-09-01'",
          );
          assert.equal(
            layerDateWhere(1, "2026-08-27", "2026-08-31"),
            "RECEIVED_DATE >= DATE '2026-08-27' AND RECEIVED_DATE < DATE '2026-09-01'",
          );
          const now = new Date("2026-08-31T12:00:00.000Z");
          assert.deepEqual(resolveSince(null, now), {{
            since: "2026-06-02",
            sinceMode: "default_90_day_lookback",
            through: "2026-08-31",
          }});
          assert.deepEqual(resolveSince("2026-08-27", now), {{
            since: "2026-08-27",
            sinceMode: "explicit",
            through: "2026-08-31",
          }});
          assert.throws(() => resolveSince("2025-01-01", now), /within 370 days/);
          assert.throws(() => resolveSince("2026-02-30", now), /within 370 days/);
          assert.throws(() => resolveSince("2026-09-01", now), /within 370 days/);
        """
        subprocess.run(
            ["node", "--experimental-strip-types", "--input-type=module", "--eval", script],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn('assertLayerSchema(layer, payload)', self.fdep)
        self.assertIn('where: layerDateWhere(layer, since, through)', self.fdep)
        self.assertNotIn(': "1=1"', self.fdep)
        self.assertIn('since_mode: sinceMode', self.fdep)
        self.assertIn('window_semantics: WINDOW_SEMANTICS', self.fdep)
        self.assertIn('attempted_event_from: `${since}T00:00:00.000Z`', self.fdep)
        self.assertIn('attempted_event_through: `${through}T23:59:59.999Z`', self.fdep)
        self.assertIn('fdep-row-v3-layer-specific', self.fdep)

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

    def test_faa_generated_broward_flag_is_database_owned(self):
        self.assertNotIn("in_broward", self.faa)
        self.assertIn(
            "array['first_fetched_at','last_fetched_at','in_broward']::text[]",
            self.sql,
        )
        faa_dml = self.sql[
            self.sql.index("insert into public.faa_oeaaa"):
            self.sql.index("  end if;", self.sql.index("insert into public.faa_oeaaa"))
        ]
        self.assertNotIn("in_broward", faa_dml)

    def test_faa_validated_xml_parser_fixtures(self):
        script = f"""
          import assert from "node:assert/strict";
          import fs from "node:fs";
          import {{
            FAA_MAX_ENTITY_EXPANDED_LENGTH,
            FAA_MAX_ENTITY_EXPANSIONS,
            FAA_MAX_NESTED_TAGS,
            faaContractShape,
            faaSourceContract,
            parseFaaCaseList,
          }} from {json.dumps(FAA_PARSER.as_uri())};
          const read = (name) => fs.readFileSync({json.dumps(str(FAA_FIXTURES))} + "/" + name, "utf8");

          const oe = parseFaaCaseList(
            read("faa_case_list_oe_valid.xml"), "OE", 2026, "application/xml;charset=UTF-8",
          );
          assert.equal(oe.observed, 1);
          assert.equal(oe.rows.length, 1);
          assert.equal(oe.rows[0].case_id, 654321);
          assert.equal(oe.rows[0].sponsor, "Example & Sons");
          assert.equal(oe.rows[0].structure_description, "Tower < Crane & Lift");
          assert.equal(oe.rows[0].sponsor_city, 'Fort "Lauderdale"');
          assert.equal(oe.rows[0].nearest_airport, "Example's Field");
          assert.equal(oe.rows[0].raw.caseId, "654321");
          assert.equal(oe.rows[0].raw.sponsor, "Example & Sons");
          assert(oe.schemaTags.has("field:OE:caseId"));

          const liveXml = read("faa_case_list_oe_live_contract_2026_08_31.xml");
          const liveEntityReferences = liveXml.match(
            /&(?:amp|lt|gt|quot|apos|#[0-9]+|#x[0-9a-f]+);/gi,
          ) ?? [];
          assert.equal(liveEntityReferences.length, 1_627);
          assert.equal(FAA_MAX_ENTITY_EXPANSIONS, 4_096);
          assert(FAA_MAX_ENTITY_EXPANSIONS > liveEntityReferences.length);
          assert.equal(FAA_MAX_ENTITY_EXPANDED_LENGTH, 1_000_000);
          assert.equal(FAA_MAX_NESTED_TAGS, 8);
          const liveOe = parseFaaCaseList(
            liveXml, "OE", 2026, "application/xml;charset=UTF-8",
          );
          assert.equal(liveOe.observed, 1);
          assert.equal(liveOe.rows[0].case_id, 876543);
          assert.equal((liveOe.rows[0].structure_description.match(/&/g) ?? []).length, 1_627);
          assert.equal(liveOe.rows[0].raw.amslOverallHeightDet, "321");
          assert.equal(liveOe.rows[0].raw.dateBuilt, "2026-08-01");
          assert.equal(liveOe.rows[0].raw.fccAsrNumber, "1234567");
          assert.equal(liveOe.rows[0].raw.recommendedMarkLightType, "MARKED_AND_LIGHTED");
          assert.equal(liveOe.rows[0].raw.recommendedMarkLightTypeOther, "NONE");

          const overEntityLimit = liveXml.replace(
            /<structureDescription>[\s\S]*?<\/structureDescription>/,
            "<structureDescription>" + "&amp; ".repeat(FAA_MAX_ENTITY_EXPANSIONS + 1)
              + "</structureDescription>",
          );
          assert.throws(
            () => parseFaaCaseList(overEntityLimit, "OE", 2026, "application/xml"),
            /Entity expansion count limit exceeded/,
          );
          const overDepthLimit = liveXml.replace(
            /<sponsor>[\s\S]*?<\/sponsor>/,
            "<sponsor><a><b><c><d><e><f><g><h>too deep</h></g></f></e></d></c></b></a></sponsor>",
          );
          assert.throws(
            () => parseFaaCaseList(overDepthLimit, "OE", 2026, "application/xml"),
            /maximum nested tags exceeded/i,
          );

          const nra = parseFaaCaseList(
            read("faa_case_list_nra_valid.xml"), "NRA", 2026, "text/xml",
          );
          assert.equal(nra.observed, 1);
          assert.equal(nra.rows[0].case_id, 765432);
          assert.equal(nra.rows[0].date_entered, "2026-08-29");
          assert.equal(nra.rows[0].structure_description, "Office & retail");

          const empty = parseFaaCaseList(
            read("faa_case_list_empty.xml"), "OE", 2026, "application/xml;charset=UTF-8",
          );
          assert.deepEqual(empty.rows, []);
          assert.equal(empty.observed, 0);
          assert.deepEqual([...empty.schemaTags].sort(), ["envelope:caseList", "expected-case:OECase"]);

          assert.throws(
            () => parseFaaCaseList(read("faa_case_list_error_200.html"), "OE", 2026, "text/html"),
            /not an XML media type/,
          );
          assert.throws(
            () => parseFaaCaseList(read("faa_case_list_error_200.html"), "OE", 2026, "application/xml"),
            /root must be caseList/,
          );
          assert.throws(
            () => parseFaaCaseList(read("faa_case_list_malformed.xml"), "OE", 2026, "application/xml"),
            /FAA XML is malformed/,
          );
          assert.throws(
            () => parseFaaCaseList(read("faa_case_list_schema_drift.xml"), "OE", 2026, "application/xml"),
            /schema drift: unknown fields: id/,
          );
          assert.throws(
            () => parseFaaCaseList(
              '<caseList><OECase><caseId>1</caseId><asn>A</asn><caseType>OE</caseType><year>2026</year><dateEntered>2026-08-30</dateEntered><latitude>1</latitude><longitude>-1</longitude><sponsor>A &bogus; B</sponsor></OECase></caseList>',
              "OE", 2026, "application/xml",
            ),
            /undeclared entity/,
          );
          assert.throws(
            () => parseFaaCaseList(
              '<!DOCTYPE caseList [<!ENTITY x "unsafe">]><caseList/>',
              "OE", 2026, "application/xml",
            ),
            /DOCTYPE is not allowed/,
          );
          assert(!faaContractShape().includes("in_broward"));
          const contract = faaSourceContract();
          assert(contract.OE.required_fields.includes("caseId"));
          assert(!contract.OE.allowed_fields.includes("id"));
          for (const field of [
            "amslOverallHeightDet", "dateBuilt", "fccAsrNumber",
            "recommendedMarkLightType", "recommendedMarkLightTypeOther",
          ]) assert(contract.OE.allowed_fields.includes(field));
        """
        subprocess.run(
            ["node", "--experimental-strip-types", "--input-type=module", "--eval", script],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertNotIn("matchAll", self.faa)
        self.assertNotRegex(self.faa, r'tag\(block,\s*["\']id["\']\)')
        self.assertIn("parseFaaCaseList(rawXml, type, year", self.faa)
        self.assertIn("faa-xml-v4-bounded-live-contract", self.faa)
        self.assertIn("faa-row-v4-live-contract", self.faa)
        self.assertIn("source_contract: faaSourceContract()", self.faa)
        self.assertEqual(json.loads(FAA_DENO.read_text())["imports"], {
            "@nodable/entities": "npm:@nodable/entities@3.0.0",
            "fast-xml-parser": "npm:fast-xml-parser@5.11.1",
            "fast-xml-validator": "npm:fast-xml-validator@1.4.2",
        })
        package_dependencies = json.loads((ROOT / "package.json").read_text())["dependencies"]
        self.assertEqual(package_dependencies["@nodable/entities"], "3.0.0")
        self.assertEqual(package_dependencies["fast-xml-parser"], "5.11.1")
        self.assertEqual(package_dependencies["fast-xml-validator"], "1.4.2")

    def test_typescript_parses_with_node_type_stripping(self):
        for path in (FDEP, FDEP_NORMALIZER, FAA, FAA_PARSER):
            subprocess.run(
                ["node", "--experimental-strip-types", "--check", str(path)],
                check=True,
                capture_output=True,
                text=True,
            )


if __name__ == "__main__":
    unittest.main()
