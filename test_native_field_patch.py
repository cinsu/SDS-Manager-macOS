# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Pure Python regressions for v0.0.7h native Favorites field-only saving."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from native_favorites_field_patch import patch_native_fields, NativePatchError, NativeStructureChanged
from native_favorites_export import build_native_bytes, validate_export_file
import scanner_configurations


def fixture_lines(*, mixed=False, bom=False):
    conventional = ['Conventional','','','Local System','Off','','Conventional'] + ['']*8
    group = ['C-Group','','','Department'] + ['']*5
    channel = ['C-Freq','','','Sample Channel','Off','155250000','Auto','','1','Off','2','0','Off','Auto','Off','On','Off','Off']
    trunk = ['Trunk','','','Trunked','Off','','P25Standard']
    site = ['Site','','','Main Site','Off','','']
    tfreq = ['T-Freq','','','','Off','851012500','1','ColorCode=Srch','OpaqueExtension']
    tgroup = ['T-Group','','','Talkgroups']
    tgid = ['TGID','','','Dispatch','Off','1234','All']+['']*10
    rows = [['TargetModel','BCDx36HP'],['FormatVersion','1.00'],conventional,group,channel,trunk,site,tfreq,tgroup,tgid]
    ends = ['\r\n','\n','\r','\r\n','\r\n','\n','\r\n','\r\n','\n',''] if mixed else ['\r\n']*len(rows)
    content = ''.join('\t'.join(row)+end for row,end in zip(rows,ends))
    return ((b'\xef\xbb\xbf' if bom else b'')+content.encode('utf-8' if bom else 'cp1252')),rows


def make_entries(source, raw, rows, encoding='cp1252'):
    return [
        {'key':['native-copy-meta',str(source)], 'scope':'metadata','source_path':str(source),
         'records':rows[:2], 'encoding':encoding,'source_sha256':hashlib.sha256(raw).hexdigest(),
         'newline':'\r\n','final_newline':True},
        {'origin':'native-copy','kind':'Conventional','name':'Local System','records':rows[2:5]},
        {'origin':'native-copy','kind':'Trunk','name':'Trunked','records':rows[5:]},
    ]

class FieldPatchTests(unittest.TestCase):
    def test_no_edit_byte_exact_with_mixed_line_endings_and_bom(self):
        raw, rows = fixture_lines(mixed=True,bom=True)
        output, changes = patch_native_fields(raw,rows,'utf-8-sig',expected_sha256=hashlib.sha256(raw).hexdigest())
        self.assertEqual((output,changes),(raw,0))

    def test_multiple_edits_preserve_every_other_byte(self):
        raw, rows = fixture_lines(mixed=True,bom=True)
        rows[4][3] = 'Renamed Channel'
        rows[4][5] = '155262500'
        rows[7][5] = '852012500'
        rows[9][5] = '4321'
        output, changes = patch_native_fields(raw,rows,'utf-8-sig')
        self.assertEqual(changes,4)
        self.assertEqual(output.count(b'\r\n'),raw.count(b'\r\n'))
        self.assertEqual(output.count(b'\n'),raw.count(b'\n'))
        self.assertEqual(output.count(b'\r'),raw.count(b'\r'))
        self.assertIn(b'\tOpaqueExtension\r\n',output)
        self.assertEqual(output.replace(b'Renamed Channel',b'Sample Channel').replace(b'155262500',b'155250000').replace(b'852012500',b'851012500').replace(b'4321',b'1234'),raw)
        restored = [list(x) for x in fixture_lines(mixed=True,bom=True)[1]]
        result, _ = patch_native_fields(output,restored,'utf-8-sig')
        self.assertEqual(result,raw)

    def test_protect_opaque_and_reserved_fields(self):
        raw, rows = fixture_lines()
        rows[7][8] = 'Altered'
        with self.assertRaisesRegex(NativePatchError,'Undocumented'):
            patch_native_fields(raw,rows)
        rows[7][8] = 'OpaqueExtension'
        rows[7][4] = 'On'
        with self.assertRaisesRegex(NativePatchError,'reserved'):
            patch_native_fields(raw,rows)

    def test_validate_known_changed_fields(self):
        for idx,value in [(5,'155.250000'),(5,'9999999999'),(6,'WFM'),(4,'Temporary')]:
            raw, rows = fixture_lines()
            rows[4][idx] = value
            with self.subTest(idx=idx,value=value), self.assertRaises(NativePatchError):
                patch_native_fields(raw,rows)
        raw, rows = fixture_lines()
        rows[9][5] = 'abc'
        with self.assertRaises(NativePatchError):
            patch_native_fields(raw,rows)

    def test_structural_change_not_silently_patched(self):
        raw, rows = fixture_lines()
        rows[4].append('new field')
        with self.assertRaises(NativeStructureChanged):
            patch_native_fields(raw,rows)
        raw, rows = fixture_lines()
        rows.pop()
        with self.assertRaises(NativeStructureChanged):
            patch_native_fields(raw,rows)

    def test_stale_sha_blocks(self):
        raw, rows = fixture_lines()
        with self.assertRaisesRegex(NativePatchError,'changed since opening'):
            patch_native_fields(raw,rows,expected_sha256='0'*64)

    def test_existing_gui_draft_serializer_preserves_native_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'f_000001.hpd'
            raw, rows = fixture_lines(mixed=True,bom=True)
            path.write_bytes(raw)
            entries = make_entries(path,raw,rows,'utf-8-sig')
            entries[1]['records'][2][5]='155275000'
            payload, desired = build_native_bytes(entries)
            self.assertEqual(payload,raw.replace(b'155250000',b'155275000'))
            candidate=Path(td)/'candidate.hpd'
            candidate.write_bytes(payload)
            self.assertEqual(validate_export_file(candidate,desired)['bytes'],len(payload))
            self.assertEqual(path.read_bytes(),raw)

    def test_existing_gui_draft_rejects_changed_source(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'f_000001.hpd'
            raw, rows=fixture_lines()
            path.write_bytes(raw)
            entries=make_entries(path,raw,rows)
            path.write_bytes(raw+b'\n')
            with self.assertRaisesRegex(ValueError,'changed since opening'):
                build_native_bytes(entries)

    def test_local_save_uses_existing_verified_backup_and_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            lib=Path(td)/'scanner-configurations'
            folder=lib/'home'
            relative=Path('BCDx36HP/favorites_lists/f_000001.hpd')
            target=folder/relative
            target.parent.mkdir(parents=True)
            raw, rows=fixture_lines()
            target.write_bytes(raw)
            import json
            manifest={'format':'sds100-configuration-snapshot-v1','name':'Home',
                      'files':{str(relative):{'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}}}
            (folder/'configuration.json').write_text(json.dumps(manifest))
            entries=make_entries(target,raw,rows)
            entries[1]['records'][2][5]='155275000'
            payload, desired=build_native_bytes(entries)
            with patch.object(scanner_configurations,'library_path',return_value=lib):
                result=scanner_configurations.save_local_favorites(folder,relative,payload,desired)
                self.assertTrue(result['changed'])
                self.assertTrue(scanner_configurations.verify_configuration(folder))
            self.assertEqual(target.read_bytes(),payload)
            self.assertEqual(Path(result['backup']).read_bytes(),raw)
            self.assertEqual(Path(result['backup']).parent,lib.parent/'scanner-configuration-backups'/'home')

if __name__=='__main__':
    unittest.main()
