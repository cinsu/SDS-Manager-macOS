# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Offline-only safety rehearsal tests. No physical scanner or scanner writes."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scanner_staging_rehearsal import rehearse_staging


# A second file system for the staging area: /dev/shm on Linux, a RAM disk from run-tests-mac.sh on macOS.
ALT_FS = os.environ.get('SDS_TEST_ALT_FS', '/dev/shm')


@unittest.skipUnless(os.path.isdir(ALT_FS), 'no second file system for staging (use run-tests-mac.sh on macOS)')
class StagingRehearsalTests(unittest.TestCase):
    def fixture(self, base):
        scanner = base/'scanner'/'BCDx36HP'
        local = base/'config'/'BCDx36HP'
        (scanner/'favorites_lists').mkdir(parents=True)
        (local/'favorites_lists').mkdir(parents=True)
        old = scanner/'favorites_lists'/'f_000001.hpd'
        old.write_bytes(b'C-Freq\tOriginal\r\n')
        replacement = local/'favorites_lists'/'f_000001.hpd'
        replacement.write_bytes(b'C-Freq\tChanged\r\n')
        added = local/'favorites_lists'/'f_000002.hpd'
        added.write_bytes(b'C-Freq\tNew\r\n')
        source = {'favorites_lists/f_000001.hpd': replacement,
                  'favorites_lists/f_000002.hpd': added}
        target = {'favorites_lists/f_000001.hpd': old}
        changes = {'ADD':['favorites_lists/f_000002.hpd'],
                   'REPLACE':['favorites_lists/f_000001.hpd'],
                   'UNCHANGED':[], 'RETAIN ON SCANNER':[]}
        return scanner, source, target, changes

    def test_success_and_injected_failure_rollback_no_scanner_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            scanner, source, target, changes = self.fixture(Path(tmp))
            originals = {p:p.read_bytes() for p in target.values()}
            report, ok = rehearse_staging(scanner,source,target,changes,workspace_base=ALT_FS)
            self.assertTrue(ok, report)
            self.assertIn('Injected interruption and simulated rollback: PASSED', report)
            self.assertIn('Scanner writes: 0', report)
            self.assertIn('Export authorization: BLOCKED', report)
            self.assertEqual(originals,{p:p.read_bytes() for p in target.values()})
            self.assertFalse((scanner/'favorites_lists'/'f_000002.hpd').exists())

    def test_workspace_on_scanner_filesystem_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            scanner, source, target, changes = self.fixture(Path(tmp))
            report, ok = rehearse_staging(scanner,source,target,changes,workspace_base=tmp)
            self.assertFalse(ok)
            self.assertIn('shares the scanner filesystem', report)

    def test_casefold_collision_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            scanner, source, target, changes = self.fixture(Path(tmp))
            source['favorites_lists/F_000001.hpd'] = source['favorites_lists/f_000001.hpd']
            report, ok = rehearse_staging(scanner,source,target,changes,workspace_base=ALT_FS)
            self.assertFalse(ok)
            self.assertIn('Case-insensitive filename collision', report)

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            scanner, source, target, changes = self.fixture(Path(tmp))
            source['favorites_lists/f_000002.hpd'].unlink()
            source['favorites_lists/f_000002.hpd'].symlink_to(source['favorites_lists/f_000001.hpd'])
            report, ok = rehearse_staging(scanner,source,target,changes,workspace_base=ALT_FS)
            self.assertFalse(ok)
            self.assertIn('Symlink', report)

    def test_empty_change_plan_is_explicitly_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            scanner, source, target, changes = self.fixture(Path(tmp))
            changes['ADD'] = []
            changes['REPLACE'] = []
            report, ok = rehearse_staging(scanner,source,target,changes,workspace_base=ALT_FS)
            self.assertTrue(ok, report)
            self.assertIn('actual-file rehearsal skipped', report)

    def test_mismatched_change_plan_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            scanner, source, target, changes = self.fixture(Path(tmp))
            changes['ADD'] = ['favorites_lists/f_000001.hpd']
            changes['REPLACE'] = []
            report, ok = rehearse_staging(scanner,source,target,changes,workspace_base=ALT_FS)
            self.assertFalse(ok)
            self.assertIn('ADD plan does not match', report)

    def test_insufficient_space_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            scanner, source, target, changes = self.fixture(Path(tmp))
            from collections import namedtuple
            Usage = namedtuple('Usage', 'total used free')
            with patch('scanner_staging_rehearsal.shutil.disk_usage', return_value=Usage(100,99,1)):
                report, ok = rehearse_staging(scanner,source,target,changes,workspace_base=ALT_FS)
            self.assertFalse(ok)
            self.assertIn('Insufficient free space', report)

if __name__ == '__main__': unittest.main()
