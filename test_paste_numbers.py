# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Quick keys and number tags when pasting, and the Keys / Tag column (v0.1.10)."""
import copy
import unittest

import favorites_clipboard as fc
import keys_model as km
from test_favorites_clipboard import FIX, find, group, native


class PasteNumberTests(unittest.TestCase):
    def setUp(self):
        self.f14 = native(FIX / 'confirmed_f_000014_p25_dmr.hpd')
        self.f12 = native(FIX / 'confirmed_f_000012_p25_nxdn.hpd')
        self.gv = native(FIX / 'real_sds100_f_000001.hpd')

    def department_keys(self, entries, system):
        records = entries[find(entries, system)]['records']
        return {r[3]: r[9] for r in records if r[0] in ('C-Group', 'T-Group')}

    def test_clashing_department_keys(self):
        # Greenville (City) - Police has department key 1, already used in the Greenville system.
        i, start = group(self.gv, 'Greenville', 'Greenville (City) - Police')
        clip = fc.copy_department(self.gv, i, start)
        target = copy.deepcopy(self.gv)
        records = target[find(target, 'Greenville')]['records']
        _k, s, e = fc.block_at(records, start)
        del records[s:e]                                    # it's gone; key 1 is free again
        result = fc.paste(copy.deepcopy(target), clip, (find(target, 'Greenville'), None))
        self.assertEqual(result['clashes'], [])
        # rename so it's a new department and paste it a second time: now key 1 clashes
        twin = copy.deepcopy(self.gv)
        clip['rows'][0][3] = 'Police 2'
        result = fc.paste(twin, clip, (find(twin, 'Greenville'), None), 'free')
        self.assertEqual([(n, w, v) for n, w, v in result['clashes'][:1]], [('Police 2', 'department quick key', 1)])
        keys = self.department_keys(twin, 'Greenville')
        self.assertNotEqual(keys['Police 2'], '1')
        self.assertNotIn(keys['Police 2'], [v for k, v in keys.items() if k != 'Police 2' and v != 'Off'])
        cleared = copy.deepcopy(self.gv)
        fc.paste(cleared, clip, (find(cleared, 'Greenville'), None), 'clear')
        self.assertEqual(self.department_keys(cleared, 'Greenville')['Police 2'], 'Off')
        kept = copy.deepcopy(self.gv)
        fc.paste(kept, clip, (find(kept, 'Greenville'), None), 'keep')
        self.assertEqual(self.department_keys(kept, 'Greenville')['Police 2'], '1')

    def test_a_whole_system_with_a_clashing_system_key(self):
        i = find(self.gv, 'Greenville')                     # system quick key 1
        clip = fc.copy_system(self.gv, i)
        clip['records'][0][3] = 'Greenville copy'
        target = copy.deepcopy(self.gv)
        result = fc.paste(target, clip, (None, None), 'free')
        self.assertIn(('Greenville copy', 'system quick key', 1), result['clashes'])
        header = target[-1]['records'][0]
        self.assertEqual(header[3], 'Greenville copy')
        self.assertNotIn(header[7], ('1', 'Off'))
        # departments in the new system are their own set: their keys don't clash with the old system's
        self.assertFalse([c for c in result['clashes'] if c[1] == 'department quick key'])

    def test_no_numbers_no_question(self):
        i, start = group(self.f14, 'Oconee', 'Oconee County - Sheriff')
        clip = fc.copy_department(self.f14, i, start)
        result = fc.paste(self.f12, clip, (find(self.f12, 'Pickens'), None))
        self.assertEqual(result['clashes'], [])

    def test_badges(self):
        records = self.gv[find(self.gv, 'Greenville')]['records']
        self.assertEqual(km.badge(records[0]), 'Key 01')
        police = next(r for r in records if r[0] == 'C-Group' and r[3] == 'Greenville (City) - Police')
        self.assertEqual(km.badge(police), 'Key 01')
        channel = list(next(r for r in records if r[0] == 'C-Freq'))
        self.assertEqual(km.badge(channel), '')
        channel[16] = '120'
        self.assertEqual(km.badge(channel), 'Tag 120')
        head = list(records[0])
        head[8] = '5'
        self.assertEqual(km.badge(head), 'Key 01 · Tag 05')
        self.assertEqual(km.badge(['Site', '', '', 'x']), '')


if __name__ == '__main__':
    unittest.main()
