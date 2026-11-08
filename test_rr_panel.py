# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Database Contents with RadioReference as the source (v0.1.1), driven on the Qt stub."""
import importlib
import unittest
from unittest.mock import MagicMock

import qt_stub
import rr_source
from test_rr_convert import FakeClient

FORGET = ('database_workspace', 'state_labels', 'favorites_explorer', 'favorites_planner')


class RRPanelTests(unittest.TestCase):
    def setUp(self):
        with qt_stub.installed(forget=FORGET):
            self.dw = importlib.import_module('database_workspace')
            self.fp = importlib.import_module('favorites_planner')
        for cls in (self.dw.DatabaseWorkspace, self.fp.FavoritesPlanner):
            cls._get_child_mock = lambda _self, **kw: MagicMock(**kw)
        self.ws = self.fp.FavoritesPlanner()
        self.ws.rr_browser = rr_source.RRBrowser(FakeClient())
        self.ws._rr_run = lambda what, work, done: done(work(self.ws.rr_browser), None)   # synchronous
        self.added = {}
        for name in ('region_choice', 'county_choice', 'system_choice'):
            combo = getattr(self.ws, name)
            items = self.added.setdefault(name, [])
            combo.clear.side_effect = items.clear
            combo.addItem.side_effect = lambda label, data=None, items=items: items.append((label, data))
        self.ws.source_choice.currentData.return_value = 'rr'
        self.ws.country_choice.currentData.return_value = 1
        self.ws.detail_table.columnWidth.return_value = 165

    def test_states_counties_systems_and_loading(self):
        ws = self.ws
        ws._country_changed(0)
        self.assertIn(('South Carolina', ('rr-state', 45)), self.added['region_choice'])
        ws.region_choice.currentData.return_value = ('rr-state', 45)
        ws.county_choice.currentData.return_value = None
        ws.system_type_choice.currentIndex.return_value = 0
        ws._region_changed(1)
        self.assertIn(('Greenville County', 2335), self.added['county_choice'])
        self.assertIn(('Palmetto 800 [Trunk]', ('rr:trs:6060', 0)), self.added['system_choice'])
        ws.system_choice.currentData.return_value = ('rr:trs:6060', 0)
        ws._system_changed(1)
        self.assertEqual(ws.db_index['rr:trs:6060'][0]['name'], 'Palmetto 800')
        ws.county_choice.currentData.return_value = 2335
        ws._county_changed(1)
        self.assertEqual([d for _l, d in self.added['system_choice'] if d],
                         [('rr:county:2335', 0)])

    def test_add_waits_until_loaded(self):
        ws = self.ws
        ws.current_draft = 'List'
        ws.system_choice.currentData.return_value = ('rr:trs:1', 0)
        self.fp.QMessageBox.information = MagicMock()
        self.assertIsNone(ws.add_selected())
        self.assertIn('Still loading', self.fp.QMessageBox.information.call_args[0][1])

    def test_uniden_choice_only_in_the_personal_build(self):
        import edition
        labels = [c.args[0] for c in self.ws.source_choice.addItem.call_args_list]
        self.assertEqual('Uniden database' in labels, edition.PERSONAL)
        self.assertIn('RadioReference', labels)


if __name__ == '__main__':
    unittest.main()
