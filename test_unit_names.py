# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Unit names from SDS100 Monitor onto trunked systems, and Monitor activity in the editor (v0.1.19).

Monitor files here are synthetic; the Favorites Lists are real SDS100 lists."""
import copy
import tempfile
import unittest
from datetime import date
from pathlib import Path

import monitor_activity as ma
import scanner_list_sync as sync
import unit_aliases as ua
from test_add_heard import raw
from test_favorites_clipboard import FIX, native, rows_of

TEMPLATE = ['UnitIds', '', '', 'Scanner Written', '1000001', 'Off', 'Auto', 'Off', 'On']


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


class UnitNameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        write(self.tmp / 'unit_names.csv', 'Unit ID,Name,Status,Notes,Updated\n'
              'UID:1000001,Engine 1,Confirmed,,\n1000002,Medic\t7,Confirmed,,\n1000003,Maybe,Guess,,\n'
              '1000004,Elsewhere,Confirmed,,\n99999999,Too Big,Confirmed,,\n')
        write(self.tmp / 'unit_ids' / 'unit_ids_2026-11-01.csv',
              'Time,Unit ID,Unit Name,System,Site,Department,Channel,Talkgroup,Frequency\n'
              '2026-11-01 10:00:00,1000001,,Palmetto 800,,,,,\n2026-11-01 10:01:00,UID:1000002,,palmetto 800,,,,,\n'
              '2026-11-01 10:02:00,1000003,,Palmetto 800,,,,,\n2026-11-01 10:03:00,1000004,,Other System,,,,,\n')
        self.drafts = native(FIX / 'real_sds100_f_000001.hpd')

    def palmetto(self):
        for e, entry in enumerate(self.drafts):
            for i, row in enumerate(entry['records']):
                if row[0] == 'Trunk' and row[3] == 'Palmetto 800':
                    return e, i
        raise AssertionError('no Palmetto 800')

    def test_reading_the_monitor(self):
        self.assertEqual(ua.load_names(self.tmp), {1000001: 'Engine 1', 1000002: 'Medic 7', 1000004: 'Elsewhere'})
        self.assertIn(1000003, ua.load_names(self.tmp, guesses=True))
        self.assertEqual(ua.load_systems(self.tmp)[1000002], {'palmetto 800'})
        self.assertEqual(ua.load_names(self.tmp / 'missing'), {})

    def test_no_unit_ids_yet_is_explained_not_guessed(self):
        result = ua.plan(self.drafts, ua.load_names(self.tmp), ua.load_systems(self.tmp))
        self.assertEqual((result['add'], result['no_template']), ([], ['Palmetto 800']))
        self.assertIn('Edit Unit IDs', ua.summary(result))

    def test_names_copied_from_a_scanner_written_row(self):
        e, i = self.palmetto()
        self.drafts[e]['records'].insert(i + 1, list(TEMPLATE))
        original = raw(rows_of(self.drafts))
        result = ua.plan(self.drafts, ua.load_names(self.tmp), ua.load_systems(self.tmp))
        self.assertEqual(len(result['add']), 1)                       # 1000002; 1000001 is renamed
        self.assertEqual(result['rename'], [(e, i + 1, 'Engine 1')])
        self.assertEqual(result['systems'], {'Palmetto 800': 2})
        self.assertEqual(ua.apply(self.drafts, result), 2)
        records = self.drafts[e]['records']
        self.assertEqual(records[i + 1], ['UnitIds', '', '', 'Engine 1', '1000001', 'Off', 'Auto', 'Off', 'On'])
        self.assertEqual(records[i + 2][3:5], ['Medic 7', '1000002'])
        ok, why = sync.assess_new_hpd(raw(rows_of(self.drafts)), original)
        self.assertTrue(ok, why)
        again = ua.plan(self.drafts, ua.load_names(self.tmp), ua.load_systems(self.tmp))
        self.assertEqual((again['add'], again['rename'], again['skipped']), ([], [], 2))

    def test_order_and_record_ids(self):
        e, i = self.palmetto()
        self.drafts[e]['records'].insert(i + 1, ['UnitIds', 'UnitId=12', '', 'Old', '5', 'Off', 'Auto', 'Off', 'On'])
        names = {n: f'Unit {n}' for n in (30, 10, 20)}
        result = ua.plan(self.drafts, names, {n: {'palmetto 800'} for n in names})
        ua.apply(self.drafts, result)
        rows = self.drafts[e]['records'][i + 1:i + 5]
        self.assertEqual([r[4] for r in rows], ['5', '10', '20', '30'])
        self.assertEqual({r[1] for r in rows[1:]}, {'UnitId=0'})

    def test_export_refuses_unit_ids_it_cannot_vouch_for(self):
        e, i = self.palmetto()
        original = raw(rows_of(self.drafts))
        self.drafts[e]['records'].insert(i + 1, list(TEMPLATE))
        ok, why = sync.assess_new_hpd(raw(rows_of(self.drafts)), original)
        self.assertFalse(ok)
        self.assertIn('layout the scanner has not written', why)
        with_template = copy.deepcopy(self.drafts)
        original = raw(rows_of(with_template))
        with_template[e]['records'].insert(i + 2, TEMPLATE[:4] + ['0'] + TEMPLATE[5:])
        ok, why = sync.assess_new_hpd(raw(rows_of(with_template)), original)
        self.assertFalse(ok)
        self.assertIn('invalid unit ID', why)


class ActivityTests(unittest.TestCase):
    def test_counts_last_heard_and_window(self):
        tmp = Path(tempfile.mkdtemp())
        head = 'Start,End,Duration (s),System,Department,Channel,Frequency,Talkgroup,RSSI (dBm)\n'
        write(tmp / 'reception_history_2026-11-05.csv', head +
              '2026-11-05 08:00:00,2026-11-05 08:00:05,5.0,Palmetto 800,Sheriff,Dispatch,853.8625MHz,TGID:44002,-80\n'
              '2026-11-05 09:00:00,2026-11-05 09:00:03,3.0,PALMETTO 800,Sheriff,Dispatch,853.8625MHz,TGID:44002,-80\n'
              '2026-11-05 10:00:00,2026-11-05 10:00:04,4.0,Greenville,Police,Main,453.1500MHz,None,-70\n')
        write(tmp / 'reception_history_2026-01-01.csv', head +
              '2026-01-01 08:00:00,2026-01-01 08:00:05,5.0,Palmetto 800,Sheriff,Dispatch,853.8625MHz,TGID:44002,-80\n')
        activity = ma.load(folder=tmp, today=date(2026, 11, 7))
        self.assertEqual(activity.files, 1)
        count, seconds, last = activity.lookup('Palmetto 800', ['TGID', 'TgidId=1', '', 'Dispatch', 'Off', '44002'])
        self.assertEqual((count, seconds, last.hour), (2, 8.0, 9))
        self.assertEqual(ma.columns(activity, 'Greenville', ['C-Freq', '', '', 'Main', 'Off', '453150000']),
                         ('1', '2026-11-05 10:00'))
        self.assertEqual(ma.columns(activity, 'Other', ['TGID', '', '', 'X', 'Off', '44002']), ('0', 'not heard'))
        self.assertEqual(ma.load(folder=tmp / 'none').files, 0)


if __name__ == '__main__':
    unittest.main()
