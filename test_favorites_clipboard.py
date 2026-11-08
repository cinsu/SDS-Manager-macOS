# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Cut, Copy and Paste between Favorites Lists (v0.1.5), on two lists confirmed working on a real SDS100:
f_000014 (Palmetto 800 P25, Oconee conventional, Oconee County Emergency Services DMR) and f_000012 (Pickens
conventional, Palmetto 800 P25, FleetTalk Carolinas NXDN). Every result must still pass the export checks."""
import copy
import tempfile
import unittest
from pathlib import Path

import favorites_clipboard as fc
import scanner_list_sync as sync
from native_favorites_export import validate_export_file

FIX = Path(__file__).resolve().parent / 'test_fixtures'


def native(path):
    """A draft as create_editable_native_copy makes it."""
    rows = [line.split('\t') for line in path.read_text(encoding='cp1252').splitlines()]
    meta = {'key': ['native-copy-meta', str(path)], 'scope': 'metadata', 'records': [], 'encoding': 'cp1252',
            'source_path': str(path)}
    entries, current = [meta], None
    for row in rows:
        if row[0] in ('Conventional', 'Trunk'):
            current = {'key': ['native-copy', str(path), len(entries) - 1], 'name': row[3], 'kind': row[0],
                       'scope': 'system', 'parent_system': row[3], 'records': [], 'origin': 'native-copy'}
            entries.append(current)
        (meta['records'] if current is None else current['records']).append(row)
    return entries


def rows_of(entries):
    out = list(entries[0]['records'])
    for e in entries[1:]:
        out.extend(e['records'])
    return out


def raw(rows):
    return ('\r\n'.join('\t'.join(r) for r in rows) + '\r\n').encode('cp1252')


def find(entries, name):
    return next(i for i, e in enumerate(entries) if e.get('name') == name)


def group(entries, system, name):
    i = find(entries, system)
    return i, next(s for k, s, _e in fc.blocks(entries[i]['records'])
                   if k in fc.DEPARTMENTS and entries[i]['records'][s][3] == name)


class ClipboardTests(unittest.TestCase):
    def setUp(self):
        self.f14 = native(FIX / 'confirmed_f_000014_p25_dmr.hpd')
        self.f12 = native(FIX / 'confirmed_f_000012_p25_nxdn.hpd')

    def assertExportable(self, entries):
        rows = rows_of(entries)
        ok, why = sync.assess_new_hpd(raw(rows))[:2]
        self.assertTrue(ok, why)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'f.hpd'
            path.write_bytes(raw(rows))
            validate_export_file(path, rows)

    def test_the_fixtures_are_exportable_as_read(self):
        self.assertExportable(self.f14)
        self.assertExportable(self.f12)

    def test_cut_a_conventional_department_into_another_list(self):
        i, start = group(self.f14, 'Oconee', 'Oconee County - Sheriff')
        rows = self.f14[i]['records'][start:fc.block_at(self.f14[i]['records'], start)[2]]
        clip = fc.copy_department(self.f14, i, start)
        self.assertFalse(fc.cut_check(self.f14, 'department', i, start))
        fc.remove_department(self.f14, i, start)
        self.assertNotIn('Oconee County - Sheriff', [r[3] for r in self.f14[i]['records']])
        pickens = find(self.f12, 'Pickens')
        result = fc.paste(self.f12, clip, (pickens, None))
        self.assertEqual((result['system'], result['new_system'], result['departments']),
                         ('Pickens', False, ['Oconee County - Sheriff']))
        self.assertEqual(self.f12[pickens]['records'][-len(rows):], rows)      # verbatim, every setting
        self.assertExportable(self.f12)
        self.assertExportable(self.f14)

    def test_a_trunked_department_brings_its_missing_sites(self):
        i, start = group(self.f14, 'Palmetto 800', 'Oconee County')
        clip = fc.copy_department(self.f14, i, start)
        result = fc.paste(self.f12, clip)
        palmetto = self.f12[find(self.f12, 'Palmetto 800')]['records']
        self.assertFalse(result['new_system'])
        self.assertEqual(result['sites'], ['Anderson County Simulcast', 'Seneca'])     # Pickens was there
        self.assertEqual([palmetto[s][3] for k, s, _e in fc.blocks(palmetto)],
                         ['Pickens', 'Anderson County Simulcast', 'Seneca', 'Pickens County', 'Oconee County'])
        self.assertExportable(self.f12)

    def test_a_trunked_department_starts_its_system_where_there_is_none(self):
        i, start = group(self.f14, 'Oconee County Emergency Services', 'Oconee Co FD')
        clip = fc.copy_department(self.f14, i, start)
        before = len(self.f12)
        result = fc.paste(self.f12, clip, (find(self.f12, 'Pickens'), None))   # selection is conventional
        self.assertTrue(result['new_system'])
        self.assertEqual(len(self.f12), before + 1)
        self.assertEqual(self.f12[-1]['records'], self.f14[i]['records'])     # its only department: the same
        self.assertEqual(self.f12[-1]['origin'], 'native-copy')
        self.assertExportable(self.f12)

    def test_pasting_twice_adds_nothing_the_second_time(self):
        i, start = group(self.f14, 'Oconee', 'Oconee County - EMS')
        clip = fc.copy_department(self.f14, i, start)
        fc.paste(self.f12, clip, (find(self.f12, 'Pickens'), None))
        again = copy.deepcopy(self.f12)
        result = fc.paste(again, clip, (find(again, 'Pickens'), None))
        self.assertEqual((result['added'], result['departments'], result['merged']),
                         (0, [], ['Oconee County - EMS']))
        self.assertEqual(again, self.f12)

    def test_channels_and_talkgroups(self):
        i, start = group(self.f14, 'Oconee', 'Oconee County - Fire Departments')
        records = self.f14[i]['records']
        leaves = [n for n in range(start + 1, fc.block_at(records, start)[2]) if records[n][0] == 'C-Freq'][:2]
        clip = fc.copy_leaves(self.f14, i, leaves)
        self.assertEqual(fc.describe(clip), '2 channels')
        target = group(self.f12, 'Pickens', 'Pickens County - Fire/EMS')
        result = fc.paste(self.f12, clip, target)
        self.assertEqual(result['added'], 2)
        self.assertExportable(self.f12)
        with self.assertRaises(fc.ClipboardError):                  # channels don't go into talkgroup departments
            fc.paste(self.f12, clip, group(self.f12, 'Palmetto 800', 'Pickens County'))
        dmr, dept = group(self.f14, 'Oconee County Emergency Services', 'Oconee Co FD')
        tgs = [n for n, r in enumerate(self.f14[dmr]['records']) if r[0] == 'TGID']
        clip = fc.copy_leaves(self.f14, dmr, tgs)
        with self.assertRaises(fc.ClipboardError) as cm:            # DMR talkgroups into a P25 system
            fc.paste(self.f12, clip, group(self.f12, 'Palmetto 800', 'Pickens County'))
        self.assertIn('DmrOneFrequency', str(cm.exception))
        with self.assertRaises(fc.ClipboardError):
            fc.copy_leaves(self.f14, i, [n for n, r in enumerate(records) if r[0] == 'C-Group'])

    def test_talkgroups_already_in_the_system_are_skipped(self):
        p, dept = group(self.f12, 'Palmetto 800', 'Pickens County')
        records = self.f12[p]['records']
        tgs = [n for n, r in enumerate(records) if r[0] == 'TGID']
        clip = fc.copy_leaves(self.f12, p, tgs)
        result = fc.paste(self.f12, clip, (p, dept))
        self.assertEqual((result['added'], result['skipped']), (0, len(tgs)))

    def test_a_whole_system(self):
        i = find(self.f14, 'Oconee County Emergency Services')
        clip = fc.copy_system(self.f14, i)
        result = fc.paste(self.f12, clip)
        self.assertTrue(result['new_system'])
        self.assertEqual(self.f12[-1]['records'], self.f14[i]['records'])
        self.assertExportable(self.f12)
        again = fc.paste(self.f12, clip)                              # now it merges, adding nothing
        self.assertFalse(again['new_system'])
        self.assertEqual(again['added'], 0)

    def test_a_list_is_never_left_empty(self):
        single = [self.f14[0], self.f14[find(self.f14, 'Oconee County Emergency Services')]]
        with self.assertRaises(fc.ClipboardError):
            fc.cut_check(single, 'system', 1)
        _i, start = group(single, 'Oconee County Emergency Services', 'Oconee Co FD')
        with self.assertRaises(fc.ClipboardError):
            fc.cut_check(single, 'department', 1, start)
        i = find(self.f14, 'Oconee County Emergency Services')
        _i, start = group(self.f14, 'Oconee County Emergency Services', 'Oconee Co FD')
        self.assertTrue(fc.cut_check(self.f14, 'department', i, start))   # its last department: system goes
        self.assertTrue(fc.remove_department(self.f14, i, start))
        self.assertNotIn('Oconee County Emergency Services', [e.get('name') for e in self.f14])
        self.assertExportable(self.f14)

    def test_paste_as_a_new_list(self):
        i, start = group(self.f14, 'Palmetto 800', 'Oconee County')
        rows = fc.new_list_rows(fc.copy_department(self.f14, i, start))
        self.assertEqual([r[0] for r in rows[:4]], ['TargetModel', 'FormatVersion', 'Trunk', 'DQKs_Status'])
        self.assertEqual(sum(r[0] == 'Site' for r in rows), 3)
        self.assertTrue(sync.assess_new_hpd(raw(rows))[0])
        with self.assertRaises(fc.ClipboardError):
            fc.new_list_rows(fc.copy_leaves(self.f14, i, [n for n, r in enumerate(self.f14[i]['records'])
                                                          if r[0] == 'TGID']))

    def test_only_lists_of_a_scanner_configuration(self):
        clip = fc.copy_system(self.f14, 1)
        with self.assertRaises(fc.ClipboardError):
            fc.paste([{'name': 'draft', 'records': []}], clip)
        self.assertFalse(fc.is_native([]))


class EditorClipboardTests(unittest.TestCase):
    """The editor's Cut and Paste, through the Qt stand-in."""

    def test_cut_in_one_list_and_paste_in_another(self):
        import qt_stub
        from unittest.mock import MagicMock
        with qt_stub.installed(forget=('favorites_settings_window',)):
            import favorites_settings_window as w
            yes = w.QMessageBox.StandardButton.Yes
            w.QMessageBox.question = MagicMock(return_value=yes)
            workspace = MagicMock()
            workspace.drafts = {'A': native(FIX / 'confirmed_f_000014_p25_dmr.hpd'),
                                'B': native(FIX / 'confirmed_f_000012_p25_nxdn.hpd')}
            workspace.favorites_clipboard = None
            workspace._snapshot = MagicMock()
            class Settings:
                def __init__(self, *args):
                    pass

                def value(self, key, default=None, type=None):
                    return default

                def setValue(self, key, value):
                    pass
            w.QSettings = Settings
            w.FavoritesSettingsDialog._get_child_mock = lambda _self, **kw: MagicMock(**kw)
            a = w.FavoritesSettingsDialog(workspace, 'A')
            a.tree, a.table = MagicMock(), MagicMock()
            place = group(workspace.drafts['A'], 'Oconee', 'Oconee County - Sheriff')
            a.tree.currentItem.return_value.data.return_value = place
            a._clipboard_key('tree', 'cut')
            self.assertEqual(workspace.favorites_clipboard['what'], 'department')
            self.assertTrue(workspace.favorites_clipboard['cut'])
            self.assertNotIn('Oconee County - Sheriff', [r[3] for r in workspace.drafts['A'][place[0]]['records']])
            b = w.FavoritesSettingsDialog(workspace, 'B')
            b.tree, b.table = MagicMock(), MagicMock()
            b.tree.currentItem.return_value.data.return_value = (find(workspace.drafts['B'], 'Pickens'), None)
            b._clipboard_key('tree', 'paste')
            self.assertIn('Oconee County - Sheriff',
                          [r[3] for r in workspace.drafts['B'][find(workspace.drafts['B'], 'Pickens')]['records']])
            self.assertIsNone(workspace.favorites_clipboard)          # a cut is pasted once
            self.assertEqual(workspace._snapshot.call_count, 2)       # each step can be undone
            # copy a department, then Paste as New Favorites List through the configuration's hooks
            b._clipboard_key('tree', 'copy')
            made = {}
            workspace.new_list_hooks = {'available': lambda: True, 'check': lambda name: None,
                                        'create_native': lambda name, rows, enc: made.update(name=name, rows=rows)
                                        or 'Pickens only (editable copy)'}
            menu = MagicMock()
            b._add_clipboard_actions(menu, 'tree', b.tree.currentItem())
            self.assertIn('Paste as New Favorites List…', [c.args[0] for c in menu.addAction.call_args_list])
            w.QInputDialog.getText = MagicMock(return_value=('Pickens only', True))
            b._paste_as_new_list()
            self.assertEqual(made['name'], 'Pickens only')
            self.assertTrue(sync.assess_new_hpd(raw(made['rows']))[0])


if __name__ == '__main__':
    unittest.main()
