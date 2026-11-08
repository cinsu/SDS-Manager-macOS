# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
import unittest
from scanner_profile_records import read_custom_service_types, patch_custom_service_types
from scanner_profile_export import assess_profile_replacement
from test_profile_service_types import PROFILE

BASE = PROFILE + b"CustomServiceType\t" + b"\t".join([b"On"] * 10) + b"\r\n"

class CustomServiceTests(unittest.TestCase):
    def test_roundtrip(self):
        self.assertEqual(patch_custom_service_types(BASE, [True]*10), BASE)
    def test_one_custom_edit_eligible(self):
        changed = patch_custom_service_types(BASE, [False] + [True]*9)
        self.assertTrue(assess_profile_replacement(BASE, changed)[0])
    def test_combined_edits(self):
        from scanner_profile_records import patch_service_types
        changed = patch_custom_service_types(patch_service_types(BASE, [False]+[True]*36), [False]+[True]*9)
        self.assertTrue(assess_profile_replacement(BASE, changed)[0])
    def test_bad_count(self):
        with self.assertRaises(ValueError): patch_custom_service_types(BASE, [True]*9)
    def test_addition_rejected(self):
        self.assertFalse(assess_profile_replacement(PROFILE, BASE)[0])
    def test_unrelated_change_rejected(self):
        self.assertFalse(assess_profile_replacement(BASE, BASE.replace(b"PreserveExactly", b"Altered"))[0])

if __name__ == '__main__': unittest.main()
