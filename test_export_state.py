# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Is the scanner up to date with the saved configuration? (v0.1.20)"""
import os
import tempfile
import unittest
from pathlib import Path

import export_state as es


class ExportStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.config = self.tmp / 'My SDS100'
        lists = self.config / 'BCDx36HP' / 'favorites_lists'
        lists.mkdir(parents=True)
        (lists / 'f_list.cfg').write_bytes(b'F-List\tGreenville\r\n')
        (lists / 'f_000001.hpd').write_bytes(b'TargetModel\tBCDx36HP\r\n')
        self.state = self.tmp / 'export-state.json'

    def test_unknown_then_exported_then_changed(self):
        self.assertEqual(es.state(self.config, self.state)['state'], 'unknown')
        self.assertIn('Not known', es.describe(es.state(self.config, self.state)))
        self.assertTrue(es.record(self.config, 'exported', self.state))
        info = es.state(self.config, self.state)
        self.assertEqual((info['state'], info['how']), ('exported', 'exported'))
        self.assertTrue(es.describe(info).startswith('Scanner is up to date (exported'))
        (self.config / 'BCDx36HP' / 'favorites_lists' / 'f_000001.hpd').write_bytes(b'changed')
        info = es.state(self.config, self.state)
        self.assertEqual(info['state'], 'changed')
        self.assertIn('not exported to the scanner yet', es.describe(info))
        self.assertTrue(info['saved'])

    def test_read_from_scanner_counts_as_matching_and_other_files_dont_matter(self):
        es.record(self.config, 'read', self.state)
        (self.config / 'notes.txt').write_text('x')
        info = es.state(self.config, self.state)
        self.assertEqual((info['state'], info['how']), ('exported', 'read'))
        self.assertIn('read from the scanner', es.describe(info))

    def test_a_deleted_list_is_a_change(self):
        es.record(self.config, 'exported', self.state)
        os.remove(self.config / 'BCDx36HP' / 'favorites_lists' / 'f_000001.hpd')
        self.assertEqual(es.state(self.config, self.state)['state'], 'changed')

    def test_a_broken_state_file_is_unknown(self):
        self.state.write_text('{not json')
        self.assertEqual(es.state(self.config, self.state)['state'], 'unknown')
        self.assertTrue(es.record(self.config, 'read', self.state))


if __name__ == '__main__':
    unittest.main()
