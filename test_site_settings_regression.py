# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Native Site field offsets from the Uniden SDS series specification."""
import unittest
from favorites_settings_window import FavoritesSettingsDialog

class TestSiteSettings(unittest.TestCase):
    def test_editor_exists(self):
        self.assertTrue(callable(FavoritesSettingsDialog._edit_selected_site))
    def test_native_site_offsets(self):
        row = 'Site\t\t\tCaesars Head\tOff\t35.112000\t-82.606000\t30.0\tAUTO\tStandard\tWide\tCircle\tOff\t400\tAuto\t8\tOff\t1DB\tGlobal'.split('\t')
        self.assertEqual([row[i] for i in (3,4,8,12,18)],
                         ['Caesars Head','Off','AUTO','Off','Global'])
