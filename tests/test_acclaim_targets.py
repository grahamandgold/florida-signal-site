import datetime as dt
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


PATH = Path(__file__).resolve().parents[1] / "ops" / "mac" / "acclaim_targets.py"
SPEC = importlib.util.spec_from_file_location("acclaim_targets", PATH)
targets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(targets)


class AcclaimTargetTests(unittest.TestCase):
    def test_before_noon_excludes_current_day(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            result = targets.candidate_dates(
                dt.date(2026, 7, 19),
                8,
                state,
                now=dt.datetime(2026, 7, 21, 0, 30),
            )
        self.assertEqual(result, [dt.date(2026, 7, 20)])

    def test_after_noon_includes_current_day_and_skips_done(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            state.write_text(
                json.dumps({"dates": {"2026-07-20": {"status": "done"}}}),
                encoding="utf-8",
            )
            result = targets.candidate_dates(
                dt.date(2026, 7, 19),
                8,
                state,
                now=dt.datetime(2026, 7, 21, 19, 0),
            )
        self.assertEqual(result, [dt.date(2026, 7, 21)])

    def test_cap_is_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            result = targets.candidate_dates(
                dt.date(2026, 7, 1),
                2,
                Path(directory) / "state.json",
                now=dt.datetime(2026, 7, 21, 19, 0),
            )
        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
