from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
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
        self.assertIn("revoke all privileges on function", normalized)
        self.assertIn("from public", normalized)
        self.assertIn("aclexplode", normalized)
        self.assertNotIn("security definer", normalized)
        self.assertNotIn("select private.fs_apply_utility_intake_anon_read_hardening", normalized)
        self.assertNotIn("create schema", normalized)
        self.assertNotRegex(normalized, r"revoke\s+all\s+on\s+schema")
        self.assertIn("makes no schema-wide grant", normalized)

    def test_gate_hardens_table_and_column_grants_and_attests_rls_policy(self):
        sql = MIGRATION.read_text(encoding="utf-8").lower()
        self.assertIn("alter table public.permits force row level security", sql)
        self.assertIn("revoke all privileges on table public.permits from anon", sql)
        self.assertIn("grant select on table public.permits to anon", sql)
        self.assertRegex(sql, re.compile(r"revoke insert .*update .*references", re.S))
        self.assertIn("has_column_privilege", sql)
        self.assertIn("has_schema_privilege", sql)
        self.assertIn("pg_has_role", sql)
        self.assertIn("policyname = 'anon_read_permits'", sql)
        self.assertIn("p.permissive = 'restrictive'", sql)
        self.assertIn("cmd in ('all', 'insert', 'update', 'delete')", sql)
        self.assertIn("anon_write', false", sql)


@unittest.skipUnless(
    all(shutil.which(binary) for binary in ("initdb", "pg_ctl", "psql")),
    "local PostgreSQL binaries are unavailable",
)
class UtilityIntakeGrantMigrationPostgresTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="utility-grant-pg-")
        self.root = Path(self.temporary.name)
        self.data = self.root / "data"
        self.socket_dir = self.root / "socket"
        self.socket_dir.mkdir()
        # No TCP listener is created; the port only disambiguates the local
        # Unix-socket filename inside this test's private directory.
        self.port = 50000 + (os.getpid() % 10000)
        try:
            subprocess.run(
                [
                    shutil.which("initdb"), "-D", str(self.data), "--auth=trust",
                    "--no-locale", "--encoding=UTF8",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            self.temporary.cleanup()
            self.skipTest(f"local PostgreSQL cannot initialize: {error.stderr.strip()}")
        subprocess.run(
            [
                shutil.which("pg_ctl"), "-D", str(self.data), "-w", "start",
                "-o", f"-F -h '' -k {self.socket_dir} -p {self.port}",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(self._stop_postgres)

    def _stop_postgres(self):
        subprocess.run(
            [shutil.which("pg_ctl"), "-D", str(self.data), "-m", "immediate", "stop"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.temporary.cleanup()

    def _psql(self, sql: str, *, succeeds: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [
                shutil.which("psql"), "-X", "-v", "ON_ERROR_STOP=1", "-At",
                "-h", str(self.socket_dir), "-p", str(self.port), "-d", "postgres",
                "-c", sql,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if succeeds:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def test_inherited_grants_policies_and_custom_function_acl_fail_closed(self):
        self._psql("""
            create schema private;
            create role anon nologin inherit;
            create role inherited_writer nologin inherit;
            create role custom_executor nologin;
            grant inherited_writer to anon;
            create table public.permits (id integer primary key, note text);
            alter table public.permits enable row level security;
            alter table public.permits force row level security;
            create policy anon_read_permits on public.permits
              for select to anon using (true);
            create function private.fs_apply_utility_intake_anon_read_hardening(text)
              returns jsonb language sql as 'select ''{}''::jsonb';
            revoke all privileges on function
              private.fs_apply_utility_intake_anon_read_hardening(text) from public;
            grant usage on schema private to custom_executor;
            grant execute on function
              private.fs_apply_utility_intake_anon_read_hardening(text) to custom_executor;
        """)
        result = subprocess.run(
            [
                shutil.which("psql"), "-X", "-v", "ON_ERROR_STOP=1",
                "-h", str(self.socket_dir), "-p", str(self.port), "-d", "postgres",
                "-f", str(MIGRATION),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        acl = self._psql("""
            select pg_catalog.has_function_privilege(
              'custom_executor',
              'private.fs_apply_utility_intake_anon_read_hardening(text)',
              'EXECUTE'
            );
        """).stdout.strip()
        self.assertEqual(acl, "f")
        denied = self._psql("""
            set role custom_executor;
            select private.fs_apply_utility_intake_anon_read_hardening('wrong');
        """, succeeds=False)
        self.assertIn("permission denied for function", denied.stderr)

        self._psql("""
            grant insert on public.permits to inherited_writer;
            create policy inherited_insert on public.permits
              for insert to inherited_writer with check (true);
        """)
        policy_attack = self._psql("""
            select private.fs_apply_utility_intake_anon_read_hardening(
              'I_APPROVE_EXACT_UTILITY_INTAKE_ANON_READ_HARDENING'
            );
        """, succeeds=False)
        self.assertIn("effective anon RLS policy contract", policy_attack.stderr)

        self._psql("drop policy inherited_insert on public.permits;")
        self._psql("""
            create policy inherited_restrictive_select on public.permits
              as restrictive for select to inherited_writer using (false);
        """)
        restrictive_select_attack = self._psql("""
            select private.fs_apply_utility_intake_anon_read_hardening(
              'I_APPROVE_EXACT_UTILITY_INTAKE_ANON_READ_HARDENING'
            );
        """, succeeds=False)
        self.assertIn("effective anon RLS policy contract", restrictive_select_attack.stderr)

        self._psql("""
            drop policy inherited_restrictive_select on public.permits;
            create policy public_restrictive_select on public.permits
              as restrictive for select to public using (false);
        """)
        public_restrictive_attack = self._psql("""
            select private.fs_apply_utility_intake_anon_read_hardening(
              'I_APPROVE_EXACT_UTILITY_INTAKE_ANON_READ_HARDENING'
            );
        """, succeeds=False)
        self.assertIn("effective anon RLS policy contract", public_restrictive_attack.stderr)

        self._psql("""
            drop policy public_restrictive_select on public.permits;
            create policy anon_restrictive_select on public.permits
              as restrictive for select to anon using (false);
        """)
        anon_restrictive_attack = self._psql("""
            select private.fs_apply_utility_intake_anon_read_hardening(
              'I_APPROVE_EXACT_UTILITY_INTAKE_ANON_READ_HARDENING'
            );
        """, succeeds=False)
        self.assertIn("effective anon RLS policy contract", anon_restrictive_attack.stderr)

        self._psql("drop policy anon_restrictive_select on public.permits;")
        table_attack = self._psql("""
            select private.fs_apply_utility_intake_anon_read_hardening(
              'I_APPROVE_EXACT_UTILITY_INTAKE_ANON_READ_HARDENING'
            );
        """, succeeds=False)
        self.assertIn("effective anon grants", table_attack.stderr)

        self._psql("""
            revoke insert on public.permits from inherited_writer;
            grant update (note) on public.permits to inherited_writer;
        """)
        column_attack = self._psql("""
            select private.fs_apply_utility_intake_anon_read_hardening(
              'I_APPROVE_EXACT_UTILITY_INTAKE_ANON_READ_HARDENING'
            );
        """, succeeds=False)
        self.assertIn("effective anon grants", column_attack.stderr)

        self._psql("""
            revoke update (note) on public.permits from inherited_writer;
            grant delete on public.permits to public;
        """)
        public_grant_attack = self._psql("""
            select private.fs_apply_utility_intake_anon_read_hardening(
              'I_APPROVE_EXACT_UTILITY_INTAKE_ANON_READ_HARDENING'
            );
        """, succeeds=False)
        self.assertIn("effective anon grants", public_grant_attack.stderr)

        self._psql("""
            revoke delete on public.permits from public;
            create policy public_delete on public.permits for delete to public using (true);
        """)
        public_policy_attack = self._psql("""
            select private.fs_apply_utility_intake_anon_read_hardening(
              'I_APPROVE_EXACT_UTILITY_INTAKE_ANON_READ_HARDENING'
            );
        """, succeeds=False)
        self.assertIn("effective anon RLS policy contract", public_policy_attack.stderr)

        self._psql("""
            drop policy public_delete on public.permits;
            select private.fs_apply_utility_intake_anon_read_hardening(
              'I_APPROVE_EXACT_UTILITY_INTAKE_ANON_READ_HARDENING'
            );
            insert into public.permits values (1, 'visible');
        """)
        visible = self._psql("""
            set role anon;
            select count(*) from public.permits;
        """).stdout.strip().splitlines()[-1]
        self.assertEqual(visible, "1")
        write = self._psql("""
            set role anon;
            insert into public.permits values (1, 'blocked');
        """, succeeds=False)
        self.assertIn("permission denied for table permits", write.stderr)


if __name__ == "__main__":
    unittest.main()
