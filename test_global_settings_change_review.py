# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
import unittest
from scanner_global_settings import describe_global_changes

class ChangeReviewTests(unittest.TestCase):
    def test_exact_diff(self):
        data = b"GlobalSetting\tOff\tOff\t\tOff\tOff\tOff" + b"\t" * 15 + b"In Phase\r\n"
        result = describe_global_changes(data, {2: 'On', 21: 'Invert Phase'})
        self.assertEqual(len(result), 2)
        self.assertIn('Global Attenuator', result[0])
        self.assertIn('Headphone Audio Output Phase', result[1])
        self.assertIn('Invert Phase', result[1])
    def test_rejects_unsupported(self):
        with self.assertRaises(ValueError):
            describe_global_changes(b'GlobalSetting\tOff\n', {3: 'On'})

if __name__ == '__main__': unittest.main()
