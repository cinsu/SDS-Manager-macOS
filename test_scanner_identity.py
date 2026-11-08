# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Linux mount-to-USB correlation tests: synthetic sysfs, no device writes."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scanner_identity import collect_identity_evidence, inspect_scanner_identity
from scanner_preflight import inspect_scanner


class ScannerIdentityTests(unittest.TestCase):
    def make_fixture(self, base, *, usb=True, mount_root='/', source='/dev/sdb1',
                     vid='1965', pid='0012', serial='PRIVATE-SERIAL-987'):
        mount = base/'media'/'USB scanner'; scanner = mount/'BCDx36HP'
        (scanner/'favorites_lists').mkdir(parents=True)
        (scanner/'favorites_lists'/'f_000001.hpd').write_bytes(b'C-Freq\tTest\r\n')
        (scanner/'profile.cfg').write_bytes(b'profile')
        sys = base/'sys'; usb_node=sys/'devices'/'pci'/'usb1'/'1-2'
        block = usb_node/'1-2:1.0'/'host0'/'target0:0:0'/'0:0:0:0'/'block'/'sdb'/'sdb1'
        block.mkdir(parents=True)
        devblock=sys/'dev'/'block'; devblock.mkdir(parents=True)
        (devblock/'8:17').symlink_to(block)
        if usb:
            (usb_node/'idVendor').write_text(vid)
            (usb_node/'idProduct').write_text(pid)
            (usb_node/'manufacturer').write_text('Example USB Device')
            (usb_node/'product').write_text('Mass Storage')
            (usb_node/'serial').write_text(serial)
        # mountinfo escapes whitespace as backslash-040
        mp=str(mount).replace(' ',r'\040')
        mountinfo=base/'mountinfo'
        mountinfo.write_text(f'91 50 8:17 {mount_root} {mp} rw,relatime - vfat {source} rw\n')
        return scanner, mountinfo, devblock

    def test_usb_correlated_but_not_authorized(self):
        with tempfile.TemporaryDirectory() as tmp:
            scanner,mi,sys=self.make_fixture(Path(tmp))
            e=collect_identity_evidence(scanner,mountinfo=mi,sys_dev_block=sys)
            self.assertEqual(e['status'],'USB_CORRELATED')
            self.assertEqual((e['vid'],e['pid']),('1965','0012'))
            report=inspect_scanner_identity(scanner,mountinfo=mi,sys_dev_block=sys)
            self.assertIn('Mounted USB device association: FOUND',report)
            self.assertIn('SDS100 model identity: NOT YET VERIFIED',report)
            self.assertIn('Export authorization: BLOCKED',report)
            self.assertNotIn('PRIVATE-SERIAL-987',report)

    def test_folder_alone_does_not_prove_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            scanner,mi,sys=self.make_fixture(Path(tmp),usb=False)
            e=collect_identity_evidence(scanner,mountinfo=mi,sys_dev_block=sys)
            self.assertEqual(e['status'],'NO_USB')
            self.assertIn('NOT ESTABLISHED',inspect_scanner_identity(scanner,mountinfo=mi,sys_dev_block=sys))

    def test_bind_mount_and_non_device_source_rejected(self):
        for kwargs in ({'mount_root':'/subfolder'}, {'source':'tmpfs'}):
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as tmp:
                scanner,mi,sys=self.make_fixture(Path(tmp),**kwargs)
                self.assertEqual(collect_identity_evidence(scanner,mountinfo=mi,sys_dev_block=sys)['status'],'NO_USB')

    def test_invalid_usb_ids_are_not_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            scanner,mi,sys=self.make_fixture(Path(tmp),vid='ZZZZ')
            self.assertEqual(collect_identity_evidence(scanner,mountinfo=mi,sys_dev_block=sys)['status'],'NO_USB')

    def test_structural_preflight_remains_valid_and_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            scanner,mi,sys=self.make_fixture(Path(tmp))
            before={p.relative_to(scanner):p.read_bytes() for p in scanner.rglob('*') if p.is_file()}
            with patch('scanner_preflight.inspect_scanner_identity',return_value='SYNTHETIC IDENTITY EVIDENCE'):
                report,ok=inspect_scanner(scanner)
            self.assertTrue(ok)
            self.assertIn('SYNTHETIC IDENTITY EVIDENCE',report)
            self.assertEqual(before,{p.relative_to(scanner):p.read_bytes() for p in scanner.rglob('*') if p.is_file()})

    def test_no_mountinfo_does_not_crash_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            scanner,mi,sys=self.make_fixture(Path(tmp))
            mi.unlink()
            report=inspect_scanner_identity(scanner,mountinfo=mi,sys_dev_block=sys)
            self.assertIn('NOT ESTABLISHED',report)
            self.assertIn('BLOCKED',report)

if __name__ == '__main__':
    unittest.main()
