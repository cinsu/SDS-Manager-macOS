# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Avoids made on the scanner are offered before Export to Scanner (v0.1.21), on a real SDS100 list."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import export_state
import scanner_avoids as sa
from test_favorites_clipboard import FIX

LIST = 'BCDx36HP/favorites_lists/f_000001.hpd'


class ScannerAvoidTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.library = self.tmp / 'scanner-configurations'
        self.config = self.library / 'Mine'
        (self.config / 'BCDx36HP' / 'favorites_lists').mkdir(parents=True)
        shutil.copy(FIX / 'real_sds100_f_000001.hpd', self.config / LIST)
        raw = (self.config / LIST).read_bytes()
        import hashlib
        (self.config / 'configuration.json').write_text(json.dumps({
            'format': 'sds100-configuration-snapshot-v1', 'name': 'Mine',
            'files': {LIST: {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}}}))
        self.scanner = self.tmp / 'card' / 'BCDx36HP'
        (self.scanner / 'favorites_lists').mkdir(parents=True)
        shutil.copy(self.config / LIST, self.scanner / 'favorites_lists' / 'f_000001.hpd')
        self.state = self.tmp / 'export-state.json'
        self.patch = patch('scanner_configurations.library_path', return_value=self.library)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def first_tgid(self):
        return next(k for k in sa.avoid_map((self.config / LIST).read_bytes()) if '/ TGID:' in k)

    def test_lines_are_found_by_place_and_line_endings_kept(self):
        found = sa.avoid_map((self.config / LIST).read_bytes())
        self.assertIn('Trunk:Palmetto 800', found)
        self.assertTrue(any('/ C-Freq:' in k for k in found))
        raw = (self.config / LIST).read_bytes()
        number, value, _label = found['Trunk:Palmetto 800']
        changed = sa.new_bytes(raw, {number: 'On'})
        self.assertEqual(changed.count(b'\r\n'), raw.count(b'\r\n'))
        self.assertEqual(value, 'Off')
        self.assertEqual(len(changed), len(raw) - 1)                 # Off → On
        self.assertEqual(sa.avoid_map(changed)['Trunk:Palmetto 800'][1], 'On')

    def test_a_scanner_avoid_is_offered_and_kept(self):
        export_state.record(self.config, 'exported', self.state)
        key = self.first_tgid()
        number = sa.avoid_map((self.scanner / 'favorites_lists' / 'f_000001.hpd').read_bytes())[key][0]
        path = self.scanner / 'favorites_lists' / 'f_000001.hpd'
        path.write_bytes(sa.new_bytes(path.read_bytes(), {number: 'On'}))
        found = sa.differences(self.config, self.scanner, export_state.matched_avoids(self.config, self.state))
        self.assertEqual([(f['key'], f['scanner'], f['configuration'], f['made_on']) for f in found],
                         [(key, 'On', 'Off', 'scanner')])
        self.assertIn('scanner avoided, configuration not avoided (changed on the scanner)', sa.describe(found[0]))
        self.assertTrue(sa.describe(found[0]).startswith('f_000001.hpd: Talkgroup Palmetto 800 › '))
        self.assertEqual(sa.keep_scanner_avoids(self.config, found), 1)
        from scanner_configurations import verify_configuration
        self.assertTrue(verify_configuration(self.config))
        self.assertEqual(sa.differences(self.config, self.scanner), [])

    def test_an_avoid_changed_in_sds_manager_is_yours(self):
        export_state.record(self.config, 'exported', self.state)
        key = self.first_tgid()
        number = sa.avoid_map((self.config / LIST).read_bytes())[key][0]
        (self.config / LIST).write_bytes(sa.new_bytes((self.config / LIST).read_bytes(), {number: 'On'}))
        found = sa.differences(self.config, self.scanner, export_state.matched_avoids(self.config, self.state))
        self.assertEqual([f['made_on'] for f in found], ['SDS-Manager'])
        self.assertEqual([f['made_on'] for f in sa.differences(self.config, self.scanner)], [''])


if __name__ == '__main__':
    unittest.main()
