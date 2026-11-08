# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""New Favorites Lists (created inside Add to Favorites) and complete deletion.

Fixtures in test_fixtures/ are real files from an SDS100 (Sentinel-written Favorites lists and
f_list.cfg) and an excerpt of the master HPDB (Greenville County conventional system).
"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scanner_configurations as sc
from new_favorites_list import build_new_list_rows, CHANNEL_DEFAULTS
from native_favorites_reader import parse_native_favorites
from scanner_favorites_expanded import _hierarchy

FIX = Path(__file__).resolve().parent / 'test_fixtures'


def rows_of(path):
    text = Path(path).read_bytes().decode('cp1252')
    return [line.split('\t') for line in text.splitlines()]


REAL_FAVORITES = rows_of(FIX / 'real_sds100_f_000001.hpd')
REAL_FLIST = rows_of(FIX / 'real_sds100_f_list.cfg')
DB = rows_of(FIX / 'real_hpdb_greenville_county.txt')


def selection(max_groups=None):
    """What the Add dialog hands over: system header plus chosen C-Group/C-Freq rows."""
    records = [DB[0]]
    groups = 0
    for row in DB[1:]:
        if row[0] == 'C-Group':
            groups += 1
            if max_groups and groups > max_groups:
                break
        if row[0] in ('C-Group', 'C-Freq'):
            records.append(row)
    return records


def hpd_bytes(rows):
    return ('\r\n'.join('\t'.join(r) for r in rows) + '\r\n').encode('cp1252')


class BuilderTests(unittest.TestCase):
    def test_new_rows_have_the_same_shape_as_real_favorites_rows(self):
        rows, enc, nl = build_new_list_rows(selection())
        self.assertEqual((enc, nl), ('cp1252', '\r\n'))
        real_header = next(r for r in REAL_FAVORITES if r[0] == 'Conventional')
        real_dqks = next(r for r in REAL_FAVORITES if r[0] == 'DQKs_Status')
        real_group = next(r for r in REAL_FAVORITES if r[0] == 'C-Group')
        real_leaf = next(r for r in REAL_FAVORITES if r[0] == 'C-Freq')
        self.assertEqual(rows[:2], [['TargetModel', 'BCDx36HP'], ['FormatVersion', '1.00']])
        header, dqks = rows[2], rows[3]
        self.assertEqual(len(header), len(real_header))
        self.assertEqual(header[:3] + header[4:7], ['Conventional', '', '', 'Off', '', 'Conventional'])
        self.assertEqual(header[9:], real_header[9:])   # hold time, AGC, wait time, mode, level
        self.assertEqual(header[3], 'Greenville')
        self.assertEqual(len(dqks), len(real_dqks))
        self.assertEqual(dqks[:2], ['DQKs_Status', ''])
        self.assertEqual(dqks[-1], '')
        self.assertTrue(all(v == 'Off' for v in dqks[2:-1]))
        groups = [r for r in rows if r[0] == 'C-Group']
        leaves = [r for r in rows if r[0] == 'C-Freq']
        self.assertTrue(groups and leaves)
        self.assertTrue(all(len(g) == len(real_group) and g[1:3] == ['', ''] for g in groups))
        self.assertTrue(all(len(l) == len(real_leaf) and l[1:3] == ['', ''] for l in leaves))
        self.assertEqual(CHANNEL_DEFAULTS, real_leaf[9:])  # defaults are what Sentinel wrote

    def test_nothing_is_assigned_a_quick_key_or_number_tag(self):
        rows, _, _ = build_new_list_rows(selection())
        header = rows[2]
        self.assertEqual([header[4], header[7], header[8]], ['Off'] * 3)
        for g in (r for r in rows if r[0] == 'C-Group'):
            self.assertEqual([g[4], g[9]], ['Off', 'Off'])
        for l in (r for r in rows if r[0] == 'C-Freq'):
            self.assertEqual([l[4], l[16], l[17]], ['Off'] * 3)

    def test_database_values_are_carried_not_template_values(self):
        sel = selection()
        rows, _, _ = build_new_list_rows(sel)
        db_leaves = {(r[3], r[5]): r for r in sel if r[0] == 'C-Freq'}
        new_leaves = [r for r in rows if r[0] == 'C-Freq']
        self.assertEqual(len(new_leaves), len({(r[3], r[5]) for r in db_leaves.values()}))
        for leaf in new_leaves:
            src = db_leaves[(leaf[3], leaf[5])]
            self.assertEqual(leaf[6:9], src[6:9])  # modulation, audio option (tone/NAC/CC), service type
        db_groups = {r[3]: r for r in sel if r[0] == 'C-Group'}
        for g in (r for r in rows if r[0] == 'C-Group'):
            self.assertEqual(g[5:9], db_groups[g[3]][5:9])  # latitude, longitude, range, type

    def test_result_is_accepted_by_the_app_validators(self):
        rows, enc, nl = build_new_list_rows(selection())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'new.hpd'
            path.write_bytes(hpd_bytes(rows))
            parsed = parse_native_favorites(path)
            self.assertEqual(parsed['warnings'], [])
            self.assertEqual(len(parsed['systems']), 1)
            _hierarchy(rows)

    def test_errors(self):
        with self.assertRaises(ValueError):
            build_new_list_rows([['Trunk', '', '', 'X']])
        with self.assertRaises(ValueError):
            build_new_list_rows([DB[0]])                         # header only
        sel = [list(r) for r in selection(max_groups=1)]
        bad_freq = [list(r) for r in sel]
        next(r for r in bad_freq if r[0] == 'C-Freq')[5] = '155.1'
        with self.assertRaises(ValueError):
            build_new_list_rows(bad_freq)
        bad_mod = [list(r) for r in sel]
        next(r for r in bad_mod if r[0] == 'C-Freq')[6] = 'XYZ'
        with self.assertRaises(ValueError):
            build_new_list_rows(bad_mod)
        bad_service = [list(r) for r in sel]
        next(r for r in bad_service if r[0] == 'C-Freq')[8] = ''
        with self.assertRaises(ValueError):
            build_new_list_rows(bad_service)

    def test_duplicate_channels_dropped_and_empty_departments_removed(self):
        sel = selection(max_groups=1)
        first = next(r for r in sel if r[0] == 'C-Freq')
        rows, _, _ = build_new_list_rows(sel + [list(first)])
        self.assertEqual(sum(1 for r in rows if r[0] == 'C-Freq'),
                         len({(r[3], r[5]) for r in sel if r[0] == 'C-Freq'}))
        empty = ['C-Group', '', '', 'Empty dept', 'Off', '', '', '', 'Circle', 'Off', 'Global']
        rows, _, _ = build_new_list_rows(sel + [empty])
        self.assertNotIn('Empty dept', [r[3] for r in rows if r[0] == 'C-Group'])


class FlistRowTests(unittest.TestCase):
    def test_real_row_gives_same_width_row_with_nothing_assigned(self):
        template = next(r for r in REAL_FLIST if r[0] == 'F-List' and r[5] == '0')
        row = sc.new_flist_row(template, 'New List', 'f_000099.hpd')
        self.assertEqual(len(row), len(template))
        self.assertEqual(row[:5], ['F-List', 'New List', 'f_000099.hpd', 'Off', 'On'])
        self.assertTrue(all(v == 'Off' for v in row[5:-1]))
        self.assertEqual(row[-1], '')

    def test_every_real_row_is_accepted_as_template(self):
        for template in (r for r in REAL_FLIST if r[0] == 'F-List'):
            self.assertEqual(len(sc.new_flist_row(template, 'n', 'f_000099.hpd')), 118)

    def test_unrecognised_layout_blocks(self):
        with self.assertRaises(ValueError):
            sc.new_flist_row(['F-List', 'a', 'f_1.hpd', 'Maybe', 'On', 'Off', 'Off'], 'n', 'f_2.hpd')
        with self.assertRaises(ValueError):
            sc.new_flist_row(['F-List', 'a', 'f_1.hpd'], 'n', 'f_2.hpd')


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.library = base / 'library'
        self.root = self.library / 'cfg'
        favorites = self.root / 'BCDx36HP' / 'favorites_lists'
        favorites.mkdir(parents=True)
        for name in ('f_000001.hpd', 'f_000002.hpd'):
            (favorites / name).write_bytes((FIX / ('real_sds100_' + name)).read_bytes())
        self.index_bytes = (FIX / 'real_sds100_f_list.cfg').read_bytes()
        # Real index lists 27 lists; only the first two files exist locally. That is a
        # valid partial configuration for these tests (the index is not manifest-checked).
        (favorites / 'f_list.cfg').write_bytes(self.index_bytes)
        files = {}
        for path in favorites.iterdir():
            data = path.read_bytes()
            files[f'BCDx36HP/favorites_lists/{path.name}'] = {
                'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        (self.root / 'configuration.json').write_text(json.dumps(
            {'format': 'sds100-configuration-snapshot-v1', 'name': 'cfg', 'files': files}))
        patcher = mock.patch.object(sc, 'library_path', lambda: self.library)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def rows(self):
        return build_new_list_rows(selection())

    def test_create_registers_everything_together(self):
        rows, enc, nl = self.rows()
        result = sc.create_local_favorites_list(self.root, 'Greenville Public Safety', rows, enc, nl)
        self.assertEqual(result['filename'], 'f_000028.hpd')  # lowest name not in the index or folder
        self.assertTrue(sc.verify_configuration(self.root))
        manifest = json.loads((self.root / 'configuration.json').read_text())
        self.assertIn('BCDx36HP/favorites_lists/f_000028.hpd', manifest['files'])
        new_index = (self.root / sc.INDEX_KEY).read_bytes()
        self.assertTrue(new_index.startswith(self.index_bytes))      # every existing row untouched
        added = new_index[len(self.index_bytes):].decode('cp1252').split('\r\n')
        self.assertEqual(added[1:], [''])                            # exactly one new CRLF row
        fields = added[0].split('\t')
        self.assertEqual(len(fields), 118)
        self.assertEqual(fields[1:5], ['Greenville Public Safety', 'f_000028.hpd', 'Off', 'On'])
        self.assertTrue(all(v == 'Off' for v in fields[5:-1]))
        saved = (self.root / 'BCDx36HP/favorites_lists/f_000028.hpd').read_bytes()
        self.assertEqual(saved, hpd_bytes(rows))

    def test_empty_list_and_duplicate_name_refused_without_side_effects(self):
        before = (self.root / 'configuration.json').read_bytes()
        with self.assertRaises(ValueError):
            sc.create_local_favorites_list(self.root, 'Empty', [['TargetModel', 'BCDx36HP']])
        with self.assertRaises(ValueError):
            sc.create_local_favorites_list(self.root, 'greenville county', *self.rows())
        self.assertEqual((self.root / 'configuration.json').read_bytes(), before)
        self.assertEqual(sorted(p.name for p in (self.root / 'BCDx36HP/favorites_lists').iterdir()),
                         ['f_000001.hpd', 'f_000002.hpd', 'f_list.cfg'])

    def test_failure_after_replace_rolls_everything_back(self):
        index_before = (self.root / sc.INDEX_KEY).read_bytes()
        manifest_before = (self.root / 'configuration.json').read_bytes()
        calls = {'n': 0}
        real = sc.verify_configuration

        def flaky(*args, **kwargs):
            calls['n'] += 1
            if calls['n'] >= 3:  # the verification inside _commit_files
                raise ValueError('simulated failure')
            return real(*args, **kwargs)
        with mock.patch.object(sc, 'verify_configuration', flaky):
            with self.assertRaises(ValueError):
                sc.create_local_favorites_list(self.root, 'Doomed', *self.rows())
        self.assertEqual((self.root / sc.INDEX_KEY).read_bytes(), index_before)
        self.assertEqual((self.root / 'configuration.json').read_bytes(), manifest_before)
        self.assertFalse((self.root / 'BCDx36HP/favorites_lists/f_000028.hpd').exists())
        self.assertTrue(real(self.root))

    def test_delete_removes_file_index_row_and_manifest_entry_and_archives(self):
        original = (self.root / 'BCDx36HP/favorites_lists/f_000002.hpd').read_bytes()
        sc.delete_local_favorites_list(self.root, 'BCDx36HP/favorites_lists/f_000002.hpd')
        self.assertTrue(sc.verify_configuration(self.root))
        index = (self.root / sc.INDEX_KEY).read_bytes().decode('cp1252')
        self.assertNotIn('f_000002.hpd', index)
        self.assertIn('f_000001.hpd', index)
        self.assertEqual(len(index.splitlines()), len(self.index_bytes.decode('cp1252').splitlines()) - 1)
        manifest = json.loads((self.root / 'configuration.json').read_text())
        self.assertNotIn('BCDx36HP/favorites_lists/f_000002.hpd', manifest['files'])
        self.assertFalse((self.root / 'BCDx36HP/favorites_lists/f_000002.hpd').exists())
        archive = self.library.parent / 'scanner-configuration-backups' / 'cfg' / 'deleted-lists'
        saved = list(archive.glob('f_000002.*.hpd'))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].read_bytes(), original)
        receipt = json.loads(saved[0].with_suffix('.json').read_text())
        self.assertEqual(len(receipt['f_list_rows']), 1)
        self.assertIn('SC Highway Patrol', receipt['f_list_rows'][0])

    def test_unregistered_or_unsafe_paths_refused(self):
        for bad in ('BCDx36HP/favorites_lists/f_999999.hpd', '../x.hpd', 'BCDx36HP/profile.cfg'):
            with self.assertRaises(ValueError):
                sc.delete_local_favorites_list(self.root, bad)

    def test_filename_of_a_pending_deletion_is_not_reused(self):
        sc.delete_local_favorites_list(self.root, 'BCDx36HP/favorites_lists/f_000002.hpd')
        result = sc.create_local_favorites_list(self.root, 'Again', *self.rows())
        self.assertEqual(result['filename'], 'f_000028.hpd')   # not f_000002: that deletion is still pending


class IntegrationSourceTests(unittest.TestCase):
    """GUI cannot run without PyQt6 here; check the wiring statically."""
    def test_standalone_create_menu_removed_and_dialog_wired(self):
        base = Path(__file__).resolve().parent
        manager = (base / 'database_favorites_manager.py').read_text()
        workspace = (base / 'database_workspace.py').read_text()
        self.assertNotIn('Create Favorites List…', manager)
        self.assertNotIn('create_favorites_list_in_configuration', manager)
        self.assertIn('new_list_hooks = self._new_list_hooks()', manager)
        self.assertIn('class AddDestinationDialog', workspace)
        self.assertIn('Create a new Favorites List with this selection', workspace)
        self.assertIn('self._add_to_new_list(section, new_list_name)', workspace)
        self.assertIn('del workspace.drafts[draft_name]', manager)


if __name__ == '__main__':
    unittest.main()
