import datetime as dt
import importlib.util
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "droplet" / "sfwmd_pending_erp_production.py"
SCHEMA = ROOT / "ops" / "droplet" / "sfwmd_pending_erp_schema.sql"
FIXTURES = ROOT / "tests" / "fixtures" / "sfwmd_shadow"
SPEC = importlib.util.spec_from_file_location("sfwmd_pending_erp_production", SCRIPT)
production = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(production)

FIXED_CLOCK = dt.datetime(2026, 8, 31, 10, 20, tzinfo=dt.timezone.utc)


class FakeMirror:
    def __init__(self):
        self.payloads = []

    def commit(self, payload):
        self.payloads.append(payload)
        return {
            "run_id": payload["run_id"],
            "payload_sha256": payload["receipt"]["mirror"]["database_payload_sha256"],
            "status": payload["receipt"]["status"],
            "idempotent_replay": False,
        }


class SfwmdProductionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.sqlite_path = self.root / "canonical.sqlite"
        self.sqlite_path.touch()
        self.writer_lock = self.root / "writer.lock"
        self.evidence = self.root / "evidence"
        self.receipts = self.root / "receipts"
        self.latest = self.receipts / "latest.json"
        self.failures = self.root / "failures"
        self.canaries = self.root / "canaries"
        production.install_schema(
            sqlite_path=self.sqlite_path,
            writer_lock_path=self.writer_lock,
            clock=lambda: FIXED_CLOCK,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def collect(self, *, fixture_dir=FIXTURES, clock=FIXED_CLOCK):
        return production.shadow.run_collection(
            output_root=self.evidence,
            transport=production.shadow.FixtureTransport(Path(fixture_dir)),
            page_size=2,
            run_id=str(uuid.uuid4()),
            clock=lambda: clock,
        )[0]

    def timer_runtime_context(self, *, clock=FIXED_CLOCK):
        cgroup_evidence = (
            f"0::/system.slice/{production.TIMER_SERVICE_UNIT}\n"
        )
        return {
            "trigger_unit": production.TIMER_UNIT,
            "trigger_timer_realtime_usec": str(int(clock.timestamp() * 1_000_000)),
            "runtime_service_unit": production.TIMER_SERVICE_UNIT,
            "runtime_cgroup_sha256": production.sha256_bytes(
                cgroup_evidence.encode("utf-8")
            ),
            "runtime_cgroup_evidence": cgroup_evidence,
        }

    def timer_provenance(self, run_dir, *, clock=FIXED_CLOCK):
        run_id = json.loads((run_dir / "receipt.json").read_text(encoding="utf-8"))["run_id"]
        return production.create_timer_provenance(
            canary_dir=self.canaries,
            run_id=run_id,
            systemd_invocation_id="a" * 32,
            runtime_context=self.timer_runtime_context(clock=clock),
            clock=lambda: clock,
        )

    def commit(self, run_dir, *, natural=True, clock=FIXED_CLOCK):
        return production.commit_bundle(
            sqlite_path=self.sqlite_path,
            writer_lock_path=self.writer_lock,
            run_dir=run_dir,
            receipt_dir=self.receipts,
            latest_pointer=self.latest,
            provenance=(
                self.timer_provenance(run_dir, clock=clock)
                if natural else production.manual_provenance("direct")
            ),
            clock=lambda: clock,
        )

    def table_count(self, table):
        with sqlite3.connect(self.sqlite_path) as connection:
            return connection.execute(f"select count(*) from {table}").fetchone()[0]

    def test_atomic_commit_versions_receipt_and_outbox_then_replays_exactly(self):
        run_dir = self.collect()
        receipt = self.commit(run_dir)

        self.assertEqual(receipt["status"], "ok")
        self.assertEqual(receipt["progress_status"], "changed")
        self.assertEqual(receipt["counts"]["rows_inserted"], 1)
        self.assertEqual(receipt["connection_state"], "not_connected")
        self.assertTrue(receipt["natural_run"])
        self.assertEqual(self.table_count("sfwmd_pending_erp_runs"), 1)
        self.assertEqual(self.table_count("sfwmd_pending_erp_records"), 1)
        self.assertEqual(self.table_count("sfwmd_pending_erp_versions"), 1)
        self.assertEqual(self.table_count("sfwmd_pending_erp_mirror_outbox"), 1)
        self.assertTrue(self.latest.exists())
        with sqlite3.connect(self.sqlite_path) as connection:
            run_counts = connection.execute(
                "select rows_accepted,rows_inserted,rows_updated,rows_unchanged,rows_retired "
                "from sfwmd_pending_erp_runs"
            ).fetchone()
        self.assertEqual(run_counts, (1, 1, 0, 0, 0))
        persisted = Path(receipt["receipt_path"])
        self.assertEqual(persisted.stat().st_mode & 0o777, 0o600)
        self.assertEqual(run_dir.stat().st_mode & 0o777, 0o500)
        self.assertEqual((run_dir / "raw").stat().st_mode & 0o777, 0o500)
        self.assertTrue(all((path.stat().st_mode & 0o777) == 0o400 for path in run_dir.glob("*.json*")))
        self.assertTrue(all((path.stat().st_mode & 0o777) == 0o400 for path in (run_dir / "raw").iterdir()))

        replay = self.commit(run_dir)
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(self.table_count("sfwmd_pending_erp_runs"), 1)
        self.assertEqual(self.table_count("sfwmd_pending_erp_versions"), 1)

    def test_same_content_is_truthfully_unchanged_without_new_version(self):
        self.commit(self.collect())
        second_clock = FIXED_CLOCK + dt.timedelta(days=1)
        second = self.commit(self.collect(clock=second_clock), clock=second_clock)
        self.assertEqual(second["progress_status"], "unchanged")
        self.assertEqual(second["counts"]["rows_unchanged"], 1)
        self.assertEqual(second["counts"]["rows_inserted"], 0)
        self.assertEqual(self.table_count("sfwmd_pending_erp_runs"), 2)
        self.assertEqual(self.table_count("sfwmd_pending_erp_versions"), 1)

    def test_changed_source_content_creates_one_new_immutable_version(self):
        self.commit(self.collect())
        fixture_copy = self.root / "changed-fixtures"
        shutil.copytree(FIXTURES, fixture_copy)
        page = fixture_copy / "page-0001.json"
        payload = json.loads(page.read_text(encoding="utf-8"))
        payload["features"][0]["attributes"]["PROJECT_NAME"] = "Changed official value"
        page.write_text(json.dumps(payload), encoding="utf-8")
        later = FIXED_CLOCK + dt.timedelta(days=1)
        changed = self.commit(self.collect(fixture_dir=fixture_copy, clock=later), clock=later)
        self.assertEqual(changed["counts"]["rows_updated"], 1)
        self.assertEqual(self.table_count("sfwmd_pending_erp_versions"), 2)

    def test_complete_empty_scope_retires_without_rewriting_last_seen(self):
        first = self.commit(self.collect())
        fixture_copy = self.root / "empty-scope-fixtures"
        shutil.copytree(FIXTURES, fixture_copy)
        page = fixture_copy / "page-0001.json"
        payload = json.loads(page.read_text(encoding="utf-8"))
        payload["features"][0]["geometry"] = payload["features"][1]["geometry"]
        page.write_text(json.dumps(payload), encoding="utf-8")
        later = FIXED_CLOCK + dt.timedelta(days=1)
        retired = self.commit(self.collect(fixture_dir=fixture_copy, clock=later), clock=later)
        self.assertEqual(retired["status"], "ok")
        self.assertEqual(retired["progress_status"], "changed")
        self.assertEqual(retired["counts"]["rows_retired"], 1)
        with sqlite3.connect(self.sqlite_path) as connection:
            row = connection.execute(
                "select is_current,last_seen_at,retired_at from sfwmd_pending_erp_records"
            ).fetchone()
        self.assertEqual(row, (0, first["observed_at"], retired["observed_at"]))

    def test_partial_observation_gets_receipt_but_never_mutates_current_rows(self):
        first = self.commit(self.collect())
        fixture_copy = self.root / "partial-fixtures"
        shutil.copytree(FIXTURES, fixture_copy)
        end_ids = fixture_copy / "object-ids-end.json"
        payload = json.loads(end_ids.read_text(encoding="utf-8"))
        payload["objectIds"] = payload["objectIds"][:-1]
        end_ids.write_text(json.dumps(payload), encoding="utf-8")

        later = FIXED_CLOCK + dt.timedelta(days=1)
        partial = self.commit(self.collect(fixture_dir=fixture_copy, clock=later), clock=later)
        self.assertEqual(partial["status"], "partial")
        self.assertEqual(partial["progress_status"], "uncommitted")
        self.assertEqual(partial["counts"]["rows_accepted"], 0)
        self.assertEqual(self.table_count("sfwmd_pending_erp_records"), 1)
        self.assertEqual(self.table_count("sfwmd_pending_erp_versions"), 1)
        self.assertEqual(self.table_count("sfwmd_pending_erp_runs"), 2)
        self.assertEqual(first["counts"]["rows_inserted"], 1)

    def test_tampered_raw_evidence_fails_before_any_database_write(self):
        run_dir = self.collect()
        raw_file = next((run_dir / "raw").iterdir())
        raw_file.chmod(0o600)
        raw_file.write_bytes(raw_file.read_bytes() + b"tampered")
        with self.assertRaisesRegex(production.ProductionError, "raw evidence"):
            self.commit(run_dir)
        self.assertEqual(self.table_count("sfwmd_pending_erp_runs"), 0)

    def test_coherently_rehashed_nested_row_tamper_fails_before_sqlite(self):
        run_dir = self.collect()
        records_path = run_dir / "shadow-records.jsonl"
        rows = [
            json.loads(line)
            for line in records_path.read_text(encoding="utf-8").splitlines()
        ]
        rows[0]["scope"]["jurisdiction"] = "UNAUTHORIZED-COHERENT-TAMPER"
        rows[0]["uncontracted_extra"] = {"accepted": True}
        records_path.write_bytes(b"".join(production.canonical_bytes(row) for row in rows))

        receipt_path = run_dir / "receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["hashes"]["shadow_records_sha256"] = production.sha256_file(records_path)
        receipt_path.write_bytes(production.canonical_bytes(receipt))

        manifest_path = run_dir / "bundle-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["shadow_records_sha256"] = production.sha256_file(records_path)
        manifest["receipt_sha256"] = production.sha256_file(receipt_path)
        manifest_path.write_bytes(production.canonical_bytes(manifest))

        with self.assertRaisesRegex(
            production.ProductionError, "deterministically replay"
        ):
            self.commit(run_dir)
        self.assertEqual(self.table_count("sfwmd_pending_erp_runs"), 0)
        self.assertEqual(self.table_count("sfwmd_pending_erp_records"), 0)

    def test_coherently_rehashed_raw_source_tamper_fails_before_sqlite(self):
        run_dir = self.collect()
        page_path = run_dir / "raw" / "page-0001.attempt-01.json"
        page = json.loads(page_path.read_text(encoding="utf-8"))
        page["features"][0]["attributes"]["PROJECT_NAME"] = "FORGED SOURCE VALUE"
        page_path.write_bytes(production.canonical_bytes(page))

        raw_manifest_path = run_dir / "raw-manifest.json"
        raw_manifest = json.loads(raw_manifest_path.read_text(encoding="utf-8"))
        page_entry = next(
            entry for entry in raw_manifest["responses"]
            if entry["logical_name"] == "page-0001"
        )
        page_entry["bytes"] = page_path.stat().st_size
        page_entry["sha256"] = production.sha256_file(page_path)
        raw_manifest_path.write_bytes(production.canonical_bytes(raw_manifest))

        receipt_path = run_dir / "receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["hashes"]["raw_manifest_sha256"] = production.sha256_file(
            raw_manifest_path
        )
        receipt_path.write_bytes(production.canonical_bytes(receipt))

        manifest_path = run_dir / "bundle-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["raw_manifest_sha256"] = production.sha256_file(raw_manifest_path)
        manifest["receipt_sha256"] = production.sha256_file(receipt_path)
        manifest_path.write_bytes(production.canonical_bytes(manifest))

        with self.assertRaisesRegex(
            production.ProductionError, "deterministically replay"
        ):
            self.commit(run_dir)
        self.assertEqual(self.table_count("sfwmd_pending_erp_runs"), 0)
        self.assertEqual(self.table_count("sfwmd_pending_erp_records"), 0)

    def test_coherently_rehashed_collection_version_drift_fails_before_sqlite(self):
        run_dir = self.collect()
        receipt_path = run_dir / "receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["versions"]["collector"] = "unreviewed-collector/9.9.9"
        receipt_path.write_bytes(production.canonical_bytes(receipt))

        manifest_path = run_dir / "bundle-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["receipt_sha256"] = production.sha256_file(receipt_path)
        manifest_path.write_bytes(production.canonical_bytes(manifest))

        with self.assertRaisesRegex(production.ProductionError, "version contract"):
            self.commit(run_dir)
        self.assertEqual(self.table_count("sfwmd_pending_erp_runs"), 0)
        self.assertFalse(self.latest.exists())

    def test_coherently_rebound_noncanonical_receipt_bytes_fail_before_sqlite(self):
        run_dir = self.collect()
        receipt_path = run_dir / "receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

        manifest_path = run_dir / "bundle-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["receipt_sha256"] = production.sha256_file(receipt_path)
        manifest_path.write_bytes(production.canonical_bytes(manifest))

        with self.assertRaisesRegex(production.ProductionError, "bytes are not canonical"):
            self.commit(run_dir)
        self.assertEqual(self.table_count("sfwmd_pending_erp_runs"), 0)

    def test_coherently_rehashed_timer_canary_still_requires_exact_types_and_slot(self):
        def seconds_only(provenance, canary):
            provenance["scheduled_for"] = "2026-08-31T10:17:00Z"
            canary["scheduled_for"] = provenance["scheduled_for"]

        def offset_clock(provenance, canary):
            provenance["scheduled_for"] = "2026-08-31T06:17:00.000000-04:00"
            canary["scheduled_for"] = provenance["scheduled_for"]

        def wrong_slot(provenance, canary):
            provenance["scheduled_for"] = "2026-08-31T10:18:00.000000Z"
            canary["scheduled_for"] = provenance["scheduled_for"]

        def numeric_trigger(provenance, canary):
            trigger = int(provenance["trigger_timer_realtime_usec"])
            provenance["trigger_timer_realtime_usec"] = trigger
            canary["trigger_timer_realtime_usec"] = trigger

        for label, mutate in (
            ("seconds_only", seconds_only),
            ("offset_clock", offset_clock),
            ("wrong_slot", wrong_slot),
            ("numeric_trigger", numeric_trigger),
        ):
            with self.subTest(label=label):
                run_dir = self.collect()
                provenance = self.timer_provenance(run_dir)
                canary_path = Path(provenance["canary_path"])
                canary = json.loads(canary_path.read_text(encoding="utf-8"))
                mutate(provenance, canary)
                os.chmod(canary_path, 0o600)
                canary_path.write_bytes(production.canonical_bytes(canary))
                os.chmod(canary_path, 0o400)
                provenance["canary_sha256"] = production.sha256_file(canary_path)

                with self.assertRaises(production.ProductionError):
                    production.commit_bundle(
                        sqlite_path=self.sqlite_path,
                        writer_lock_path=self.writer_lock,
                        run_dir=run_dir,
                        receipt_dir=self.receipts,
                        latest_pointer=self.latest,
                        provenance=provenance,
                        clock=lambda: FIXED_CLOCK,
                    )

        self.assertEqual(self.table_count("sfwmd_pending_erp_runs"), 0)
        self.assertEqual(self.table_count("sfwmd_pending_erp_records"), 0)
        self.assertFalse(self.latest.exists())

    def test_default_off_scheduled_command_is_inert(self):
        class NeverTransport:
            def fetch(self, *_args, **_kwargs):
                raise AssertionError("disabled command attempted network access")

        with mock.patch.dict(os.environ, {
            "FLORIDA_SIGNAL_SFWMD_ENABLED": "0",
            "FLORIDA_SIGNAL_SFWMD_MIRROR_ENABLED": "0",
        }):
            result = production.scheduled_run(
                sqlite_path=self.sqlite_path,
                writer_lock_path=self.writer_lock,
                evidence_dir=self.evidence,
                receipt_dir=self.receipts,
                latest_pointer=self.latest,
                failure_ledger_dir=self.failures,
                page_size=2,
                transport=NeverTransport(),
            )
        self.assertEqual(result["status"], "disabled")
        self.assertFalse(self.evidence.exists())
        self.assertEqual(self.table_count("sfwmd_pending_erp_runs"), 0)

    def test_enabled_fixture_timer_run_is_natural_but_still_not_connected(self):
        with mock.patch.dict(os.environ, {
            "FLORIDA_SIGNAL_SFWMD_ENABLED": "1",
            "FLORIDA_SIGNAL_SFWMD_MIRROR_ENABLED": "0",
        }):
            result = production.timer_run(
                sqlite_path=self.sqlite_path,
                writer_lock_path=self.writer_lock,
                evidence_dir=self.evidence,
                receipt_dir=self.receipts,
                latest_pointer=self.latest,
                failure_ledger_dir=self.failures,
                canary_dir=self.canaries,
                systemd_invocation_id="b" * 32,
                runtime_probe=lambda: self.timer_runtime_context(),
                page_size=2,
                clock=lambda: FIXED_CLOCK,
                transport=production.shadow.FixtureTransport(FIXTURES),
            )
        pointer = json.loads(self.latest.read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["connection_state"], "not_connected")
        self.assertTrue(pointer["natural_run"])
        self.assertEqual(pointer["connection_state"], "not_connected")

    def test_direct_timer_command_without_systemd_trigger_is_only_a_canary(self):
        def no_timer_context():
            raise production.ProductionError("no timer activation metadata")

        with mock.patch.dict(os.environ, {
            "FLORIDA_SIGNAL_SFWMD_ENABLED": "1",
            "FLORIDA_SIGNAL_SFWMD_MIRROR_ENABLED": "0",
        }):
            result = production.timer_run(
                sqlite_path=self.sqlite_path,
                writer_lock_path=self.writer_lock,
                evidence_dir=self.evidence,
                receipt_dir=self.receipts,
                latest_pointer=self.latest,
                failure_ledger_dir=self.failures,
                canary_dir=self.canaries,
                systemd_invocation_id="b" * 32,
                runtime_probe=no_timer_context,
                page_size=2,
                clock=lambda: FIXED_CLOCK,
                transport=production.shadow.FixtureTransport(FIXTURES),
            )
        self.assertFalse(result["natural_run"])
        self.assertEqual(result["progress_status"], "canary")
        self.assertFalse(self.latest.exists())
        self.assertEqual(self.table_count("sfwmd_pending_erp_records"), 0)
        self.assertEqual(self.table_count("sfwmd_pending_erp_versions"), 0)
        self.assertEqual(self.table_count("sfwmd_pending_erp_mirror_outbox"), 0)

    def test_mirror_is_one_bounded_idempotent_outbox_delivery(self):
        receipt = self.commit(self.collect(), natural=True)
        mirror = FakeMirror()
        result = production.flush_one_mirror(
            sqlite_path=self.sqlite_path,
            writer_lock_path=self.writer_lock,
            transport=mirror,
            clock=lambda: FIXED_CLOCK,
        )
        self.assertEqual(result, {"status": "sent", "mirrored": 1, "run_id": receipt["run_id"]})
        self.assertEqual(len(mirror.payloads), 1)
        self.assertLessEqual(len(mirror.payloads[0]["rows"]), production.MAX_IN_SCOPE_ROWS)
        self.assertNotIn("raw", json.dumps(mirror.payloads[0]["rows"]))
        empty = production.flush_one_mirror(
            sqlite_path=self.sqlite_path,
            writer_lock_path=self.writer_lock,
            transport=mirror,
        )
        self.assertEqual(empty, {"status": "empty", "mirrored": 0})

    def test_mirror_payload_is_immutable_and_anchored_against_coherent_tampering(self):
        self.commit(self.collect(), natural=True)
        with sqlite3.connect(self.sqlite_path) as connection:
            row = connection.execute(
                "select run_id,payload_json from sfwmd_pending_erp_mirror_outbox"
            ).fetchone()
            payload = json.loads(row[1])
            payload["rows"][0]["record"]["attributes"]["PROJECT_NAME"] = "mutated"
            mirror_row = payload["rows"][0]
            source_basis = {
                "schema_version": "FloridaSignalSfwmdSourceContentV1",
                "attributes": {
                    key: value
                    for key, value in mirror_row["record"]["attributes"].items()
                    if key != "OBJECTID"
                },
                "geometry": mirror_row["record"]["geometry"],
            }
            source_canonical = production.canonical_bytes(source_basis).decode("utf-8")
            source_sha = production.sha256_bytes(source_canonical.encode("utf-8"))
            mirror_row["source_content_canonical"] = source_canonical
            mirror_row["source_content_sha256"] = source_sha
            mirror_row["record"]["source_content_sha256"] = source_sha
            record_canonical = production.canonical_bytes(mirror_row["record"]).decode("utf-8")
            mirror_row["record_canonical"] = record_canonical
            mirror_row["record_sha256"] = production.sha256_bytes(
                record_canonical.encode("utf-8")
            )
            index_sha = production._validate_mirror_rows(payload["rows"])
            ordered_sha = production._ordered_rows_sha256(payload["rows"])
            receipt = payload["receipt"]
            receipt["source_content_index_sha256"] = index_sha
            receipt["mirror"]["ordered_rows_sha256"] = ordered_sha
            payload_sha = production._database_payload_sha256(
                run_id=row[0],
                status=receipt["status"],
                progress_status=receipt["progress_status"],
                observed_at=receipt["observed_at"],
                source_content_index_sha256=index_sha,
                row_count=len(payload["rows"]),
                ordered_rows_sha256=ordered_sha,
            )
            receipt["mirror"]["database_payload_sha256"] = payload_sha
            with self.assertRaisesRegex(sqlite3.DatabaseError, "payloads are immutable"):
                connection.execute(
                    "update sfwmd_pending_erp_mirror_outbox "
                    "set payload_sha256=?,payload_json=? where run_id=?",
                    (payload_sha, production.canonical_bytes(payload).decode("utf-8"), row[0]),
                )
            connection.rollback()
            # Simulate lower-level database corruption, then restore the exact
            # reviewed trigger so schema validation still passes. The flush
            # must independently bind the outbox back to the immutable run row.
            connection.execute("drop trigger sfwmd_pending_erp_outbox_payload_no_update")
            connection.execute(
                "update sfwmd_pending_erp_mirror_outbox "
                "set payload_sha256=?,payload_json=? where run_id=?",
                (payload_sha, production.canonical_bytes(payload).decode("utf-8"), row[0]),
            )
            connection.execute(
                """create trigger sfwmd_pending_erp_outbox_payload_no_update
before update of run_id,payload_sha256,payload_json on sfwmd_pending_erp_mirror_outbox
begin
  select raise(abort, 'SFWMD mirror payloads are immutable');
end"""
            )
        mirror = FakeMirror()
        with self.assertRaisesRegex(production.ProductionError, "immutable run receipt"):
            production.flush_one_mirror(
                sqlite_path=self.sqlite_path,
                writer_lock_path=self.writer_lock,
                transport=mirror,
            )
        self.assertEqual(mirror.payloads, [])

    def test_schema_is_a_required_deployment_prerequisite(self):
        missing = self.root / "missing-schema.sqlite"
        missing.touch()
        with self.assertRaisesRegex(production.ProductionError, "object set"):
            with production._open_database(missing) as connection:
                production.check_schema(connection)

    def test_receipt_repair_only_recreates_an_existing_hash_bound_run(self):
        run_dir = self.collect()
        receipt = self.commit(run_dir, natural=True)
        receipt_path = Path(receipt["receipt_path"])
        displaced = self.root / "displaced-receipt.json"
        receipt_path.rename(displaced)
        self.latest.rename(self.root / "displaced-latest.json")

        repaired = production.repair_receipt_file(
            sqlite_path=self.sqlite_path,
            writer_lock_path=self.writer_lock,
            run_dir=run_dir,
            receipt_dir=self.receipts,
            latest_pointer=self.latest,
        )
        self.assertEqual(repaired["status"], "repaired")
        self.assertEqual(receipt_path.read_bytes(), displaced.read_bytes())
        self.assertTrue(self.latest.is_file())

        uncommitted = self.collect()
        with self.assertRaisesRegex(production.ProductionError, "existing immutable"):
            production.repair_receipt_file(
                sqlite_path=self.sqlite_path,
                writer_lock_path=self.writer_lock,
                run_dir=uncommitted,
                receipt_dir=self.receipts,
                latest_pointer=self.latest,
            )

    def test_direct_and_manual_service_runs_are_canaries_never_latest(self):
        common = {
            "sqlite_path": self.sqlite_path,
            "writer_lock_path": self.writer_lock,
            "evidence_dir": self.evidence,
            "receipt_dir": self.receipts,
            "latest_pointer": self.latest,
            "failure_ledger_dir": self.failures,
            "page_size": 2,
        }
        with mock.patch.dict(os.environ, {
            "FLORIDA_SIGNAL_SFWMD_ENABLED": "1",
            "FLORIDA_SIGNAL_SFWMD_MIRROR_ENABLED": "0",
        }):
            direct = production.scheduled_run(
                **common,
                invocation_kind="direct",
                clock=lambda: FIXED_CLOCK,
                transport=production.shadow.FixtureTransport(FIXTURES),
            )
            manual = production.scheduled_run(
                **common,
                invocation_kind="manual_service",
                clock=lambda: FIXED_CLOCK + dt.timedelta(minutes=1),
                transport=production.shadow.FixtureTransport(FIXTURES),
            )
        self.assertFalse(direct["natural_run"])
        self.assertFalse(manual["natural_run"])
        self.assertEqual(direct["progress_status"], "canary")
        self.assertEqual(manual["progress_status"], "canary")
        self.assertFalse(self.latest.exists())
        self.assertEqual(self.table_count("sfwmd_pending_erp_runs"), 2)
        self.assertEqual(self.table_count("sfwmd_pending_erp_records"), 0)
        self.assertEqual(self.table_count("sfwmd_pending_erp_versions"), 0)
        self.assertEqual(self.table_count("sfwmd_pending_erp_mirror_outbox"), 0)

    def test_bad_timer_invocation_writes_durable_failure_and_never_latest(self):
        with mock.patch.dict(os.environ, {"FLORIDA_SIGNAL_SFWMD_ENABLED": "1"}):
            with self.assertRaisesRegex(production.ProductionError, "INVOCATION_ID"):
                production.timer_run(
                    sqlite_path=self.sqlite_path,
                    writer_lock_path=self.writer_lock,
                    evidence_dir=self.evidence,
                    receipt_dir=self.receipts,
                    latest_pointer=self.latest,
                    failure_ledger_dir=self.failures,
                    canary_dir=self.canaries,
                    systemd_invocation_id="",
                    runtime_probe=lambda: self.timer_runtime_context(),
                    page_size=2,
                    clock=lambda: FIXED_CLOCK,
                    transport=production.shadow.FixtureTransport(FIXTURES),
                )
        pointer = json.loads((self.failures / "latest.json").read_text())
        failure_path = Path(pointer["receipt_path"])
        self.assertEqual(
            production.sha256_file(failure_path), pointer["receipt_sha256"]
        )
        failure = json.loads(failure_path.read_text())
        self.assertEqual(failure["stage"], "timer_provenance")
        self.assertFalse(failure["natural_run"])
        self.assertTrue(failure["alert_required"])
        self.assertFalse(self.latest.exists())

    def test_second_timer_provenance_failure_still_has_correlated_ledger(self):
        original = production.create_timer_provenance

        def create_then_remove(**kwargs):
            provenance = original(**kwargs)
            Path(provenance["canary_path"]).unlink()
            return provenance

        with mock.patch.dict(os.environ, {"FLORIDA_SIGNAL_SFWMD_ENABLED": "1"}), \
                mock.patch.object(
                    production, "create_timer_provenance", side_effect=create_then_remove
                ):
            with self.assertRaisesRegex(production.ProductionError, "canary is missing"):
                production.timer_run(
                    sqlite_path=self.sqlite_path,
                    writer_lock_path=self.writer_lock,
                    evidence_dir=self.evidence,
                    receipt_dir=self.receipts,
                    latest_pointer=self.latest,
                    failure_ledger_dir=self.failures,
                    canary_dir=self.canaries,
                    systemd_invocation_id="b" * 32,
                    runtime_probe=lambda: self.timer_runtime_context(),
                    page_size=2,
                    clock=lambda: FIXED_CLOCK,
                    transport=production.shadow.FixtureTransport(FIXTURES),
                )
        pointer = json.loads(
            (self.failures / f"{production.TIMER_SERVICE_UNIT}.latest.json").read_text()
        )
        failure = json.loads(Path(pointer["receipt_path"]).read_text())
        self.assertEqual(failure["stage"], "collection_initialization")
        self.assertEqual(failure["failed_unit"], production.TIMER_SERVICE_UNIT)
        self.assertFalse(failure["natural_run"])
        self.assertFalse(self.latest.exists())

    def test_precanonical_database_failure_writes_early_failure_ledger(self):
        with mock.patch.dict(os.environ, {"FLORIDA_SIGNAL_SFWMD_ENABLED": "1"}):
            with self.assertRaisesRegex(production.ProductionError, "database is missing"):
                production.scheduled_run(
                    sqlite_path=self.root / "absent.sqlite",
                    writer_lock_path=self.writer_lock,
                    evidence_dir=self.evidence,
                    receipt_dir=self.receipts,
                    latest_pointer=self.latest,
                    failure_ledger_dir=self.failures,
                    invocation_kind="manual_service",
                    page_size=2,
                    clock=lambda: FIXED_CLOCK,
                    transport=production.shadow.FixtureTransport(FIXTURES),
                )
        pointer = json.loads((self.failures / "latest.json").read_text())
        failure = json.loads(Path(pointer["receipt_path"]).read_text())
        self.assertEqual(failure["stage"], "canonical_commit")
        self.assertFalse(failure["canonical_receipt_committed"])
        self.assertTrue(failure["alert_required"])

    def test_postcommit_file_failure_ledger_truthfully_marks_canonical_receipt(self):
        original_write = production.write_create_only_fsynced

        def fail_terminal_file(path, value):
            if path.parent == self.receipts:
                raise OSError("simulated terminal receipt interruption")
            return original_write(path, value)

        with mock.patch.dict(os.environ, {"FLORIDA_SIGNAL_SFWMD_ENABLED": "1"}), \
                mock.patch.object(
                    production, "write_create_only_fsynced", side_effect=fail_terminal_file
                ):
            with self.assertRaisesRegex(OSError, "receipt interruption"):
                production.scheduled_run(
                    sqlite_path=self.sqlite_path,
                    writer_lock_path=self.writer_lock,
                    evidence_dir=self.evidence,
                    receipt_dir=self.receipts,
                    latest_pointer=self.latest,
                    failure_ledger_dir=self.failures,
                    invocation_kind="manual_service",
                    page_size=2,
                    clock=lambda: FIXED_CLOCK,
                    transport=production.shadow.FixtureTransport(FIXTURES),
                )
        failure_pointer = json.loads((self.failures / "latest.json").read_text())
        failure = json.loads(Path(failure_pointer["receipt_path"]).read_text())
        self.assertTrue(failure["canonical_receipt_committed"])
        self.assertEqual(self.table_count("sfwmd_pending_erp_runs"), 1)

    def test_scheduled_partial_terminal_has_onfailure_ledger_route(self):
        fixture_copy = self.root / "partial-scheduled-fixtures"
        shutil.copytree(FIXTURES, fixture_copy)
        end_ids = fixture_copy / "object-ids-end.json"
        payload = json.loads(end_ids.read_text())
        payload["objectIds"] = payload["objectIds"][:-1]
        end_ids.write_text(json.dumps(payload))
        with mock.patch.dict(os.environ, {"FLORIDA_SIGNAL_SFWMD_ENABLED": "1"}):
            result = production.scheduled_run(
                sqlite_path=self.sqlite_path,
                writer_lock_path=self.writer_lock,
                evidence_dir=self.evidence,
                receipt_dir=self.receipts,
                latest_pointer=self.latest,
                failure_ledger_dir=self.failures,
                invocation_kind="manual_service",
                page_size=2,
                clock=lambda: FIXED_CLOCK,
                transport=production.shadow.FixtureTransport(fixture_copy),
            )
        self.assertEqual(result["status"], "partial")
        failure_pointer = json.loads((self.failures / "latest.json").read_text())
        failure = json.loads(Path(failure_pointer["receipt_path"]).read_text())
        self.assertEqual(failure["stage"], "canonical_terminal")
        self.assertTrue(failure["canonical_receipt_committed"])

    def test_stale_natural_run_and_repair_cannot_roll_back_current_or_latest(self):
        newer_clock = FIXED_CLOCK + dt.timedelta(days=2)
        older_clock = FIXED_CLOCK + dt.timedelta(days=1)
        newer_dir = self.collect(clock=newer_clock)
        older_dir = self.collect(clock=older_clock)
        newer = self.commit(newer_dir, clock=newer_clock)
        older = self.commit(older_dir, clock=older_clock)
        self.assertEqual(newer["progress_status"], "changed")
        self.assertEqual(older["progress_status"], "superseded")
        self.assertEqual(older["counts"]["rows_accepted"], 0)
        with sqlite3.connect(self.sqlite_path) as connection:
            current_run = connection.execute(
                "select last_run_id from sfwmd_pending_erp_records where is_current=1"
            ).fetchone()[0]
            state = connection.execute(
                "select latest_snapshot_run_id,latest_natural_run_id "
                "from sfwmd_pending_erp_state where singleton=1"
            ).fetchone()
        self.assertEqual(current_run, newer["run_id"])
        self.assertEqual(state, (newer["run_id"], newer["run_id"]))
        pointer_before = self.latest.read_bytes()
        Path(older["receipt_path"]).unlink()
        repaired = production.repair_receipt_file(
            sqlite_path=self.sqlite_path,
            writer_lock_path=self.writer_lock,
            run_dir=older_dir,
            receipt_dir=self.receipts,
            latest_pointer=self.latest,
        )
        self.assertFalse(repaired["latest_pointer_advanced"])
        self.assertEqual(self.latest.read_bytes(), pointer_before)

    def test_fractional_second_observation_advances_after_exact_second(self):
        first = self.commit(self.collect(clock=FIXED_CLOCK), clock=FIXED_CLOCK)
        later_clock = FIXED_CLOCK + dt.timedelta(microseconds=500_000)
        later = self.commit(
            self.collect(clock=later_clock),
            clock=later_clock,
        )
        self.assertEqual(first["progress_status"], "changed")
        self.assertEqual(later["progress_status"], "unchanged")
        self.assertIn(".000000Z|", first["observation_order_key"])
        self.assertIn(".500000Z|", later["observation_order_key"])
        pointer = json.loads(self.latest.read_text())
        self.assertEqual(pointer["run_id"], later["run_id"])

    def test_schema_installer_is_exact_idempotent_and_refuses_poison(self):
        replay = production.install_schema(
            sqlite_path=self.sqlite_path,
            writer_lock_path=self.writer_lock,
        )
        self.assertEqual(replay["status"], "already_current")
        with production._open_database(self.sqlite_path) as connection:
            row = connection.execute(
                "select migration_sha256,object_manifest_sha256 "
                "from sfwmd_pending_erp_schema where singleton=1"
            ).fetchone()
            self.assertEqual(row["migration_sha256"], production.SQLITE_MIGRATION_SHA256)
            self.assertRegex(row["object_manifest_sha256"], r"^[0-9a-f]{64}$")

        with sqlite3.connect(self.sqlite_path) as connection:
            connection.execute("drop trigger sfwmd_pending_erp_runs_no_delete")
            connection.execute(
                "create trigger sfwmd_pending_erp_runs_no_delete "
                "before delete on sfwmd_pending_erp_runs begin "
                "select raise(abort, 'poisoned definition'); end"
            )
            _, forged_manifest_sha = production._schema_object_manifest(connection)
            connection.execute(
                "update sfwmd_pending_erp_schema set object_manifest_sha256=? where singleton=1",
                (forged_manifest_sha,),
            )
        with production._open_database(self.sqlite_path) as connection:
            with self.assertRaisesRegex(production.ProductionError, "definitions differ"):
                production.check_schema(connection)

        extra = self.root / "extra-object.sqlite"
        extra.touch()
        production.install_schema(
            sqlite_path=extra,
            writer_lock_path=self.root / "extra-object.lock",
        )
        with sqlite3.connect(extra) as connection:
            connection.execute(
                "create index unreviewed_sfwmd_index "
                "on sfwmd_pending_erp_records (app_no)"
            )
        with production._open_database(extra) as connection:
            with self.assertRaisesRegex(production.ProductionError, "object set"):
                production.check_schema(connection)

        case_variant = self.root / "case-variant.sqlite"
        case_variant.touch()
        production.install_schema(
            sqlite_path=case_variant,
            writer_lock_path=self.root / "case-variant.lock",
        )
        with sqlite3.connect(case_variant) as connection:
            connection.execute(
                "create view SFWMD_PENDING_ERP_EXPORT as "
                "select * from sfwmd_pending_erp_records"
            )
        with production._open_database(case_variant) as connection:
            with self.assertRaisesRegex(production.ProductionError, "object set"):
                production.check_schema(connection)

        poisoned = self.root / "poisoned.sqlite"
        with sqlite3.connect(poisoned) as connection:
            connection.execute("create table sfwmd_pending_erp_runs (wrong text)")
        with self.assertRaisesRegex(production.ProductionError, "poisoned or partial"):
            production.install_schema(
                sqlite_path=poisoned,
                writer_lock_path=self.root / "poisoned.lock",
            )
        with sqlite3.connect(poisoned) as connection:
            names = connection.execute(
                "select name from sqlite_master where name glob 'sfwmd_pending_erp_*'"
            ).fetchall()
        self.assertEqual(names, [("sfwmd_pending_erp_runs",)])

    def test_schema_installer_rolls_back_a_mid_migration_error(self):
        database = self.root / "rollback.sqlite"
        database.touch()
        migration = self.root / "bad.sql"
        migration.write_text(
            "create table sfwmd_pending_erp_first (value text);\n"
            "insert into sfwmd_pending_erp_missing values ('boom');\n"
        )
        digest = production.sha256_file(migration)
        with mock.patch.object(production, "SCHEMA_SQL_PATH", migration), \
                mock.patch.object(production, "SQLITE_MIGRATION_SHA256", digest):
            with self.assertRaises(sqlite3.Error):
                production.install_schema(
                    sqlite_path=database,
                    writer_lock_path=self.root / "rollback.lock",
                )
        with sqlite3.connect(database) as connection:
            count = connection.execute(
                "select count(*) from sqlite_master where name glob 'sfwmd_pending_erp_*'"
            ).fetchone()[0]
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
