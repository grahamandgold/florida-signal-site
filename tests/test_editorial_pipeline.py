import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "20260811235116_restore_editorial_loop.sql"


class EditorialPipelineContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8")

    def test_current_view_has_a_hard_freshness_gate(self):
        self.assertIn("create or replace view public.broward_property_transfer_current", self.sql)
        self.assertIn("where freshness.snapshot_is_current", self.sql)
        self.assertIn("snapshot_lag_business_days", self.sql)

    def test_candidate_join_is_exact_and_source_backed(self):
        self.assertIn("permit.parcel_id_verified = transfer.folio_canonical", self.sql)
        self.assertIn("'method', 'EXACT_CANONICAL_FOLIO'", self.sql)
        self.assertIn("'schema_version', 'EvidencePacketV1'", self.sql)
        self.assertIn("evidence_hash", self.sql)

    def test_candidate_generation_is_capped_and_idempotent(self):
        self.assertIn("least(coalesce(candidate_limit, 8), 25)", self.sql)
        self.assertIn("on conflict (signal_id) do nothing", self.sql)
        self.assertIn("pg_advisory_xact_lock", self.sql)

    def test_durable_jobs_do_not_publish_or_send(self):
        self.assertIn("cron.schedule", self.sql)
        lowered = self.sql.lower()
        self.assertNotIn("api.mailchimp.com", lowered)
        self.assertNotIn("mailchimp_upsert", lowered)
        self.assertNotIn("publication_registry", lowered)
        self.assertNotIn("insert into public.stories", lowered)

    def test_private_candidate_view_and_functions_are_not_publicly_executable(self):
        self.assertIn("revoke all on schema internal from public, anon, authenticated", self.sql)
        self.assertIn(
            "revoke all on function internal.enqueue_transfer_permit_candidates_v1(integer)",
            self.sql,
        )


if __name__ == "__main__":
    unittest.main()
