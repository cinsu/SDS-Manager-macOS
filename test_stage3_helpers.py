# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Undo-all, bulk edit and drag-and-drop classification."""
import tempfile
import unittest
from pathlib import Path

import bulk_edit
import drop_targets
import undo_stack


def step_by_step(undo, redo, current):
    undo, redo = list(undo), list(redo)
    while undo:
        redo.append(current)
        current = undo.pop()
    return current, undo, redo


class UndoAllTests(unittest.TestCase):
    def test_matches_repeated_undo(self):
        for n in range(1, 6):
            undo = ['s%d' % i for i in range(n)]
            for redo in ([], ['r']):
                restore, new_undo, new_redo = undo_stack.rewind_all(undo, redo, 'now')
                self.assertEqual((restore, new_undo, new_redo), step_by_step(undo, redo, 'now'))

    def test_nothing_to_undo(self):
        self.assertIsNone(undo_stack.rewind_all([], ['x'], 'now'))

    def test_inputs_not_mutated(self):
        undo, redo = ['a', 'b'], []
        undo_stack.rewind_all(undo, redo, 'c')
        self.assertEqual((undo, redo), (['a', 'b'], []))


class BulkEditTests(unittest.TestCase):
    def records(self):
        return [['C-Group', '', '', 'Dept', 'Off'],
                ['C-Freq', '', '', 'Fire', 'Off', '154000000', 'FM', '', '3', 'Off', '2', '0'],
                ['C-Freq', '', '', 'Police', 'On', '155000000', 'FM', '', '2', 'On', '2', '1'],
                ['C-Freq', '', '', 'Short', 'Off'],
                ['TGID', '', '', 'Admin', 'Off', '44042']]

    def test_plan_and_apply(self):
        recs = self.records()
        result = bulk_edit.plan(recs, [1, 2, 3, 4, 0], 'Avoid', 'On')
        self.assertEqual([c[0] for c in result['changes']], [1, 3, 4])
        self.assertEqual(result['unchanged'], 1)
        self.assertEqual([s[0] for s in result['skipped']], [0])
        before = [r.copy() for r in recs]
        self.assertEqual(recs, before)               # planning never changes anything
        self.assertEqual(bulk_edit.apply(recs, result['changes'], 'Avoid', 'On'), 3)
        self.assertEqual([r[4] for r in recs[1:]], ['On', 'On', 'On', 'On'])
        self.assertEqual(recs[1][5:], before[1][5:])  # nothing else on the row moved

    def test_inapplicable_and_short_rows_are_skipped(self):
        recs = self.records()
        result = bulk_edit.plan(recs, [1, 3, 4], 'Delay', '5')
        self.assertEqual([c[0] for c in result['changes']], [1])
        reasons = {s[0]: s[2] for s in result['skipped']}
        self.assertIn('does not apply', reasons[4])
        self.assertIn('no Delay field', reasons[3])

    def test_rejects_unknown_field_and_bad_value(self):
        with self.assertRaises(ValueError):
            bulk_edit.plan(self.records(), [1], 'Nope', 'On')
        with self.assertRaises(ValueError):
            bulk_edit.plan(self.records(), [1], 'Delay', '99')
        with self.assertRaises(ValueError):
            bulk_edit.apply(self.records(), [(1, '', '')], 'Attenuator', 'Maybe')

    def test_out_of_range_target_skipped(self):
        result = bulk_edit.plan(self.records(), [99], 'Avoid', 'On')
        self.assertEqual(result['skipped'][0][2], 'no such record')

    def test_field_names_and_summary(self):
        self.assertEqual(bulk_edit.field_names(['TGID']), ['Avoid'])
        self.assertEqual(bulk_edit.field_names(['C-Freq', 'TGID']), list(bulk_edit.FIELDS))
        text = bulk_edit.summary('Avoid', 'On', bulk_edit.plan(self.records(), [1, 2, 3], 'Avoid', 'On'), limit=1)
        self.assertIn('Permanent Avoid', text)
        self.assertIn('and 1 more', text)
        self.assertIn('Undo restores every item at once', text)

    def test_choices_match_the_single_row_editor(self):
        import test_ui_extras_stub as stubs
        window = stubs.load('favorites_settings_window')
        self.assertEqual(bulk_edit.FIELDS['Avoid'][2], window.AVOID_CHOICES)
        self.assertEqual(bulk_edit.FIELDS['Attenuator'][2], window.ATTENUATOR_CHOICES)
        self.assertEqual(bulk_edit.FIELDS['Delay'][2], window.DELAY_CHOICES)
        self.assertEqual(bulk_edit.FIELDS['Volume Offset'][2], window.VOLUME_OFFSET_CHOICES)
        self.assertEqual(bulk_edit.AVOID_LABELS, window.AVOID_LABELS)


class DropTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def test_card_root_and_inner_folder(self):
        (self.base / 'card' / 'BCDx36HP').mkdir(parents=True)
        self.assertEqual(drop_targets.classify([self.base / 'card']), ('scanner', str(self.base / 'card'), ''))
        self.assertEqual(drop_targets.classify([self.base / 'card' / 'BCDx36HP'])[:2], ('scanner', str(self.base / 'card')))

    def test_hpd_file(self):
        f = self.base / 'f_000001.HPD'
        f.write_text('x')
        self.assertEqual(drop_targets.classify([f])[:2], ('hpd', str(f)))

    def test_refusals(self):
        (self.base / 'plain').mkdir()
        other = self.base / 'notes.txt'
        other.write_text('x')
        for paths in ([], [self.base / 'plain'], [other], [other, other], [self.base / 'missing.hpd']):
            action, path, message = drop_targets.classify(paths)
            self.assertIsNone(action)
            self.assertTrue(message)

    def test_symlink_refused(self):
        (self.base / 'card' / 'BCDx36HP').mkdir(parents=True)
        (self.base / 'link').symlink_to(self.base / 'card')
        self.assertIsNone(drop_targets.classify([self.base / 'link'])[0])



class DialogLogicTests(unittest.TestCase):
    """The dialog's new methods run against stand-in widgets (appearance is not tested)."""

    @classmethod
    def setUpClass(cls):
        import test_ui_extras_stub as stubs
        cls.mod = stubs.load('favorites_settings_window')

    def fake(self, rows=(0, 1, 2), records=None):
        from unittest.mock import MagicMock
        dialog = MagicMock()
        dialog.draft_name = 'D'
        self.records = records or [
            ['C-Group', '', '', 'Dept', 'Off'],
            ['C-Freq', '', '', 'Fire', 'Off', '1', 'FM', '', '3', 'Off', '2', '0'],
            ['C-Freq', '', '', 'Police', 'On', '2', 'FM', '', '2', 'Off', '2', '1']]
        dialog.workspace.drafts = {'D': [{'records': self.records}]}
        dialog.table.selectedIndexes.return_value = [MagicMock(**{'row.return_value': r}) for r in rows]
        dialog.table.item.side_effect = lambda r, c: MagicMock(**{'data.return_value': (0, r)})
        dialog.tree.currentItem.return_value.data.return_value = (0, 0)
        return dialog

    def run_bulk(self, dialog, field, shown, confirm=True):
        from unittest.mock import MagicMock
        box, question = self.mod.QMessageBox, self.mod.QInputDialog
        self.mod.QMessageBox = MagicMock()
        self.mod.QMessageBox.StandardButton.Yes = 'yes'
        self.mod.QMessageBox.question.return_value = 'yes' if confirm else 'no'
        self.mod.QInputDialog = MagicMock()
        self.mod.QInputDialog.getItem.side_effect = [(field, True), (shown, True)]
        try:
            self.mod.FavoritesSettingsDialog._bulk_edit_selected(dialog)
        finally:
            used = self.mod.QMessageBox
            self.mod.QMessageBox, self.mod.QInputDialog = box, question
        return used

    def test_bulk_change_is_one_snapshot_and_skips_the_group_row(self):
        dialog = self.fake()
        self.run_bulk(dialog, 'Avoid', 'Permanent Avoid')
        self.assertEqual([r[4] for r in self.records], ['Off', 'On', 'On'])   # group row untouched
        dialog.workspace._snapshot.assert_called_once()
        dialog.workspace.refresh_draft.assert_called_once()

    def test_declined_confirmation_changes_nothing(self):
        dialog = self.fake()
        self.run_bulk(dialog, 'Avoid', 'Permanent Avoid', confirm=False)
        self.assertEqual([r[4] for r in self.records], ['Off', 'Off', 'On'])
        dialog.workspace._snapshot.assert_not_called()

    def test_single_row_selection_is_refused(self):
        dialog = self.fake(rows=(1,))
        used = self.run_bulk(dialog, 'Avoid', 'Off')
        self.assertIn('Select two or more', str(used.information.call_args))
        dialog.workspace._snapshot.assert_not_called()

    def test_undo_redo_reports_empty_and_redraws(self):
        dialog = self.fake()
        dialog.workspace._undo, dialog.workspace._redo = [], []
        self.mod.FavoritesSettingsDialog._undo_redo(dialog, 'undo')
        dialog.workspace.undo_change.assert_not_called()
        dialog.workspace._undo = ['state']
        self.mod.FavoritesSettingsDialog._undo_redo(dialog, 'undo')
        dialog.workspace.undo_change.assert_called_once()
        dialog._restore_editor_selection.assert_called_once_with(0, 0)

    def test_undo_that_removes_the_draft_closes_the_editor(self):
        dialog = self.fake()
        dialog.workspace._undo = ['state']
        dialog.workspace.undo_change.side_effect = lambda: dialog.workspace.drafts.clear()
        box = self.mod.QMessageBox
        from unittest.mock import MagicMock
        self.mod.QMessageBox = MagicMock()
        try:
            self.mod.FavoritesSettingsDialog._undo_redo(dialog, 'undo')
        finally:
            self.mod.QMessageBox = box
        dialog.reject.assert_called_once()

    def test_right_click_inside_a_multi_selection_keeps_it(self):
        from unittest.mock import MagicMock
        dialog = self.fake(rows=(1, 2))
        point = MagicMock()
        dialog.table.rowAt.return_value = 1
        dialog.table.columnAt.return_value = 0
        menu = MagicMock()
        original = self.mod.QMenu
        self.mod.QMenu = MagicMock(return_value=menu)
        try:
            self.mod.FavoritesSettingsDialog._table_context_menu(dialog, point)
        finally:
            self.mod.QMenu = original
        dialog.table.selectRow.assert_not_called()
        self.assertIn('Change 2 Selected Rows', str(menu.addAction.call_args))

    def test_right_click_outside_the_selection_selects_that_row(self):
        from unittest.mock import MagicMock
        dialog = self.fake(rows=(1, 2))
        dialog.table.rowAt.return_value = 0
        dialog.table.columnAt.return_value = 0
        original = self.mod.QMenu
        self.mod.QMenu = MagicMock()
        try:
            self.mod.FavoritesSettingsDialog._table_context_menu(dialog, MagicMock())
        finally:
            self.mod.QMenu = original
        dialog.table.selectRow.assert_called_once_with(0)


if __name__ == '__main__':
    unittest.main()
