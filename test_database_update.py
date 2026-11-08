# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scanner_database_update as du
import scanner_first_write as writer
from test_list_sync_export import SyncBase, FIX

CRLF = b'\r\n'
HEADER = b'TargetModel\tBCDx36HP\r\nFormatVersion\t1.00\r\n'


def state_file(state_id):
    body = (FIX / 'real_hpdb_greenville_county.txt').read_bytes()
    body += (FIX / 'real_hpdb_palmetto_trunk_excerpt.txt').read_bytes() if False else b''
    if state_id != 45:
        body = body.replace(b'StateId=45', b'StateId=%d' % state_id)
    return HEADER + body


def config_file(date, states=(45, 13)):
    lines = [b'TargetModel\tBCDx36HP', b'FormatVersion\t1.00', b'DateModified\t' + date.encode()]
    lines += [b'StateInfo\tStateId=%d\tCountryId=1\tState %d\t' % (s, s) for s in states]
    lines += [b'CountyInfo\tCountyId=%d\tStateId=%d\tCounty %d' % (s * 100, s, s) for s in states]
    return CRLF.join(lines) + CRLF


class DbBase(SyncBase):
    OLD_DATE = '09/01/2026 10:00:00'
    NEW_DATE = '10/01/2026 10:00:00'

    def setUp(self):
        super().setUp()
        self.card = self.scanner / 'HPDB'
        self.card.mkdir()
        self.package = self.base / 'package'
        self.package.mkdir()
        for folder, date in ((self.card, self.OLD_DATE), (self.package, self.NEW_DATE)):
            for sid in (45, 13):
                (folder / ('s_%06d.hpd' % sid)).write_bytes(state_file(sid))
            (folder / 'hpdb.cfg').write_bytes(config_file(date))
        (self.package / 'MasterHpdb.hp1').write_bytes(b'not for the card')

    def card_state(self):
        return {p.name: p.read_bytes() for p in self.card.iterdir()}

    def put(self, name, data):
        (self.package / name).write_bytes(data)

    def new_text(self, name='s_000045.hpd'):
        return (self.package / name).read_bytes()

    def edit_new(self, old, new, name='s_000045.hpd', count=1):
        data = self.new_text(name)
        self.assertIn(old, data)
        self.put(name, data.replace(old, new, count))

    def refused(self, fragment=''):
        ok, reason = du.database_update_eligibility(self.package, self.scanner)
        self.assertFalse(ok)
        self.assertIn(fragment, reason)
        return reason


class UpdateTests(DbBase):
    def test_changed_state_and_config_are_written_with_verified_backup(self):
        self.edit_new(b'Caesars Head Repeater/Skywarn Upstate', b'Caesars Head Repeater (renamed)')
        before = self.scanner_state()
        ok, reason = du.database_update_eligibility(self.package, self.scanner)
        self.assertTrue(ok, reason)
        self.assertIn('1 state file(s) will be replaced (1 already identical) and hpdb.cfg', reason)
        result = du.execute_database_update(self.package, self.scanner)
        self.assertEqual(result['files'], ['HPDB/s_000045.hpd', 'HPDB/hpdb.cfg'])      # hpdb.cfg last
        self.assertEqual((self.card / 's_000045.hpd').read_bytes(), self.new_text())
        self.assertEqual((self.card / 'hpdb.cfg').read_bytes(), (self.package / 'hpdb.cfg').read_bytes())
        after = self.scanner_state()
        for name, data in before.items():
            if not name.startswith('HPDB/'):
                self.assertEqual(after[name], data, name)       # favorites, profile, everything else
        self.assertEqual(after['HPDB/s_000013.hpd'], before['HPDB/s_000013.hpd'])
        self.assertNotIn('HPDB/MasterHpdb.hp1', after)
        backup = Path(result['backup'])
        self.assertEqual((backup / 'BCDx36HP/HPDB/s_000045.hpd').read_bytes(), before['HPDB/s_000045.hpd'])
        self.assertTrue((backup / 'EXPORT_RECOVERY.txt').is_file())
        self.assertTrue((backup / 'EXPORT_RESULT.json').is_file())

    def test_second_run_has_nothing_to_do(self):
        self.edit_new(b'Caesars Head', b'Caesars Hd')
        du.execute_database_update(self.package, self.scanner)
        self.refused('already holds exactly this database')

    def test_failure_part_way_restores_every_file(self):
        self.edit_new(b'Caesars Head', b'Caesars Hd')
        self.edit_new(b'Furman', b'Furmans', 's_000013.hpd')
        before = self.scanner_state()
        real = writer._stage_and_replace
        calls = []

        def flaky(destination, payload, expected):
            calls.append(destination.name)
            if len(calls) == 2:
                raise OSError('simulated card error')
            return real(destination, payload, expected)
        with patch.object(writer, '_stage_and_replace', flaky):
            with self.assertRaises(writer.FirstWriteError) as raised:
                du.execute_database_update(self.package, self.scanner)
        self.assertIn('restored from the verified backup', str(raised.exception))
        self.assertEqual(self.scanner_state(), before)

    def test_package_is_never_modified(self):
        self.edit_new(b'Caesars Head', b'Caesars Hd')
        snapshot = {p.name: p.read_bytes() for p in self.package.iterdir()}
        du.execute_database_update(self.package, self.scanner)
        self.assertEqual({p.name: p.read_bytes() for p in self.package.iterdir()}, snapshot)


class GuardTests(DbBase):
    def test_older_database_is_refused(self):
        self.put('hpdb.cfg', config_file('08/01/2026 10:00:00'))
        self.refused('OLDER')

    def test_different_set_of_states_is_refused(self):
        (self.package / 's_000013.hpd').unlink()
        self.refused('different states')

    def test_unknown_record_type_or_field_count_is_refused(self):
        self.put('s_000045.hpd', self.new_text() + b'Mystery\tx\ty\r\n')
        self.refused('type the scanner does not use')
        self.put('s_000045.hpd', state_file(45) + b'AreaState\tCountyId=1\tStateId=45\textra\r\n')
        self.refused('field count the scanner does not use')

    def test_system_for_another_state_is_refused(self):
        self.edit_new(b'StateId=45', b'StateId=13', count=1)
        self.refused('belong to another state')

    def test_wrong_header_and_line_endings_are_refused(self):
        self.put('s_000045.hpd', self.new_text().replace(b'BCDx36HP', b'BCD436HP', 1))
        self.refused('header')
        self.put('s_000045.hpd', self.new_text().replace(b'BCD436HP', b'BCDx36HP').rstrip(b'\r\n'))
        self.refused('CRLF')

    def test_a_database_that_barely_resembles_the_card_is_refused(self):
        # Every frequency changes: the rebuilt format is not what the scanner holds.
        data = self.new_text()
        self.put('s_000045.hpd', data.replace(b'\tFM\t', b'\tNFM\t'))
        self.refused('records are present in the new file')

    def test_truncated_state_file_is_refused(self):
        data = self.new_text()
        lines = data.split(b'\r\n')
        self.put('s_000045.hpd', b'\r\n'.join(lines[:len(lines) // 5]) + b'\r\n')
        self.refused('')

    def test_config_must_list_the_same_states_and_have_a_date(self):
        self.put('hpdb.cfg', config_file(self.NEW_DATE, states=(45,)))
        self.refused('different states')
        self.put('hpdb.cfg', config_file(self.NEW_DATE).replace(b'DateModified\t10/01/2026 10:00:00', b'DateModified\tsoon'))
        self.refused('DateModified')

    def test_scanner_identity_and_symlinks_are_enforced(self):
        self.edit_new(b'Caesars Head', b'Caesars Hd')
        self.evidence = dict(self.evidence, product_name='Other')
        self.refused('USB identity')
        self.evidence = dict(self.evidence, product_name='SDS100')
        (self.package / 'link').symlink_to(self.package / 'hpdb.cfg')        # any symlink in the package
        self.refused('Symbolic link')


class AfterUpdateTests(DbBase):
    def test_favorites_export_still_works_after_the_database_changed(self):
        shutil.copytree(self.card, self.local / 'HPDB')          # the saved configuration holds the old HPDB
        self.refresh_manifest()
        self.edit_new(b'Caesars Head', b'Caesars Hd')
        du.execute_database_update(self.package, self.scanner)
        self.create_list()
        ok, reason = writer.first_write_eligibility(self.config, self.scanner)
        self.assertTrue(ok, reason)
        self.assertNotIn('HPDB', reason)
        writer.execute_first_write(self.config, self.scanner)
        self.assertEqual((self.card / 's_000045.hpd').read_bytes(), self.new_text())     # new database kept


if __name__ == '__main__':
    unittest.main()
