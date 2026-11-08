# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import scanner_detect as sd


class DetectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def card(self, name, with_hpdb=True):
        root = self.base / name
        (root / 'BCDx36HP' / 'favorites_lists').mkdir(parents=True)
        (root / 'BCDx36HP' / 'scanner.inf').write_bytes(
            b'TargetModel\tBCDx36HP\r\nFormatVersion\t1.00\r\nScanner\tSDS100\t38326-000000000-000\t1.26.01 \t01\r\n')
        (root / 'BCDx36HP' / 'favorites_lists' / 'f_000001.hpd').write_bytes(b'x')
        (root / 'BCDx36HP' / 'favorites_lists' / 'f_list.cfg').write_bytes(b'x')
        if with_hpdb:
            (root / 'BCDx36HP' / 'HPDB').mkdir()
            (root / 'BCDx36HP' / 'HPDB' / 'hpdb.cfg').write_bytes(
                b'TargetModel\tBCDx36HP\r\nFormatVersion\t1.00\r\nDateModified\t10/25/2026 04:30:15\r\n')
        return root

    def proc(self, lines):
        path = self.base / 'mounts'
        path.write_text('\n'.join(lines) + '\n')
        return str(path)

    def test_only_fat_block_devices_with_a_bcdx36hp_folder_are_found(self):
        a, b, c = self.card('a'), self.card('b'), self.base / 'plain'
        c.mkdir()
        proc = self.proc([f'/dev/sdb1 {a} vfat rw 0 0', f'/dev/sdc1 {b} ext4 rw 0 0', f'/dev/sdd1 {c} vfat rw 0 0',
                          f'tmpfs {a} vfat rw 0 0', 'garbage'])
        hits = sd.find_scanners(proc=proc)
        self.assertEqual([h['mountpoint'] for h in hits], [str(a)])

    def test_preferred_folder_sorts_first_and_spaces_are_decoded(self):
        spaced = self.card('SD CARD')
        other = self.card('other')
        proc = self.proc([f'/dev/sdb1 {other} vfat rw 0 0', f'/dev/sdc1 {str(spaced).replace(" ", chr(92) + "040")} vfat rw 0 0'])
        hits = sd.find_scanners(str(self.base / 'SD CARD'), proc)
        self.assertEqual(hits[0]['mountpoint'], str(spaced))
        self.assertEqual(len(hits), 2)

    def test_summary(self):
        info = sd.summarize(self.card('a'))
        self.assertEqual((info['model'], info['firmware']), ('SDS100', '1.26.01'))
        self.assertEqual(info['database_date'], datetime(2026, 10, 25, 4, 30, 15))
        self.assertEqual(info['favorites_lists'], 1)
        self.assertGreater(info['free_bytes'], 0)
        self.assertEqual(info['warnings'], [])
        self.assertNotIn('38326', repr(info))                    # the serial-like field is never surfaced

    def test_missing_files_become_warnings_not_errors(self):
        info = sd.summarize(self.card('a', with_hpdb=False))
        self.assertIsNone(info['database_date'])
        self.assertTrue(info['warnings'])
        empty = self.base / 'empty'
        empty.mkdir()
        self.assertIsNone(sd.summarize(empty)['model'])

    def test_human_bytes(self):
        self.assertEqual(sd.human_bytes(500), '500 B')
        self.assertEqual(sd.human_bytes(1536), '1.5 KB')
        self.assertEqual(sd.human_bytes(None), 'unknown')


if __name__ == '__main__':
    unittest.main()
