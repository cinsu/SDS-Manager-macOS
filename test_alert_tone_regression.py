# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Headless Alert Tone handler regression tests."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
SRC=Path(__file__).with_name('favorites_settings_window.py')
TREE=ast.parse(SRC.read_text())
CHOICES=next(n for n in TREE.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ALERT_TONE_CHOICES' for t in n.targets))
DIALOG=next(n for n in TREE.body if isinstance(n,ast.ClassDef) and n.name=='FavoritesSettingsDialog')
HANDLER=next(n for n in DIALOG.body if isinstance(n,ast.FunctionDef) and n.name=='_change_alert_tone')
class MessageBox:
    StandardButton=SimpleNamespace(Yes=1, No=2)
    answer=1; questions=0
    @classmethod
    def question(cls,*a): cls.questions+=1;return cls.answer
namespace={'QMessageBox':MessageBox,'ROLE':'record'}
exec(compile(ast.Module(body=[CHOICES,HANDLER],type_ignores=[]),str(SRC),'exec'),namespace)
class Combo:
    def __init__(self,s): self.s=s
    def setCurrentText(self,s):self.s=s
class Item:
    def __init__(self): self.text=''
    def data(self,k):return (0,0)
    def setText(self,x):self.text=x
class Dialog:
    _change_alert_tone=namespace['_change_alert_tone']
    def __init__(self, old):
        self.native=['C-Freq','','','Test']+['']*8+[old]+['X']*5
        self.workspace=SimpleNamespace(drafts={'draft':[{'records':[self.native]}]},_snapshot=self.snap,refresh_draft=self.refresh,status=SimpleNamespace(setText=lambda s:None))
        self.draft_name='draft';self._refreshing=False;self.snapshots=0;self.refreshes=0;self.item=Item()
        self.table=SimpleNamespace(rowCount=lambda:1,item=lambda r,c:self.item if c==10 else None)
    def snap(self):self.snapshots+=1
    def refresh(self):self.refreshes+=1
class Tests(unittest.TestCase):
    def setUp(self):MessageBox.answer=1;MessageBox.questions=0
    def test_choices(self): self.assertEqual(namespace['ALERT_TONE_CHOICES'],('Off', '1','2','3','4','5','6','7','8','9'))
    def test_accept_mutates_only_field12(self):
        d=Dialog('Off'); before=d.native.copy(); c=Combo('5');d._change_alert_tone(0,0,c,'5')
        self.assertEqual(d.native[12],'5');self.assertEqual(d.native[:12],before[:12]);self.assertEqual(d.native[13:],before[13:]);self.assertEqual(d.item.text,'5');self.assertEqual(d.snapshots,1);self.assertEqual(d.refreshes,1)
    def test_cancel(self):
        MessageBox.answer=2;d=Dialog('3');c=Combo('7');d._change_alert_tone(0,0,c,'7');self.assertEqual(d.native[12],'3');self.assertEqual(c.s,'3');self.assertEqual(d.snapshots,0)
    def test_unknown_old_on_cancel(self):
        MessageBox.answer=2;d=Dialog('Unknown');c=Combo('1');d._change_alert_tone(0,0,c,'1');self.assertEqual(d.native[12],'Unknown')
    def test_reject_unsupported(self):
        d=Dialog('Off');c=Combo('10');d._change_alert_tone(0,0,c,'10');self.assertEqual(d.native[12],'Off');self.assertEqual(c.s,'Off');self.assertEqual(d.snapshots,0)
    def test_noop(self):
        d=Dialog('Off');c=Combo('Off');d._change_alert_tone(0,0,c,'Off');self.assertEqual(d.snapshots,0);self.assertEqual(MessageBox.questions,0)
if __name__=='__main__':unittest.main()
