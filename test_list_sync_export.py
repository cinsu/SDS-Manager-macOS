# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Export of NEW and DELETED Favorites Lists to an isolated mock scanner (real SDS100 sample files)."""
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scanner_configurations as sc
import scanner_first_write as writer
import scanner_list_sync as sync
from scanner_backup import backup_scanner as real_backup
from new_favorites_list import build_new_list_rows

FIX = Path(__file__).resolve().parent / 'test_fixtures'
DB = [l.split('\t') for l in (FIX / 'real_hpdb_greenville_county.txt').read_bytes().decode('cp1252').splitlines()]


def selection(groups=2):
    out, count = [DB[0]], 0
    for row in DB[1:]:
        if row[0] == 'C-Group':
            count += 1
            if count > groups:
                break
        if row[0] in ('C-Group', 'C-Freq'):
            out.append(row)
    return out


class SyncBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.scanner = self.base / 'mounted-scanner' / 'BCDx36HP'
        self.configs = self.base / 'configs'
        self.config = self.configs / 'test'
        self.local = self.config / 'BCDx36HP'
        for root in (self.scanner, self.local):
            (root / 'favorites_lists').mkdir(parents=True)
            (root / 'profile.cfg').write_bytes(b'Profile test')
            (root / 'scanner.inf').write_bytes(b'Scanner test')
            for name in ('f_000001.hpd', 'f_000002.hpd'):
                (root / 'favorites_lists' / name).write_bytes((FIX / ('real_sds100_' + name)).read_bytes())
            (root / 'favorites_lists' / 'f_list.cfg').write_bytes((FIX / 'real_sds100_f_list.cfg').read_bytes())
        self.refresh_manifest()
        self.evidence = {'status': 'USB_CORRELATED', 'vid': '1965', 'pid': '001c',
                         'manufacturer': 'UNIDEN AMERICA CORP.', 'product_name': 'SDS100',
                         'serial_present': True, 'filesystem': 'vfat',
                         'mountpoint': str(self.scanner.parent), 'mount_root': '/',
                         'source': '/dev/sdb1', 'device': '8:17'}
        patches = [
            patch.object(sc, 'library_path', lambda: self.configs),
            patch.object(writer, 'list_configurations', lambda: [(self.config, self.manifest())]),
            patch.object(writer, 'collect_identity_evidence', lambda scanner: self.evidence),
            patch.object(writer, 'backup_scanner', lambda path: real_backup(path, self.base / 'backups')),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def refresh_manifest(self):
        files = {}
        for f in self.local.rglob('*'):
            if f.is_file():
                files['BCDx36HP/' + f.relative_to(self.local).as_posix()] = {
                    'size': f.stat().st_size, 'sha256': hashlib.sha256(f.read_bytes()).hexdigest()}
        (self.config / 'configuration.json').write_text(json.dumps(
            {'format': 'sds100-configuration-snapshot-v1', 'name': 'Test', 'files': files}))

    def manifest(self):
        return json.loads((self.config / 'configuration.json').read_text())

    def create_list(self, name='Greenville education', groups=2):
        rows, enc, nl = build_new_list_rows(selection(groups))
        return sc.create_local_favorites_list(self.config, name, rows, enc, nl)

    def scanner_state(self):
        return {p.relative_to(self.scanner).as_posix(): p.read_bytes()
                for p in self.scanner.rglob('*') if p.is_file()}


class AddListTests(SyncBase):
    def test_new_list_and_index_row_are_written_with_verified_backup(self):
        created = self.create_list()
        before = self.scanner_state()
        ok, reason = writer.first_write_eligibility(self.config, self.scanner)
        self.assertTrue(ok, reason)
        self.assertIn('NEW Favorites List file', reason)
        result = writer.execute_first_write(self.config, self.scanner)
        after = self.scanner_state()
        new_name = 'favorites_lists/' + created['filename']
        self.assertEqual(result['added'], [new_name])
        self.assertEqual(after[new_name], (self.local / new_name).read_bytes())
        self.assertEqual(after['favorites_lists/f_list.cfg'], (self.local / 'favorites_lists/f_list.cfg').read_bytes())
        self.assertTrue(after['favorites_lists/f_list.cfg'].startswith(before['favorites_lists/f_list.cfg']))
        for name in before:   # nothing else changed
            if name != 'favorites_lists/f_list.cfg':
                self.assertEqual(after[name], before[name], name)
        backup = Path(result['backup'])
        self.assertEqual((backup / 'BCDx36HP/favorites_lists/f_list.cfg').read_bytes(), before['favorites_lists/f_list.cfg'])
        self.assertFalse((backup / 'BCDx36HP' / new_name).exists())
        self.assertIn('ADDED', (backup / 'EXPORT_RECOVERY.txt').read_text())

    def test_new_file_without_index_row_is_refused(self):
        created = self.create_list()
        shutil.copyfile(FIX / 'real_sds100_f_list.cfg', self.local / 'favorites_lists/f_list.cfg')
        self.refresh_manifest()
        ok, reason = writer.first_write_eligibility(self.config, self.scanner)
        self.assertFalse(ok)
        self.assertIn('f_list.cfg', reason)
        self.assertEqual(created['filename'], 'f_000028.hpd')

    def test_index_row_that_takes_an_existing_quick_key_is_refused(self):
        self.create_list()
        index = self.local / 'favorites_lists/f_list.cfg'
        lines = index.read_bytes().decode('cp1252').split('\r\n')
        fields = lines[-2].split('\t')
        fields[5] = '0'                 # Greenville County already owns quick key 0
        lines[-2] = '\t'.join(fields)
        index.write_bytes('\r\n'.join(lines).encode('cp1252'))
        self.refresh_manifest()
        ok, reason = writer.first_write_eligibility(self.config, self.scanner)
        self.assertFalse(ok)
        self.assertIn('share quick key', reason)

    def test_new_list_with_invalid_content_is_refused(self):
        created = self.create_list()
        path = self.local / 'favorites_lists' / created['filename']
        path.write_bytes(path.read_bytes().replace(b'\tFM\t', b'\tXX\t', 1))
        self.refresh_manifest()
        ok, reason = writer.first_write_eligibility(self.config, self.scanner)
        self.assertFalse(ok)
        self.assertIn('modulation', reason)

    def test_failure_midway_removes_the_new_file_and_restores_the_index(self):
        self.create_list()
        before = self.scanner_state()
        real = writer._stage_and_replace
        calls = {'n': 0}

        def fail_on_index(destination, payload, expected):
            calls['n'] += 1
            if destination.name == 'f_list.cfg':
                raise OSError('injected index failure')
            return real(destination, payload, expected)
        with patch.object(writer, '_stage_and_replace', fail_on_index):
            with self.assertRaisesRegex(writer.FirstWriteError, 'restored from verified backup'):
                writer.execute_first_write(self.config, self.scanner)
        self.assertEqual(self.scanner_state(), before)


class DeleteListTests(SyncBase):
    def test_deleted_list_is_removed_from_scanner_and_index(self):
        sc.delete_local_favorites_list(self.config, 'BCDx36HP/favorites_lists/f_000002.hpd')
        self.refresh_manifest()
        before = self.scanner_state()
        ok, reason = writer.first_write_eligibility(self.config, self.scanner)
        self.assertTrue(ok, reason)
        self.assertIn('REMOVED', reason)
        result = writer.execute_first_write(self.config, self.scanner)
        after = self.scanner_state()
        self.assertEqual(result['removed'], ['favorites_lists/f_000002.hpd'])
        self.assertNotIn('favorites_lists/f_000002.hpd', after)
        self.assertNotIn(b'f_000002.hpd', after['favorites_lists/f_list.cfg'])
        self.assertEqual(after['favorites_lists/f_000001.hpd'], before['favorites_lists/f_000001.hpd'])
        backup = Path(result['backup'])
        self.assertEqual((backup / 'BCDx36HP/favorites_lists/f_000002.hpd').read_bytes(),
                         before['favorites_lists/f_000002.hpd'])
        # the deletion is spent: it can never be applied a second time
        ok, reason = writer.first_write_eligibility(self.config, self.scanner)
        self.assertFalse(ok)
        self.assertIn('No changed', reason)

    def test_preview_lists_the_removal_separately_from_retained_files(self):
        import scanner_export_preview as preview
        sc.delete_local_favorites_list(self.config, 'BCDx36HP/favorites_lists/f_000002.hpd')
        self.refresh_manifest()
        extra = self.scanner / 'favorites_lists/f_000099.hpd'
        extra.write_bytes(b'TargetModel\tBCDx36HP\r\n')
        with patch.object(preview, 'list_configurations', lambda: [(self.config, self.manifest())]):
            report, results, _ = preview.preview_export(self.config, self.scanner, compact=True)
        self.assertRegex(report, r'(?m)^REMOVE FROM SCANNER: 1')
        self.assertRegex(report, r'(?m)^RETAIN ON SCANNER: 1$')
        self.assertIn('  favorites_lists/f_000002.hpd', report)
        self.assertIn('  favorites_lists/f_000099.hpd', report)

    def test_scanner_copy_that_differs_from_what_was_deleted_is_kept(self):
        sc.delete_local_favorites_list(self.config, 'BCDx36HP/favorites_lists/f_000002.hpd')
        self.refresh_manifest()
        scanner_copy = self.scanner / 'favorites_lists/f_000002.hpd'
        scanner_copy.write_bytes(scanner_copy.read_bytes() + b'TGID\r\n')   # edited on the scanner since
        before = self.scanner_state()
        ok, reason = writer.first_write_eligibility(self.config, self.scanner)
        self.assertFalse(ok)
        self.assertEqual(self.scanner_state(), before)

    def test_scanner_only_list_never_deleted_without_a_record(self):
        # local config simply lacks a list the scanner has (e.g. an older snapshot)
        (self.local / 'favorites_lists/f_000002.hpd').unlink()
        self.refresh_manifest()
        before = self.scanner_state()
        ok, reason = writer.first_write_eligibility(self.config, self.scanner)
        self.assertFalse(ok)
        self.assertEqual(self.scanner_state(), before)

    def test_failure_while_removing_restores_everything(self):
        sc.delete_local_favorites_list(self.config, 'BCDx36HP/favorites_lists/f_000002.hpd')
        self.refresh_manifest()
        before = self.scanner_state()
        with patch.object(writer, '_remove_file', side_effect=OSError('injected removal failure')):
            with self.assertRaisesRegex(writer.FirstWriteError, 'restored from verified backup'):
                writer.execute_first_write(self.config, self.scanner)
        self.assertEqual(self.scanner_state(), before)
        self.assertTrue(sync.recorded_deletions(self.config))   # still pending, not marked exported

    def test_add_and_delete_in_one_export(self):
        sc.delete_local_favorites_list(self.config, 'BCDx36HP/favorites_lists/f_000002.hpd')
        created = self.create_list()
        self.assertNotEqual(created['filename'], 'f_000002.hpd')
        self.refresh_manifest()
        result = writer.execute_first_write(self.config, self.scanner)
        after = self.scanner_state()
        self.assertEqual(result['added'], ['favorites_lists/' + created['filename']])
        self.assertEqual(result['removed'], ['favorites_lists/f_000002.hpd'])
        self.assertIn('favorites_lists/' + created['filename'], after)
        self.assertNotIn('favorites_lists/f_000002.hpd', after)
        self.assertEqual(after['favorites_lists/f_list.cfg'], (self.local / 'favorites_lists/f_list.cfg').read_bytes())


class AssessTests(unittest.TestCase):
    def test_unknown_records_are_refused_and_real_trunk_list_accepted(self):
        trunk = (FIX / 'real_sds100_f_000002.hpd').read_bytes()
        self.assertTrue(sync.assess_new_hpd(trunk)[0])
        odd = trunk.replace(b'\r\nTGID', b'\r\nTGIDX', 1)
        self.assertFalse(sync.assess_new_hpd(odd)[0])

    def test_generated_list_is_accepted(self):
        rows, _, _ = build_new_list_rows(selection())
        raw = ('\r\n'.join('\t'.join(r) for r in rows) + '\r\n').encode('cp1252')
        self.assertTrue(sync.assess_new_hpd(raw)[0])

    def test_index_rejects_changed_filenames_and_accepts_a_new_order(self):
        old = (FIX / 'real_sds100_f_list.cfg').read_bytes()
        renamed_file = old.replace(b'f_000001.hpd', b'f_000099.hpd', 1)
        ok, detail, _ = sync.assess_flist_replacement(old, renamed_file, [], [])
        self.assertFalse(ok)
        lines = old.split(b'\r\n')
        swapped = b'\r\n'.join(lines[:2] + [lines[3], lines[2]] + lines[4:])
        self.assertTrue(sync.assess_flist_replacement(old, swapped, [], [])[0])      # v0.1.7: reorder
        dropped = b'\r\n'.join(lines[:2] + lines[3:])
        self.assertFalse(sync.assess_flist_replacement(old, dropped, [], [])[0])
        twice = b'\r\n'.join(lines[:3] + [lines[2]] + lines[3:])
        self.assertFalse(sync.assess_flist_replacement(old, twice, [], [])[0])


if __name__ == '__main__':
    unittest.main()
