# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""v0.0.7m isolated durable-recovery tests: NEVER use a real scanner."""
import tempfile
import unittest
from pathlib import Path

from scanner_write_recovery_rehearsal import (
    LocalMockTransaction, SimulatedPowerLoss, rehearse_write_recovery, sha)


def native(value=b'851012500'):
    fields = [b''] * 18
    fields[0] = b'C-Freq'
    fields[3] = b'Example'
    fields[4] = b'Off'
    fields[5] = value
    fields[6] = b'Auto'
    return b'TargetModel\tBCDx36HP\r\n' + b'\t'.join(fields) + b'\r\n'


class DurableRecoveryTests(unittest.TestCase):
    def fixture(self, base):
        root = base/'scanner'/'BCDx36HP'
        target = root/'favorites_lists'/'f_000001.hpd'
        target.parent.mkdir(parents=True)
        target.write_bytes(native())
        source = base/'local'/'f_000001.hpd'
        source.parent.mkdir()
        source.write_bytes(native(b'851475000'))
        rel = 'favorites_lists/f_000001.hpd'
        return root, rel, target, source

    def test_mock_transaction_commit_verified_and_journal_cleared(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _, rel, original, proposed = self.fixture(base)
            workspace = base/'sandbox'; workspace.mkdir()
            tx = LocalMockTransaction(workspace,rel)
            old,new = tx.prepare(original,proposed)
            self.assertTrue(tx.apply(proposed,old,new))
            self.assertEqual(sha(tx.target),new)
            self.assertEqual(sha(tx.backup),old)
            self.assertFalse(tx.journal.exists())
            self.assertEqual(original.read_bytes(),native())

    def test_recovery_after_all_three_interruption_points(self):
        for phase in ('journal','stage','replace'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                _,rel,original,proposed = self.fixture(base)
                workspace = base/'sandbox'; workspace.mkdir()
                tx = LocalMockTransaction(workspace,rel)
                old,new = tx.prepare(original,proposed)
                with self.assertRaises(SimulatedPowerLoss):
                    tx.apply(proposed,old,new,fail_at=phase)
                restarted = LocalMockTransaction(workspace,rel)
                self.assertTrue(restarted.recover())
                self.assertEqual(sha(restarted.target),old)
                self.assertFalse(restarted.journal.exists())
                self.assertFalse(restarted.stage.exists())
                self.assertEqual(original.read_bytes(),native())

    def test_corrupt_backup_fails_closed_and_retains_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _,rel,original,proposed = self.fixture(base)
            workspace = base/'sandbox'; workspace.mkdir()
            tx = LocalMockTransaction(workspace,rel)
            old,new = tx.prepare(original,proposed)
            with self.assertRaises(SimulatedPowerLoss):
                tx.apply(proposed,old,new,fail_at='replace')
            tx.backup.write_bytes(b'corrupt')
            with self.assertRaisesRegex(IOError,'backup missing or corrupt'):
                LocalMockTransaction(workspace,rel).recover()
            self.assertTrue(tx.journal.exists())

    def test_tampered_destination_fails_closed_and_retains_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _,rel,original,proposed = self.fixture(base)
            workspace = base/'sandbox'; workspace.mkdir()
            tx = LocalMockTransaction(workspace,rel)
            old,new = tx.prepare(original,proposed)
            with self.assertRaises(SimulatedPowerLoss):
                tx.apply(proposed,old,new,fail_at='replace')
            tx.target.write_bytes(b'unexpected third version')
            with self.assertRaisesRegex(IOError,'Unexpected mock target'):
                LocalMockTransaction(workspace,rel).recover()
            self.assertTrue(tx.journal.exists())

    def test_source_changes_before_apply_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _,rel,original,proposed = self.fixture(base)
            workspace = base/'sandbox'; workspace.mkdir()
            tx = LocalMockTransaction(workspace,rel)
            old,new = tx.prepare(original,proposed)
            proposed.write_bytes(native(b'851475025'))
            with self.assertRaisesRegex(IOError,'Proposed file changed'):
                tx.apply(proposed,old,new)
            self.assertFalse(tx.journal.exists())

    def test_unsafe_or_structural_edits_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _,rel,original,proposed = self.fixture(base)
            workspace = base/'sandbox'; workspace.mkdir()
            with self.assertRaises(ValueError):
                LocalMockTransaction(workspace,'../escape.hpd')
            tx = LocalMockTransaction(workspace,rel)
            proposed.write_bytes(native()+native())
            with self.assertRaisesRegex(ValueError,'Unsafe native candidate'):
                tx.prepare(original,proposed)
            self.assertFalse(tx.target.exists())

    def test_local_rehearsal_on_different_filesystem_uses_real_narrow_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root,rel,target,source = self.fixture(base)
            original = target.read_bytes()
            report,ok = rehearse_write_recovery(root,{rel:source},{rel:target},
                {'ADD':[],'REPLACE':[rel]},workspace_base='/dev/shm')
            self.assertTrue(ok,report)
            self.assertIn('actual narrow candidate',report)
            self.assertIn('Restart recovery after journal/stage/replacement interruption: PASSED (3/3)',report)
            self.assertIn('Scanner writes: 0',report)
            self.assertEqual(target.read_bytes(),original)

    def test_structural_candidate_uses_synthetic_copy_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root,rel,target,source = self.fixture(base)
            source.write_bytes(native()+native())
            original = target.read_bytes()
            report,ok = rehearse_write_recovery(root,{rel:source},{rel:target},
                {'ADD':[],'REPLACE':[rel]},workspace_base='/dev/shm')
            self.assertTrue(ok,report)
            self.assertIn('synthetic one-field edit',report)
            self.assertEqual(target.read_bytes(),original)

    def test_same_filesystem_rejected_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root,rel,target,source = self.fixture(base)
            original = target.read_bytes()
            report,ok = rehearse_write_recovery(root,{rel:source},{rel:target},
                {'ADD':[],'REPLACE':[rel]},workspace_base=tmp)
            self.assertFalse(ok)
            self.assertIn('DIFFERENT filesystem',report)
            self.assertEqual(target.read_bytes(),original)

    def test_mock_parent_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _,rel,original,proposed = self.fixture(base)
            workspace = base/'sandbox'; workspace.mkdir()
            (workspace/'mock-device').mkdir()
            (workspace/'external').mkdir()
            (workspace/'mock-device'/'favorites_lists').symlink_to(workspace/'external', target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'Symlinked mock'):
                LocalMockTransaction(workspace,rel)

    def test_symlink_candidate_not_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root,rel,target,source = self.fixture(base)
            source.unlink()
            source.symlink_to(target)
            original = target.read_bytes()
            report,ok = rehearse_write_recovery(root,{rel:source},{rel:target},
                {'ADD':[],'REPLACE':[rel]},workspace_base='/dev/shm')
            self.assertTrue(ok,report)
            self.assertIn('synthetic one-field edit',report)
            self.assertEqual(target.read_bytes(),original)


if __name__ == '__main__':
    unittest.main()
