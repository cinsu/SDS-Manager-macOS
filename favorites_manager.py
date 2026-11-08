# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""The Favorites Lists of the open scanner configuration, loaded for editing."""
import hashlib
import re
from pathlib import Path

from keys_model import badge

KEYS_COLUMN = 6       # 'Keys / Tag' in the Favorites tree (v0.1.10)
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QMessageBox, QFileDialog,
                             QTreeWidgetItem, QPushButton, QMenu)
from favorites_planner import FavoritesPlanner
from database_workspace import record_columns, favorites_record_columns
from favorites_explorer import read_text

ROLE = Qt.ItemDataRole.UserRole

class FavoritesManager(FavoritesPlanner):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('FavoritesManagerV17')
        self.import_sources = {}
        self.native_readonly_files = []
        self._two_row_toolbar()
        self._editing_tree = False
        self.draft_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.draft_tree.customContextMenuRequested.connect(self._favorites_context_menu)
        self.status.setText('V17: Open all existing Favorites Lists to import each into an editable draft. '
                            'Select a draft and add database entries to it. Originals are never modified.')

    def _favorites_context_menu(self, point):
        if not self.current_draft or not self.drafts.get(self.current_draft):
            return
        menu = QMenu(self.draft_tree)
        action = menu.addAction('Edit Favorites List…')
        chosen = menu.exec(self.draft_tree.viewport().mapToGlobal(point))
        if chosen == action:
            self.open_favorites_editor()

    def open_favorites_editor(self):
        if not self.current_draft:
            return
        from favorites_settings_window import FavoritesSettingsDialog
        dialog = FavoritesSettingsDialog(self, self.current_draft)
        dialog.exec()

    def _two_row_toolbar(self):
        layout = self.layout()
        original = layout.itemAt(0).layout()
        buttons=[]
        while original.count():
            item=original.takeAt(0)
            widget=item.widget()
            if widget is not None:
                buttons.append(widget)
        second=QHBoxLayout()
        layout.insertLayout(1,second)
        database_titles={'Open full database','Index entire database','Search ALL'}
        for button in buttons:
            (original if button.text() in database_titles else second).addWidget(button)
        original.insertWidget(0,QLabel('DATABASE:'))
        original.addStretch(1)
        second.addStretch(1)

    def _channel_record_for_item(self, item):
        if item is None or not self.current_draft:
            return None
        ref = item.data(0, ROLE)
        if not isinstance(ref, tuple) or len(ref) != 2 or ref[0] != 'draft_row':
            return None
        parent = item.parent()
        entry_index = None
        while parent is not None:
            value = parent.data(0, ROLE)
            if isinstance(value, int):
                entry_index = value
                break
            parent = parent.parent()
        entries = self.drafts.get(self.current_draft, [])
        if entry_index is None or not 0 <= entry_index < len(entries):
            return None
        entry = entries[entry_index]
        row_index = ref[1]
        rows = entry.get('records', [])
        if (entry.get('kind') != 'Conventional' or not isinstance(row_index, int)
                or not 0 <= row_index < len(rows)):
            return None
        row = rows[row_index]
        if not row or row[0] != 'C-Freq' or len(row) <= 3:
            return None
        return row

    def _begin_inline_channel_edit(self, item, column):
        if column != 0 or self._channel_record_for_item(item) is None:
            return
        self._editing_tree = True
        try:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.draft_tree.editItem(item, 0)
        finally:
            self._editing_tree = False

    def _commit_inline_channel_edit(self, item, column):
        if self._editing_tree or column != 0:
            return
        row = self._channel_record_for_item(item)
        if row is None:
            return
        old = row[3]
        name = item.text(0).strip()
        if name == old:
            return
        if not name or len(name) > 64 or any(ch in name for ch in '\t\r\n\x00'):
            QMessageBox.warning(self, 'Invalid channel name',
                                'Enter a nonempty name of up to 64 characters without tabs or line breaks.')
            self._restore_channel_label(item, old)
            return
        entries = self.drafts.get(self.current_draft, [])
        meta = entries[0] if entries and entries[0].get('scope') == 'metadata' else {}
        encoding = meta.get('encoding', 'cp1252')
        try:
            name.encode(encoding)
        except (UnicodeError, LookupError):
            QMessageBox.warning(self, 'Unsupported characters',
                                'The channel name cannot be represented in this Favorites List encoding.')
            self._restore_channel_label(item, old)
            return
        answer = QMessageBox.question(
            self, 'Confirm channel name change',
            f'Change this conventional channel name?\n\nCurrent name: {old}\nNew name: {name}',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            self._restore_channel_label(item, old)
            self.status.setText('Channel name change canceled; original value preserved.')
            return
        self._snapshot()
        row[3] = name
        self.status.setText(f'Channel renamed to {name}. Save the local scanner configuration to keep the change.')

    def _restore_channel_label(self, item, name):
        self._editing_tree = True
        try:
            item.setText(0, name)
        finally:
            self._editing_tree = False

    @staticmethod
    def favorites_names(directory):
        """Map .hpd filenames to display names using f_list.cfg, read-only."""
        candidates = [directory / 'f_list.cfg', directory.parent / 'f_list.cfg',
                      directory.parent.parent / 'f_list.cfg']
        config = next((candidate for candidate in candidates if candidate.is_file()), None)
        if config is None:
            return {}
        raw = config.read_bytes()
        content = None
        for encoding in ('utf-8-sig', 'utf-16', 'cp1252', 'latin-1'):
            try:
                content = raw.decode(encoding)
                break
            except UnicodeError:
                pass
        if content is None:
            return {}
        names = {}
        for line in content.splitlines():
            fields = [field.strip().strip('"') for field in line.split('\t')]
            if not fields or fields[0].casefold() != 'f-list':
                continue
            # Accept numeric identifiers with one or more digits; locate the
            # actual filename field rather than assuming a fixed column.
            for index, field in enumerate(fields):
                match = re.search(r'(f_\d+\.hpd)\b', field, re.IGNORECASE)
                if not match:
                    continue
                filename = match.group(1).casefold()
                options = [value for j, value in enumerate(fields)
                           if j != index and j != 0 and value
                           and not re.fullmatch(r'\d+', value)
                           and not re.search(r'f_\d+\.hpd', value, re.IGNORECASE)]
                if options and filename not in names:
                    names[filename] = options[0]
                break
        return names

    def open_favorites_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'Open ALL existing Favorites Lists')
        if not folder: return
        base=Path(folder)
        dirs=[base/'BCDx36HP'/'favorites_lists',base/'favorites_lists',base]
        directory=next((p for p in dirs if p.is_dir() and any(p.glob('*.hpd'))),None)
        if directory is None:
            QMessageBox.warning(self,'No lists','No .hpd files found in that folder.'); return
        paths=sorted(directory.glob('*.hpd'))
        names=self.favorites_names(directory)
        if len(paths)>500:
            QMessageBox.warning(self,'Too many lists','Select a folder containing 500 or fewer lists.'); return
        staged=[]
        try:
            for path in paths:
                if path.stat().st_size>25*1024*1024:
                    raise ValueError(f'{path.name} exceeds the 25 MB per-file limit')
                text,encoding=read_text(path)
                rows=[line.split('\t') for line in text.splitlines()]
                systems=[]
                preamble=[]
                current=None
                for row in rows:
                    kind=row[0] if row else ''
                    if kind in ('Conventional','Trunk'):
                        name=row[3] if len(row)>3 else kind
                        current={'key':['import',str(path.resolve()),len(systems)],
                                 'name':name,'kind':kind,'scope':'system',
                                 'parent_system':name,'records':[],'origin':'existing'}
                        systems.append(current)
                    if current is None:
                        preamble.append(row)
                    else:
                        current['records'].append(row)
                staged.append((path,systems,preamble,encoding,
                               '\r\n' if '\r\n' in text else '\r' if '\r' in text else '\n',
                               text.endswith(('\n','\r')),
                               hashlib.sha256(path.read_bytes()).hexdigest()))
        except (OSError,ValueError,UnicodeError) as exc:
            QMessageBox.warning(self,'Unable to import lists',str(exc)); return
        duplicates=[p.name for p,*_ in staged if any(e.get('source_path')==str(p.resolve())
                        for entries in self.drafts.values() for e in entries)]
        if duplicates:
            QMessageBox.information(self,'Previously imported',
                'Already imported source files will be skipped to avoid duplicate drafts.')
        imported=[]
        self._snapshot()
        for path,systems,preamble,encoding,newline,final_newline,digest in staged:
            source=str(path.resolve())
            if any(e.get('source_path')==source for entries in self.drafts.values() for e in entries):
                continue
            name=names.get(path.name.casefold(), path.stem)
            if name in self.drafts:
                counter=2
                while f'{name} ({counter})' in self.drafts: counter+=1
                name=f'{name} ({counter})'
            # A metadata record preserves pre-system header lines in JSON drafts.
            # It is NOT scanner programming and is never exported to .hpd.
            meta={'key':['import-meta',source], 'name':'Original file metadata',
                  'kind':'Metadata','scope':'metadata','records':preamble,
                  'source_path':source,'encoding':encoding,'newline':newline,
                  'final_newline':final_newline,'source_sha256':digest}
            self.drafts[name]=[meta]+systems
            self.draft_choice.addItem(name)
            imported.append(name)
        if imported:
            self.draft_choice.setCurrentText(imported[0])
        self.refresh_draft()
        self.status.setText(f'Imported {len(imported)} existing Favorites Lists into draft workspace '
                            'Choose a list above, then add database entries. Save as JSON draft only.')

    def add_native_readonly_file(self, path):
        """Register an inspected native file; never copy it into editable drafts."""
        from native_favorites_reader import parse_native_favorites
        path = Path(path).resolve()
        parsed = parse_native_favorites(path)
        if str(path) not in self.native_readonly_files:
            self.native_readonly_files.append(str(path))
        self.refresh_draft()
        self.status.setText(f'Opened native Favorites read-only: {path.name} — {len(parsed["systems"])} systems.')
        return parsed

    def create_editable_native_copy(self, native_path=None):
        """Copy the selected native file into a new JSON-only editable draft.

        Original bytes are only read. Keep every tab-separated record verbatim
        in the draft model, including preamble and unrecognized record types.
        """
        selected = self.draft_tree.currentItem()
        filename = None
        while selected is not None:
            value = selected.data(0, ROLE)
            if isinstance(value, tuple) and len(value) == 2 and value[0] == 'native_file':
                filename = value[1]
                break
            selected = selected.parent()
        if native_path is not None:
            filename = str(Path(native_path).resolve())
        if filename is None:
            QMessageBox.information(self, 'Select native Favorites',
                'Select a file or item under Native Favorites (read-only) first.')
            return
        path = Path(filename)
        from favorites_explorer import read_text
        import hashlib
        try:
            if path.stat().st_size > 25 * 1024 * 1024:
                raise ValueError('Native Favorites file exceeds the 25 MB limit')
            data = path.read_bytes()
            text, encoding = read_text(path)
            rows = [line.split('\t') for line in text.splitlines()]
            systems, preamble, current = [], [], None
            for row in rows:
                kind = row[0].strip() if row else ''
                if kind in ('Conventional', 'Trunk'):
                    name = row[3] if len(row) > 3 else kind
                    current = {'key': ['native-copy', str(path), len(systems)],
                               'name': name, 'kind': kind, 'scope': 'system',
                               'parent_system': name, 'records': [], 'origin': 'native-copy'}
                    systems.append(current)
                if current is None:
                    preamble.append(row)
                else:
                    current['records'].append(row)
            if not systems:
                raise ValueError('No conventional or trunked systems found')
        except (OSError, ValueError, UnicodeError) as exc:
            QMessageBox.warning(self, 'Cannot copy native Favorites', str(exc))
            return
        display_names = self.favorites_names(path.parent)
        name = display_names.get(path.name.casefold(), 'Unnamed Favorites List')
        if name in self.drafts:
            suffix = 2
            while f'{name} {suffix}' in self.drafts:
                suffix += 1
            name = f'{name} {suffix}'
        metadata = {'key': ['native-copy-meta', str(path)],
                    'name': 'Original file metadata', 'kind': 'Metadata',
                    'scope': 'metadata', 'records': preamble,
                    'source_path': str(path), 'encoding': encoding,
                    'newline': '\r\n' if '\r\n' in text else '\r' if '\r' in text else '\n',
                    'final_newline': text.endswith(('\r', '\n')),
                    'source_sha256': hashlib.sha256(data).hexdigest()}
        self._snapshot()
        self.drafts[name] = [metadata] + systems
        self.draft_choice.addItem(name)
        self.draft_choice.setCurrentText(name)
        self.refresh_draft()
        self.status.setText(f'Opened Favorites List {name}. Save Configuration keeps your changes.')

    def refresh_draft(self):
        """Show source fields in sortable columns while preserving deletion row IDs."""
        self.draft_tree.setSortingEnabled(False)
        self.draft_tree.blockSignals(True)
        self.draft_tree.clear()
        if self.native_readonly_files:
            from native_favorites_reader import parse_native_favorites, record_columns as native_columns
            native_root = QTreeWidgetItem(self.draft_tree, ['Native Favorites (read-only)', 'Read-only', '', '', '', ''])
            native_root.setToolTip(0, 'Original .hpd files are never modified here.')
            for filename in self.native_readonly_files:
                try:
                    parsed = parse_native_favorites(filename)
                except (OSError, UnicodeError, ValueError) as exc:
                    QTreeWidgetItem(native_root, [Path(filename).name + ': ' + str(exc), 'Error', '', '', '', ''])
                    continue
                file_node = QTreeWidgetItem(native_root, [Path(filename).name, 'Native .hpd', '', '', '', ''])
                file_node.setData(0, ROLE, ('native_file', filename))
                file_node.setToolTip(0, filename + ' — READ-ONLY')
                for system in parsed['systems']:
                    system_node = QTreeWidgetItem(file_node, [system['name'], system['kind'], '', '', '', ''])
                    for group in system['groups']:
                        group_node = QTreeWidgetItem(system_node, [group['name'], group['kind'], '', '', '', ''])
                        for row in group['leaves']:
                            QTreeWidgetItem(group_node, favorites_record_columns(row))
                if parsed['warnings']:
                    file_node.setToolTip(0, filename + ' — READ-ONLY; ' + '; '.join(parsed['warnings'][:3]))
        for index, entry in enumerate(self.drafts.get(self.current_draft, [])):
            if entry.get('scope') == 'metadata':
                continue
            item = QTreeWidgetItem([entry.get('name', '(unnamed)'),
                                    entry.get('kind', entry.get('scope', 'system')).capitalize(), '', '', '', ''])
            item.setData(0, ROLE, index)
            records = entry.get('records') or []
            if records:
                item.setText(KEYS_COLUMN, badge(records[0]))
            self.draft_tree.addTopLevelItem(item)
            current_group = None
            for row_index, row in enumerate(entry.get('records', [])):
                if not row: continue
                kind = row[0].strip()
                if kind in ('Conventional', 'Trunk'): continue
                if kind in ('C-Group', 'T-Group', 'Site'):
                    current_group = QTreeWidgetItem(item, [row[3] if len(row)>3 and row[3] else kind,
                                                           kind, '', '', '', ''])
                    current_group.setData(0, ROLE, ('draft_row', row_index))
                    current_group.setText(KEYS_COLUMN, badge(row))
                elif kind in ('C-Freq','T-Freq','TGID','C-Channel','T-Channel',
                              'C-Frequency','T-Frequency','Tgid','T-Id'):
                    leaf = QTreeWidgetItem(current_group or item, favorites_record_columns(row))
                    leaf.setData(0, ROLE, ('draft_row', row_index))
                    leaf.setText(KEYS_COLUMN, badge(row))
            item.setToolTip(0, 'Select a department or channel to remove only that item.')
        self.draft_tree.setSortingEnabled(True)
        self.draft_tree.blockSignals(False)

    def delete_selected(self):
        """Use the hierarchy-aware deletion implementation in FavoritesPlanner.

        The former FavoritesManager override promoted every selected tree node
        to the system root, unintentionally deleting the entire system.
        """
        return super().delete_selected()

