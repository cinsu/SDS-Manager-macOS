# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Headless native Alert Volume editing regression tests."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
SRC=Path(__file__).with_name('favorites_settings_window.py')
TREE=ast.parse(SRC.read_text())
CHOICES=next(n for n in TREE.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ALERT_VOLUME_CHOICES' for t in n.targets))
DIALOG=next(n for n in TREE.body if isinstance(n,ast.ClassDef) and n.name=='FavoritesSettingsDialog')
HANDLER=next(n for n in DIALOG.body if isinstance(n,ast.FunctionDef) and n.name=='_change_alert_volume')
class QMessageBox:
    StandardButton=SimpleNamespace(Yes=1, No=2)
    answer=1; questions=0
    @classmethod
    def question(cls,*a): cls.questions+=1;return cls.answer
scope={'QMessageBox':QMessageBox,'ROLE':'record'}
exec(compile(ast.Module(body=[CHOICES,HANDLER],type_ignores=[]),str(SRC),'exec'),scope)
class Combo:
    def __init__(self,s):self.s=s
    def setCurrentText(self,s):self.s=s
class Item:
    def __init__(self):self.text=''
    def data(self,k):return (0,0)
    def setText(self,v):self.text=v
class Dialog:
    _change_alert_volume=scope['_change_alert_volume']
    def __init__(self,old):
        self.native=['C-Freq','','','Test']+['']*9+[old]+['X']*5
        self.item=Item();self.snapshots=0;self.refreshes=0
        self.workspace=SimpleNamespace(drafts={'draft':[{'records':[self.native]}]},_snapshot=self.snap,refresh_draft=self.refresh,status=SimpleNamespace(setText=lambda s:None))
        self.draft_name='draft';self._refreshing=False
        self.table=SimpleNamespace(rowCount=lambda:1,item=lambda r,c:self.item if c==11 else None)
    def snap(self):self.snapshots+=1
    def refresh(self):self.refreshes+=1
class Tests(unittest.TestCase):
    def setUp(self):QMessageBox.answer=1;QMessageBox.questions=0
    def test_choices(self):self.assertEqual(scope['ALERT_VOLUME_CHOICES'],('Auto',)+tuple(str(i) for i in range(1,16)))
    def test_accept_field13_only(self):
        d=Dialog('Auto');before=d.native.copy();c=Combo('5');d._change_alert_volume(0,0,c,'5')
        self.assertEqual(d.native[13],'5');self.assertEqual(d.native[:13],before[:13]);self.assertEqual(d.native[14:],before[14:]);self.assertEqual(d.item.text,'5');self.assertEqual(d.snapshots,1);self.assertEqual(d.refreshes,1)
    def test_cancel(self):
        QMessageBox.answer=2;d=Dialog('Auto');c=Combo('9');d._change_alert_volume(0,0,c,'9');self.assertEqual(d.native[13],'Auto');self.assertEqual(c.s,'Auto');self.assertEqual(d.snapshots,0)
    def test_unknown_preservation(self):
        QMessageBox.answer=2;d=Dialog('Mystery');c=Combo('2');d._change_alert_volume(0,0,c,'2');self.assertEqual(d.native[13],'Mystery')
    def test_reject_out_of_range(self):
        d=Dialog('Auto');c=Combo('16');d._change_alert_volume(0,0,c,'16');self.assertEqual(d.native[13],'Auto');self.assertEqual(c.s,'Auto');self.assertEqual(d.snapshots,0)
    def test_noop(self):
        d=Dialog('Auto');c=Combo('Auto');d._change_alert_volume(0,0,c,'Auto');self.assertEqual(d.snapshots,0);self.assertEqual(QMessageBox.questions,0)
    def test_default_column_placement(self):
        assign=next(n for n in TREE.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='COLUMNS' for t in n.targets))
        cols=ast.literal_eval(assign.value)
        self.assertEqual(cols.index('Alert Volume'),cols.index('Alert Tone')+1)
if __name__=='__main__':unittest.main()
