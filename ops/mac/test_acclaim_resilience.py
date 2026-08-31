#!/usr/bin/env python3

import contextlib
import datetime as dt
import importlib.util
import io
import json
import pathlib
import plistlib
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock


HERE = pathlib.Path(__file__).parent


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verified = load_module("acclaim_verified_max")
targets = load_module("acclaim_targets")
empty_policy = load_module("acclaim_empty_policy")


def harvest_runner_source():
    script = (HERE / "acclaim_pull.sh").read_text(encoding="utf-8")
    marker = "<<'PY'\nimport subprocess, sys\n"
    start = script.index(marker) + len("<<'PY'\n")
    end = script.index("\nPY\n)", start)
    return script[start:end]


def run_harvest_runner(results):
    stdout = io.StringIO()
    stderr = io.StringIO()
    argv = ["-", "1200", "harvest.applescript", "8/30/2026", "/tmp/out", "40"]
    with (
        mock.patch.object(sys, "argv", argv),
        mock.patch("subprocess.run", side_effect=results) as runner,
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        exec(compile(harvest_runner_source(), "acclaim_pull.sh:inline", "exec"), {})
    return stdout.getvalue().strip(), stderr.getvalue(), runner.call_count


class HarvestRetryTests(unittest.TestCase):
    def result(self, stdout, *, returncode=0, stderr=""):
        return subprocess.CompletedProcess(
            ["/usr/bin/osascript"], returncode, stdout=stdout, stderr=stderr
        )

    def test_transient_missing_result_state_retries_once(self):
        stdout, stderr, calls = run_harvest_runner(
            [
                self.result("INCOMPLETE|0|0|timeout_no_result_state\n"),
                self.result("EMPTY|0|0\n"),
            ]
        )

        self.assertEqual(stdout, "EMPTY|0|0")
        self.assertIn("retrying once", stderr)
        self.assertEqual(calls, 2)

    def test_second_missing_result_state_remains_truthful_failure(self):
        stdout, _stderr, calls = run_harvest_runner(
            [
                self.result("INCOMPLETE|0|0|timeout_no_result_state\n"),
                self.result("INCOMPLETE|0|0|timeout_no_result_state\n"),
            ]
        )

        self.assertEqual(
            stdout, "INCOMPLETE|0|0|timeout_no_result_state_after_retry"
        )
        self.assertEqual(calls, 2)

    def test_other_terminal_state_is_not_retried(self):
        stdout, _stderr, calls = run_harvest_runner(
            [self.result("SOURCE_WAIT|0|0|terms_acceptance_required\n")]
        )

        self.assertEqual(stdout, "SOURCE_WAIT|0|0|terms_acceptance_required")
        self.assertEqual(calls, 1)


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


class EmptyPolicyTests(unittest.TestCase):
    def test_unverified_past_weekday_remains_retryable(self):
        self.assertEqual(
            empty_policy.classify_empty(
                dt.date(2026, 8, 13),
                dt.date(2026, 8, 11),
                today=dt.date(2026, 8, 15),
            ),
            "retry",
        )

    def test_past_weekend_can_close_as_zero(self):
        self.assertEqual(
            empty_policy.classify_empty(
                dt.date(2026, 8, 9),
                dt.date(2026, 8, 7),
                today=dt.date(2026, 8, 15),
            ),
            "done",
        )

    def test_current_day_remains_retryable(self):
        self.assertEqual(
            empty_policy.classify_empty(
                dt.date(2026, 8, 15),
                dt.date(2026, 8, 11),
                today=dt.date(2026, 8, 15),
            ),
            "retry",
        )

    def test_authoritatively_covered_weekday_can_close(self):
        self.assertEqual(
            empty_policy.classify_empty(
                dt.date(2026, 8, 11),
                dt.date(2026, 8, 11),
                today=dt.date(2026, 8, 15),
            ),
            "done",
        )

class LaunchAgentTests(unittest.TestCase):
    def test_hourly_and_login_recovery_are_enabled(self):
        with (HERE / "com.floridasignal.acclaim.plist").open("rb") as handle:
            config = plistlib.load(handle)
        self.assertEqual(config.get("StartInterval"), 3600)
        self.assertIs(config.get("RunAtLoad"), True)


if __name__ == "__main__":
    unittest.main()
