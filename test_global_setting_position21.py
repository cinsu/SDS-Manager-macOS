# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
import unittest
from scanner_global_settings import GLOBAL_LABELS, EDITABLE_GLOBAL_CHOICES, read_global_setting, patch_global_setting

class Position21Tests(unittest.TestCase):
    def test_position21_label_and_choices(self):
        self.assertEqual(GLOBAL_LABELS[20], 'Headphone Audio Output Phase')
        self.assertEqual(EDITABLE_GLOBAL_CHOICES[21], ('In Phase', 'Invert Phase'))
    def test_preserved_when_editing_supported_field(self):
        original = b'GlobalSetting\t' + b'\t'.join([b'Off'] * 20 + [b'Invert Phase']) + b'\r\nOther\tdata\r\n'
        changed = patch_global_setting(original, {1: 'On'})
        self.assertEqual(read_global_setting(changed)[20], 'Invert Phase')
        self.assertTrue(changed.endswith(b'Other\tdata\r\n'))
    def test_reject_invalid_edit_to_position21(self):
        original = b'GlobalSetting\t' + b'\t'.join([b'Off'] * 20 + [b'Invert Phase']) + b'\n'
        with self.assertRaises(ValueError):
            patch_global_setting(original, {21: 'Normal Phase'})

    def test_exact_hardware_capture_roundtrip(self):
        from pathlib import Path
        a = Path('/mnt/data/profile(3).cfg')
        b = Path('/mnt/data/profile(4).cfg')
        if not (a.exists() and b.exists()):
            self.skipTest('Hardware capture files not supplied')
        invert = a.read_bytes()
        normal = b.read_bytes()
        self.assertEqual(read_global_setting(invert)[20], 'Invert Phase')
        self.assertEqual(read_global_setting(normal)[20], 'In Phase')
        self.assertEqual(patch_global_setting(invert, {21: 'In Phase'}), normal)
        self.assertEqual(patch_global_setting(normal, {21: 'Invert Phase'}), invert)

if __name__ == '__main__': unittest.main()
