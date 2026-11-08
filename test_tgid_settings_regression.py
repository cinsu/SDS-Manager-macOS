# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Native TGID [field isolation + confirmation + rendering] offline regression tests.

Can run in the build environment without PyQt6; GUI testing still required.
"""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

source = Path(__file__).with_name('favorites_settings_window.py')
tree = ast.parse(source.read_text())
editor = next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name == 'FavoritesSettingsDialog')
extract = {'TGID_VISIBLE_NATIVE', 'TGID_EDIT_CHOICES', 'TGID_FIELD_LABELS',
           'TGID_AUDIO_TYPE_CHOICES', 'TGID_TDMA_SLOT_CHOICES',
           'SERVICE_TYPE_NAMES', 'tgid_display_value', 'service_label'}
nodes = [n for n in tree.body if (
    isinstance(n,ast.Assign) and any(isinstance(target,ast.Name) and target.id in extract for target in n.targets)
    or isinstance(n,ast.FunctionDef) and n.name in extract)]
method_names = {'_change_tgid_setting', '_restore_tgid_combo', '_change_tgid_name'}
nodes += [n for n in editor.body if isinstance(n,ast.FunctionDef) and n.name in method_names]

class Message:
    StandardButton = SimpleNamespace(Yes=1,No=2)
    answer=1
    @classmethod
    def question(cls,*args): return cls.answer
    @classmethod
    def warning(cls,*args): pass

ns={'QMessageBox':Message,'ROLE':'role'}
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'),ns)

class Combo:
    def __init__(self, old, new):
        self.values=[old,new]
        self.current=1
    def currentData(self):return self.values[self.current]
    def findData(self,value):
        try:return self.values.index(value)
        except ValueError:return -1
    def setCurrentIndex(self,index):self.current=index

class TestNativeTalkgroupSettings(unittest.TestCase):
    def setUp(self):
        self.row=['TGID','TgidId=7','TGroupId=2','Police Dispatch','Off','1234','ALL',
                  '2','2','0','Off','Auto','Off','On','Off','Off','Any']
        self.before=self.row.copy()
        self.events=[]
        self.display={}
        self.workspace=SimpleNamespace(
            drafts={'Test':[{'scope':'metadata','encoding':'cp1252'}, {'records':[self.row]}]},
            _snapshot=lambda:self.events.append('snapshot'),
            refresh_draft=lambda:self.events.append('refresh'),
            status=SimpleNamespace(setText=lambda v:self.events.append('status')))
        self.items={c: SimpleNamespace(data=lambda role:(1,0),setText=lambda v,c=c:self.display.__setitem__(c,v))
                    for c in range(18)}
        self.obj=SimpleNamespace(workspace=self.workspace,draft_name='Test',
                                 _refreshing=False,
                                 table=SimpleNamespace(rowCount=lambda:1,item=lambda r,c:self.items[c]),
                                 _restore_tgid_combo=lambda combo,original:ns['_restore_tgid_combo'](self.obj,combo,original))
        Message.answer=1

    def change(self,column,new,confirm=1):
        Message.answer=confirm
        native_index=ns['TGID_VISIBLE_NATIVE'][column]
        combo=Combo(self.row[native_index],new)
        ns['_change_tgid_setting'](self.obj,1,0,combo,column)
        return combo

    def test_spec_offsets(self):
        self.assertEqual(ns['TGID_VISIBLE_NATIVE'],{
            5:7,7:6,9:8,10:10,11:11,12:12,13:13,14:9,15:14,16:15,17:16})
        self.assertEqual(tuple(ns['TGID_AUDIO_TYPE_CHOICES']),('ALL','ANALOG','DIGITAL'))
        self.assertEqual(tuple(ns['TGID_TDMA_SLOT_CHOICES']),('Any','1','2'))

    def test_every_enabled_field_edits_only_its_native_slot(self):
        options={5:'7',7:'DIGITAL',9:'-5',10:'4',11:'7',12:'Blue',13:'Slow Blink',14:'-3',15:'123',16:'On',17:'2'}
        for col,new in options.items():
            with self.subTest(column=col):
                self.setUp()
                self.change(col,new)
                index=ns['TGID_VISIBLE_NATIVE'][col]
                self.assertEqual(self.row[index],new)
                self.assertEqual(self.row[:index]+self.row[index+1:],
                                 self.before[:index]+self.before[index+1:])
                self.assertEqual(self.events.count('snapshot'),1)
                self.assertEqual(self.events.count('refresh'),1)
                self.assertEqual(self.display[col],ns['tgid_display_value'](col,new))

    def test_cancel_rolls_back_combo_and_native_row(self):
        combo=self.change(17,'1',confirm=2)
        self.assertEqual(combo.currentData(),'Any')
        self.assertEqual(self.row,self.before)
        self.assertEqual(self.events,[])

    def test_tgid_alert_tone_cancel_and_validation(self):
        combo=self.change(10,'4',confirm=2)
        self.assertEqual(combo.currentData(),'Off')
        self.assertEqual(self.row,self.before)
        self.assertEqual(self.events,[])
        combo=self.change(10,'10')
        self.assertEqual(combo.currentData(),'Off')
        self.assertEqual(self.row,self.before)
        self.assertEqual(self.events,[])

    def test_noop_does_not_snapshot(self):
        self.change(9,'2')
        self.assertEqual(self.row,self.before)
        self.assertEqual(self.events,[])

    def test_unknown_import_preserved_and_unsupported_new_value_rejected(self):
        self.row[16]='Unrecognized'
        self.before=self.row.copy()
        combo=self.change(17,'3')
        self.assertEqual(combo.currentData(),'Unrecognized')
        self.assertEqual(self.row,self.before)
        self.assertEqual(self.events,[])

    def test_short_or_other_kind_is_ignored(self):
        self.row.pop()
        ns['_change_tgid_setting'](self.obj,1,0,Combo('Any','2'),17)
        self.assertEqual(self.events,[])
        self.row[0]='C-Freq'
        self.change(7,'DIGITAL')
        self.assertEqual(self.events,[])

    def test_service_names_and_audio_type_labels(self):
        self.assertEqual(ns['tgid_display_value'](5,'2'),'Law Dispatch')
        self.assertEqual(ns['tgid_display_value'](5,'999'),'Service ID 999')
        self.assertEqual(ns['tgid_display_value'](7,'ALL'),'All')
        self.assertEqual(ns['tgid_display_value'](7,'DIGITAL'),'DIGITAL')

    def test_tgid_name_accepts_only_name_field(self):
        cell=SimpleNamespace(text=lambda:'County Police',setText=lambda x:None)
        ns['_change_tgid_name'](self.obj,cell,self.row)
        self.assertEqual(self.row[3],'County Police')
        self.assertEqual(self.row[:3]+self.row[4:],self.before[:3]+self.before[4:])
        self.assertEqual(self.events.count('snapshot'),1)

    def test_tgid_name_cancel_and_invalid(self):
        seen=[]
        cell=SimpleNamespace(text=lambda:'County Police',setText=lambda x:seen.append(x))
        Message.answer=2
        ns['_change_tgid_name'](self.obj,cell,self.row)
        self.assertEqual(self.row,self.before)
        self.assertEqual(seen,['Police Dispatch'])
        self.assertEqual(self.events,[])
        cell=SimpleNamespace(text=lambda:'Bad\nName',setText=lambda x:seen.append(x))
        ns['_change_tgid_name'](self.obj,cell,self.row)
        self.assertEqual(self.row,self.before)
        self.assertEqual(len(seen),2)

    def test_gui_hook_and_editable_alerts(self):
        source_text=source.read_text()
        self.assertIn("if kind == 'TGID':\n                    for logical_column, choices",source_text)
        self.assertIn('self._change_tgid_setting(ei, ri, cb, col)',source_text)
        self.assertIn('self._change_tgid_name(cell, row)',source_text)
        for col in (11,12,13,15):
            self.assertIn(col,ns['TGID_EDIT_CHOICES'])

if __name__=='__main__': unittest.main()
