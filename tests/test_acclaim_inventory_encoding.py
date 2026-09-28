"""Compile actual inventory syntax; never execute the harvester or send app events."""
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]

@unittest.skipUnless(sys.platform=='darwin' and shutil.which('osacompile'), 'AppleScript compiler needs macOS')
class InventoryEncoding(unittest.TestCase):
    def test_compiled_inventory_concatenation_contains_no_chrome_tab_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            compiled=pathlib.Path(tmp)/'harvester.scpt'
            subprocess.run(['osacompile','-o',str(compiled),str(ROOT/'ops/mac/acclaim_harvest.applescript')],check=True,capture_output=True,text=True)
            script=subprocess.check_output(['osadecompile',str(compiled)],text=True)
        inventory=next(line for line in script.splitlines() if 'set inventory to inventory &' in line)
        source=(ROOT/'ops/mac/acclaim_harvest.applescript').read_text()
        declarations=[line.strip() for line in source.splitlines() if ' to character id 9' in line]
        # The only executed script is an extracted expression over local record literals.
        # using terms imports the same lexical dictionary without targeting an application.
        fixture='\n'.join(declarations+[
            'using terms from application "Google Chrome"',
            'set browserWindow to {id:"1420000001"}',
            'set browserTab to {id:"1420000002"}',
            'set tabURL to "https://officialrecords.broward.org/AcclaimWeb/search/SearchTypeRecordDate"',
            'set inventory to ""',inventory.strip(),'return inventory','end using terms from'])
        completed=subprocess.run(['osascript','-'],input=fixture,capture_output=True,text=True)
        self.assertEqual(completed.returncode,0,completed.stderr+'\n'+fixture)
        result=completed.stdout
        self.assertEqual(result.strip(),'1420000001\t1420000002\thttps://officialrecords.broward.org/AcclaimWeb/search/SearchTypeRecordDate')
