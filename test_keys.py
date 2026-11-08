# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Keys & Tags (v0.1.8): every quick key, number tag and On/Off switch, on real SDS100 files."""
import unittest

import keys_model as km
import scanner_configurations as sc
import scanner_first_write as writer
from test_list_sync_export import SyncBase


class KeysModelTests(SyncBase):
    def model(self):
        return km.model_for_configuration(self.config)

    def find(self, model, level, name, parent=None):
        return next(i for i in model.items if i['level'] == level and i['name'] == name
                    and (parent is None or model.parent(i)['name'] == parent))

    def test_the_tree_and_what_is_scanned(self):
        m = self.model()
        greenville = self.find(m, 'list', 'Greenville County')
        self.assertEqual((greenville['key'], greenville['tag'], greenville['monitor']), (0, None, True))
        system = self.find(m, 'system', 'Greenville')
        self.assertEqual(system['key'], 1)
        police = self.find(m, 'department', 'Greenville (City) - Police')
        self.assertEqual(police['key'], 1)
        self.assertEqual([c['level'] for c in m.children(police['id'])][:1], ['channel'])
        self.assertTrue(m.scanned(greenville)[0])
        self.assertIn('key 00 is On', m.scanned(greenville)[1])
        palmetto = self.find(m, 'system', 'Palmetto 800', 'Greenville County')
        self.assertEqual(palmetto['key'], 0)                     # a trunked system's key is column 12 (v0.1.17)
        self.assertEqual(m.scanned(palmetto), (True, 'scanned: key 00 is On'))

    def test_switching_a_key_off_shows_what_is_skipped(self):
        m = self.model()
        police = self.find(m, 'department', 'Greenville (City) - Police')
        m.set_on(police, False)
        self.assertEqual(m.scanned(police), (False, 'not scanned: department key 01 is Off'))
        channel = m.children(police['id'])[0]
        self.assertIn('department key 01 is Off (department Greenville (City) - Police)', m.scanned(channel)[1])
        skipped = [t for k, t in m.warnings() if k == 'skipped']
        self.assertTrue(any('Department key 01 is Off in Greenville (Greenville County)' in t for t in skipped), skipped)
        edits = m.row_edits()
        self.assertEqual(len(edits), 1)
        filename, ei, ri, column, value = edits[0]
        self.assertEqual((filename, column, value), ('f_000001.hpd', 3, 'Off'))     # DQKs_Status, key 01
        greenville = self.find(m, 'list', 'Greenville County')
        m.set_on(greenville, False)
        self.assertIn('Favorites List key 00 is Off', m.scanned(channel)[1])

    def test_numbers_used_twice_in_one_set_only(self):
        m = self.model()
        fire = self.find(m, 'department', 'Greenville (City) - Fire Department')
        police = self.find(m, 'department', 'Greenville (City) - Police')
        self.assertEqual(m.users(police, 'key', 0), [fire])
        county = self.find(m, 'department', 'Greenville County')                 # Palmetto 800, also key 0
        self.assertNotIn(county, m.users(fire, 'key', 0))
        self.assertEqual([k for k, _t in m.warnings() if k == 'shared'], [])
        m.set_number(police, 'key', 0)
        shared = [t for k, t in m.warnings() if k == 'shared']
        self.assertEqual(len(shared), 1)
        self.assertIn('Department quick key 00 is used by 2 in Greenville (Greenville County)', shared[0])
        self.assertEqual(m.next_free(police, 'key'), 1)

    def test_changes_go_to_the_right_files_and_columns(self):
        m = self.model()
        hp = self.find(m, 'list', 'SC Highway Patrol')
        m.set_number(hp, 'key', 9)
        m.set_number(hp, 'tag', 2)
        system = self.find(m, 'system', 'Greenville')
        m.set_on(system, False)
        m.set_number(system, 'tag', 5)
        police = self.find(m, 'department', 'Greenville (City) - Police')
        channels = m.children(police['id'])
        m.number_in_order(channels, 'tag', 100, 10)
        self.assertEqual(m.flist_edits(), {('f_000002.hpd', 5): '9', ('f_000002.hpd', 6): '2',
                                           ('f_000001.hpd', 18): 'Off'})
        rows = m.row_edits()
        self.assertIn(('f_000001.hpd', system['ref'][2], 0, km.HEADER_TAG, '5'), rows)
        tags = [r for r in rows if r[3] == 16]
        self.assertEqual([r[4] for r in tags], [str(100 + 10 * n) for n in range(len(channels))])
        lines = m.describe_changes()
        self.assertIn('SC Highway Patrol: quick key Off → 9', lines)
        with self.assertRaises(ValueError):
            m.set_number(channels[0], 'key', 1)
        with self.assertRaises(ValueError):
            m.set_number(system, 'tag', 100)
        # the list-level part saves and still exports
        sc.save_local_flist_settings(self.config, m.flist_edits())
        ok, why = writer.first_write_eligibility(self.config, self.scanner)
        self.assertTrue(ok, why)
        self.assertEqual(km.model_for_configuration(self.config).items[
            self.find(m, 'list', 'SC Highway Patrol')['id']]['key'], 9)

    def test_export_summary(self):
        self.assertEqual(km.export_summary(self.config), '')
        m = self.model()
        system = self.find(m, 'system', 'Greenville')
        m.set_on(system, False)
        sc.save_local_flist_settings(self.config, m.flist_edits())
        text = km.export_summary(self.config)
        self.assertIn("Won't be scanned", text)
        self.assertIn('System key 01 is Off in Greenville County: not scanned: Greenville', text)


class KeysWindowTests(SyncBase):
    def test_the_window_builds_and_numbers(self):
        import qt_stub
        from unittest.mock import MagicMock
        with qt_stub.installed(forget=('keys_window',)):
            import keys_window as w
            w.KeysWindow._get_child_mock = lambda _self, **kw: MagicMock(**kw)
            window = w.KeysWindow(None, self.config, {})
            self.assertEqual(len(window.nodes), len(window.model.items))
            police = next(i for i in window.model.items if i['name'] == 'Greenville (City) - Police')
            window.tree.currentItem.return_value = window.nodes[police['id']]
            window.nodes[police['id']].data.return_value = police['id']
            w.QInputDialog.getInt = MagicMock(side_effect=[(200, True), (1, True)])
            window._number_children('tag')
            tags = [c['tag'] for c in window.model.children(police['id'])]
            self.assertEqual(tags, list(range(200, 200 + len(tags))))
            expected = window.model.next_free(police, 'key')
            window._next_free('key')
            self.assertEqual(police['key'], expected)
            self.assertEqual(window.model.users(police, 'key', expected), [])
            self.assertTrue(window.model.describe_changes())


if __name__ == '__main__':
    unittest.main()
