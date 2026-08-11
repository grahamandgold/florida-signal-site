import datetime as dt
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


OPS_PATH = Path(__file__).resolve().parents[1] / "ops" / "mac"
sys.path.insert(0, str(OPS_PATH))
SPEC = importlib.util.spec_from_file_location("acclaim_state", OPS_PATH / "acclaim_state.py")
state_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(state_module)


class AcclaimStateTests(unittest.TestCase):
    def test_before_noon_does_not_report_forming_day_as_backlog(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "state.json"
            state_file.write_text(
                json.dumps(
                    {
                        "dates": {
                            "2026-08-06": {"status": "done"},
                            "2026-08-07": {"status": "done"},
                            "2026-08-08": {"status": "done"},
                            "2026-08-09": {"status": "done"},
                            "2026-08-10": {"status": "done"},
                        }
                    }
                ),
                encoding="utf-8",
            )
            state = state_module.update_state(
                state_file,
                "2026-08-05",
                "done",
                5,
                2446,
                1196,
                "2026-08-05",
                2446,
                now=dt.datetime(2026, 8, 11, 4, 56, tzinfo=dt.timezone.utc),
            )

        self.assertEqual(state["backlog_remaining"], [])
        self.assertEqual(state["last_completed_date"], "2026-08-10")
        self.assertEqual(state["dates"]["2026-08-05"]["found"], 2446)


if __name__ == "__main__":
    unittest.main()
