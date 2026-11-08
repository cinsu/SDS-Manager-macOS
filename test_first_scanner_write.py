# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Isolated filesystem tests for actual first-write code; no USB scanner needed."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scanner_first_write as writer
from scanner_backup import backup_scanner as real_backup


def hpd(freq='155000000'):
    fields = [''] * 18
    fields[0] = 'C-Freq'
    fields[3] = 'TEST CHANNEL'
    fields[4] = 'Off'
    fields[5] = freq
    fields[6] = 'Auto'
    return ('TargetModel\tBCDx36HP\r\nFormatVersion\t1.00\r\n' +
            'Conventional\t\t\tTest System\r\n' +
            'C-Group\t\t\tTest Department\r\n' +
            '\t'.join(fields) + '\r\n').encode('ascii')


class FirstWriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.scanner = self.base/'mounted-scanner'/'BCDx36HP'
        self.local_config = self.base/'configs'/'test'
        self.local = self.local_config/'BCDx36HP'
        self.scanner_file = self.scanner/'favorites_lists'/'f_000001.hpd'
        self.local_file = self.local/'favorites_lists'/'f_000001.hpd'
        for folder in (self.scanner_file.parent, self.local_file.parent):
            folder.mkdir(parents=True)
        self.original = hpd()
        self.proposed = hpd('155002500')
        self.scanner_file.write_bytes(self.original)
        self.local_file.write_bytes(self.proposed)
        for root in (self.scanner, self.local):
            (root/'profile.cfg').write_bytes(b'Profile test')
            (root/'scanner.inf').write_bytes(b'Scanner test')
        files = {}
        for f in self.local.rglob('*'):
            if f.is_file():
                files['BCDx36HP/' + f.relative_to(self.local).as_posix()] = {
                    'size':f.stat().st_size, 'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
        self.manifest = {'format':'sds100-configuration-snapshot-v1','name':'Test','files':files}
        (self.local_config/'configuration.json').write_text(json.dumps(self.manifest))
        self.evidence = {'status':'USB_CORRELATED', 'vid':'1965', 'pid':'001c',
                         'manufacturer':'UNIDEN AMERICA CORP.', 'product_name':'SDS100',
                         'serial_present':True, 'filesystem':'vfat',
                         'mountpoint':str(self.scanner.parent), 'mount_root':'/',
                         'source':'/dev/sdb1', 'device':'8:17'}
        self.patches = [
            patch.object(writer, 'list_configurations', lambda: [(self.local_config,self.manifest)]),
            patch.object(writer, 'collect_identity_evidence', lambda scanner: self.evidence),
            patch.object(writer, 'backup_scanner', lambda path: real_backup(path, self.base/'backups')),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_first_write_and_verified_full_backup(self):
        eligible, reason = writer.first_write_eligibility(self.local_config, self.scanner)
        self.assertTrue(eligible, reason)
        result = writer.execute_first_write(self.local_config, self.scanner)
        self.assertEqual(self.scanner_file.read_bytes(), self.proposed)
        backup = Path(result['backup'])
        self.assertEqual((backup/'BCDx36HP/favorites_lists/f_000001.hpd').read_bytes(),self.original)
        self.assertTrue((backup/'manifest.json').is_file())
        self.assertTrue((backup/'EXPORT_RECOVERY.txt').is_file())
        self.assertTrue((backup/'EXPORT_RESULT.json').is_file())
        self.assertEqual(writer.first_write_eligibility(self.local_config, self.scanner)[0],False)

    def test_structural_change_blocked_without_writing(self):
        self.local_file.write_bytes(self.proposed + self.original)
        self._refresh_manifest()
        with self.assertRaisesRegex(ValueError, 'Unsupported Favorites HPD change'):
            writer.prepare_first_write(self.local_config, self.scanner)
        self.assertEqual(self.scanner_file.read_bytes(), self.original)

    def test_unknown_usb_blocked(self):
        self.evidence['pid'] = '9999'
        self.assertFalse(writer.first_write_eligibility(self.local_config, self.scanner)[0])
        with self.assertRaises(ValueError):
            writer.execute_first_write(self.local_config, self.scanner)
        self.assertEqual(self.scanner_file.read_bytes(), self.original)

    def test_bad_local_checksum_blocked(self):
        self.local_file.write_bytes(hpd('155005000'))
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            writer.prepare_first_write(self.local_config, self.scanner)

    def test_backup_failure_blocks_write(self):
        with patch.object(writer, 'backup_scanner', side_effect=OSError('backup unavailable')):
            with self.assertRaises(writer.FirstWriteError):
                writer.execute_first_write(self.local_config, self.scanner)
        self.assertEqual(self.scanner_file.read_bytes(),self.original)

    def test_destination_changes_during_backup_blocks_write(self):
        def altered_backup(path):
            backup = real_backup(path, self.base/'backups')
            self.scanner_file.write_bytes(hpd('155010000'))
            return backup
        with patch.object(writer, 'backup_scanner', side_effect=altered_backup):
            with self.assertRaisesRegex(writer.FirstWriteError, 'changed during backup'):
                writer.execute_first_write(self.local_config, self.scanner)
        self.assertEqual(self.scanner_file.read_bytes(), hpd('155010000'))

    def test_failed_postwrite_verify_rolls_back(self):
        real_stage = writer._stage_and_replace
        calls = []
        def corrupt_after_replace(dest,payload,expected):
            calls.append(True)
            if len(calls)==1:
                dest.write_bytes(b'corrupted')
                raise OSError('injected post-write failure')
            return real_stage(dest,payload,expected)
        with patch.object(writer, '_stage_and_replace', side_effect=corrupt_after_replace):
            with self.assertRaisesRegex(writer.FirstWriteError, 'original HPD restored'):
                writer.execute_first_write(self.local_config, self.scanner)
        self.assertEqual(self.scanner_file.read_bytes(),self.original)
        self.assertEqual(len(calls),2)

    def test_non_hpd_change_blocked(self):
        (self.local/'profile.cfg').write_bytes(b'Other')
        self._refresh_manifest()
        with self.assertRaisesRegex(ValueError, 'Only existing native Favorites HPD'):
            writer.prepare_first_write(self.local_config, self.scanner)

    def _add_second_hpd(self):
        scanner_second = self.scanner_file.with_name('f_000002.hpd')
        local_second = self.local_file.with_name('f_000002.hpd')
        scanner_second.write_bytes(hpd('162000000'))
        local_second.write_bytes(hpd('162002500'))
        self._refresh_manifest()
        return scanner_second, local_second

    def test_two_hpd_batch_write(self):
        second, proposed = self._add_second_hpd()
        eligible, detail = writer.first_write_eligibility(self.local_config, self.scanner)
        self.assertTrue(eligible, detail)
        self.assertIn('2 existing Favorites HPD', detail)
        result = writer.execute_first_write(self.local_config, self.scanner)
        self.assertEqual(len(result['files']), 2)
        self.assertEqual(self.scanner_file.read_bytes(), self.proposed)
        self.assertEqual(second.read_bytes(), proposed.read_bytes())
        self.assertEqual((Path(result['backup'])/'BCDx36HP/favorites_lists/f_000002.hpd').read_bytes(),hpd('162000000'))

    def test_second_file_failure_rolls_back_first(self):
        second, _ = self._add_second_hpd()
        original_second = second.read_bytes()
        real_stage = writer._stage_and_replace
        calls = []
        def fail_second(dest, payload, expected):
            calls.append(dest)
            if len(calls) == 2:
                raise OSError('injected second-file failure')
            return real_stage(dest, payload, expected)
        with patch.object(writer, '_stage_and_replace', side_effect=fail_second):
            with self.assertRaisesRegex(writer.FirstWriteError, 'restored from verified backup'):
                writer.execute_first_write(self.local_config, self.scanner)
        self.assertEqual(self.scanner_file.read_bytes(), self.original)
        self.assertEqual(second.read_bytes(), original_second)

    def test_second_file_invalid_blocks_all_writes(self):
        second, local_second = self._add_second_hpd()
        local_second.write_bytes(b'not an HPD')
        self._refresh_manifest()
        with self.assertRaises(ValueError):
            writer.prepare_first_write(self.local_config, self.scanner)
        self.assertEqual(self.scanner_file.read_bytes(), self.original)
        self.assertEqual(second.read_bytes(), hpd('162000000'))

    def _refresh_manifest(self):
        for f in self.local.rglob('*'):
            if f.is_file():
                key='BCDx36HP/' + f.relative_to(self.local).as_posix()
                self.manifest['files'][key]={'size':f.stat().st_size,
                                             'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
        (self.local_config/'configuration.json').write_text(json.dumps(self.manifest))

if __name__ == '__main__': unittest.main()
