from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import importlib.util
import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Sequence
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "droplet" / "utility_intake_shadow.py"
SPEC = importlib.util.spec_from_file_location("utility_intake_shadow", SCRIPT)
shadow = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = shadow
SPEC.loader.exec_module(shadow)


FIXED_CLOCK = dt.datetime(2026, 8, 31, 12, 0, tzinfo=dt.timezone.utc)

POSITIVE_ROWS = (
    ("ENG-CR-26010001", "Capacity Request", "2026-01-10", "2026-01-11", "2026-01-20"),
    ("ENG-OAA-26020001", "Outside Agency", "2026-02-01", None, None),
    ("ROW-SEW-25050015", "Sewer ROW", "2025-05-02", "2025-05-03", "2025-06-01"),
    ("ROW-SEW-25050015.D001", "Sewer ROW subpermit", "2025-05-04", None, None),
    ("ROW-WTR-26030001", "Water ROW", "2026-03-01", "2026-03-02", None),
    ("PLB-SEWCP-WT-26040010", "Sewer cap walk-through", "2026-04-10", None, None),
)

NEGATIVE_ROWS = (
    "ENG-26010099",
    "ENG-MISC-26010002",
    "ROW-26010003",
    "ROW-SEWER-26010004",
    "ROW-SW-26010005",
    "PLB-RES-26010006",
    "PLB-SEWCP-26010007",
    "TMP-26010008",
    "26TMP-26010009",
    "BLD-NEW-26010010",
)


def _touch_lock(path: Path) -> Path:
    path.write_text("")
    return path


def _create_fixture_db(
    path: Path,
    *,
    include_clocks: bool = True,
    include_accela: bool = True,
    duplicate_identity: bool = False,
    missing_clock_identity: str | None = "ENG-OAA-26020001",
    extra_rows: Sequence[tuple] | None = None,
    permits_table: bool = True,
    source_modified_at: str | None = None,
    last_updated_at_value: str | None = None,
    raw_json_by_permit: dict[str, str] | None = None,
) -> Path:
    connection = sqlite3.connect(path)
    try:
        if permits_table:
            columns = [
                "permit_number TEXT",
                "report_source TEXT NOT NULL",
                "permit_type TEXT",
                "status TEXT",
                "address TEXT",
                "parcel_id TEXT",
                "owner_name TEXT",
                "contractor_name TEXT",
                "description TEXT",
                "raw_json TEXT",
                "first_seen_at TEXT NOT NULL",
                "last_seen_at TEXT NOT NULL",
            ]
            if include_clocks:
                columns[4:4] = [
                    "applied_date TEXT",
                    "issued_date TEXT",
                    "opened_date TEXT",
                    "finalized_date TEXT",
                    "last_updated_at TEXT",
                    "source_modified_at TEXT",
                ]
            connection.execute("CREATE TABLE permits (" + ", ".join(columns) + ")")
            rows = list(POSITIVE_ROWS) + [
                (number, "other", None, None, None) for number in NEGATIVE_ROWS
            ]
            if extra_rows:
                rows.extend(extra_rows)
            for permit_number, permit_type, applied, opened, issued in rows:
                values = {
                    "permit_number": permit_number,
                    "report_source": "opened_permits",
                    "permit_type": permit_type,
                    "status": "Applied",
                    "address": "100 N Andrews Ave",
                    "parcel_id": "123456789012",
                    "owner_name": "Example Owner",
                    "contractor_name": "Example Contractor",
                    "description": permit_type,
                    "raw_json": (raw_json_by_permit or {}).get(
                        permit_number, json.dumps({"permit_number": permit_number})
                    ),
                    "first_seen_at": "2026-08-01T00:00:00Z",
                    "last_seen_at": "2026-08-15T00:00:00Z",
                }
                if include_clocks:
                    use_dates = permit_number != missing_clock_identity
                    values.update(
                        {
                            "applied_date": applied if use_dates else None,
                            "opened_date": opened if use_dates else None,
                            "issued_date": issued if use_dates else None,
                            "finalized_date": None,
                            "last_updated_at": last_updated_at_value,
                            "source_modified_at": source_modified_at if use_dates else None,
                        }
                    )
                placeholders = ", ".join(":" + key for key in values)
                connection.execute(
                    f"INSERT INTO permits ({', '.join(values)}) VALUES ({placeholders})",
                    values,
                )
            if duplicate_identity:
                connection.execute(
                    "INSERT INTO permits (permit_number, report_source, permit_type, "
                    "status, address, description, raw_json, first_seen_at, last_seen_at"
                    + (", applied_date" if include_clocks else "")
                    + ") VALUES (?, 'opened_permits', 'dup', 'Applied', 'x', 'dup', '{}', "
                    "'2026-08-01T00:00:00Z', '2026-08-15T00:00:00Z'"
                    + (", '2026-01-01'" if include_clocks else "")
                    + ")",
                    ("ENG-CR-26010001",),
                )
            connection.execute(
                "INSERT INTO permits (permit_number, report_source, permit_type, status, "
                "address, description, raw_json, first_seen_at, last_seen_at"
                + (", applied_date" if include_clocks else "")
                + ") VALUES ('', 'opened_permits', 'blank', 'Applied', 'x', 'blank', '{}', "
                "'2026-08-01T00:00:00Z', '2026-08-15T00:00:00Z'"
                + (", NULL" if include_clocks else "")
                + ")"
            )
        else:
            connection.execute("CREATE TABLE other_table (id INTEGER)")
        if include_accela and permits_table:
            connection.execute(
                "CREATE TABLE accela_details ("
                "permit_number TEXT, source_url TEXT, status_date TEXT, raw_json TEXT)"
            )
            connection.execute(
                "INSERT INTO accela_details VALUES (?, ?, ?, ?)",
                (
                    "ENG-CR-26010001",
                    "https://aca-prod.accela.com/FTL/Cap/CapDetail.aspx?"
                    "Module=Permits&capID1=CAP1&capID2=CAP2&capID3=CAP3&agencyCode=FTL",
                    "2026-01-12",
                    "{}",
                ),
            )
        connection.commit()
    finally:
        connection.close()
    return path


class UtilityIntakeShadowTests(unittest.TestCase):
    def run_fixture(self, output_root, sqlite_path, **kwargs):
        lock_path = kwargs.pop("writer_lock_path", None)
        if lock_path is None:
            lock_path = Path(sqlite_path).parent / ".writer.lock"
            if not Path(lock_path).exists():
                _touch_lock(Path(lock_path))
        run_dir, receipt = shadow.run_collection(
            sqlite_path=Path(sqlite_path),
            output_root=Path(output_root),
            writer_lock_path=Path(lock_path),
            run_id=kwargs.pop("run_id", "utility-intake-test"),
            clock=kwargs.pop("clock", lambda: FIXED_CLOCK),
            **kwargs,
        )
        return run_dir, receipt

    def test_positive_families_and_negative_prefixes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = _create_fixture_db(Path(tmp) / "permits.sqlite")
            run_dir, receipt = self.run_fixture(Path(tmp) / "out", db_path)

            self.assertEqual(receipt["status"], "partial")
            self.assertEqual(receipt["mode"], "shadow_file_only")
            self.assertTrue(receipt["dry_run"])
            self.assertEqual(receipt["counts"]["rows_admitted"], 6)
            self.assertEqual(receipt["family_counts"]["ENG-CR"], 1)
            self.assertEqual(receipt["family_counts"]["ENG-OAA"], 1)
            self.assertEqual(receipt["family_counts"]["ROW-SEW"], 2)
            self.assertEqual(receipt["family_counts"]["ROW-WTR"], 1)
            self.assertEqual(receipt["family_counts"]["PLB-SEWCP-WT"], 1)
            self.assertEqual(receipt["unknown_prefix_counts"]["ENG"], 2)
            self.assertEqual(receipt["unknown_prefix_counts"]["ROW"], 3)
            self.assertEqual(receipt["unknown_prefix_counts"]["PLB"], 2)
            self.assertEqual(receipt["unknown_prefix_counts"]["TMP"], 1)
            self.assertGreaterEqual(receipt["unknown_prefix_counts"]["other"], 2)
            self.assertEqual(receipt["counts"]["rows_rejected"], 1)
            self.assertEqual(
                receipt["rejection_reasons"]["malformed_permit_number"], 1
            )
            self.assertFalse(receipt["safety"]["promotion_eligible"])
            self.assertFalse(receipt["safety"]["connected_label_allowed"])
            self.assertFalse(receipt["safety"]["collector_issued_source_row_writes"])
            self.assertFalse(receipt["safety"]["collector_issued_main_database_content_writes"])
            self.assertFalse(receipt["safety"]["collector_issued_wal_content_writes"])
            self.assertTrue(receipt["safety"]["sqlite_shm_reader_metadata_may_change"])
            self.assertFalse(receipt["safety"]["zero_filesystem_mutation_claimed"])
            self.assertFalse(receipt["safety"]["candidate_scoring"])
            self.assertFalse(receipt["timing_claims"]["earlier_than_pdmr"])
            self.assertEqual(receipt["schema_version"], shadow.SCHEMA_VERSION)
            self.assertEqual(
                receipt["input_database"]["fingerprint_kind"],
                "contract_relevant_logical_projection",
            )
            lock = receipt["input_database"]["writer_lock"]
            self.assertEqual(lock["mode"], "shared_nonblocking")
            self.assertEqual(
                lock["stat_before"]["inode"],
                (Path(tmp) / ".writer.lock").stat().st_ino,
            )
            self.assertEqual(lock["stat_before"], lock["stat_after"])
            self.assertTrue(lock["stat_unchanged"])
            self.assertEqual(lock["basename"], ".writer.lock")
            self.assertNotIn("sha256", receipt["input_database"])
            self.assertNotIn("input_database_sha256", receipt["hashes"])
            self.assertIn("logical_input_database_fingerprint", receipt["hashes"])
            self.assertTrue(receipt["input_database"]["data_version_stable"])
            self.assertEqual(receipt["input_database"]["quick_check"]["permits"], "ok")
            self.assertTrue(receipt["input_database"]["stat_unchanged"])
            sidecars = receipt["input_database"]["sidecars"]
            self.assertFalse(sidecars["before"]["wal"]["exists"])
            self.assertTrue(sidecars["contract_passed"])
            self.assertTrue(receipt["quality"]["sidecar_contract_passed"])
            self.assertEqual(run_dir.stat().st_mode & 0o777, 0o700)

            records = [
                json.loads(line)
                for line in (run_dir / "shadow-records.jsonl").read_text().splitlines()
            ]
            identities = [row["identity"]["permit_number"] for row in records]
            self.assertEqual(
                identities,
                [
                    "ENG-CR-26010001",
                    "ENG-OAA-26020001",
                    "PLB-SEWCP-WT-26040010",
                    "ROW-SEW-25050015",
                    "ROW-SEW-25050015.D001",
                    "ROW-WTR-26030001",
                ],
            )
            self.assertEqual(records[0]["identity"]["family_id"], "ENG-CR")
            self.assertEqual(records[4]["identity"]["record_role"], "subpermit")
            self.assertEqual(records[0]["cap_id"]["value"]["capID1"], "CAP1")
            admitted = set(identities)
            for negative in NEGATIVE_ROWS:
                self.assertNotIn(negative, admitted)

    def test_broad_prefix_classifier_never_matches(self):
        for number in NEGATIVE_ROWS:
            self.assertIsNone(shadow.classify_record_number(number), number)
        self.assertEqual(
            shadow.classify_record_number("ENG-CR-26010001").family_id, "ENG-CR"
        )
        self.assertIsNone(shadow.classify_record_number("ENG-CR-"))
        self.assertIsNone(shadow.classify_record_number("PLB-SEWCP-WT"))
        self.assertIsNone(shadow.classify_record_number("ENG-CR-26010001.D001"))
        self.assertIsNone(shadow.classify_record_number("ENG-OAA-26020001.S001"))
        self.assertEqual(
            shadow.classify_record_number("ROW-SEW-25050015.D001").family_id,
            "ROW-SEW",
        )
        self.assertEqual(
            shadow.classify_record_number("PLB-SEWCP-WT-26040010.D001").family_id,
            "PLB-SEWCP-WT",
        )

    def test_duplicate_identity_is_rejected_and_blocks_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = _create_fixture_db(
                Path(tmp) / "permits.sqlite", duplicate_identity=True
            )
            _, receipt = self.run_fixture(Path(tmp) / "out", db_path)
            self.assertEqual(receipt["status"], "partial")
            self.assertEqual(receipt["counts"]["duplicate_identities"], 1)
            self.assertEqual(receipt["family_counts"]["ENG-CR"], 1)
            self.assertFalse(receipt["quality"]["business_identity_unique"])

    def test_missing_clocks_are_unknown_not_invented(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = _create_fixture_db(Path(tmp) / "permits.sqlite")
            run_dir, _ = self.run_fixture(Path(tmp) / "out", db_path)
            records = {
                json.loads(line)["identity"]["permit_number"]: json.loads(line)
                for line in (run_dir / "shadow-records.jsonl").read_text().splitlines()
            }
            missing = records["ENG-OAA-26020001"]
            self.assertEqual(
                missing["clocks"]["application"]["status"], "UNKNOWN_VALUE_ABSENT"
            )
            self.assertEqual(
                missing["clocks"]["event"]["opened_at"]["status"],
                "UNKNOWN_VALUE_ABSENT",
            )
            self.assertEqual(
                missing["clocks"]["source_modified"]["status"],
                "UNKNOWN_VALUE_ABSENT",
            )
            present = records["ENG-CR-26010001"]
            self.assertEqual(present["clocks"]["application"]["value"], "2026-01-10")
            self.assertEqual(
                present["clocks"]["event"]["status_date"]["value"], "2026-01-12"
            )

    def test_last_updated_at_is_not_a_source_modified_clock(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = _create_fixture_db(
                Path(tmp) / "permits.sqlite",
                last_updated_at_value="2026-08-30T12:00:00Z",
                include_accela=False,
            )
            run_dir, _ = self.run_fixture(Path(tmp) / "out", db_path)
            records = [
                json.loads(line)
                for line in (run_dir / "shadow-records.jsonl").read_text().splitlines()
            ]
            sample = records[0]
            self.assertEqual(
                sample["clocks"]["source_modified"]["status"], "UNKNOWN_VALUE_ABSENT"
            )
            self.assertIsNone(sample["clocks"]["source_modified"]["value"])
            self.assertEqual(
                sample["source"]["last_updated_at"], "2026-08-30T12:00:00Z"
            )

    def test_source_modified_at_is_used_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = _create_fixture_db(
                Path(tmp) / "permits.sqlite",
                source_modified_at="2026-05-01T00:00:00Z",
                last_updated_at_value="1999-01-01T00:00:00Z",
            )
            run_dir, _ = self.run_fixture(Path(tmp) / "out", db_path)
            records = {
                json.loads(line)["identity"]["permit_number"]: json.loads(line)
                for line in (run_dir / "shadow-records.jsonl").read_text().splitlines()
            }
            present = records["ENG-CR-26010001"]
            self.assertEqual(present["clocks"]["source_modified"]["status"], "PRESENT")
            self.assertEqual(
                present["clocks"]["source_modified"]["value"], "2026-05-01T00:00:00Z"
            )
            self.assertEqual(
                present["clocks"]["source_modified"]["column"], "source_modified_at"
            )
            self.assertNotEqual(
                present["clocks"]["source_modified"]["value"],
                present["source"]["last_updated_at"],
            )

    def test_absent_clock_columns_are_unknown_column_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = _create_fixture_db(
                Path(tmp) / "permits.sqlite",
                include_clocks=False,
                include_accela=False,
            )
            run_dir, receipt = self.run_fixture(Path(tmp) / "out", db_path)
            sample = json.loads(
                (run_dir / "shadow-records.jsonl").read_text().splitlines()[0]
            )
            self.assertEqual(
                sample["clocks"]["application"]["status"], "UNKNOWN_COLUMN_ABSENT"
            )
            self.assertEqual(
                sample["clocks"]["source_modified"]["status"], "UNKNOWN_COLUMN_ABSENT"
            )
            self.assertIsNone(sample["clocks"]["source_modified"]["column"])
            self.assertEqual(receipt["source"]["serving_utility"], "UNKNOWN_NOT_IN_SOURCE_ROW")

    def test_ordering_and_hashes_are_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = _create_fixture_db(Path(tmp) / "permits.sqlite")
            first_dir, first = self.run_fixture(
                Path(tmp) / "out", db_path, run_id="first"
            )
            second_dir, second = self.run_fixture(
                Path(tmp) / "out", db_path, run_id="second"
            )
            self.assertEqual(
                first["hashes"]["record_identity_fingerprint"],
                second["hashes"]["record_identity_fingerprint"],
            )
            self.assertEqual(
                first["hashes"]["content_fingerprint"],
                second["hashes"]["content_fingerprint"],
            )
            self.assertEqual(
                first["hashes"]["logical_input_database_fingerprint"],
                second["hashes"]["logical_input_database_fingerprint"],
            )
            self.assertEqual(
                (first_dir / "shadow-records.jsonl").read_bytes(),
                (second_dir / "shadow-records.jsonl").read_bytes(),
            )
            later = FIXED_CLOCK + dt.timedelta(hours=1)
            third_dir, third = shadow.run_collection(
                sqlite_path=db_path,
                output_root=Path(tmp) / "out",
                writer_lock_path=Path(tmp) / ".writer.lock",
                run_id="third-clock",
                clock=lambda: later,
            )
            self.assertEqual(
                first["hashes"]["content_fingerprint"],
                third["hashes"]["content_fingerprint"],
            )
            self.assertEqual(
                (first_dir / "shadow-content-index.jsonl").read_bytes(),
                (third_dir / "shadow-content-index.jsonl").read_bytes(),
            )
            self.assertNotEqual(
                first["hashes"]["observation_bundle_sha256"],
                third["hashes"]["observation_bundle_sha256"],
            )

    def test_query_only_enforcement_and_unchanged_database_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = _create_fixture_db(Path(tmp) / "permits.sqlite")
            before = hashlib.sha256(db_path.read_bytes()).hexdigest()
            connection = shadow.connect_query_only(db_path)
            try:
                flag = connection.execute("PRAGMA query_only").fetchone()[0]
                self.assertEqual(int(flag), 1)
                with self.assertRaises(sqlite3.OperationalError):
                    connection.execute(
                        "INSERT INTO permits (permit_number, report_source, "
                        "first_seen_at, last_seen_at) VALUES ('X', 'x', 'x', 'x')"
                    )
            finally:
                connection.close()
            _, receipt = self.run_fixture(Path(tmp) / "out", db_path)
            after = hashlib.sha256(db_path.read_bytes()).hexdigest()
            self.assertEqual(before, after)
            self.assertTrue(receipt["quality"]["query_only"])
            self.assertFalse(receipt["safety"]["collector_issued_source_row_writes"])
            self.assertFalse((Path(str(db_path) + "-wal")).exists())
            self.assertFalse((Path(str(db_path) + "-shm")).exists())
            self.assertFalse((Path(str(db_path) + "-journal")).exists())

    def test_refuses_to_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = _create_fixture_db(Path(tmp) / "permits.sqlite")
            self.run_fixture(Path(tmp) / "out", db_path, run_id="same-run")
            with self.assertRaises(FileExistsError):
                self.run_fixture(Path(tmp) / "out", db_path, run_id="same-run")

    def test_missing_permits_table_fails_closed_with_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = _create_fixture_db(
                Path(tmp) / "permits.sqlite",
                permits_table=False,
                include_accela=False,
            )
            run_dir, receipt = self.run_fixture(Path(tmp) / "out", db_path)
            self.assertEqual(receipt["status"], "failed")
            self.assertIn("required table permits is absent", receipt["terminal_error"])
            self.assertTrue((run_dir / "receipt.json").is_file())
            self.assertFalse(receipt["quality"]["schema_contract_passed"])
            self.assertFalse(receipt["safety"]["collector_issued_source_row_writes"])
            self.assertFalse(receipt["safety"]["collector_issued_main_database_content_writes"])
            self.assertFalse(receipt["safety"]["collector_issued_wal_content_writes"])
            self.assertNotIn("source_row_writes", receipt["safety"])

    def test_secrets_are_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "permits.sqlite"
            connection = sqlite3.connect(db_path)
            connection.execute(
                "CREATE TABLE permits (permit_number TEXT, report_source TEXT NOT NULL, "
                "api_token TEXT, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO permits VALUES ('ENG-CR-1', 'opened_permits', 'super-secret', "
                "'2026-08-01T00:00:00Z', '2026-08-15T00:00:00Z')"
            )
            connection.commit()
            connection.close()
            run_dir, receipt = self.run_fixture(Path(tmp) / "out", db_path)
            dumped = (run_dir / "observation-bundle.json").read_text()
            self.assertNotIn("super-secret", dumped)
            self.assertNotIn("super-secret", json.dumps(receipt))
            record = json.loads(dumped)["records"][0]
            self.assertEqual(record["source"]["api_token"], "<redacted>")

    def test_nested_secrets_in_raw_json_are_redacted(self):
        nested = json.dumps(
            {
                "ok": "visible",
                "child": {"api_token": "nested-secret-value", "note": "keep"},
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            db_path = _create_fixture_db(
                Path(tmp) / "permits.sqlite",
                raw_json_by_permit={"ENG-CR-26010001": nested},
            )
            run_dir, receipt = self.run_fixture(Path(tmp) / "out", db_path)
            dumped = (run_dir / "observation-bundle.json").read_text()
            self.assertNotIn("nested-secret-value", dumped)
            self.assertNotIn("nested-secret-value", json.dumps(receipt))
            records = {
                json.loads(line)["identity"]["permit_number"]: json.loads(line)
                for line in (run_dir / "shadow-records.jsonl").read_text().splitlines()
            }
            payload = records["ENG-CR-26010001"]["source"]["raw_json"]
            self.assertEqual(payload["ok"], "visible")
            self.assertEqual(payload["child"]["api_token"], "<redacted>")
            self.assertEqual(payload["child"]["note"], "keep")
            self.assertGreaterEqual(receipt["counts"]["secrets_redacted"], 1)

    def test_writer_lock_contention_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = _create_fixture_db(Path(tmp) / "permits.sqlite")
            lock_path = _touch_lock(Path(tmp) / ".writer.lock")
            holder = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    "import fcntl, sys, time\n"
                    "handle = open(sys.argv[1], 'r+')\n"
                    "fcntl.flock(handle.fileno(), fcntl.LOCK_EX)\n"
                    "print('ready', flush=True)\n"
                    "time.sleep(30)\n",
                    str(lock_path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                line = holder.stdout.readline()
                self.assertEqual(line.strip(), "ready")
                with self.assertRaises(shadow.CollectorError) as caught:
                    self.run_fixture(
                        Path(tmp) / "out",
                        db_path,
                        writer_lock_path=lock_path,
                    )
                self.assertIn("exclusively", str(caught.exception))
                self.assertFalse((Path(tmp) / "out" / "utility-intake-test").exists())
            finally:
                holder.terminate()
                try:
                    holder.wait(timeout=5)
                finally:
                    if holder.stdout:
                        holder.stdout.close()
                    if holder.stderr:
                        holder.stderr.close()

    def test_writer_lock_path_replacement_during_read_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = _create_fixture_db(Path(tmp) / "permits.sqlite")
            lock_path = _touch_lock(Path(tmp) / ".writer.lock")
            original_read = shadow._read_snapshot

            def read_then_replace(*args, **kwargs):
                snapshot = original_read(*args, **kwargs)
                lock_path.unlink()
                lock_path.write_text("replacement")
                return snapshot

            with mock.patch.object(
                shadow, "_read_snapshot", side_effect=read_then_replace
            ):
                _, receipt = self.run_fixture(
                    Path(tmp) / "out",
                    db_path,
                    writer_lock_path=lock_path,
                )
            self.assertEqual(receipt["status"], "failed")
            self.assertIn("writer-lock path identity changed", receipt["terminal_error"])
            self.assertFalse(
                receipt["input_database"]["writer_lock"]["stat_unchanged"]
            )

    def test_incomplete_or_rollback_sidecars_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = _create_fixture_db(Path(tmp) / "permits.sqlite")
            (Path(str(db_path) + "-wal")).write_bytes(b"not-a-checkpoint")
            with self.assertRaises(shadow.SourceContractError) as caught:
                self.run_fixture(Path(tmp) / "out", db_path)
            self.assertIn("sidecar", str(caught.exception))
            self.assertFalse((Path(tmp) / "out" / "utility-intake-test").exists())

        with tempfile.TemporaryDirectory() as tmp:
            db_path = _create_fixture_db(Path(tmp) / "permits.sqlite")
            (Path(str(db_path) + "-journal")).write_bytes(b"rollback")
            with self.assertRaises(shadow.SourceContractError):
                self.run_fixture(Path(tmp) / "out", db_path)

    def test_real_wal_pair_is_read_as_one_stable_query_only_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = _create_fixture_db(Path(tmp) / "permits.sqlite")
            writer = sqlite3.connect(db_path)
            try:
                self.assertEqual(writer.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
                writer.execute("PRAGMA wal_autocheckpoint=0")
                writer.execute(
                    "UPDATE permits SET status = ? WHERE permit_number = ?",
                    ("WAL_ONLY_STATUS", "ENG-CR-26010001"),
                )
                writer.commit()
                wal_path = Path(str(db_path) + "-wal")
                shm_path = Path(str(db_path) + "-shm")
                self.assertTrue(wal_path.is_file())
                self.assertTrue(shm_path.is_file())
                self.assertGreater(wal_path.stat().st_size, 32)
                wal_before = shadow.file_stat_snapshot(wal_path)

                run_dir, receipt = self.run_fixture(Path(tmp) / "out", db_path)

                sidecars = receipt["input_database"]["sidecars"]
                self.assertEqual(sidecars["snapshot_mode"], "wal_read_transaction")
                self.assertEqual(sidecars["journal_mode"], "wal")
                self.assertTrue(sidecars["before"]["wal"]["exists"])
                self.assertTrue(sidecars["before"]["shm"]["exists"])
                self.assertEqual(sidecars["before"]["wal"]["stat"], wal_before)
                self.assertTrue(sidecars["wal_stat_stable"])
                self.assertTrue(sidecars["shm_identity_stable"])
                self.assertTrue(sidecars["rollback_journal_absent"])
                self.assertTrue(sidecars["contract_passed"])
                self.assertTrue(receipt["quality"]["sidecar_contract_passed"])
                self.assertTrue(receipt["quality"]["query_only"])
                records = [
                    json.loads(line)
                    for line in (run_dir / "shadow-records.jsonl").read_text().splitlines()
                ]
                wal_record = next(
                    row for row in records
                    if row["identity"]["permit_number"] == "ENG-CR-26010001"
                )
                self.assertEqual(wal_record["source"]["status"], "WAL_ONLY_STATUS")
                self.assertFalse(receipt["safety"]["collector_issued_source_row_writes"])
                self.assertFalse(receipt["safety"]["collector_issued_main_database_content_writes"])
                self.assertFalse(receipt["safety"]["collector_issued_wal_content_writes"])
                self.assertTrue(receipt["safety"]["sqlite_shm_reader_metadata_may_change"])
                self.assertFalse(receipt["safety"]["zero_filesystem_mutation_claimed"])
            finally:
                writer.close()

    def test_failed_wal_change_receipt_scopes_collector_write_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = _create_fixture_db(Path(tmp) / "permits.sqlite")
            writer = sqlite3.connect(db_path)
            try:
                self.assertEqual(writer.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
                writer.execute("PRAGMA wal_autocheckpoint=0")
                writer.execute(
                    "UPDATE permits SET status = ? WHERE permit_number = ?",
                    ("WAL_BASELINE", "ENG-CR-26010001"),
                )
                writer.commit()
                before = shadow.sidecar_snapshot(db_path)
                after = json.loads(json.dumps(before))
                after["wal"]["stat"]["size_bytes"] += 1
                with mock.patch.object(
                    shadow,
                    "sidecar_snapshot",
                    side_effect=[before, after],
                ):
                    _, receipt = self.run_fixture(Path(tmp) / "out", db_path)

                self.assertEqual(receipt["status"], "failed")
                self.assertIn("SQLite WAL changed", receipt["terminal_error"])
                self.assertFalse(receipt["quality"]["sidecar_contract_passed"])
                self.assertFalse(receipt["safety"]["collector_issued_source_row_writes"])
                self.assertFalse(receipt["safety"]["collector_issued_main_database_content_writes"])
                self.assertFalse(receipt["safety"]["collector_issued_wal_content_writes"])
                self.assertNotIn("wal_content_writes", receipt["safety"])
            finally:
                writer.close()

    def test_postflight_rejects_every_material_sidecar_transition(self):
        stat = {"size_bytes": 100, "mtime_ns": 10, "inode": 20, "device": 30}
        absent = {"exists": False, "stat": None}
        present = {"exists": True, "stat": dict(stat)}

        cases = []
        before = {"wal": present, "shm": present, "journal": absent}
        after = json.loads(json.dumps(before))
        after["wal"]["stat"]["size_bytes"] += 1
        cases.append(("wal append", before, after, "SQLite WAL changed"))

        before = {"wal": absent, "shm": absent, "journal": absent}
        after = {"wal": present, "shm": present, "journal": absent}
        cases.append(("wal pair appeared", before, after, "sidecar presence changed"))

        before = {"wal": present, "shm": present, "journal": absent}
        after = {"wal": absent, "shm": absent, "journal": absent}
        cases.append(("wal pair disappeared", before, after, "sidecar presence changed"))

        before = {"wal": present, "shm": present, "journal": absent}
        after = json.loads(json.dumps(before))
        after["shm"]["stat"]["inode"] += 1
        cases.append(("shm replaced", before, after, "SHM file identity changed"))

        before = {"wal": present, "shm": present, "journal": absent}
        after = json.loads(json.dumps(before))
        after["journal"] = present
        cases.append(("rollback journal appeared", before, after, "rollback journal appeared"))

        for label, before, after, expected_error in cases:
            with self.subTest(label=label):
                result, error = shadow.validate_sidecar_postflight(before, after, "wal")
                self.assertFalse(result["contract_passed"])
                self.assertIn(expected_error, error)

    def test_data_version_is_rechecked_after_commit_and_detects_concurrent_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = _create_fixture_db(Path(tmp) / "permits.sqlite")
            writer = sqlite3.connect(db_path)
            try:
                self.assertEqual(writer.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
                writer.execute("PRAGMA wal_autocheckpoint=0")
                writer.execute(
                    "UPDATE permits SET status = ? WHERE permit_number = ?",
                    ("WAL_BASELINE", "ENG-CR-26010001"),
                )
                writer.commit()
                original = shadow.build_observation
                committed = False

                def build_then_commit(**kwargs):
                    nonlocal committed
                    if not committed:
                        writer.execute(
                            "UPDATE permits SET status = ? WHERE permit_number = ?",
                            ("CONCURRENT_COMMIT", "ROW-WTR-26030001"),
                        )
                        writer.commit()
                        committed = True
                    return original(**kwargs)

                with mock.patch.object(
                    shadow, "build_observation", side_effect=build_then_commit
                ):
                    snapshot = shadow._read_snapshot(db_path, "2026-08-31T12:00:00Z")

                self.assertTrue(committed, snapshot["terminal_error"])
                self.assertNotEqual(
                    snapshot["data_version_start"], snapshot["data_version_end"]
                )
                self.assertFalse(snapshot["data_version_stable"])
                self.assertIn("data_version changed", snapshot["terminal_error"])
            finally:
                writer.close()

    def test_missing_writer_lock_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = _create_fixture_db(Path(tmp) / "permits.sqlite")
            with self.assertRaises(shadow.CollectorError) as caught:
                shadow.run_collection(
                    sqlite_path=db_path,
                    output_root=Path(tmp) / "out",
                    writer_lock_path=Path(tmp) / "missing.lock",
                    run_id="no-lock",
                    clock=lambda: FIXED_CLOCK,
                )
            self.assertIn("does not exist", str(caught.exception))

    def test_cli_requires_absolute_paths_and_reports_shadow_only(self):
        with contextlib.redirect_stderr(io.StringIO()):
            rc = shadow.main(
                [
                    "--sqlite-path",
                    "relative.sqlite",
                    "--writer-lock-path",
                    "/tmp/lock",
                    "--output-dir",
                    "/tmp/utility-shadow",
                ]
            )
        self.assertEqual(rc, 64)
        with tempfile.TemporaryDirectory() as tmp:
            db_path = _create_fixture_db(Path(tmp) / "permits.sqlite")
            lock_path = _touch_lock(Path(tmp) / ".writer.lock")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = shadow.main(
                    [
                        "--sqlite-path",
                        str(db_path),
                        "--writer-lock-path",
                        str(lock_path),
                        "--output-dir",
                        str(Path(tmp) / "out"),
                        "--run-id",
                        "utility-cli",
                    ]
                )
            result = json.loads(stdout.getvalue())
            self.assertEqual(rc, 65)
            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["mode"], "shadow_file_only")
            self.assertFalse(result["promotion_eligible"])
            self.assertFalse(result["connected_label_allowed"])
            receipt = json.loads(
                (Path(result["run_dir"]) / "receipt.json").read_text()
            )
            self.assertIn("logical_input_database_fingerprint", receipt["hashes"])
            self.assertNotIn("input_database_sha256", receipt["hashes"])
            self.assertEqual(
                receipt["input_database"]["fingerprint_kind"],
                "contract_relevant_logical_projection",
            )

    def test_dotted_eng_subpermits_are_not_admitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = _create_fixture_db(
                Path(tmp) / "permits.sqlite",
                extra_rows=(
                    ("ENG-CR-26010001.D001", "Capacity subpermit", "2026-01-12", None, None),
                    ("ENG-OAA-26020001.S001", "OAA subpermit", "2026-02-02", None, None),
                ),
            )
            run_dir, receipt = self.run_fixture(Path(tmp) / "out", db_path)
            identities = [
                json.loads(line)["identity"]["permit_number"]
                for line in (run_dir / "shadow-records.jsonl").read_text().splitlines()
            ]
            self.assertNotIn("ENG-CR-26010001.D001", identities)
            self.assertNotIn("ENG-OAA-26020001.S001", identities)
            self.assertIn("ENG-CR-26010001", identities)
            self.assertIn("ROW-SEW-25050015.D001", identities)
            self.assertEqual(receipt["family_counts"]["ENG-CR"], 1)
            self.assertEqual(receipt["family_counts"]["ENG-OAA"], 1)
            self.assertGreaterEqual(receipt["unknown_prefix_counts"]["ENG"], 4)

    def test_evidence_files_are_0600_create_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = shadow.EvidenceBundle(Path(tmp), "perm-test")
            path, _ = bundle.write_json("receipt.json", {"ok": True})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                bundle.write_json("receipt.json", {"again": True})
            self.assertEqual(path.read_bytes()[:10], b'{"ok":true')

    def test_evidence_write_zero_progress_fails_and_removes_partial_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "partial.json"
            with mock.patch.object(shadow.os, "write", return_value=0):
                with self.assertRaises(OSError) as caught:
                    shadow.EvidenceBundle._write_private_create_only(path, b"payload")
            self.assertIn("no forward progress", str(caught.exception))
            self.assertFalse(path.exists())

    def test_supporting_source_modified_clock_is_preferred(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "permits.sqlite"
            connection = sqlite3.connect(db_path)
            connection.execute(
                "CREATE TABLE permits (permit_number TEXT, report_source TEXT NOT NULL, "
                "last_updated_at TEXT, source_modified_at TEXT, source_url TEXT, "
                "first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO permits VALUES ('ENG-CR-1', 'opened_permits', "
                "'1999-01-01T00:00:00Z', '2026-01-01T00:00:00Z', "
                "'https://example.invalid/CapDetail.aspx?capID1=PERM1&capID2=PERM2&capID3=PERM3', "
                "'2026-08-01T00:00:00Z', '2026-08-15T00:00:00Z')"
            )
            connection.execute(
                "CREATE TABLE accela_details (permit_number TEXT, source_url TEXT, "
                "source_modified_at TEXT, last_updated_at TEXT)"
            )
            connection.execute(
                "INSERT INTO accela_details VALUES ('ENG-CR-1', '', "
                "'2026-04-02T00:00:00Z', '1998-01-01T00:00:00Z')"
            )
            connection.commit()
            connection.close()
            run_dir, _ = self.run_fixture(Path(tmp) / "out", db_path)
            record = json.loads(
                (run_dir / "shadow-records.jsonl").read_text().splitlines()[0]
            )
            clock = record["clocks"]["source_modified"]
            self.assertEqual(clock["status"], "PRESENT")
            self.assertEqual(clock["value"], "2026-04-02T00:00:00Z")
            self.assertEqual(clock["origin"], "accela_details")
            self.assertEqual(clock["column"], "source_modified_at")
            self.assertEqual(record["source"]["last_updated_at"], "1999-01-01T00:00:00Z")
            self.assertEqual(record["cap_id"]["value"]["capID1"], "PERM1")

    def test_empty_supporting_source_modified_falls_back_to_permits(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "permits.sqlite"
            connection = sqlite3.connect(db_path)
            connection.execute(
                "CREATE TABLE permits (permit_number TEXT, report_source TEXT NOT NULL, "
                "source_modified_at TEXT, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO permits VALUES ('ENG-CR-1', 'opened_permits', "
                "'2026-03-03T00:00:00Z', '2026-08-01T00:00:00Z', '2026-08-15T00:00:00Z')"
            )
            connection.execute(
                "CREATE TABLE accela_details (permit_number TEXT, source_modified_at TEXT)"
            )
            connection.execute("INSERT INTO accela_details VALUES ('ENG-CR-1', '')")
            connection.commit()
            connection.close()
            run_dir, _ = self.run_fixture(Path(tmp) / "out", db_path)
            record = json.loads(
                (run_dir / "shadow-records.jsonl").read_text().splitlines()[0]
            )
            clock = record["clocks"]["source_modified"]
            self.assertEqual(clock["status"], "PRESENT")
            self.assertEqual(clock["value"], "2026-03-03T00:00:00Z")
            self.assertEqual(clock["origin"], "permits")

    def test_blank_supporting_source_url_falls_back_to_permits_cap_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "permits.sqlite"
            connection = sqlite3.connect(db_path)
            connection.execute(
                "CREATE TABLE permits (permit_number TEXT, report_source TEXT NOT NULL, "
                "source_url TEXT, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO permits VALUES ('ENG-CR-1', 'opened_permits', "
                "'https://aca-prod.accela.com/FTL/Cap/CapDetail.aspx?"
                "capID1=FALL1&capID2=FALL2&capID3=FALL3', "
                "'2026-08-01T00:00:00Z', '2026-08-15T00:00:00Z')"
            )
            connection.execute(
                "CREATE TABLE accela_details (permit_number TEXT, source_url TEXT)"
            )
            connection.execute(
                "INSERT INTO accela_details VALUES ('ENG-CR-1', 'not-a-cap-url')"
            )
            connection.commit()
            connection.close()
            run_dir, _ = self.run_fixture(Path(tmp) / "out", db_path)
            record = json.loads(
                (run_dir / "shadow-records.jsonl").read_text().splitlines()[0]
            )
            self.assertEqual(record["cap_id"]["status"], "PRESENT")
            self.assertEqual(record["cap_id"]["value"]["capID1"], "FALL1")


if __name__ == "__main__":
    unittest.main()
