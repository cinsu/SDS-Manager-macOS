# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""v0.0.7i: independent editable offline scanner configurations, no hardware."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scanner_configurations as sc
from native_favorites_export import build_native_bytes
from test_native_field_patch import fixture_lines, make_entries

REL = 'BCDx36HP/favorites_lists/f_000001.hpd'


def setup_config(root, raw):
    folder = root / 'base'
    file = folder / REL
    file.parent.mkdir(parents=True)
    file.write_bytes(raw)
    cfg = folder / 'BCDx36HP/profile.cfg'
    cfg.write_bytes(b'opaque profile bytes\x00\r\n')
    files = {}
    for path in (file, cfg):
        data = path.read_bytes()
        files[str(path.relative_to(folder))] = {
            'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    (folder/'configuration.json').write_text(json.dumps({
        'format':'sds100-configuration-snapshot-v1','name':'Base','files':files}))
    return folder, file


class SaveAsTests(unittest.TestCase):
    def test_clone_is_byte_exact_and_independent(self):
        with tempfile.TemporaryDirectory() as td:
            lib=Path(td)/'scanner-configurations'
            raw,rows=fixture_lines(mixed=True,bom=True)
            original,file=setup_config(lib,raw)
            clone,manifest=sc.save_configuration_as(original,'Second Configuration',library=lib)
            self.assertEqual(clone.name,'Second-Configuration')
            self.assertEqual((clone/REL).read_bytes(),raw)
            self.assertEqual((clone/'BCDx36HP/profile.cfg').read_bytes(),b'opaque profile bytes\x00\r\n')
            self.assertTrue(sc.verify_configuration(clone))
            self.assertEqual(manifest['name'],'Second Configuration')
            (clone/REL).write_bytes(b'changed independently')
            self.assertEqual(file.read_bytes(),raw)
            self.assertTrue(sc.verify_configuration(original))

    def test_save_as_includes_unsaved_native_edit_without_changing_source(self):
        with tempfile.TemporaryDirectory() as td:
            lib=Path(td)/'scanner-configurations'
            raw,rows=fixture_lines(mixed=True,bom=True)
            original,file=setup_config(lib,raw)
            entries=make_entries(file,raw,rows,'utf-8-sig')
            entries[1]['records'][2][5]='155275000'
            payload,expected=build_native_bytes(entries)
            clone,manifest=sc.save_configuration_as(original,'Edited Copy',{
                REL:(payload,expected)},library=lib)
            self.assertEqual((clone/REL).read_bytes(),payload)
            self.assertEqual(file.read_bytes(),raw)
            self.assertEqual((clone/'BCDx36HP/profile.cfg').read_bytes(),
                             (original/'BCDx36HP/profile.cfg').read_bytes())
            self.assertTrue(sc.verify_configuration(clone,manifest))
            self.assertTrue(sc.verify_configuration(original))
            self.assertIn(b'155275000', (clone/REL).read_bytes())
            self.assertIn(b'155250000', file.read_bytes())

    def test_duplicate_name_and_source_integrity_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            lib=Path(td)/'scanner-configurations'
            raw,_=fixture_lines()
            original,file=setup_config(lib,raw)
            with self.assertRaises(FileExistsError):
                sc.save_configuration_as(original,'base',library=lib)
            clone,_=sc.save_configuration_as(original,'Copy',library=lib)
            with self.assertRaises(FileExistsError):
                sc.save_configuration_as(original,'cOpY',library=lib)
            with self.assertRaises(FileExistsError):
                sc.save_configuration_as(original,'Copy',library=lib)
            self.assertTrue(clone.exists())
            file.write_bytes(raw+b'extra')
            with self.assertRaisesRegex(ValueError,'checksum'):
                sc.save_configuration_as(original,'New Name',library=lib)

    def test_bad_override_does_not_publish_partial_configuration(self):
        with tempfile.TemporaryDirectory() as td:
            lib=Path(td)/'scanner-configurations'
            raw,rows=fixture_lines()
            original,file=setup_config(lib,raw)
            with self.assertRaises(ValueError):
                sc.save_configuration_as(original,'Unsafe',{
                    REL:(b'invalid',rows)},library=lib)
            self.assertFalse((lib/'Unsafe').exists())
            self.assertEqual(file.read_bytes(),raw)
            self.assertEqual(list(lib.glob('.sds100-save-as-*')),[])

    def test_symlink_and_unsupported_override_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            lib=Path(td)/'scanner-configurations'
            raw,rows=fixture_lines()
            original,file=setup_config(lib,raw)
            with self.assertRaisesRegex(ValueError,'registered native HPD'):
                sc.save_configuration_as(original,'Wrong',{'BCDx36HP/profile.cfg':(b'x',rows)},library=lib)
            (original/'BCDx36HP/link').symlink_to(file)
            with self.assertRaisesRegex(ValueError,'symbolic link'):
                sc.save_configuration_as(original,'Linked',library=lib)

    def test_real_native_hpd_field_edit_in_save_as_is_byte_preserving(self):
        real=Path('/mnt/data/f_000003.hpd')
        if not real.is_file():
            self.skipTest('Optional real native sample not supplied')
        with tempfile.TemporaryDirectory() as td:
            lib=Path(td)/'scanner-configurations'
            raw=real.read_bytes()
            original,file=setup_config(lib,raw)
            rows=[line.split('\t') for line in raw.decode('cp1252').splitlines()]
            preamble=[]
            systems=[]
            current=None
            for row in rows:
                if row[0] in ('Trunk','Conventional'):
                    current={'origin':'native-copy','kind':row[0],
                             'name':row[3],'records':[]}
                    systems.append(current)
                if current is None:
                    preamble.append(row)
                else:
                    current['records'].append(row)
            entries=[{'key':['native-copy-meta',str(file)],'scope':'metadata',
                      'source_path':str(file),'records':preamble,'encoding':'cp1252',
                      'source_sha256':hashlib.sha256(raw).hexdigest(),
                      'newline':'\r\n','final_newline':True}]+systems
            frequency=next(row for sys in systems for row in sys['records']
                           if row[0] == 'T-Freq' and row[5].isdigit())
            old=frequency[5]
            frequency[5]=str(int(old)+12500)
            payload,desired=build_native_bytes(entries)
            self.assertEqual(payload,raw.replace(old.encode(),frequency[5].encode(),1))
            clone,manifest=sc.save_configuration_as(original,'Real native edit',{
                REL:(payload,desired)},library=lib)
            self.assertEqual((clone/REL).read_bytes(),payload)
            self.assertEqual(file.read_bytes(),raw)
            self.assertTrue(sc.verify_configuration(clone,manifest))

    def test_real_native_hpd_unmodified_save_as(self):
        real=Path('/mnt/data/f_000003.hpd')
        if not real.is_file():
            self.skipTest('Optional real native sample not supplied')
        with tempfile.TemporaryDirectory() as td:
            lib=Path(td)/'scanner-configurations'
            raw=real.read_bytes()
            original,file=setup_config(lib,raw)
            clone,_=sc.save_configuration_as(original,'Native sample copy',library=lib)
            self.assertEqual((clone/REL).read_bytes(),raw)
            self.assertTrue(sc.verify_configuration(clone))


if __name__=='__main__':
    unittest.main()
