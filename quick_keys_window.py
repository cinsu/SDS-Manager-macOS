# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Favorites → Quick Keys… (v0.1.6): what every quick key is assigned to, at all three levels.

Replaces the bare 00-99 grid of Quick Keys Status. One tree shows each Favorites List with its quick key,
its systems with theirs and their departments with theirs, and whether the scanner scans them. The
Favorites List and system key statuses can be switched here; department keys are shown read-only.
Reads the configuration as last saved."""
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel,
                             QMessageBox, QScrollArea, QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                             QWidget)

import flist_settings as fls
import quick_key_map as qk

ROLE = Qt.ItemDataRole.UserRole
DIM = QColor('#8a8f98')
WARN = QColor('#ff9e91')

INTRO = ('<b>Quick keys switch scanning on and off in groups.</b> There are three sets, each numbered 00–99:'
         '<ul style="margin:2px">'
         '<li><b>Favorites List keys</b> switch whole Favorites Lists (one set for the scanner).</li>'
         '<li><b>System keys</b> switch systems inside one Favorites List (each list has its own set).</li>'
         '<li><b>Department keys</b> switch departments inside one system (each system has its own set).</li>'
         '</ul>'
         'Each item below shows the key it is assigned to and whether that key is On. Tick or untick a '
         'Favorites List or system key to switch it; every item using the same key follows. Items with no '
         'key are never switched by a key. Shown as last saved in the configuration.')


def load(folder):
    """Everything the window shows, read from a local configuration folder."""
    from favorites_explorer import read_text
    from quick_keys_settings import read_quick_keys
    root = Path(folder) / 'BCDx36HP'
    profile = (root / 'profile.cfg').read_bytes()
    index = (root / 'favorites_lists' / 'f_list.cfg').read_bytes()
    lists = fls.read_lists(index)
    for item in lists:
        path = root / 'favorites_lists' / item['filename']
        try:
            text, _encoding = read_text(path)
            item['systems'] = qk.read_systems([line.split('\t') for line in text.splitlines()])
        except (OSError, ValueError, UnicodeError):
            item['systems'] = []
            item['unreadable'] = True
        item['key'] = qk.key_number(item['quick_key'])
    return profile, read_quick_keys(profile), index, lists


class QuickKeysWindow(QDialog):
    def __init__(self, parent, folder, manifest):
        super().__init__(parent)
        self.folder = folder
        self.profile, saved, self.index, self.lists = load(folder)
        self.fl_saved = list(saved)
        self.fl_status = list(saved)
        self.sys_saved = {l['filename']: [v == 'On' for v in l['system_keys']] for l in self.lists}
        self.sys_status = {k: list(v) for k, v in self.sys_saved.items()}
        self.fl_owners = qk.owners([{'name': l['name'], 'key': l['key']} for l in self.lists])
        self._loading = False
        self.setWindowTitle('Quick Keys — ' + manifest.get('name', ''))
        self.resize(980, 720)
        layout = QVBoxLayout(self)
        intro = QLabel(INTRO)
        intro.setWordWrap(True)
        layout.addWidget(intro)
        tabs = QTabWidget(self)
        layout.addWidget(tabs, 1)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['Favorites List / System / Department', 'Quick key', 'Scanning'])
        self.tree.setColumnWidth(0, 430)
        self.tree.setColumnWidth(1, 140)
        self.tree.itemChanged.connect(self._tree_changed)
        tabs.addTab(self.tree, 'What each key switches')
        grid_page = QWidget()
        grid_layout = QVBoxLayout(grid_page)
        self.only_used = QCheckBox('Show only keys assigned to a Favorites List')
        self.only_used.toggled.connect(lambda _on: self._fill_grid())
        grid_layout.addWidget(self.only_used)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.grid_holder = QWidget()
        self.grid = QGridLayout(self.grid_holder)
        scroll.setWidget(self.grid_holder)
        grid_layout.addWidget(scroll, 1)
        tabs.addTab(grid_page, 'Favorites List keys 00–99')
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Close)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(buttons)
        layout.addLayout(row)
        self.grid_boxes = {}
        self._fill_tree()
        self._fill_grid()

    # ---- tree ------------------------------------------------------------------------------------
    def _key_cell(self, item, key, others, level):
        text = qk.key_label(key)
        if key is not None and len(others) > 1:
            text += f'  (shared by {len(others)})'
            item.setForeground(1, QBrush(WARN))
            item.setToolTip(1, f'{level} key {key:02d} is also assigned to: ' +
                            ', '.join(n for n in others if n != item.text(0)) +
                            '. They are switched together.')
        item.setText(1, text)

    def _set_state(self, item, key, statuses, checkable):
        item.setText(2, qk.state(key, statuses))
        if key is None:
            for column in range(3):
                item.setForeground(column, QBrush(DIM))
            return
        if checkable:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(2, Qt.CheckState.Checked if statuses[key] else Qt.CheckState.Unchecked)
        elif not statuses[key]:
            item.setForeground(2, QBrush(WARN))

    def _fill_tree(self):
        self._loading = True
        try:
            self.tree.clear()
            for l in self.lists:
                top = QTreeWidgetItem(self.tree, [l['name'], '', ''])
                top.setData(0, ROLE, ('list', l['filename'], l['key']))
                self._key_cell(top, l['key'], self.fl_owners.get(l['key'], []), qk.FL)
                self._set_state(top, l['key'], self.fl_status, True)
                if l.get('unreadable'):
                    QTreeWidgetItem(top, ['(this list could not be read)', '', ''])
                system_owners = qk.owners(l['systems'])
                for s in l['systems']:
                    node = QTreeWidgetItem(top, [s['name'], '', ''])
                    node.setData(0, ROLE, ('system', l['filename'], s['key']))
                    self._key_cell(node, s['key'], system_owners.get(s['key'], []), qk.SYSTEM)
                    self._set_state(node, s['key'], self.sys_status[l['filename']], True)
                    department_owners = qk.owners(s['departments'])
                    for d in s['departments']:
                        leaf = QTreeWidgetItem(node, [d['name'], '', ''])
                        self._key_cell(leaf, d['key'], department_owners.get(d['key'], []), qk.DEPARTMENT)
                        self._set_state(leaf, d['key'], s['status'], False)
                        if d['key'] is not None:
                            leaf.setToolTip(2, 'Department key status is shown here; change it on the scanner '
                                               'or in Sentinel for now.')
                top.setExpanded(l['key'] is not None)
        finally:
            self._loading = False
        self._update_summary()

    def _tree_changed(self, item, column):
        if self._loading or column != 2:
            return
        data = item.data(0, ROLE)
        if not data or data[2] is None:
            return
        on = item.checkState(2) == Qt.CheckState.Checked
        level, filename, key = data
        if level == 'list':
            self.fl_status[key] = on
        else:
            self.sys_status[filename][key] = on
        self._fill_tree()
        self._fill_grid()

    # ---- 00-99 grid ------------------------------------------------------------------------------
    def _fill_grid(self):
        for box in self.grid_boxes.values():
            self.grid.removeWidget(box)
            box.deleteLater()
        self.grid_boxes = {}
        shown = [row for row in qk.key_rows(self.fl_status, self.fl_owners)
                 if row[2] or not self.only_used.isChecked()]
        for position, (number, on, names) in enumerate(shown):
            box = QCheckBox(f'{number:02d}  ' + (', '.join(names) if names else '—'))
            box.setChecked(on)
            if not names:
                box.setToolTip('No Favorites List uses this key; switching it does nothing until one does.')
            box.toggled.connect(lambda checked, n=number: self._grid_changed(n, checked))
            self.grid.addWidget(box, position // 3, position % 3)
            self.grid_boxes[number] = box

    def _grid_changed(self, number, checked):
        if self.fl_status[number] == checked:
            return
        self.fl_status[number] = checked
        self._fill_tree()

    def _update_summary(self):
        self.summary.setText('Favorites List keys: ' + qk.summary(self.fl_status, self.fl_owners) +
                             ('  <b>Unsaved changes.</b>' if self.changes() else ''))

    # ---- saving ----------------------------------------------------------------------------------
    def changes(self):
        """Plain-words lines for every switched key."""
        lines = []
        for n in range(100):
            if self.fl_status[n] != self.fl_saved[n]:
                names = ', '.join(self.fl_owners.get(n, [])) or 'no list'
                lines.append(f'Favorites List key {n:02d} ({names}): {"On" if self.fl_status[n] else "Off"}')
        for l in self.lists:
            system_owners = qk.owners(l['systems'])
            for n in range(100):
                if self.sys_status[l['filename']][n] != self.sys_saved[l['filename']][n]:
                    names = ', '.join(system_owners.get(n, [])) or 'no system'
                    lines.append(f'{l["name"]}: system key {n:02d} ({names}): '
                                 f'{"On" if self.sys_status[l["filename"]][n] else "Off"}')
        return lines

    def flist_edits(self):
        edits = {}
        for l in self.lists:
            for n in range(100):
                if self.sys_status[l['filename']][n] != self.sys_saved[l['filename']][n]:
                    edits[(l['filename'], fls.POS_SQK[0] + n)] = 'On' if self.sys_status[l['filename']][n] else 'Off'
        return edits

    def save(self):
        from location_settings import save_profile
        from quick_keys_settings import patch_quick_keys
        from scanner_configurations import save_local_flist_settings
        lines = self.changes()
        if not lines:
            self.accept()
            return
        shown = '\n'.join(lines[:25]) + (f'\n… and {len(lines) - 25} more' if len(lines) > 25 else '')
        if QMessageBox.question(self, 'Save Quick Keys', 'Save these changes to the local scanner configuration?\n\n'
                                + shown + '\n\nThe scanner changes when you export.',
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.Yes) != QMessageBox.StandardButton.Yes:
            return
        try:
            if self.fl_status != self.fl_saved:
                save_profile(self.folder, patch_quick_keys(self.profile, self.fl_status))
            edits = self.flist_edits()
            if edits:
                save_local_flist_settings(self.folder, edits)
        except (OSError, ValueError, UnicodeError) as exc:
            QMessageBox.warning(self, 'Quick keys not saved', str(exc))
            return
        QMessageBox.information(self, 'Quick Keys', 'Saved to the local configuration (previous files backed up).')
        self.accept()
