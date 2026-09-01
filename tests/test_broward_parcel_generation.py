import importlib.util
import json
import sys
import tempfile
import unittest
import uuid
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "ops" / "droplet" / "broward_parcel_generation.py"
MIGRATION_PATH = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260831153000_broward_parcel_generation_pipeline.sql"
)
SERVICE_PATH = ROOT / "ops" / "droplet" / "florida-broward-parcel-generation.service"
TIMER_PATH = ROOT / "ops" / "droplet" / "florida-broward-parcel-generation.timer"
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "broward_parcel_generation"

SPEC = importlib.util.spec_from_file_location("broward_parcel_generation", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FailingFixtureSource(MODULE.FixtureSource):
    def page(self, page_index, object_ids):
        if page_index == 1:
            raise MODULE.ParcelGenerationError("fixture partial failure")
        return super().page(page_index, object_ids)


class DownloadResponse:
    def __init__(self, url, body):
        self._url = url
        self._body = body
        self._offset = 0
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return self._url

    def read(self, size=-1):
        if size < 0:
            size = len(self._body) - self._offset
        chunk = self._body[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


class BrowardParcelGenerationTests(unittest.TestCase):
    def _fixture_observations(self):
        source = MODULE.FixtureSource(FIXTURE_ROOT)
        pages = []
        for page_index, expected in enumerate(([1, 2, 3, 4], [5, 6, 7])):
            payload = source.page(page_index, expected)
            pages.append(
                (
                    page_index,
                    MODULE.sha256_bytes(MODULE.canonical_json_bytes(payload)),
                    MODULE.validate_page(payload, expected),
                )
            )
        return pages

    def _finalize_in_order(self, parent: Path, pages):
        evidence = MODULE.EvidenceBundle(parent / "evidence", str(uuid.uuid4()))
        store = MODULE.ObservationStore(parent / "observations.sqlite")
        try:
            for page_index, raw_sha, observations in pages:
                store.ingest_page(
                    page_index=page_index,
                    raw_sha256=raw_sha,
                    observations=observations,
                )
            return store.finalize(evidence)
        finally:
            store.close()

    def test_contract_hashes_are_fixed_and_distinct(self):
        self.assertRegex(MODULE.PRODUCTION_QUALITY_CONTRACT_SHA256, r"^[0-9a-f]{64}$")
        self.assertRegex(MODULE.CANARY_QUALITY_CONTRACT_SHA256, r"^[0-9a-f]{64}$")
        self.assertNotEqual(
            MODULE.PRODUCTION_QUALITY_CONTRACT_SHA256,
            MODULE.CANARY_QUALITY_CONTRACT_SHA256,
        )
        self.assertEqual(MODULE.PRODUCTION_QUALITY_CONTRACT["minimum_source_rows"], 550_000)
        self.assertEqual(MODULE.PRODUCTION_QUALITY_CONTRACT["maximum_source_rows"], 560_000)

    def test_source_item_identity_is_pinned(self):
        self.assertEqual(MODULE.SOURCE_ITEM_ID, "4b6c15240fdc492a87b8f984b11d2854")
        item = json.loads((FIXTURE_ROOT / "item-metadata.json").read_text())
        layer = json.loads((FIXTURE_ROOT / "metadata.json").read_text())
        self.assertEqual(item["id"], MODULE.SOURCE_ITEM_ID)
        self.assertEqual(layer["serviceItemId"], MODULE.SOURCE_ITEM_ID)

    def test_shuffled_page_and_range_order_are_invariant(self):
        pages = self._fixture_observations()
        with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
            first = self._finalize_in_order(Path(left), pages)
            second = self._finalize_in_order(Path(right), list(reversed(pages)))
        self.assertEqual(first.folio_set_sha256, second.folio_set_sha256)
        self.assertEqual(first.source_object_id_set_sha256, second.source_object_id_set_sha256)
        self.assertEqual(first.source_content_sha256, second.source_content_sha256)
        self.assertEqual(first.winner_content_sha256, second.winner_content_sha256)
        self.assertEqual(
            [(item.range_start, item.range_end, item.rows_accepted) for item in first.range_receipts],
            [(item.range_start, item.range_end, item.rows_accepted) for item in second.range_receipts],
        )

    def test_cross_range_duplicate_has_one_global_winner(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self._finalize_in_order(Path(directory), self._fixture_observations())
        self.assertEqual(result.source_rows, 7)
        self.assertEqual(result.accepted_rows, 2)
        self.assertEqual(result.duplicate_rows, 1)
        self.assertEqual(result.rejected_rows, 4)
        by_start = {item.range_start: item for item in result.range_receipts}
        self.assertEqual(by_start[0].rows_accepted, 1)
        self.assertEqual(by_start[20_000].rows_accepted, 1)
        self.assertEqual(by_start[20_000].duplicates_within_or_across_ranges, 1)

    def test_page_replay_is_idempotent_but_changed_replay_fails(self):
        page_index, raw_sha, observations = self._fixture_observations()[0]
        with tempfile.TemporaryDirectory() as directory:
            store = MODULE.ObservationStore(Path(directory) / "observations.sqlite")
            try:
                self.assertEqual(
                    store.ingest_page(
                        page_index=page_index,
                        raw_sha256=raw_sha,
                        observations=observations,
                    ),
                    "inserted",
                )
                self.assertEqual(
                    store.ingest_page(
                        page_index=page_index,
                        raw_sha256=raw_sha,
                        observations=observations,
                    ),
                    "replayed",
                )
                with self.assertRaisesRegex(
                    MODULE.ParcelGenerationError, "replay changed its evidence"
                ):
                    store.ingest_page(
                        page_index=page_index,
                        raw_sha256="f" * 64,
                        observations=observations,
                    )
            finally:
                store.close()

    def test_canary_is_small_and_never_promotable(self):
        run_id = str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = MODULE.collect_generation(
                source=MODULE.FixtureSource(FIXTURE_ROOT),
                evidence_root=root,
                run_id=run_id,
                mode="canary",
                page_size=4,
                canary_rows=7,
            )
            self.assertEqual(
                (root / run_id / "raw" / "page-000000.json").read_bytes(),
                (FIXTURE_ROOT / "page-0000.json").read_bytes(),
            )
            manifest = json.loads((root / run_id / "manifest.json").read_text())
            raw_page = next(
                item for item in manifest["objects"]
                if item["path"] == "raw/page-000000.json"
            )
            self.assertEqual(
                raw_page["sha256"],
                MODULE.sha256_bytes((FIXTURE_ROOT / "page-0000.json").read_bytes()),
            )
        self.assertEqual(result["status"], "canary_complete")
        self.assertFalse(result["promotion_eligible"])
        self.assertFalse(result["promotion_performed"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["source_rows"], 7)
        self.assertEqual(result["accepted_rows"], 2)

    def test_sink_has_no_promotion_method_and_requires_exact_gate(self):
        self.assertFalse(hasattr(MODULE.SupabaseStagingSink, "promote"))
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(
                MODULE.ParcelGenerationError, "exact staging-only write approval"
            ):
                MODULE.SupabaseStagingSink.from_environment(MODULE.DEFAULT_BUCKET)

    def test_storage_upload_is_roundtrip_hashed_and_size_checked(self):
        body = b"immutable parcel evidence\n"
        sink = MODULE.SupabaseStagingSink(
            url="https://example.invalid", service_key="not-printed"
        )
        object_key = "broward-parcel-generations/00000000-0000-0000-0000-000000000001/raw/page.json"
        info = {
            "id": "10000000-0000-0000-0000-000000000001",
            "updated_at": "2026-08-31T20:00:00Z",
            "metadata": {"size": len(body)},
        }
        with mock.patch.object(
            sink, "_request", side_effect=[{}, info, info]
        ), mock.patch.object(
            MODULE.urllib.request,
            "urlopen",
            return_value=DownloadResponse(
                f"https://example.invalid/storage/v1/object/authenticated/{MODULE.DEFAULT_BUCKET}/{object_key}",
                body,
            ),
        ):
            receipt = sink.upload_once(object_key, body, "application/json")
        self.assertEqual(receipt["bytes"], len(body))
        self.assertEqual(receipt["sha256"], MODULE.sha256_bytes(body))
        self.assertEqual(receipt["storage_object_id"], info["id"])
        self.assertEqual(receipt["storage_updated_at"], info["updated_at"])
        self.assertEqual(receipt["storage_metadata_size"], len(body))
        self.assertEqual(
            receipt["verification_method"],
            "private_storage_roundtrip_sha256_v1",
        )

        with mock.patch.object(
            sink, "_request", side_effect=[{}, info, info]
        ), mock.patch.object(
            MODULE.urllib.request,
            "urlopen",
            return_value=DownloadResponse(
                f"https://example.invalid/storage/v1/object/authenticated/{MODULE.DEFAULT_BUCKET}/{object_key}",
                b"wrong bytes",
            ),
        ):
            with self.assertRaisesRegex(
                MODULE.ParcelGenerationError, "round-trip verification failed"
            ):
                sink.upload_once(object_key, body, "application/json")

        replaced = {
            **info,
            "id": "20000000-0000-0000-0000-000000000002",
        }
        with mock.patch.object(
            sink, "_request", side_effect=[{}, info, replaced]
        ), mock.patch.object(
            MODULE.urllib.request,
            "urlopen",
            return_value=DownloadResponse(
                f"https://example.invalid/storage/v1/object/authenticated/{MODULE.DEFAULT_BUCKET}/{object_key}",
                body,
            ),
        ):
            with self.assertRaisesRegex(
                MODULE.ParcelGenerationError, "version-fenced round-trip"
            ):
                sink.upload_once(object_key, body, "application/json")
        with mock.patch.dict(
            "os.environ",
            {
                "FL_SIGNAL_PARCEL_WRITE_APPROVAL": MODULE.WRITE_APPROVAL,
                "SUPABASE_URL": "http://example.invalid?key=unsafe",
                "SUPABASE_SERVICE_ROLE_KEY": "not-printed",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(
                MODULE.ParcelGenerationError, "credential-free HTTPS origin"
            ):
                MODULE.SupabaseStagingSink.from_environment(MODULE.DEFAULT_BUCKET)

    def test_timer_is_default_off_marker_gated_and_nonblocking(self):
        service = SERVICE_PATH.read_text(encoding="utf-8")
        timer = TIMER_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "ConditionPathExists=/etc/florida-signal/enable-broward-parcel-generation",
            service,
        )
        self.assertIn("/usr/bin/flock --nonblock", service)
        self.assertIn("OnFailure=florida-freshness-alert.service", service)
        self.assertIn("OnCalendar=*-*-02 05:20:00 UTC", timer)
        self.assertNotIn("systemctl enable", service + timer)
        sql = MIGRATION_PATH.read_text(encoding="utf-8")
        self.assertIn("broward_parcel_one_staging_current_generation_idx", sql)

    def test_contract_hashes_match_reviewed_migration_rows(self):
        sql = MIGRATION_PATH.read_text(encoding="utf-8")
        self.assertIn(MODULE.PRODUCTION_QUALITY_CONTRACT_SHA256, sql)
        self.assertIn(MODULE.CANARY_QUALITY_CONTRACT_SHA256, sql)

    def test_small_current_generation_cannot_pass_production_contract(self):
        run_id = str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(
                MODULE.ParcelGenerationError, "source row count outside reviewed contract"
            ):
                MODULE.collect_generation(
                    source=MODULE.FixtureSource(FIXTURE_ROOT),
                    evidence_root=root,
                    run_id=run_id,
                    mode="current_generation",
                    page_size=4,
                    canary_rows=7,
                )
            failure = json.loads((root / run_id / "failure-receipt.json").read_text())
        self.assertEqual(failure["status"], "failed")
        self.assertFalse(failure["promotion_eligible"])

    def test_partial_failure_preserves_evidence_and_cannot_promote(self):
        run_id = str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(MODULE.ParcelGenerationError, "partial failure"):
                MODULE.collect_generation(
                    source=FailingFixtureSource(FIXTURE_ROOT),
                    evidence_root=root,
                    run_id=run_id,
                    mode="canary",
                    page_size=4,
                    canary_rows=7,
                )
            run_root = root / run_id
            failure = json.loads((run_root / "failure-receipt.json").read_text())
            self.assertTrue((run_root / "raw" / "page-000000.json").exists())
            self.assertFalse((run_root / "receipt.json").exists())
        self.assertEqual(failure["status"], "failed")
        self.assertFalse(failure["promotion_eligible"])

    def test_migration_keeps_live_table_out_of_collector_permissions(self):
        sql = MIGRATION_PATH.read_text(encoding="utf-8").lower()
        self.assertIn("revoke insert, update, delete, truncate", sql)
        self.assertIn("on public.broward_parcel_geography", sql)
        self.assertIn("from service_role", sql)
        self.assertIn("force row level security", sql)
        self.assertNotIn(
            "grant execute on function public.fs_promote_broward_parcel_generation(uuid) to service_role",
            sql,
        )
        for table in (
            "broward_parcel_evidence_objects",
            "broward_parcel_generation_pages",
            "broward_parcel_generation_observations",
            "broward_parcel_generation_ranges",
            "broward_parcel_geography_stage",
        ):
            self.assertNotIn(f"grant insert on table public.{table} to service_role", sql)
        self.assertGreaterEqual(sql.count("security definer\nset search_path = ''"), 6)

    def test_promotion_requires_reviewed_preview_and_backup(self):
        sql = MIGRATION_PATH.read_text(encoding="utf-8").lower()
        self.assertIn("broward_parcel_promotion_previews", sql)
        self.assertIn("broward_parcel_promotion_authorizations", sql)
        self.assertIn("backup_object_key", sql)
        self.assertIn("backup_sha256", sql)
        self.assertIn("backup_storage_object_id", sql)
        self.assertIn("backup_storage_updated_at", sql)
        self.assertIn("owner_private_storage_download_sha256_v1", sql)
        self.assertIn("current_generation_only_no_historical_backfill", sql)
        self.assertIn("promotion_eligible", sql)
        self.assertIn("run_mode <> 'current_generation'", sql)
        self.assertIn("broward-parcel-backups/", sql)
        self.assertIn("position(backup_sha256 in backup_object_key) > 0", sql)
        self.assertIn("live parcel state changed after preview", sql)
        self.assertIn(
            "lock table public.broward_parcel_geography in access exclusive mode",
            sql,
        )

    def test_database_requires_append_only_storage_attestations(self):
        sql = MIGRATION_PATH.read_text(encoding="utf-8").lower()
        collector = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("create table public.broward_parcel_evidence_objects", sql)
        self.assertIn("broward_parcel_evidence_no_row_mutation", sql)
        self.assertIn("storage_object_id", sql)
        self.assertIn("storage_updated_at", sql)
        self.assertIn("storage_metadata_size", sql)
        self.assertIn("on o.id = e.storage_object_id", sql)
        self.assertIn("and o.updated_at = e.storage_updated_at", sql)
        self.assertIn("private_storage_roundtrip_sha256_v1", sql)
        self.assertIn("p_evidence_objects", sql)
        self.assertIn("p_evidence_objects", collector)
        self.assertIn("_download_digest", collector)
        self.assertIn("/storage/v1/object/authenticated/", collector)
        self.assertNotIn("p_source_content_sha256", sql)
        self.assertIn("observed_source_content_hash", sql)
        self.assertNotIn(
            "message = 'private raw page object is absent'",
            sql,
        )


if __name__ == "__main__":
    unittest.main()
