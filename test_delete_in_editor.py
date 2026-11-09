# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Deleting sites, and several channels or talkgroups at once, in the list editor (v0.1.25)."""
import unittest

import favorites_clipboard as clip
import scanner_list_sync as sync
from test_add_heard import raw
from test_favorites_clipboard import FIX, native, rows_of


class DeleteTests(unittest.TestCase):
    def setUp(self):
        self.entries = native(FIX / 'real_sds100_f_000001.hpd')
        self.original = raw(rows_of(self.entries))
        self.trunk = next(i for i, e in enumerate(self.entries)
                          if e.get('records') and e['records'][0][0] == 'Trunk')

    def sites(self):
        return [b for b in clip.blocks(self.entries[self.trunk]['records']) if b[0] == 'Site']

    def test_a_site_goes_with_its_frequencies_and_the_list_still_exports(self):
        records = self.entries[self.trunk]['records']
        before = self.sites()
        self.assertGreater(len(before), 1)
        _kind, start, end = before[-1]
        name, removed = records[start][3], end - start
        length = len(records)
        clip.remove_site(self.entries, self.trunk, start)
        self.assertEqual(len(records), length - removed)
        self.assertNotIn(name, [r[3] for r in records if r[0] == 'Site'])
        ok, why = sync.assess_new_hpd(raw(rows_of(self.entries)), self.original)
        self.assertTrue(ok, why)

    def test_the_last_site_is_refused(self):
        while len(self.sites()) > 1:
            clip.remove_site(self.entries, self.trunk, self.sites()[-1][1])
        with self.assertRaises(clip.ClipboardError) as caught:
            clip.remove_site(self.entries, self.trunk, self.sites()[0][1])
        self.assertIn('Delete the system instead', str(caught.exception))

    def test_several_rows_but_never_a_whole_department(self):
        records = self.entries[self.trunk]['records']
        _kind, start, end = next(b for b in clip.blocks(records) if b[0] == 'T-Group' and b[2] - b[1] > 3)
        leaves = [i for i in range(start + 1, end) if records[i][0] == 'TGID']
        with self.assertRaises(clip.ClipboardError):
            clip.leaves_check(self.entries, self.trunk, leaves)
        rows = clip.leaves_check(self.entries, self.trunk, leaves[:2] + [start])
        self.assertEqual(rows, leaves[:2])
        clip.remove_leaves(self.entries, self.trunk, rows)
        self.assertTrue(sync.assess_new_hpd(raw(rows_of(self.entries)), self.original)[0])


class MultiSelectDeleteTests(DeleteTests):
    """Several systems, sites and departments selected with Ctrl or Shift (v0.1.27)."""
    def test_departments_and_sites_together_in_one_step(self):
        records = self.entries[self.trunk]['records']
        found = clip.blocks(records)
        groups = [b for b in found if b[0] == 'T-Group']
        departments = groups[:max(1, len(groups) - 1)]
        site = [b for b in found if b[0] == 'Site'][-1]
        targets = [(self.trunk, b[1]) for b in departments + [site]]
        plan = clip.removal_plan(self.entries, targets)
        self.assertEqual((len(plan['departments']), len(plan['sites'])), (len(departments), 1))
        self.assertTrue(clip.describe_plan(plan).startswith('Delete 1 site: '))
        clip.remove_planned(self.entries, plan, targets)
        names = [r[3] for r in records if r[0] in ('Site', 'T-Group')]
        for name in plan['departments'] + plan['sites']:
            self.assertNotIn(name, names)
        self.assertTrue(sync.assess_new_hpd(raw(rows_of(self.entries)), self.original)[0])

    def test_whole_systems_and_the_guards(self):
        systems = [i for i, e in enumerate(self.entries) if e.get('scope') != 'metadata']
        with self.assertRaises(clip.ClipboardError):
            clip.removal_plan(self.entries, [(i, None) for i in systems])          # the whole list
        sites = [(self.trunk, b[1]) for b in self.sites()]
        with self.assertRaises(clip.ClipboardError):
            clip.removal_plan(self.entries, sites)                                 # every site of a trunk
        keep = systems[0] if systems[0] != self.trunk else systems[1]
        targets = [(i, None) for i in systems if i != keep]
        plan = clip.removal_plan(self.entries, targets)
        clip.remove_planned(self.entries, plan, targets)
        self.assertEqual(len([e for e in self.entries if e.get('scope') != 'metadata']), 1)
        records = self.entries[-1]['records']
        everything = [(len(self.entries) - 1, b[1]) for b in clip.blocks(records) if b[0] in clip.DEPARTMENTS]
        with self.assertRaises(clip.ClipboardError):
            clip.removal_plan(self.entries, everything)                            # last system emptied


if __name__ == '__main__':
    unittest.main()
