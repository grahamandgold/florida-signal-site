from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DataWireAcclaimReceiptTests(unittest.TestCase):
    def test_preliminary_clerk_uses_run_receipt_not_row_fetch_clock(self):
        html = (ROOT / "cms" / "data.html").read_text(encoding="utf-8")
        preliminary_block = html.split(
            '{ name: "Preliminary Clerk recordings"', 1
        )[1].split("},", 1)[0]

        self.assertIn(
            'receiptTable: "broward_clerk_preliminary_run"', preliminary_block
        )
        self.assertIn("collected: null", preliminary_block)
        self.assertNotIn('collected: "fetched_at"', preliminary_block)
        self.assertIn('"terminal health receipt"', html)
        self.assertIn("receipt.completed_at || receipt.observed_at", html)
        self.assertIn("collectedVal ? dateTimeish(collectedVal)", html)
        self.assertIn("businessCalendarAge(eventVal)", html)
        self.assertIn("formatReceiptReason(receipt.reason)", html)
        self.assertIn("PRELIMINARY · CURRENT / RETRYING", html)
        self.assertNotIn("last successful collection", html)
        self.assertIn('collectedLabel: "latest row fetched"', html)
        self.assertIn("rowOnlyHealthUnknown", html)
        self.assertIn("connected · ${refresh} · health unknown", html)

    def test_newsroom_surfaces_disambiguated_source_clocks(self):
        home = (ROOT / "cms" / "home.html").read_text(encoding="utf-8")
        shell = (ROOT / "cms" / "desk-shell.js").read_text(encoding="utf-8")
        for source in (home, shell):
            self.assertIn("Event through", source)
            self.assertIn("Fetched ", source)
            self.assertIn("Health receipt ", source)
            self.assertNotIn("<br>System ", source)


if __name__ == "__main__":
    unittest.main()
