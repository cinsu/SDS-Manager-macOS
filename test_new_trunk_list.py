# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""New Favorites Lists from TRUNKED systems.

Ground truth: real_sds100_f_000002.hpd is a Sentinel-written list for Palmetto 800;
real_hpdb_palmetto_trunk_excerpt.txt holds the same system's database rows (same sites and
departments).  The builder must reproduce the native layout from the database rows alone.
"""
import unittest
from pathlib import Path

import scanner_first_write as writer
import scanner_list_sync as sync
from new_favorites_list import build_new_list_rows, DEFAULT_P25_BANDPLAN
from native_favorites_reader import parse_native_favorites
from scanner_favorites_expanded import _hierarchy
from test_list_sync_export import SyncBase
import scanner_configurations as sc

FIX = Path(__file__).resolve().parent / 'test_fixtures'


def rows_of(path):
    return [l.split('\t') for l in Path(path).read_bytes().decode('cp1252').splitlines()]


DB = rows_of(FIX / 'real_hpdb_palmetto_trunk_excerpt.txt')
NATIVE = rows_of(FIX / 'real_sds100_f_000002.hpd')


def raw(rows):
    return ('\r\n'.join('\t'.join(r) for r in rows) + '\r\n').encode('cp1252')


def of(rows, kind):
    return [r for r in rows if r[0] == kind]


class TrunkBuilderTests(unittest.TestCase):
    def setUp(self):
        self.rows, self.enc, self.nl = build_new_list_rows(DB)

    def test_layout_matches_the_real_sentinel_list(self):
        self.assertEqual({(r[0], len(r)) for r in self.rows}, {(r[0], len(r)) for r in NATIVE})
        self.assertEqual([r[0] for r in self.rows if r[0] not in ('T-Freq', 'TGID')],
                         [r[0] for r in NATIVE if r[0] not in ('T-Freq', 'TGID')])
        for kind in ('DQKs_Status', 'Site', 'BandPlan_P25'):
            self.assertEqual(of(self.rows, kind), of(NATIVE, kind), kind)
        self.assertEqual(of(self.rows, 'T-Freq')[:10], of(NATIVE, 'T-Freq')[:10])
        self.assertEqual(self.rows[2][:21], NATIVE[2][:21])

    def test_departments_and_talkgroups_take_database_values_and_defaults(self):
        group = of(self.rows, 'T-Group')[0]
        self.assertEqual(group, of(NATIVE, 'T-Group')[0])
        tgid = of(self.rows, 'TGID')[0]
        self.assertEqual(tgid[:3], ['TGID', '', ''])
        self.assertEqual(tgid[8:], ['2', '0', 'Off', 'Auto', 'Off', 'On', 'Off', 'Off', 'Any'])
        source = next(r for r in DB if r[0] == 'TGID' and r[3] == tgid[3])
        self.assertEqual((tgid[3], tgid[5], tgid[6], tgid[7]), (source[3], source[5], source[6], source[7]))

    def test_nothing_is_assigned(self):
        for r in of(self.rows, 'TGID'):
            self.assertEqual((r[4], r[14], r[15]), ('Off', 'Off', 'Off'))
        for r in of(self.rows, 'T-Freq'):
            self.assertEqual(r[4], 'Off')

    def test_accepted_by_all_validators(self):
        self.assertTrue(sync.assess_new_hpd(raw(self.rows))[0])
        _hierarchy(self.rows)
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'n.hpd'
            p.write_bytes(raw(self.rows))
            self.assertEqual(parse_native_favorites(p)['warnings'], [])

    def test_band_plan_in_database_is_kept(self):
        rows = [list(r) for r in DB]
        i = next(k for k, r in enumerate(rows) if r[0] == 'Site')
        custom = ['BandPlan_P25', 'SiteId=1'] + ['5'] * 48
        rows.insert(i + 1, custom)
        out, _, _ = build_new_list_rows(rows)
        self.assertEqual(of(out, 'BandPlan_P25')[0], ['BandPlan_P25', ''] + ['5'] * 48)
        self.assertEqual(len(of(out, 'BandPlan_P25')), 3)

    def test_non_p25_keeps_database_channel_numbers_and_ignores_band_types_for_p25(self):
        rows = [list(r) for r in DB]
        rows[0][6] = 'MotoTrbo'
        for r in rows:
            if r[0] == 'T-Freq':
                r[6] = '7'
        out, _, _ = build_new_list_rows(rows)
        self.assertEqual(out[2][6], 'MotoTrbo')
        self.assertTrue(all(r[6] == '7' for r in of(out, 'T-Freq')))
        self.assertEqual(of(out, 'BandPlan_P25'), [])          # only P25 Standard gets the default
        self.assertTrue(sync.assess_new_hpd(raw(out))[0])

    def test_errors(self):
        def with_change(fn):
            rows = [list(r) for r in DB]
            fn(rows)
            with self.assertRaises(ValueError):
                build_new_list_rows(rows)
        with_change(lambda rows: rows[0].__setitem__(6, 'Weird'))
        with_change(lambda rows: next(r for r in rows if r[0] == 'T-Freq').__setitem__(5, '851.3'))
        with_change(lambda rows: next(r for r in rows if r[0] == 'TGID').__setitem__(6, 'BOTH'))
        with_change(lambda rows: next(r for r in rows if r[0] == 'TGID').__setitem__(7, ''))
        with_change(lambda rows: next(r for r in rows if r[0] == 'TGID').__setitem__(5, 'x'))
        with_change(lambda rows: next(r for r in rows if r[0] == 'Site').__setitem__(11, 'Rectangles'))
        with_change(lambda rows: [rows.remove(r) for r in [r for r in rows if r[0] == 'T-Group']])
        with_change(lambda rows: [rows.remove(r) for r in [r for r in rows if r[0] == 'TGID']])
        rows = [r for r in DB if r[0] not in ('T-Freq',)]
        with self.assertRaises(ValueError):
            build_new_list_rows(rows)                                # sites need frequencies

    def test_duplicates_dropped_and_empty_departments_removed(self):
        rows = [list(r) for r in DB]
        t = next(r for r in rows if r[0] == 'TGID')
        rows.insert(rows.index(t) + 1, list(t))
        f = next(r for r in rows if r[0] == 'T-Freq')
        rows.insert(rows.index(f) + 1, list(f))
        out, _, _ = build_new_list_rows(rows)
        self.assertEqual(len(of(out, 'TGID')), len(of(self.rows, 'TGID')))
        self.assertEqual(len(of(out, 'T-Freq')), len(of(self.rows, 'T-Freq')))

    def test_default_band_plan_equals_the_real_one(self):
        self.assertEqual(DEFAULT_P25_BANDPLAN, of(NATIVE, 'BandPlan_P25')[0])

    def test_assess_rejects_bad_trunk_rows(self):
        for kind, idx, value in (('Trunk', 6, 'X'), ('Site', 11, 'Rectangles'), ('T-Freq', 5, '12'),
                                 ('T-Group', 8, 'Rectangles'), ('TGID', 6, 'BOTH'), ('TGID', 16, '9'),
                                 ('TGID', 7, '99')):
            rows = [list(r) for r in self.rows]
            next(r for r in rows if r[0] == kind)[idx] = value
            self.assertFalse(sync.assess_new_hpd(raw(rows))[0], (kind, idx))


def as_database(native_rows):
    """Re-express a native trunk section the way the master database holds it (IDs, 20-column sites)."""
    out = []
    for r in native_rows:
        if r[0] in ('TargetModel', 'FormatVersion', 'DQKs_Status'):
            continue
        r = list(r)
        if r[0] == 'Trunk':
            r[1:3] = ['TrunkId=1', 'StateId=45']
            r[7:21] = [''] * 14
            r[21] = 'NEXEDGE'
        elif r[0] == 'Site':
            r = r[:1] + ['SiteId=1', 'TrunkId=1'] + r[3:9] + ['Standard', 'Wide', 'Circle'] + [''] * 5 \
                + ['Srch', 'Global', 'FDMA']
        elif r[0] == 'T-Freq':
            r[1:3] = ['TFreqId=0', 'SiteId=1']
            r[4] = ''
        elif r[0] == 'T-Group':
            r[1:3] = ['TGroupId=1', 'TrunkId=1']
            r[9] = ''
        elif r[0] == 'TGID':
            r[1:3] = ['Tid=1', 'TGroupId=1']
            r[8:16] = [''] * 8
        out.append(r)
    return out


class OtherSystemTypeTests(unittest.TestCase):
    def test_nxdn_matches_real_sentinel_section(self):
        native = rows_of(FIX / 'real_sds100_nxdn_section.hpd')
        rows, _, _ = build_new_list_rows(as_database(native))
        self.assertEqual(rows[2], native[2])                  # Trunk header incl. NEXEDGE
        self.assertEqual([r for r in rows[4:]], [r for r in native[4:]])
        self.assertEqual(of(rows, 'BandPlan_P25'), [])
        self.assertTrue(sync.assess_new_hpd(raw(rows))[0])

    def test_dmr_matches_real_sentinel_section_from_real_database_rows(self):
        db = rows_of(FIX / 'real_hpdb_oconee_dmr_excerpt.txt')
        native = rows_of(FIX / 'real_sds100_dmr_section.hpd')
        rows, _, _ = build_new_list_rows(db)
        mine = [r for r in rows[4:]]
        real = [r for r in native[4:]]
        self.assertEqual(rows[2], native[2])                  # IDAS, same defaults
        self.assertEqual(len(mine), len(real))                # the database has since renamed one site, nothing else
        by_name = {r[3]: r for r in real if r[0] == 'Site'}
        for r in mine:
            if r[0] == 'Site' and r[3] in by_name:
                self.assertEqual(r, by_name[r[3]], r[3])
        self.assertEqual(of(mine, 'TGID'), of(real, 'TGID'))
        self.assertEqual([r[6] for r in of(mine, 'T-Freq')], [r[6] for r in of(real, 'T-Freq')])
        self.assertTrue(all(r[6] == '0' for r in of(rows, 'T-Freq')))
        self.assertIn('8', {r[7] for r in of(rows, 'T-Freq')})  # bare DMR colour code kept
        self.assertTrue(sync.assess_new_hpd(raw(rows))[0])


class TrunkExportTests(SyncBase):
    def test_new_trunk_list_is_created_and_exported(self):
        rows, enc, nl = build_new_list_rows(DB)
        created = sc.create_local_favorites_list(self.config, 'Palmetto 800 test', rows, enc, nl)
        before = self.scanner_state()
        ok, reason = writer.first_write_eligibility(self.config, self.scanner)
        self.assertTrue(ok, reason)
        result = writer.execute_first_write(self.config, self.scanner)
        name = 'favorites_lists/' + created['filename']
        after = self.scanner_state()
        self.assertEqual(result['added'], [name])
        self.assertEqual(after[name], raw(rows))
        self.assertTrue(after['favorites_lists/f_list.cfg'].startswith(before['favorites_lists/f_list.cfg']))


if __name__ == '__main__':
    unittest.main()
