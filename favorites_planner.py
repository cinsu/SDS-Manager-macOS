# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Favorites List editing with Undo and Redo, on top of the database workspace."""
import copy
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton, QMessageBox, QInputDialog, QTreeWidgetItem
from database_workspace import DatabaseWorkspace, build_sections, read_hpd_records
from database_workspace import record_columns
import undo_stack

ROLE = Qt.ItemDataRole.UserRole

class FavoritesPlanner(DatabaseWorkspace):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('FavoritesPlannerV15')
        self._undo = []
        self._redo = []
        self._install_actions()

    def _install_actions(self):
        layout = self.layout()
        buttons = self.findChildren(QPushButton)
        for button in buttons:
            if button.text() == '→ Add selected system to Favorites draft':
                button.setText('→ Add selected item to Favorites draft')
            elif button.text() == 'Delete selected system from draft':
                button.setText('Remove selected draft item')
        row = layout.itemAt(0).layout()
        for name, fn in [('Undo change', self.undo_change),
                         ('Redo change', self.redo_change)]:
            button = QPushButton(name)
            button.clicked.connect(fn)
            row.addWidget(button)

    def _snapshot(self):
        self._undo.append((copy.deepcopy(self.drafts), self.current_draft))
        self._undo = self._undo[-40:]
        self._redo.clear()

    def _restore(self, state):
        self.drafts, self.current_draft = copy.deepcopy(state[0]), state[1]
        self.draft_choice.blockSignals(True)
        self.draft_choice.clear()
        self.draft_choice.addItems(self.drafts.keys())
        if self.current_draft:
            self.draft_choice.setCurrentText(self.current_draft)
        self.draft_choice.blockSignals(False)
        self.refresh_draft()

    def undo_change(self):
        if self._undo:
            self._redo.append((copy.deepcopy(self.drafts), self.current_draft))
            self._restore(self._undo.pop())

    def redo_change(self):
        if self._redo:
            self._undo.append((copy.deepcopy(self.drafts), self.current_draft))
            self._restore(self._redo.pop())

    def undo_all_changes(self):
        """Step back through every remembered change at once; Redo then replays them one by one."""
        if not self._undo:
            QMessageBox.information(self, 'Undo All Changes', 'There are no changes to undo.')
            return False
        steps = len(self._undo)
        if QMessageBox.question(
                self, 'Undo All Changes',
                f'Undo all {steps} remembered change(s) to the open Favorites Lists?\n\n'
                'Redo can bring them back one step at a time. Nothing is written to the scanner either way.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return False
        current = (copy.deepcopy(self.drafts), self.current_draft)
        restore, self._undo, self._redo = undo_stack.rewind_all(self._undo, self._redo, current)
        self._restore(restore)
        self.status.setText(f'Undid {steps} change(s). Redo restores them one step at a time.')
        return True

    def expand_db_item(self, item):
        super().expand_db_item(item)
        data = item.data(0,ROLE)
        if not isinstance(data,tuple) or data[0]!='file' or data[1] not in self.db_index:
            return
        for i in range(item.childCount()):
            system_node = item.child(i)
            sdata=system_node.data(0,ROLE)
            if not isinstance(sdata,tuple) or sdata[0]!='system':
                continue
            section=self.db_index[sdata[1]][sdata[2]]
            for j, group in enumerate(section['children']):
                if j >= system_node.childCount():
                    break
                group_node=system_node.child(j)
                group_node.setData(0,ROLE,('group',sdata[1],sdata[2],j))
                if group_node.childCount():
                    continue
                for k, record in enumerate(group['records'][1:],1):
                    if record and record[0] in ('C-Freq','T-Freq','TGID','C-Channel','T-Channel','C-Frequency','T-Frequency','Tgid','T-Id'):
                        label = record[3] if len(record)>3 and record[3] else (record[1] if len(record)>1 else record[0])
                        leaf=QTreeWidgetItem(group_node,record_columns(record))
                        leaf.setData(0,ROLE,('record',sdata[1],sdata[2],j,k))

    def _resolve(self,node):
        while node:
            data=node.data(0,ROLE)
            if isinstance(data,tuple) and data[0] in ('system','group','record'):
                source,idx=data[1],data[2]
                return self.db_index[source][idx],source,idx,data
            if isinstance(data,tuple) and data[0]=='search_hit':
                section=self.get_indexed_system(data[1],data[2])
                return section,str(Path(self.source)/data[1]),data[2],data
            node=node.parent()
        return None,None,None,None

    def add_selected(self):
        if not self.current_draft:
            QMessageBox.information(self,'Create list','Create a Favorites draft first.')
            return
        chosen_system = self.system_choice.currentData()
        if chosen_system:
            source, idx = chosen_system
            if source not in self.db_index:
                QMessageBox.information(self, 'Still loading',
                                        'This system is still loading from RadioReference. Try again in a moment.')
                return
            section = self.db_index[source][idx]
            data = ('system', source, idx)
        else:
            section,source,idx,data=self._resolve(self.db_tree.currentItem())
        if not section:
            QMessageBox.information(self,'Select an item','Select a system, department, or channel.')
            return
        # Single selection path for both conventional and trunked systems.
        # DatabaseWorkspace owns the checkbox dialogs and selective serialization.
        # Never fall back to the legacy whole-system/direct-copy routine.
        self._snapshot()
        return super().add_selected((source, idx))

    def refresh_draft(self):
        super().refresh_draft()
        for i,entry in enumerate(self.drafts.get(self.current_draft,[])):
            # Loaded favorites appear as one root; drafts follow it.
            offset=1 if self.favorites_files else 0
            node=self.draft_tree.topLevelItem(i+offset)
            if node:
                node.setText(1,entry.get('scope','system').capitalize())
                node.setToolTip(0,'Parent system: '+entry.get('parent_system',entry['name']))

    def delete_selected(self):
        """Remove only the selected draft node; never promote a leaf to its system."""
        node = self.draft_tree.currentItem()
        if node is None or not self.current_draft:
            return
        root = node
        while root.parent() is not None:
            root = root.parent()
        index = root.data(0, ROLE)
        entries = self.drafts.get(self.current_draft, [])
        if not isinstance(index, int) or not 0 <= index < len(entries):
            QMessageBox.information(self, 'Read-only list', 'Select an item in an offline draft.')
            return
        entry = entries[index]
        if node is root:
            label = entry.get('name', 'system')
            message = f'Remove the entire system {label} and all its contents from this draft?'
            operation = ('system', None, None)
        else:
            records = entry.get('records', [])
            parent = node.parent()
            if parent is root:
                # Group/site nodes are generated in record order from the draft.
                group_number = root.indexOfChild(node)
                group_positions = [i for i, row in enumerate(records) if row and row[0].strip() in ('C-Group', 'T-Group', 'Site')]
                node_data = node.data(0, ROLE)
                if isinstance(node_data, tuple) and node_data[0] == 'draft_row':
                    start = node_data[1]
                elif group_number < len(group_positions):
                    start = group_positions[group_number]
                else:
                    return
                end = next((i for i in group_positions if i > start), len(records))
                operation = ('group', start, end)
                message = f'Remove {node.text(0)} and its contents from this draft?'
            elif parent.parent() is root:
                group_number = root.indexOfChild(parent)
                group_positions = [i for i, row in enumerate(records) if row and row[0].strip() in ('C-Group', 'T-Group', 'Site')]
                node_data = parent.data(0, ROLE)
                if isinstance(node_data, tuple) and node_data[0] == 'draft_row':
                    start = node_data[1]
                elif group_number < len(group_positions):
                    start = group_positions[group_number]
                else:
                    return
                end = next((i for i in group_positions if i > start), len(records))
                # The visible leaf sequence corresponds to leaf records in the group.
                leaf_positions = [i for i in range(start + 1, end) if records[i] and records[i][0].strip() in ('C-Freq','C-Channel','C-Frequency','T-Freq','T-Channel','TGID','Tgid','T-Id')]
                leaf_number = parent.indexOfChild(node)
                leaf_data = node.data(0, ROLE)
                if isinstance(leaf_data, tuple) and leaf_data[0] == 'draft_row':
                    leaf_index = leaf_data[1]
                elif leaf_number < len(leaf_positions):
                    leaf_index = leaf_positions[leaf_number]
                else:
                    return
                operation = ('leaf', leaf_index, None)
                message = f'Remove only {node.text(0)} from this draft?'
            else:
                return
        # A trunked system with talkgroups cannot remain without a site.
        # Removing its final site therefore removes the complete system.
        if operation[0] == 'group':
            records = entry.get('records', [])
            selected_row = records[operation[1]]
            if selected_row and selected_row[0].strip() == 'Site':
                site_count = sum(1 for row in records if row and row[0].strip() == 'Site')
                if site_count == 1:
                    operation = ('system', None, None)
                    message = (f'This is the last site in {entry.get("name", "this trunked system")}. '
                               'Removing it will delete the entire trunked system, '
                               'including all talkgroups. Continue?')
        if QMessageBox.question(self, 'Remove from draft', message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self._snapshot()
        kind, start, end = operation
        if kind == 'system':
            del entries[index]
        elif kind == 'group':
            del entry['records'][start:end]
        else:
            del entry['records'][start]
        if kind != 'system':
            entry['selected_sites'] = [r[3] for r in entry['records'] if r and r[0].strip() == 'Site' and len(r)>3]
            entry['selected_departments'] = [r[3] for r in entry['records'] if r and r[0].strip() in ('C-Group','T-Group') and len(r)>3]
        self.refresh_draft()
        self.status.setText('Removed selected draft item only; other records preserved.')
