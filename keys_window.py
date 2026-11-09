# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Favorites → Keys & Tags… (v0.1.8): every quick key, number tag and On/Off switch in one window.

One tree: Favorites Lists › systems › departments › channels and talkgroups. Columns keep the two
separate questions apart: which number an item has (Quick key, Number tag) and whether the scanner
scans it (Scanning). Double-click a number to change it; the list shows which numbers are free and who
uses the others. Tick Scanning to switch a key On or Off. Problems are listed underneath as you work.
Apply puts the changes into the open configuration (list keys straight away; systems, departments and
channels into the lists, kept by Save Configuration)."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog, QLabel,
                             QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSplitter, QTreeWidget,
                             QTreeWidgetItem, QVBoxLayout)

import keys_model as km

NAME, DETAIL, KEY, SCANNING, TAG, ORDER = range(6)
SORT_ROLE = Qt.ItemDataRole.UserRole + 1
SORTS = (('Scanner order', ORDER, Qt.SortOrder.AscendingOrder),
         ('Name (A–Z)', NAME, Qt.SortOrder.AscendingOrder),
         ('Name (Z–A)', NAME, Qt.SortOrder.DescendingOrder),
         ('Quick key (low first)', KEY, Qt.SortOrder.AscendingOrder),
         ('Quick key (high first)', KEY, Qt.SortOrder.DescendingOrder),
         ('Number tag (low first)', TAG, Qt.SortOrder.AscendingOrder),
         ('Number tag (high first)', TAG, Qt.SortOrder.DescendingOrder),
         ('Not scanned first', SCANNING, Qt.SortOrder.AscendingOrder),
         ('Detail', DETAIL, Qt.SortOrder.AscendingOrder))


class SortItem(QTreeWidgetItem):
    """Sorts by a key kept per column (numbers as numbers; items without a number last), so a sort
    keeps each system under its list and each department under its system (v0.1.13)."""

    def __lt__(self, other):
        tree = self.treeWidget()
        column = tree.sortColumn() if tree is not None else ORDER
        mine, theirs = self.data(column, SORT_ROLE), other.data(column, SORT_ROLE)
        if mine is None or theirs is None:
            return str(self.text(column)).casefold() < str(other.text(column)).casefold()
        if mine[0] != theirs[0]:                      # items without a number go last either way
            descending = tree is not None and tree.header().sortIndicatorOrder() == Qt.SortOrder.DescendingOrder
            return (mine[0] < theirs[0]) != descending
        return mine < theirs


def sort_key(column, item, scanned):
    """(no-value flag, value, name) for sorting a column."""
    name = item['name'].casefold()
    if column == KEY:
        return (item['key'] is None, item['key'] or 0, name)
    if column == TAG:
        return (item['tag'] is None, item['tag'] or 0, name)
    if column == SCANNING:
        return (False, 1 if scanned else 0, name)
    if column == ORDER:
        return (False, item['id'], '')
    if column == DETAIL:
        return (False, str(item.get('detail') or ''), name)
    return (False, name, item['id'])
DIM, WARN, GOOD = QColor('#8a8f98'), QColor('#ff9e91'), QColor('#8fd19e')
ROLE = Qt.ItemDataRole.UserRole

HELP = ('<b>Quick key</b> and <b>Number tag</b> are numbers an item is given; <b>Scanning</b> says whether the '
        'scanner scans it. Double-click a number to change it (the list shows free numbers and who uses the '
        'others). Tick or untick Scanning to switch that key On or Off; everything on the same key follows. '
        'Favorites List numbers are one set for the scanner; system numbers one set per list; department keys '
        'and channel number tags one set per system.')


class NumberPicker(QDialog):
    def __init__(self, parent, model, item, field):
        super().__init__(parent)
        word = 'quick key' if field == 'key' else 'number tag'
        self.setWindowTitle(f'{word.capitalize()} — {item["name"]}')
        layout = QVBoxLayout(self)
        label = QLabel(f'{km.LEVEL_WORD[item["level"]].capitalize()} {word} for <b>{item["name"]}</b>:')
        layout.addWidget(label)
        self.combo = QComboBox()
        self.combo.addItem('Off (none)', None)
        free = model.next_free(item, field)
        start = 0
        for n in range(model.maximum(field, item) + 1):
            users = model.users(item, field, n)
            text = f'{n:02d}' + (f'  — used by {", ".join(u["name"] for u in users[:3])}' if users else '  — free')
            self.combo.addItem(text, n)
            if n == item[field]:
                start = self.combo.count() - 1
        self.combo.setCurrentIndex(start)
        layout.addWidget(self.combo)
        if free is not None:
            nxt = QPushButton(f'Next free: {free:02d}')
            nxt.clicked.connect(lambda: self.combo.setCurrentIndex(free + 1))
            layout.addWidget(nxt)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def value(self):
        return self.combo.currentData()


class KeysWindow(QDialog):
    def __init__(self, main, folder, entries_by_file):
        super().__init__(main)
        self.main, self.folder = main, folder
        self.model = km.model_for_configuration(folder, entries_by_file)
        self._loading = False
        self.setWindowTitle('Keys & Tags')
        self.resize(1180, 820)
        layout = QVBoxLayout(self)
        intro = QLabel(HELP)
        intro.setWordWrap(True)
        layout.addWidget(intro)
        split = QSplitter(Qt.Orientation.Vertical)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['Favorites List / System / Department / Channel', 'Detail', 'Quick key',
                                   'Scanning', 'Number tag', 'Order'])
        self.tree.setColumnHidden(ORDER, True)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)    # v0.1.27: Ctrl / Shift
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(ORDER, Qt.SortOrder.AscendingOrder)
        self.tree.header().setToolTip('Click a column heading to sort by it; click again to reverse. '
                                      'Lists, systems and departments stay together.')
        for column, width in ((NAME, 420), (DETAIL, 120), (KEY, 90), (SCANNING, 330), (TAG, 90)):
            self.tree.setColumnWidth(column, width)
        self.tree.itemDoubleClicked.connect(self._double_clicked)
        self.tree.itemChanged.connect(self._item_changed)
        split.addWidget(self.tree)
        lower = QListWidget()
        self.problems = lower
        split.addWidget(lower)
        split.setSizes([620, 160])
        layout.addWidget(split, 1)
        tools = QHBoxLayout()
        tools.addWidget(QLabel('Sort:'))
        self.sort_choice = QComboBox()
        for label, _column, _order in SORTS:
            self.sort_choice.addItem(label)
        self.sort_choice.setToolTip('Sorts the items under each list, system and department; lists, systems '
                                    'and departments stay together')
        self.sort_choice.currentIndexChanged.connect(self._sort_chosen)
        tools.addWidget(self.sort_choice)
        for label, slot, tip in (
                ('Number Keys in Order…', lambda: self._number_children('key'),
                 'Give the systems or departments under the selected item quick keys in order'),
                ('Number Tags in Order…', lambda: self._number_children('tag'),
                 'Give the systems, or the channels of a department, number tags in order'),
                ('Next Free Key', lambda: self._next_free('key'), 'Give the selected item the next free quick key'),
                ('Next Free Tag', lambda: self._next_free('tag'), 'Give the selected item the next free number tag'),
                ('Tags by Department…', self._tags_by_department,
                 'Channel number tags in blocks per department of the selected system (100s, 200s, ...)'),
                ('Match Tags to Keys', self._match_tags,
                 'Number tag = quick key for the selected item and everything under it that has a key'),
                ('Clear', self._clear_selected, 'Set the selected item\'s quick key and number tag to Off')):
            button = QPushButton(label)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            tools.addWidget(button)
        tools.addStretch(1)
        self.summary = QLabel()
        tools.addWidget(self.summary)
        layout.addLayout(tools)
        profiles = QHBoxLayout()
        profiles.addWidget(QLabel('Scan profile:'))
        self.profile_choice = QComboBox()
        self.profile_choice.setMinimumWidth(220)
        self.profile_choice.setToolTip('Saved sets of which keys are On and which lists are monitored')
        profiles.addWidget(self.profile_choice)
        for label, slot in (('Use', self._use_profile), ('Save Current as Profile…', self._save_profile),
                            ('Delete', self._delete_profile)):
            button = QPushButton(label)
            button.clicked.connect(slot)
            profiles.addWidget(button)
        profiles.addStretch(1)
        for label, slot, tip in (
                ('Save Spreadsheet…', self._save_sheet, 'A LibreOffice Calc spreadsheet of every key and tag'),
                ('Read Spreadsheet…', self._read_sheet, 'Bring back numbers edited in that spreadsheet'),
                ('Key Card (PDF)…', self._key_card, 'A printable page of keys and tags to keep with the scanner')):
            button = QPushButton(label)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            profiles.addWidget(button)
        layout.addLayout(profiles)
        self._fill_profiles()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply)
        buttons.rejected.connect(self.close_window)
        layout.addWidget(buttons)
        self.nodes = {}
        self._build()

    # ---- tree ------------------------------------------------------------------------------------------
    def _build(self):
        self._loading = True
        try:
            self.tree.clear()
            self.nodes = {}
            for item in self.model.items:
                parent = self.nodes.get(item['parent'])
                node = SortItem(parent if parent is not None else self.tree, [item['name'], '', '', '', '', ''])
                node.setData(NAME, ROLE, item['id'])
                self.nodes[item['id']] = node
                if item['level'] == 'list':
                    node.setExpanded(False)
        finally:
            self._loading = False
        self._refresh()

    def _sort_chosen(self, index):
        _label, column, order = SORTS[index]
        self.tree.sortByColumn(column, order)

    def _refresh(self):
        self._loading = True
        sorting = self.tree.isSortingEnabled()
        self.tree.setSortingEnabled(False)          # re-sorted once, after every item is updated
        try:
            for item in self.model.items:
                node = self.nodes[item['id']]
                node.setText(DETAIL, item.get('detail', '') or ('Monitor ' + ('On' if item.get('monitor') else 'Off')
                                                                if item['level'] == 'list' else ''))
                if item['level'] != 'channel':
                    node.setText(KEY, '—' if item['key'] is None else f'{item["key"]:02d}')
                if item['tag_scope'] is not None:
                    node.setText(TAG, '—' if item['tag'] is None else f'{item["tag"]:02d}')
                scanned, reason = self.model.scanned(item)
                for column in (NAME, DETAIL, KEY, SCANNING, TAG, ORDER):
                    node.setData(column, SORT_ROLE, sort_key(column, item, scanned))
                node.setText(SCANNING, reason if item['level'] != 'channel' else ('' if scanned else reason))
                node.setForeground(SCANNING, QBrush(GOOD if scanned else WARN))
                if item['level'] == 'list':
                    node.setFlags(node.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    node.setCheckState(DETAIL, Qt.CheckState.Checked if item.get('monitor') else Qt.CheckState.Unchecked)
                on = self.model.key_on(item)
                if on is not None:
                    node.setFlags(node.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    node.setCheckState(SCANNING, Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
                for field, column in (('key', KEY), ('tag', TAG)):
                    shared = item[field] is not None and self.model.users(item, field, item[field])
                    node.setForeground(column, QBrush(WARN if shared else (DIM if item[field] is None else GOOD)))
                    node.setToolTip(column, ('Also used by: ' + ', '.join(u['name'] for u in shared)) if shared
                                    else 'Double-click to change')
        finally:
            self.tree.setSortingEnabled(sorting)
            self._loading = False
        self._show_problems()

    def _show_problems(self):
        self.problems.clear()
        found = self.model.warnings()
        for kind, text in found:
            entry = QListWidgetItem(('⚠ ' if kind == 'shared' else '○ ' if kind == 'skipped' else 'ℹ ') + text)
            entry.setForeground(QBrush(WARN if kind == 'shared' else DIM if kind == 'unused' else QColor('#e0a040')))
            self.problems.addItem(entry)
        if not found:
            self.problems.addItem('No problems: no number is used twice, and everything with a key is scanned.')
        shared = sum(1 for k, _t in found if k == 'shared')
        changes = len(self.model.describe_changes())
        self.summary.setText(f'{shared} number(s) used twice · {changes} unapplied change(s)')

    def _selected(self):
        node = self.tree.currentItem()
        return None if node is None else self.model.items[node.data(NAME, ROLE)]

    def _all_selected(self):
        """Every selected item (v0.1.27: Ctrl+click and Shift+click), in tree order; else the current one."""
        items = [self.model.items[n.data(NAME, ROLE)] for n in self.tree.selectedItems()]
        if not items and self._selected() is not None:
            items = [self._selected()]
        return sorted(items, key=lambda i: i['id'])

    def _double_clicked(self, node, column):
        item = self.model.items[node.data(NAME, ROLE)]
        field = {KEY: 'key', TAG: 'tag'}.get(column)
        if field is None or (field == 'key' and item['key_scope'] is None) or \
                (field == 'tag' and item['tag_scope'] is None):
            return
        picker = NumberPicker(self, self.model, item, field)
        if picker.exec() == QDialog.DialogCode.Accepted:
            self.model.set_number(item, field, picker.value())
            self._refresh()

    def _item_changed(self, node, column):
        if self._loading:
            return
        item = self.model.items[node.data(NAME, ROLE)]
        checked = node.checkState(column) == Qt.CheckState.Checked
        # v0.1.27: ticking one of several selected items ticks them all
        family = self._all_selected() if node.isSelected() else [item]
        changed = False
        for one in family:
            if column == SCANNING and self.model.key_on(one) is not None and checked != self.model.key_on(one):
                self.model.set_on(one, checked)
                changed = True
            elif column == DETAIL and one['level'] == 'list' and checked != one.get('monitor'):
                self.model.set_monitor(one, checked)
                changed = True
        if changed:
            self._refresh()

    # ---- helpers ---------------------------------------------------------------------------------------
    def _number_children(self, field):
        item = self._selected()
        if item is None:
            QMessageBox.information(self, 'Number in Order', 'Select a Favorites List or system first.')
            return
        targets = [c for c in self.model.children(item['id'])
                   if (c['key_scope'] if field == 'key' else c['tag_scope']) is not None]
        if field == 'key' and {c['level'] for c in targets} == {'department', 'site'}:
            # v0.1.22: a trunked system's departments and sites share one set of keys
            choices = ['Departments only', 'Sites only', 'Departments, then sites']
            choice, ok = QInputDialog.getItem(self, 'Number in Order', 'Departments and sites share these keys. '
                                              'Number:', choices, 0, False)
            if not ok:
                return
            if choice == choices[0]:
                targets = [c for c in targets if c['level'] == 'department']
            elif choice == choices[1]:
                targets = [c for c in targets if c['level'] == 'site']
            else:
                targets = ([c for c in targets if c['level'] == 'department']
                           + [c for c in targets if c['level'] == 'site'])
        if not targets:
            QMessageBox.information(self, 'Number in Order', 'Nothing under the selected item takes '
                                    + ('a quick key.' if field == 'key' else 'a number tag.'))
            return
        top = self.model.maximum(field, targets[0])
        start, ok = QInputDialog.getInt(self, 'Number in Order', f'Number the {len(targets)} items under '
                                        f'{item["name"]} starting at:', 0, 0, top)
        if not ok:
            return
        step, ok = QInputDialog.getInt(self, 'Number in Order', 'Count up by:', 1, 1, max(1, top))
        if not ok:
            return
        if start + (len(targets) - 1) * step > top:
            QMessageBox.information(self, 'Number in Order', f'That runs past {top}. Start lower or count by less.')
            return
        self.model.number_in_order(targets, field, start, step)
        self._refresh()

    def _next_free(self, field):
        items = [i for i in self._all_selected() if (i['key_scope'] if field == 'key' else i['tag_scope'])]
        for item in items:                       # v0.1.27: each selected item gets its own free number
            free = self.model.next_free(item, field)
            if free is None:
                QMessageBox.information(self, 'Next Free', f'Every number is used in the set of {item["name"]}.')
                break
            self.model.set_number(item, field, free)
        if items:
            self._refresh()

    def _tags_by_department(self):
        item = self._selected()
        if item is None or item['level'] != 'system':
            QMessageBox.information(self, 'Tags by Department', 'Select a system first.')
            return
        block, ok = QInputDialog.getInt(self, 'Tags by Department', 'Numbers per department (block size):',
                                        100, 10, 500, 10)
        if not ok:
            return
        first, ok = QInputDialog.getInt(self, 'Tags by Department', 'First department starts at:', block, 0, 999)
        if not ok:
            return
        try:
            count = self.model.tags_by_department(item, block, first)
        except ValueError as exc:
            QMessageBox.information(self, 'Tags by Department', str(exc))
            return
        self._refresh()
        self.summary.setText(f'Tagged {count} departments of {item["name"]} in blocks of {block}.')

    def _match_tags(self):
        item = self._selected()
        if item is None:
            QMessageBox.information(self, 'Match Tags to Keys', 'Select a Favorites List or system first.')
            return
        family, stack = [], [item]
        while stack:
            node = stack.pop()
            family.append(node)
            stack.extend(self.model.children(node['id']))
        changed = self.model.match_tags_to_keys(family)
        self._refresh()
        self.summary.setText(f'{changed} number tag(s) now match their quick key.')

    # ---- scan profiles ---------------------------------------------------------------------------------
    def _fill_profiles(self):
        self.profiles = km.load_profiles(self.folder)
        self.profile_choice.clear()
        self.profile_choice.addItems(sorted(self.profiles, key=str.casefold))

    def _save_profile(self):
        name, ok = QInputDialog.getText(self, 'Save Scan Profile', 'Name (for example Home, Fire only, Storm):',
                                        text=self.profile_choice.currentText())
        name = name.strip()
        if not ok or not name:
            return
        if name in self.profiles and QMessageBox.question(
                self, 'Save Scan Profile', f'Replace the profile {name}?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.profiles[name] = self.model.profile()
        km.save_profiles(self.folder, self.profiles)
        km.write_monitor_file(self.folder, self._title())
        self._fill_profiles()
        self.profile_choice.setCurrentText(name)
        self.summary.setText(f'Saved scan profile {name}.')

    def _use_profile(self):
        name = self.profile_choice.currentText()
        if name not in self.profiles:
            return
        missing = self.model.apply_profile(self.profiles[name])
        self._refresh()
        note = f' Not in the profile (left as they were): {", ".join(missing)}.' if missing else ''
        self.summary.setText(f'Profile {name} set; Apply to keep it.{note}')

    def _delete_profile(self):
        name = self.profile_choice.currentText()
        if name in self.profiles and QMessageBox.question(
                self, 'Delete Scan Profile', f'Delete the profile {name}?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            del self.profiles[name]
            km.save_profiles(self.folder, self.profiles)
            km.write_monitor_file(self.folder, self._title())
            self._fill_profiles()

    # ---- spreadsheet and key card (v0.1.11) -------------------------------------------------------------
    def _title(self):
        from pathlib import Path
        return Path(self.folder).name

    def _save_sheet(self):
        import keys_export
        from pathlib import Path
        from PyQt6.QtWidgets import QFileDialog
        if self.model.describe_changes():
            QMessageBox.information(self, 'Save Spreadsheet', 'The spreadsheet shows the numbers as they are in '
                                    'this window, including changes you haven\'t applied yet.')
        start = str(Path.home() / f'{self._title()} keys and tags.ods')
        path, _ = QFileDialog.getSaveFileName(self, 'Save Spreadsheet', start,
                                              'LibreOffice Calc (*.ods);;Excel (*.xlsx)')
        if not path:
            return
        if not path.lower().endswith(('.ods', '.xlsx')):
            path += '.ods'
        try:
            written = keys_export.write_workbook(self.model, path, self._title())
        except (keys_export.ExportError, OSError) as exc:
            QMessageBox.warning(self, 'Save Spreadsheet', str(exc))
            return
        note = '' if str(written) == path else '\n\nLibreOffice isn\'t installed, so it was saved as .xlsx (Calc opens it).'
        QMessageBox.information(self, 'Save Spreadsheet', f'Saved {written}.{note}')

    def _read_sheet(self):
        import keys_export
        from pathlib import Path
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, 'Read Spreadsheet', str(Path.home()),
                                              'Spreadsheets (*.ods *.xlsx)')
        if not path:
            return
        try:
            values = keys_export.read_values(path)
        except (keys_export.ExportError, OSError) as exc:
            QMessageBox.warning(self, 'Read Spreadsheet', str(exc))
            return
        changed, problems = keys_export.apply_values(self.model, values)
        self._refresh()
        text = f'{changed} change(s) read from the spreadsheet. Check them here, then Apply.'
        if problems:
            text += '\n\nSkipped:\n' + '\n'.join(problems[:15]) + (
                f'\n… and {len(problems) - 15} more' if len(problems) > 15 else '')
        QMessageBox.information(self, 'Read Spreadsheet', text)

    def _key_card(self):
        import keys_export
        from pathlib import Path
        from PyQt6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument
        from PyQt6.QtCore import QMarginsF
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, 'Key Card', str(Path.home() / f'{self._title()} key card.pdf'),
                                              'PDF (*.pdf)')
        if not path:
            return
        if not path.lower().endswith('.pdf'):
            path += '.pdf'
        document = QTextDocument()
        document.setHtml(keys_export.card_html(self.model, self._title()))
        writer = QPdfWriter(path)
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.Letter))
        writer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter)
        printer = getattr(document, 'print', None) or getattr(document, 'print_')
        printer(writer)
        QMessageBox.information(self, 'Key Card', f'Saved {path}.')

    def _clear_selected(self):
        items = self._all_selected()
        if not items:
            return
        for item in items:                       # v0.1.27: every selected item
            for field, scope in (('key', 'key_scope'), ('tag', 'tag_scope')):
                if item[scope] is not None:
                    self.model.set_number(item, field, None)
        self._refresh()

    # ---- applying --------------------------------------------------------------------------------------
    def apply(self):
        lines = self.model.describe_changes()
        if not lines:
            return True
        shared = [t for k, t in self.model.warnings() if k == 'shared' and t.startswith('Favorites List')]
        if shared:
            QMessageBox.warning(self, 'Keys & Tags', 'Two Favorites Lists can\'t share a quick key or number tag; '
                                'the scanner wouldn\'t know which one to use:\n\n' + '\n'.join(shared))
            return False
        shown = '\n'.join(lines[:30]) + (f'\n… and {len(lines) - 30} more' if len(lines) > 30 else '')
        if QMessageBox.question(self, 'Apply Keys & Tags', 'Apply these changes?\n\n' + shown,
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.Yes) != QMessageBox.StandardButton.Yes:
            return False
        try:
            self.main.apply_keys_model(self.model)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Keys & Tags not applied', str(exc))
            return False
        entries = {f: e for f, e in self.main.keys_entries().items()}
        self.model = km.model_for_configuration(self.folder, entries)
        self._build()
        return True

    def close_window(self):
        if self.model.describe_changes():
            answer = QMessageBox.question(self, 'Keys & Tags', 'Apply your changes before closing?',
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No |
                                          QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Yes)
            if answer == QMessageBox.StandardButton.Cancel:
                return
            if answer == QMessageBox.StandardButton.Yes and not self.apply():
                return
        self.reject()
