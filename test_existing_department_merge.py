# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Regression: restore a deleted channel into a scanner-imported department."""
import copy
import unittest
from favorites_merge import (
    AmbiguousFavoritesMatch, find_existing_system, merge_draft_entry, merge_records)


class ExistingDepartmentMergeTests(unittest.TestCase):
    def setUp(self):
        self.native_system = ['Conventional', 'native-id', '', 'County Radio', 'local-setting']
        self.database_system = ['Conventional', 'hpdb-id', '', 'County Radio', 'db-setting']
        self.native_department = ['C-Group', 'native-dept', '', 'Fire Dispatch', 'native-settings']
        self.database_department = ['C-Group', 'hpdb-dept', '', '  fire  dispatch ', 'db-settings']
        self.existing_channel = ['C-Freq', '', '', 'Engine 1', 'Off', '154100000', 'Auto']
        self.restored_channel = ['C-Freq', '', '', 'Engine 2', 'Off', '154200000', 'Auto']
        self.entry = {'key': ['native-copy', '/tmp/f_000001.hpd', 0],
                      'origin': 'native-copy', 'scope': 'system', 'kind': 'Conventional',
                      'records': [self.native_system, self.native_department, self.existing_channel]}

    def test_restored_channel_goes_into_existing_scanner_department(self):
        entries = [{'scope': 'metadata', 'records': []}, self.entry]
        selected, matched = find_existing_system(entries, ('/hpdb/state.hpd', 3), self.database_system)
        self.assertIs(selected, self.entry)
        self.assertTrue(matched)
        count = merge_draft_entry(selected, {'records': [self.database_system,
                                  self.database_department, self.restored_channel]})
        self.assertEqual(count, 1)
        self.assertEqual(selected['records'], [self.native_system, self.native_department,
                                               self.existing_channel, self.restored_channel])
        self.assertEqual(selected['origin'], 'native-copy')
        self.assertEqual(selected['key'][0], 'native-copy')

    def test_restoring_same_channel_twice_is_noop(self):
        incoming = [self.database_system, self.database_department, self.restored_channel]
        merged, added = merge_records(self.entry['records'], incoming)
        again, added_again = merge_records(merged, incoming)
        self.assertEqual(added, 1)
        self.assertEqual(added_again, 0)
        self.assertEqual(again, merged)

    def test_same_channel_name_and_frequency_preserves_native_settings(self):
        old = self.restored_channel.copy()
        old[-1] = 'NFM'
        merged, added = merge_records([self.native_system, self.native_department, old],
                                      [self.database_system, self.database_department, self.restored_channel])
        self.assertEqual(added, 0)
        self.assertEqual(merged[-1], old)

    def test_same_name_different_frequency_is_distinct_channel(self):
        another = self.restored_channel.copy()
        another[5] = '155100000'
        merged, added = merge_records([self.native_system, self.native_department, another],
                                      [self.database_system, self.database_department, self.restored_channel])
        self.assertEqual(added, 1)
        self.assertEqual(merged[-1], self.restored_channel)

    def test_unrelated_system_is_not_merged(self):
        other = ['Conventional', '', '', 'Another County']
        entry, matched = find_existing_system([self.entry], ('/hpdb', 1), other)
        self.assertIsNone(entry)
        self.assertFalse(matched)
        with self.assertRaises(ValueError):
            merge_records(self.entry['records'], [other, self.database_department, self.restored_channel])

    def test_duplicate_system_names_fail_closed(self):
        other = copy.deepcopy(self.entry)
        other['key'] = ['native-copy', '/tmp/f_000001.hpd', 1]
        with self.assertRaises(AmbiguousFavoritesMatch):
            find_existing_system([self.entry, other], ('/hpdb', 3), self.database_system)

    def test_duplicate_department_names_fail_closed_without_mutation(self):
        second = ['C-Group', 'different', '', 'Fire Dispatch']
        original = [self.native_system, self.native_department, self.existing_channel, second]
        with self.assertRaises(AmbiguousFavoritesMatch):
            merge_records(original, [self.database_system, self.database_department, self.restored_channel])
        self.assertEqual(original, [self.native_system, self.native_department, self.existing_channel, second])

    def test_no_matching_department_creates_one(self):
        other = ['C-Group', '', '', 'Police']
        merged, count = merge_records([self.native_system, other],
                                      [self.database_system, self.database_department, self.restored_channel])
        self.assertEqual(count, 2)
        self.assertEqual(merged, [self.native_system, other,
                                  self.database_department, self.restored_channel])

    def test_exact_source_key_takes_priority(self):
        self.entry['key'] = ['/hpdb/state.hpd', 3]
        entry, matched = find_existing_system([self.entry], ('/hpdb/state.hpd', 3), self.database_system)
        self.assertIs(entry, self.entry)
        self.assertFalse(matched)


if __name__ == '__main__':
    unittest.main()

class NativeCandidateTests(unittest.TestCase):
    def setUp(self):
        from favorites_merge import native_conventional_candidate
        self.prepare = native_conventional_candidate
        self.sys = ['Conventional', '', '', 'County']
        self.group = ['C-Group', '', '', 'Fire']
        self.native = ['C-Freq', '', '', 'Dispatch', 'Off', '154100000', 'FM', 'Srch'] + ['Off'] * 10
        self.db_sys = ['Conventional', 'CountyId=42', 'StateId=5', 'County']
        self.db_group = ['C-Group', 'CGroupId=99', 'CountyId=42', 'Fire']
        self.db_channel = ['C-Freq', 'CFreqId=123', 'CGroupId=99', 'Tactical', 'Off', '154200000', 'FM', '', '8'] + [''] * 9
        self.entry = {'origin': 'native-copy', 'records': [self.sys, self.group, self.native]}

    def test_native_channel_uses_existing_template_and_no_new_department(self):
        proposed = self.prepare(self.entry, [self.db_sys, self.db_group, self.db_channel])
        self.assertEqual(proposed[1], self.group)
        self.assertEqual(proposed[2][1], 'CFreqId=0')
        self.assertEqual(proposed[2][2], self.native[2])
        self.assertEqual(proposed[2][3], 'Tactical')
        self.assertEqual(proposed[2][5], '154200000')
        # Audio option comes from the database row (blank = no tone), not the template channel;
        # everything from column 9 on follows the template.
        self.assertEqual(proposed[2][6], self.native[6])
        self.assertEqual(proposed[2][7], '')
        self.assertEqual(proposed[2][9:], self.native[9:])
        merged, added = merge_records(self.entry['records'], proposed)
        self.assertEqual(added, 1)
        self.assertEqual(sum(r[0] == 'C-Group' for r in merged), 1)

    def test_database_identity_is_carried_and_assignments_are_not_inherited(self):
        template = ['C-Freq', '', '', 'Dispatch', 'On', '154100000', 'FM', 'TONE=C127.3', '8', 'Off', '2', '0',
                    'Off', 'Auto', 'Off', 'On', '42', 'On']
        entry = {'origin': 'native-copy', 'records': [self.sys, self.group, template]}
        db = list(self.db_channel)
        db[6:9] = ['NFM', 'ColorCode=1', '3']
        leaf = self.prepare(entry, [self.db_sys, self.db_group, db])[2]
        self.assertEqual(leaf[6:9], ['NFM', 'ColorCode=1', '3'])
        self.assertEqual([leaf[4], leaf[16], leaf[17]], ['Off', 'Off', 'Off'])  # avoid, number tag, priority
        self.assertEqual(leaf[9:16], template[9:16])

    def test_invalid_database_values_are_blank_never_the_templates(self):
        template = ['C-Freq', '', '', 'Dispatch', 'Off', '154100000', 'FM', 'TONE=C127.3', '8'] + ['Off'] * 9
        entry = {'origin': 'native-copy', 'records': [self.sys, self.group, template]}
        db = list(self.db_channel)
        db[6:9] = ['???', 'garbage', '3']
        leaf = self.prepare(entry, [self.db_sys, self.db_group, db])[2]
        self.assertEqual(leaf[6:9], ['AUTO', '', '3'])   # blank tone; AUTO because modulation cannot be blank

    def test_channel_without_service_type_is_refused(self):
        entry = {'origin': 'native-copy', 'records': [self.sys, self.group, self.native]}
        db = list(self.db_channel)
        db[8] = ''
        with self.assertRaisesRegex(ValueError, 'no valid service type'):
            self.prepare(entry, [self.db_sys, self.db_group, db])

    def test_missing_native_template_blocks(self):
        with self.assertRaisesRegex(ValueError, 'no native channel template'):
            self.prepare({'origin': 'native-copy', 'records': [self.sys, self.group]},
                         [self.db_sys, self.db_group, self.db_channel])

    def test_new_department_blocked_for_native_export(self):
        new_group = ['C-Group', '', '', 'New Department']
        with self.assertRaisesRegex(ValueError, 'does not exist'):
            self.prepare(self.entry, [self.db_sys, new_group, self.db_channel])

    def test_duplicate_frequency_with_different_name_blocked(self):
        existing = self.db_channel.copy()
        existing[5] = self.native[5]
        with self.assertRaisesRegex(ValueError, 'already uses that frequency'):
            self.prepare(self.entry, [self.db_sys, self.db_group, existing])

    def test_real_native_hpd_merge_passes_export_validator(self):
        from pathlib import Path
        from favorites_merge import native_conventional_candidate
        from scanner_favorites_expanded import assess_expanded_hpd_replacement
        native_path = Path('/mnt/data/f_000003.hpd')
        if not native_path.is_file():
            self.skipTest('Optional native scanner fixture absent')
        raw = native_path.read_bytes()
        rows = [line.split('\t') for line in raw.decode('cp1252').splitlines()]
        sys_start = next(i for i, r in enumerate(rows) if r[0] == 'Conventional')
        group_index = next(i for i in range(sys_start+1, len(rows)) if rows[i][0] == 'C-Group'
                           and any(r[0] == 'C-Freq' for r in rows[i+1:i+8]))
        end = next((i for i in range(group_index+1, len(rows)) if rows[i][0] in ('C-Group','Trunk','Conventional')),len(rows))
        system_header, group_header = rows[sys_start], rows[group_index]
        existing = {'origin':'native-copy','records': [system_header] + rows[group_index:end]}
        incoming_header = system_header.copy(); incoming_header[1] = 'CountyId=123'
        incoming_group = group_header.copy(); incoming_group[1] = 'CGroupId=456'
        incoming_channel = next(r.copy() for r in rows[group_index+1:end] if r[0] == 'C-Freq')
        incoming_channel[1] = 'CFreqId=1234'; incoming_channel[2] = 'CGroupId=456'
        incoming_channel[3] = 'RESTORED TEST CHANNEL'
        used = {r[5] for r in rows[group_index+1:end] if r[0] == 'C-Freq'}
        incoming_channel[5] = next(str(n) for n in range(155000000, 156000000, 12500) if str(n) not in used)
        candidate = native_conventional_candidate(existing, [incoming_header, incoming_group, incoming_channel])
        merged, added = merge_records(existing['records'], candidate)
        self.assertEqual(added, 1)
        self.assertEqual(sum(r[0] == 'C-Group' for r in merged), 1)
        proposed = rows[:group_index] + merged[1:] + rows[end:]
        newline = '\r\n' if b'\r\n' in raw else '\n'
        payload = (newline.join('\t'.join(r) for r in proposed) + newline).encode('cp1252')
        passed, reason, counts = assess_expanded_hpd_replacement(raw, payload)
        self.assertTrue(passed, reason)
        self.assertEqual(counts['added'], 1)

class NativeSaveIntegrationTests(unittest.TestCase):
    def test_database_restore_serializes_one_leaf_without_new_department(self):
        import hashlib
        import tempfile
        from pathlib import Path
        from native_favorites_export import build_native_bytes
        from favorites_merge import native_conventional_candidate
        from scanner_favorites_expanded import assess_expanded_hpd_replacement

        original = (b'TargetModel\tBCDx36HP\r\nFormatVersion\t1.00\r\n'
                    b'Conventional\t\t\tCounty\r\nC-Group\t\t\tFire\r\n'
                    + ('\t'.join(['C-Freq','','','Dispatch','Off','154100000','FM','Srch'] + ['Off'] * 10)
                       + '\r\n').encode('ascii'))
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'f_000001.hpd'
            source.write_bytes(original)
            rows = [line.split('\t') for line in original.decode('cp1252').splitlines()]
            existing = {'key':['native-copy',str(source),0], 'origin':'native-copy',
                        'kind':'Conventional','name':'County','records':rows[2:]}
            database = [['Conventional','CountyId=7','StateId=1','County'],
                        ['C-Group','CGroupId=3','CountyId=7','Fire'],
                        ['C-Freq','CFreqId=999','CGroupId=3','Tactical','Off','154200000','FM','','8']]
            candidate = native_conventional_candidate(existing, database)
            added = merge_draft_entry(existing, {'records':candidate})
            self.assertEqual(added,1)
            entries = [{'key':['native-copy-meta',str(source)], 'scope':'metadata',
                        'source_path':str(source),'source_sha256':hashlib.sha256(original).hexdigest(),
                        'encoding':'cp1252','newline':'\r\n','final_newline':True,
                        'records':rows[:2]},existing]
            payload, _ = build_native_bytes(entries)
            passed, reason, counts = assess_expanded_hpd_replacement(original,payload)
            self.assertTrue(passed,reason)
            self.assertEqual(counts['added'],1)
            self.assertEqual(payload.count(b'C-Group\t'),1)
            self.assertIn(b'CFreqId=0',payload)
            self.assertEqual(source.read_bytes(),original)
