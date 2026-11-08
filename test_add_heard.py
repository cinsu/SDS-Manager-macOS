# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Add to Favorites List from SDS100 Monitor (v0.1.18), on real SDS100 lists."""
import unittest

import monitor_link as ml
import scanner_list_sync as sync
from test_favorites_clipboard import FIX, native, rows_of


def raw(rows):
    return ('\r\n'.join('\t'.join(r) for r in rows) + '\r\n').encode('cp1252')


class AddHeardTests(unittest.TestCase):
    def setUp(self):
        self.drafts = {'Greenville County': native(FIX / 'real_sds100_f_000001.hpd'),
                       'Oconee': native(FIX / 'confirmed_f_000014_p25_dmr.hpd')}

    def test_requests(self):
        req = ml.clean_request({'action': 'add', 'system': 'Close Call Hits', 'channel': '453.1500MHz',
                                'frequency': '453.150000MHz', 'tgid': '—', 'modulation': 'nfm'})
        self.assertEqual((req['action'], req['frequency'], req['tgid'], req['modulation']),
                         ('add', '453.150000', '', 'NFM'))
        self.assertEqual(ml.clean_request({'tgid': '44358'})['action'], 'edit')
        self.assertEqual(ml.suggested_name(req), '')
        self.assertEqual(ml.suggested_name(dict(req, channel='Lake Patrol')), 'Lake Patrol')

    def test_a_heard_channel(self):
        req = ml.clean_request({'action': 'add', 'system': 'Greenville', 'department': 'Greenville (City) - Police',
                                'frequency': '453.1500MHz', 'modulation': 'FM'})
        targets = ml.add_targets(self.drafts, req)
        self.assertTrue(targets[0]['preferred'])
        self.assertEqual(targets[0]['label'], 'Greenville County › Greenville › Greenville (City) - Police')
        self.assertTrue(all(t['label'].count('›') == 2 for t in targets))
        row = ml.add_heard(self.drafts, targets[0], req, 'Lake Patrol', 'FM', '107.2')
        records = self.drafts['Greenville County'][targets[0]['entry_index']]['records']
        self.assertEqual(records[row][3:8], ['Lake Patrol', 'Off', '453150000', 'FM', 'TONE=C107.2'])
        self.assertTrue(sync.assess_new_hpd(raw(rows_of(self.drafts['Greenville County'])))[0])
        with self.assertRaises(ValueError):
            ml.add_heard(self.drafts, targets[0], req, 'Again', 'FM', '107.2')

    def test_a_heard_talkgroup(self):
        req = ml.clean_request({'action': 'add', 'system': 'Palmetto 800', 'department': 'Greenville County',
                                'channel': 'TGID 44999', 'frequency': '853.862500MHz', 'tgid': 'TGID:44999'})
        targets = ml.add_targets(self.drafts, req)
        self.assertTrue(all('Palmetto 800' in t['label'] or 'Oconee County Emergency' in t['label'] for t in targets))
        self.assertTrue(targets[0]['preferred'])
        row = ml.add_heard(self.drafts, targets[0], req, 'New Talkgroup')
        records = self.drafts[targets[0]['draft']][targets[0]['entry_index']]['records']
        self.assertEqual((records[row][0], records[row][3], records[row][5]), ('TGID', 'New Talkgroup', '44999'))
        self.assertTrue(sync.assess_new_hpd(raw(rows_of(self.drafts[targets[0]['draft']])))[0])
        with self.assertRaises(ValueError):
            ml.add_heard(self.drafts, targets[0], req, 'Twice')


if __name__ == '__main__':
    unittest.main()
