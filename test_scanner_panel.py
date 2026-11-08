# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
import unittest
from datetime import datetime

import scanner_panel as sp

INFO = {'model': 'SDS100', 'firmware': '1.26.01', 'database_date': datetime(2026, 10, 25), 'free_bytes': 2 * 1024 ** 3,
        'total_bytes': 8 * 1024 ** 3, 'favorites_lists': 29}


def rows(**kw):
    return {label: (value, sev) for label, value, sev in sp.panel_rows(**kw)}


class PanelTests(unittest.TestCase):
    def test_not_connected(self):
        r = rows(info=None)
        self.assertEqual(r['Scanner'], ('Not connected', sp.NOTE))
        self.assertNotIn('Database on scanner', r)
        self.assertEqual(sp.status_text(None), 'Scanner: not connected')

    def test_connected_summary(self):
        r = rows(info=INFO, local_date=datetime(2026, 10, 25), configuration='My Scanner')
        self.assertEqual(r['Scanner'], ('SDS100 firmware 1.26.01', sp.OK))
        self.assertEqual(r['Database on scanner'][1], sp.OK)
        self.assertEqual(r['Favorites lists on scanner'][0], '29')
        self.assertEqual(r['Open configuration'], ('My Scanner', sp.OK))
        self.assertEqual(sp.status_text(INFO), 'Scanner: SDS100 connected • database 10/25/2026')

    def test_database_comparisons(self):
        newer = rows(info=INFO, local_date=datetime(2026, 11, 1))['Database on scanner']
        self.assertEqual(newer[1], sp.NOTE)
        self.assertIn('newer database is available locally', newer[0])
        older = rows(info=INFO, local_date=datetime(2026, 9, 1))['Database on scanner']
        self.assertEqual(older[1], sp.WARN)
        unknown = rows(info=dict(INFO, database_date=None))['Database on scanner']
        self.assertEqual(unknown[1], sp.WARN)

    def test_low_space_and_large_backups_warn(self):
        self.assertEqual(rows(info=dict(INFO, free_bytes=10 * 1024 ** 2))['Free space'][1], sp.WARN)
        big = {'count': 30, 'bytes': 3 * 1024 ** 3, 'newest': '20261025T120000Z'}
        value, sev = rows(info=None, backups=big, backup_warn_mb=2000)['Backups']
        self.assertEqual(sev, sp.WARN)
        self.assertIn('newest 10/25/2026', value)
        none = rows(info=None, backups={'count': 0, 'bytes': 0, 'newest': None})['Backups']
        self.assertEqual(none[1], sp.NOTE)

    def test_update_message(self):
        names = ['MasterHpdb_10_18_2026.gz', 'MasterHpdb_10_25_2026.gz', 'junk.txt', 'MasterHpdb_13_40_2026.gz']
        self.assertEqual(sp.newest_archive(names)[0], 'MasterHpdb_10_25_2026.gz')
        self.assertIn('10/25/2026', sp.update_message(names, datetime(2026, 9, 1), datetime(2026, 9, 1)))
        self.assertIsNone(sp.update_message(names, datetime(2026, 10, 25, 4, 30), None))
        self.assertIsNone(sp.update_message(names, None, datetime(2026, 10, 25)))
        self.assertIsNone(sp.update_message(['nothing'], None, None))
        self.assertIsNotNone(sp.update_message(names, None, None))


if __name__ == '__main__':
    unittest.main()
