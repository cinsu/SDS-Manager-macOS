# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Trunked systems keep their quick key in column 12 and number tag in column 13 (Uniden SDS Series File
Specification v2.00); columns 7 and 8 are ID Search and Alert Tone. Versions 0.1.8–0.1.16 used 7 and 8 (v0.1.17)."""
import copy
import unittest

import favorites_clipboard as fc
import keys_model as km
import scanner_list_sync as sync
from test_favorites_clipboard import FIX, find, native


def raw(rows):
    return ('\r\n'.join('\t'.join(r) for r in rows) + '\r\n').encode('cp1252')


class TrunkColumnTests(unittest.TestCase):
    def setUp(self):
        self.rows = [l.split('\t') for l in (FIX / 'real_sds100_f_000001.hpd').read_text('cp1252').splitlines()]
        self.trunk = next(r for r in self.rows if r[0] == 'Trunk')

    def test_real_palmetto_800(self):
        self.assertEqual((self.trunk[7], self.trunk[8], self.trunk[12], self.trunk[13]), ('Off', 'Off', '0', 'Off'))
        self.assertEqual(km.badge(self.trunk), 'Key 00')

    def test_keys_and_tags_writes_columns_12_and_13(self):
        import flist_settings as fls
        lists = fls.read_lists((FIX / 'real_sds100_f_list.cfg').read_bytes())
        m = km.Model(lists, [True] * 100, {'f_000001.hpd': km.entries_from_rows(self.rows)})
        palmetto = next(i for i in m.items if i['name'] == 'Palmetto 800')
        m.set_number(palmetto, 'key', 4)
        m.set_number(palmetto, 'tag', 2)
        self.assertEqual(sorted((c, v) for _f, _e, _r, c, v in m.row_edits()), [(12, '4'), (13, '2')])

    def test_repair_of_the_old_mistake(self):
        damaged = list(self.trunk)
        damaged[7], damaged[8] = '3', '25'                       # what 0.1.8–0.1.16 wrote
        self.assertEqual(km.misplaced_numbers(damaged), ('3', '25'))
        whole = [r if r[0] != 'Trunk' else damaged for r in self.rows]
        ok, why = sync.assess_new_hpd(raw(whole))
        self.assertFalse(ok)
        self.assertIn('Keys & Tags to repair', why)
        text = km.repair_row(damaged)
        self.assertEqual(text, 'Palmetto 800: quick key 3 (was in ID Search), number tag 25 (was in Alert Tone)')
        self.assertEqual((damaged[7], damaged[8], damaged[12], damaged[13]), ('Off', 'Off', '3', '25'))
        self.assertTrue(sync.assess_new_hpd(raw([r if r[0] != 'Trunk' else damaged for r in self.rows]))[0])
        self.assertIsNone(km.misplaced_numbers(self.trunk))
        self.assertEqual(km.repair_row(list(self.trunk)), '')

    def test_paste_renumbers_the_right_columns(self):
        lists = native(FIX / 'confirmed_f_000014_p25_dmr.hpd')
        clip = fc.copy_system(lists, find(lists, 'Palmetto 800'))
        clip['records'][0][3] = 'Palmetto copy'
        clip['records'][0][12] = '0'
        target = copy.deepcopy(lists)
        target[find(target, 'Palmetto 800')]['records'][0][12] = '0'
        result = fc.paste(target, clip, (None, None), 'free')
        self.assertIn(('Palmetto copy', 'system quick key', 0), result['clashes'])
        header = target[-1]['records'][0]
        self.assertEqual((header[7], header[8]), ('Off', 'Off'))       # ID Search and Alert Tone untouched
        self.assertNotIn(header[12], ('0', 'Off'))


if __name__ == '__main__':
    unittest.main()
