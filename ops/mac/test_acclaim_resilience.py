#!/usr/bin/env python3

import datetime as dt
import importlib.util
import json
import pathlib
import plistlib
import tempfile
import unittest
import urllib.error


HERE = pathlib.Path(__file__).parent


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verified = load_module("acclaim_verified_max")
targets = load_module("acclaim_targets")


class VerifiedMaxTests(unittest.TestCase):
    def test_cached_floor_is_retained_when_remote_query_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            state = pathlib.Path(directory) / "state.json"
            state.write_text(
                json.dumps({"verified_max_at_last_run": "2026-07-22"}),
                encoding="utf-8",
            )
            original = verified.fetch_verified_max
            verified.fetch_verified_max = lambda: (_ for _ in ()).throw(
                RuntimeError("temporary outage")
            )
            try:
                self.assertEqual(
                    verified.resolve_verified_max(str(state)),
                    ("2026-07-22", True),
                )
            finally:
                verified.fetch_verified_max = original

    def test_remote_query_retries_and_returns_valid_date(self):
        calls = []

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'[{"business_date":"2026-07-23"}]'

        def opener(_request, timeout):
            calls.append(timeout)
            if len(calls) < 3:
                raise urllib.error.URLError("temporary")
            return Response()

        self.assertEqual(
            verified.fetch_verified_max(
                urlopen=opener, attempts=3, sleep=lambda _seconds: None
            ),
            "2026-07-23",
        )
        self.assertEqual(len(calls), 3)


class TargetTests(unittest.TestCase):
    def test_before_noon_does_not_probe_a_forming_current_day(self):
        with tempfile.TemporaryDirectory() as directory:
            state = pathlib.Path(directory) / "state.json"
            now = dt.datetime(2026, 7, 24, 9, 0)
            self.assertEqual(
                targets.candidate_dates(
                    dt.date(2026, 7, 22), 8, str(state), now=now
                ),
                [dt.date(2026, 7, 23)],
            )

    def test_completed_current_day_is_rechecked_after_noon(self):
        with tempfile.TemporaryDirectory() as directory:
            state = pathlib.Path(directory) / "state.json"
            state.write_text(
                json.dumps(
                    {
                        "dates": {
                            "2026-07-23": {"status": "done"},
                            "2026-07-24": {"status": "done"},
                        }
                    }
                ),
                encoding="utf-8",
            )
            now = dt.datetime(2026, 7, 24, 15, 0)
            self.assertEqual(
                targets.candidate_dates(
                    dt.date(2026, 7, 22), 8, str(state), now=now
                ),
                [dt.date(2026, 7, 24)],
            )

    def test_current_day_keeps_a_slot_during_long_catchup(self):
        with tempfile.TemporaryDirectory() as directory:
            state = pathlib.Path(directory) / "state.json"
            now = dt.datetime(2026, 7, 24, 15, 0)
            self.assertEqual(
                targets.candidate_dates(
                    dt.date(2026, 7, 15), 3, str(state), now=now
                ),
                [
                    dt.date(2026, 7, 16),
                    dt.date(2026, 7, 17),
                    dt.date(2026, 7, 24),
                ],
            )

    def test_completed_past_dates_remain_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            state = pathlib.Path(directory) / "state.json"
            state.write_text(
                json.dumps({"dates": {"2026-07-23": {"status": "done"}}}),
                encoding="utf-8",
            )
            now = dt.datetime(2026, 7, 24, 15, 0)
            self.assertEqual(
                targets.candidate_dates(
                    dt.date(2026, 7, 22), 8, str(state), now=now
                ),
                [dt.date(2026, 7, 24)],
            )


class LaunchAgentTests(unittest.TestCase):
    def test_hourly_and_login_recovery_are_enabled(self):
        with (HERE / "com.floridasignal.acclaim.plist").open("rb") as handle:
            config = plistlib.load(handle)
        self.assertEqual(config.get("StartInterval"), 3600)
        self.assertIs(config.get("RunAtLoad"), True)


if __name__ == "__main__":
    unittest.main()
