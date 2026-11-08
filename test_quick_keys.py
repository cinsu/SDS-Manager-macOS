# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Quick keys shown with what they are assigned to (v0.1.6), from real SDS100 files."""
import shutil
import tempfile
import unittest
from pathlib import Path

import quick_key_map as qk
import scanner_list_sync as sync

FIX = Path(__file__).resolve().parent / 'test_fixtures'


def rows(name):
    return [l.split('\t') for l in (FIX / name).read_text(encoding='cp1252').splitlines()]


class QuickKeyMapTests(unittest.TestCase):
    def test_systems_and_departments_with_their_keys(self):
        systems = qk.read_systems(rows('real_sds100_f_000001.hpd'))
        self.assertEqual([(s['name'], s['kind'], s['key']) for s in systems],
                         [('Palmetto 800', 'Trunk', 0), ('Greenville', 'Conventional', 1)])   # Palmetto: column 12 (v0.1.17)
        greenville = systems[1]
        self.assertEqual([(d['name'], d['key']) for d in greenville['departments']][:3],
                         [('Greenville (City) - Fire Department', 0), ('Greenville (City) - Police', 1),
                          ('Greenville County - EMS', 2)])
        self.assertEqual(len(greenville['status']), 100)
        self.assertEqual(qk.owners(greenville['departments'])[1], ['Greenville (City) - Police'])

    def test_plain_words(self):
        statuses = [False] * 100
        statuses[3] = True
        self.assertEqual(qk.state(3, statuses), 'Key 03 is On: scanned')
        self.assertEqual(qk.state(4, statuses), 'Key 04 is Off: not scanned')
        self.assertIn('No quick key', qk.state(None, statuses))
        self.assertEqual(qk.key_label(None), 'none')
        self.assertEqual([qk.key_number(v) for v in ('0', '7', 'Off', '', '100', '7.0')], [0, 7, None, None, None, None])
        assigned = {3: ['A'], 4: ['B', 'C']}
        self.assertEqual(qk.shared(assigned), {4: ['B', 'C']})
        statuses[50] = True
        self.assertEqual(qk.summary(statuses, assigned),
                         '2 key(s) assigned: 1 On, 1 Off. 1 unassigned key(s) are On; that does nothing until '
                         'something uses them.')

    def test_department_keys_are_numbered_per_system(self):
        # Palmetto 800's department and Greenville's first department both use key 0, as the scanner allows.
        data = (FIX / 'real_sds100_f_000001.hpd').read_bytes()
        systems = qk.read_systems(rows('real_sds100_f_000001.hpd'))
        self.assertEqual((systems[0]['departments'][0]['key'], systems[1]['departments'][0]['key']), (0, 0))
        text = data.decode('cp1252').splitlines()
        conv = [l for l in text if l.startswith(('C-Group', 'C-Freq', 'Conventional', 'DQKs_Status'))]
        start = text.index(next(l for l in text if l.startswith('Conventional')))
        body = text[start:]
        second = [l.replace('\tGreenville\t', '\tGreenville 2\t', 1) if l.startswith('Conventional') else l for l in body]
        twice = '\r\n'.join(text[:2] + body + second) + '\r\n'
        self.assertTrue(conv)
        ok, why = sync.assess_new_hpd(twice.encode('cp1252'))[:2]
        self.assertTrue(ok, why)


class QuickKeysWindowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        lists = self.tmp / 'BCDx36HP' / 'favorites_lists'
        lists.mkdir(parents=True)
        shutil.copy(FIX / 'real_sds100_profile.cfg', self.tmp / 'BCDx36HP' / 'profile.cfg')
        shutil.copy(FIX / 'real_sds100_f_list.cfg', lists / 'f_list.cfg')
        for name in ('f_000001.hpd', 'f_000002.hpd'):
            shutil.copy(FIX / ('real_sds100_' + name), lists / name)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_switching_keys_gives_plain_changes(self):
        import qt_stub
        from unittest.mock import MagicMock
        with qt_stub.installed(forget=('quick_keys_window',)):
            import quick_keys_window as w
            w.QuickKeysWindow._get_child_mock = lambda _self, **kw: MagicMock(**kw)
            window = w.QuickKeysWindow(None, self.tmp, {'name': 'Home'})
            greenville = next(l for l in window.lists if l['filename'] == 'f_000001.hpd')
            self.assertEqual(greenville['key'], 0)
            self.assertEqual(window.fl_owners[0], ['Greenville County'])
            self.assertEqual(window.changes(), [])
            window._grid_changed(0, not window.fl_status[0])
            window.sys_status['f_000001.hpd'][1] = not window.sys_saved['f_000001.hpd'][1]
            lines = window.changes()
            self.assertEqual(len(lines), 2)
            self.assertIn('Favorites List key 00 (Greenville County)', lines[0])
            self.assertIn('Greenville County: system key 01 (Greenville)', lines[1])
            self.assertEqual(list(window.flist_edits()), [('f_000001.hpd', 18)])
            self.assertIsNone(w.fls.check_edits(w.fls.read_lists(window.index), window.flist_edits()))


if __name__ == '__main__':
    unittest.main()
