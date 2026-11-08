# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import managed_storage as ms
import scanner_backup as sb


class BackupCleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        for day in range(1, 8):
            folder = self.base / f'202610{day:02d}T120000Z'
            (folder / 'BCDx36HP').mkdir(parents=True)
            (folder / 'manifest.json').write_text('{}')
            (folder / 'BCDx36HP' / 'x.hpd').write_bytes(b'x' * 100)
        (self.base / 'not-a-backup').mkdir()
        (self.base / '.backup-in-progress-abc').mkdir()
        (self.base / '20261009T120000Z').mkdir()               # right name but no manifest

    def test_only_real_backups_are_listed_and_sized(self):
        usage = sb.backup_usage(self.base)
        self.assertEqual((usage['count'], usage['newest']), (7, '20261007T120000Z'))
        self.assertGreaterEqual(usage['bytes'], 700)

    def test_cleanup_keeps_the_newest_and_never_fewer_than_three(self):
        self.assertEqual([b['name'] for b in sb.plan_prune(5, self.base)],
                         ['20261001T120000Z', '20261002T120000Z'])
        self.assertEqual(len(sb.plan_prune(1, self.base)), 4)            # 1 is raised to 3
        self.assertEqual(sb.plan_prune(50, self.base), [])

    def test_prune_deletes_only_what_the_fresh_plan_allows(self):
        removed = sb.prune_backups(['20261001T120000Z', '20261007T120000Z', 'not-a-backup', '../x'], 5, self.base)
        self.assertEqual(removed, ['20261001T120000Z'])
        remaining = sorted(p.name for p in self.base.iterdir())
        self.assertIn('20261007T120000Z', remaining)
        self.assertIn('not-a-backup', remaining)
        self.assertNotIn('20261001T120000Z', remaining)

    def test_symlinked_backup_is_not_followed(self):
        target = self.base / 'elsewhere'
        target.mkdir()
        (target / 'manifest.json').write_text('{}')
        (self.base / '20260930T120000Z').symlink_to(target)
        self.assertNotIn('20260930T120000Z', [b['name'] for b in sb.list_backups(self.base)])
        self.assertEqual(sb.prune_backups(['20260930T120000Z'], 3, self.base), [])
        self.assertTrue(target.exists())


class VersionCleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patcher = patch.object(ms, 'ROOT', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        (self.root / 'database' / 'versions').mkdir(parents=True)
        for n in range(1, 6):
            self.version(f'HPDB-Experimental-2026_0{n}_01', f'0{n}/01/2026 00:00:00')

    def version(self, name, date):
        folder = self.root / 'database' / 'versions' / name
        folder.mkdir()
        for i in range(68):
            (folder / f's_{i + 1:06d}.hpd').write_bytes(b'x')
        (folder / 'hpdb.cfg').write_bytes(f'TargetModel\tBCDx36HP\r\nFormatVersion\t1.00\r\nDateModified\t{date}\r\n'.encode())
        (folder / 'MasterHpdb.hp1').write_bytes(b'm')

    def names(self, paths):
        return [p.name for p in paths]

    def test_plan_keeps_the_newest_and_protects_current_and_scanner_versions(self):
        self.assertEqual(self.names(ms.plan_version_cleanup(2)),
                         ['HPDB-Experimental-2026_01_01', 'HPDB-Experimental-2026_02_01', 'HPDB-Experimental-2026_03_01'])
        (self.root / 'database' / 'current').symlink_to(Path('versions') / 'HPDB-Experimental-2026_01_01',
                                                         target_is_directory=True)
        from datetime import datetime
        plan = self.names(ms.plan_version_cleanup(2, {datetime(2026, 2, 1)}))
        self.assertEqual(plan, ['HPDB-Experimental-2026_03_01'])

    def test_cleanup_deletes_only_planned_versions(self):
        removed = ms.cleanup_versions(['HPDB-Experimental-2026_01_01', 'HPDB-Experimental-2026_05_01', 'nope'], 3)
        self.assertEqual(removed, ['HPDB-Experimental-2026_01_01'])
        self.assertTrue((self.root / 'database' / 'versions' / 'HPDB-Experimental-2026_05_01').is_dir())

    def test_incomplete_folders_are_not_versions(self):
        (self.root / 'database' / 'versions' / 'half').mkdir()
        self.assertNotIn('half', self.names(ms.list_versions()))


if __name__ == '__main__':
    unittest.main()
