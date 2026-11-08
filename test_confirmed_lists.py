# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Favorites lists confirmed working on a real SDS100 (v0.1.2): f_000014 (Palmetto 800 P25, Oconee
conventional, Oconee County Emergency Services DMR one-frequency) and f_000012 (Pickens conventional,
Palmetto 800 P25, FleetTalk Carolinas NXDN). New lists must come out the same, whether the selection
comes from the Uniden database or from RadioReference."""
import unittest
from pathlib import Path

import new_favorites_list as nfl
import rr_convert as rc
import scanner_list_sync as sync

FIX = Path(__file__).resolve().parent / 'test_fixtures'
F14 = FIX / 'confirmed_f_000014_p25_dmr.hpd'
F12 = FIX / 'confirmed_f_000012_p25_nxdn.hpd'
F31 = FIX / 'confirmed_f_000031_mototrbo_sentinel.hpd'     # written by Sentinel (v0.1.3)


def systems(path):
    rows = [line.split('\t') for line in path.read_text(encoding='cp1252').splitlines() if line.strip()]
    found, current = {}, None
    for row in rows[2:]:
        if row[0] in ('Trunk', 'Conventional'):
            current = found.setdefault(row[3], [row])
        elif row[0] != 'DQKs_Status' and current is not None:
            current.append(row)
    return found


def built(records):
    rows, _enc, _nl = nfl.build_new_list_rows(records)
    return [r for r in rows[2:] if r[0] != 'DQKs_Status'], rows


def raw(rows):
    return ('\r\n'.join('\t'.join(r) for r in rows) + '\r\n').encode('cp1252')


class ConfirmedListTests(unittest.TestCase):
    def test_every_system_is_rebuilt_exactly(self):
        for path in (F12, F14):
            for name, rows in systems(path).items():
                mine, whole = built(rows)
                if path == F14 and rows[0][6] == 'P25Standard':
                    # Sentinel-style: no band plan, 8-column site frequencies; both forms work on the scanner.
                    mine = [r[:8] if r[0] == 'T-Freq' else r for r in mine if r[0] != 'BandPlan_P25']
                self.assertEqual(mine, rows, f'{path.name}: {name}')
                self.assertTrue(sync.assess_new_hpd(raw(whole))[0], name)

    def test_mototrbo_is_rebuilt_exactly(self):
        rows = systems(F31)['Charleston Wireless Group/James White']
        mine, whole = built(rows)
        self.assertEqual(mine, rows)
        self.assertTrue(sync.assess_new_hpd(raw(whole))[0])
        conventional = systems(F31)['Businesses']
        self.assertEqual(built(conventional)[0], conventional)

    def test_the_confirmed_files_pass_the_export_checks(self):
        for path in (F12, F14, F31):
            self.assertTrue(sync.assess_new_hpd(path.read_bytes())[0], path.name)


class RadioReferenceMatchesConfirmedTests(unittest.TestCase):
    def test_dmr_one_frequency(self):
        real = systems(F14)['Oconee County Emergency Services']
        sites = [{'siteDescr': r[3], 'lat': float(r[5]), 'lon': float(r[6]), 'range': float(r[7]),
                  'siteFreqs': [{'lcn': 0, 'freq': int(f[5]) / 1e6, 'colorCode': int(f[7])}]}
                 for r, f in zip(real, real[1:]) if r[0] == 'Site']
        cat = {'tgCid': 1, 'tgCname': 'Oconee Co FD', 'lat': 34.73738, 'lon': -83.06316, 'range': 20}
        tgs = [{'tgDec': int(r[5]), 'tgDescr': r[3], 'tgSlot': r[16], 'tgCid': 1, 'enc': 0,
                'tags': [{'tagDescr': 'Fire-Tac'}]} for r in real if r[0] == 'TGID']
        section, why = rc.trunk_section({'sName': real[0][3]}, 'DMR Tier II', sites, [cat], tgs)
        self.assertIsNone(why)
        mine, whole = built(section['records'])
        self.assertEqual(mine, real)
        self.assertTrue(sync.assess_new_hpd(raw(whole))[0])

    def test_nxdn_nexedge(self):
        real = systems(F12)['FleetTalk Carolinas']
        sites, cur = [], None
        for r in real:
            if r[0] == 'Site':
                cur = {'siteDescr': r[3], 'lat': float(r[5]), 'lon': float(r[6]), 'range': float(r[7]), 'siteFreqs': []}
                sites.append(cur)
            elif r[0] == 'T-Freq':
                cur['siteFreqs'].append({'lcn': int(r[6]), 'freq': int(r[5]) / 1e6, 'colorCode': int(r[7][4:])})
        group = next(r for r in real if r[0] == 'T-Group')
        cat = {'tgCid': 5, 'tgCname': group[3], 'lat': float(group[5]), 'lon': float(group[6]), 'range': float(group[7])}
        service = {v: k for k, v in rc.SERVICE_TYPES.items()}
        tgs = [{'tgDec': int(r[5]), 'tgDescr': r[3], 'tgCid': 5, 'enc': 0, 'tags': [{'tagDescr': service[r[7]]}]}
               for r in real if r[0] == 'TGID']
        section, why = rc.trunk_section({'sName': real[0][3]}, 'NXDN NEXEDGE 48', sites, [cat], tgs)
        self.assertIsNone(why)
        mine, _whole = built(section['records'])
        self.assertEqual(mine, real)

    def test_mototrbo(self):
        real = systems(F31)['Charleston Wireless Group/James White']
        sites, cur = [], None
        for r in real:
            if r[0] == 'Site':
                cur = {'siteDescr': r[3], 'lat': float(r[5]), 'lon': float(r[6]), 'range': float(r[7]), 'siteFreqs': []}
                sites.append(cur)
            elif r[0] == 'T-Freq':
                cur['siteFreqs'].append({'lcn': int(r[6]), 'freq': int(r[5]) / 1e6,
                                         'colorCode': int(r[7]) if r[7].isdigit() else None})
        group = next(r for r in real if r[0] == 'T-Group')
        cat = {'tgCid': 3, 'tgCname': group[3], 'lat': float(group[5]), 'lon': float(group[6]), 'range': float(group[7])}
        tgs = [{'tgDec': int(r[5]), 'tgDescr': r[3], 'tgCid': 3, 'tgSlot': 1, 'enc': 0, 'tags': [{'tagDescr': 'Business'}]}
               for r in real if r[0] == 'TGID']
        section, why = rc.trunk_section({'sName': real[0][3]}, 'MotoTRBO Capacity Plus', sites, [cat], tgs)
        self.assertIsNone(why)
        mine, _whole = built(section['records'])
        self.assertEqual(mine, real)

    def test_types_not_confirmed_yet_are_refused(self):
        multi = [{'siteDescr': 'A', 'siteFreqs': [{'freq': 451.1, 'colorCode': 1}, {'freq': 452.2, 'colorCode': 1}]}]
        for description, sites in (('MotoTRBO Capacity Plus', multi), ('NXDN IDAS', []),     # multi: no LCNs
                                   ('Motorola Type II Smartzone', []), ('EDACS Standard', []), ('LTR Standard', [])):
            system_type, why = rc.trunk_type(description, sites)
            self.assertIsNone(system_type, description)
            self.assertTrue(why)
        self.assertEqual(rc.trunk_type('DMR Tier III', [{'siteFreqs': [{'freq': 451.1}]}])[0], 'DmrOneFrequency')


if __name__ == '__main__':
    unittest.main()
