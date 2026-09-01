from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/20260831235500_utility_intake_anon_read_hardening.sql"


class UtilityIntakeGrantMigrationTests(unittest.TestCase):
    def test_gate_is_default_off_owner_only_and_exactly_scoped(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        normalized = " ".join(sql.lower().split())
        self.assertIn("security invoker", normalized)
        self.assertIn("set search_path = ''", normalized)
        self.assertIn("i_approve_exact_utility_intake_anon_read_hardening", normalized)
        self.assertIn("revoke execute on function", normalized)
        self.assertIn("from public, anon, authenticated, service_role", normalized)
        self.assertNotIn("security definer", normalized)
        self.assertNotIn("select private.fs_apply_utility_intake_anon_read_hardening", normalized)

    def test_gate_hardens_table_and_column_grants_and_attests_rls_policy(self):
        sql = MIGRATION.read_text(encoding="utf-8").lower()
        self.assertIn("alter table public.permits force row level security", sql)
        self.assertIn("revoke all privileges on table public.permits from anon", sql)
        self.assertIn("grant select on table public.permits to anon", sql)
        self.assertRegex(sql, re.compile(r"revoke insert .*update .*references", re.S))
        self.assertIn("information_schema.column_privileges", sql)
        self.assertIn("policyname = 'anon_read_permits'", sql)
        self.assertIn("cmd in ('all', 'insert', 'update', 'delete')", sql)
        self.assertIn("anon_write', false", sql)


if __name__ == "__main__":
    unittest.main()
