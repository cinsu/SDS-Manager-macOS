# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Per-list settings in f_list.cfg: lossless editing, uniqueness, export guard and export."""
import unittest
from pathlib import Path

import flist_settings as fl
import scanner_list_sync as sync
import scanner_first_write as writer
import scanner_configurations as sc
from test_list_sync_export import SyncBase

FIX = Path(__file__).resolve().parent / 'test_fixtures'
REAL = (FIX / 'real_sds100_f_list.cfg').read_bytes()
LISTS = fl.read_lists(REAL)


def by_name(name):
    return next(l for l in LISTS if l['name'] == name)


class ModelTests(unittest.TestCase):
    def test_real_rows_are_valid(self):
        self.assertEqual(len(LISTS), 28)
        for l in LISTS:
            for position, value in ((fl.POS_NAME, l['name']), (fl.POS_LOCATION, l['location']),
                                    (fl.POS_MONITOR, l['monitor']), (fl.POS_QUICK, l['quick_key']),
                                    (fl.POS_TAG, l['number_tag'])):
                self.assertTrue(fl.valid_value(position, value), (l['name'], position, value))
            self.assertEqual(len(l['startup']), 10)
            self.assertEqual(len(l['system_keys']), 100)

    def test_patch_is_lossless_and_reversible(self):
        key = by_name('Rail')['filename']
        edits = {(key, fl.POS_NAME): 'Railroads', (key, fl.POS_LOCATION): 'On', (key, fl.POS_QUICK): '40',
                 (key, fl.POS_TAG): '12', (key, 7): 'On', (key, 20): 'On'}
        edited = fl.patch_lists(REAL, edits)
        self.assertEqual(edited.count(b'\r\n'), REAL.count(b'\r\n'))
        self.assertEqual(len(edited.splitlines()), len(REAL.splitlines()))
        new = fl.read_lists(edited)
        row = next(l for l in new if l['filename'] == key)
        self.assertEqual((row['name'], row['location'], row['quick_key'], row['number_tag']),
                         ('Railroads', 'On', '40', '12'))
        self.assertEqual(row['startup'][0], 'On')
        self.assertEqual(row['system_keys'][3], 'On')
        for other_old, other_new in zip(LISTS, new):
            if other_old['filename'] != key:
                self.assertEqual(other_old, other_new)
        reverse = {(key, p): v for (k, p), v in
                   fl.edits_between(new, LISTS).items()}
        self.assertEqual(fl.patch_lists(edited, reverse), REAL)

    def test_invalid_edits_refused(self):
        key = by_name('Rail')['filename']
        for position, value in ((fl.POS_NAME, ''), (fl.POS_NAME, 'x' * 65), (fl.POS_NAME, ' pad'),
                                (fl.POS_NAME, 'a\tb'), (fl.POS_NAME, 'café'), (fl.POS_LOCATION, 'Yes'),
                                (fl.POS_MONITOR, 'off'), (fl.POS_QUICK, '100'), (fl.POS_QUICK, '07'),
                                (fl.POS_QUICK, '-1'), (fl.POS_TAG, '100'), (fl.POS_TAG, 'x'), (7, '1'),
                                (116, 'Maybe'), (fl.POS_FILE, 'f_000099.hpd'), (117, 'x'), (0, 'x')):
            with self.assertRaises(ValueError, msg=(position, value)):
                fl.patch_lists(REAL, {(key, position): value})
        with self.assertRaises(ValueError):
            fl.patch_lists(REAL, {('f_999999.hpd', fl.POS_NAME): 'Nope'})
        with self.assertRaises(ValueError):
            fl.patch_lists(REAL, {})

    def test_two_lists_cannot_share_quick_key_number_tag_or_name(self):
        rail, spart = by_name('Rail')['filename'], by_name('Spartanburg County')
        with self.assertRaises(ValueError):
            fl.patch_lists(REAL, {(rail, fl.POS_QUICK): spart['quick_key']})
        tagged = fl.patch_lists(REAL, {(rail, fl.POS_TAG): '5'})
        with self.assertRaises(ValueError):
            fl.patch_lists(tagged, {(spart['filename'], fl.POS_TAG): '5'})
        with self.assertRaises(ValueError):
            fl.patch_lists(REAL, {(rail, fl.POS_NAME): 'spartanburg county'})
        # swapping two lists' keys in one edit is fine
        a = by_name('Spartanburg County')
        b = by_name('Pickens County')
        edited = fl.patch_lists(REAL, {(a['filename'], fl.POS_QUICK): b['quick_key'],
                                       (b['filename'], fl.POS_QUICK): a['quick_key']})
        self.assertEqual(next(l for l in fl.read_lists(edited) if l['name'] == 'Pickens County')['quick_key'],
                         a['quick_key'])

    def test_existing_duplicates_do_not_block_unrelated_edits(self):
        dup = REAL.replace(b'Pickens County\tf_000012.hpd\tOn\tOn\t2', b'Pickens County\tf_000012.hpd\tOn\tOn\t1', 1)
        self.assertNotEqual(dup, REAL)
        edited = fl.patch_lists(dup, {(by_name('Rail')['filename'], fl.POS_MONITOR): 'On'})
        self.assertNotEqual(edited, dup)

    def test_describe(self):
        key = by_name('Rail')['filename']
        text = fl.describe(LISTS, {(key, fl.POS_QUICK): '40', (key, 18): 'On'})
        self.assertIn("Quick Key: 'Off' → '40'", text[0])
        self.assertIn('System Quick Key 01', text[1])


class GuardTests(unittest.TestCase):
    def test_edit_only_change_is_authorised(self):
        key = by_name('Rail')['filename']
        edited = fl.patch_lists(REAL, {(key, fl.POS_QUICK): '40', (key, fl.POS_NAME): 'Railroads'})
        ok, detail, counts = sync.assess_flist_replacement(REAL, edited, [], [])
        self.assertTrue(ok, detail)
        self.assertEqual(counts, {'field_edits': 2, 'added': 0, 'deleted': 0})

    def test_bad_hand_edits_refused(self):
        spart = by_name('Spartanburg County')
        cases = {
            'duplicate quick key': REAL.replace(b'Rail\tf_000010.hpd\tOff\tOff\tOff',
                                                b'Rail\tf_000010.hpd\tOff\tOff\t' + spart['quick_key'].encode(), 1),
            'bad value': REAL.replace(b'Rail\tf_000010.hpd\tOff', b'Rail\tf_000010.hpd\tMaybe', 1),
            'lost field': REAL.replace(b'Rail\tf_000010.hpd\tOff\tOff\tOff\tOff', b'Rail\tf_000010.hpd\tOff\tOff\tOff', 1),
            'header change': REAL.replace(b'FormatVersion\t1.00', b'FormatVersion\t1.01', 1),
        }
        for name, proposed in cases.items():
            self.assertNotEqual(proposed, REAL, name)
            self.assertFalse(sync.assess_flist_replacement(REAL, proposed, [], [])[0], name)

    def test_edit_combined_with_added_row(self):
        key = by_name('Rail')['filename']
        edited = fl.patch_lists(REAL, {(key, fl.POS_QUICK): '40'})
        row = sc.new_flist_row(REAL.decode('cp1252').splitlines()[2].split('\t'), 'New list', 'f_000040.hpd')
        proposed = edited + ('\t'.join(row) + '\r\n').encode('cp1252')
        ok, detail, counts = sync.assess_flist_replacement(REAL, proposed, ['favorites_lists/f_000040.hpd'], [])
        self.assertTrue(ok, detail)
        self.assertEqual((counts['field_edits'], counts['added']), (1, 1))
        clash = edited + ('\t'.join(row[:5] + ['40'] + row[6:]) + '\r\n').encode('cp1252')
        self.assertFalse(sync.assess_flist_replacement(REAL, clash, ['favorites_lists/f_000040.hpd'], [])[0])


class ExportTests(SyncBase):
    def test_list_settings_are_exported_with_backup(self):
        key = by_name('Rail')['filename']
        edited = fl.patch_lists(REAL, {(key, fl.POS_QUICK): '40', (key, fl.POS_MONITOR): 'On'})
        (self.local / 'favorites_lists/f_list.cfg').write_bytes(edited)
        self.refresh_manifest()
        before = self.scanner_state()
        ok, reason = writer.first_write_eligibility(self.config, self.scanner)
        self.assertTrue(ok, reason)
        result = writer.execute_first_write(self.config, self.scanner)
        after = self.scanner_state()
        self.assertEqual(after['favorites_lists/f_list.cfg'], edited)
        self.assertEqual((Path(result['backup']) / 'BCDx36HP/favorites_lists/f_list.cfg').read_bytes(), REAL)
        for name in before:
            if name != 'favorites_lists/f_list.cfg':
                self.assertEqual(after[name], before[name], name)

    def test_invalid_list_settings_are_blocked(self):
        spart = by_name('Spartanburg County')
        bad = REAL.replace(b'Rail\tf_000010.hpd\tOff\tOff\tOff',
                           b'Rail\tf_000010.hpd\tOff\tOff\t' + spart['quick_key'].encode(), 1)
        (self.local / 'favorites_lists/f_list.cfg').write_bytes(bad)
        self.refresh_manifest()
        ok, reason = writer.first_write_eligibility(self.config, self.scanner)
        self.assertFalse(ok)
        self.assertEqual(self.scanner_state()['favorites_lists/f_list.cfg'], REAL)


if __name__ == '__main__':
    unittest.main()


class LocalSaveTests(unittest.TestCase):
    def setUp(self):
        import hashlib, json, tempfile
        from unittest import mock
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.library = Path(self.tmp.name) / 'scanner-configurations'
        self.root = self.library / 'cfg'
        (self.root / 'BCDx36HP/favorites_lists').mkdir(parents=True)
        (self.root / sc.INDEX_KEY).write_bytes(REAL)
        (self.root / 'configuration.json').write_text(json.dumps({
            'format': 'sds100-configuration-snapshot-v1', 'name': 'cfg',
            'files': {sc.INDEX_KEY: {'size': len(REAL), 'sha256': hashlib.sha256(REAL).hexdigest()}}}))
        patcher = mock.patch.object(sc, 'library_path', lambda: self.library)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_save_updates_index_manifest_and_keeps_backup(self):
        key = by_name('Rail')['filename']
        payload = sc.save_local_flist_settings(self.root, {(key, fl.POS_QUICK): '40'})
        self.assertEqual((self.root / sc.INDEX_KEY).read_bytes(), payload)
        self.assertTrue(sc.verify_configuration(self.root))
        backups = list((Path(self.tmp.name) / 'scanner-configuration-backups' / 'cfg').glob('f_list.*.cfg'))
        self.assertEqual([b.read_bytes() for b in backups], [REAL])

    def test_invalid_save_changes_nothing(self):
        spart = by_name('Spartanburg County')
        with self.assertRaises(ValueError):
            sc.save_local_flist_settings(self.root, {(by_name('Rail')['filename'], fl.POS_QUICK): spart['quick_key']})
        self.assertEqual((self.root / sc.INDEX_KEY).read_bytes(), REAL)
