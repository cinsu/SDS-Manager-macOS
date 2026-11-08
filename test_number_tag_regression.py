# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Headless domain/handler tests; no PyQt6 needed for CI compilation checks.

The actual graphical control still requires a user test on Kubuntu.
"""
import ast
from pathlib import Path
from types import SimpleNamespace
import re
import unittest

SRC=Path(__file__).with_name('favorites_settings_window.py')
TREE=ast.parse(SRC.read_text(encoding='utf-8'))
VALIDATOR=next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=='valid_number_tag')
DIALOG=next(n for n in TREE.body if isinstance(n,ast.ClassDef) and n.name=='FavoritesSettingsDialog')
HANDLER=next(n for n in DIALOG.body if isinstance(n,ast.FunctionDef) and n.name=='_change_number_tag')
class FakeQMessageBox:
    StandardButton=SimpleNamespace(Yes=1,No=2)
    answer=1
    questions=0
    warnings=0
    @classmethod
    def question(cls, *args):
        cls.questions+=1
        return cls.answer
    @classmethod
    def warning(cls, *args):
        cls.warnings+=1
namespace={'re':re,'QMessageBox':FakeQMessageBox,'ROLE':'row'}
exec(compile(ast.Module(body=[VALIDATOR,HANDLER],type_ignores=[]),str(SRC),'exec'),namespace)

class FakeCombo:
    def __init__(self,txt): self.txt=txt
    def currentText(self): return self.txt
    def setCurrentText(self,v): self.txt=v
class FakeItem:
    def __init__(self): self.txt=''
    def data(self,key): return (0,0)
    def setText(self,v): self.txt=v
class FakeWorkspace:
    def __init__(self,old):
        self.row=['C-Freq','','','Test Channel']+['']*12+[old,'On']
        self.drafts={'test':[{'records':[self.row]}]}
        self.status=SimpleNamespace(setText=lambda v:None)
        self.snapshots=0;self.refreshes=0
    def _snapshot(self): self.snapshots+=1
    def refresh_draft(self): self.refreshes+=1
class FakeDialog:
    _change_number_tag=namespace['_change_number_tag']
    def __init__(self,old):
        self.workspace=FakeWorkspace(old)
        self.draft_name='test';self._refreshing=False;self._tag_confirmation_active=False
        self.item=FakeItem();self.table=SimpleNamespace(rowCount=lambda:1,item=lambda row,col:self.item if col==14 else None)

class Tests(unittest.TestCase):
    def setUp(self):
        FakeQMessageBox.answer=1
        FakeQMessageBox.questions=0
        FakeQMessageBox.warnings=0
    def test_native_validation(self):
        v=namespace['valid_number_tag']
        for tag in ('Off','0','1','35','999'): self.assertTrue(v(tag),tag)
        for tag in ('','off','On','-1','1000','01','003','1.5','+1',' 2 '): self.assertFalse(v(tag),tag)
    def test_accept_only_field_16(self):
        d=FakeDialog('Off'); c=FakeCombo('999');before=d.workspace.row.copy()
        d._change_number_tag(0,0,c)
        self.assertEqual(d.workspace.row[16],'999')
        self.assertEqual(d.workspace.row[:16],before[:16]);self.assertEqual(d.workspace.row[17:],before[17:])
        self.assertEqual(d.item.txt,'999');self.assertEqual(d.workspace.snapshots,1)
        self.assertEqual(d.workspace.refreshes,1)
        self.assertFalse(d._tag_confirmation_active)
    def test_reject_change_leaves_model_and_view(self):
        FakeQMessageBox.answer=2
        d=FakeDialog('14');c=FakeCombo('17')
        d._change_number_tag(0,0,c)
        self.assertEqual(d.workspace.row[16],'14');self.assertEqual(c.txt,'14')
        self.assertEqual(d.workspace.snapshots,0)
    def test_invalid_leaves_model_intact(self):
        d=FakeDialog('Off');c=FakeCombo('1000')
        d._change_number_tag(0,0,c)
        self.assertEqual(d.workspace.row[16],'Off');self.assertEqual(c.txt,'Off')
        self.assertEqual(d.workspace.snapshots,0);self.assertEqual(FakeQMessageBox.warnings,1)
    def test_unknown_original_preserved_on_cancel(self):
        FakeQMessageBox.answer=2
        d=FakeDialog('invalid-from-scanner');c=FakeCombo('45')
        d._change_number_tag(0,0,c)
        self.assertEqual(d.workspace.row[16],'invalid-from-scanner')
        self.assertEqual(c.txt,'invalid-from-scanner')
    def test_no_op(self):
        d=FakeDialog('5');c=FakeCombo('5')
        d._change_number_tag(0,0,c)
        self.assertEqual(d.workspace.snapshots,0);self.assertEqual(FakeQMessageBox.questions,0)
    def test_reentrant_focus_signal_suppressed(self):
        d=FakeDialog('Off');c=FakeCombo('5')
        d._tag_confirmation_active=True
        d._change_number_tag(0,0,c)
        self.assertEqual(d.workspace.snapshots,0)
        self.assertEqual(FakeQMessageBox.questions,0)

if __name__=='__main__': unittest.main()
