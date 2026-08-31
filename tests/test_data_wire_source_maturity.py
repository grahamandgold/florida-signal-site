import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_HTML = ROOT / "cms" / "data.html"


class DataWireSourceMaturityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = DATA_HTML.read_text(encoding="utf-8")

    def test_sfwmd_is_shadow_observed_but_still_not_connected(self):
        self.assertIn('status: "Shadow observed · not connected"', self.html)
        self.assertIn(
            "two manual observations each saved receipts for 1,100 official rows",
            self.html,
        )
        self.assertIn(
            "No natural timer, stage, database mirror or detector is connected",
            self.html,
        )
        self.assertNotIn("safest next collector", self.html)
        self.assertNotIn('status: "Next collector · JSON"', self.html)

    def test_open_desk_rechecks_receipts_every_ten_minutes(self):
        self.assertIn("auto-check every 10 minutes while open", self.html)
        self.assertIn("Date.now() - libraryCheckedAt > 600000", self.html)
        self.assertIn("checkLibraryConnections()", self.html)

    def test_source_probes_timeout_and_release_the_refresh_guard(self):
        self.assertIn("const SOURCE_REQUEST_TIMEOUT_MS = 12000", self.html)
        self.assertIn("controller.abort()", self.html)
        self.assertIn('error.name === "AbortError"', self.html)
        self.assertIn("timed out after 12 seconds", self.html)
        self.assertIn("finally {", self.html)
        self.assertIn("libraryChecking = false", self.html)


if __name__ == "__main__":
    unittest.main()
