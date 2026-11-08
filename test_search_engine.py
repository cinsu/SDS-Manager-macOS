# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Find Everywhere search over raw database and Favorites List files."""
import shutil
import tempfile
import unittest
from pathlib import Path

import search_engine as se

FIX = Path(__file__).resolve().parent / 'test_fixtures'


class QueryTests(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(se.Query('154.9').freq, (154900000, 155000000))
        self.assertEqual(se.Query('460.025').freq, (460025000, 460026000))
        self.assertEqual(se.Query('154900000').freq, (154900000, 154900001))
        self.assertEqual(se.Query('00442').tgid, '442')
        self.assertIsNone(se.Query('fire').freq)
        self.assertTrue(se.Query('  ').empty)

    def test_freq_range_edges(self):
        q = se.Query('154.9')
        self.assertTrue(q.matches_freq('154900000'))
        self.assertTrue(q.matches_freq('154999999'))
        self.assertFalse(q.matches_freq('155000000'))
        self.assertFalse(q.matches_freq('154899999'))
        self.assertFalse(q.matches_freq(''))


class FileTests(unittest.TestCase):
    def test_database_frequency_and_context(self):
        hits = se.search_file(FIX / 'real_hpdb_greenville_county.txt', se.Query('146.94'), 'db')
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]['system'], 'Greenville')
        self.assertIn('Skywarn', se.context(hits[0]))
        self.assertEqual(hits[0]['value'], '146.94000 MHz')

    def test_talkgroup_exact_and_name(self):
        hits = se.search_file(FIX / 'real_sds100_f_000001.hpd', se.Query('44042'), 'x')
        self.assertEqual([(h['kind'], h['value']) for h in hits], [('talkgroup', '44042')])
        self.assertEqual(se.search_file(FIX / 'real_sds100_f_000001.hpd', se.Query('4404'), 'x'), [])

    def test_text_is_case_insensitive_and_limit_and_cancel(self):
        path = FIX / 'real_hpdb_greenville_county.txt'
        self.assertEqual(len(se.search_file(path, se.Query('SKYWARN'), 'x')), 3)
        self.assertEqual(len(se.search_file(path, se.Query('a'), 'x', limit=5)), 5)
        self.assertEqual(se.search_file(path, se.Query('a'), 'x', cancel=lambda: True), [])

    def test_missing_file_is_empty(self):
        self.assertEqual(se.search_file('/nonexistent/s_000001.hpd', se.Query('a'), 'x'), [])


class SearchAllTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.db = base / 'db'
        self.db.mkdir()
        shutil.copy(FIX / 'real_hpdb_greenville_county.txt', self.db / 's_000045.hpd')
        self.cfg = base / 'cfg'
        folder = self.cfg / 'BCDx36HP' / 'favorites_lists'
        folder.mkdir(parents=True)
        for n in ('f_000001.hpd', 'f_list.cfg'):
            shutil.copy(FIX / ('real_sds100_' + n), folder / n)

    def test_both_sources_and_list_name(self):
        results, truncated = se.search_all('greenville', self.db, self.cfg)
        self.assertFalse(truncated)
        sources = {r['source'].split(':')[0] for r in results}
        self.assertEqual(sources, {'Database', 'List'})
        self.assertTrue(any(r['kind'] == 'list' for r in results))

    def test_cap_truncates_and_empty_query(self):
        results, truncated = se.search_all('a', self.db, self.cfg, cap=7)
        self.assertEqual((len(results), truncated), (7, True))
        self.assertEqual(se.search_all('  ', self.db, self.cfg), ([], False))

    def test_progress_and_cancel(self):
        seen = []
        se.search_all('fire', self.db, self.cfg, progress=lambda i, n, label: seen.append((i, n)))
        self.assertEqual(seen[-1][1], len(seen))
        self.assertEqual(se.search_all('fire', self.db, self.cfg, cancel=lambda: True), ([], False))

    def test_no_sources(self):
        self.assertEqual(se.search_all('fire'), ([], False))


if __name__ == '__main__':
    unittest.main()
