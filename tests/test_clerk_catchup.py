import importlib.util
import os
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("BROWARD_SFTP_USER", "test-user")
os.environ.setdefault("BROWARD_SFTP_PASS", "test-password")
SPEC = importlib.util.spec_from_file_location(
    "clerk_catchup", ROOT / "ops" / "droplet" / "clerk_catchup.py"
)
clerk_catchup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(clerk_catchup)


class ClerkCatchupLedgerTests(unittest.TestCase):
    def test_existing_business_dates_reads_every_postgrest_page(self):
        first = [{"business_date": f"2024-01-{(index % 28) + 1:02d}"} for index in range(1000)]
        second = [
            {"business_date": "2026-08-10"},
            {"business_date": "2026-08-11"},
        ]

        with mock.patch.object(clerk_catchup, "rest", side_effect=[first, second]) as rest:
            dates = clerk_catchup.existing_business_dates(page_size=1000)

        self.assertIn("2026-08-10", dates)
        self.assertIn("2026-08-11", dates)
        self.assertEqual(rest.call_count, 2)
        self.assertIn("offset=0", rest.call_args_list[0].args[0])
        self.assertIn("offset=1000", rest.call_args_list[1].args[0])

    def test_default_capacity_catches_up_more_than_one_week(self):
        self.assertEqual(clerk_catchup.MAX_DATES, 10)


if __name__ == "__main__":
    unittest.main()
