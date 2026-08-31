import contextlib
import datetime as dt
import hashlib
import importlib.util
import io
import json
import shutil
import socket
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "droplet" / "sfwmd_pending_erp_shadow.py"
FIXTURES = ROOT / "tests" / "fixtures" / "sfwmd_shadow"
SPEC = importlib.util.spec_from_file_location("sfwmd_pending_erp_shadow", SCRIPT)
sfwmd = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = sfwmd
SPEC.loader.exec_module(sfwmd)


FIXED_CLOCK = dt.datetime(2026, 8, 31, 12, 0, tzinfo=dt.timezone.utc)


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self.body = body

    def read(self, size=-1):
        return self.body if size is None or size < 0 else self.body[:size]

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class SfwmdShadowCollectorTests(unittest.TestCase):
    def run_fixture(self, output_root, fixture_dir=FIXTURES, **kwargs):
        transport = sfwmd.FixtureTransport(Path(fixture_dir))
        run_dir, receipt = sfwmd.run_collection(
            output_root=Path(output_root),
            transport=transport,
            page_size=2,
            run_id=kwargs.pop("run_id", "sfwmd-shadow-test"),
            clock=lambda: FIXED_CLOCK,
            **kwargs,
        )
        return transport, run_dir, receipt

    def test_offline_replay_is_exactly_scoped_and_receipted(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport, run_dir, receipt = self.run_fixture(tmp)

            self.assertEqual(receipt["status"], "ok")
            self.assertEqual(receipt["mode"], "shadow_file_only")
            self.assertTrue(receipt["dry_run"])
            self.assertEqual(receipt["counts"]["rows_observed"], 3)
            self.assertEqual(receipt["counts"]["rows_shadow_included"], 1)
            self.assertEqual(receipt["counts"]["rows_outside_boundary"], 1)
            self.assertEqual(receipt["counts"]["rows_test_excluded"], 1)
            self.assertEqual(receipt["counts"]["rows_rejected"], 0)
            self.assertEqual(
                receipt["app_status_counts_observed"],
                {
                    "Additional Information Required": 1,
                    "Application Complete": 1,
                    "Pending Review": 1,
                },
            )
            self.assertEqual(receipt["app_status_counts_in_scope"], {"Pending Review": 1})
            self.assertIn("no_allowlist", receipt["app_status_policy"])
            self.assertTrue(receipt["quality"]["accounting_identity_passed"])
            self.assertTrue(receipt["quality"]["source_count_parity_passed"])
            self.assertFalse(receipt["safety"]["promotion_eligible"])
            self.assertFalse(receipt["safety"]["connected_label_allowed"])
            self.assertFalse(receipt["safety"]["database_writes"])
            self.assertFalse(receipt["safety"]["supabase_writes"])
            self.assertEqual(run_dir.stat().st_mode & 0o777, 0o700)
            self.assertEqual((run_dir / "receipt.json").stat().st_mode & 0o777, 0o600)

            rows = [
                json.loads(line)
                for line in (run_dir / "shadow-records.jsonl").read_text().splitlines()
            ]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["identity"]["app_no"], "ERP-2026-0001")
            self.assertEqual(
                rows[0]["identity"]["global_id"],
                "11111111-1111-4111-8111-111111111111",
            )
            self.assertEqual(rows[0]["source"]["app_status"], "Pending Review")
            self.assertEqual(rows[0]["attributes"]["City"], "MIAMI")
            self.assertFalse(rows[0]["scope"]["mailing_city_used_for_scope"])
            self.assertIsNone(rows[0]["clocks"]["source_modified_at"])
            self.assertEqual(
                rows[0]["clocks"]["source_modified_status"],
                "UNKNOWN_NOT_EXPOSED",
            )
            self.assertIsNotNone(rows[0]["event_clocks"]["app_received_at"])
            self.assertIsNone(rows[0]["event_clocks"]["issue_at"])

            self.assertEqual(
                [call[0] for call in transport.calls],
                [
                    "boundary-layer-metadata",
                    "boundary-fort-lauderdale",
                    "layer-metadata",
                    "object-ids-start",
                    "page-0001",
                    "page-0002",
                    "object-ids-end",
                ],
            )

    def test_pagination_freezes_sorted_object_ids_and_reconciles_end_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport, _, receipt = self.run_fixture(tmp)
        pages = [call for call in transport.calls if call[0].startswith("page-")]
        self.assertEqual(pages[0][2]["where"], "OBJECTID >= 1 AND OBJECTID <= 2")
        self.assertEqual(pages[1][2]["where"], "OBJECTID = 3")
        self.assertNotIn("objectIds", pages[0][2])
        self.assertEqual(pages[0][2]["orderByFields"], "OBJECTID ASC")
        self.assertEqual(pages[0][2]["resultRecordCount"], "2")
        self.assertEqual(pages[1][2]["resultRecordCount"], "1")
        self.assertEqual(pages[0][2]["outSR"], "4326")
        self.assertTrue(receipt["pagination"]["object_ids_stable"])
        self.assertEqual(
            receipt["pagination"]["method"],
            "frozen_OBJECTID_set_range_pages_in_ASC_order",
        )

    def test_boundary_is_queried_from_exact_official_city_layer_and_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport, _, receipt = self.run_fixture(tmp)
        boundary_call = next(
            call for call in transport.calls if call[0] == "boundary-fort-lauderdale"
        )
        self.assertEqual(boundary_call[1], sfwmd.BOUNDARY_QUERY_URL)
        self.assertEqual(
            boundary_call[2]["where"],
            "NAME = 'Fort Lauderdale' AND TYPE = 'City'",
        )
        self.assertEqual(boundary_call[2]["outSR"], "4326")
        self.assertEqual(receipt["scope"]["boundary_layer_id"], 44)
        self.assertEqual(
            receipt["scope"]["boundary_layer_name"],
            "Fort Lauderdale Municipal Boundary - Administrative Area",
        )
        self.assertEqual(receipt["scope"]["boundary_record"]["name"], "Fort Lauderdale")
        self.assertEqual(receipt["scope"]["boundary_record"]["record_count"], 1)

    def test_raw_manifest_hashes_every_attempt_and_matches_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, run_dir, receipt = self.run_fixture(tmp)
            manifest_bytes = (run_dir / "raw-manifest.json").read_bytes()
            manifest = json.loads(manifest_bytes)
            self.assertEqual(
                hashlib.sha256(manifest_bytes).hexdigest(),
                receipt["hashes"]["raw_manifest_sha256"],
            )
            self.assertEqual(len(manifest["responses"]), 7)
            for response in manifest["responses"]:
                self.assertRegex(response["observed_at"], r"Z$")
                raw = (run_dir / response["object_path"]).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), response["sha256"])
                self.assertEqual(len(raw), response["bytes"])
                self.assertFalse(response["truncated"])

    def test_oversize_raw_manifest_marks_bounded_prefix_as_truncated(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = sfwmd.EvidenceBundle(Path(tmp), "oversize-evidence")
            bundle.capture(
                "layer-metadata",
                sfwmd.LAYER_URL,
                {"f": "json"},
                [sfwmd.FetchAttempt(200, b"bounded", "ResponseTooLarge", 1)],
            )
            path, _ = bundle.finalize_raw_manifest()
            response = json.loads(path.read_text())["responses"][0]
            self.assertTrue(response["truncated"])
            self.assertEqual(response["bytes"], 7)
            self.assertEqual(
                (bundle.raw_dir / "layer-metadata.attempt-01.json").read_bytes(),
                b"bounded",
            )

    def test_source_content_index_is_stable_across_observation_clocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            first_dir, first = sfwmd.run_collection(
                output_root=Path(tmp),
                transport=sfwmd.FixtureTransport(FIXTURES),
                page_size=2,
                run_id="first-clock",
                clock=lambda: FIXED_CLOCK,
            )
            later = FIXED_CLOCK + dt.timedelta(days=1)
            second_dir, second = sfwmd.run_collection(
                output_root=Path(tmp),
                transport=sfwmd.FixtureTransport(FIXTURES),
                page_size=2,
                run_id="second-clock",
                clock=lambda: later,
            )

            self.assertEqual(
                first["hashes"]["source_content_index_sha256"],
                second["hashes"]["source_content_index_sha256"],
            )
            self.assertNotEqual(
                first["hashes"]["shadow_records_sha256"],
                second["hashes"]["shadow_records_sha256"],
            )
            self.assertEqual(
                (first_dir / "shadow-content-index.jsonl").read_text(),
                (second_dir / "shadow-content-index.jsonl").read_text(),
            )

    def test_boundary_name_drift_fails_closed_with_receipt(self):
        with tempfile.TemporaryDirectory() as fixture_tmp, tempfile.TemporaryDirectory() as out:
            fixture_copy = Path(fixture_tmp) / "fixtures"
            shutil.copytree(FIXTURES, fixture_copy)
            path = fixture_copy / "boundary-fort-lauderdale.json"
            payload = json.loads(path.read_text())
            payload["features"][0]["properties"]["NAME"] = "Not Fort Lauderdale"
            path.write_text(json.dumps(payload))

            _, run_dir, receipt = self.run_fixture(out, fixture_copy)

            self.assertEqual(receipt["status"], "failed")
            self.assertEqual(receipt["reason_code"], "COLLECTOR_OR_CONTRACT_FAILURE")
            self.assertIn("BoundaryContractError", receipt["terminal_error"])
            self.assertFalse(receipt["quality"]["schema_contract_passed"])
            self.assertTrue((run_dir / "receipt.json").is_file())

    def test_boundary_accepts_multiple_exact_unique_official_components(self):
        payload = json.loads((FIXTURES / "boundary-fort-lauderdale.json").read_text())
        second = json.loads(json.dumps(payload["features"][0]))
        second["properties"]["OBJECTID"] = 45
        second["properties"]["GlobalID"] = "{bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb}"
        second["geometry"]["coordinates"] = [
            [[20, 20], [21, 20], [21, 21], [20, 21], [20, 20]]
        ]
        payload["features"].append(second)

        components, record = sfwmd.validate_boundary_feature(payload)

        self.assertEqual(record["record_count"], 2)
        self.assertEqual(record["object_ids"], [44, 45])
        self.assertEqual(len(components), 2)
        duplicate = json.loads(json.dumps(payload))
        duplicate["features"][1]["properties"]["OBJECTID"] = 44
        with self.assertRaises(sfwmd.BoundaryContractError):
            sfwmd.validate_boundary_feature(duplicate)

    def test_boundary_crs_must_be_exact_epsg_4326(self):
        payload = json.loads((FIXTURES / "boundary-fort-lauderdale.json").read_text())
        sfwmd.validate_boundary_feature(payload)
        payload["crs"]["properties"]["name"] = "EPSG:2881"
        with self.assertRaises(sfwmd.BoundaryContractError):
            sfwmd.validate_boundary_feature(payload)

    def test_boundary_metadata_accepts_only_one_unambiguous_objectid_oid(self):
        metadata = json.loads((FIXTURES / "boundary-layer-metadata.json").read_text())
        metadata.pop("objectIdField", None)
        metadata.pop("objectIdFieldName", None)

        projection = sfwmd.validate_boundary_layer_metadata(metadata)

        self.assertEqual(projection["objectIdField"], "OBJECTID")
        metadata["fields"].append(
            {"name": "SECOND_OID", "type": "esriFieldTypeOID", "alias": "SECOND_OID"}
        )
        with self.assertRaises(sfwmd.BoundaryContractError):
            sfwmd.validate_boundary_layer_metadata(metadata)

    def test_sfwmd_schema_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as fixture_tmp, tempfile.TemporaryDirectory() as out:
            fixture_copy = Path(fixture_tmp) / "fixtures"
            shutil.copytree(FIXTURES, fixture_copy)
            path = fixture_copy / "layer-metadata.json"
            payload = json.loads(path.read_text())
            payload["fields"] = [
                field for field in payload["fields"] if field["name"] != "APP_NO"
            ]
            path.write_text(json.dumps(payload))

            _, _, receipt = self.run_fixture(out, fixture_copy)

            self.assertEqual(receipt["status"], "failed")
            self.assertIn("field contract drifted", receipt["terminal_error"])

    def test_sfwmd_metadata_accepts_only_one_unambiguous_objectid_oid(self):
        metadata = json.loads((FIXTURES / "layer-metadata.json").read_text())
        metadata.pop("objectIdField", None)
        metadata.pop("objectIdFieldName", None)

        projection = sfwmd.validate_layer_metadata(metadata)

        self.assertEqual(projection["objectIdField"], "OBJECTID")
        metadata["fields"].append(
            {"name": "SECOND_OID", "type": "esriFieldTypeOID"}
        )
        with self.assertRaises(sfwmd.SourceContractError):
            sfwmd.validate_layer_metadata(metadata)

    def test_sfwmd_time_reference_requires_windows_and_iana_contracts(self):
        metadata = json.loads((FIXTURES / "layer-metadata.json").read_text())
        sfwmd.validate_layer_metadata(metadata)
        metadata["preferredTimeReference"]["timeZoneIANA"] = "America/Chicago"
        with self.assertRaises(sfwmd.SourceContractError):
            sfwmd.validate_layer_metadata(metadata)

    def test_object_id_set_change_is_truthful_partial_not_green(self):
        with tempfile.TemporaryDirectory() as fixture_tmp, tempfile.TemporaryDirectory() as out:
            fixture_copy = Path(fixture_tmp) / "fixtures"
            shutil.copytree(FIXTURES, fixture_copy)
            path = fixture_copy / "object-ids-end.json"
            payload = json.loads(path.read_text())
            payload["objectIds"].append(4)
            path.write_text(json.dumps(payload))

            _, _, receipt = self.run_fixture(out, fixture_copy)

            self.assertEqual(receipt["status"], "partial")
            self.assertEqual(
                receipt["reason_code"], "SOURCE_OBJECT_ID_SET_CHANGED_DURING_RUN"
            )
            self.assertFalse(receipt["quality"]["source_object_id_set_stable"])

    def test_stable_authoritative_empty_run_has_an_empty_receipt(self):
        with tempfile.TemporaryDirectory() as fixture_tmp, tempfile.TemporaryDirectory() as out:
            fixture_copy = Path(fixture_tmp) / "fixtures"
            shutil.copytree(FIXTURES, fixture_copy)
            empty_ids = {"objectIdFieldName": "OBJECTID", "objectIds": []}
            for name in ("object-ids-start.json", "object-ids-end.json"):
                (fixture_copy / name).write_text(json.dumps(empty_ids))

            transport = sfwmd.FixtureTransport(fixture_copy)
            _, receipt = sfwmd.run_collection(
                output_root=Path(out),
                transport=transport,
                page_size=2,
                run_id="sfwmd-empty-test",
                clock=lambda: FIXED_CLOCK,
            )

            self.assertEqual(receipt["status"], "empty")
            self.assertEqual(receipt["counts"]["rows_observed"], 0)
            self.assertEqual(receipt["counts"]["pages_expected"], 0)
            self.assertEqual(receipt["counts"]["pages_succeeded"], 0)
            self.assertEqual(
                [call[0] for call in transport.calls],
                [
                    "boundary-layer-metadata",
                    "boundary-fort-lauderdale",
                    "layer-metadata",
                    "object-ids-start",
                    "object-ids-end",
                ],
            )

    def test_unknown_test_flag_is_rejected_and_blocks_green(self):
        with tempfile.TemporaryDirectory() as fixture_tmp, tempfile.TemporaryDirectory() as out:
            fixture_copy = Path(fixture_tmp) / "fixtures"
            shutil.copytree(FIXTURES, fixture_copy)
            path = fixture_copy / "page-0002.json"
            payload = json.loads(path.read_text())
            payload["features"][0]["attributes"]["IsTestData"] = "maybe"
            path.write_text(json.dumps(payload))

            _, _, receipt = self.run_fixture(out, fixture_copy)

            self.assertEqual(receipt["status"], "partial")
            self.assertEqual(receipt["counts"]["rows_rejected"], 1)
            self.assertEqual(receipt["counts"]["rows_test_excluded"], 0)
            self.assertEqual(
                receipt["rejection_reasons"]["IsTestData contains an unknown value"], 1
            )

    def test_network_transport_retries_only_bounded_official_request(self):
        responses = [FakeResponse(503, b'{"error":"busy"}'), FakeResponse(200, b'{"ok":true}')]
        opener = mock.Mock(side_effect=responses)
        sleeper = mock.Mock()
        transport = sfwmd.NetworkTransport(
            timeout_seconds=5,
            retries=2,
            opener=opener,
            sleeper=sleeper,
        )

        result = transport.fetch("metadata", sfwmd.LAYER_URL, {"f": "json"})

        self.assertEqual(len(result.attempts), 2)
        self.assertEqual([attempt.status for attempt in result.attempts], [503, 200])
        sleeper.assert_called_once()
        self.assertEqual(opener.call_count, 2)

    def test_network_transport_records_bounded_timeout_failures(self):
        transport = sfwmd.NetworkTransport(
            timeout_seconds=5,
            retries=2,
            opener=mock.Mock(side_effect=socket.timeout()),
            sleeper=mock.Mock(),
        )
        with self.assertRaises(sfwmd.FetchError) as caught:
            transport.fetch("metadata", sfwmd.LAYER_URL, {"f": "json"})
        self.assertEqual(len(caught.exception.attempts), 3)
        self.assertTrue(
            all(
                attempt.error_class in {"TimeoutError", "timeout"}
                for attempt in caught.exception.attempts
            )
        )

    def test_network_transport_fails_closed_at_response_byte_ceiling(self):
        transport = sfwmd.NetworkTransport(
            timeout_seconds=5,
            retries=0,
            max_response_bytes=10,
            opener=mock.Mock(return_value=FakeResponse(200, b"01234567890")),
        )
        with self.assertRaises(sfwmd.FetchError) as caught:
            transport.fetch("metadata", sfwmd.LAYER_URL, {"f": "json"})
        self.assertEqual(len(caught.exception.attempts), 1)
        self.assertEqual(caught.exception.attempts[0].error_class, "ResponseTooLarge")
        self.assertEqual(len(caught.exception.attempts[0].body), 10)

    def test_network_transport_rejects_any_unpinned_url(self):
        transport = sfwmd.NetworkTransport(timeout_seconds=5, retries=0)
        with self.assertRaises(sfwmd.FetchError):
            transport.fetch("bad", "https://example.com/query", {"f": "json"})

    def test_network_transport_fails_closed_on_redirect(self):
        redirect = urllib.error.HTTPError(
            sfwmd.LAYER_URL,
            302,
            "redirect",
            {"Location": "https://example.com/not-allowed"},
            io.BytesIO(b"redirect refused"),
        )
        transport = sfwmd.NetworkTransport(
            timeout_seconds=5,
            retries=3,
            opener=mock.Mock(side_effect=redirect),
            sleeper=mock.Mock(),
        )
        with self.assertRaises(sfwmd.FetchError) as caught:
            transport.fetch("metadata", sfwmd.LAYER_URL, {"f": "json"})
        self.assertEqual(len(caught.exception.attempts), 1)
        self.assertEqual(caught.exception.attempts[0].status, 302)

    def test_output_root_must_be_absolute_and_run_is_create_only(self):
        transport = sfwmd.FixtureTransport(FIXTURES)
        with self.assertRaises(sfwmd.CollectorError):
            sfwmd.run_collection(
                output_root=Path("relative"),
                transport=transport,
                page_size=2,
                run_id="test-run",
                clock=lambda: FIXED_CLOCK,
            )
        with tempfile.TemporaryDirectory() as tmp:
            self.run_fixture(tmp, run_id="same-run")
            with self.assertRaises(FileExistsError):
                self.run_fixture(tmp, run_id="same-run")

    def test_cli_requires_explicit_transport_and_output_path(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                sfwmd.build_parser().parse_args(["--output-dir", "/tmp/shadow"])
        with contextlib.redirect_stderr(io.StringIO()):
            rc = sfwmd.main(
                [
                    "--output-dir",
                    "relative",
                    "--fixture-dir",
                    str(FIXTURES),
                ]
            )
        self.assertEqual(rc, 64)
        with contextlib.redirect_stderr(io.StringIO()):
            rc = sfwmd.main(
                [
                    "--output-dir",
                    "/tmp/shadow",
                    "--allow-network",
                    "--max-response-bytes",
                    "0",
                ]
            )
        self.assertEqual(rc, 64)

    def test_cli_offline_fixture_success_reports_shadow_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = sfwmd.main(
                    [
                        "--output-dir",
                        tmp,
                        "--fixture-dir",
                        str(FIXTURES),
                        "--page-size",
                        "2",
                        "--run-id",
                        "sfwmd-cli-fixture",
                    ]
                )
            result = json.loads(stdout.getvalue())
            self.assertEqual(rc, 0)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["mode"], "shadow_file_only")
            self.assertTrue(result["dry_run"])
            self.assertFalse(result["promotion_eligible"])
            self.assertTrue((Path(result["run_dir"]) / "receipt.json").is_file())

    def test_polygon_intersection_handles_containment_and_touching(self):
        boundary = [[(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]]
        containing = [[(-1, -1), (11, -1), (11, 11), (-1, 11), (-1, -1)]]
        touching = [[(10, 5), (11, 5), (11, 6), (10, 6), (10, 5)]]
        outside = [[(20, 20), (21, 20), (21, 21), (20, 21), (20, 20)]]
        self.assertTrue(sfwmd.polygon_intersects(containing, boundary))
        self.assertTrue(sfwmd.polygon_intersects(touching, boundary))
        self.assertFalse(sfwmd.polygon_intersects(outside, boundary))

    def test_overlapping_boundary_components_use_union_not_flattened_xor(self):
        first = [[(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]]
        second = [[(5, 0), (15, 0), (15, 10), (5, 10), (5, 0)]]
        source_inside_overlap = [[(6, 2), (7, 2), (7, 3), (6, 3), (6, 2)]]
        self.assertFalse(
            sfwmd.polygon_intersects(source_inside_overlap, first + second)
        )
        self.assertTrue(
            sfwmd.polygon_intersects_boundary_components(
                source_inside_overlap,
                [first, second],
            )
        )

    def test_page_field_and_attribute_contracts_fail_closed(self):
        page = json.loads((FIXTURES / "page-0001.json").read_text())
        ids = [feature["attributes"]["OBJECTID"] for feature in page["features"]]
        sfwmd.validate_page(page, ids)

        missing_field = json.loads(json.dumps(page))
        missing_field["fields"] = missing_field["fields"][:-1]
        with self.assertRaises(sfwmd.SourceContractError):
            sfwmd.validate_page(missing_field, ids)

        missing_attribute = json.loads(json.dumps(page))
        missing_attribute["features"][0]["attributes"].pop("ApplicantName")
        with self.assertRaises(sfwmd.SourceContractError):
            sfwmd.validate_page(missing_attribute, ids)


if __name__ == "__main__":
    unittest.main()
