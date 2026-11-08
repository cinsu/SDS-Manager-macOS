# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Keys & Tags spreadsheet round trip and key card (v0.1.11), on real SDS100 files."""
import unittest

import keys_export as ke
import keys_model as km
from test_list_sync_export import SyncBase

try:
    import openpyxl
except ImportError:                                  # the package recommends python3-openpyxl
    openpyxl = None


@unittest.skipIf(openpyxl is None, 'openpyxl not installed')
class SpreadsheetTests(SyncBase):
    def model(self):
        return km.model_for_configuration(self.config)

    def test_round_trip_through_xlsx(self):
        path = self.base / 'keys.xlsx'
        self.assertEqual(ke.write_workbook(self.model(), path, 'Home'), path)
        wb = openpyxl.load_workbook(path)
        self.assertEqual(wb.sheetnames, ['How to Use', 'Key & Tag Map', 'Favorites Lists', 'Systems', 'Departments',
                                         'Channels'])
        lists = wb['Favorites Lists']
        self.assertEqual([lists.cell(5, c).value for c in (1, 2, 3, 4)], ['Greenville County', 'On', 0, 'Off'])
        self.assertEqual(lists.cell(5, 8).value, 'flist:f_000001.hpd')
        self.assertTrue(lists.cell(5, 6).value.startswith('=IF('))
        departments = wb['Departments']
        police = next(r for r in range(5, departments.max_row + 1)
                      if departments.cell(r, 3).value == 'Greenville (City) - Police')
        departments.cell(police, 4).value = 7
        systems = wb['Systems']
        greenville = next(r for r in range(5, systems.max_row + 1) if systems.cell(r, 2).value == 'Greenville')
        systems.cell(greenville, 4).value = 'abc'
        lists.cell(6, 3).value = 'Off'
        lists.cell(6, 2).value = 'Off'
        wb.save(path)
        values = ke.read_values(path)
        model = self.model()
        changed, problems = ke.apply_values(model, values)
        self.assertEqual(changed, 2)                     # police key 7, SC Highway Patrol monitor Off
        self.assertEqual(len(problems), 1)
        self.assertIn('not a whole number', problems[0])
        lines = model.describe_changes()
        self.assertIn('Greenville County › Greenville › Greenville (City) - Police: quick key 1 → 7', lines)
        self.assertIn('SC Highway Patrol: Monitor Off', lines)

    @unittest.skipIf(ke.soffice() is None, 'LibreOffice not installed')
    def test_ods_with_working_formulas(self):
        model = self.model()
        fire = next(i for i in model.items if i['name'] == 'Greenville (City) - Fire Department')
        police = next(i for i in model.items if i['name'] == 'Greenville (City) - Police')
        model.set_number(police, 'key', fire['key'])                 # a clash the sheet should flag
        path = ke.write_workbook(model, self.base / 'keys.ods', 'Home')
        self.assertEqual(path.suffix, '.ods')
        values = ke.read_values(path)
        self.assertEqual(values['flist:f_000001.hpd']['key'], 0)
        import shutil, subprocess
        subprocess.run([ke.soffice(), '--headless', '--convert-to', 'xlsx', '--outdir', str(self.base), str(path)],
                       check=True, capture_output=True, timeout=180)
        wb = openpyxl.load_workbook(self.base / 'keys.xlsx', data_only=True)
        departments = wb['Departments']
        checks = {departments.cell(r, 3).value: departments.cell(r, 6).value for r in range(5, departments.max_row + 1)}
        self.assertEqual(checks['Greenville (City) - Police'], 'Shared – used twice')
        self.assertEqual(checks['Greenville County'], 'OK')          # Palmetto 800's key 0: another system
        self.assertEqual(wb['Key & Tag Map'].cell(4, 2).value, 'Greenville County')
        self.assertEqual(wb['Key & Tag Map'].cell(4, 4).value, 'Used')

    def test_stale_rows_are_skipped(self):
        changed, problems = ke.apply_values(self.model(), {'row:f_000009.hpd:1:0': {'name': 'Gone', 'key': 3}})
        self.assertEqual((changed, len(problems)), (0, 1))


class KeyCardTests(SyncBase):
    def test_card(self):
        model = km.model_for_configuration(self.config)
        channel = next(i for i in model.items if i['level'] == 'channel')
        model.set_number(channel, 'tag', 120)
        html = ke.card_html(model, 'Home')
        self.assertIn('<td align="center">00</td><td>Greenville County</td>', html)
        self.assertIn('01 Greenville (City) - Police', html)
        self.assertIn(f'<td align="center">120</td><td>{channel["name"]}</td>', html)
        self.assertNotIn('Military', html)               # no key, no tag, not monitored


if __name__ == '__main__':
    unittest.main()
