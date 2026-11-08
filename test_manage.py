# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Managing configurations and lists (v0.1.7): new configuration, duplicate, copy, import, reorder, and
systems, departments and channels typed in by hand. Real SDS100 files, an isolated mock scanner."""
import unittest
from pathlib import Path
from unittest.mock import patch

import configuration_tasks as tasks
import favorites_clipboard as fc
import hand_entry as he
import scanner_configurations as sc
import scanner_first_write as writer
import scanner_list_sync as sync
from native_favorites_export import validate_export_file
from test_list_sync_export import FIX, SyncBase


def raw(rows):
    return ('\r\n'.join('\t'.join(r) for r in rows) + '\r\n').encode('cp1252')


class ListTaskTests(SyncBase):
    def names(self, folder=None):
        return [l['name'] for l in tasks.lists_in_order(folder or self.config)]

    def test_lists_in_the_scanners_order(self):
        self.assertEqual(self.names(), ['Greenville County', 'SC Highway Patrol'])

    def test_duplicate_a_list(self):
        self.assertEqual(tasks.free_name(self.config, 'Greenville County'), 'Greenville County (2)')
        result = tasks.duplicate_list(self.config, 'BCDx36HP/favorites_lists/f_000001.hpd', 'Greenville County (2)')
        copy = Path(result['path'])
        self.assertEqual(copy.read_bytes(), (FIX / 'real_sds100_f_000001.hpd').read_bytes().rstrip(b'\r\n') + b'\r\n')
        self.assertEqual(self.names()[-1], 'Greenville County (2)')
        row = next(l for l in (self.local / 'favorites_lists/f_list.cfg').read_text('cp1252').splitlines()
                   if l.startswith('F-List\tGreenville County (2)'))
        self.assertEqual(row.split('\t')[5:7], ['Off', 'Off'])          # no quick key or number tag clash
        sc.verify_configuration(self.config)
        ok, why = writer.first_write_eligibility(self.config, self.scanner)
        self.assertTrue(ok, why)

    def test_import_a_list_file(self):
        result = tasks.import_list_file(self.config, FIX / 'confirmed_f_000014_p25_dmr.hpd', 'Oconee')
        self.assertEqual(self.names()[-1], 'Oconee')
        self.assertTrue(sync.assess_new_hpd(Path(result['path']).read_bytes())[0])
        not_a_list = self.base / 'notes.hpd'
        not_a_list.write_text('hello')
        with self.assertRaises(ValueError):
            tasks.import_list_file(self.config, not_a_list, 'Bad')

    def test_reorder_and_export(self):
        self.assertTrue(tasks.reorder_lists(self.config, ['f_000002.hpd', 'f_000001.hpd']))
        self.assertEqual(self.names(), ['SC Highway Patrol', 'Greenville County'])
        sc.verify_configuration(self.config)
        ok, why = writer.first_write_eligibility(self.config, self.scanner)
        self.assertTrue(ok, why)
        writer.execute_first_write(self.config, self.scanner)
        self.assertEqual((self.scanner / 'favorites_lists/f_list.cfg').read_bytes(),
                         (self.local / 'favorites_lists/f_list.cfg').read_bytes())
        with self.assertRaises(ValueError):
            tasks.reorder_lists(self.config, ['f_000001.hpd'])

    def test_new_configuration_has_the_settings_and_no_lists(self):
        folder, manifest = tasks.new_configuration(self.config, 'Fresh')
        self.assertEqual(manifest['name'], 'Fresh')
        self.assertEqual(self.names(folder), [])
        self.assertEqual((folder / 'BCDx36HP/profile.cfg').read_bytes(), b'Profile test')
        self.assertEqual(self.names(), ['Greenville County', 'SC Highway Patrol'])   # source unchanged
        # a list can be added, and exporting removes the scanner's old lists (they were archived)
        tasks.import_list_file(folder, FIX / 'confirmed_f_000012_p25_nxdn.hpd', 'Pickens')
        with patch.object(writer, 'list_configurations', lambda: [(folder, sc.json.loads(
                (folder / 'configuration.json').read_text()))]):
            ok, why = writer.first_write_eligibility(folder, self.scanner)
            self.assertTrue(ok, why)
            self.assertIn('REMOVED', why)
            result = writer.execute_first_write(folder, self.scanner)
        self.assertFalse((self.scanner / 'favorites_lists/f_000001.hpd').exists())
        self.assertEqual(len(result['added']), 1)

    def test_copy_to_another_configuration(self):
        folder, _ = tasks.new_configuration(self.config, 'Other')
        tasks.duplicate_list(self.config, 'BCDx36HP/favorites_lists/f_000002.hpd', 'SC Highway Patrol',
                             target=folder)
        self.assertEqual(self.names(folder), ['SC Highway Patrol'])


class HandEntryTests(unittest.TestCase):
    def test_a_typed_in_system_is_a_valid_list(self):
        rows = he.conventional_system_rows('Lake Keowee', 'Marinas', [he.channel('Marina 1', '154.570', 'NFM', '100.0')])
        self.assertEqual([r[0] for r in rows], ['Conventional', 'DQKs_Status', 'C-Group', 'C-Freq'])
        self.assertEqual(rows[3][5:8], ['154570000', 'NFM', 'TONE=C100.0'])
        whole = [['TargetModel', 'BCDx36HP'], ['FormatVersion', '1.00']] + rows
        self.assertTrue(sync.assess_new_hpd(raw(whole))[0])

    def test_bad_values_are_explained(self):
        for bad in (('', '154.57'), ('A', 'abc'), ('A', '2000'), ('A', '154.1234567')):
            with self.assertRaises(he.EntryError):
                he.channel(*bad)
        with self.assertRaises(he.EntryError):
            he.channel('A', '154.57', 'AM', 'nonsense')
        with self.assertRaises(he.EntryError):
            he.talkgroup_id('12a')
        self.assertEqual(he.frequency_hz('460.025 MHz'), '460025000')

    def test_departments_and_talkgroups_in_a_real_list(self):
        from test_favorites_clipboard import native, rows_of, find
        lists = native(FIX / 'confirmed_f_000014_p25_dmr.hpd')
        palmetto = lists[find(lists, 'Palmetto 800')]['records']
        template = next(r for r in palmetto if r[0] == 'TGID')
        like = next(r for r in palmetto if r[0] == 'T-Group')
        palmetto.extend(he.talkgroup_department_rows('Seneca PD', [he.talkgroup_row(template, 'Seneca PD Disp', '44900')], like))
        oconee = lists[find(lists, 'Oconee')]['records']
        oconee.extend(he.conventional_department_rows('Lake Patrol', [he.channel('Lake 1', '453.150', 'FM')]))
        lists.append(fc._new_entry(lists, he.conventional_system_rows('Mine', 'Dept', [he.channel('Ch', '462.5625')])))
        rows = rows_of(lists)
        self.assertTrue(sync.assess_new_hpd(raw(rows))[0])
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'f.hpd'
            path.write_bytes(raw(rows))
            validate_export_file(path, rows)
        tg = palmetto[-1]
        self.assertEqual((tg[3], tg[5], tg[16]), ('Seneca PD Disp', '44900', 'Any'))
        with self.assertRaises(he.EntryError):
            he.talkgroup_row(None, 'x', '1')


if __name__ == '__main__':
    unittest.main()


class MenuWiringTests(unittest.TestCase):
    def test_every_menu_action_exists(self):
        import ast
        source = (Path(__file__).parent / 'database_favorites_manager.py').read_text()
        tree = ast.parse(source)
        window = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ManagerWindow')
        build = next(n for n in window.body if isinstance(n, ast.FunctionDef) and n.name == '_build_menus')
        used = {n.attr for n in ast.walk(build) if isinstance(n, ast.Attribute)
                and isinstance(n.value, ast.Name) and n.value.id == 'self'}
        mixin_tree = ast.parse((Path(__file__).parent / 'manage_actions.py').read_text())
        defined = {n.name for c in (window,) + tuple(n for n in mixin_tree.body if isinstance(n, ast.ClassDef))
                   for n in c.body if isinstance(n, ast.FunctionDef)}
        for other in ('ui_extras.py', 'monitor_link_ui.py', 'updates.py'):
            defined |= {n.name for n in ast.walk(ast.parse((Path(__file__).parent / other).read_text()))
                        if isinstance(n, ast.FunctionDef)}
        missing = sorted(u for u in used if u not in defined and u not in (
            'workspace', 'menuBar', 'statusBar', 'close', 'build_theme_menu', '_tools_menu', '_workspace_actions'))
        self.assertEqual(missing, [])
        self.assertNotIn('Drafts & Planning', source)
        self.assertNotIn('sds100draft', (Path(__file__).parent / 'database_workspace.py').read_text())


class OpenConfigurationTests(SyncBase):
    def test_opening_loads_every_list_in_order_and_nothing_else(self):
        import qt_stub
        from unittest.mock import MagicMock
        from test_favorites_clipboard import native
        with qt_stub.installed(forget=('manage_actions',)):
            import manage_actions as ma

            class Workspace:
                def __init__(self):
                    self.drafts = {'Old list from another configuration': [{}]}
                    self.draft_choice = MagicMock()
                    self.current_draft = None

                def refresh_draft(self):
                    pass

                def create_editable_native_copy(self, path):
                    entries = native(Path(path))
                    data = Path(path).read_bytes()
                    entries[0].update(newline='\r\n', final_newline=data.endswith(b'\n'),
                                      source_sha256=__import__('hashlib').sha256(data).hexdigest())
                    name = [l['name'] for l in tasks.lists_in_order(Path(path).parents[2])
                            if l['filename'] == Path(path).name][0]
                    self.drafts[name] = entries

            class Window(ma.ManageMixin):
                def __init__(self):
                    self.workspace = Workspace()
                    self.statusBar = MagicMock()

                def _refresh_configuration_label(self):
                    pass

            w = Window()
            self.assertTrue(w._open_configuration(self.config, self.manifest(), check_unsaved=False))
            self.assertEqual(list(w.workspace.drafts), ['Greenville County', 'SC Highway Patrol'])
            self.assertEqual(w._modified_list_names(), [])
            self.assertEqual(w._draft_for('BCDx36HP/favorites_lists/f_000002.hpd'), 'SC Highway Patrol')
            w.workspace.drafts['Greenville County'][1]['records'][0][3] = 'Renamed'
            self.assertEqual(w._modified_list_names(), ['Greenville County'])
