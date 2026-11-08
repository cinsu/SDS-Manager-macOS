# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
import unittest
from scanner_global_settings import read_global_setting

class GlobalSettingTests(unittest.TestCase):
    def test_reads_fields_without_changes(self):
        payload = b"Version\t2\r\nGlobalSetting\tOn\t12\tOff\r\nServiceType\tOff\r\n"
        self.assertEqual(read_global_setting(payload), ('On', '12', 'Off'))
        self.assertIn(b"GlobalSetting\tOn\t12\tOff", payload)
    def test_missing_rejected(self):
        with self.assertRaises(ValueError): read_global_setting(b"Other\tOn\r\n")
    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError): read_global_setting(b"GlobalSetting\tOn\nGlobalSetting\tOff\n")
    def test_empty_field_preserved(self):
        self.assertEqual(read_global_setting(b"GlobalSetting\tOn\t\tOff\n"), ("On", "", "Off"))

if __name__ == '__main__': unittest.main()
