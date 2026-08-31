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
        self.assertIn('"latest collector run"', html)
        self.assertIn("f.receiptTable ? dateTimeish(collectedVal)", html)
        self.assertIn("businessCalendarAge(eventVal)", html)
        self.assertIn("PRELIMINARY · CURRENT / RETRYING", html)


if __name__ == "__main__":
    unittest.main()
