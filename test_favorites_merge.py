# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
import unittest
from favorites_merge import merge_records, merge_draft_entry

S=['Conventional','1','','Greenville']
P=['C-Group','1','','Police']
F=['C-Group','2','','Fire']
A=['C-Freq','1','','Events','','155.1']
B=['C-Freq','2','','Forensics','','155.2']
C=['C-Freq','3','','Dispatch','','154.1']
T=['Trunk','1','','Palmetto 800']
SITE=['Site','1','','Greenville County Simulcast']
SITE2=['Site','2','','Spartanburg']
D=['T-Group','1','','Police']
TG1=['TGID','1','','Ops','','100']
TG2=['TGID','2','','Dispatch','','101']

class MergeTests(unittest.TestCase):
    def test_add_channel_existing_department(self):
        merged,n=merge_records([S,P,A],[S,P,B]);self.assertEqual(n,1);self.assertEqual(merged,[S,P,A,B])
    def test_add_department(self):
        merged,n=merge_records([S,P,A],[S,F,C]);self.assertEqual(n,2);self.assertEqual(merged,[S,P,A,F,C])
    def test_duplicate_noop(self):
        original=[S,P,A]; merged,n=merge_records(original,[S,P,A]);self.assertEqual(n,0);self.assertEqual(merged,original)
    def test_trunk_add_talkgroup_and_site(self):
        merged,n=merge_records([T,SITE,D,TG1],[T,SITE2,D,TG2]);self.assertEqual(n,2);self.assertEqual(merged,[T,SITE,SITE2,D,TG1,TG2])
    def test_preserve_other_group(self):
        merged,n=merge_records([S,P,A,F,C],[S,P,B]);self.assertEqual(n,1);self.assertEqual(merged,[S,P,A,B,F,C])
    def test_reject_different_system(self):
        with self.assertRaises(ValueError): merge_records([S,P,A],[T,SITE])
    def test_entry_metadata(self):
        old={'records':[S,P,A], 'selected_departments':['Police']}
        added=merge_draft_entry(old,{'records':[S,F,C], 'selected_departments':['Fire']})
        self.assertEqual(added,2);self.assertEqual(old['selected_departments'],['Police','Fire'])

if __name__=='__main__': unittest.main()
