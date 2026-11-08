# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
import unittest
from scanner_profile_records import read_service_types, patch_service_types
from scanner_profile_export import assess_profile_replacement
from test_profile_export import BASE

ROW = b'ServiceType\t' + b'\t'.join([b'On'] * 37) + b'\r\n'
PROFILE = BASE + ROW

class ServiceTypeTests(unittest.TestCase):
    def test_roundtrip_preserves_bytes(self):
        self.assertEqual(patch_service_types(PROFILE, [True] * 37), PROFILE)
    def test_one_field_export(self):
        states = [True] * 37; states[2] = False
        updated = patch_service_types(PROFILE, states)
        self.assertEqual(len(read_service_types(updated)), 37)
        self.assertTrue(assess_profile_replacement(PROFILE, updated)[0])
    def test_combined_quick_key_and_service(self):
        from quick_keys_settings import patch_quick_keys
        states = [True] * 37; states[0] = False
        keys = [True] * 100; keys[0] = False
        updated = patch_quick_keys(patch_service_types(PROFILE, states), keys)
        self.assertTrue(assess_profile_replacement(PROFILE, updated)[0])
    def test_invalid_count_rejected(self):
        with self.assertRaises(ValueError): patch_service_types(PROFILE, [True]*36)
    def test_unrelated_edit_rejected(self):
        self.assertFalse(assess_profile_replacement(PROFILE, PROFILE.replace(b'PreserveExactly', b'Changed'))[0])
    def test_added_record_rejected(self):
        self.assertFalse(assess_profile_replacement(BASE, PROFILE)[0])

if __name__ == '__main__': unittest.main()
