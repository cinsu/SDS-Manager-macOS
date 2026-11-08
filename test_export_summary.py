# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Plain-language export summary, built on the mock scanner from the list-sync tests."""
import unittest

import export_summary
import scanner_configurations as sc
import scanner_first_write as writer
from test_list_sync_export import SyncBase


class SummaryTests(SyncBase):
    def plan(self):
        return writer.prepare_first_write(self.config, self.scanner)

    def test_new_list_is_described_with_counts(self):
        self.create_list('Greenville education', groups=2)
        lines = export_summary.summarize(self.plan())
        text = '\n'.join(lines)
        self.assertIn('NEW list "Greenville education"', text)
        self.assertRegex(text, r'2 departments')
        self.assertRegex(text, r'\d+ channels')

    def test_removed_list_is_named(self):
        names = export_summary._list_names(self.local / export_summary.INDEX_FILE)
        sc.delete_local_favorites_list(self.config, 'BCDx36HP/favorites_lists/f_000002.hpd')
        lines = export_summary.summarize(self.plan())
        self.assertTrue(any(l.startswith('REMOVE list "%s"' % names['f_000002.hpd']) for l in lines), lines)

    def test_setting_change_uses_readable_labels(self):
        index = self.local / export_summary.INDEX_FILE
        raw = index.read_bytes().decode('cp1252').split('\r\n')
        fields = raw[0].split('\t') if raw[0].startswith('F-List') else None
        for i, row in enumerate(raw):
            if row.startswith('F-List'):
                fields = row.split('\t')
                fields[4] = 'Off' if fields[4] == 'On' else 'On'
                raw[i] = '\t'.join(fields)
                break
        index.write_bytes('\r\n'.join(raw).encode('cp1252'))
        self.refresh_manifest()
        lines = export_summary.summarize(self.plan())
        self.assertTrue(any(l.startswith('SETTING ') and 'Monitor' in l for l in lines), lines)

    def test_header_formats_and_truncates(self):
        self.assertEqual(export_summary.header(()), 'No changes.')
        text = export_summary.header(tuple('line %d' % i for i in range(50)), limit=5)
        self.assertEqual(text.count('•'), 5)
        self.assertIn('45 more', text)

    def test_counts_and_plurals(self):
        raw = (b'Conventional\t\t\tSys\r\nC-Group\t\t\tA\r\nC-Freq\t\t\tx\r\nC-Freq\t\t\ty\r\n')
        counts, systems = export_summary.hpd_counts(raw)
        self.assertEqual(systems, ['Sys'])
        self.assertEqual(export_summary._count_text(counts), '1 system, 1 department, 2 channels')


if __name__ == '__main__':
    unittest.main()
