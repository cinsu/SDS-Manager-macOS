# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
import hashlib
import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

import scanner_firmware as sf

MAIN = bytes(range(256)) * 2048           # 512 KiB of binary
SUB = bytes(reversed(range(256))) * 64    # 16 KiB


class FirmwareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.card = self.base / 'card'
        (self.card / 'BCDx36HP').mkdir(parents=True)
        (self.card / 'BCDx36HP' / 'scanner.inf').write_bytes(
            b'TargetModel\tBCDx36HP\r\nFormatVersion\t1.00\r\nScanner\tSDS100\t38326-000000000-000\t1.26.01 \t01\r\n')
        self.identity_calls = 0

    def identity(self, root):
        self.identity_calls += 1
        return ('usb', '1965:001c', str(root))

    def cand(self, name, data):
        return sf.candidate_from_bytes(name, data, 'SDS100', source='test')

    # names ------------------------------------------------------------------------------
    def test_names_match_only_this_model(self):
        self.assertEqual(sf.parse_name('SDS100_V1_26_01.bin', 'SDS100')['version'], (1, 26, 1))
        self.assertEqual(sf.parse_name('SDS100-SUB_V1_03_15.firm', 'SDS100')['kind'], 'sub')
        self.assertEqual(sf.parse_name('SDS100_V1.23.20.bin', 'SDS100')['label'], '1.23.20')
        for bad in ('SDS100E_V1_23_09.bin', 'SDS200_V1_24_00.bin', 'SDS100_V1_26_01.bin.exe',
                    'SDS100-SUB_V1_03_15.bin', 'xSDS100_V1_26_01.bin', 'SDS100_V1_26.bin'):
            self.assertIsNone(sf.parse_name(bad, 'SDS100'), bad)
        self.assertEqual(sf.parse_name('SDS100E_V1_23_09.bin', 'SDS100E')['label'], '1.23.09')
        self.assertIsNone(sf.parse_name('SDS100_V1_26_01.bin', 'SDS 100'))

    def test_uniden_server_spelling_with_a_hyphen(self):
        self.assertEqual(sf.parse_name('SDS-100_V1_26_01.bin', 'SDS100')['label'], '1.26.01')
        self.assertEqual(sf.parse_name('SDS-100-SUB_V1_03_15.firm', 'SDS100')['kind'], 'sub')
        for bad in ('SDS-100E_V1_23_15.bin', 'SDS100E-SUB_V1_03_06.firm', 'SDS--100_V1_26_01.bin',
                    'BCD436HP_V1_28_24.bin'):
            self.assertIsNone(sf.parse_name(bad, 'SDS100'), bad)

    def test_location_tables_are_not_leftovers(self):
        folder = self.card / 'BCDx36HP' / 'firmware'
        folder.mkdir()
        for name in ('CityTable_V1_00_00.dat', 'ZipTable_V1_00_00.dat', 'SDS100_V1_20_00.bin'):
            (folder / name).write_bytes(b'x' * 10)
        info = sf.card_info(self.card)
        self.assertEqual(info['waiting'], ['SDS100_V1_20_00.bin'])
        self.assertEqual(info['other_files'], ['CityTable_V1_00_00.dat', 'ZipTable_V1_00_00.dat'])
        sf.execute(self.card, [self.cand('SDS100_V1_27_00.bin', MAIN)], identity=self.identity)
        self.assertTrue((folder / 'CityTable_V1_00_00.dat').exists())
        self.assertTrue((folder / 'ZipTable_V1_00_00.dat').exists())

    def test_card_info_reads_model_and_version(self):
        info = sf.card_info(self.card)
        self.assertEqual((info['model'], info['firmware'], info['version']), ('SDS100', '1.26.01', (1, 26, 1)))
        self.assertEqual(info['waiting'], [])

    def test_card_without_inf_is_refused(self):
        (self.card / 'BCDx36HP' / 'scanner.inf').unlink()
        with self.assertRaises(sf.FirmwareError):
            sf.card_info(self.card)

    # checking files ---------------------------------------------------------------------
    def test_error_pages_and_wrong_sizes_refused(self):
        page = b'<!DOCTYPE html><html><body>401 Unauthorized</body></html>' + b' ' * 300000
        with self.assertRaisesRegex(sf.FirmwareError, 'web page'):
            self.cand('SDS100_V1_26_01.bin', page)
        with self.assertRaisesRegex(sf.FirmwareError, 'outside the expected size'):
            self.cand('SDS100_V1_26_01.bin', b'\x01' * 1000)
        with self.assertRaisesRegex(sf.FirmwareError, 'not firmware for the SDS100'):
            self.cand('SDS200_V1_24_00.bin', MAIN)
        self.assertEqual(self.cand('SDS100-SUB_V1_03_15.firm', SUB)['sha256'], hashlib.sha256(SUB).hexdigest())

    def test_text_sub_firmware_is_allowed(self):
        hexfile = (b':10000000' + b'0123456789ABCDEF' * 2 + b'00\r\n') * 600
        self.assertEqual(self.cand('SDS100-SUB_V1_03_15.firm', hexfile)['kind'], 'sub')

    def test_uniden_zip_is_opened_in_memory(self):
        z = self.base / 'SDS100_V1.23.15_Main_V1.03.06_Sub.zip'
        with zipfile.ZipFile(z, 'w') as archive:
            archive.writestr('SDS100_V1_23_15/SDS100_V1_23_15.bin', MAIN)
            archive.writestr('SDS100_V1_23_15/SDS100-SUB_V1_03_06.firm', SUB)
            archive.writestr('../../evil.bin', MAIN)
            archive.writestr('readme.txt', b'hello')
        found = sf.load_local(z, 'SDS100')
        self.assertEqual(sorted(c['name'] for c in found), ['SDS100-SUB_V1_03_06.firm', 'SDS100_V1_23_15.bin'])
        self.assertFalse((self.base / 'evil.bin').exists())
        wrong = self.base / 'other.zip'
        with zipfile.ZipFile(wrong, 'w') as archive:
            archive.writestr('SDS200_V1_24_00.bin', MAIN)
        with self.assertRaisesRegex(sf.FirmwareError, 'SDS200_V1_24_00.bin'):
            sf.load_local(wrong, 'SDS100')

    # server -------------------------------------------------------------------------------
    def test_discover_lists_only_this_model(self):
        page = ('<html><a href="MasterHpdb_10_25_2026.gz">x</a><a href="SDS100_V1_26_01.bin">a</a>'
                '<a href="/BCDx36HP/SDS100-SUB_V1_03_15.firm">b</a><a href="SDS100E_V1_26_01.bin">c</a>'
                '<a href="SDS200_V1_24_00.bin">d</a><a href="SDS100_V1_24_00.bin">e</a></html>').encode()
        result = sf.discover('SDS100', 'u', 'p', fetch=lambda name: page)
        self.assertEqual([f['name'] for f in result['files']],
                         ['SDS100-SUB_V1_03_15.firm', 'SDS100_V1_26_01.bin', 'SDS100_V1_24_00.bin'])
        self.assertEqual(result['others'], ['SDS100E_V1_26_01.bin', 'SDS200_V1_24_00.bin'])

    def test_discover_with_unidens_real_listing(self):
        # The names Uniden's server listed on 2026-11-04.
        names = ['BCD436HP_V1_28_24.bin', 'BCD536HP_V1_28_24.bin', 'SDS-100-SUB_V1_03_15.firm',
                 'SDS-100_V1_26_01.bin', 'SDS100E-SUB_V1_03_06.firm', 'SDS100E_V1_23_15.bin']
        page = ''.join(f'<a href="{n}">{n}</a>' for n in names).encode()
        result = sf.discover('SDS100', 'u', 'p', fetch=lambda name: page)
        self.assertEqual(sorted(f['name'] for f in result['files']),
                         ['SDS-100-SUB_V1_03_15.firm', 'SDS-100_V1_26_01.bin'])

    def test_download_keeps_file_and_refuses_bad_names(self):
        got = sf.download('SDS100_V1_26_01.bin', 'SDS100', 'u', 'p', self.base / 'dl', fetch=lambda n: MAIN)
        self.assertTrue((self.base / 'dl' / 'SDS100_V1_26_01.bin').is_file())
        self.assertEqual(got['sha256'], hashlib.sha256(MAIN).hexdigest())
        again = sf.download('SDS100_V1_26_01.bin', 'SDS100', 'u', 'p', self.base / 'dl',
                            fetch=lambda n: self.fail('should reuse the saved file'))
        self.assertEqual(again['sha256'], got['sha256'])
        with self.assertRaises(sf.FirmwareError):
            sf.download('../SDS100_V1_26_01.bin.sh', 'SDS100', 'u', 'p', self.base / 'dl', fetch=lambda n: MAIN)
        with self.assertRaisesRegex(sf.FirmwareError, 'web page'):
            sf.download('SDS100_V1_27_00.bin', 'SDS100', 'u', 'p', self.base / 'dl',
                        fetch=lambda n: b'<html>' + b'x' * 300000)
        self.assertFalse((self.base / 'dl' / 'SDS100_V1_27_00.bin').exists())

    # planning and writing ----------------------------------------------------------------
    def test_plan_versions_and_limits(self):
        p = sf.plan(self.card, [self.cand('SDS100_V1_27_00.bin', MAIN)])
        self.assertFalse(p['downgrade'])
        self.assertIn('1.26.01 → 1.27.00', p['notes'][0])
        p = sf.plan(self.card, [self.cand('SDS100_V1_23_20.bin', MAIN)])
        self.assertTrue(p['downgrade'])
        with self.assertRaisesRegex(sf.FirmwareError, 'at most one main'):
            sf.plan(self.card, [self.cand('SDS100_V1_27_00.bin', MAIN), self.cand('SDS100_V1_26_01.bin', MAIN)])
        with self.assertRaises(sf.FirmwareError):
            sf.plan(self.card, [])

    def test_write_places_verified_files_and_removes_leftovers(self):
        folder = self.card / 'BCDx36HP' / 'firmware'
        folder.mkdir()
        (folder / 'SDS100_V1_20_00.bin').write_bytes(MAIN[:300000])
        files = [self.cand('SDS100_V1_27_00.bin', MAIN), self.cand('SDS100-SUB_V1_03_16.firm', SUB)]
        plan = sf.plan(self.card, files)
        self.assertEqual(plan['leftovers'], ['SDS100_V1_20_00.bin'])
        result = sf.execute(self.card, files, identity=self.identity, log_folder=self.base / 'logs')
        self.assertEqual(sorted(p.name for p in folder.iterdir()),
                         ['SDS100-SUB_V1_03_16.firm', 'SDS100_V1_27_00.bin'])
        self.assertEqual((folder / 'SDS100_V1_27_00.bin').read_bytes(), MAIN)
        self.assertEqual(result['removed'], ['SDS100_V1_20_00.bin'])
        self.assertIn('WROTE SDS100_V1_27_00.bin', Path(result['receipt']).read_text())
        self.assertGreaterEqual(self.identity_calls, 3)

    def test_leftovers_kept_when_asked(self):
        folder = self.card / 'BCDx36HP' / 'firmware'
        folder.mkdir()
        (folder / 'SDS100_V1_20_00.bin').write_bytes(b'x')
        sf.execute(self.card, [self.cand('SDS100_V1_27_00.bin', MAIN)], remove_leftovers=False,
                   identity=self.identity)
        self.assertTrue((folder / 'SDS100_V1_20_00.bin').exists())

    def test_write_stops_if_the_scanner_changes(self):
        calls = {'n': 0}

        def flaky(root):
            calls['n'] += 1
            return 'first' if calls['n'] == 1 else 'other'
        with self.assertRaisesRegex(sf.FirmwareError, 'changed'):
            sf.execute(self.card, [self.cand('SDS100_V1_27_00.bin', MAIN)], identity=flaky)
        folder = self.card / 'BCDx36HP' / 'firmware'
        self.assertEqual(list(folder.iterdir()) if folder.exists() else [], [])

    def test_symlinked_firmware_folder_refused(self):
        elsewhere = self.base / 'elsewhere'
        elsewhere.mkdir()
        os.symlink(elsewhere, self.card / 'BCDx36HP' / 'firmware')
        with self.assertRaises(sf.FirmwareError):
            sf.execute(self.card, [self.cand('SDS100_V1_27_00.bin', MAIN)], identity=self.identity)
        self.assertEqual(list(elsewhere.iterdir()), [])


if __name__ == '__main__':
    unittest.main()


class FirmwareDialogStubTests(unittest.TestCase):
    """Drives the window on the Qt stub: catches typos and broken control flow (not appearance)."""

    def setUp(self):
        import importlib
        from unittest.mock import MagicMock
        import qt_stub
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.card = base / 'card'
        (self.card / 'BCDx36HP').mkdir(parents=True)
        (self.card / 'BCDx36HP' / 'scanner.inf').write_bytes(
            b'Scanner\tSDS100\t38326-000000000-000\t1.26.01 \t01\r\n')
        with qt_stub.installed(forget=('firmware_dialog',)):
            self.fd = importlib.import_module('firmware_dialog')
        # The stub QDialog is a MagicMock; make its child widgets plain mocks, not FirmwareDialogs.
        self.fd.FirmwareDialog._get_child_mock = lambda _self, **kw: MagicMock(**kw)
        self.fd.DOWNLOADS = base / 'downloads'
        self.fd.RECEIPTS = base / 'receipts'
        self.window = MagicMock()
        self.window._db_update_busy = False
        self.window.pick_scanner_folder.return_value = str(self.card)
        # run background work immediately
        self.window._run_background.side_effect = lambda title, text, work, done: self._run(work, done)
        self.MagicMock = MagicMock

    def _run(self, work, done):
        try:
            done(work(), None)
        except Exception as exc:
            done(None, f'{type(exc).__name__}: {exc}')


    def test_add_file_rejects_other_models(self):
        dialog = self.fd.FirmwareDialog(self.window)
        dialog.choose_scanner()
        other = Path(self.tmp.name) / 'SDS200_V1_24_00.bin'
        other.write_bytes(MAIN)
        self.fd.QFileDialog.getOpenFileName.return_value = (str(other), '')
        dialog.add_file()
        self.assertEqual(dialog.rows, [])
        good = Path(self.tmp.name) / 'SDS100_V1_26_01.bin'
        good.write_bytes(MAIN)
        self.fd.QFileDialog.getOpenFileName.return_value = (str(good), '')
        dialog.add_file()
        self.assertEqual([r['name'] for r in dialog.rows], ['SDS100_V1_26_01.bin'])
