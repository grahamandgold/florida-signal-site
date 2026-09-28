"""Real PostgreSQL regression; always owns a disposable, socket-only cluster."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase/migrations"


class HealthClockDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pg_config = shutil.which("pg_config")
        cls.bin = Path(subprocess.check_output([pg_config, "--bindir"], text=True).strip()) if pg_config else Path("/missing")
        if not (cls.bin / "initdb").exists():
            if os.environ.get("REQUIRE_POSTGRES_TESTS") == "1":
                raise RuntimeError("PostgreSQL server binaries are required")
            raise unittest.SkipTest("PostgreSQL server binaries unavailable")
        cls.temp = tempfile.TemporaryDirectory(prefix="fs-clock-", dir="/tmp")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.base = Path(cls.temp.name)
        cls.data = cls.base / "data"
        subprocess.run([str(cls.bin / "initdb"), "-D", str(cls.data), "-A", "trust", "-U", "postgres", "--no-locale"], check=True, capture_output=True)
        subprocess.run([str(cls.bin / "pg_ctl"), "-D", str(cls.data), "-l", str(cls.base / "server.log"), "-o", f"-k {cls.base} -h ''", "-w", "start"], check=True, capture_output=True)
        cls.addClassCleanup(lambda: subprocess.run([str(cls.bin / "pg_ctl"), "-D", str(cls.data), "-m", "fast", "-w", "stop"], check=True, capture_output=True))
        cls.sql("CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role;")
        old = (MIGRATIONS / "20260811235949_label_source_delay_without_blocking_verified_candidates.sql").read_text()
        cls.old_view = old[old.index("create or replace view"):old.index("revoke all")]
        functions = (MIGRATIONS / "20260811235116_restore_editorial_loop.sql").read_text()
        cls.function = functions[functions.index("create or replace function public.fs_business_days_between"):functions.index("-- Public, aggregate-only")]
        patches = sorted(MIGRATIONS.glob("*_optimize_health_clock_reads.sql"))
        cls.patch = patches[-1].read_text() if patches else ""

    @classmethod
    def sql(cls, query):
        result = subprocess.run([str(cls.bin / "psql"), "-X", "-qAt", "-v", "ON_ERROR_STOP=1", "-h", str(cls.base), "-U", "postgres", "postgres"], input=query, text=True, capture_output=True)
        if result.returncode:
            raise AssertionError(result.stderr)
        return result.stdout.strip()

    def setUp(self):
        self.sql("""DROP SCHEMA public CASCADE; CREATE SCHEMA public;
GRANT USAGE ON SCHEMA public TO anon, authenticated;
CREATE TABLE public.broward_clerk_records_doc(recording_date_iso date, doc_type_code text, visible boolean DEFAULT true);
CREATE TABLE public.broward_property_transfer_map(recording_date date);
CREATE TABLE public.broward_clerk_preliminary(fetched_at timestamptz);
CREATE INDEX idx_brc_doc_recording_date ON public.broward_clerk_records_doc(recording_date_iso);
CREATE INDEX idx_ptm_type_date ON public.broward_property_transfer_map((true), recording_date DESC);
ALTER TABLE public.broward_clerk_records_doc ENABLE ROW LEVEL SECURITY;
CREATE POLICY read_visible ON public.broward_clerk_records_doc FOR SELECT TO anon, authenticated USING (visible);
GRANT SELECT ON ALL TABLES IN SCHEMA public TO anon, authenticated;
""" + self.function + self.old_view + "GRANT SELECT ON public.broward_property_transfer_freshness TO anon, authenticated;")

    def upgrade(self):
        self.sql("BEGIN;" + self.patch + "COMMIT;")

    def clocks(self, role="anon"):
        return json.loads(self.sql(f"SET ROLE {role}; SELECT row_to_json(f) FROM public.broward_property_transfer_freshness f;"))

    def test_clocks_keep_null_empty_filter_and_business_day_semantics(self):
        cases = [([], []), ([(None, 'D')], [None]), ([("2026-09-28", 'M')], ['2026-09-25']),
                 ([("2026-09-25", 'D'), ("2026-09-28", 'M')], ['2026-09-25']),
                 ([("2026-09-28", 'EAS')], ['2026-09-24']),
                 ([("2026-09-28", 'D')], ['2026-09-23']),
                 ([("2026-09-25", 'D')], ['2026-09-28'])]
        for docs, snapshots in cases:
            with self.subTest(docs=docs, snapshots=snapshots):
                self.setUp()
                for date, kind in docs:
                    literal = "NULL" if date is None else f"'{date}'"
                    self.sql(f"INSERT INTO public.broward_clerk_records_doc VALUES ({literal}, '{kind}', true);")
                for date in snapshots:
                    literal = "NULL" if date is None else f"'{date}'"
                    self.sql(f"INSERT INTO public.broward_property_transfer_map VALUES ({literal});")
                before = self.clocks()
                self.upgrade()
                self.assertEqual(before, self.clocks())
                self.assertEqual(before, self.clocks("authenticated"))
                if not docs or docs[0][0] is None or all(k == 'M' for _, k in docs):
                    self.assertIsNone(before['source_event_through'])
                    self.assertFalse(before['editorial_ready'])

    def test_security_invoker_keeps_caller_visibility_and_grants(self):
        self.sql("INSERT INTO public.broward_clerk_records_doc VALUES ('2026-09-22','D',true),('2026-09-28','D',false); INSERT INTO public.broward_property_transfer_map VALUES ('2026-09-22');")
        before = self.clocks()
        self.upgrade()
        self.assertEqual(before, self.clocks())
        self.assertEqual("2026-09-22", self.clocks()['source_event_through'])
        self.assertEqual("2026-09-28", self.clocks('postgres')['source_event_through'])
        self.assertEqual('f', self.sql("SELECT has_table_privilege('anon','public.broward_clerk_preliminary','INSERT');"))

    def test_health_reads_do_not_scan_or_sort_the_corpus(self):
        self.sql("""
INSERT INTO public.broward_clerk_records_doc SELECT date '2020-01-01' + g % 2000, CASE WHEN g % 3 = 0 THEN 'D' ELSE 'M' END, true FROM generate_series(1,60000) g;
INSERT INTO public.broward_clerk_records_doc SELECT date '2030-01-01' + g % 2000, 'M', true FROM generate_series(1,20000) g;
INSERT INTO public.broward_property_transfer_map SELECT date '2020-01-01' + g % 2000 FROM generate_series(1,15000) g;
INSERT INTO public.broward_clerk_preliminary SELECT timestamptz '2020-01-01Z' + g * interval '1 minute' FROM generate_series(1,20000) g;
ANALYZE;
""")
        before_clock = self.clocks()
        before_fetch = self.sql("SELECT max(fetched_at) FROM public.broward_clerk_preliminary;")
        self.upgrade()
        self.assertEqual(before_clock, self.clocks())
        self.assertEqual(before_fetch, self.sql("SELECT max(fetched_at) FROM public.broward_clerk_preliminary;"))
        for query in ["SELECT * FROM public.broward_property_transfer_freshness", "SELECT fetched_at FROM public.broward_clerk_preliminary WHERE fetched_at IS NOT NULL ORDER BY fetched_at DESC LIMIT 1"]:
            plan = json.loads(self.sql("SET ROLE anon; EXPLAIN (ANALYZE, FORMAT JSON) " + query))[0]['Plan']
            def walk(node):
                yield node
                for child in node.get('Plans', []):
                    yield from walk(child)
            for node in walk(plan):
                self.assertNotIn(node['Node Type'], ('Seq Scan', 'Sort'), node)
                self.assertLess(node['Actual Rows'], 20, node)
                self.assertLess(node.get('Rows Removed by Filter', 0), 20, node)

    def test_unknown_view_definition_aborts_without_partial_indexes(self):
        self.sql("CREATE OR REPLACE VIEW public.broward_property_transfer_freshness WITH (security_invoker=true) AS SELECT * FROM (" + self.old_view.split('as\n', 1)[1].rstrip().rstrip(';') + ") f WHERE false;")
        with self.assertRaises(AssertionError):
            self.upgrade()
        self.assertEqual('0', self.sql("SELECT count(*) FROM pg_indexes WHERE indexname IN ('idx_clerk_prelim_fetched_at','idx_brc_doc_transfer_recording_date','idx_ptm_recording_date');"))

    def test_mid_migration_failure_rolls_back_new_index_and_view(self):
        before = self.sql("SELECT pg_get_viewdef('public.broward_property_transfer_freshness'::regclass,true);")
        self.sql("CREATE INDEX idx_ptm_recording_date ON public.broward_property_transfer_map(recording_date);")
        with self.assertRaises(AssertionError):
            self.upgrade()
        self.assertEqual(before, self.sql("SELECT pg_get_viewdef('public.broward_property_transfer_freshness'::regclass,true);"))
        self.assertEqual('0', self.sql("SELECT count(*) FROM pg_indexes WHERE indexname IN ('idx_clerk_prelim_fetched_at','idx_brc_doc_transfer_recording_date');"))

    def test_reviewed_rollback_restores_original_view_and_clocks(self):
        self.sql("INSERT INTO public.broward_clerk_records_doc VALUES ('2026-09-22','D',true); INSERT INTO public.broward_property_transfer_map VALUES ('2026-09-22');")
        before = self.clocks()
        definition = self.sql("SELECT pg_get_viewdef('public.broward_property_transfer_freshness'::regclass,true);")
        self.upgrade()
        rollback = (ROOT / 'supabase/rollback/optimize_health_clock_reads.sql').read_text()
        self.sql('BEGIN;' + rollback + 'COMMIT;')
        self.assertEqual(before, self.clocks())
        self.assertEqual(definition, self.sql("SELECT pg_get_viewdef('public.broward_property_transfer_freshness'::regclass,true);"))
        self.assertEqual('0', self.sql("SELECT count(*) FROM pg_indexes WHERE indexname IN ('idx_clerk_prelim_fetched_at','idx_brc_doc_transfer_recording_date','idx_ptm_recording_date');"))


if __name__ == '__main__':
    unittest.main()
