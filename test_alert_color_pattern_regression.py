# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Headless regression checks for SDS native C-Freq alert color and pattern."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

SRC = Path(__file__).with_name('favorites_settings_window.py')
TREE = ast.parse(SRC.read_text())
DIALOG = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'FavoritesSettingsDialog')

def top(name):
    return next(n for n in TREE.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets))
def method(name):
    return next(n for n in DIALOG.body if isinstance(n, ast.FunctionDef) and n.name == name)

class Message:
    StandardButton = SimpleNamespace(Yes=1, No=2)
    answer = 1
    calls = 0
    @classmethod
    def question(cls, *args):
        cls.calls += 1
        return cls.answer

scope = {'QMessageBox': Message, 'ROLE': 'record'}
exec(compile(ast.Module(body=[top('ALERT_COLOR_CHOICES'), top('ALERT_PATTERN_CHOICES'),
                              method('_change_alert_color'), method('_change_alert_pattern')],
                        type_ignores=[]), str(SRC), 'exec'), scope)

class Combo:
    def __init__(self, value): self.value = value
    def setCurrentText(self, value): self.value = value
class Item:
    def __init__(self): self.value = None
    def data(self, role): return (0, 0)
    def setText(self, value): self.value = value
class Dialog:
    _change_alert_color = scope['_change_alert_color']
    _change_alert_pattern = scope['_change_alert_pattern']
    def __init__(self, field, original):
        self.native = ['C-Freq', '', '', 'Sample'] + ['X'] * 14
        self.native[field] = original
        self.item = Item()
        self.snapshots = 0
        self.refreshes = 0
        self.workspace = SimpleNamespace(
            drafts={'draft': [{'records': [self.native]}]},
            _snapshot=self.snap,
            refresh_draft=self.refresh,
            status=SimpleNamespace(setText=lambda message: None))
        self.draft_name = 'draft'
        self._refreshing = False
        expected_column = field - 2
        self.table = SimpleNamespace(rowCount=lambda: 1,
                                     item=lambda row, col: self.item if col == expected_column else None)
    def snap(self): self.snapshots += 1
    def refresh(self): self.refreshes += 1

class TestAlerts(unittest.TestCase):
    def setUp(self): Message.answer = 1; Message.calls = 0
    def test_color_choices(self):
        self.assertEqual(scope['ALERT_COLOR_CHOICES'], ('Off','Blue','Red','Magenta','Green','Cyan','Yellow','White'))
    def test_pattern_choices(self):
        self.assertEqual(scope['ALERT_PATTERN_CHOICES'], ('On','Slow Blink','Fast Blink'))
    def test_columns(self):
        columns = ast.literal_eval(top('COLUMNS').value)
        self.assertEqual(columns[10:14], ['Alert Tone','Alert Volume','Alert Color','Alert Pattern'])
        self.assertEqual(columns[14:17], ['Volume Offset','Number Tag','Priority'])
    def run_change(self, field, method_name, original, target, answer=1):
        Message.answer = answer
        dialog = Dialog(field, original)
        combo = Combo(target)
        before = dialog.native.copy()
        getattr(dialog, method_name)(0, 0, combo, target)
        return dialog, combo, before
    def test_color_success_preserves_other_fields(self):
        d,c,b = self.run_change(14, '_change_alert_color','Off','Magenta')
        self.assertEqual(d.native[14], 'Magenta')
        self.assertEqual(d.native[:14], b[:14]); self.assertEqual(d.native[15:], b[15:])
        self.assertEqual((d.snapshots,d.refreshes,d.item.value), (1,1,'Magenta'))
    def test_pattern_success_preserves_other_fields(self):
        d,c,b = self.run_change(15,'_change_alert_pattern','On','Slow Blink')
        self.assertEqual(d.native[15], 'Slow Blink')
        self.assertEqual(d.native[:15], b[:15]); self.assertEqual(d.native[16:], b[16:])
        self.assertEqual((d.snapshots,d.refreshes,d.item.value), (1,1,'Slow Blink'))
    def test_color_cancel(self):
        d,c,b = self.run_change(14,'_change_alert_color','Blue','Green',2)
        self.assertEqual(d.native,b); self.assertEqual(c.value,'Blue'); self.assertEqual(d.snapshots,0)
    def test_pattern_cancel(self):
        d,c,b = self.run_change(15,'_change_alert_pattern','On','Fast Blink',2)
        self.assertEqual(d.native,b); self.assertEqual(c.value,'On'); self.assertEqual(d.snapshots,0)
    def test_invalid_color(self):
        d,c,b = self.run_change(14,'_change_alert_color','Off','Orange')
        self.assertEqual(d.native,b); self.assertEqual(c.value,'Off'); self.assertEqual(Message.calls,0)
    def test_invalid_pattern(self):
        d,c,b = self.run_change(15,'_change_alert_pattern','On','Strobe')
        self.assertEqual(d.native,b); self.assertEqual(c.value,'On'); self.assertEqual(Message.calls,0)
    def test_unknown_imported_values_remain_on_cancel(self):
        d,c,b = self.run_change(14,'_change_alert_color','UnknownImportedColor','Red',2)
        self.assertEqual(d.native,b)
        d,c,b = self.run_change(15,'_change_alert_pattern','UnknownImportedPattern','On',2)
        self.assertEqual(d.native,b)
    def test_no_changes_no_dialog(self):
        d,c,b = self.run_change(14,'_change_alert_color','Off','Off')
        self.assertEqual(Message.calls,0); self.assertEqual(d.snapshots,0)
        d,c,b = self.run_change(15,'_change_alert_pattern','On','On')
        self.assertEqual(Message.calls,0); self.assertEqual(d.snapshots,0)

if __name__ == '__main__': unittest.main()
