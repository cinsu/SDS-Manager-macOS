# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Regression checks for the Sentinel-inspired native Audio Option editor.

The tests exercise parsing, serialization, confirmation, cancellation and native
field isolation without requiring Qt or scanner hardware on the build host.
"""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

source = Path(__file__).with_name('favorites_settings_window.py')
tree = ast.parse(source.read_text())
settings = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FavoritesSettingsDialog')
audio_dialog = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'AudioOptionDialog')
needed = {'audio_choices', 'audio_label', 'decode_audio_option', 'CTCSS_TONES', 'DCS_CODES'}
nodes = [n for n in tree.body if
         (isinstance(n, ast.FunctionDef) and n.name in needed) or
         (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in needed for t in n.targets))]
change_method = next(n for n in settings.body if isinstance(n, ast.FunctionDef) and n.name == '_change_audio_option')
selected_method = next(n for n in audio_dialog.body if isinstance(n, ast.FunctionDef) and n.name == 'selected_native_value')

class Message:
    StandardButton = SimpleNamespace(Yes=1, No=2)
    answer = 1
    @classmethod
    def question(cls, *args): return cls.answer

class Dialog:
    DialogCode = SimpleNamespace(Accepted=1)
    accepted = 1
    selected = 'TONE=C67.0'
    def __init__(self, original, parent): self.original = original
    def exec(self): return self.accepted
    def selected_native_value(self): return self.selected

ns = {'QMessageBox': Message, 'QDialog': Dialog, 'AudioOptionDialog': Dialog, 'ROLE': 'record', 're': __import__('re')}
exec(compile(ast.Module(body=nodes+[change_method, selected_method], type_ignores=[]), str(source), 'exec'), ns)

class TestAudioOptions(unittest.TestCase):
    def test_choices(self):
        options = dict(ns['audio_choices']())
        self.assertEqual(options['CTCSS 67.0 Hz'], 'TONE=C67.0')
        self.assertEqual(options['DCS 006'], 'TONE=D006')
        self.assertEqual(options['P25 NAC FFF'], 'NAC=FFF')
        self.assertEqual(options['DMR Color Code 15'], 'ColorCode=15')
        self.assertEqual(options['NXDN RAN 63'], 'RAN=63')
        self.assertEqual(options['NXDN Area 1'], 'Area=1')

    def test_native_parse_and_labels(self):
        cases = [
            ('', ('all', '', False), 'All (no code)'),
            ('TONE=Srch', ('analog', 'TONE=Srch', False), 'Tone Search'),
            ('TONE=C127.3,L/O', ('analog', 'TONE=C127.3', True), 'CTCSS 127.3 Hz (Tone L/O)'),
            ('TONE=D006,L/O', ('analog', 'TONE=D006', True), 'DCS 006 (Tone L/O)'),
            ('NAC=0af', ('digital', 'NAC=AF', False), 'P25 NAC 0AF'),
            ('ColorCode=15', ('digital', 'ColorCode=15', False), 'DMR Color Code 15'),
            ('RAN=Srch', ('digital', 'RAN=Srch', False), 'NXDN RAN/Area Search'),
            ('RAN=63', ('digital', 'RAN=63', False), 'NXDN RAN 63'),
            ('Area=1', ('digital', 'Area=1', False), 'NXDN Area 1'),
            ('NAC=FFFF', ('imported', 'NAC=FFFF', False), 'P25 NAC FFFF'),
            ('TONE=C99.9', ('imported', 'TONE=C99.9', False), 'CTCSS 99.9 Hz'),
        ]
        for original, parsed, label in cases:
            with self.subTest(original=original):
                self.assertEqual(ns['decode_audio_option'](original), parsed)
                self.assertEqual(ns['audio_label'](original), label)

    def test_reject_unsupported_native_codes_without_rewriting(self):
        for value in ('RAN=64', 'Area=2', 'ColorCode=16', 'TONE=D999', 'NAC=1000', 'UNKNOWN'):
            self.assertEqual(ns['decode_audio_option'](value)[0], 'imported')

    def test_select_saves_and_preserves_original_spelling(self):
        def combo(value): return SimpleNamespace(currentData=lambda: value)
        obj = SimpleNamespace(
            _original='NAC=0af',
            audio_type=combo('digital'), search_radio=SimpleNamespace(isChecked=lambda:False),
            nac_radio=SimpleNamespace(isChecked=lambda:True), nac=combo('NAC=AF'),
            color_radio=SimpleNamespace(isChecked=lambda:False), color_code=combo('ColorCode=0'),
            area_radio=SimpleNamespace(isChecked=lambda:False), area=combo('Area=0'),
            ran_radio=SimpleNamespace(isChecked=lambda:False), ran=combo('RAN=0'),
            search_type=combo('NAC=Srch'), tone=combo('TONE=C67.0'),
            tone_lo=SimpleNamespace(isChecked=lambda:True))
        self.assertEqual(ns['selected_native_value'](obj), 'NAC=0af')
        obj.audio_type = combo('analog')
        self.assertEqual(ns['selected_native_value'](obj), 'TONE=C67.0,L/O')
        obj.audio_type = combo('all')
        self.assertEqual(ns['selected_native_value'](obj), '')
        obj.audio_type = combo('imported')
        self.assertEqual(ns['selected_native_value'](obj), 'NAC=0af')

    def change(self, accepted, confirmed):
        Message.answer = confirmed
        Dialog.accepted = accepted
        Dialog.selected = 'TONE=C67.0'
        row = ['C-Freq', '', '', 'Example', '', '', '', ''] + ['unchanged']*10
        before = row.copy()
        state = SimpleNamespace(count=0, refreshes=0)
        item = SimpleNamespace(data=lambda role:(0,0), setText=lambda v:None)
        button = SimpleNamespace(setText=lambda v:None)
        workspace = SimpleNamespace(
            drafts={'x':[{'records':[row]}]},
            _snapshot=lambda:setattr(state,'count',state.count+1),
            refresh_draft=lambda:setattr(state,'refreshes',state.refreshes+1),
            status=SimpleNamespace(setText=lambda v:None))
        obj = SimpleNamespace(_refreshing=False, workspace=workspace, draft_name='x',
            table=SimpleNamespace(rowCount=lambda:1,item=lambda r,c:item))
        ns['_change_audio_option'](obj,0,0,button)
        return row,before,state

    def test_confirm_changes_only_audio_field(self):
        row,before,state=self.change(1,1)
        self.assertEqual(row[7],'TONE=C67.0')
        self.assertEqual(row[:7]+row[8:],before[:7]+before[8:])
        self.assertEqual((state.count,state.refreshes),(1,1))

    def test_cancel_modal_leaves_all_fields(self):
        row,before,state=self.change(0,1)
        self.assertEqual(row,before)
        self.assertEqual((state.count,state.refreshes),(0,0))

    def test_decline_confirmation_leaves_all_fields(self):
        row,before,state=self.change(1,2)
        self.assertEqual(row,before)
        self.assertEqual((state.count,state.refreshes),(0,0))

    def test_dialog_has_families_and_tone_lockout(self):
        source_text = source.read_text()
        self.assertIn("QGroupBox('Analog Options')",source_text)
        self.assertIn("QGroupBox('Digital Options')",source_text)
        self.assertIn("QCheckBox('Tone L/O')",source_text)
        self.assertIn("QRadioButton('Digital Code Search')",source_text)
        self.assertIn("QRadioButton('NXDN Area')",source_text)
        self.assertIn("QRadioButton('NXDN RAN')",source_text)

if __name__=='__main__': unittest.main()
