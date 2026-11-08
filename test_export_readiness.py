# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""v0.0.7l: no scanner required; candidate audit and fail-closed export."""
import tempfile
import unittest
from pathlib import Path
from scanner_export_readiness import (
    assess_hpd_frequency_replacement, audit_native_export_candidates, readiness_summary)


def line(kind='C-Freq', value=b'851012500', width=18, newline=b'\r\n'):
    fields = [b''] * width
    fields[0] = kind.encode('ascii')
    fields[3] = b'Channel'
    fields[4] = b'Off'
    fields[5] = value
    fields[6] = b'Auto' if kind == 'C-Freq' else b'0'
    if width == 9:
        fields[8] = b'opaque extension'
    return b'\t'.join(fields) + newline


class NativeCandidateTests(unittest.TestCase):
    def test_frequency_only_preserves_all_other_bytes(self):
        before = b'TargetModel\tBCDx36HP\r\n' + line() + line('T-Freq', b'851312500', 9, b'\n')
        after = before.replace(b'851012500', b'851012525')
        self.assertEqual(assess_hpd_frequency_replacement(before, after)[0], True)
        self.assertEqual(assess_hpd_frequency_replacement(before, after)[2], 1)

    def test_tfreq_ninth_opaque_field_preserved(self):
        before = line('T-Freq', b'851312500', 9)
        after = before.replace(b'851312500', b'851475000')
        self.assertTrue(assess_hpd_frequency_replacement(before, after)[0])
        after = after.replace(b'opaque extension', b'mutated')
        self.assertFalse(assess_hpd_frequency_replacement(before, after)[0])

    def test_line_ending_change_blocked(self):
        self.assertFalse(assess_hpd_frequency_replacement(line(), line(value=b'851475000', newline=b'\n'))[0])

    def test_add_remove_blocked(self):
        self.assertFalse(assess_hpd_frequency_replacement(line(), line()+line())[0])

    def test_name_change_blocked(self):
        self.assertFalse(assess_hpd_frequency_replacement(line(), line(value=b'851475000').replace(b'Channel', b'Other'))[0])

    def test_invalid_frequency_blocked(self):
        self.assertFalse(assess_hpd_frequency_replacement(line(), line(value=b'abc'))[0])
        self.assertFalse(assess_hpd_frequency_replacement(line(), line(value=b'0'))[0])

    def test_opaque_cfg_change_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            old, new = p/'old.cfg', p/'new.cfg'
            old.write_bytes(b'old'); new.write_bytes(b'new')
            changes = {'ADD':[], 'REPLACE':['app_data.cfg']}
            report, valid = audit_native_export_candidates({'app_data.cfg':new}, {'app_data.cfg':old}, changes)
            self.assertFalse(valid)
            self.assertIn('app_data.cfg: unsupported first-write file type', report)
            summary, allowed = readiness_summary({'app_data.cfg':new}, {'app_data.cfg':old}, changes, True, True)
            self.assertFalse(allowed)
            self.assertIn('Proceed with Export: DISABLED', summary)

    def test_frequency_candidate_even_if_valid_never_authorized(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            old, new = p/'old.hpd', p/'new.hpd'
            old.write_bytes(line()); new.write_bytes(line(value=b'851475000'))
            path = 'favorites_lists/f_000001.hpd'
            changes = {'ADD':[], 'REPLACE':[path]}
            report, valid = audit_native_export_candidates({path:new}, {path:old}, changes)
            self.assertTrue(valid)
            self.assertIn('FORMAT CHECK PASSED', report)
            summary, allowed = readiness_summary({path:new}, {path:old}, changes, True, True)
            self.assertFalse(allowed)
            self.assertIn('Proceed with Export: DISABLED', summary)

    def test_added_file_blocked(self):
        changes = {'ADD':['favorites_lists/f_000002.hpd'], 'REPLACE':[]}
        report, valid = audit_native_export_candidates({}, {}, changes)
        self.assertFalse(valid)
        self.assertIn('new-file/structural serialization not certified', report)

    def test_no_change_blocked(self):
        report, valid = audit_native_export_candidates({}, {}, {'ADD':[], 'REPLACE':[]})
        self.assertFalse(valid)
        self.assertIn('nothing to export', report)


class GuiWiringTests(unittest.TestCase):
    def test_single_export_menu_and_conditional_proceed(self):
        source = (Path(__file__).parent/'database_favorites_manager.py').read_text()
        self.assertIn("menus['File'].addAction('Export to Scanner…', self.export_to_scanner)", source)
        self.assertIn('self.preview_scanner_export(export_flow=True)', source)
        self.assertIn("proceed.setEnabled(bool(eligible))", source)
        self.assertIn("QTimer.singleShot(300", source)
        self.assertIn("tools_advanced.addAction('Diagnostic Export Preview (Read-only)…'", source)


if __name__ == '__main__':
    unittest.main()
