import importlib.util
import json
import sys
import tempfile
import traceback
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
    def _read_failure_bundle(self, run_root: Path):
        failure = json.loads((run_root / "failure-receipt.json").read_text())
        binding = failure["evidence_manifest"]
        manifest_path = run_root / binding["path"]
        manifest_body = manifest_path.read_bytes()
        manifest = json.loads(manifest_body)
        self.assertEqual(binding["path"], "failure-manifest.json")
        self.assertEqual(binding["bytes"], len(manifest_body))
        self.assertEqual(binding["sha256"], MODULE.sha256_bytes(manifest_body))
        self.assertEqual(
            binding["schema_version"], MODULE.FAILURE_EVIDENCE_MANIFEST_SCHEMA
        )
        self.assertEqual(
            manifest["schema_version"], MODULE.FAILURE_EVIDENCE_MANIFEST_SCHEMA
        )
        self.assertEqual(binding["object_count"], len(manifest["objects"]))
        self.assertEqual(manifest["object_count"], len(manifest["objects"]))
        self.assertEqual(
            manifest_body,
            MODULE.canonical_json_bytes(manifest) + b"\n",
        )
        self.assertEqual(
            manifest["objects"],
            sorted(
                manifest["objects"],
                key=lambda item: (
                    item["path"],
                    item["sha256"],
                    item["bytes"],
                    item["media_type"],
                ),
            ),
        )
        self.assertNotIn(
            "failure-manifest.json",
            {item["path"] for item in manifest["objects"]},
        )
        for item in manifest["objects"]:
            body = (run_root / item["path"]).read_bytes()
            self.assertEqual(item["bytes"], len(body), item["path"])
            self.assertEqual(
                item["sha256"], MODULE.sha256_bytes(body), item["path"]
            )
        return failure, manifest

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
        self.assertEqual(
            MODULE.PRODUCTION_QUALITY_CONTRACT["normalizer_version"],
            MODULE.NORMALIZER_VERSION,
        )
        self.assertEqual(
            MODULE.PRODUCTION_QUALITY_CONTRACT["field_null_policy"]["sale_date_1"],
            MODULE.SALE_DATE_FIELD_NULL_POLICY,
        )

    def test_source_item_identity_is_pinned(self):
        self.assertEqual(MODULE.SOURCE_ITEM_ID, "4b6c15240fdc492a87b8f984b11d2854")
        item = json.loads((FIXTURE_ROOT / "item-metadata.json").read_text())
        layer = json.loads((FIXTURE_ROOT / "metadata.json").read_text())
        self.assertEqual(item["id"], MODULE.SOURCE_ITEM_ID)
        self.assertEqual(layer["serviceItemId"], MODULE.SOURCE_ITEM_ID)
        sale_date_field = next(
            field for field in layer["fields"] if field["name"] == "SALE_DATE_1"
        )
        self.assertEqual(sale_date_field["type"], "esriFieldTypeDate")

    def test_durable_directory_creation_uses_exact_mkdir_and_parent_fsync_sequence(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            run_root = parent / "run-id"
            raw_root = run_root / "raw"
            manifests_root = run_root / "manifests"
            real_mkdir = MODULE.os.mkdir
            manager = mock.Mock()
            with mock.patch.object(
                MODULE.os,
                "mkdir",
                side_effect=real_mkdir,
            ) as mkdir, mock.patch.object(
                MODULE.os,
                "open",
                side_effect=[51, 52, 53],
            ) as open_directory, mock.patch.object(
                MODULE.os, "fsync"
            ) as fsync, mock.patch.object(MODULE.os, "close") as close:
                manager.attach_mock(mkdir, "mkdir")
                manager.attach_mock(open_directory, "open")
                manager.attach_mock(fsync, "fsync")
                manager.attach_mock(close, "close")
                MODULE.create_durable_directory(run_root)
                MODULE.create_durable_directory(raw_root)
                MODULE.create_durable_directory(manifests_root)
        directory_flags = MODULE.os.O_RDONLY | getattr(MODULE.os, "O_DIRECTORY", 0)
        self.assertEqual(
            manager.mock_calls,
            [
                mock.call.mkdir(run_root, 0o700),
                mock.call.open(parent, directory_flags),
                mock.call.fsync(51),
                mock.call.close(51),
                mock.call.mkdir(raw_root, 0o700),
                mock.call.open(run_root, directory_flags),
                mock.call.fsync(52),
                mock.call.close(52),
                mock.call.mkdir(manifests_root, 0o700),
                mock.call.open(run_root, directory_flags),
                mock.call.fsync(53),
                mock.call.close(53),
            ],
        )

    def test_run_raw_and_manifest_directories_are_parent_fsynced_in_order(self):
        run_id = str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as directory:
            evidence_root = Path(directory) / "evidence"
            evidence_root.mkdir()
            with mock.patch.object(
                MODULE,
                "fsync_directory",
                wraps=MODULE.fsync_directory,
            ) as fsync_directory:
                evidence = MODULE.EvidenceBundle(evidence_root, run_id)
                evidence.write_json("raw/page.json", {"raw": True})
                evidence.write_json("manifests/range.json", {"range": True})
            run_root = evidence_root / run_id
            self.assertEqual(
                [call.args[0] for call in fsync_directory.call_args_list],
                [
                    evidence_root,
                    run_root,
                    run_root / "raw",
                    run_root,
                    run_root / "manifests",
                ],
            )
            self.assertEqual(run_root.stat().st_mode & 0o777, 0o700)
            self.assertEqual((run_root / "raw").stat().st_mode & 0o777, 0o700)
            self.assertEqual(
                (run_root / "manifests").stat().st_mode & 0o777,
                0o700,
            )

    def test_negative_arcgis_epoch_milliseconds_preserve_pre_1970_sale_date(self):
        feature = json.loads(
            (FIXTURE_ROOT / "sale-date-negative-epoch.json").read_text()
        )
        observation = MODULE.normalize_feature(feature)
        self.assertEqual(observation.sale_date_1, "1967-04-26")
        self.assertEqual(observation.field_null_reasons, {})
        self.assertEqual(observation.attributes["SALE_DATE_1"], -84_758_400_000)
        self.assertIsNone(observation.rejection_reason)

    def test_overflow_epoch_is_explicit_field_null_without_row_rejection(self):
        feature = json.loads(
            (FIXTURE_ROOT / "sale-date-overflow-epoch.json").read_text()
        )
        observation = MODULE.normalize_feature(feature)
        self.assertIsNone(observation.sale_date_1)
        self.assertEqual(
            observation.field_null_reasons,
            {"sale_date_1": MODULE.SALE_DATE_OUT_OF_RANGE_REASON},
        )
        self.assertEqual(
            observation.attributes["SALE_DATE_1"],
            MODULE.SALE_DATE_MAX_EPOCH_MS + 1,
        )
        self.assertIsNone(observation.rejection_reason)

    def test_sale_date_never_guesses_units_or_coerces_malformed_values(self):
        self.assertEqual(MODULE.sale_date(None), (None, None))
        for value in ("", "0", True, 0.5, float("nan"), float("inf")):
            with self.subTest(value=value):
                self.assertEqual(
                    MODULE.sale_date(value),
                    (None, MODULE.SALE_DATE_INVALID_REASON),
                )
        self.assertEqual(MODULE.sale_date(0), ("1970-01-01", None))
        self.assertEqual(
            MODULE.sale_date(MODULE.SALE_DATE_MIN_EPOCH_MS),
            (MODULE.SALE_DATE_MIN, None),
        )
        self.assertEqual(
            MODULE.sale_date(MODULE.SALE_DATE_MAX_EPOCH_MS),
            (MODULE.SALE_DATE_MAX, None),
        )
        for value in (
            MODULE.SALE_DATE_MIN_EPOCH_MS - 1,
            MODULE.SALE_DATE_MAX_EPOCH_MS + 1,
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    MODULE.sale_date(value),
                    (None, MODULE.SALE_DATE_OUT_OF_RANGE_REASON),
                )

    def test_missing_required_sale_date_attribute_fails_closed(self):
        feature = json.loads(
            (FIXTURE_ROOT / "sale-date-negative-epoch.json").read_text()
        )
        del feature["attributes"]["SALE_DATE_1"]
        with self.assertRaisesRegex(
            MODULE.ParcelGenerationError,
            "feature omitted required SALE_DATE_1 attribute",
        ):
            MODULE.normalize_feature(feature)

    def test_field_null_accounting_is_orthogonal_to_source_row_partition(self):
        features = [
            json.loads(
                (FIXTURE_ROOT / "sale-date-negative-epoch.json").read_text()
            ),
            json.loads(
                (FIXTURE_ROOT / "sale-date-overflow-epoch.json").read_text()
            ),
        ]
        observations = [MODULE.normalize_feature(feature) for feature in features]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = MODULE.EvidenceBundle(root / "evidence", str(uuid.uuid4()))
            store = MODULE.ObservationStore(root / "observations.sqlite")
            try:
                store.ingest_page(
                    page_index=0,
                    raw_sha256="a" * 64,
                    observations=observations,
                )
                result = store.finalize(evidence)
            finally:
                store.close()
            field_null_rows = [
                json.loads(line)
                for line in (evidence.root / result.field_nulls_path)
                .read_text()
                .splitlines()
            ]
        self.assertEqual(result.source_rows, 2)
        self.assertEqual(result.accepted_rows, 2)
        self.assertEqual(result.rejected_rows, 0)
        self.assertEqual(result.duplicate_rows, 0)
        self.assertEqual(result.field_null_rows, 1)
        self.assertEqual(
            result.field_null_counts[MODULE.SALE_DATE_OUT_OF_RANGE_REASON], 1
        )
        self.assertEqual(len(field_null_rows), 1)
        self.assertEqual(
            field_null_rows[0]["attributes"]["SALE_DATE_1"],
            MODULE.SALE_DATE_MAX_EPOCH_MS + 1,
        )
        self.assertEqual(MODULE.quality_gate("canary", result), [])

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
            self.assertTrue(
                (root / run_id / "manifests" / "field-nulls.jsonl").exists()
            )
            self.assertNotIn(
                "receipt.json",
                {item["path"] for item in manifest["objects"]},
            )
        self.assertEqual(result["status"], "canary_complete")
        self.assertFalse(result["promotion_eligible"])
        self.assertFalse(result["promotion_performed"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["source_rows"], 7)
        self.assertEqual(result["accepted_rows"], 2)
        self.assertEqual(result["field_null_rows"], 0)

    def test_sink_has_no_promotion_method_and_requires_exact_gate(self):
        self.assertFalse(hasattr(MODULE.SupabaseStagingSink, "promote"))
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(
                MODULE.ParcelGenerationError, "exact staging-only write approval"
            ):
                MODULE.SupabaseStagingSink.from_environment(MODULE.DEFAULT_BUCKET)
        with mock.patch.dict(
            "os.environ",
            {"FL_SIGNAL_PARCEL_WRITE_APPROVAL": MODULE.WRITE_APPROVAL},
            clear=True,
        ):
            with self.assertRaisesRegex(
                MODULE.ParcelGenerationError,
                "exact parcel failure-evidence upload/binding approval",
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
                "FL_SIGNAL_PARCEL_FAILURE_EVIDENCE_APPROVAL": (
                    MODULE.FAILURE_EVIDENCE_WRITE_APPROVAL
                ),
                "SUPABASE_URL": "http://example.invalid?key=unsafe",
                "SUPABASE_SERVICE_ROLE_KEY": "not-printed",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(
                MODULE.ParcelGenerationError, "credential-free HTTPS origin"
            ):
                MODULE.SupabaseStagingSink.from_environment(MODULE.DEFAULT_BUCKET)

    def test_storage_upload_exact_existing_object_is_idempotent_not_upserted(self):
        body = b"immutable parcel failure evidence\n"
        sink = MODULE.SupabaseStagingSink(
            url="https://example.invalid",
            service_key="not-printed",
        )
        object_key = (
            "broward-parcel-generations/"
            "00000000-0000-0000-0000-000000000001/failure-manifest.json"
        )
        info = {
            "id": "10000000-0000-0000-0000-000000000001",
            "updated_at": "2026-08-31T20:00:00Z",
            "metadata": {"size": len(body)},
        }
        with mock.patch.object(
            sink,
            "_request",
            side_effect=[
                MODULE.ImmutableStorageObjectAlreadyExists("already exists"),
                info,
                info,
            ],
        ) as request, mock.patch.object(
            MODULE.urllib.request,
            "urlopen",
            return_value=DownloadResponse(
                f"https://example.invalid/storage/v1/object/authenticated/"
                f"{MODULE.DEFAULT_BUCKET}/{object_key}",
                body,
            ),
        ):
            receipt = sink.upload_once(object_key, body, "application/json")
        self.assertEqual(receipt["upload_disposition"], "verified_existing")
        self.assertEqual(receipt["sha256"], MODULE.sha256_bytes(body))
        self.assertEqual(
            request.call_args_list[0].kwargs["extra_headers"],
            {"x-upsert": "false"},
        )
        self.assertTrue(
            request.call_args_list[0].kwargs["allow_immutable_object_exists"]
        )
        self.assertTrue(
            sink._is_immutable_object_exists_response(
                json.dumps({"statusCode": "409", "error": "Duplicate", "message": "The resource already exists"})
            )
        )
        self.assertTrue(
            sink._is_immutable_object_exists_response(
                json.dumps({"message": "Asset Already Exists"})
            )
        )
        self.assertFalse(
            sink._is_immutable_object_exists_response(
                json.dumps({"message": "invalid bucket"})
            )
        )

    def test_failure_pair_upload_and_rpc_binding_are_exact_and_replayable(self):
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
            manifest_body = (run_root / "failure-manifest.json").read_bytes()
            receipt_body = (run_root / "failure-receipt.json").read_bytes()
            sink = MODULE.SupabaseStagingSink(
                url="https://example.invalid",
                service_key="not-printed",
                failure_evidence_write_approved=True,
            )
            storage_rows = [
                {
                    "bytes": len(manifest_body),
                    "object_key": (
                        f"broward-parcel-generations/{run_id}/failure-manifest.json"
                    ),
                    "sha256": MODULE.sha256_bytes(manifest_body),
                    "storage_metadata_size": len(manifest_body),
                    "storage_object_id": "10000000-0000-0000-0000-000000000001",
                    "storage_updated_at": "2026-08-31T20:00:00Z",
                    "upload_disposition": "created",
                    "verification_method": "private_storage_roundtrip_sha256_v1",
                },
                {
                    "bytes": len(receipt_body),
                    "object_key": (
                        f"broward-parcel-generations/{run_id}/failure-receipt.json"
                    ),
                    "sha256": MODULE.sha256_bytes(receipt_body),
                    "storage_metadata_size": len(receipt_body),
                    "storage_object_id": "20000000-0000-0000-0000-000000000002",
                    "storage_updated_at": "2026-08-31T20:00:01Z",
                    "upload_disposition": "created",
                    "verification_method": "private_storage_roundtrip_sha256_v1",
                },
            ]
            database_result = {
                "failure_manifest_object_key": storage_rows[0]["object_key"],
                "failure_manifest_sha256": storage_rows[0]["sha256"],
                "failure_receipt_object_key": storage_rows[1]["object_key"],
                "failure_receipt_sha256": storage_rows[1]["sha256"],
                "generation_id": run_id,
                "status": "failed",
            }
            with mock.patch.object(
                sink,
                "upload_once",
                side_effect=storage_rows,
            ) as upload, mock.patch.object(
                sink,
                "rpc",
                return_value=database_result,
            ) as rpc:
                result = sink.bind_failure_evidence(
                    run_root=run_root,
                    run_id=run_id,
                )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_manifest_upload"], "created")
        self.assertEqual(result["failure_receipt_upload"], "created")
        self.assertEqual(upload.call_count, 2)
        self.assertEqual(upload.call_args_list[0].args[1], manifest_body)
        self.assertEqual(upload.call_args_list[1].args[1], receipt_body)
        rpc.assert_called_once()
        function_name, payload = rpc.call_args.args
        self.assertEqual(function_name, "fs_fail_broward_parcel_generation")
        self.assertEqual(payload["p_generation_id"], run_id)
        self.assertEqual(payload["p_failure_manifest_storage"], storage_rows[0])
        self.assertEqual(payload["p_failure_receipt_storage"], storage_rows[1])
        self.assertEqual(
            payload["p_failure_manifest_body"], manifest_body.decode("utf-8")
        )
        self.assertEqual(
            payload["p_failure_receipt_body"], receipt_body.decode("utf-8")
        )
        self.assertNotIn("not-printed", json.dumps(payload, sort_keys=True))

    def test_failure_pair_upload_refuses_missing_gate_or_local_tamper(self):
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
            gated_sink = MODULE.SupabaseStagingSink(
                url="https://example.invalid",
                service_key="not-printed",
            )
            with self.assertRaisesRegex(
                MODULE.ParcelGenerationError,
                "exact parcel failure-evidence upload/binding approval",
            ):
                gated_sink.bind_failure_evidence(
                    run_root=run_root,
                    run_id=run_id,
                )

            approved_sink = MODULE.SupabaseStagingSink(
                url="https://example.invalid",
                service_key="not-printed",
                failure_evidence_write_approved=True,
            )
            manifest = json.loads(
                (run_root / "failure-manifest.json").read_text()
            )
            referenced_path = run_root / manifest["objects"][0]["path"]
            referenced_body = referenced_path.read_bytes()
            referenced_path.write_bytes(referenced_body + b"tamper")
            with self.assertRaisesRegex(
                MODULE.ParcelGenerationError,
                "references changed local evidence",
            ), mock.patch.object(approved_sink, "upload_once") as upload:
                approved_sink.bind_failure_evidence(
                    run_root=run_root,
                    run_id=run_id,
                )
            upload.assert_not_called()
            referenced_path.write_bytes(referenced_body)

            manifest_path = run_root / "failure-manifest.json"
            manifest_path.write_bytes(manifest_path.read_bytes() + b"tamper")
            with self.assertRaisesRegex(
                MODULE.ParcelGenerationError,
                "absent or invalid|not canonical|does not reconcile",
            ), mock.patch.object(approved_sink, "upload_once") as upload:
                approved_sink.bind_failure_evidence(
                    run_root=run_root,
                    run_id=run_id,
                )
            upload.assert_not_called()

    def test_failure_binding_cli_is_explicit_and_source_free(self):
        run_id = str(uuid.uuid4())
        args = MODULE.parse_args(
            [
                "--bind-existing-failure",
                "--write-supabase",
                "--run-id",
                run_id,
                "--evidence-root",
                "/tmp/parcel-failure-replay-test",
            ]
        )
        self.assertTrue(args.bind_existing_failure)
        self.assertTrue(args.write_supabase)
        self.assertEqual(args.run_id, run_id)
        self.assertFalse(args.allow_network)
        self.assertIsNone(args.fixture_dir)

        sink = mock.Mock(spec=MODULE.SupabaseStagingSink)
        sink.bind_failure_evidence.return_value = {
            "generation_id": run_id,
            "status": "replayed",
        }
        with mock.patch.object(
            MODULE.SupabaseStagingSink,
            "from_environment",
            return_value=sink,
        ), mock.patch.object(MODULE, "ArcGISSource") as arcgis, mock.patch.object(
            MODULE, "FixtureSource"
        ) as fixture, mock.patch("builtins.print"):
            exit_code = MODULE.main(
                [
                    "--bind-existing-failure",
                    "--write-supabase",
                    "--run-id",
                    run_id,
                    "--evidence-root",
                    "/tmp/parcel-failure-replay-test",
                ]
            )
        self.assertEqual(exit_code, 0)
        arcgis.assert_not_called()
        fixture.assert_not_called()
        sink.verify_private_bucket.assert_called_once_with()
        sink.bind_failure_evidence.assert_called_once_with(
            run_root=Path("/tmp/parcel-failure-replay-test") / run_id,
            run_id=run_id,
        )

        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            MODULE.parse_args(
                [
                    "--bind-existing-failure",
                    "--run-id",
                    run_id,
                    "--evidence-root",
                    "/tmp/parcel-failure-replay-test",
                ]
            )
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            MODULE.parse_args(
                [
                    "--allow-network",
                    "--bind-existing-failure",
                    "--write-supabase",
                    "--run-id",
                    run_id,
                    "--evidence-root",
                    "/tmp/parcel-failure-replay-test",
                ]
            )

    def test_staging_failure_automatically_attempts_dual_binding(self):
        run_id = str(uuid.uuid4())
        sink = mock.Mock(spec=MODULE.SupabaseStagingSink)
        sink.service_key = "synthetic-service-key"
        object_counter = 0

        def upload_once(object_key, body, _media_type):
            nonlocal object_counter
            object_counter += 1
            return {
                "bytes": len(body),
                "object_key": object_key,
                "sha256": MODULE.sha256_bytes(body),
                "storage_metadata_size": len(body),
                "storage_object_id": str(uuid.UUID(int=object_counter)),
                "storage_updated_at": "2026-08-31T20:00:00Z",
                "upload_disposition": "created",
                "verification_method": "private_storage_roundtrip_sha256_v1",
            }

        def rpc(function_name, _payload, **_kwargs):
            if function_name == "fs_begin_broward_parcel_generation":
                return {"status": "staging"}
            if function_name == "fs_stage_broward_parcel_page":
                raise MODULE.ParcelGenerationError(
                    "synthetic staging failure echoed synthetic-service-key"
                )
            self.fail(f"unexpected RPC {function_name}")

        sink.upload_once.side_effect = upload_once
        sink.rpc.side_effect = rpc
        sink.bind_failure_evidence.return_value = {"status": "failed"}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(MODULE.ParcelGenerationError) as raised:
                MODULE.collect_generation(
                    source=MODULE.FixtureSource(FIXTURE_ROOT),
                    evidence_root=root,
                    run_id=run_id,
                    mode="canary",
                    page_size=4,
                    canary_rows=7,
                    sink=sink,
                )
            run_root = root / run_id
            self.assertTrue((run_root / "failure-manifest.json").is_file())
            self.assertTrue((run_root / "failure-receipt.json").is_file())
            failure_receipt = (
                run_root / "failure-receipt.json"
            ).read_text()
            self.assertNotIn("synthetic-service-key", failure_receipt)
            self.assertNotIn("synthetic-service-key", str(raised.exception))
            rendered_traceback = "".join(
                traceback.format_exception(
                    type(raised.exception),
                    raised.exception,
                    raised.exception.__traceback__,
                )
            )
            self.assertNotIn("synthetic-service-key", rendered_traceback)
            self.assertTrue(raised.exception.__suppress_context__)
            self.assertIn(
                MODULE.REDACTED_SUPABASE_CREDENTIAL,
                failure_receipt,
            )
            sink.bind_failure_evidence.assert_called_once_with(
                run_root=run_root,
                run_id=run_id,
            )

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
        self.assertIn(
            MODULE.canonical_json_bytes(MODULE.PRODUCTION_QUALITY_CONTRACT).decode(),
            sql,
        )
        self.assertIn(
            MODULE.canonical_json_bytes(MODULE.CANARY_QUALITY_CONTRACT).decode(),
            sql,
        )

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
            failure, manifest = self._read_failure_bundle(run_root)
            self.assertTrue((run_root / "raw" / "page-000000.json").exists())
            self.assertFalse((run_root / "receipt.json").exists())
            paths = [item["path"] for item in manifest["objects"]]
            self.assertEqual(paths, sorted(paths))
            self.assertEqual(len(paths), len(set(paths)))
            for expected_path in (
                "raw/source-metadata.json",
                "raw/source-metadata.json.request.json",
                "raw/source-item-metadata.json",
                "raw/source-item-metadata.json.request.json",
                "raw/object-ids-start.json",
                "raw/object-ids-start.json.request.json",
                "raw/page-000000.json",
                "raw/page-000000.json.request.json",
            ):
                self.assertIn(expected_path, paths)
            self.assertNotIn("raw/page-000001.json", paths)
            by_path = {item["path"]: item for item in manifest["objects"]}
            for tampered_path in (
                "raw/page-000000.json",
                "raw/source-metadata.json",
            ):
                path = run_root / tampered_path
                original = path.read_bytes()
                path.write_bytes(original + b"tamper")
                self.assertNotEqual(
                    by_path[tampered_path]["sha256"],
                    MODULE.sha256_bytes(path.read_bytes()),
                )
                self.assertNotEqual(by_path[tampered_path]["bytes"], path.stat().st_size)
                path.write_bytes(original)
        self.assertEqual(failure["status"], "failed")
        self.assertFalse(failure["promotion_eligible"])

    def test_failure_manifest_is_durable_before_terminal_failure_receipt(self):
        run_id = str(uuid.uuid4())
        original_write_once = MODULE.write_once

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            MODULE,
            "write_once",
            side_effect=original_write_once,
        ) as write_once:
            with self.assertRaisesRegex(MODULE.ParcelGenerationError, "partial failure"):
                MODULE.collect_generation(
                    source=FailingFixtureSource(FIXTURE_ROOT),
                    evidence_root=Path(directory),
                    run_id=run_id,
                    mode="canary",
                    page_size=4,
                    canary_rows=7,
                )
            immutable_paths = [call.args[0].name for call in write_once.call_args_list]
            self.assertLess(
                immutable_paths.index("failure-manifest.json"),
                immutable_paths.index("failure-receipt.json"),
            )

    def test_attempted_success_receipt_is_preserved_but_not_double_counted(self):
        run_id = str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = MODULE.EvidenceBundle(root, run_id)
            evidence.write_json("base.json", {"bound": True})
            receipt_path, receipt_sha = evidence.write_terminal_receipt(
                {"run_id": run_id, "status": "canary_complete"}
            )
            binding = evidence.finish_failure_manifest()
            manifest = json.loads(
                (root / run_id / binding["path"]).read_text()
            )
        self.assertEqual(receipt_path, "receipt.json")
        self.assertEqual(
            evidence.attempted_terminal_receipt,
            {
                "bytes": len(
                    MODULE.canonical_json_bytes(
                        {"run_id": run_id, "status": "canary_complete"}
                    )
                    + b"\n"
                ),
                "media_type": "application/json",
                "path": "receipt.json",
                "sha256": receipt_sha,
            },
        )
        self.assertEqual([item["path"] for item in manifest["objects"]], ["base.json"])

    def test_ambiguous_terminal_binding_closes_with_reconcilable_failure_manifest(self):
        with tempfile.TemporaryDirectory() as dry_directory:
            dry_result = MODULE.collect_generation(
                source=MODULE.FixtureSource(FIXTURE_ROOT),
                evidence_root=Path(dry_directory),
                run_id=str(uuid.uuid4()),
                mode="canary",
                page_size=4,
                canary_rows=7,
            )

        run_id = str(uuid.uuid4())
        sink = mock.Mock(spec=MODULE.SupabaseStagingSink)
        sink.service_key = "synthetic-service-key"
        object_counter = 0

        def upload_once(object_key, body, _media_type):
            nonlocal object_counter
            object_counter += 1
            return {
                "bytes": len(body),
                "object_key": object_key,
                "sha256": MODULE.sha256_bytes(body),
                "storage_metadata_size": len(body),
                "storage_object_id": str(uuid.UUID(int=object_counter)),
                "storage_updated_at": "2026-09-01T16:00:00Z",
                "upload_disposition": "created",
                "verification_method": "private_storage_roundtrip_sha256_v1",
            }

        def rpc(function_name, payload, **_kwargs):
            if function_name == "fs_begin_broward_parcel_generation":
                return {"status": "staging"}
            if function_name == "fs_stage_broward_parcel_page":
                return {"status": "staged"}
            if function_name == "fs_finalize_broward_parcel_generation":
                return {
                    "duplicate_rows": dry_result["duplicate_rows"],
                    "folio_set_sha256": dry_result["folio_set_sha256"],
                    "generation_id": run_id,
                    "promotion_eligible": False,
                    "promotion_eligible_on_receipt": False,
                    "rejected_rows": dry_result["rejected_rows"],
                    "rows_accepted": dry_result["accepted_rows"],
                    "rows_received": dry_result["source_rows"],
                    "sale_date_1_field_null_rows": dry_result["field_null_rows"],
                    "source_content_sha256": "a" * 64,
                    "source_object_id_set_sha256": payload[
                        "p_source_object_id_set_sha256"
                    ],
                    "status": "validated",
                    "system_object_id_set_sha256": payload[
                        "p_system_object_id_set_sha256"
                    ],
                    "terminal_status": "canary_complete",
                }
            if function_name == "fs_commit_broward_parcel_generation_receipt":
                raise MODULE.ParcelGenerationError(
                    "synthetic ambiguous terminal receipt response"
                )
            self.fail(f"unexpected RPC {function_name}")

        sink.upload_once.side_effect = upload_once
        sink.rpc.side_effect = rpc
        sink.bind_failure_evidence.return_value = {"status": "failed"}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(
                MODULE.ParcelGenerationError,
                "synthetic ambiguous terminal receipt response",
            ):
                MODULE.collect_generation(
                    source=MODULE.FixtureSource(FIXTURE_ROOT),
                    evidence_root=root,
                    run_id=run_id,
                    mode="canary",
                    page_size=4,
                    canary_rows=7,
                    sink=sink,
                )
            run_root = root / run_id
            failure, manifest = self._read_failure_bundle(run_root)
            attempted = failure["attempted_terminal_receipt"]
            receipt_body = (run_root / "receipt.json").read_bytes()
            self.assertEqual(attempted["path"], "receipt.json")
            self.assertEqual(attempted["bytes"], len(receipt_body))
            self.assertEqual(attempted["sha256"], MODULE.sha256_bytes(receipt_body))
            self.assertNotIn(
                "receipt.json",
                {item["path"] for item in manifest["objects"]},
            )
            sink.bind_failure_evidence.assert_called_once_with(
                run_root=run_root,
                run_id=run_id,
            )

    def test_mid_capture_failure_manifest_includes_raw_before_request_receipt(self):
        run_id = str(uuid.uuid4())
        original_write_json = MODULE.EvidenceBundle.write_json

        def fail_page_request_receipt(evidence, relative_path, value):
            if relative_path == "raw/page-000000.json.request.json":
                raise RuntimeError("fixture request receipt write failed")
            return original_write_json(evidence, relative_path, value)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(
                MODULE.EvidenceBundle,
                "write_json",
                new=fail_page_request_receipt,
            ):
                with self.assertRaisesRegex(
                    MODULE.ParcelGenerationError,
                    "fixture request receipt write failed",
                ):
                    MODULE.collect_generation(
                        source=MODULE.FixtureSource(FIXTURE_ROOT),
                        evidence_root=root,
                        run_id=run_id,
                        mode="canary",
                        page_size=4,
                        canary_rows=7,
                    )
            run_root = root / run_id
            failure, manifest = self._read_failure_bundle(run_root)
            by_path = {item["path"]: item for item in manifest["objects"]}
            raw_path = "raw/page-000000.json"
            self.assertIn(raw_path, by_path)
            self.assertNotIn(f"{raw_path}.request.json", by_path)
            raw_body = (run_root / raw_path).read_bytes()
            self.assertEqual(by_path[raw_path]["bytes"], len(raw_body))
            self.assertEqual(
                by_path[raw_path]["sha256"], MODULE.sha256_bytes(raw_body)
            )
        self.assertEqual(failure["failure_stage"], "raw_page_capture")
        self.assertEqual(failure["raw_page_path"], "raw/page-000000.json")
        self.assertEqual(failure["source_accounting"]["raw_pages_captured"], 1)
        self.assertEqual(failure["source_accounting"]["raw_rows_captured"], 4)
        self.assertEqual(failure["source_accounting"]["indexed_rows"], 0)
        self.assertEqual(failure["source_accounting"]["raw_rows_not_indexed"], 4)

    def test_unexpected_normalization_failure_has_durable_terminal_receipt(self):
        run_id = str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(
                MODULE,
                "sale_date",
                side_effect=RuntimeError("unexpected normalization fixture"),
            ):
                with self.assertRaises(MODULE.ParcelGenerationError) as raised:
                    MODULE.collect_generation(
                        source=MODULE.FixtureSource(FIXTURE_ROOT),
                        evidence_root=root,
                        run_id=run_id,
                        mode="canary",
                        page_size=4,
                        canary_rows=7,
                    )
            run_root = root / run_id
            failure_path = run_root / "failure-receipt.json"
            failure_body = failure_path.read_bytes()
            failure, manifest = self._read_failure_bundle(run_root)
            failure_sha256 = MODULE.sha256_bytes(failure_body)
            raw_page_path = run_root / "raw" / "page-000000.json"
            raw_page_sha256 = MODULE.sha256_bytes(raw_page_path.read_bytes())
            self.assertEqual(failure_path.stat().st_mode & 0o777, 0o600)
            self.assertTrue(raw_page_path.is_file())
            self.assertFalse((run_root / "receipt.json").exists())
        self.assertEqual(failure["status"], "failed")
        self.assertEqual(failure["reason_code"], "ROW_NORMALIZATION_FAILURE")
        self.assertEqual(failure["failure_stage"], "page_normalization")
        self.assertEqual(failure["error_class"], "RuntimeError")
        self.assertEqual(failure["error_message"], "unexpected normalization fixture")
        self.assertEqual(failure["raw_page_path"], "raw/page-000000.json")
        self.assertEqual(failure["raw_page_sha256"], raw_page_sha256)
        self.assertEqual(failure["source_accounting"]["selected_source_rows"], 7)
        self.assertEqual(failure["source_accounting"]["indexed_pages"], 0)
        self.assertEqual(failure["source_accounting"]["raw_rows_captured"], 4)
        self.assertEqual(failure["source_accounting"]["indexed_rows"], 0)
        self.assertEqual(failure["source_accounting"]["raw_rows_not_indexed"], 4)
        self.assertFalse(failure["source_accounting"]["row_partition_complete"])
        self.assertFalse(failure["promotion_eligible"])
        self.assertIn(
            "raw/page-000000.json",
            {item["path"] for item in manifest["objects"]},
        )
        self.assertIn(f"sha256={failure_sha256}", str(raised.exception))

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

    def test_failure_rpc_atomically_binds_manifest_and_receipt(self):
        sql = MIGRATION_PATH.read_text(encoding="utf-8").lower()
        self.assertIn("add column failure_receipt_sha256 text", sql)
        self.assertIn("add column failure_receipt_object_key text", sql)
        self.assertIn("'failure_manifest'", sql)
        self.assertIn(
            "p_failure_manifest_body text,\n  p_failure_receipt_body text,\n  p_failure_manifest_storage jsonb,\n  p_failure_receipt_storage jsonb",
            sql,
        )
        self.assertIn(
            "drop function if exists public.fs_fail_broward_parcel_generation(uuid, jsonb)",
            sql,
        )
        self.assertIn("'/failure-manifest.json'", sql)
        self.assertIn("'/failure-receipt.json'", sql)
        self.assertIn("e.purpose = 'failure_manifest'", sql)
        self.assertIn("e.purpose = 'failure_receipt'", sql)
        self.assertIn("raw_manifest_sha256 = manifest_sha", sql)
        self.assertIn("raw_manifest_object_key = manifest_key", sql)
        self.assertIn("failure_receipt_sha256 = receipt_sha", sql)
        self.assertIn("failure_receipt_object_key = receipt_key", sql)
        self.assertIn(
            "failure evidence replay changed the immutable pair",
            sql,
        )
        self.assertIn(
            "failure manifest differs from the immutable evidence ledger",
            sql,
        )
        self.assertIn("jsonb_array_elements(failure_manifest->'objects')", sql)
        self.assertIn("p_failure_manifest_body", sql)
        self.assertIn("p_failure_receipt_body", sql)
        self.assertIn(
            "old.status in ('validated', 'ready', 'canary_complete')",
            sql,
        )
        self.assertIn(
            "old_status is null\n     or old_status not in ('staging', 'validated', 'canary_complete', 'ready')",
            sql,
        )
        self.assertNotIn("only a staging generation can fail", sql)
        self.assertNotIn(
            "raw_manifest_sha256 = receipt_sha",
            sql,
        )
        self.assertNotIn(
            "raw_manifest_object_key = receipt_key",
            sql,
        )

    def test_ready_requires_exact_terminal_receipt_binding(self):
        sql = MIGRATION_PATH.read_text(encoding="utf-8").lower()
        collector = MODULE_PATH.read_text(encoding="utf-8").lower()
        self.assertIn("add column terminal_receipt_sha256 text", sql)
        self.assertIn("add column terminal_receipt_object_key text", sql)
        self.assertIn("'terminal_receipt'", sql)
        self.assertIn(
            "create or replace function public.fs_commit_broward_parcel_generation_receipt",
            sql,
        )
        self.assertIn("status = 'validated'", sql)
        self.assertIn(
            "only a validated parcel generation can bind its terminal receipt",
            sql,
        )
        self.assertIn("p_terminal_receipt_body", sql)
        self.assertIn("pg_catalog.octet_length", sql)
        self.assertIn("extensions.digest", sql)
        self.assertIn("fs_commit_broward_parcel_generation_receipt", collector)
        self.assertIn("write_terminal_receipt", collector)

    def test_migration_owns_reviewed_sale_date_contract(self):
        sql = MIGRATION_PATH.read_text(encoding="utf-8")
        self.assertIn(MODULE.PRODUCTION_QUALITY_CONTRACT_SHA256, sql)
        self.assertIn(MODULE.CANARY_QUALITY_CONTRACT_SHA256, sql)
        self.assertIn("esriFieldTypeDate_epoch_milliseconds_utc", sql)
        self.assertIn("field_null_with_reason_and_raw_attribute_v1", sql)
        self.assertIn("sale_date_1_null_reason text", sql)
        self.assertIn("field_null_manifest", sql)
        self.assertIn("where item->>'purpose' = 'field_null_manifest'", sql)
        self.assertIn("parcel SALE_DATE_1 field-null classification is inconsistent", sql)
        self.assertIn("'sale_date_1_field_null_rows'", sql)

    def test_finalizer_replay_requires_exact_persisted_range_manifests(self):
        sql = MIGRATION_PATH.read_text(encoding="utf-8").lower()
        self.assertIn("fs_broward_parcel_range_manifests_match", sql)
        self.assertIn("select * from supplied except all select * from stored", sql)
        self.assertIn("select * from stored except all select * from supplied", sql)
        self.assertIn("and replay_range_manifests_match then", sql)
        self.assertIn("invalid parcel range manifest payload", sql)
        self.assertIn(
            "revoke all on function public.fs_broward_parcel_range_manifests_match",
            sql,
        )

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
