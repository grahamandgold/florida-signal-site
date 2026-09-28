"""Regressions for choosing the accepted session without fresh window churn."""
import importlib.util
import pathlib
import json
import subprocess
import sys
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


class SessionDiagnosticTests(unittest.TestCase):
    KEYS = {'stage', 'chrome_running', 'window_count', 'tab_count', 'official_prefix_count',
            'parser_valid_id_count', 'candidate_count', 'selection'}

    def cli(self, inventory, running=True, windows=1, tabs=1, official=1):
        result = subprocess.run([sys.executable, str(ROOT/'ops/mac/acclaim_browser_session.py'),
                                 inventory, '--diagnostic', str(running).lower(),
                                 str(windows), str(tabs), str(official)],
                                capture_output=True, text=True, check=True)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 2)
        report = json.loads(lines[1])
        self.assertEqual(set(report), self.KEYS)
        self.assertEqual(result.stderr, '')
        return lines[0], report

    def test_false_running_and_empty_inventory_have_distinct_diagnostics_same_hold(self):
        absent, no_chrome = self.cli('', False, 0, 0, 0)
        empty, no_match = self.cli('', True, 2, 5, 0)
        self.assertEqual(absent, 'MISSING|0|0'); self.assertEqual(empty, absent)
        self.assertEqual(no_chrome['stage'], 'chrome_running_check')
        self.assertFalse(no_chrome['chrome_running'])
        self.assertEqual(no_match['stage'], 'inventory_selection')
        self.assertTrue(no_match['chrome_running'])
        self.assertEqual(no_match['window_count'], 2); self.assertEqual(no_match['tab_count'], 5)
        self.assertEqual(no_match['candidate_count'], 0)

    def test_exact_route_and_large_decimal_ids_remain_ready(self):
        selection, report = self.cli('1420000001\t1420000002\t'+BASE+'search/SearchTypeRecordDate\n')
        self.assertEqual(selection, 'READY|1420000001|1420000002')
        self.assertEqual(report['selection'], 'READY')
        self.assertEqual(report['parser_valid_id_count'], 1)
        self.assertEqual(report['candidate_count'], 1)

    def test_malformed_rows_are_counted_without_making_them_eligible(self):
        inventory = 'bad\t72\t'+BASE+'search/SearchTypeRecordDate\n'
        inventory += '8\t73\t'+BASE+'unrelated\ntruncated\n'
        selection, report = self.cli(inventory, tabs=3, official=3)
        self.assertEqual(selection, 'MISSING|0|0')
        self.assertEqual(report['parser_valid_id_count'], 1)
        self.assertEqual(report['candidate_count'], 0)
        self.assertEqual(report['official_prefix_count'], 3)

    def test_ambiguous_search_and_terms_are_not_reclassified(self):
        inventory = '9\t72\t'+BASE+'search/SearchTypeRecordDate\n10\t73\t'+BASE+'Disclaimer\n'
        selection, report = self.cli(inventory, windows=2, tabs=2, official=2)
        self.assertEqual(selection, 'AMBIGUOUS|0|0')
        self.assertEqual(report['parser_valid_id_count'], 2)
        self.assertEqual(report['candidate_count'], 2)
        selection, report = self.cli('9\t72\t'+BASE+'Disclaimer\n')
        self.assertEqual(selection, 'TERMS|9|72'); self.assertEqual(report['selection'], 'TERMS')

    def test_only_allowlisted_values_reach_diagnostic(self):
        inventory = '918273\t817263\t'+BASE+'search/SearchTypeRecordDate?token=DO_NOT_LOG&name=PRIVATE_FIXTURE\n'
        _, report = self.cli(inventory)
        text = json.dumps(report)
        for value in ('918273', '817263', 'broward.org', 'token', 'DO_NOT_LOG', 'PRIVATE_FIXTURE'):
            self.assertNotIn(value, text)
        self.assertTrue(all(type(v) is int and v >= 0 for k, v in report.items() if k.endswith('_count')))

    def test_legacy_cli_stdout_is_unchanged(self):
        result = subprocess.run([sys.executable, str(ROOT/'ops/mac/acclaim_browser_session.py'),
                                 '9\t72\t'+BASE+'search/SearchTypeRecordDate\n'],
                                capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout, 'READY|9|72\n'); self.assertEqual(result.stderr, '')

    def test_applescript_logs_both_branches_before_return_without_changing_reason(self):
        source = (ROOT/'ops/mac/acclaim_harvest.applescript').read_text()
        self.assertIn('\\"stage\\":\\"chrome_running_check\\",\\"chrome_running\\":false', source)
        self.assertIn('" --diagnostic true " & windowCount & " " & tabCount & " " & officialPrefixCount', source)
        self.assertIn('log ("ACCLAIM_SESSION_DIAGNOSTIC " & paragraph 2 of selectionOutput)', source)
        self.assertEqual(source.count('return "SOURCE_WAIT|0|0|accepted_search_session_missing"'), 2)
        pull = (ROOT/'ops/mac/acclaim_pull.sh').read_text()
        self.assertIn('2>>"$LOG" <<\'PY\'', pull)
        self.assertIn('print(result.stderr, file=sys.stderr, end="")', pull)

if __name__ == '__main__': unittest.main()
