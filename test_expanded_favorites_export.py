# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""v0.0.7o: bounded native Favorites changes and real write engine on local mock."""
from pathlib import Path
import unittest
from scanner_favorites_expanded import assess_expanded_hpd_replacement as assess
from test_first_scanner_write import FirstWriteTests, hpd


def rows(raw):
    return raw.splitlines(keepends=True)


def insert_leaf(raw, kind, new_freq):
    lines = rows(raw)
    index = next(i for i,line in enumerate(lines) if line.startswith(kind+b'\t'))
    old = lines[index].rstrip(b'\r\n').split(b'\t')
    new = old[:]
    new[1] = {b'C-Freq':b'CFreqId=0', b'T-Freq':old[1], b'TGID':b'TgidId=0'}[kind]
    new[5] = new_freq
    return b''.join(lines[:index+1] + [b'\t'.join(new)+b'\r\n'] + lines[index+1:])


class ExpandedValidatorTests(unittest.TestCase):
    def test_multiple_field_edits(self):
        old=hpd()
        new=old.replace(b'155000000',b'155012500').replace(b'TEST CHANNEL',b'EDITED CHANNEL')
        passed,reason,counts=assess(old,new)
        self.assertTrue(passed,reason)
        self.assertEqual(counts, {'field_edits':2,'added':0,'deleted':0})

    def test_one_conventional_channel_delete(self):
        old=hpd()
        new=b''.join(line for line in rows(old) if not line.startswith(b'C-Freq\t'))
        # An empty conventional department remains valid (not a trunked site).
        passed,reason,counts=assess(old,new)
        self.assertTrue(passed,reason)
        self.assertEqual(counts['deleted'],1)

    def test_conventional_add_from_existing_template(self):
        old=hpd()
        new=insert_leaf(old,b'C-Freq',b'155250000')
        passed,reason,counts=assess(old,new)
        self.assertTrue(passed,reason)
        self.assertEqual(counts['added'],1)

    def test_bad_new_record_id_rejected(self):
        old=hpd()
        new=insert_leaf(old,b'C-Freq',b'155250000').replace(b'CFreqId=0',b'CFreqId=12345')
        self.assertFalse(assess(old,new)[0])

    def test_header_and_opaque_edit_rejected(self):
        old=hpd()
        self.assertFalse(assess(old.replace(b'1.00',b'2.00'),old)[0])
        self.assertFalse(assess(old,old.replace(b'BCDx36HP',b'BCDx36XP'))[0])
        self.assertFalse(assess(old,old.replace(b'C-Group',b'T-Group'))[0])

    def test_unsupported_group_deletion_rejected(self):
        old=hpd()
        new=b''.join(line for line in rows(old) if not line.startswith(b'C-Group\t'))
        self.assertFalse(assess(old,new)[0])

    def test_mixed_edit_and_add_rejected(self):
        old=hpd()
        new=insert_leaf(old,b'C-Freq',b'155250000').replace(b'TEST CHANNEL',b'NEW CHANNEL')
        self.assertFalse(assess(old,new)[0])

    def test_tfreq_added_on_genuine_eight_column_layout(self):
        path=Path('/mnt/data/f_000003.hpd')
        if not path.is_file(): self.skipTest('Optional native fixture absent')
        old=path.read_bytes()
        new=insert_leaf(old,b'T-Freq',b'855125000')
        passed,reason,counts=assess(old,new)
        self.assertTrue(passed,reason)
        self.assertEqual(counts['added'],1)

    def test_real_hpd_delete_and_add(self):
        path=Path('/mnt/data/s_000045_experimental.hpd')
        if not path.is_file(): self.skipTest('Optional native fixture absent')
        old=path.read_bytes()
        new=insert_leaf(old,b'C-Freq',b'155285000')
        self.assertTrue(assess(old,new)[0])
        index=next(i for i,line in enumerate(rows(old)) if line.startswith(b'C-Freq\t'))
        self.assertTrue(assess(old,b''.join(rows(old)[:index]+rows(old)[index+1:]))[0])

    def test_last_site_frequency_rejected(self):
        prefix=b'TargetModel\tBCDx36HP\r\nFormatVersion\t1.00\r\nTrunk\t\t\tSystem\r\nSite\t\t\tSite\r\n'
        site=b'T-Freq\t\t\t\tOff\t851312500\t1\tSrch\r\n'
        self.assertFalse(assess(prefix+site,prefix)[0])

    def test_unsupported_control_bytes(self):
        old=hpd()
        self.assertFalse(assess(old,old.replace(b'TEST CHANNEL',b'bad\x00name'))[0])

    def test_gui_accepts_native_eight_column_site_frequency_template(self):
        source=(Path(__file__).parent/'favorites_settings_window.py').read_text()
        self.assertIn('if len(template) not in (8, 9):',source)
        self.assertIn('new_record[1] = template[1]',source)


class ExpandedActualWriteTests(unittest.TestCase):
    """Reuse the isolated mounted-filesystem setup, without rerunning old tests."""
    setUp = FirstWriteTests.setUp
    _refresh_manifest = FirstWriteTests._refresh_manifest
    def test_structural_deletion_is_written_and_backed_up(self):
        self.local_file.write_bytes(b''.join(line for line in rows(self.original) if not line.startswith(b'C-Freq\t')))
        self._refresh_manifest()
        result=__import__('scanner_first_write').execute_first_write(self.local_config,self.scanner)
        self.assertEqual(self.scanner_file.read_bytes(),self.local_file.read_bytes())
        self.assertEqual(result['changes']['deleted'],1)
        self.assertEqual((Path(result['backup'])/'BCDx36HP/favorites_lists/f_000001.hpd').read_bytes(),self.original)

    def test_structural_addition_is_written_and_backed_up(self):
        self.local_file.write_bytes(insert_leaf(self.original,b'C-Freq',b'155250000'))
        self._refresh_manifest()
        result=__import__('scanner_first_write').execute_first_write(self.local_config,self.scanner)
        self.assertEqual(self.scanner_file.read_bytes(),self.local_file.read_bytes())
        self.assertEqual(result['changes']['added'],1)


if __name__ == '__main__': unittest.main()
