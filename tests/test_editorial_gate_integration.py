"""Exercise the existing local CMS/public adapter with disposable fixture data only."""

import importlib.util
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cms_gate_fixture", ROOT / "cms" / "server.py")
cms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cms)


class EditorialGateIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "fixture.sqlite"
        self.db_patch = mock.patch.object(cms, "DB_PATH", self.db)
        self.token_patch = mock.patch.object(cms, "ADMIN_TOKEN", "local-integration-fixture-token")
        self.db_patch.start()
        self.token_patch.start()
        cms.init_db()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), cms.Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = "http://127.0.0.1:" + str(self.httpd.server_port)

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.token_patch.stop()
        self.db_patch.stop()
        self.temp.cleanup()

    def request(self, route, body=None, *, authorized=True):
        headers = {"Content-Type": "application/json"}
        if authorized:
            headers["Authorization"] = "Bearer local-integration-fixture-token"
        request = urllib.request.Request(self.base + route, headers=headers,
            data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def fixture(self, **changes):
        return {
            "market": "broward", "county": "broward-county", "city": "fort-lauderdale",
            "headline": "Local integration fixture — never publish", "dek": "Fixture summary",
            "body": "Disposable test text, not real reporting.", "event_date": "2026-09-27",
            "source_title": "Official fixture record", "source_url": "https://example.test/source",
            "topic_tags": ["topic:development"], "geography_tags": ["city:fort-lauderdale"],
            "claims_status": "passed", "tags_status": "passed", "verification_status": "verified",
            "validator_status": "passed", "current_trigger": "Dated fixture record",
            "project_identity_basis": "One source record; no inferred join", "editor_name": "Fixture editor",
            "claim_slots": [{"claim": "Fixture claim", "source_url": "https://example.test/source"}],
            **changes,
        }

    def test_draft_requires_explicit_authorized_approval_and_hold_removes_it(self):
        code, draft = self.request("/api/admin/stories", self.fixture(status="approved"))
        self.assertEqual(code, 201)
        self.assertEqual(draft["status"], "draft")
        feed = "/api/wire/packets?market=broward&city=fort-lauderdale"
        self.assertEqual(self.request(feed, authorized=False)[1]["packets"], [])
        approval = "/api/admin/stories/" + draft["id"] + "/approve"
        self.assertEqual(self.request(approval, {}, authorized=False)[0], 401)
        self.assertEqual(self.request(approval, {})[0], 200)
        packets = self.request(feed, authorized=False)[1]["packets"]
        self.assertEqual(len(packets), 1)
        self.assertEqual(packets[0]["id"], draft["id"])
        self.assertNotIn("editor_note", packets[0])
        self.assertEqual(self.request("/api/admin/stories/" + draft["id"] + "/hold", {})[0], 200)
        self.assertEqual(self.request(feed, authorized=False)[1]["packets"], [])
        with sqlite3.connect(self.db) as db:
            actions = [r[0] for r in db.execute("select action from audit_log order by id")]
        self.assertEqual(actions, ["draft_created", "approve", "hold"])

    def test_unresolved_or_unsourced_drafts_stay_private(self):
        for changes, block in [({"unresolved_issues": "Ownership contradiction"}, "Unresolved issues"),
                               ({"source_url": "", "claim_slots": []}, "source")]:
            changes["slug"] = "held" if "unresolved_issues" in changes else "unsourced"
            code, draft = self.request("/api/admin/stories", self.fixture(**changes))
            self.assertEqual(code, 201)
            code, denied = self.request("/api/admin/stories/" + draft["id"] + "/approve", {})
            self.assertEqual(code, 422)
            self.assertIn(block, " ".join(denied["blocks"]))
        self.assertEqual(self.request("/api/wire/packets", authorized=False)[1]["packets"], [])


if __name__ == "__main__":
    unittest.main()
