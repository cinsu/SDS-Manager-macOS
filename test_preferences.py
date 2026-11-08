# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
import json
import tempfile
import unittest
from pathlib import Path

import preferences as pr


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'sub' / 'preferences.json'

    def test_defaults_when_missing_or_unreadable(self):
        self.assertEqual(pr.load(self.path), pr.DEFAULTS)
        self.path.parent.mkdir()
        self.path.write_text('{not json')
        self.assertEqual(pr.load(self.path), pr.DEFAULTS)
        self.path.write_text('[1,2]')
        self.assertEqual(pr.load(self.path), pr.DEFAULTS)

    def test_save_and_load_round_trip_is_atomic(self):
        values = dict(pr.DEFAULTS, backup_keep=7, theme='dark', auto_detect=False, font_size=12)
        pr.save(values, self.path)
        self.assertEqual(pr.load(self.path), values)
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ['preferences.json'])

    def test_invalid_values_fall_back_one_at_a_time(self):
        self.path.parent.mkdir()
        self.path.write_text(json.dumps({'backup_keep': 2, 'theme': 'dark', 'font_size': True, 'mystery': 1,
                                         'mount_folder': 'relative/path', 'auto_detect': 'yes'}))
        loaded = pr.load(self.path)
        self.assertEqual(loaded['theme'], 'dark')                       # the valid one is kept
        for key in ('backup_keep', 'font_size', 'mount_folder', 'auto_detect'):
            self.assertEqual(loaded[key], pr.DEFAULTS[key], key)
        self.assertNotIn('mystery', loaded)

    def test_save_refuses_invalid_values(self):
        for bad in ({'backup_keep': 1}, {'theme': 'neon'}, {'font_size': 99}, {'unknown': 1}, {'log_level': 'TRACE'}):
            with self.assertRaises(ValueError, msg=bad):
                pr.save(dict(pr.DEFAULTS, **bad), self.path)
        self.assertFalse(self.path.exists())

    def test_bool_is_not_accepted_as_int(self):
        self.assertFalse(pr.BY_KEY['backup_keep'].valid(True))

    def test_every_default_is_valid_and_no_write_safeguard_is_a_preference(self):
        for p in pr.PREFS:
            self.assertTrue(p.valid(p.default), p.key)
        forbidden = ('backup_before', 'skip', 'confirm_write', 'verify', 'rollback', 'identity')
        for p in pr.PREFS:
            self.assertFalse(any(word in p.key for word in forbidden), p.key)

    def test_symlink_and_oversized_files_are_ignored(self):
        self.path.parent.mkdir()
        real = self.path.parent / 'real.json'
        real.write_text(json.dumps({'theme': 'dark'}))
        self.path.symlink_to(real)
        self.assertEqual(pr.load(self.path)['theme'], 'system')
        self.path.unlink()
        self.path.write_text(' ' * 70000)
        self.assertEqual(pr.load(self.path), pr.DEFAULTS)

    def test_retired_coordinate_format_setting_is_ignored(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({'theme': 'dark', 'coordinate_format': 'dms'}))
        loaded = pr.load(self.path)
        self.assertEqual(loaded['theme'], 'dark')
        self.assertNotIn('coordinate_format', loaded)


if __name__ == '__main__':
    unittest.main()
