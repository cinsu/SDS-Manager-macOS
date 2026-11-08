# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
import unittest
from scanner_global_settings import read_global_setting, patch_global_setting
from scanner_profile_export import assess_profile_replacement

class GlobalEdits(unittest.TestCase):
    def test_lossless_patch_and_reject(self):
        data = b"GlobalSetting\tOff\tOff\t\tOff\tOff\tOff\t2\t100\tCustom1\tCustom2\tCustom3\tOff\tAuto\t6\t2\tOff\tOff\tIgnore\tNormal\t0\tInvert Phase\r\n"
        edited = patch_global_setting(data, {1:'On', 18:'Compare'})
        self.assertEqual(read_global_setting(edited)[20], 'Invert Phase')
        self.assertIn(b'\tOn\tOff\t\t', edited)
        self.assertEqual(patch_global_setting(edited, {1:'Off', 18:'Ignore'}), data)
        with self.assertRaises(ValueError): patch_global_setting(data, {21:'On'})
        with self.assertRaises(ValueError): patch_global_setting(data, {4:'Maybe'})

if __name__ == '__main__': unittest.main()
