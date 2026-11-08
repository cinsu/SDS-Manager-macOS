# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Rectangle locations in new Favorites Lists.

Ground truth: real_sds100_f_000029_rectangle.hpd, a Sentinel-written Palmetto 800 list whose Laurens site is a
rectangle site.  Layout: Site, band plan(s), Rectangle(s), frequencies.  The rows Sentinel wrote carry every column
the builder reads from the database, so they double as database input.  Rectangle departments (T-Group, C-Group) follow
the database layout (group row, Rectangle row, members); no real Sentinel sample of those exists yet.
"""
import unittest
from pathlib import Path

import scanner_list_sync as sync
from new_favorites_list import build_new_list_rows
from test_new_trunk_list import rows_of, raw
from test_list_sync_export import SyncBase
import scanner_configurations as sc
import scanner_first_write as writer

FIX = Path(__file__).resolve().parent / 'test_fixtures'
REAL = (FIX / 'real_sds100_f_000029_rectangle.hpd').read_bytes()
NATIVE = rows_of(FIX / 'real_sds100_f_000029_rectangle.hpd')
BODY = NATIVE[2:]          # drop TargetModel / FormatVersion


def kinds(rows):
    return [r[0] for r in rows]


class SentinelRectangleSite(unittest.TestCase):
    def test_the_real_sentinel_list_is_accepted(self):
        self.assertEqual(sync.assess_new_hpd(REAL)[0], True)

    def test_builder_reproduces_the_real_list_exactly(self):
        rows, enc, nl = build_new_list_rows([r[:] for r in BODY if r[0] != 'DQKs_Status'])
        self.assertEqual(rows, NATIVE)

    def test_database_order_does_not_matter(self):
        db = [r[:] for r in BODY if r[0] != 'DQKs_Status']
        rect = next(r for r in db if r[0] == 'Rectangle')
        db.remove(rect)
        db.insert(2, rect)               # Rectangle straight after the Site, before the band plan
        rows, _, _ = build_new_list_rows(db)
        self.assertEqual(rows, NATIVE)

    def test_site_without_a_rectangle_is_refused(self):
        db = [r[:] for r in BODY if r[0] not in ('DQKs_Status', 'Rectangle')]
        with self.assertRaises(ValueError):
            build_new_list_rows(db)

    def test_rectangle_under_a_circle_site_is_refused(self):
        db = [r[:] for r in BODY if r[0] != 'DQKs_Status']
        next(r for r in db if r[0] == 'Site')[11] = 'Circle'
        with self.assertRaises(ValueError):
            build_new_list_rows(db)

    def test_bad_coordinates_are_refused(self):
        for bad in ('95.000000', 'north', '', '34.1234567'):
            db = [r[:] for r in BODY if r[0] != 'DQKs_Status']
            next(r for r in db if r[0] == 'Rectangle')[2] = bad
            with self.assertRaises(ValueError, msg=bad):
                build_new_list_rows(db)


class GuardTests(unittest.TestCase):
    def check(self, mutate):
        rows = [r[:] for r in NATIVE]
        mutate(rows)
        return sync.assess_new_hpd(raw(rows))

    def test_rectangle_must_follow_its_location(self):
        def move(rows):
            i = next(i for i, r in enumerate(rows) if r[0] == 'Rectangle')
            rect = rows.pop(i)
            rows.insert(i + 2, rect)         # after two frequencies
        self.assertFalse(self.check(move)[0])

    def test_rectangles_site_needs_a_rectangle_and_circle_must_not_have_one(self):
        self.assertFalse(self.check(lambda rows: rows.pop(next(i for i, r in enumerate(rows) if r[0] == 'Rectangle')))[0])
        self.assertFalse(self.check(lambda rows: next(r for r in rows if r[0] == 'Site').__setitem__(11, 'Circle'))[0])

    def test_rectangle_layout_is_checked(self):
        def widen(rows):
            next(r for r in rows if r[0] == 'Rectangle').append('x')
        self.assertFalse(self.check(widen)[0])
        self.assertFalse(self.check(lambda rows: next(r for r in rows if r[0] == 'Rectangle').__setitem__(1, 'x'))[0])
        self.assertFalse(self.check(lambda rows: next(r for r in rows if r[0] == 'Rectangle').__setitem__(2, '120.000000'))[0])


class RectangleDepartments(unittest.TestCase):
    def test_trunk_department_rectangle_goes_between_group_and_talkgroups(self):
        db = [r[:] for r in BODY if r[0] != 'DQKs_Status']
        group = next(r for r in db if r[0] == 'T-Group')
        group[8] = 'Rectangles'
        i = db.index(group)
        db.insert(i + 1, ['Rectangle', '', '85.000000', '-170.500000', '15.000000', '-50.000000'])
        rows, _, _ = build_new_list_rows(db)
        i = kinds(rows).index('T-Group')
        self.assertEqual(kinds(rows)[i:i + 3], ['T-Group', 'Rectangle', 'TGID'])
        self.assertEqual(rows[i][8], 'Rectangles')
        self.assertTrue(sync.assess_new_hpd(raw(rows))[0])

    def test_conventional_department_rectangle(self):
        db = [['Conventional', 'CountyId=1', 'StateId=45', 'Test County', 'Off', '', 'Conventional', '', '', '', '', '', '', '', ''],
              ['C-Group', 'CGroupId=1', 'CountyId=1', 'Statewide', 'Off', '0.000000', '0.000000', '0.0', 'Rectangles', 'Off', 'Global'],
              ['Rectangle', '', '85.000000', '-170.500000', '15.000000', '-50.000000'],
              ['C-Freq', 'CFreqId=1', 'CGroupId=1', 'Channel', 'Off', '155280000', 'FM', '', '9', '', '', '', '', '', '', '', '', '']]
        rows, _, _ = build_new_list_rows(db)
        self.assertEqual(kinds(rows)[-3:], ['C-Group', 'Rectangle', 'C-Freq'])
        self.assertTrue(sync.assess_new_hpd(raw(rows))[0])
        db[2][2] = 'bad'
        with self.assertRaises(ValueError):
            build_new_list_rows(db)

    def test_circle_departments_are_unchanged(self):
        db = [['Conventional', 'CountyId=1', 'StateId=45', 'Test County', 'Off', '', 'Conventional', '', '', '', '', '', '', '', ''],
              ['C-Group', 'CGroupId=1', 'CountyId=1', 'Fire', 'Off', '34.0', '-82.0', '5.0', 'Circle', 'Off', 'Global'],
              ['C-Freq', 'CFreqId=1', 'CGroupId=1', 'Channel', 'Off', '155280000', 'FM', '', '9', '', '', '', '', '', '', '', '', '']]
        rows, _, _ = build_new_list_rows(db)
        self.assertNotIn('Rectangle', kinds(rows))
        self.assertEqual(rows[2 + 2][8], 'Circle')


class ExportTests(SyncBase):
    def test_rectangle_list_is_created_and_exported_byte_for_byte(self):
        db = [r[:] for r in BODY if r[0] != 'DQKs_Status']
        rows, enc, nl = build_new_list_rows(db)
        created = sc.create_local_favorites_list(self.config, 'Laurens rectangle', rows, enc, nl)
        ok, reason = writer.first_write_eligibility(self.config, self.scanner)
        self.assertTrue(ok, reason)
        result = writer.execute_first_write(self.config, self.scanner)
        written = (self.scanner / result['added'][0]).read_bytes()
        self.assertEqual(written, REAL)


if __name__ == '__main__':
    unittest.main()
