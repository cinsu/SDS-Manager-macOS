# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Exporting lists changed by Keys & Tags and by the list editor (v0.1.13). A real export was refused
with "Line 3: only a system/site/department name may change" after a system's quick key was changed."""
import copy

import favorites_clipboard as fc
import hand_entry as he
import keys_model as km
import scanner_first_write as writer
from native_favorites_export import build_native_bytes
from test_favorites_clipboard import FIX, find, native
from test_list_sync_export import SyncBase

LIST = 'favorites_lists/f_000001.hpd'


class ExportKeysTests(SyncBase):
    def entries(self):
        path = self.local / LIST
        entries = native(path)
        data = path.read_bytes()
        import hashlib
        entries[0].update(newline='\r\n', final_newline=True, source_sha256=hashlib.sha256(data).hexdigest(),
                          records=entries[0]['records'])
        return entries

    def save(self, entries):
        rows = [r for e in entries for r in e['records']]
        payload = b''.join(('\t'.join(r) + '\r\n').encode('cp1252') for r in rows)
        (self.local / LIST).write_bytes(payload)
        self.refresh_manifest()

    def eligible(self):
        return writer.first_write_eligibility(self.config, self.scanner)

    def test_keys_and_tags_edits_export(self):
        entries = self.entries()
        greenville = entries[find(entries, 'Greenville')]['records']
        greenville[0][7], greenville[0][8] = '5', '2'            # system quick key and number tag
        police = next(r for r in greenville if r[0] == 'C-Group' and r[3] == 'Greenville (City) - Police')
        police[9] = '7'                                          # department quick key
        dqk = next(r for r in greenville if r[0] == 'DQKs_Status')
        dqk[2 + 1] = 'Off'                                       # department key 01 switched Off
        channel = next(r for r in greenville if r[0] == 'C-Freq')
        channel[16] = '120'                                      # channel number tag
        self.save(entries)
        ok, why = self.eligible()
        self.assertTrue(ok, why)
        self.assertNotIn('only a system/site/department name may change', why)
        result = writer.execute_first_write(self.config, self.scanner)
        self.assertEqual((self.scanner / LIST).read_bytes(), (self.local / LIST).read_bytes())
        self.assertTrue(result)

    def test_bigger_edits_are_checked_as_a_whole_list(self):
        entries = self.entries()
        i = find(entries, 'Greenville')
        records = entries[i]['records']
        records[0][7] = '4'                                      # a field change ...
        records.extend(he.conventional_department_rows('Lake Patrol', [he.channel('Lake 1', '453.150', 'FM')]))
        _k, start, _e = next(b for b in fc.blocks(records) if b[0] == 'C-Group')
        fc.remove_department(entries, i, start)                  # ... a new and a deleted department
        entries.append(fc._new_entry(entries, he.conventional_system_rows('Mine', 'Dept', [he.channel('Ch', '462.5625')])))
        ExportKeysTests.save(self, entries)
        ok, why = ExportKeysTests.eligible(self)
        self.assertTrue(ok, why)
        self.assertIn('checked as a complete Favorites List', why)

    def test_a_broken_list_is_still_refused(self):
        entries = self.entries()
        records = entries[find(entries, 'Greenville')]['records']
        records[0][7] = '150'                                    # no such quick key
        self.save(entries)
        ok, why = self.eligible()
        self.assertFalse(ok)
        self.assertIn('f_000001.hpd', why)


class ScannerBandPlanTests(SyncBase):
    """A real SDS100 list had a 34-column BandPlan_P25 line; the full-list check expected 50 (v0.1.16)."""

    def short_band_plan(self, data):
        lines = data.split(b'\r\n')
        out = []
        for line in lines:
            if line.startswith(b'BandPlan_P25\t'):
                line = b'\t'.join(line.split(b'\t')[:34])
            out.append(line)
        return b'\r\n'.join(out)

    def test_scanner_band_plan_kept_through_a_bigger_edit(self):
        import scanner_list_sync as sync
        source = (FIX / 'confirmed_f_000012_p25_nxdn.hpd').read_bytes()
        scanner_copy = self.short_band_plan(source)
        self.assertIn(b'BandPlan_P25', scanner_copy)
        self.assertTrue(sync.assess_new_hpd(scanner_copy)[0])          # 34 columns is a known layout now
        odd = b'\r\n'.join(b'\t'.join(l.split(b'\t')[:20]) if l.startswith(b'BandPlan_P25\t') else l
                           for l in source.split(b'\r\n'))
        self.assertFalse(sync.assess_new_hpd(odd)[0])                   # an unknown layout on its own: refused
        self.assertTrue(sync.assess_new_hpd(odd, original=odd)[0])      # ... unless the scanner wrote it
        # export: scanner and configuration hold the list; the configuration adds a department and a key
        (self.scanner / LIST).write_bytes(scanner_copy)
        (self.local / LIST).write_bytes(scanner_copy)
        self.refresh_manifest()
        entries = ExportKeysTests.entries(self)
        palmetto = entries[find(entries, 'Palmetto 800')]['records']
        palmetto[0][12] = '3'                                    # a trunked system's quick key (v0.1.17)
        greenville = entries[find(entries, 'Pickens')]['records']
        greenville.extend(he.conventional_department_rows('Lake Patrol', [he.channel('Lake 1', '453.150', 'FM')]))
        ExportKeysTests.save(self, entries)
        ok, why = ExportKeysTests.eligible(self)
        self.assertTrue(ok, why)
        self.assertIn('checked as a complete Favorites List', why)
