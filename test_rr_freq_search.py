# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Search Frequency in RadioReference (v0.1.28), with a made-up RadioReference in the API's own shapes."""
import unittest

import monitor_link
import rr_api
import rr_freq_search as fs
from rr_source import RRBrowser


class FakeClient:
    def __init__(self, state_search=True):
        self.calls = []
        self.state_search = state_search

    def state(self, stid):
        self.calls.append(('state', stid))
        return {'countyList': [{'ctid': 1, 'countyName': 'Lakeside'}, {'ctid': 2, 'countyName': 'Hill'}],
                'trsList': {'sid': 900, 'sName': 'Statewide P25'}}       # a one-item list comes as a plain value

    def county(self, ctid):
        self.calls.append(('county', ctid))
        return {1: {'countyName': 'Lakeside', 'trsList': [{'sid': 901, 'sName': 'Lakeside Trunk'}]},
                2: {'countyName': 'Hill', 'trsList': [{'sid': 900, 'sName': 'Statewide P25'}]}}[ctid]

    def search_county_freq(self, ctid, mhz, tone=''):
        self.calls.append(('county-search', ctid, mhz))
        if ctid == 1:
            return [{'out': '154.25000', 'in': '0', 'tone': '107.2 PL', 'alpha': 'Lakeside FD',
                     'descr': 'Fire Dispatch', 'mode': '1', 'tags': 'Fire Dispatch', 'ctid': 1}]
        return {'out': '154.25000', 'alpha': 'Hill EMS', 'descr': 'EMS', 'mode': '1', 'ctid': 2}

    def search_state_freq(self, stid, mhz, tone=''):
        self.calls.append(('state-search', stid, mhz))
        if not self.state_search:
            raise rr_api.RRError('Unknown method')
        return [{'out': '154.25000', 'alpha': 'Lakeside FD', 'descr': 'Fire Dispatch', 'mode': '1', 'ctid': 1},
                {'out': '154.25000', 'alpha': 'Hill EMS', 'descr': 'EMS', 'mode': '1', 'ctid': 2}]

    def mode(self, mode):
        return [{'mode': 1, 'modeName': 'FMN'}]

    def trs_sites(self, sid):
        self.calls.append(('sites', sid))
        if sid == 901:
            return {'siteDescr': 'North', 'nac': '293',
                    'siteFreqs': [{'freq': '154.25', 'lcn': '1', 'use': 'a'}, {'freq': '853.0125', 'lcn': '2', 'use': ''}]}
        return [{'siteDescr': 'Hilltop', 'siteFreqs': {'freq': '851.2625', 'lcn': '1', 'colorCode': '1'}}]


class FrequencySearchTests(unittest.TestCase):
    def test_hz(self):
        self.assertEqual([fs.hz(v) for v in ('154.25', '154.2500 MHz', 154250000, 'x', '5')],
                         [154250000, 154250000, 154250000, None, None])

    def test_county_search_with_trunked_sites(self):
        browser = RRBrowser(FakeClient())
        rows = fs.search(browser, '154.2500', stid=7, ctid=1)
        self.assertEqual([(r['type'], r['name'], r['where']) for r in rows],
                         [('Conventional', 'Lakeside FD', 'Lakeside County'),
                          ('Trunked site', 'Lakeside Trunk', 'Lakeside Trunk › North')])
        self.assertEqual((rows[0]['mode'], rows[0]['tone']), ('FMN', '107.2 PL'))
        self.assertEqual((rows[1]['tone'], rows[1]['description']), ('NAC 293', 'LCN 1 · control'))

    def test_whole_state_searches_every_trunked_system_once_and_caches_sites(self):
        client = FakeClient()
        browser = RRBrowser(client)
        seen = []
        rows = fs.search(browser, '154.25', stid=7, progress=lambda d, t: seen.append((d, t)))
        self.assertEqual({r['where'] for r in rows if r['type'] == 'Conventional'}, {'Lakeside County', 'Hill County'})
        self.assertEqual(sorted(c[1] for c in client.calls if c[0] == 'sites'), [900, 901])
        self.assertEqual(seen[-1], (2, 2))
        fs.search(browser, '851.2625', stid=7)
        self.assertEqual(len([c for c in client.calls if c[0] == 'sites']), 2)       # read once per session
        self.assertEqual([r['where'] for r in fs.search(browser, '851.2625', stid=7) if r['type'] == 'Trunked site'],
                         ['Statewide P25 › Hilltop'])

    def test_falls_back_to_each_county_and_can_stop(self):
        client = FakeClient(state_search=False)
        browser = RRBrowser(client)
        rows = fs.search(browser, '154.25', stid=7, trunked=False)
        self.assertEqual(len(rows), 2)
        self.assertEqual(len([c for c in client.calls if c[0] == 'county-search']), 2)
        with self.assertRaises(fs.Cancelled):
            fs.search(RRBrowser(FakeClient(state_search=False)), '154.25', stid=7, cancel=lambda: True)
        with self.assertRaises(ValueError):
            fs.search(browser, 'abc', stid=7)

    def test_adding_a_result_and_the_monitor_request(self):
        row = fs.search(RRBrowser(FakeClient()), '154.25', stid=7, ctid=1, trunked=False)[0]
        request = fs.request_for(row)
        self.assertEqual((request['frequency'], request['channel'], request['tone'], request['source']),
                         ('154.250000', 'Lakeside FD', '107.2', 'rr'))
        sent = monitor_link.clean_request({'action': 'rr_freq', 'frequency': '154.2500MHz', 'tone': '107.2'})
        self.assertEqual((sent['action'], sent['frequency'], sent['tone']), ('rr_freq', '154.250000', '107.2'))
        self.assertEqual(monitor_link.clean_request({'action': 'rm -rf', 'frequency': '154.25'})['action'], 'edit')


if __name__ == '__main__':
    unittest.main()
