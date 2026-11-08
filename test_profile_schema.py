# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Core profile.cfg records (GlobalSetting, SearchCommon, CloseCall, Weather, WxSameList).

real_sds100_profile.cfg is a profile.cfg captured from a real SDS100.
"""
import unittest
from pathlib import Path

import profile_schema as ps
from scanner_global_settings import patch_global_setting, EDITABLE_GLOBAL_CHOICES
from scanner_profile_export import assess_profile_replacement

REAL = (Path(__file__).resolve().parent / 'test_fixtures' / 'real_sds100_profile.cfg').read_bytes()


class SchemaTests(unittest.TestCase):
    def test_every_value_of_a_real_profile_is_valid(self):
        for kind, spec in ps.SCHEMA.items():
            for row in ps.check_layout(REAL, kind):
                for position, (field, value) in enumerate(zip(ps.fields_of(kind, row), row), 1):
                    if field.editable:
                        self.assertTrue(field.valid(value), (kind, position, value))

    def test_patch_is_lossless_and_reversible(self):
        edits = {('GlobalSetting', 0, 14): '9', ('SearchCommon', 0, 4): '5', ('CloseCall', 0, 7): 'Red',
                 ('Weather', 0, 2): '-5', ('WxSameList', 1, 2): 'COUNTY'}
        edited = ps.patch_fields(REAL, edits)
        self.assertNotEqual(edited, REAL)
        self.assertEqual(len(edited.splitlines()), len(REAL.splitlines()))
        self.assertEqual(ps.diff_sections(REAL, edited), edits)
        back = ps.patch_fields(edited, {k: ps.read_section(REAL, k[0])[k[1]][k[2] - 1] for k in edits})
        self.assertEqual(back, REAL)

    def test_invalid_edits_are_refused(self):
        bad = [(('GlobalSetting', 0, 14), '16'), (('GlobalSetting', 0, 14), '07'), (('GlobalSetting', 0, 14), 'x'),
               (('GlobalSetting', 0, 7), '0'), (('GlobalSetting', 0, 8), '101'), (('GlobalSetting', 0, 9), 'Custom10'),
               (('GlobalSetting', 0, 13), '16'), (('GlobalSetting', 0, 20), '7'), (('GlobalSetting', 0, 19), 'Global'),
               (('GlobalSetting', 0, 3), 'On'),                       # reserved
               (('SearchCommon', 0, 1), 'x'), (('SearchCommon', 0, 10), '14'), (('SearchCommon', 0, 8), '1001'),
               (('CloseCall', 0, 4), '20'), (('CloseCall', 0, 18), '256'), (('CloseCall', 0, 16), 'On'),
               (('Weather', 0, 2), '7'), (('WxSameList', 0, 1), 'SameId=9'),
               (('WxSameList', 0, 2), 'A' * 17), (('WxSameList', 0, 2), 'a\tb'), (('WxSameList', 0, 3), '12345'),
               (('WxSameList', 0, 3), 'abcdef'), (('WxSameList', 7, 2), 'X'), (('Nope', 0, 1), 'X'),
               (('GlobalSetting', 0, 99), 'On'), (('GlobalSetting', 0, 14), 9)]
        for key, value in bad:
            with self.assertRaises(ValueError, msg=(key, value)):
                ps.patch_fields(REAL, {key: value})
        with self.assertRaises(ValueError):
            ps.patch_fields(REAL, {})

    def test_wrong_layout_is_refused(self):
        short = REAL.replace(b'GlobalSetting\tOff', b'GlobalSetting\tOff', 1)
        lines = short.split(b'\r\n') if b'\r\n' in short else short.split(b'\n')
        sep = b'\r\n' if b'\r\n' in short else b'\n'
        lines = [l[:l.rindex(b'\t')] if l.startswith(b'GlobalSetting') else l for l in lines]
        with self.assertRaises(ValueError):
            ps.patch_fields(sep.join(lines), {('GlobalSetting', 0, 1): 'On'})

    def test_untouched_odd_records_never_block_other_changes(self):
        odd = REAL.replace(b'Weather\t', b'Weather\tZ\t', 1)
        self.assertEqual(ps.diff_sections(odd, odd), {})

    def test_choices_for_the_editor(self):
        self.assertEqual(EDITABLE_GLOBAL_CHOICES[14][0], '0')
        self.assertEqual(EDITABLE_GLOBAL_CHOICES[14][-1], '15')
        self.assertIn('Waterfall', EDITABLE_GLOBAL_CHOICES[9])
        self.assertNotIn(3, EDITABLE_GLOBAL_CHOICES)
        self.assertEqual(patch_global_setting(REAL, {14: '6'}), REAL)


class ExportGuardTests(unittest.TestCase):
    def test_valid_settings_edits_are_authorised(self):
        edited = ps.patch_fields(REAL, {('GlobalSetting', 0, 14): '9', ('CloseCall', 0, 5): '7',
                                        ('SearchCommon', 0, 6): 'On', ('WxSameList', 0, 2): 'HOME'})
        ok, detail, counts = assess_profile_replacement(REAL, edited)
        self.assertTrue(ok, detail)
        for kind in ('GlobalSetting', 'CloseCall', 'SearchCommon', 'WxSameList'):
            self.assertIn(kind, detail)

    def test_invalid_or_hand_edited_bytes_are_refused(self):
        cases = {
            'out of range': REAL.replace(b'Normal\t0\tIn Phase', b'Normal\t7\tIn Phase'),
            'reserved': REAL.replace(b'Off\tOff\t\tOff\tOff\tOff\t2', b'Off\tOff\tOn\tOff\tOff\tOff\t2', 1),
            'line ending': REAL.replace(b'ClockOption', b'ClockOption', 1).replace(b'\r\n', b'\n', 1)
            if b'\r\n' in REAL else REAL + b'\r',
            'extra record': REAL + b'Backlight\tX\n',
            'unmapped section': REAL.replace(b'IfxFreqs\t\t', b'IfxFreqs\t100\t', 1),
        }
        for name, proposed in cases.items():
            self.assertNotEqual(proposed, REAL, name)
            ok, detail, _ = assess_profile_replacement(REAL, proposed)
            self.assertFalse(ok, name)

    def test_combined_with_existing_editors(self):
        from quick_keys_settings import read_quick_keys, patch_quick_keys
        keys = list(read_quick_keys(REAL))
        keys[0] = not keys[0]
        edited = ps.patch_fields(patch_quick_keys(REAL, keys), {('GlobalSetting', 0, 15): '3'})
        ok, detail, _ = assess_profile_replacement(REAL, edited)
        self.assertTrue(ok, detail)
        self.assertIn('quick keys', detail)


if __name__ == '__main__':
    unittest.main()


from test_list_sync_export import SyncBase   # noqa: E402
import scanner_first_write as writer          # noqa: E402


class ProfileExportTests(SyncBase):
    def setUp(self):
        super().setUp()
        for root in (self.scanner, self.local):
            (root / 'profile.cfg').write_bytes(REAL)
        self.refresh_manifest()

    def test_settings_edit_is_exported_with_backup(self):
        edited = ps.patch_fields(REAL, {('GlobalSetting', 0, 14): '9', ('CloseCall', 0, 5): '7'})
        (self.local / 'profile.cfg').write_bytes(edited)
        self.refresh_manifest()
        before = self.scanner_state()
        ok, reason = writer.first_write_eligibility(self.config, self.scanner)
        self.assertTrue(ok, reason)
        result = writer.execute_first_write(self.config, self.scanner)
        after = self.scanner_state()
        self.assertEqual(after['profile.cfg'], edited)
        self.assertEqual((Path(result['backup']) / 'BCDx36HP/profile.cfg').read_bytes(), REAL)
        for name in before:
            if name != 'profile.cfg':
                self.assertEqual(after[name], before[name], name)

    def test_invalid_settings_edit_is_blocked(self):
        (self.local / 'profile.cfg').write_bytes(REAL.replace(b'Normal\t0\tIn Phase', b'Normal\t7\tIn Phase'))
        self.refresh_manifest()
        ok, reason = writer.first_write_eligibility(self.config, self.scanner)
        self.assertFalse(ok)
        self.assertEqual(self.scanner_state()['profile.cfg'], REAL)


class DisplayHardwareTests(unittest.TestCase):
    def test_real_layouts_are_accepted(self):
        for kind in ('DisplayOption', 'Backlight', 'Battery', 'OwnerInfo', 'ClockOption',
                     'RecordingOption', 'StandbyOption'):
            self.assertEqual(len(ps.check_layout(REAL, kind)), 1, kind)

    def test_edits_round_trip(self):
        edits = {('DisplayOption', 0, 6): 'HEX', ('DisplayOption', 0, 11): 'On', ('DisplayOption', 0, 13): 'BLACK',
                 ('Backlight', 0, 6): '80', ('Backlight', 0, 10): 'OpenSquelch', ('Backlight', 0, 11): 'Infinite',
                 ('Battery', 0, 1): 'Off', ('Battery', 0, 4): '30', ('Battery', 0, 5): '1200', ('Battery', 0, 6): '7',
                 ('OwnerInfo', 0, 1): 'John Smith', ('OwnerInfo', 0, 3): '', ('OwnerInfo', 0, 4): '  centred  ',
                 ('ClockOption', 0, 2): '-4.5', ('ClockOption', 0, 3): 'Off',
                 ('RecordingOption', 0, 1): '120', ('RecordingOption', 0, 2): 'On'}
        edited = ps.patch_fields(REAL, edits)
        self.assertEqual(ps.diff_sections(REAL, edited), {k: v for k, v in edits.items()
                                                          if ps.read_section(REAL, k[0])[0][k[2] - 1] != v})
        ok, detail, _ = assess_profile_replacement(REAL, edited)
        self.assertTrue(ok, detail)
        back = ps.patch_fields(edited, {k: ps.read_section(REAL, k[0])[k[1]][k[2] - 1] for k in edits})
        self.assertEqual(back, REAL)

    def test_invalid_edits_refused(self):
        bad = [(('DisplayOption', 0, 6), 'dec'), (('DisplayOption', 0, 1), 'x'), (('DisplayOption', 0, 10), 'x'),
               (('Backlight', 0, 6), '45'), (('Backlight', 0, 6), '0'), (('Backlight', 0, 2), 'Low'),
               (('Backlight', 0, 10), '20'), (('Backlight', 0, 11), '45'), (('Backlight', 0, 12), 'On'),
               (('Battery', 0, 4), '0'), (('Battery', 0, 4), '61'), (('Battery', 0, 5), '700'),
               (('Battery', 0, 2), 'x'), (('OwnerInfo', 0, 1), 'x' * 25), (('OwnerInfo', 0, 1), 'tab\there'),
               (('OwnerInfo', 0, 1), 'café'), (('OwnerInfo', 0, 2), ' '),
               (('ClockOption', 0, 1), '12H'), (('ClockOption', 0, 2), '-5'), (('ClockOption', 0, 2), '14.5'),
               (('ClockOption', 0, 2), '-14.5'), (('ClockOption', 0, 2), '1.2'),
               (('RecordingOption', 0, 1), '45'), (('RecordingOption', 0, 1), '270'),
               (('StandbyOption', 0, 1), 'Clock Standby'), (('StandbyOption', 0, 2), 'All On')]
        for key, value in bad:
            with self.assertRaises(ValueError, msg=(key, value)):
                ps.patch_fields(REAL, {key: value})

    def test_other_firmware_layout_blocks_only_that_record(self):
        sds200 = REAL.replace(b'Backlight\t', b'Backlight\tX\t', 1)
        edited = ps.patch_fields(sds200, {('GlobalSetting', 0, 14): '9'})
        ok, detail, _ = assess_profile_replacement(sds200, edited)
        self.assertTrue(ok, detail)
        with self.assertRaises(ValueError):
            ps.patch_fields(sds200, {('Backlight', 0, 6): '80'})


class DisplayHardwareExportTests(SyncBase):
    def test_display_and_hardware_edits_are_exported(self):
        for root in (self.scanner, self.local):
            (root / 'profile.cfg').write_bytes(REAL)
        edited = ps.patch_fields(REAL, {('Backlight', 0, 6): '80', ('OwnerInfo', 0, 1): 'John Smith',
                                        ('ClockOption', 0, 2): '-4.0', ('DisplayOption', 0, 13): 'BLACK'})
        (self.local / 'profile.cfg').write_bytes(edited)
        self.refresh_manifest()
        ok, reason = writer.first_write_eligibility(self.config, self.scanner)
        self.assertTrue(ok, reason)
        result = writer.execute_first_write(self.config, self.scanner)
        self.assertEqual(self.scanner_state()['profile.cfg'], edited)
        self.assertEqual((Path(result['backup']) / 'BCDx36HP/profile.cfg').read_bytes(), REAL)


class SearchToolsTests(unittest.TestCase):
    def test_real_layouts_are_accepted(self):
        counts = {'LimitSearch': 10, 'ToneOut': 32, 'Waterfall': 1, 'CustomWfBand': 10, 'WfColors': 1,
                  'BandDefault': 31, 'PresetBroadcastScreen': 1, 'CustomBroadcastScreen': 1}
        for kind, rows in counts.items():
            self.assertEqual(len(ps.check_layout(REAL, kind)), rows, kind)

    def test_edits_round_trip_and_export(self):
        edits = {('LimitSearch', 2, 2): 'Marine', ('LimitSearch', 2, 3): '156000000', ('LimitSearch', 2, 4): '162000000',
                 ('LimitSearch', 2, 5): 'NFM', ('LimitSearch', 2, 6): '12500', ('LimitSearch', 2, 15): '5',
                 ('ToneOut', 4, 2): 'Station 5', ('ToneOut', 4, 4): '154280000', ('ToneOut', 4, 6): '3300',
                 ('ToneOut', 4, 7): '0', ('ToneOut', 4, 9): 'Infinite', ('ToneOut', 4, 13): 'Red',
                 ('Waterfall', 0, 3): '156800000', ('Waterfall', 0, 7): '2.88', ('Waterfall', 0, 13): 'Bar',
                 ('Waterfall', 0, 18): '7', ('CustomWfBand', 1, 2): 'Airband', ('CustomWfBand', 1, 3): '121500000',
                 ('WfColors', 0, 2): 'ff00ff', ('BandDefault', 4, 2): 'FM', ('BandDefault', 4, 3): '25000',
                 ('PresetBroadcastScreen', 0, 2): 'On', ('CustomBroadcastScreen', 0, 1): 'On',
                 ('CustomBroadcastScreen', 0, 2): '118', ('CustomBroadcastScreen', 0, 3): '1300'}
        edited = ps.patch_fields(REAL, edits)
        self.assertEqual(set(ps.diff_sections(REAL, edited)), {k for k in edits
                         if ps.read_section(REAL, k[0])[k[1]][k[2] - 1] != edits[k]})
        ok, detail, _ = assess_profile_replacement(REAL, edited)
        self.assertTrue(ok, detail)
        back = ps.patch_fields(edited, {k: ps.read_section(REAL, k[0])[k[1]][k[2] - 1] for k in edits})
        self.assertEqual(back, REAL)

    def test_invalid_edits_refused(self):
        bad = [(('LimitSearch', 0, 1), 'SrchId=99'), (('LimitSearch', 0, 3), '24999999'), (('LimitSearch', 0, 3), '1300000001'),
               (('LimitSearch', 0, 3), '025000000'), (('LimitSearch', 0, 3), '25.0'), (('LimitSearch', 0, 2), ''),
               (('LimitSearch', 0, 2), 'N' * 17), (('LimitSearch', 0, 6), '4000'), (('LimitSearch', 0, 11), 'x'),
               (('LimitSearch', 0, 15), '256'), (('LimitSearch', 10, 2), 'x'),
               (('ToneOut', 0, 6), '2499'), (('ToneOut', 0, 6), '35001'), (('ToneOut', 0, 5), 'AM'),
               (('ToneOut', 0, 9), '-5'), (('ToneOut', 0, 12), '0'), (('ToneOut', 0, 13), 'Orange'),
               (('Waterfall', 0, 7), '3'), (('Waterfall', 0, 6), '7500'), (('Waterfall', 0, 14), '60'),
               (('Waterfall', 0, 16), '5'), (('Waterfall', 0, 18), '16'), (('Waterfall', 0, 2), 'N' * 17),
               (('CustomWfBand', 0, 8), 'x'), (('CustomWfBand', 0, 7), '1'),
               (('WfColors', 0, 1), 'FF0000'), (('WfColors', 0, 1), 'ff00'), (('WfColors', 0, 1), 'gg0000'),
               (('BandDefault', 0, 2), 'AUTO'), (('BandDefault', 0, 3), 'Auto'), (('BandDefault', 31, 2), 'AM'),
               (('PresetBroadcastScreen', 0, 1), 'Yes'),
               (('CustomBroadcastScreen', 0, 2), '1301'), (('CustomBroadcastScreen', 0, 2), '18'),
               (('CustomBroadcastScreen', 0, 2), '0118'), (('CustomBroadcastScreen', 0, 2), 'abc')]
        for key, value in bad:
            with self.assertRaises(ValueError, msg=(key, value)):
                ps.patch_fields(REAL, {key: value})

    def test_limit_search_lower_must_not_exceed_upper(self):
        with self.assertRaises(ValueError):
            ps.patch_fields(REAL, {('LimitSearch', 0, 3): '30000000'})          # upper is 27999900
        ps.patch_fields(REAL, {('LimitSearch', 0, 3): '27000000'})
        ps.patch_fields(REAL, {('LimitSearch', 0, 3): '30000000', ('LimitSearch', 0, 4): '31000000'})

    def test_ifx_and_unmapped_sections_stay_locked(self):
        for needle in (b'IfxFreqs\t',):
            self.assertIn(needle, REAL)
        bad = REAL.replace(b'IfxFreqs\t\t', b'IfxFreqs\t100\t', 1)
        self.assertNotEqual(bad, REAL)
        self.assertFalse(assess_profile_replacement(REAL, bad)[0])


class DisplayLayoutTests(unittest.TestCase):
    def test_every_real_layout_row_is_recognised(self):
        self.assertEqual(len(ps.check_layout(REAL, 'DispOptItems')), 25)
        self.assertEqual(len(ps.check_layout(REAL, 'DispColors')), 46)

    def test_item_and_colour_edits_round_trip_and_export(self):
        edits = {('DispOptItems', 0, 5): 'SiteName', ('DispOptItems', 3, 3): 'IFX',
                 ('DispColors', 0, 3): '00ff00', ('DispColors', 1, 4): '123abc'}
        edits[('DispOptItems', 3, 3)] = 'SCR'        # layout 1 row 4: Modulation -> SCR (not already in the row)
        edited = ps.patch_fields(REAL, edits)
        self.assertEqual(ps.diff_sections(REAL, edited), edits)
        self.assertEqual(len(edited.splitlines()), len(REAL.splitlines()))
        self.assertTrue(assess_profile_replacement(REAL, edited)[0])

    def test_unknown_items_bad_colours_duplicates_and_shape_changes_are_refused(self):
        for bad in ({('DispOptItems', 0, 3): 'NotAnItem'},       # name not seen for that row
                    {('DispOptItems', 0, 3): 'ServiceType'},     # belongs to a different screen row
                    {('DispOptItems', 3, 4): 'Modulation'},      # already shown in that row
                    {('DispColors', 0, 3): 'FF4600'},            # upper case
                    {('DispColors', 0, 1): 'DispColorId=2'},     # identifier
                    {('DispColors', 0, 99): '000000'}):
            with self.assertRaises(ValueError, msg=bad):
                ps.patch_fields(REAL, bad)
        longer = REAL.replace(b'DispColorId=2\tColorLayoutId=1\tff4600', b'DispColorId=2\tColorLayoutId=1\tff4600\t000000\tff4600', 1)
        self.assertNotEqual(longer, REAL)
        self.assertFalse(assess_profile_replacement(REAL, longer)[0])

    def test_unknown_layout_is_not_edited_but_does_not_block_other_changes(self):
        odd = REAL.replace(b'DispOptId=1\tDispLayoutId=1\t', b'DispOptId=9\tDispLayoutId=1\t', 1)
        with self.assertRaises(ValueError):
            ps.check_layout(odd, 'DispOptItems')
        edited = ps.patch_fields(odd, {('Weather', 0, 2): '-5'})
        self.assertTrue(assess_profile_replacement(odd, edited)[0])
