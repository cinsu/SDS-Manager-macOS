# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""The SDS100 Monitor link: Edit in Manager requests, finding entries, and naming unnamed talkgroups."""
import csv
import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import monitor_link as ml
import qt_stub

FORGET = ('monitor_link_ui', 'favorites_settings_window', 'database_workspace', 'state_labels',
          'favorites_explorer', 'database_favorites_manager', 'ui_extras', 'favorites_manager',
          'favorites_planner', 'favorites_editor')


def drafts():
    """Two lists: Greenville (trunked) and Weather (conventional)."""
    meta = {'scope': 'metadata', 'encoding': 'cp1252', 'records': []}
    trunk = {'name': 'Palmetto 800', 'kind': 'Trunk', 'scope': 'system', 'records': [
        ['Trunk', '', '', 'Palmetto 800'],
        ['T-Group', '', '', 'Greenville County Fire'],
        ['TGID', '', '', 'Fire Dispatch', 'Off', '44002', 'ALL', '3', '2'],
        ['TGID', '', '', '44353', 'Off', '44353', 'ALL', '3', '2'],
        ['TGID', '', '', 'TGID 45000', 'Off', '45000', 'ALL', '3', '2'],
        ['T-Group', '', '', 'Greenville County EMS'],
        ['TGID', '', '', '', 'Off', '44010', 'ALL', '3', '2'],
        ['TGID', '', '', 'Medic Ops', 'Off', '44002', 'ALL', '3', '2'],
    ]}
    conv = {'name': 'Weather', 'kind': 'Conventional', 'scope': 'system', 'records': [
        ['Conventional', '', '', 'Weather'],
        ['C-Group', '', '', 'NOAA'],
        ['C-Freq', '', '', 'NWS Greenville', 'Off', '162550000', 'FM'],
    ]}
    other = {'name': 'Other System', 'kind': 'Trunk', 'scope': 'system', 'records': [
        ['Trunk', '', '', 'Other System'],
        ['T-Group', '', '', 'Ops'],
        ['TGID', '', '', 'Ops 1', 'Off', '44353', 'ALL', '3', '2'],
    ]}
    return {'Greenville (editable copy)': [meta, trunk, conv], 'Away (editable copy)': [dict(meta), other]}


class RequestTests(unittest.TestCase):
    def test_clean_request(self):
        req = ml.clean_request(json.dumps({'system': 'Palmetto 800', 'tgid': 'TGID:44353', 'frequency': ' 859.262500MHz',
                                           'extra': 'ignored'}))
        self.assertEqual(req['tgid'], '44353')
        self.assertEqual(req['frequency'], '859.262500')
        self.assertNotIn('extra', req)
        self.assertIsNone(ml.clean_request('not json'))
        self.assertIsNone(ml.clean_request({'system': 'x', 'tgid': 'abc', 'frequency': '5000'}))
        self.assertEqual(ml.clean_request({'frequency': '162.55'})['frequency'], '162.550000')
        self.assertLessEqual(len(ml.clean_request({'tgid': '1', 'channel': 'x' * 999})['channel']), 200)

    def test_describe(self):
        self.assertEqual(ml.describe_request(ml.clean_request({'tgid': '44353', 'system': 'P800', 'department': '—'})),
                         'talkgroup 44353 (P800)')
        self.assertEqual(ml.describe_request(ml.clean_request({'frequency': '162.55'})), '162.55 MHz')


class FindTests(unittest.TestCase):
    def test_talkgroup_with_system_and_department_wins(self):
        req = ml.clean_request({'system': 'Palmetto 800', 'department': 'Greenville County Fire', 'tgid': '44353'})
        m = ml.find_entries(drafts(), req)
        self.assertEqual(len(m), 2)
        self.assertEqual((m[0]['draft'], m[0]['entry_index'], m[0]['group_index'], m[0]['row_index']),
                         ('Greenville (editable copy)', 1, 1, 3))
        self.assertEqual(m[0]['score'], 6)
        self.assertIs(ml.pick_match(m), m[0])
        self.assertEqual(m[0]['label'], 'Greenville › Palmetto 800 › Greenville County Fire › 44353')

    def test_same_talkgroup_twice_in_one_system_asks(self):
        m = ml.find_entries(drafts(), ml.clean_request({'system': 'Palmetto 800', 'tgid': '44002'}))
        self.assertEqual(len(m), 2)
        self.assertIsNone(ml.pick_match(m))
        m = ml.find_entries(drafts(), ml.clean_request({'system': 'Palmetto 800', 'department': 'Greenville County EMS',
                                                        'tgid': '44002'}))
        self.assertEqual(ml.pick_match(m)['row_index'], 7)

    def test_frequency_and_nothing(self):
        m = ml.find_entries(drafts(), ml.clean_request({'frequency': '162.550000', 'channel': 'NWS Greenville'}))
        self.assertEqual((m[0]['entry_index'], m[0]['row_index']), (2, 2))
        self.assertEqual(ml.pick_match(m), m[0])
        self.assertEqual(ml.find_entries(drafts(), ml.clean_request({'tgid': '99999'})), [])


class UnnamedTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_placeholders(self):
        for name in ('', '44353', 'TGID 44353', 'TG:44353', 'Talkgroup 44353', 'Id=12', 'Unknown', 'AD41h', ' '):
            self.assertTrue(ml.is_placeholder_name(name, '44353'), name)
        for name in ('Fire Dispatch', 'F1', 'CAD1', 'Ops 51', 'Medic 4', '44 Ops'):
            self.assertFalse(ml.is_placeholder_name(name, '44353'), name)

    def test_finds_unnamed_talkgroups(self):
        items = ml.unnamed_talkgroups(drafts())
        self.assertEqual([(i['tgid'], i['department']) for i in items],
                         [('44353', 'Greenville County Fire'), ('45000', 'Greenville County Fire'),
                          ('44010', 'Greenville County EMS')])

    def write_monitor(self):
        hist = self.dir / 'history'
        hist.mkdir(parents=True)
        with (hist / 'reception_history_2026-10-30.csv').open('w', newline='') as f:
            w = csv.writer(f)
            w.writerow(ml.MONITOR_HISTORY_HEADERS)
            w.writerow(['2026-10-30 10:00:00', '', '3', 'Palmetto 800', 'Greenville County', 'Ops 51 (GFD)',
                        '', 'TGID:44353', ''])
            w.writerow(['2026-10-30 11:00:00', '', '3', 'Palmetto 800', 'Greenville County', 'TGID 45000',
                        '', 'TGID:45000', ''])
            w.writerow(['2026-10-30 12:00:00', '', '3', 'Other', 'X', 'Somewhere Else', '', 'TGID:44010', ''])
        with (self.dir / 'analyze_found_ids.csv').open('w', newline='') as f:
            w = csv.writer(f)
            w.writerow(ml.MONITOR_FOUND_HEADERS)
            w.writerow(['Talkgroup', '45000', '', '', '3', '', 'Probably public works'])
            w.writerow(['Unit', '3238410', '', '', '3', '', 'Engine 12'])

    def write_database(self):
        db = self.dir / 'db'
        db.mkdir()
        (db / 's_000045.hpd').write_bytes('\n'.join([
            'Trunk\t\t\tPalmetto 800', 'T-Group\t\t\tGreenville County Fire',
            'TGID\t\t\tGCFD Ops 51\tOff\t44353\tALL', 'TGID\t\t\t44010\tOff\t44010\tALL',
            'Trunk\t\t\tYork County', 'T-Group\t\t\tEMS', 'TGID\t\t\tYork EMS 1\tOff\t44010\tALL',
        ]).encode('cp1252'))
        return db

    def test_suggestions_from_database_and_monitor(self):
        self.write_monitor()
        heard = ml.monitor_heard_names(self.dir)
        self.assertEqual(heard['44353']['palmetto 800'][0], 'Ops 51 (GFD)')
        self.assertNotIn('45000', heard)                              # the scanner only showed the ID
        notes = ml.monitor_notes(self.dir)
        self.assertEqual(notes, {'45000': 'Probably public works'})
        db = ml.database_names(self.write_database(), {'44353', '45000', '44010'})
        self.assertEqual(db['44353'], [('Palmetto 800', 'Greenville County Fire', 'GCFD Ops 51')])
        self.assertEqual(db['44010'], [('York County', 'EMS', 'York EMS 1')])   # the 44010 placeholder skipped
        items = {i['tgid']: i for i in ml.unnamed_talkgroups(drafts())}
        s = ml.suggest(items['44353'], db, heard, notes)
        self.assertEqual([n for n, _src in s], ['GCFD Ops 51', 'Ops 51 (GFD)'])
        self.assertTrue(s[0][1].startswith('Database: Palmetto 800'))
        self.assertEqual(ml.suggest(items['45000'], db, heard, notes)[0][0], 'Probably public works')
        s = ml.suggest(items['44010'], db, heard, notes)
        self.assertEqual([n for n, _src in s], ['York EMS 1', 'Somewhere Else'])
        self.assertIn('another system', s[0][1])

    def test_monitor_files_missing_or_damaged(self):
        self.assertEqual(ml.monitor_heard_names(self.dir / 'none'), {})
        self.assertEqual(ml.monitor_notes(self.dir / 'none'), {})
        (self.dir / 'analyze_found_ids.csv').write_text('wrong,header\n')
        self.assertEqual(ml.monitor_notes(self.dir), {})
        self.assertEqual(ml.database_names(None, {'1'}), {'1': []})

    def test_apply_names(self):
        d = drafts()
        items = ml.unnamed_talkgroups(d)
        self.assertEqual(ml.apply_names(d, [(items[0], 'GCFD Ops 51')]), 1)
        self.assertEqual(d['Greenville (editable copy)'][1]['records'][3][3], 'GCFD Ops 51')
        self.assertEqual(d['Greenville (editable copy)'][1]['records'][3][5], '44353')     # nothing else moved
        d['Greenville (editable copy)'][1]['records'][4][5] = '1'
        with self.assertRaises(ValueError):
            ml.apply_names(d, [(items[1], 'x')])

    def test_valid_names(self):
        self.assertTrue(ml.valid_name('Fire Ops'))
        for bad in ('', ' ', 'x' * 65, 'a\tb', 'smile \U0001F600'):
            self.assertFalse(ml.valid_name(bad), bad)

    def test_versions(self):
        names = ['SDS100DatabaseFavoritesManager-0.0.9e', 'SDS100DatabaseFavoritesManager-0.0.10',
                 'SDS100DatabaseFavoritesManager-0.0.9f']
        self.assertEqual(max(names, key=ml.newest_version_key), 'SDS100DatabaseFavoritesManager-0.0.10')


class UiTests(unittest.TestCase):
    """The windows on the Qt stub."""

    def load(self):
        with qt_stub.installed(forget=FORGET):
            return importlib.import_module('monitor_link_ui')

    def host(self, ui):
        class Host(ui.MonitorLinkMixin):
            pass
        h = Host()
        h.workspace = MagicMock()
        h.workspace.drafts = drafts()
        h.statusBar = MagicMock()
        h.isMinimized = lambda: False
        for name in ('raise_', 'activateWindow', 'showNormal', 'show_scanner_configurations'):
            setattr(h, name, MagicMock())
        return h

    def test_request_opens_the_editor_at_the_entry(self):
        ui = self.load()
        h = self.host(ui)
        ui.QApplication.activeModalWidget = MagicMock(return_value=None)
        opened = []
        h.open_list_editor_at = opened.append
        h.open_monitor_request(ml.clean_request({'system': 'Palmetto 800', 'department': 'Greenville County Fire',
                                                 'tgid': '44353'}))
        self.assertEqual(opened[0]['row_index'], 3)

    def test_request_choice_and_not_found(self):
        ui = self.load()
        h = self.host(ui)
        ui.QApplication.activeModalWidget = MagicMock(return_value=None)
        opened = []
        h.open_list_editor_at = opened.append
        ui.QInputDialog.getItem = MagicMock(return_value=('Greenville › Palmetto 800 › Greenville County EMS › Medic Ops', True))
        h.open_monitor_request(ml.clean_request({'tgid': '44002'}))
        self.assertEqual(opened[0]['row_index'], 7)
        ui.QMessageBox.information = MagicMock()
        h.open_monitor_request(ml.clean_request({'tgid': '99999'}))
        self.assertIn('not in the open', ui.QMessageBox.information.call_args[0][2])

    def test_request_without_a_configuration_offers_one(self):
        ui = self.load()
        h = self.host(ui)
        h.workspace.drafts = {}
        ui.QApplication.activeModalWidget = MagicMock(return_value=None)
        ui.QMessageBox.question = MagicMock(return_value=ui.QMessageBox.StandardButton.Yes)
        h.open_monitor_request(ml.clean_request({'tgid': '44353'}))
        h.show_scanner_configurations.assert_called_once()

    def test_server_reads_one_request(self):
        ui = self.load()
        server = ui.LinkServer()
        got = []
        server.received = MagicMock()
        server.received.emit = got.append
        sock = MagicMock()
        sock.readAll.return_value = json.dumps({'tgid': '44353'}).encode()[:5]
        server._read(sock)
        self.assertEqual(got, [])                               # waits for the whole line
        sock.readAll.return_value = json.dumps({'tgid': '44353'}).encode()[5:] + b'\n'
        server._read(sock)
        self.assertEqual(got[0]['tgid'], '44353')
        sock.write.assert_called_with(b'ok\n')
        sock2 = MagicMock()
        sock2.readAll.return_value = b'x' * 9000
        server._read(sock2)
        sock2.abort.assert_called_once()

    def test_unnamed_dialog_applies_ticked_names(self):
        ui = self.load()
        h = self.host(ui)
        h.workspace.drafts = drafts()
        items = ml.unnamed_talkgroups(h.workspace.drafts)
        ui.UnnamedTalkgroupsDialog._get_child_mock = lambda _self, **kw: MagicMock(**kw)
        with patch.object(ml, 'monitor_heard_names', return_value={}), \
                patch.object(ml, 'monitor_notes', return_value={'45000': 'Public Works'}), \
                patch.object(ui.threading, 'Thread', MagicMock()):
            dialog = ui.UnnamedTalkgroupsDialog(h, items)
        dialog.lookup.update(done=True, db={'44353': [('Palmetto 800', 'Fire', 'GCFD Ops 51')]})
        use, combo = [], []

        def widget(r, c, w):
            (use if c == 0 else combo).append(w)
        dialog.table.setCellWidget = widget
        dialog.fill()
        self.assertEqual(len(dialog.choices), 3)
        checks = []
        for box, has in zip(use, (True, True, False)):
            box.isChecked.return_value = has
        combo[0].currentText.return_value = 'GCFD Ops 51'
        combo[1].currentText.return_value = 'Public Works'
        ui.QMessageBox.question = MagicMock(return_value=ui.QMessageBox.StandardButton.Yes)
        dialog.apply()
        records = h.workspace.drafts['Greenville (editable copy)'][1]['records']
        self.assertEqual((records[3][3], records[4][3], records[6][3]), ('GCFD Ops 51', 'Public Works', ''))
        h.workspace._snapshot.assert_called_once()
        combo[0].currentText.return_value = 'bad\tname'
        ui.QMessageBox.warning = MagicMock()
        dialog.apply()
        ui.QMessageBox.warning.assert_called_once()

    def test_manager_menu_and_arguments(self):
        with qt_stub.installed(forget=FORGET):
            module = importlib.import_module('database_favorites_manager')
        self.assertTrue(hasattr(module.ManagerWindow, 'name_unnamed_talkgroups'))
        self.assertTrue(hasattr(module.ManagerWindow, 'open_monitor_request'))
        req = module.monitor_request_from_args(['x', '--open-entry', json.dumps({'tgid': '44353'})])
        self.assertEqual(req['tgid'], '44353')
        self.assertIsNone(module.monitor_request_from_args(['x']))
        self.assertIsNone(module.monitor_request_from_args(['x', '--open-entry']))


if __name__ == '__main__':
    unittest.main()
