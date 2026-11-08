# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Add to Favorites into an EXISTING list (v0.1.24): database rows go in in the scanner's own format, so Save
and Export accept them. Before, a trunked system added this way was refused at Save ("Draft includes
non-native or unsupported system records")."""
import unittest
from pathlib import Path

import favorites_clipboard as clip
import scanner_list_sync as sync
from native_favorites_export import build_native_bytes
from test_export_keys import LIST, ExportKeysTests
from test_list_sync_export import SyncBase
from test_new_trunk_list import DB, FIX, rows_of
import scanner_first_write as writer

DMR = rows_of(FIX / 'real_hpdb_oconee_dmr_excerpt.txt')


class AddDatabaseToListTests(SyncBase):
    entries, save, eligible = ExportKeysTests.entries, ExportKeysTests.save, ExportKeysTests.eligible

    def saved_bytes(self, entries):
        entries[0]['source_path'] = str(self.local / LIST)
        payload, rows = build_native_bytes(entries)       # the check that refused it before
        return payload

    def test_a_new_trunked_system_saves_and_exports(self):
        entries = self.entries()
        original = (self.local / LIST).read_bytes()
        systems = len(entries)
        result = clip.paste(entries, clip.database_clip(DMR), (None, None), 'free')
        self.assertTrue(result['new_system'])
        self.assertEqual(len(entries), systems + 1)
        self.assertEqual(entries[-1]['origin'], 'native-copy')
        payload = self.saved_bytes(entries)
        ok, why = sync.assess_new_hpd(payload, original)
        self.assertTrue(ok, why)
        self.save(entries)
        ok, why = self.eligible()
        self.assertTrue(ok, why)
        writer.execute_first_write(self.config, self.scanner)
        self.assertEqual((self.scanner / LIST).read_bytes(), (self.local / LIST).read_bytes())

    def test_more_of_a_system_already_in_the_list_merges(self):
        entries = self.entries()
        palmetto = next(e for e in entries if e.get('name') == 'Palmetto 800')
        before = len(palmetto['records'])
        result = clip.paste(entries, clip.database_clip(DB), (None, None), 'free')
        self.assertFalse(result['new_system'])
        self.assertEqual(result['system'], 'Palmetto 800')
        self.assertGreaterEqual(len(palmetto['records']), before)
        again = clip.paste(entries, clip.database_clip(DB), (None, None), 'free')
        self.assertEqual((again['added'], again['departments'], again['sites']), (0, [], []))
        self.assertTrue(sync.assess_new_hpd(self.saved_bytes(entries), (self.local / LIST).read_bytes())[0])


if __name__ == '__main__':
    unittest.main()
