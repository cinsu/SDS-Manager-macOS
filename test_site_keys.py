# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Site quick keys (v0.1.22): Site column 16, in the same set as the system's department keys."""
import unittest

import favorites_clipboard as clip
import keys_export as ke
import keys_model as km
import quick_key_map as qkm
import scanner_list_sync as sync
from test_add_heard import raw
from test_favorites_clipboard import FIX, native, rows_of
from test_list_sync_export import SyncBase
from test_export_keys import LIST, ExportKeysTests
import scanner_first_write as writer


class SiteKeyTests(SyncBase):
    def model(self):
        return km.model_for_configuration(self.config)

    def sites(self, m):
        return [i for i in m.items if i['level'] == 'site']

    def test_sites_share_the_department_keys(self):
        m = self.model()
        sites = self.sites(m)
        self.assertTrue(sites)
        site = sites[0]
        system = m.parent(site)
        self.assertEqual((system['name'], site['key'], site['detail']), ('Palmetto 800', None, 'Site'))
        department = next(i for i in m.children(system['id']) if i['level'] == 'department' and i['key'] is not None)
        self.assertEqual(site['key_scope'], department['key_scope'])
        m.set_number(site, 'key', department['key'])
        self.assertTrue(any('used by 2' in t and site['name'] in t for k, t in m.warnings() if k == 'shared'))
        m.set_on(department, False)
        self.assertEqual(m.scanned(site)[0], False)
        self.assertEqual(m.next_free(site, 'key'), m.next_free(department, 'key'))
        with self.assertRaises(ValueError):
            m.set_number(site, 'tag', 1)
        edits = [e for e in m.row_edits() if e[3] == km.SITE_KEY]
        self.assertEqual(edits, [(site['ref'][1], site['ref'][2], site['ref'][3], 16, str(department['key']))])
        self.assertIn('Department/site key', '\n'.join(m.describe_changes()))
        names = [d['name'] for l in km.monitor_summary(m)['lists'] for s in l['systems'] for d in s['departments']]
        self.assertIn(site['name'] + ' (site)', names)

    def test_badge_quick_keys_spreadsheet_and_card(self):
        row = ['Site', '', '', 'Caesars Head'] + ['x'] * 12 + ['07', '1DB', 'Global']
        self.assertEqual(km.badge(row), 'Key 07')
        rows = rows_of(native(FIX / 'real_sds100_f_000001.hpd'))
        site = next(r for r in rows if r[0] == 'Site')
        site[16] = '5'
        departments = [d for s in qkm.read_systems(rows) for d in s['departments']]
        self.assertIn((site[3] + ' (site)', 5), [(d['name'], d['key']) for d in departments])
        m = self.model()
        sheet = ke.rows_for(m, 'department', ('site',))
        self.assertTrue(any(values[2].endswith(' (site)') for values, _ref in sheet))
        site_item = self.sites(m)[0]
        changed, problems = ke.apply_values(m, {ke.ref_text(site_item): {'name': site_item['name'] + ' (site)',
                                                                         'key': 9}})
        self.assertEqual((changed, problems, site_item['key']), (1, [], 9))

    def test_export_checks_and_paste(self):
        lists = native(FIX / 'real_sds100_f_000001.hpd')
        original = raw(rows_of(lists))
        site = next(r for e in lists for r in e['records'] if r[0] == 'Site')
        site[16] = '12'
        self.assertTrue(sync.assess_new_hpd(raw(rows_of(lists)), original)[0])
        site[16] = '100'
        ok, why = sync.assess_new_hpd(raw(rows_of(lists)), original)
        self.assertFalse(ok)
        self.assertIn('site quick key', why)
        self.assertEqual(clip.NUMBER_FIELDS[('Site', 16)], 'dept-key')



class SiteKeyExportTests(SyncBase):
    entries, save, eligible = ExportKeysTests.entries, ExportKeysTests.save, ExportKeysTests.eligible

    def test_a_site_quick_key_exports(self):
        entries = self.entries()
        site = next(r for e in entries for r in e['records'] if r[0] == 'Site')
        site[16] = '4'
        self.save(entries)
        ok, why = self.eligible()
        self.assertTrue(ok, why)
        writer.execute_first_write(self.config, self.scanner)
        self.assertEqual((self.scanner / LIST).read_bytes(), (self.local / LIST).read_bytes())
        sites = [i for i in km.model_for_configuration(self.config).items if i['level'] == 'site']
        self.assertEqual(sites[0]['key'], 4)


if __name__ == '__main__':
    unittest.main()
