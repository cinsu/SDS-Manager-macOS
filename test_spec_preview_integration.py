# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Read-only preview integration regression for spec field audit (no scanner required)."""
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import scanner_export_preview as preview

def sample(kind, width, col6, col7, col5='Off'):
    fields = [''] * width
    fields[0] = kind
    fields[3] = 'Sample'
    fields[4] = col5
    fields[5] = col6
    fields[6] = col7
    return ('\t'.join(fields) + '\r\n').encode('ascii')

class SpecPreviewIntegrationTests(unittest.TestCase):
    def test_full_preview_includes_spec_audit_and_no_write(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            cfg = base/'config'
            local = cfg/'BCDx36HP'/'favorites_lists'
            scanner = base/'scanner'/'BCDx36HP'
            local.mkdir(parents=True)
            (scanner/'favorites_lists').mkdir(parents=True)
            body = (sample('C-Freq',18,'851012500','Auto') +
                    sample('T-Freq',8,'851312500','0') +
                    sample('T-Freq',9,'852250000','1') +
                    sample('TGID',17,'1234','All'))
            src = local/'f_000001.hpd'
            target = scanner/'favorites_lists'/'f_000001.hpd'
            src.write_bytes(body)
            target.write_bytes(body)
            patches = {
                'list_configurations': lambda: [(cfg, {'name':'unchanged'})],
                'inspect_scanner': lambda path: ('Synthetic test only', True),
                '_backup_status': lambda *args: ('Synthetic backup status', True),
            }
            old_audits = (
                'audit_export_safety', 'inspect_native_files', 'inspect_roundtrip',
                'inspect_edit_probe', 'inspect_multifield_probe', 'inspect_native_values',
                'inspect_numeric_representations', 'inspect_frequency_spec',
                'inspect_record_layout', 'audit_field_structure',
                'audit_lossless_field_edits', 'audit_variable_length_edits',
            )
            for name in old_audits:
                patches[name] = lambda *args: 'PREVIOUS AUDIT TEST PLACEHOLDER'
            with ExitStack() as stack:
                for name, replacement in patches.items():
                    stack.enter_context(patch.object(preview,name,replacement))
                report, changes, backup_ok = preview.preview_export(cfg,scanner)
            self.assertIn('NATIVE FAVORITES SPEC FIELD MAPPING AUDIT — READ ONLY',report)
            self.assertIn('LOCAL STAGING AND ROLLBACK REHEARSAL — READ ONLY', report)
            self.assertIn('DURABLE WRITE/RESTART RECOVERY REHEARSAL — LOCAL MOCK ONLY', report)
            self.assertIn('Scanner writes: 0', report)
            self.assertIn('Extra undocumented T-Freq columns: 1 records',report)
            self.assertIn('Export action: DISABLED',report)
            self.assertIn('This DIAGNOSTIC is read-only and cannot authorize writing',report)
            self.assertIn('134', '134')  # previous synthetic probes covered separately
            self.assertEqual(changes['UNCHANGED'], ['favorites_lists/f_000001.hpd'])
            self.assertTrue(backup_ok)
            self.assertEqual(src.read_bytes(),body)
            self.assertEqual(target.read_bytes(),body)

if __name__ == '__main__':
    unittest.main()
