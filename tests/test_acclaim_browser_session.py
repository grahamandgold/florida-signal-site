"""Regressions for choosing the accepted session without fresh window churn."""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('session', ROOT/'ops/mac/acclaim_browser_session.py')
session = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(session)
BASE = 'https://officialrecords.broward.org/AcclaimWeb/'

class SessionSelectionTests(unittest.TestCase):
    def test_existing_accepted_search_is_reused(self):
        self.assertEqual(session.select_session('9\t72\t'+BASE+'search/SearchTypeRecordDate\n'), ('READY',9,72))
    def test_missing_session_never_creates_a_window(self):
        self.assertEqual(session.select_session(''), ('MISSING',0,0))
    def test_ambiguous_sessions_fail_closed(self):
        lines='9\t72\t'+BASE+'search/SearchTypeRecordDate\n10\t73\t'+BASE+'search/SearchTypeRecordDate\n'
        self.assertEqual(session.select_session(lines), ('AMBIGUOUS',0,0))
    def test_terms_session_remains_a_gate(self):
        self.assertEqual(session.select_session('9\t72\t'+BASE+'Disclaimer?returnUrl=/search\n'), ('TERMS',9,72))
    def test_unrelated_or_spoofed_hosts_do_not_match(self):
        for url in [BASE.replace('https:', 'http:'), BASE.replace('.org/','.org.evil/'), BASE.replace('.org/','.org:444/'), 'https://officialrecords.broward.org.evil/AcclaimWeb/search/SearchTypeRecordDate']:
            self.assertEqual(session.select_session('9\t72\t'+url), ('MISSING',0,0))
    def test_terms_plus_search_is_ambiguous_not_silent_bypass(self):
        lines='9\t72\t'+BASE+'search/SearchTypeRecordDate\n10\t73\t'+BASE+'Disclaimer\n'
        self.assertEqual(session.select_session(lines), ('AMBIGUOUS',0,0))
    def test_rejects_non_numeric_browser_ids(self):
        self.assertEqual(session.select_session('nine\t72\t'+BASE+'search/SearchTypeRecordDate'),('MISSING',0,0))

if __name__ == '__main__': unittest.main()
