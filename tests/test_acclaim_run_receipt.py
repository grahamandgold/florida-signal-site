import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "acclaim_run_receipt", ROOT / "ops" / "mac" / "acclaim_run_receipt.py"
)
receipt_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(receipt_module)


class AcclaimRunReceiptTests(unittest.TestCase):
    def outcomes(self):
        return [
            {
                "target_date": "2026-08-28",
                "status": "ok",
                "pages": 5,
                "rows_observed": 2463,
                "rows_new": 0,
                "observed_at": "2026-08-30T20:09:24Z",
                "reason": None,
            },
            {
                "target_date": "2026-08-29",
                "status": "empty",
                "pages": 0,
                "rows_observed": 0,
                "rows_new": 0,
                "observed_at": "2026-08-30T20:09:29Z",
                "reason": None,
            },
            {
                "target_date": "2026-08-30",
                "status": "source_wait",
                "pages": 0,
                "rows_observed": 0,
                "rows_new": 0,
                "observed_at": "2026-08-30T20:09:34Z",
                "reason": "empty_unverified_date",
            },
        ]

    def test_mixed_run_keeps_event_attempt_and_system_clocks_separate(self):
        receipt = receipt_module.build_receipt(
            run_id="0dff405a-2bb4-4df1-965e-854453e58925",
            started_at="2026-08-30T20:09:00Z",
            completed_at="2026-08-30T20:09:40Z",
            verified_through="2026-08-25",
            outcomes=self.outcomes(),
            event_through="2026-08-28",
        )
        self.assertEqual(receipt["status"], "source_wait")
        self.assertEqual(receipt["attempted_from"], "2026-08-28")
        self.assertEqual(receipt["attempted_through"], "2026-08-30")
        self.assertEqual(receipt["event_through"], "2026-08-28")
        self.assertEqual(receipt["observed_at"], "2026-08-30T20:09:34+00:00")
        self.assertEqual(receipt["dates_attempted"], 3)
        self.assertEqual(receipt["rows_observed"], 2463)
        self.assertEqual(receipt["rows_new"], 0)

    def test_outcome_timestamp_must_fall_inside_run_window(self):
        outcomes = self.outcomes()
        outcomes[-1]["observed_at"] = "2026-08-30T20:10:00Z"
        with self.assertRaisesRegex(ValueError, "outside the run window"):
            receipt_module.build_receipt(
                run_id="0dff405a-2bb4-4df1-965e-854453e58925",
                started_at="2026-08-30T20:09:00Z",
                completed_at="2026-08-30T20:09:40Z",
                verified_through="2026-08-25",
                outcomes=outcomes,
                event_through="2026-08-28",
            )

    def test_empty_run_is_explicit_and_has_zero_counts(self):
        receipt = receipt_module.build_receipt(
            run_id="0dff405a-2bb4-4df1-965e-854453e58925",
            started_at="2026-08-30T23:00:00Z",
            completed_at="2026-08-30T23:00:10Z",
            verified_through="2026-08-25",
            outcomes=[{
                "target_date": "2026-08-30",
                "status": "empty",
                "pages": 0,
                "rows_observed": 0,
                "rows_new": 0,
                "observed_at": "2026-08-30T23:00:09Z",
            }],
            event_through="2026-08-28",
        )
        self.assertEqual(receipt["status"], "empty")
        self.assertEqual(receipt["rows_observed"], 0)
        self.assertEqual(receipt["rows_new"], 0)

    def test_local_outbox_precedes_remote_write_and_replays(self):
        receipt = receipt_module.build_receipt(
            run_id="0dff405a-2bb4-4df1-965e-854453e58925",
            started_at="2026-08-30T23:00:00Z",
            completed_at="2026-08-30T23:00:10Z",
            verified_through="2026-08-25",
            outcomes=[],
            event_through="2026-08-28",
            forced_status="ok",
            forced_reason="no_targets",
        )
        with tempfile.TemporaryDirectory() as directory:
            outbox = Path(directory)
            pending = receipt_module.persist_pending(receipt, outbox)
            self.assertTrue(pending.exists())
            posted = []
            sent, failed = receipt_module.flush_outbox(
                outbox, post=lambda value: posted.append(value)
            )
            self.assertEqual((sent, failed), (1, 0))
            self.assertEqual(posted, [receipt])
            self.assertFalse(pending.exists())
            self.assertTrue((outbox / (receipt["run_id"] + ".sent.json")).exists())

    def test_tampered_pending_receipt_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            outbox = Path(directory)
            pending = outbox / "bad.pending.json"
            pending.write_text(
                json.dumps({"run_id": "not-a-receipt", "secret": "must-not-send"}),
                encoding="utf-8",
            )
            posted = []
            sent, failed = receipt_module.flush_outbox(
                outbox, post=lambda value: posted.append(
                    receipt_module.validate_receipt(value)
                )
            )
            self.assertEqual((sent, failed), (0, 1))
            self.assertEqual(posted, [])
            self.assertTrue(pending.exists())

    def test_post_is_idempotent_and_uses_no_secret_in_payload(self):
        receipt = receipt_module.build_receipt(
            run_id="0dff405a-2bb4-4df1-965e-854453e58925",
            started_at="2026-08-30T23:00:00Z",
            completed_at="2026-08-30T23:00:10Z",
            verified_through="2026-08-25",
            outcomes=[],
            event_through="2026-08-28",
            forced_status="ok",
        )

        class Response:
            status = 201

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        captured = {}

        def opener(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return Response()

        environment = {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "test-secret",
        }
        with mock.patch.dict(os.environ, environment, clear=True):
            receipt_module.post_receipt(receipt, urlopen=opener)
        request = captured["request"]
        self.assertIn("on_conflict=run_id", request.full_url)
        self.assertEqual(request.headers["Prefer"], "resolution=ignore-duplicates,return=minimal")
        self.assertNotIn(b"test-secret", request.data)
        self.assertEqual(captured["timeout"], 60)

    def test_legacy_state_derives_last_nonempty_event_date(self):
        state = {
            "dates": {
                "2026-08-28": {"status": "done", "found": 2463},
                "2026-08-29": {"status": "done", "found": 0},
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text(json.dumps(state), encoding="utf-8")
            self.assertEqual(
                receipt_module.event_through_from_state(path), "2026-08-28"
            )


class AcclaimRunMigrationContractTests(unittest.TestCase):
    def test_migration_is_receipt_only_and_unscheduled(self):
        sql = (
            ROOT
            / "supabase"
            / "migrations"
            / "20260830233000_acclaim_run_receipts.sql"
        ).read_text(encoding="utf-8").lower()
        self.assertIn("create table if not exists public.broward_clerk_preliminary_run", sql)
        self.assertIn("'ok', 'empty', 'source_wait', 'failed'", sql)
        self.assertIn("rows_new <= rows_observed", sql)
        self.assertIn("started_at <= observed_at", sql)
        self.assertIn("observed_at <= completed_at", sql)
        self.assertIn("grant select, insert", sql)
        self.assertNotIn("cron.schedule", sql)
        self.assertNotIn("create trigger", sql)

    def test_data_room_uses_receipt_clock_not_row_fetch_clock(self):
        html = (ROOT / "cms" / "data.html").read_text(encoding="utf-8")
        preliminary_block = html.split(
            '{ name: "Preliminary Clerk recordings"', 1
        )[1].split("},", 1)[0]
        self.assertIn('receiptTable: "broward_clerk_preliminary_run"', preliminary_block)
        self.assertIn('collected: null', preliminary_block)
        self.assertNotIn('collected: "fetched_at"', preliminary_block)
        self.assertIn('"latest collector run"', html)
        self.assertIn('f.receiptTable ? dateTimeish(collectedVal)', html)
        self.assertIn('businessCalendarAge(eventVal)', html)
        self.assertIn('PRELIMINARY · CURRENT / RETRYING', html)


if __name__ == "__main__":
    unittest.main()
