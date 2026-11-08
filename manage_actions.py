# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""File and Favorites menu tasks for managing configurations and lists (v0.1.7).

Replaces the old Drafts & Planning menu: everything now works on the open scanner configuration, its
Favorites Lists are the lists you edit, Save Configuration keeps the changes and Export to Scanner sends
them. New Scanner Configuration, New / Duplicate / Copy / Import / Reorder Favorites Lists.
"""
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                             QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QMessageBox, QPushButton, QRadioButton, QVBoxLayout)

import configuration_tasks as tasks
import favorites_clipboard as clipboard
import hand_entry

YES, NO = QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No


class NewListDialog(QDialog):
    """Name and first content of a new Favorites List."""

    def __init__(self, parent, section_name, clip):
        super().__init__(parent)
        self.setWindowTitle('New Favorites List')
        self.resize(520, 420)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setMaxLength(64)
        form.addRow('Name', self.name)
        layout.addLayout(form)
        layout.addWidget(QLabel('A Favorites List starts with at least one system. Start it with:'))
        self.from_database = QRadioButton('The system selected in the database: ' + (section_name or '(none selected)'))
        self.from_database.setEnabled(bool(section_name))
        usable_clip = clip is not None and clip['what'] != 'leaves'
        self.from_clipboard = QRadioButton('What you cut or copied: ' +
                                           (clipboard.describe(clip) if usable_clip else '(nothing)'))
        self.from_clipboard.setEnabled(usable_clip)
        self.by_hand = QRadioButton('A conventional system I type in')
        for button in (self.from_database, self.from_clipboard, self.by_hand):
            layout.addWidget(button)
        (self.from_database if section_name else self.from_clipboard if usable_clip else self.by_hand).setChecked(True)
        hand = QFormLayout()
        self.system = QLineEdit()
        self.department = QLineEdit()
        self.channel = QLineEdit()
        self.frequency = QLineEdit()
        self.frequency.setPlaceholderText('MHz, e.g. 155.250')
        self.modulation = QComboBox()
        self.modulation.addItems(hand_entry.MODULATIONS)
        self.tone = QLineEdit()
        self.tone.setPlaceholderText('optional: 107.2, 023 DPL, NAC 293, CC 1')
        for label, widget in (('System name', self.system), ('Department', self.department),
                              ('First channel', self.channel), ('Frequency', self.frequency),
                              ('Modulation', self.modulation), ('Tone / NAC / colour code', self.tone)):
            hand.addRow(label, widget)
        layout.addLayout(hand)
        self.by_hand.toggled.connect(self._hand_fields)
        self._hand_fields(self.by_hand.isChecked())
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _hand_fields(self, on):
        for widget in (self.system, self.department, self.channel, self.frequency, self.modulation, self.tone):
            widget.setEnabled(on)

    def choice(self):
        if self.by_hand.isChecked():
            return 'hand'
        return 'database' if self.from_database.isChecked() else 'clipboard'

    def hand_records(self):
        item = hand_entry.channel(self.channel.text(), self.frequency.text(), self.modulation.currentText(),
                                  self.tone.text())
        return hand_entry.new_list_records(self.system.text(), self.department.text(), [item])


class ReorderDialog(QDialog):
    def __init__(self, parent, lists):
        super().__init__(parent)
        self.setWindowTitle('Reorder Favorites Lists')
        self.resize(480, 560)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Drag the lists, or use Up and Down. The scanner shows them in this order.'))
        row = QHBoxLayout()
        self.view = QListWidget()
        self.view.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        for item in lists:
            entry = QListWidgetItem(item['name'])
            entry.setData(Qt.ItemDataRole.UserRole, item['filename'])
            self.view.addItem(entry)
        row.addWidget(self.view, 1)
        side = QVBoxLayout()
        for label, step in (('Up', -1), ('Down', 1)):
            button = QPushButton(label)
            button.clicked.connect(lambda _c=False, s=step: self.move_selected(s))
            side.addWidget(button)
        side.addStretch(1)
        row.addLayout(side)
        layout.addLayout(row, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def move_selected(self, step):
        row = self.view.currentRow()
        target = row + step
        if row < 0 or not 0 <= target < self.view.count():
            return
        item = self.view.takeItem(row)
        self.view.insertItem(target, item)
        self.view.setCurrentRow(target)

    def order(self):
        return [self.view.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.view.count())]


class ManageMixin:
    # ---- the open configuration -----------------------------------------------------------------
    def _config_folder(self, title):
        folder = getattr(self, 'active_scanner_configuration', None)
        if folder is None:
            QMessageBox.information(self, title, 'Open a scanner configuration first (File → Open Scanner '
                                    'Configuration…, or File → New Scanner Configuration…).')
            return None
        return Path(folder).resolve()

    def _list_drafts(self):
        """{draft name: entries} for the lists of the open configuration."""
        folder = getattr(self, 'active_scanner_configuration', None)
        found = {}
        if folder is None:
            return found
        base = Path(folder).resolve() / 'BCDx36HP' / 'favorites_lists'
        for name, entries in self.workspace.drafts.items():
            source = entries[0].get('source_path') if entries else None
            if source and Path(source).resolve().is_relative_to(base):
                found[name] = entries
        return found

    def _modified_list_names(self):
        from native_favorites_export import build_native_bytes
        changed = []
        for name, entries in self._list_drafts().items():
            try:
                if build_native_bytes(entries)[0] != Path(entries[0]['source_path']).read_bytes():
                    changed.append(name)
            except (OSError, ValueError, KeyError, TypeError, UnicodeError):
                changed.append(name)
        return changed

    def _draft_for(self, relative):
        target = (Path(self.active_scanner_configuration) / relative).resolve()
        return next((n for n, e in self._list_drafts().items() if Path(e[0]['source_path']).resolve() == target), None)

    def _ask_unsaved(self, title):
        """True to go on: nothing unsaved, or saved, or the user chose to discard."""
        changed = self._modified_list_names()
        if not changed:
            return True
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText('These Favorites Lists have changes that are not saved:\n\n  ' + '\n  '.join(changed[:12]))
        box.setInformativeText('Save them to the configuration first?')
        save = box.addButton('Save', QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton('Discard Changes', QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is save:
            self.save_draft_to_configuration()
            return not self._modified_list_names()
        return box.clickedButton() is discard

    def _clear_lists(self):
        workspace = self.workspace
        workspace.drafts = {}
        workspace.current_draft = None
        workspace.native_readonly_files = []
        workspace._undo, workspace._redo = [], []
        workspace.draft_choice.blockSignals(True)
        workspace.draft_choice.clear()
        workspace.draft_choice.blockSignals(False)
        workspace.refresh_draft()

    def _open_configuration(self, path, manifest, check_unsaved=True):
        """Make path the open configuration and load its lists, in the scanner's order."""
        from scanner_configurations import verify_configuration
        if check_unsaved and not self._ask_unsaved('Open Scanner Configuration'):
            return False
        verify_configuration(path, manifest)
        self._clear_lists()
        self.active_scanner_configuration = Path(path)
        loaded = []
        for item in tasks.lists_in_order(path):
            before = set(self.workspace.drafts)
            self.workspace.create_editable_native_copy(str(Path(path) / item['relative']))
            loaded.extend(set(self.workspace.drafts) - before)
        self.workspace._undo, self.workspace._redo = [], []
        if loaded:
            first = tasks.lists_in_order(path)[0]
            self.workspace.draft_choice.setCurrentIndex(0)
            self._active_working_name = self.workspace.draft_choice.currentText()
            self._active_working_source = str(Path(path) / first['relative'])
        heading = getattr(self.workspace, 'lists_heading', None)
        if heading is not None:
            heading.setText(f'FAVORITES LISTS — {manifest.get("name", Path(path).name)} ({len(loaded)})')
        self._refresh_configuration_label()
        self.statusBar().showMessage(f'Configuration {manifest.get("name", "")}: {len(loaded)} Favorites Lists. '
                                     'Save Configuration keeps changes; Export to Scanner sends them.')
        self.repair_trunk_numbers()
        return True

    def _show_new_list(self, path):
        before = set(self.workspace.drafts)
        self.workspace.create_editable_native_copy(str(path))
        created = set(self.workspace.drafts) - before
        self._refresh_configuration_label()
        return created.pop() if created else None

    def _choose_list(self, title, prompt):
        folder = self._config_folder(title)
        if folder is None:
            return None, None
        lists = tasks.lists_in_order(folder)
        if not lists:
            QMessageBox.information(self, title, 'This configuration has no Favorites Lists yet.')
            return folder, None
        current = self.workspace.current_draft
        labels = [l['name'] for l in lists]
        start = labels.index(current) if current in labels else 0
        choice, ok = QInputDialog.getItem(self, title, prompt, labels, start, False)
        if not ok:
            return folder, None
        return folder, lists[labels.index(choice)]

    def _needs_saved(self, folder, item, title):
        """Copies are made from the saved list; offer to save first if it has changes."""
        name = self._draft_for(item['relative'])
        if name in self._modified_list_names():
            if QMessageBox.question(self, title, f'{item["name"]} has unsaved changes. Save the configuration '
                                    'first so the copy includes them?', YES | NO, YES) == YES:
                self.save_draft_to_configuration()
        return True

    # ---- File menu --------------------------------------------------------------------------------
    def new_scanner_configuration(self):
        from scanner_configurations import list_configurations
        title = 'New Scanner Configuration'
        configs = list_configurations()
        if not configs:
            QMessageBox.information(self, title, 'A new configuration takes its scanner settings from an '
                                    'existing one. Import from Scanner… first.')
            return
        labels = [m['name'] for _p, m in configs]
        active = getattr(self, 'active_scanner_configuration', None)
        start = next((i for i, (p, _m) in enumerate(configs) if active and p.resolve() == Path(active).resolve()), 0)
        source, ok = QInputDialog.getItem(self, title, 'Take the scanner settings (GPS, display, service types, '
                                          'search, alerts ...) from:', labels, start, False)
        if not ok:
            return
        folder, manifest = configs[labels.index(source)]
        name, ok = QInputDialog.getText(self, title, 'Name of the new configuration:', text=source + ' — new')
        if not ok or not name.strip():
            return
        if QMessageBox.question(self, title,
                f'Create {name.strip()!r} with the settings of {source} and no Favorites Lists?\n\n'
                'Add lists with Favorites → New Favorites List…, Import, or Copy from another configuration.\n\n'
                'Exporting it to the scanner it came from removes that scanner\'s current Favorites Lists '
                '(the export backs up the scanner first).', YES | NO, YES) != YES:
            return
        if not self._ask_unsaved(title):
            return
        try:
            root, created = tasks.new_configuration(folder, name)
            self._open_configuration(root, created, check_unsaved=False)
        except (OSError, ValueError, FileExistsError) as exc:
            QMessageBox.warning(self, title, str(exc))

    # ---- Favorites menu ---------------------------------------------------------------------------
    def new_favorites_list(self):
        title = 'New Favorites List'
        folder = self._config_folder(title)
        if folder is None:
            return
        section = self.workspace.selected_section()
        clip = getattr(self.workspace, 'favorites_clipboard', None)
        dialog = NewListDialog(self, section['name'] if section else '', clip)
        while True:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            name = dialog.name.text().strip()
            try:
                hooks = self.workspace.new_list_hooks
                hooks['check'](name)
                choice = dialog.choice()
                if choice == 'database':
                    self.workspace._add_to_new_list(section, name)
                    return
                if choice == 'clipboard':
                    hooks['create_native'](name, clipboard.new_list_rows(clip), clip.get('encoding', 'cp1252'))
                    if clip.get('cut'):
                        self.workspace.favorites_clipboard = None
                else:
                    hooks['create'](name, dialog.hand_records())
                self.statusBar().showMessage(f'Created Favorites List {name}. Export to Scanner sends it.')
                return
            except (ValueError, OSError) as exc:
                QMessageBox.warning(self, title, str(exc))

    def duplicate_favorites_list(self):
        title = 'Duplicate Favorites List'
        folder, item = self._choose_list(title, 'Duplicate which Favorites List?')
        if item is None:
            return
        self._needs_saved(folder, item, title)
        name, ok = QInputDialog.getText(self, title, 'Name of the copy:', text=tasks.free_name(folder, item['name']))
        if not ok or not name.strip():
            return
        try:
            result = tasks.duplicate_list(folder, item['relative'], name)
            self._show_new_list(result['path'])
            self.statusBar().showMessage(f'Duplicated {item["name"]} as {name.strip()}. Its quick key, number tag '
                                         'and startup keys start Off.')
        except (OSError, ValueError, FileExistsError) as exc:
            QMessageBox.warning(self, title, str(exc))

    def copy_list_to_configuration(self):
        from scanner_configurations import list_configurations
        title = 'Copy Favorites List to Another Configuration'
        folder, item = self._choose_list(title, 'Copy which Favorites List?')
        if item is None:
            return
        others = [(p, m) for p, m in list_configurations() if p.resolve() != folder]
        if not others:
            QMessageBox.information(self, title, 'There is no other configuration. File → New Scanner '
                                    'Configuration… makes one.')
            return
        labels = [m['name'] for _p, m in others]
        target, ok = QInputDialog.getItem(self, title, f'Copy {item["name"]} to:', labels, 0, False)
        if not ok:
            return
        self._needs_saved(folder, item, title)
        target_folder = others[labels.index(target)][0]
        try:
            name = tasks.free_name(target_folder, item['name'])
            tasks.duplicate_list(folder, item['relative'], name, target=target_folder)
            QMessageBox.information(self, title, f'Copied {item["name"]} to {target} as {name}.')
        except (OSError, ValueError, FileExistsError) as exc:
            QMessageBox.warning(self, title, str(exc))

    def import_favorites_list_file(self):
        from favorites_manager import FavoritesManager
        title = 'Import Favorites List File'
        folder = self._config_folder(title)
        if folder is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, title, str(Path.home()), 'SDS100 Favorites List (*.hpd)')
        if not path:
            return
        path = Path(path)
        suggested = FavoritesManager.favorites_names(path.parent).get(path.name.casefold()) or path.stem
        name, ok = QInputDialog.getText(self, title, 'Name of the list in this configuration:',
                                        text=tasks.free_name(folder, suggested))
        if not ok or not name.strip():
            return
        try:
            result = tasks.import_list_file(folder, path, name)
            self._show_new_list(result['path'])
            self.statusBar().showMessage(f'Imported {path.name} as {name.strip()}.')
        except (OSError, ValueError, FileExistsError, UnicodeError) as exc:
            QMessageBox.warning(self, title, str(exc))

    def reorder_favorites_lists(self):
        title = 'Reorder Favorites Lists'
        folder = self._config_folder(title)
        if folder is None:
            return
        lists = tasks.lists_in_order(folder)
        if len(lists) < 2:
            QMessageBox.information(self, title, 'There is nothing to reorder.')
            return
        dialog = ReorderDialog(self, lists)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            if not tasks.reorder_lists(folder, dialog.order()):
                return
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, title, str(exc))
            return
        combo = self.workspace.draft_choice
        current = combo.currentText()
        names = [self._draft_for(item['relative']) for item in tasks.lists_in_order(folder)]
        combo.blockSignals(True)
        combo.clear()
        combo.addItems([n for n in names if n])
        combo.setCurrentText(current)
        combo.blockSignals(False)
        self._refresh_configuration_label()
        self.statusBar().showMessage('Favorites Lists reordered. Export to Scanner sends the new order.')

    def edit_favorites_list(self):
        if self._config_folder('Edit Favorites List') is None:
            return
        if not self.workspace.current_draft:
            QMessageBox.information(self, 'Edit Favorites List', 'Choose a Favorites List first.')
            return
        self.workspace.open_favorites_editor()

    # ---- Keys & Tags (v0.1.8) ------------------------------------------------------------------------
    def keys_entries(self):
        """{list filename: its entries as they stand now, unsaved edits included}."""
        return {Path(e[0]['source_path']).name: e for e in self._list_drafts().values()}

    def open_keys_and_tags(self):
        from keys_window import KeysWindow
        folder = self._config_folder('Keys & Tags')
        if folder is None:
            return
        self.repair_trunk_numbers()
        try:
            KeysWindow(self, folder, self.keys_entries()).exec()
        except (OSError, ValueError, UnicodeError) as exc:
            QMessageBox.warning(self, 'Keys & Tags', str(exc))

    def apply_keys_model(self, model):
        """Put a Keys & Tags model's changes into the open configuration."""
        from location_settings import save_profile
        from quick_keys_settings import patch_quick_keys
        from scanner_configurations import save_local_flist_settings
        folder = self._config_folder('Keys & Tags')
        edits = model.flist_edits()
        if edits:
            save_local_flist_settings(folder, edits)
        if model.fl_status_changed():
            profile = (folder / 'BCDx36HP' / 'profile.cfg').read_bytes()
            save_profile(folder, patch_quick_keys(profile, model.status[('fl',)]))
        rows = model.row_edits()
        if rows:
            names = {Path(e[0]['source_path']).name: n for n, e in self._list_drafts().items()}
            self.workspace._snapshot()
            for filename, ei, ri, column, value in rows:
                record = self.workspace.drafts[names[filename]][ei]['records'][ri]
                record[column] = value
            self.workspace.refresh_draft()
            if QMessageBox.question(self, 'Keys & Tags', 'Systems, departments and channels were changed in the '
                                    'Favorites Lists. Save the configuration now?', YES | NO, YES) == YES:
                self.save_draft_to_configuration()
        self._refresh_configuration_label()
        self.statusBar().showMessage('Keys & Tags applied. Export to Scanner sends them.')

    def repair_trunk_numbers(self, ask=True):
        """Versions 0.1.8–0.1.16 put trunked systems' quick keys and number tags into their ID Search and
        Alert Tone columns. Find those and move them where they belong (v0.1.17). Returns the fixes made."""
        import copy
        from keys_model import misplaced_numbers, repair_row
        found = []
        for name, entries in self._list_drafts().items():
            for entry in entries[1:]:
                records = entry.get('records') or []
                if records and misplaced_numbers(records[0]) is not None:
                    found.append((name, records[0]))
        if not found:
            return []
        lines = [repair_row(copy.deepcopy(row)) + f'  [{name}]' for name, row in found]
        if ask and QMessageBox.question(
                self, 'Repair trunked systems',
                'SDS-Manager 0.1.8 to 0.1.16 put the quick key and number tag of trunked systems in the wrong '
                'columns (ID Search and Alert Tone), so the scanner never saw them. These systems have numbers '
                'there:\n\n  ' + '\n  '.join(lines[:20]) + (f'\n  … and {len(lines) - 20} more' if len(lines) > 20 else '')
                + '\n\nMove them to the quick key and number tag, and set ID Search and Alert Tone back to Off? '
                '(If you set an emergency Alert Tone yourself on one of these, set it again afterwards.)',
                YES | NO, YES) != YES:
            return []
        self.workspace._snapshot()
        fixes = [repair_row(row) for _name, row in found]
        self.workspace.refresh_draft()
        self._refresh_configuration_label()
        if ask and QMessageBox.question(self, 'Repair trunked systems', f'{len(fixes)} system(s) repaired. Save the '
                                        'configuration now? (Then Export to Scanner to fix the scanner too.)',
                                        YES | NO, YES) == YES:
            self.save_draft_to_configuration()
        return fixes

