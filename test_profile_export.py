# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
import unittest
from scanner_profile_export import assess_profile_replacement
from quick_keys_settings import patch_quick_keys
from location_settings import patch_profile

BASE = (b'QuickKeys\t' + b'\t'.join([b'On']*100) + b'\r\n'
        b'CurrentLocation\t33.000000\t-84.000000\t10\r\n'
        b'GpsOption\tDEG\t4800\r\n'
        b'InterestingLocation\tHome\t33.000000\t-84.000000\t10\r\n'
        b'Unrelated\tPreserveExactly\r\n')

class ProfileExportTests(unittest.TestCase):
    def test_quick_keys(self):
        statuses=[True]*100;statuses[0]=False
        self.assertTrue(assess_profile_replacement(BASE,patch_quick_keys(BASE,statuses))[0])
    def test_location(self):
        new=patch_profile(BASE,['34','-84','10'],['DEG','4800'],[['Home','33','-84','10']])
        self.assertTrue(assess_profile_replacement(BASE,new)[0])
    def test_combined(self):
        statuses=[True]*100;statuses[1]=False
        new=patch_profile(patch_quick_keys(BASE,statuses),['34','-84','10'],['DEG','4800'],[['Home','33','-84','10']])
        self.assertTrue(assess_profile_replacement(BASE,new)[0])
    def test_unsupported_record_blocked(self):
        self.assertFalse(assess_profile_replacement(BASE,BASE.replace(b'PreserveExactly',b'Changed'))[0])
    def test_malformed_blocked(self):
        self.assertFalse(assess_profile_replacement(b'bad',b'changed')[0])
