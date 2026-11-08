# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Keys & Tags helpers and scan profiles (v0.1.9), on real SDS100 files."""
import keys_model as km
import scanner_configurations as sc
from test_list_sync_export import SyncBase


class HelperAndProfileTests(SyncBase):
    def find(self, m, level, name):
        return next(i for i in m.items if i['level'] == level and i['name'] == name)

    def test_tags_in_blocks_per_department(self):
        m = km.model_for_configuration(self.config)
        system = self.find(m, 'system', 'Greenville')
        departments = [d for d in m.children(system['id'])]
        self.assertEqual(m.tags_by_department(system, 50, 100), len(departments))
        for n, department in enumerate(departments):
            tags = [c['tag'] for c in m.children(department['id'])]
            self.assertEqual(tags, list(range(100 + 50 * n, 100 + 50 * n + len(tags))))
        self.assertEqual([k for k, _t in m.warnings() if k == 'shared'], [])
        with self.assertRaises(ValueError):                  # 11 departments don't fit from 500 in 100s
            m.tags_by_department(system, 100, 500)

    def test_match_tags_to_keys(self):
        m = km.model_for_configuration(self.config)
        system = self.find(m, 'system', 'Greenville')
        self.assertEqual(m.match_tags_to_keys([system]), 1)
        self.assertEqual(system['tag'], 1)
        self.assertEqual(m.match_tags_to_keys([system]), 0)
        police = self.find(m, 'department', 'Greenville (City) - Police')
        self.assertEqual(m.match_tags_to_keys([police]), 0)          # departments have no number tags

    def test_profiles_save_and_restore_every_switch(self):
        m = km.model_for_configuration(self.config)
        home = m.profile()
        self.assertEqual(len(home['monitor']), 28)                    # every list in f_list.cfg
        self.assertIn('f_000001.hpd|Greenville', home['dept'])
        police = self.find(m, 'department', 'Greenville (City) - Police')
        greenville = self.find(m, 'list', 'Greenville County')
        m.set_on(police, False)
        m.set_monitor(greenville, False)
        storm = m.profile()
        km.save_profiles(self.config, {'Home': home, 'Storm': storm})
        self.assertEqual(sorted(km.load_profiles(self.config)), ['Home', 'Storm'])
        self.assertTrue(str(km.profiles_path(self.config)).endswith('scan-profiles/' + self.config.name + '.json'))
        sc.verify_configuration(self.config)                          # profiles are not in the configuration
        fresh = km.model_for_configuration(self.config)
        self.assertEqual(fresh.apply_profile(km.load_profiles(self.config)['Storm']), [])
        self.assertFalse(fresh.key_on(self.find(fresh, 'department', 'Greenville (City) - Police')))
        self.assertFalse(self.find(fresh, 'list', 'Greenville County')['monitor'])
        fresh.apply_profile(home)
        self.assertFalse(fresh.describe_changes())
        partial = dict(home, monitor={'f_000001.hpd': True})
        missing = fresh.apply_profile(partial)
        self.assertIn('SC Highway Patrol', missing)
        self.assertNotIn('Greenville County', missing)


class MonitorFileTests(SyncBase):
    def test_shared_file_for_the_monitor(self):
        import json
        from unittest.mock import patch
        km.save_profiles(self.config, {'Home': km.model_for_configuration(self.config).profile()})
        with patch.object(km, 'monitor_file_path', lambda: self.base / 'monitor-keys.json'):
            path = km.write_monitor_file(self.config, 'Home config')
        data = json.loads(path.read_text())
        self.assertEqual(data['configuration'], 'Home config')
        greenville = data['lists'][0]
        self.assertEqual((greenville['name'], greenville['key'], greenville['filename']),
                         ('Greenville County', 0, 'f_000001.hpd'))
        system = next(s for s in greenville['systems'] if s['name'] == 'Greenville')
        self.assertEqual(system['key'], 1)
        self.assertIn({'name': 'Greenville (City) - Police', 'key': 1}, system['departments'])
        self.assertEqual(list(data['profiles']), ['Home'])
        self.assertEqual(len(data['lists']), 28)
