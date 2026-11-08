# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""RadioReference data as database records (v0.1.1): the rows must be the ones the new-list builder accepts."""
import unittest
from pathlib import Path

import new_favorites_list as nfl
import rr_convert as rc
import rr_source

FIXTURES = Path(__file__).resolve().parent / 'test_fixtures'
DETAILS = {'sName': 'Palmetto 800', 'sType': 8, 'lat': 34.0, 'lon': -81.0, 'range': 150}
SITES = [{'siteDescr': 'Greenville County Simulcast', 'siteNumber': '023', 'nac': '1DB', 'lat': 34.885930,
          'lon': -82.348020, 'range': 30, 'tdma_cc': 0,
          'siteFreqs': [{'lcn': 1, 'freq': 851.1875, 'use': 'd'}, {'lcn': 2, 'freq': 851.875, 'use': ''},
                        {'lcn': 3, 'freq': 851.875, 'use': ''}]},
         {'siteDescr': 'Empty site', 'siteFreqs': []}]
CATS = [{'tgCid': 7, 'tgCname': 'Greenville City Police', 'lat': 0, 'lon': 0, 'range': 0},
        {'tgCid': 9, 'tgCname': 'Nothing here'}]
TGS = [{'tgDec': 44358, 'tgAlpha': 'GVL PD Disp', 'tgDescr': 'Police Dispatch', 'enc': 0, 'tgCid': 7,
        'tags': [{'tagId': 2, 'tagDescr': 'Law Dispatch'}]},
       {'tgDec': 44357, 'tgAlpha': 'GVL PD Inv', 'tgDescr': 'Investigations', 'enc': 2, 'tgCid': 7,
        'tags': [{'tagId': 23, 'tagDescr': 'Law Talk'}]},
       {'tgDec': 44356, 'tgAlpha': 'GVL PD Traffic', 'tgDescr': '', 'enc': 1, 'tgCid': 7,
        'tags': [{'tagId': 7, 'tagDescr': 'Law Tactical'}]},
       {'tgDec': 50001, 'tgAlpha': 'Lost', 'tgDescr': 'No category', 'tgCid': 99, 'tags': []}]
SUB = {'scid': 11, 'scName': 'Fire', 'lat': 34.85, 'lon': -82.39, 'range': 25}
FREQS = [{'out': 154.43, 'descr': 'Fire Dispatch', 'mode': 'FM', 'tone': '107.2 PL',
          'tags': [{'tagDescr': 'Fire Dispatch'}]},
         {'out': 154.28, 'alpha': 'Fireground', 'mode': 'FMN', 'tone': '023 DPL', 'tags': [{'tagDescr': 'Fire-Tac'}]},
         {'out': 460.0, 'descr': 'P25 channel', 'mode': 'P25', 'tone': 'NAC 293', 'tags': []},
         {'out': 'nonsense', 'descr': 'bad'}]


class ConvertTests(unittest.TestCase):
    def test_trunk_rows_match_the_real_database_layout(self):
        section, why = rc.trunk_section(DETAILS, 'Project 25 Phase II', SITES, CATS, TGS)
        self.assertIsNone(why)
        real = [l.rstrip('\r\n').split('\t')
                for l in (FIXTURES / 'real_hpdb_palmetto_trunk_excerpt.txt').read_text(encoding='cp1252').splitlines()]
        made = section['records']
        for kind in ('Trunk', 'Site', 'T-Freq', 'T-Group', 'TGID'):
            mine = next(r for r in made if r[0] == kind)
            theirs = next(r for r in real if r[0] == kind)
            self.assertEqual(len(mine), len(theirs), kind)
        site = next(r for r in made if r[0] == 'Site')
        self.assertEqual(site[3], 'Greenville County Simulcast')
        self.assertEqual(site[17], '1DB')
        self.assertEqual([r[5] for r in made if r[0] == 'T-Freq'], ['851187500', '851875000'])   # no duplicate
        names = [r[3] for r in made if r[0] == 'TGID']
        self.assertEqual(names, ['Police Dispatch', 'GVL PD Traffic', 'No category'])          # enc 2 left out
        self.assertEqual([r[7] for r in made if r[0] == 'TGID'], ['2', '7', '21'])
        groups = [r for r in made if r[0] == 'T-Group']
        self.assertEqual([g[3] for g in groups], ['Greenville City Police', 'Other talkgroups'])
        self.assertEqual(groups[0][5:8], ['34.000000', '-81.000000', '150.0'])                  # system's area

    def test_trunk_rows_build_a_real_favorites_list(self):
        section, _ = rc.trunk_section(DETAILS, 'APCO-25 Common Air Interface', SITES, CATS, TGS)
        rows, encoding, newline = nfl.build_new_list_rows(section['records'])
        kinds = [r[0] for r in rows]
        self.assertEqual(kinds[:4], ['TargetModel', 'FormatVersion', 'Trunk', 'DQKs_Status'])
        self.assertIn('BandPlan_P25', kinds)
        self.assertEqual(sum(k == 'TGID' for k in kinds), 3)

    def test_other_trunk_types_are_refused_for_now(self):
        section, why = rc.trunk_section(DETAILS, 'Motorola Type II Smartnet', SITES, CATS, TGS)
        self.assertIsNone(section)
        self.assertIn('P25', why)
        section, why = rc.trunk_section(DETAILS, 'Project 25 Phase I', [], CATS, TGS)
        self.assertIsNone(section)

    def test_conventional_rows_build_a_real_favorites_list(self):
        area = {'lat': 34.8, 'lon': -82.4, 'range': 30}
        section = rc.conventional_section('Greenville County', [(SUB, FREQS), ({'scName': 'Empty'}, [])], area)
        made = section['records']
        freqs = [r for r in made if r[0] == 'C-Freq']
        self.assertEqual([(r[3], r[5], r[6], r[7], r[8]) for r in freqs],
                         [('Fire Dispatch', '154430000', 'FM', 'TONE=C107.2', '3'),
                          ('Fireground', '154280000', 'NFM', 'TONE=D023', '8'),
                          ('P25 channel', '460000000', 'AUTO', 'NAC=293', '21')])
        real = [l.split('\t') for l in (FIXTURES / 'real_hpdb_greenville_county.txt').read_text(
            encoding='cp1252').splitlines()]
        for kind in ('Conventional', 'C-Group', 'C-Freq'):
            mine = next(r for r in made if r[0] == kind)
            theirs = next(r for r in real if r[0] == kind)
            self.assertEqual(len(mine), len(theirs), kind)
        rows, _enc, _nl = nfl.build_new_list_rows(made)
        self.assertEqual(sum(r[0] == 'C-Freq' for r in rows), 3)
        self.assertEqual([r[3] for r in rows if r[0] == 'C-Group'], ['Fire'])

    def test_tones_modes_and_service_types(self):
        cases = {'100.0 PL': 'TONE=C100.0', '156.7': 'TONE=C156.7', '023 DPL': 'TONE=D023', 'D411N': 'TONE=D411',
                 'NAC 293': 'NAC=293', 'CC1': 'ColorCode=1', 'RAN 4': 'RAN=4', 'CSQ': '', '': ''}
        for tone, want in cases.items():
            self.assertEqual(rc.audio_option(tone), want, tone)
            self.assertTrue(nfl.AUDIO_OPTION.fullmatch(want), want)
        self.assertEqual(rc.audio_option('', color_code='3'), 'ColorCode=3')
        self.assertEqual([rc.modulation(m) for m in ('FM', 'fmn', 'AM', 'P25', 'DMR', None)],
                         ['FM', 'NFM', 'AM', 'AUTO', 'AUTO', 'AUTO'])
        self.assertEqual(rc.service_type([{'tagDescr': 'EMS-Talk'}]), '25')
        self.assertEqual(rc.service_type([{'tagDescr': 'Law Tactical'}]), '7')
        self.assertEqual(rc.service_type([{'tagDescr': 'Something new'}]), '21')
        for value in rc.SERVICE_TYPES.values():
            self.assertTrue(nfl.valid_func_tag(value))

    def test_long_names_are_clipped(self):
        self.assertEqual(len(rc.clip('x' * 100, 'y')), 64)
        self.assertEqual(rc.clip('  ', 'fallback'), 'fallback')


class FakeClient:
    def __init__(self):
        self.calls = []

    def _log(self, name, value):
        self.calls.append(name)
        return value

    def country(self, coid):
        return self._log('country', {'stateList': [{'stid': 45, 'stateName': 'South Carolina'},
                                                   {'stid': 37, 'stateName': 'North Carolina'}]})

    def state(self, stid):
        return self._log('state', {'countyList': [{'ctid': 2335, 'countyName': 'Greenville'}],
                                   'trsList': [{'sid': 6060, 'sName': 'Palmetto 800'}],
                                   'agencyList': {'aid': 100, 'aName': 'SC Highway Patrol'}})

    def county(self, ctid):
        return self._log('county', {'countyName': 'Greenville', 'lat': 34.8, 'lon': -82.4, 'range': 30,
                                    'cats': [{'cid': 1, 'cName': 'Fire', 'subcats': [SUB]}], 'trsList': [],
                                    'agencyList': []})

    def subcat_freqs(self, scid):
        return self._log('subcat', [dict(f, mode=1 if f.get('mode') == 'FM' else f.get('mode')) for f in FREQS])

    def mode(self, mode):
        return self._log('mode', [{'mode': 1, 'modeName': 'FM'}])

    def trs_details(self, sid):
        return self._log('trs', DETAILS)

    def trs_type(self, type_id):
        return self._log('type', [{'sType': 8, 'sTypeDescr': 'Project 25 Phase II'}])

    def trs_sites(self, sid):
        return self._log('sites', SITES)

    def trs_talkgroup_cats(self, sid):
        return self._log('cats', CATS)

    def trs_talkgroups(self, sid):
        return self._log('tgs', TGS)


class BrowserTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.b = rr_source.RRBrowser(self.client)

    def test_places_and_systems(self):
        self.assertEqual(self.b.states(1), [(37, 'North Carolina'), (45, 'South Carolina')])
        self.assertEqual(self.b.counties(45), [(2335, 'Greenville')])
        self.assertEqual(self.b.systems(45), [('Palmetto 800', 'Trunk', ('trs', 6060)),
                                              ('SC Highway Patrol', 'Conventional', ('agency', 100))])
        self.assertEqual(self.b.systems(45, 2335), [('Greenville County (conventional)', 'Conventional',
                                                     ('county', 2335))])
        self.b.states(1)
        self.assertEqual(self.client.calls.count('country'), 1)          # kept for the session

    def test_loading_systems(self):
        section, why = self.b.load(('trs', 6060))
        self.assertIsNone(why)
        self.assertEqual(section['name'], 'Palmetto 800')
        section, why = self.b.load(('county', 2335))
        self.assertEqual(section['name'], 'Greenville County')
        fm = next(r for r in section['records'] if r[0] == 'C-Freq')
        self.assertEqual(fm[6], 'FM')                                    # mode number 1 looked up
        self.b.load(('county', 2335))
        self.assertEqual(self.client.calls.count('subcat'), 1)


if __name__ == '__main__':
    unittest.main()
