# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
from hpdb_country_ids import load_country_ids
"""Database browser and the Favorites Lists of the open scanner configuration.
No scanner writes and no unvalidated .hpd serialization.
"""
import app_theme
import json
import sqlite3
import hashlib
import threading
import queue
import os
import tempfile
from datetime import datetime
from pathlib import Path
from PyQt6.QtCore import Qt, QTimer, QSettings
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeWidget, QTreeWidgetItem, QPushButton, QLabel, QLineEdit,
    QFileDialog, QMessageBox, QInputDialog, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QDialog, QDialogButtonBox, QCheckBox, QGroupBox, QScrollArea, QTabWidget, QTreeWidgetItemIterator, QRadioButton)
from favorites_explorer import read_text, MAX_BYTES, detect_mounts
from favorites_merge import merge_draft_entry, find_existing_system, AmbiguousFavoritesMatch, native_conventional_candidate
from database_updater import import_hpdb, find_hpdb
from hpdb_metadata import inspect_hpdb
from state_labels import load_state_names, state_display_name
from uniden_source_check import check_official_source
from edition import PERSONAL
import rr_api
import rr_source
import favorites_clipboard

import re


def _natural_key(value):
    """Compare digit runs numerically (Channel 2 before Channel 10)."""
    return tuple((1, int(part)) if part.isdecimal() else (0, part.casefold())
                 for part in re.split(r'(\d+)', str(value)))


class NaturalTreeItem(QTreeWidgetItem):
    """Natural Name sorting and numeric frequency/TGID sorting."""
    def __lt__(self, other):
        tree = self.treeWidget()
        column = tree.sortColumn() if tree else 0
        left, right = self.text(column).strip(), other.text(column).strip()
        if column in (2, 3):
            def numeric(value):
                try: return (0, float(value.replace('MHz','').replace(',','').strip()))
                except ValueError: return (1, _natural_key(value))
            return numeric(left) < numeric(right)
        return _natural_key(left) < _natural_key(right)


DISPLAY_FIELDS = [('name','Name'),('kind','Type'),('frequency','Frequency (MHz)'),('tgid','TGID'),('mode','Mode'),('service','Service')]

# Compact main-window Favorites browser. Full settings live in the separate editor.
FAVORITES_FIELDS = DISPLAY_FIELDS + [('keys', 'Keys / Tag')]   # v0.1.10: quick key and number tag

def favorites_record_columns(row):
    return record_columns(row)


def _frequency_from_record(row):
    """Decode the confirmed HPDB C-Freq/T-Freq hertz field (column index 5)."""
    if not row or row[0].strip() not in ('C-Freq','C-Channel','C-Frequency','T-Freq','T-Frequency','T-Channel'):
        return ''
    if len(row) <= 5:
        return ''
    value = row[5].strip()
    # Original HPDB stores hertz as integers; draft records retain that field.
    if value.isdecimal():
        hz = int(value)
        if 25_000_000 <= hz <= 1_300_000_000:
            return f'{hz / 1_000_000:.6f}'
    # Also accept a genuine MHz decimal in this same documented field.
    import re
    if re.fullmatch(r'\d{2,4}\.\d{3,6}', value) and 25 <= float(value) <= 1300:
        return f'{float(value):.6f}'
    return ''


def _tgid_from_record(row):
    if not row or row[0].strip() not in ('TGID','Tgid','T-Id'): return ''
    # The source TGID field is normally at position six.
    value = row[5].strip() if len(row) > 5 else ''
    return value if value and value.isdecimal() else ''


def record_columns(row):
    """Source-backed display fields; absent values stay empty."""
    if not row: return ['', '', '', '', '', '']
    kind = row[0].strip()
    name = row[3].strip() if len(row)>3 and row[3].strip() else kind
    frequency = _frequency_from_record(row)
    tgid = _tgid_from_record(row)
    if frequency and (name == kind or name.startswith('Id=')):
        name = frequency + ' MHz'
    return [name, kind, frequency, tgid, '', '']

from hpdb_sections import SYSTEMS, GROUPS, CHILDREN, build_sections
LIMIT = 1500000
DB_MAX_BYTES = 300 * 1024 * 1024


def read_hpd_records(path):
    """Read a large Uniden HPDB state file without the former 100k-row cutoff.

    Files are read line by line; an upper bound still prevents runaway memory use.
    """
    path = Path(path)
    if path.stat().st_size > DB_MAX_BYTES:
        raise ValueError('Database file exceeds 300 MB safety limit')
    records = []
    with path.open('r', encoding='cp1252', errors='replace', newline=None) as stream:
        for line in stream:
            if line.strip():
                records.append(line.rstrip('\r\n').split('\t'))
                if len(records) > LIMIT:
                    raise ValueError('Database exceeds 1,500,000 records; contact developer for an indexed loader')
    return records


# A separate SQLite index is used for cross-state searches. Raw database files
# remain read-only; index writes occur only in the local application folder.
INDEX_VERSION = 1

def index_folder(folder, db_path, events):
    try:
        folder = Path(folder)
        files = sorted(folder.glob('s_*.hpd'))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(db_path))
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)')
        connection.execute('CREATE TABLE IF NOT EXISTS records (file TEXT, line INTEGER, system_line INTEGER, kind TEXT, label TEXT, content TEXT, PRIMARY KEY(file,line))')
        connection.execute('CREATE INDEX IF NOT EXISTS idx_records_file_system ON records(file,system_line)')
        connection.execute('CREATE INDEX IF NOT EXISTS idx_records_label ON records(label COLLATE NOCASE)')
        connection.commit()
        for number, path in enumerate(files, 1):
            stamp = f'{path.stat().st_size}:{path.stat().st_mtime_ns}'
            key = 'file:' + path.name
            old = connection.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
            if old and old[0] == stamp:
                events.put(('progress',f'Indexed {number}/{len(files)}: {path.name} (unchanged)'))
                continue
            connection.execute('DELETE FROM records WHERE file=?',(path.name,))
            current_system = 0
            batch=[]
            with path.open('r',encoding='cp1252',errors='replace') as stream:
                for line_number, line in enumerate(stream,1):
                    fields=line.rstrip('\r\n').split('\t')
                    kind=fields[0] if fields else ''
                    if kind in SYSTEMS:
                        current_system=line_number
                    if not line.strip():
                        continue
                    label=fields[3] if len(fields)>3 else (fields[1] if len(fields)>1 else kind)
                    batch.append((path.name,line_number,current_system,kind,label,line.rstrip('\r\n')))
                    if len(batch)>=2500:
                        connection.executemany('INSERT INTO records VALUES (?,?,?,?,?,?)',batch)
                        batch.clear()
            if batch:
                connection.executemany('INSERT INTO records VALUES (?,?,?,?,?,?)',batch)
            connection.execute('INSERT OR REPLACE INTO meta VALUES (?,?)',(key,stamp))
            connection.commit()
            events.put(('progress',f'Indexed {number}/{len(files)}: {path.name}'))
        connection.close()
        events.put(('done',str(db_path)))
    except Exception as exc:
        events.put(('error',str(exc)))

class SelectConventionalDialog(QDialog):
    """Explicit conventional department and individual channel selection."""
    def __init__(self, section, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Select conventional departments and channels')
        self.resize(850, 640)
        self.groups = []
        current = None
        for record in section['records'][1:]:
            kind = record[0].strip() if record else ''
            if kind == 'C-Group':
                current = {'name': record[3] if len(record)>3 else 'Department', 'records': [record]}
                self.groups.append(current)
            elif current is not None:
                current['records'].append(record)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('System: ' + section['name']))
        layout.addWidget(QLabel('Check departments or individual channels. Nothing is imported until you confirm.'))
        controls = QHBoxLayout()
        for label, state in [('Select all', Qt.CheckState.Checked), ('Clear all', Qt.CheckState.Unchecked)]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, st=state: self.set_all(st))
            controls.addWidget(button)
        layout.addLayout(controls)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['Department / Channel', 'Frequency / source field'])
        self.tree.setColumnWidth(0, 580)
        layout.addWidget(self.tree, 1)
        self.items = []
        for group in self.groups:
            parent_node = QTreeWidgetItem(self.tree, [group['name'], 'Department'])
            parent_node.setFlags(parent_node.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
            parent_node.setCheckState(0, Qt.CheckState.Unchecked)
            for record in group['records'][1:]:
                kind = record[0].strip() if record else ''
                if kind in ('C-Freq', 'C-Channel', 'C-Frequency'):
                    name = record[3] if len(record)>3 else '(unnamed channel)'
                    frequency = record[5] if len(record)>5 else ''
                    node = QTreeWidgetItem(parent_node, [name, frequency])
                    node.setFlags(node.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    node.setCheckState(0, Qt.CheckState.Unchecked)
                    self.items.append((group, record, node))
        self.filter = QLineEdit()
        self.filter.setPlaceholderText('Filter departments or channels…')
        self.filter.textChanged.connect(self.filter_items)
        layout.addWidget(self.filter)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Review selected channels')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def set_all(self, state):
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setCheckState(0, state)

    def filter_items(self, text):
        query = text.casefold().strip()
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            matches_group = query in group.text(0).casefold()
            for j in range(group.childCount()):
                child = group.child(j)
                match = matches_group or query in (child.text(0) + ' ' + child.text(1)).casefold()
                child.setHidden(not match)
            group.setHidden(bool(query and not matches_group and not any(not group.child(j).isHidden() for j in range(group.childCount()))))
            if query:
                group.setExpanded(True)

    def selected(self):
        chosen = []
        for group in self.groups:
            selected_records = [record for g, record, node in self.items
                                if g is group and node.checkState(0) == Qt.CheckState.Checked]
            if selected_records:
                rectangles = [r for r in group['records'][1:] if r and r[0].strip() == 'Rectangle']
                chosen.append({'name': group['name'],
                               'records': [group['records'][0]] + rectangles + selected_records})
        return chosen


class AddDestinationDialog(QDialog):
    """Choose where Add to Favorites puts the selection: an existing list or a new one.

    A new list is only ever created together with its first content, so the
    dialog never leaves an empty Favorites List behind.
    """
    def __init__(self, system_name, list_names, current, can_create, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Add to Favorites')
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Adding from: ' + system_name))
        layout.addWidget(QLabel('Destination Favorites List'))
        self.existing_radio = QRadioButton('Add to an existing Favorites List')
        self.new_radio = QRadioButton('Create a new Favorites List with this selection')
        self.list_combo = QComboBox()
        self.list_combo.addItems(list_names)
        if current in list_names:
            self.list_combo.setCurrentText(current)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText('Name for the new Favorites List (1–64 characters)')
        self.name_edit.setMaxLength(64)
        layout.addWidget(self.existing_radio)
        layout.addWidget(self.list_combo)
        layout.addWidget(self.new_radio)
        layout.addWidget(self.name_edit)
        self.hint = QLabel('')
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.new_radio.setEnabled(can_create)
        if not can_create:
            self.hint.setText('Open a scanner configuration to create new Favorites Lists.')
        if not list_names:
            self.existing_radio.setEnabled(False)
            self.list_combo.setEnabled(False)
        (self.new_radio if (not list_names and can_create) else self.existing_radio).setChecked(True)
        self.existing_radio.toggled.connect(self._sync)
        self._sync()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.buttons = buttons

    def _sync(self):
        creating = self.new_radio.isChecked()
        self.list_combo.setEnabled(not creating and self.existing_radio.isEnabled())
        self.name_edit.setEnabled(creating)
        if creating:
            self.hint.setText('The list is created only when you confirm the channels to add; '
                              'cancelling leaves nothing behind. Local configuration only.')

    def result_choice(self):
        """Return ('existing', draft name) or ('new', list name)."""
        if self.new_radio.isChecked():
            return 'new', self.name_edit.text().strip()
        return 'existing', self.list_combo.currentText()


class SelectTrunkDialog(QDialog):
    """Explicit site and individual TGID selection, source record blocks only."""
    def __init__(self, section, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Select site frequencies and individual talkgroups')
        self.resize(900, 680)
        self.groups = []
        current = None
        for record in section['records'][1:]:
            kind = record[0].strip() if record else ''
            if kind in ('Site', 'T-Group'):
                current = {'kind': kind, 'name': record[3] if len(record)>3 else kind,
                           'records': [record]}
                self.groups.append(current)
            elif current is not None:
                current['records'].append(record)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('System: ' + section['name']))
        layout.addWidget(QLabel('Select individual site frequencies and talkgroups.'))
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.site_tree = QTreeWidget()
        self.site_tree.setHeaderLabels(['Site / Frequency'])
        self.tg_tree = QTreeWidget()
        self.tg_tree.setHeaderLabels(['Department / Talkgroup', 'TGID (source field 6)'])
        self.tg_tree.setColumnWidth(0, 570)
        self.site_items=[]
        self.frequency_items=[]
        self.tg_items=[]
        for group in self.groups:
            if group['kind']=='Site':
                node=QTreeWidgetItem(self.site_tree,[group['name']])
                node.setFlags(node.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
                node.setCheckState(0,Qt.CheckState.Unchecked)
                self.site_items.append((group,node))
                for record in group['records'][1:]:
                    if record and record[0].strip() in ('T-Freq','T-Frequency','T-Channel'):
                        leaf=QTreeWidgetItem(node,[record_columns(record)[0]])
                        leaf.setFlags(leaf.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        leaf.setCheckState(0,Qt.CheckState.Unchecked)
                        self.frequency_items.append((group,record,leaf))
            else:
                parent_node=QTreeWidgetItem(self.tg_tree,[group['name'],'Department'])
                parent_node.setFlags(parent_node.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
                parent_node.setCheckState(0,Qt.CheckState.Unchecked)
                for record in group['records'][1:]:
                    if record and record[0].strip()=='TGID':
                        name=record[3] if len(record)>3 else '(unnamed talkgroup)'
                        identifier=record[5] if len(record)>5 else '(missing)'
                        node=QTreeWidgetItem(parent_node,[name,identifier])
                        node.setFlags(node.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        node.setCheckState(0,Qt.CheckState.Unchecked)
                        self.tg_items.append((group,record,node))
        self.tabs.addTab(self.site_tree,'Sites')
        self.tabs.addTab(self.tg_tree,'Individual talkgroups')
        self.filter=QLineEdit()
        self.filter.setPlaceholderText('Filter talkgroups by name or TGID…')
        self.filter.textChanged.connect(self.filter_talkgroups)
        layout.addWidget(self.filter)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Add to Favorites List')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def filter_talkgroups(self, text):
        query=text.casefold().strip()
        for _,_,node in self.tg_items:
            node.setHidden(bool(query and query not in (node.text(0)+' '+node.text(1)).casefold()))
        for i in range(self.tg_tree.topLevelItemCount()):
            group=self.tg_tree.topLevelItem(i)
            group.setHidden(bool(query and not any(not group.child(j).isHidden() for j in range(group.childCount()))))
            if query: group.setExpanded(True)

    def selected(self):
        chosen=[]
        for group,node in self.site_items:
            frequencies = [record for owner,record,leaf in self.frequency_items
                           if owner is group and leaf.checkState(0)==Qt.CheckState.Checked]
            if frequencies:
                chosen.append({'kind':'Site','name':group['name'],
                               'records':[group['records'][0]] + frequencies,
                               'bandplans':[r for r in group['records'][1:]
                                            if r and r[0].strip() in ('BandPlan_P25','BandPlan_Mot')],
                               'rectangles':[r for r in group['records'][1:] if r and r[0].strip() == 'Rectangle']})
            elif not node.childCount() and node.checkState(0)==Qt.CheckState.Checked:
                chosen.append(group)
        by_group={}
        for group,record,node in self.tg_items:
            if node.checkState(0)==Qt.CheckState.Checked:
                by_group.setdefault(id(group),{'kind':'T-Group','name':group['name'],
                   'records':[group['records'][0]] + [r for r in group['records'][1:]
                                                      if r and r[0].strip() == 'Rectangle']})['records'].append(record)
        chosen.extend(by_group.values())
        return chosen


class DatabaseWorkspace(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.source_check_events = queue.Queue()
        self.source_check_thread = None
        self.source_check_timer = QTimer(self)
        self.source_check_timer.timeout.connect(self.poll_source_check)
        self.import_events = queue.Queue()
        self.import_thread = None
        self.import_timer = QTimer(self)
        self.import_timer.timeout.connect(self.poll_import)
        self.index_path = None
        self.index_events = queue.Queue()
        self.index_thread = None
        self.index_timer = QTimer(self)
        self.index_timer.timeout.connect(self.poll_index)
        self.source = None
        self.sections = []
        self.db_files = []
        self.favorites_files = []
        self.db_index = {}
        self._loading = False
        self.drafts = {}
        self.current_draft = None
        # Set by the main window when a local configuration is open:
        # {'available': callable() -> bool,
        #  'check': callable(name) -> None (raises ValueError),
        #  'create': callable(name, database_rows) -> new draft name}
        self.new_list_hooks = None
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search system names and record contents…')
        self.search.setPlaceholderText('Search current state (use Search ALL for the entire database)')
        self.search.textChanged.connect(self.apply_search)
        self.db_tree = QTreeWidget()
        self.db_tree.setHeaderLabels([title for _,title in DISPLAY_FIELDS])
        self.db_tree.setUniformRowHeights(True)
        self.db_tree.itemExpanded.connect(self.expand_db_item)
        self.db_tree.currentItemChanged.connect(self.show_db_details)
        # Source of Database Contents (v0.1.1): the Uniden master database (personal build) or RadioReference.
        self.source_choice = QComboBox()
        if PERSONAL:
            self.source_choice.addItem('Uniden database', 'uniden')
        self.source_choice.addItem('RadioReference', 'rr')
        self.rr_browser = None
        self.rr_entries = []
        self.rr_generation = 0
        self.rr_jobs = []
        self.rr_timer = QTimer(self)
        self.rr_timer.timeout.connect(self._rr_poll)
        self.country_choice = QComboBox()
        self.country_choice.addItem("USA", 1)
        self.country_choice.addItem("Canada", 2)
        self.country_choice.currentIndexChanged.connect(self._country_changed)
        self._country_map = {}
        self._region_paths = []
        self._region_names = {}
        self.region_choice = QComboBox()
        self.county_choice = QComboBox()
        self.system_choice = QComboBox()
        self.group_choice = QComboBox()
        self.system_type_choice = QComboBox()
        self.system_type_choice.addItems(["All Systems", "Conventional", "Trunked"])
        self.system_type_choice.currentIndexChanged.connect(self._filter_system_types)
        self.region_choice.currentIndexChanged.connect(self._region_changed)
        self.county_choice.currentIndexChanged.connect(self._county_changed)
        self.system_choice.currentIndexChanged.connect(self._system_changed)
        self.group_choice.currentIndexChanged.connect(self._group_changed)
        self.draft_tree = QTreeWidget()
        self.draft_tree.setHeaderLabels([title for _,title in FAVORITES_FIELDS])
        self.draft_tree.setUniformRowHeights(True)
        self.display_settings = QSettings('SDS100Manager', 'DatabaseFavoritesManager')
        for tree, key in ((self.db_tree,'database'), (self.draft_tree,'favorites')):
            tree.setSortingEnabled(True)
            tree.header().setSectionsMovable(True)
            tree.header().setStretchLastSection(False)
            tree.setColumnWidth(0, 340)
            tree.setColumnWidth(1, 150)
            for col in range(2,tree.columnCount()): tree.setColumnWidth(col, 165 if col == 2 else 125)
            fields = FAVORITES_FIELDS if key == 'favorites' else DISPLAY_FIELDS
            for col, (field, _) in enumerate(fields):
                visible = self.display_settings.value(f'columns/{key}/{field}', (key == 'favorites' or field in ('name','kind','frequency','tgid')), type=bool)
                tree.setColumnHidden(col, not visible if col else False)

        self.draft_choice = QComboBox()
        self.draft_choice.currentTextChanged.connect(self.choose_draft)
        self.status = QLabel('Open a scanner configuration, choose a system in the database, then Add to Favorites. '
                             'Nothing is written to the scanner until you Export to Scanner.')
        self.status.setWordWrap(True)
        root = QVBoxLayout(self)
        # Three consistent, compact rows. Each row has a single purpose.
        toolbar_rows = (
            ("BROWSE", (
                ("Open Database", self.open_folder, "Open the local full HPDB database"),
                ("Build Index", self.start_index, "Index all states for searching"),
                ("Search All", self.search_all, "Search the entire indexed database"),
            )),
            ("MASTER HPDB", (
                ("Import HPDB", self.import_database, "Import a verified local HPDB folder"),
                ("Database Info", self.show_database_info, "Inspect the local HPDB version and files"),
                ("Compare HPDB", self.compare_hpdb, "Compare two local HPDB copies without modifying either"),
                ("Source Status", self.check_uniden_source,
                 "Check Uniden's software page only; not a database update check"),
            )),
        )
        for row_name, actions in toolbar_rows:
            bar = QHBoxLayout()
            bar.setSpacing(6)
            heading = QLabel(row_name)
            heading.setFixedWidth(112)
            app_theme.set_css(heading, "font-weight:700; color:#a5bdd2;")
            bar.addWidget(heading)
            for title, fn, tooltip in actions:
                button = QPushButton(title)
                button.setToolTip(tooltip)
                button.setMinimumHeight(30)
                button.clicked.connect(fn)
                bar.addWidget(button)
            bar.addStretch(1)
            root.addLayout(bar)
        root.addWidget(self.search)
        # Two-row browser: country / region / type, then system and primary action.
        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.county_cell = []
        for label, widget, stretch in (
            ('Source', self.source_choice, 1),
            ('Country', self.country_choice, 1),
            ('State / Region', self.region_choice, 3),
            ('County', self.county_choice, 2),
            ('System Type', self.system_type_choice, 2)):
            cell = QVBoxLayout()
            cell.setSpacing(2)
            caption = QLabel(label)
            cell.addWidget(caption)
            cell.addWidget(widget)
            filters.addLayout(cell, stretch)
            if widget is self.county_choice:
                self.county_cell = [caption, widget]
        root.addLayout(filters)
        system_row = QHBoxLayout()
        system_row.setSpacing(8)
        system_cell = QVBoxLayout()
        system_cell.setSpacing(2)
        system_cell.addWidget(QLabel('System'))
        system_cell.addWidget(self.system_choice)
        system_row.addLayout(system_cell, 1)
        add_button = QPushButton('＋ Add to Favorites →')
        add_button.setMinimumHeight(34)
        add_button.setMinimumWidth(190)
        add_button.setToolTip('Add selected Database Contents items to the current Favorites draft')
        app_theme.set_css(add_button, 'QPushButton {background-color:#2167b1;color:white;font-weight:bold;'
                                      'border-radius:5px;padding:6px 14px;} '
                                      'QPushButton:hover {background-color:#2975b8;}')
        add_button.clicked.connect(self.add_selected)
        system_row.addWidget(add_button, 0, Qt.AlignmentFlag.AlignBottom)
        root.addLayout(system_row)
        self.county_choice.addItem('All counties — mapping not yet verified')
        self.county_choice.setEnabled(False)
        saved = str(self.display_settings.value('database/source', 'uniden') or 'uniden')
        index = self.source_choice.findData(saved)
        self.source_choice.setCurrentIndex(index if isinstance(index, int) and index >= 0 else 0)
        self.source_choice.currentIndexChanged.connect(self._source_changed)
        self._show_county(self.rr_mode())
        if self.rr_mode():
            QTimer.singleShot(0, lambda: self._country_changed(self.country_choice.currentIndex()))
        # Legacy group selector remains internal; Database Contents provides detail navigation.
        self.db_tree.hide()
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.addWidget(QLabel('DATABASE BROWSER'))
        left_l.addWidget(QLabel('Select a system above, then inspect its records in Database Contents.'))
        left_l.addStretch(1)
        add = QPushButton('Add Selection →')
        add.clicked.connect(self.add_selected)
        left_l.addWidget(add)
        right = QWidget()
        right_l = QVBoxLayout(right)
        self.lists_heading = QLabel('FAVORITES LISTS — open a scanner configuration (File → Open Scanner Configuration…)')
        right_l.addWidget(self.lists_heading)
        right_l.addWidget(self.draft_choice)
        right_l.addWidget(self.draft_tree, 1)
        delete = QPushButton('Remove Selection')
        delete.clicked.connect(self.delete_selected)
        right_l.addWidget(delete)
        details = QWidget()
        details_layout = QVBoxLayout(details)
        details_layout.addWidget(QLabel('DATABASE CONTENTS — selected item (read-only)'))
        self.detail_table = QTreeWidget()
        self.detail_table.setHeaderLabels([label for _, label in DISPLAY_FIELDS])
        self.detail_table.setSortingEnabled(True)
        self.detail_table.header().setSectionsMovable(True)
        self.detail_table.setColumnWidth(0, 340)
        self.detail_table.setColumnWidth(2, 165)
        for col, (field, _) in enumerate(DISPLAY_FIELDS):
            visible = self.display_settings.value(f'columns/database/{field}', field in ('name','kind','frequency','tgid'), type=bool)
            self.detail_table.setColumnHidden(col, not visible if col else False)
        details_layout.addWidget(self.detail_table, 1)
        split.addWidget(details)
        split.addWidget(right)
        split.setSizes([690, 570])
        root.addWidget(split, 1)
        root.addWidget(self.status)

    def check_uniden_source(self):
        if self.source_check_thread and self.source_check_thread.is_alive():
            return
        self.status.setText("Checking official Uniden SDS100 downloads page…")
        def worker():
            try:
                self.source_check_events.put(("done", check_official_source()))
            except Exception as exc:
                self.source_check_events.put(("error", str(exc)))
        self.source_check_thread = threading.Thread(target=worker, daemon=True)
        self.source_check_thread.start()
        self.source_check_timer.start(250)

    def poll_source_check(self):
        try:
            state, value = self.source_check_events.get_nowait()
        except queue.Empty:
            return
        self.source_check_timer.stop()
        if state == "error":
            self.status.setText("Unable to check Uniden source: " + value)
            QMessageBox.warning(self, "Uniden source check failed", value)
            return
        versions = ", ".join(value["sentinel_versions"]) or "Not parsed"
        message = (f"Checked: {value['checked_utc']}\n"
                   f"Official page: {value['url']}\n"
                   f"Sentinel software versions shown: {versions}\n\n"
                   "Standalone Master HPDB database download: NOT VERIFIED.\n\n"
                   "This checks Uniden's official software page only. "
                   "It does not download or install a database, and does not "
                   "indicate whether your local database is current.")
        self.status.setText("Uniden source checked. Direct Master HPDB download still unverified.")
        QMessageBox.information(self, "Official Uniden source status", message)

    def show_database_info(self):
        base = self.source
        if not base:
            folder = QFileDialog.getExistingDirectory(
                self, "Select HPDB folder to inspect")
            if not folder:
                return
            try:
                base = find_hpdb(folder)
            except ValueError as exc:
                QMessageBox.warning(self, "Database folder", str(exc))
                return
        try:
            info = inspect_hpdb(base)
        except OSError as exc:
            QMessageBox.warning(self, "Unable to inspect", str(exc))
            return
        QMessageBox.information(self, "Local Uniden HPDB information",
            f"Folder: {info['path']}\n"
            f"Catalog: {info['catalog']}\n"
            f"Catalog version: {info['version']}\n"
            f"Catalog date: {info['date']}\n"
            f"State files: {info['state_files']}\n"
            f"Total state-file bytes: {info['total_bytes']:,}\n\n"
            "These are local-file details, not confirmation that the database "
            "is the latest release.\n"
            "Official Uniden direct download is not implemented.")

    def compare_hpdb(self):
        """Read-only comparison of two local Master HPDB copies."""
        first = QFileDialog.getExistingDirectory(self, "Select existing HPDB folder")
        if not first:
            return
        second = QFileDialog.getExistingDirectory(self, "Select candidate HPDB folder")
        if not second:
            return
        try:
            a = inspect_hpdb(find_hpdb(first))
            b = inspect_hpdb(find_hpdb(second))
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Unable to compare HPDB", str(exc))
            return
        def describe(label, info):
            return (f"{label}: {info['path']}\n"
                    f"  Version: {info['version']}\n"
                    f"  Date: {info['date']}\n"
                    f"  State files: {info['state_files']}\n"
                    f"  Total bytes: {info['total_bytes']:,}")
        differences = []
        for key, title in (("version", "Catalog version"), ("date", "Catalog date"),
                           ("state_files", "State-file count"),
                           ("total_bytes", "State-file bytes")):
            if a[key] != b[key]:
                differences.append(title)
        summary = ", ".join(differences) if differences else "No differences in inspected metadata"
        QMessageBox.information(self, "Local HPDB comparison",
            describe("Existing", a) + "\n\n" + describe("Candidate", b) +
            "\n\nDifferences: " + summary +
            "\n\nThis is a metadata comparison, not a proof of completeness, "
            "authenticity, or newer database release. Neither folder was modified.")

    def import_database(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select complete Uniden HPDB folder (offline import)")
        if not folder:
            return
        try:
            find_hpdb(folder)
        except ValueError as exc:
            QMessageBox.warning(self, "Incomplete database", str(exc))
            return
        if self.import_thread and self.import_thread.is_alive():
            QMessageBox.information(self, "Import in progress", "Please wait for the current import.")
            return
        target = Path.home() / "SDS100MonitorData" / "HPDB"
        if QMessageBox.question(self, "Import local HPDB",
                f"Copy database to:\n{target}\n\n"
                "The existing local database will be backed up. "
                "No scanner files will be modified. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                ) != QMessageBox.StandardButton.Yes:
            return
        self.status.setText("Importing and checking HPDB files in background…")
        def worker():
            try:
                result = import_hpdb(folder, target)
                self.import_events.put(("done", result))
            except Exception as exc:
                self.import_events.put(("error", str(exc)))
        self.import_thread = threading.Thread(target=worker, daemon=True)
        self.import_thread.start()
        self.import_timer.start(250)

    def poll_import(self):
        try:
            state, result = self.import_events.get_nowait()
        except queue.Empty:
            return
        self.import_timer.stop()
        if state == "error":
            QMessageBox.critical(self, "Database import failed", result)
            self.status.setText("Database import failed; existing local database retained.")
            return
        self.status.setText(f"Imported {result['state_count']} state files to "
                            "~/SDS100MonitorData/HPDB. Select Open full database "
                            "to browse it, then Index entire database.")
        QMessageBox.information(self, "Database imported",
            f"Copied and SHA-256 checked {result['file_count']} files.\n"
            "Previous local database backed up.\n\n"
            "This verifies copy integrity, NOT authenticity or database freshness.\n"
            "Direct download from Uniden is not available yet.")

    def open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Choose Uniden database folder or scanner root')
        if folder:
            self.open_database_path(folder)

    def open_database_path(self, folder):
        base = Path(folder)
        choices = [base / 'BCDx36HP' / 'HPDB', base / 'HPDB', base]
        db = next((p for p in choices if p.is_dir() and any(p.glob('s_*.hpd'))), None)
        if not db:
            QMessageBox.warning(self, 'Database not found', 'No s_*.hpd files found. Select the HPDB directory or its parent.')
            return
        names = load_state_names(db)
        paths = sorted(db.glob('s_*.hpd'), key=lambda p: (names.get(int(p.stem[2:]), '').casefold() or '\uffff', p.name))
        self.db_files = paths
        self.db_index = {}
        self.sections = []
        self.source = str(db)
        self.db_tree.clear()
        nationwide = QTreeWidgetItem(['Nationwide Systems', 'Category', ''])
        regions = QTreeWidgetItem(['States and Territories', 'Category', ''])
        self.db_tree.addTopLevelItem(nationwide)
        self.db_tree.addTopLevelItem(regions)
        for path in paths:
            state_id = int(path.stem[2:])
            parent = nationwide if state_id == 0 else regions
            label = ('Nationwide Systems' if state_id == 0 else state_display_name(path, names))
            state = QTreeWidgetItem(parent, [label, 'Database file', 'Not loaded'])
            state.setData(0, Qt.ItemDataRole.UserRole, ('file', str(path)))
            QTreeWidgetItem(state, ['Expand to load systems', '', ''])
        nationwide.setHidden(nationwide.childCount() == 0)
        regions.setHidden(regions.childCount() == 0)
        regions.setExpanded(True)
        self._country_map = load_country_ids(db)
        self._region_paths = paths
        self._region_names = names
        self._country_changed(self.country_choice.currentIndex())
        self.index_path = None
        self.status.setText(f'Opened full Uniden database: {len(paths)} regional files. '
                            'Expand a state to load its systems; no individual file selection required.')
        self.apply_search(self.search.text())


    # ---- RadioReference as the source (v0.1.1) ------------------------------------------------------
    def rr_mode(self):
        return self.source_choice.currentData() == 'rr'

    def _show_county(self, on):
        for widget in self.county_cell:
            widget.setVisible(on)

    def _source_changed(self, _index=None):
        self.display_settings.setValue('database/source', self.source_choice.currentData())
        self._show_county(self.rr_mode())
        self.detail_table.clear()
        self._country_changed(self.country_choice.currentIndex())

    def _rr_client_browser(self):
        if self.rr_browser is None:
            from rr_account_dialog import rr_settings
            try:
                self.rr_browser = rr_source.RRBrowser(rr_api.Account(rr_settings()).client())
            except rr_api.RRError as exc:
                self.status.setText(f'RadioReference: {exc} (Tools → RadioReference Account…)')
                return None
        return self.rr_browser

    def rr_account_changed(self):
        """The account was changed: sign in again next time."""
        self.rr_browser = None

    def _rr_run(self, what, work, done):
        """Run work() off the GUI thread; done(result, error) runs on the GUI thread unless a newer request
        of the same kind (what) was made meanwhile."""
        browser = self._rr_client_browser()
        if browser is None:
            done(None, None)
            return
        self.rr_generation += 1
        job = {'what': what, 'gen': self.rr_generation, 'done': done, 'box': {}}

        def run():
            try:
                job['box']['result'] = work(browser)
            except Exception as exc:          # network, sign-in, or an unexpected reply
                job['box']['error'] = str(exc)
        job['thread'] = threading.Thread(target=run, daemon=True)
        self.rr_jobs = [j for j in self.rr_jobs if j['what'] != what] + [job]
        job['thread'].start()
        self.status.setText('Asking RadioReference…')
        self.rr_timer.start(100)

    def _rr_poll(self):
        for job in list(self.rr_jobs):
            if job['thread'].is_alive():
                continue
            self.rr_jobs.remove(job)
            error = job['box'].get('error')
            if error and ('credential' in error.lower() or 'key' in error.lower() or 'password' in error.lower()):
                self.rr_browser = None
            if error:
                self.status.setText(f'RadioReference: {error}')
            job['done'](job['box'].get('result'), error)
        if not self.rr_jobs:
            self.rr_timer.stop()

    def _rr_states(self):
        coid = self.country_choice.currentData()
        self.region_choice.blockSignals(True)
        self.region_choice.clear()
        self.region_choice.addItem('Loading states from RadioReference…', None)
        self.region_choice.blockSignals(False)
        self._rr_reset_counties()

        def done(states, error):
            if not self.rr_mode():
                return
            self.region_choice.blockSignals(True)
            self.region_choice.clear()
            self.region_choice.addItem('Choose state / region…', None)
            for stid, name in states or []:
                self.region_choice.addItem(name, ('rr-state', stid))
            self.region_choice.blockSignals(False)
            if states:
                self.status.setText(f'RadioReference: {len(states)} states and provinces.')
        self._rr_run('states', lambda b: b.states(coid), done)

    def _rr_reset_counties(self):
        self.county_choice.blockSignals(True)
        self.county_choice.clear()
        self.county_choice.addItem('Statewide systems and agencies', None)
        self.county_choice.setEnabled(False)
        self.county_choice.blockSignals(False)
        self.system_choice.blockSignals(True)
        self.system_choice.clear()
        self.system_choice.addItem('Choose a system…', None)
        self.system_choice.blockSignals(False)
        self.rr_entries = []

    def _rr_region_changed(self):
        data = self.region_choice.currentData()
        self._rr_reset_counties()
        self.detail_table.clear()
        if not data:
            return
        stid = data[1]

        def done(counties, error):
            if self.region_choice.currentData() != data:
                return
            self.county_choice.blockSignals(True)
            for ctid, name in counties or []:
                self.county_choice.addItem(f'{name} County', ctid)
            self.county_choice.setEnabled(True)
            self.county_choice.blockSignals(False)
            self._rr_systems()
        self._rr_run('counties', lambda b: b.counties(stid), done)

    def _rr_systems(self):
        data = self.region_choice.currentData()
        if not data:
            return
        stid, ctid = data[1], self.county_choice.currentData()

        def done(entries, error):
            if self.region_choice.currentData() != data or self.county_choice.currentData() != ctid:
                return
            self.rr_entries = entries or []
            self._rr_fill_systems()
            self.status.setText(f'RadioReference: {len(self.rr_entries)} systems and agencies '
                                f'{"in this county" if ctid else "statewide"}.')
        self._rr_run('systems', lambda b: b.systems(stid, ctid), done)

    def _rr_fill_systems(self):
        self.system_choice.blockSignals(True)
        self.system_choice.clear()
        self.system_choice.addItem('Choose a system…', None)
        for label, kind, key in sorted(self.rr_entries, key=lambda e: e[0].casefold()):
            if self._system_type_matches({'kind': kind}):
                self.system_choice.addItem(f'{label} [{kind}]', (f'rr:{key[0]}:{key[1]}', 0))
        self.system_choice.blockSignals(False)
        self.group_choice.blockSignals(True)
        self.group_choice.clear()
        self.group_choice.addItem('All departments / sites', None)
        self.group_choice.blockSignals(False)

    def _rr_system_changed(self):
        data = self.system_choice.currentData()
        self.detail_table.clear()
        if not data:
            return
        source = data[0]
        if source in self.db_index:
            self._system_changed(self.system_choice.currentIndex())
            return
        _rr, kind, ident = source.split(':')
        key = (kind, int(ident))

        def done(result, error):
            if not result:
                return
            section, why = result
            if section is None:
                self.status.setText(f'RadioReference: {why}')
                QMessageBox.information(self, 'RadioReference', why)
                return
            self.db_index[source] = [section]
            if self.system_choice.currentData() == data:
                self._system_changed(self.system_choice.currentIndex())
                self.status.setText(f'RadioReference: {section["name"]} loaded. Choose items and use Add to '
                                    'Favorites; RadioReference data is kept for this session only.')
        self._rr_run('load', lambda b: b.load(key), done)

    def _country_changed(self, index):
        if self.rr_mode():
            self._rr_states()
            return
        selected = self.country_choice.currentData()
        self.region_choice.blockSignals(True)
        self.region_choice.clear()
        self.region_choice.addItem('Choose state / region…', None)
        # StateId=0 is the HPDB multiple-states/nationwide file. It has
        # CountryId=0, so expose it explicitly for both country selections.
        # Do not relabel other regions or infer nationwide membership.
        nationwide_paths = [p for p in self._region_paths if int(p.stem[2:]) == 0]
        for path in nationwide_paths:
            self.region_choice.addItem('Nationwide', str(path))
        for path in self._region_paths:
            state_id = int(path.stem[2:])
            if state_id == 0 or self._country_map.get(state_id) != selected:
                continue
            self.region_choice.addItem(state_display_name(path, self._region_names), str(path))
        self.region_choice.blockSignals(False)
        self._region_changed(self.region_choice.currentIndex())

    def _region_changed(self, index):
        if self.rr_mode():
            self._rr_region_changed()
            return
        self.system_choice.blockSignals(True)
        self.group_choice.blockSignals(True)
        self.system_choice.clear()
        self.group_choice.clear()
        self.system_choice.addItem('Choose a system…', None)
        self.group_choice.addItem('All departments / sites', None)
        self.system_choice.blockSignals(False)
        self.group_choice.blockSignals(False)
        path = self.region_choice.currentData()
        if not path:
            self.detail_table.clear()
            return
        if path not in self.db_index:
            try:
                self.db_index[path] = build_sections(read_hpd_records(path))
            except (OSError, UnicodeError, ValueError) as exc:
                QMessageBox.warning(self, 'Database unreadable', str(exc))
                return
        self.system_choice.blockSignals(True)
        for idx, section in sorted(enumerate(self.db_index[path]),
                                   key=lambda item: item[1]['name'].casefold()):
            if not self._system_type_matches(section):
                continue
            self.system_choice.addItem(section['name'] + ' [' + section['kind'] + ']',
                                       (path, idx))
        self.system_choice.blockSignals(False)
        self.status.setText(f'{len(self.db_index[path])} systems available.')

    def _system_type_matches(self, section):
        kind = str(section.get('kind', '')).strip().casefold()
        selected = self.system_type_choice.currentIndex()
        return selected == 0 or (selected == 1 and kind == 'conventional') or (selected == 2 and kind in ('trunk', 'trunked'))

    def _filter_system_types(self, index):
        # Reload only the system dropdown, preserving the selected region.
        if self.rr_mode():
            self._rr_fill_systems()
            return
        self._region_changed(self.region_choice.currentIndex())

    def _county_changed(self, index):
        # Uniden: county mappings are not yet verified. RadioReference: the county's systems.
        if self.rr_mode():
            self._rr_systems()

    def _system_changed(self, index):
        data = self.system_choice.currentData()
        if self.rr_mode() and data and data[0] not in self.db_index:
            self._rr_system_changed()
            return
        self.group_choice.blockSignals(True)
        self.group_choice.clear()
        self.group_choice.addItem('All departments / sites', None)
        data = self.system_choice.currentData()
        if data:
            path, idx = data
            section = self.db_index[path][idx]
            for child_idx, group in enumerate(section['children']):
                self.group_choice.addItem(group['name'] + ' [' + group['kind'] + ']',
                                          (path, idx, child_idx))
            self._show_records(section['records'])
        else:
            self.detail_table.clear()
        self.group_choice.blockSignals(False)

    def _group_changed(self, index):
        data = self.group_choice.currentData()
        if data:
            path, idx, child_idx = data
            self._show_records(self.db_index[path][idx]['children'][child_idx]['records'])
        else:
            self._system_changed(self.system_choice.currentIndex())

    def _show_records(self, records):
        """Show meaningful HPDB hierarchy; exclude area metadata nodes."""
        tree = self.detail_table
        tree.setSortingEnabled(False)
        tree.clear()
        system = None
        parent = None
        for record in records[:2000]:
            kind = record[0].strip() if record else ''
            if kind in ('AreaState', 'AreaCounty'):
                continue  # geographic metadata, not radio channels
            columns = record_columns(record)
            if kind in ('Conventional', 'Trunk'):
                system = NaturalTreeItem(tree, columns)
                parent = system
            elif kind in ('C-Group', 'T-Group', 'Site'):
                parent = NaturalTreeItem(system, columns) if system is not None else NaturalTreeItem(tree, columns)
            elif parent is not None:
                NaturalTreeItem(parent, columns)
            else:
                NaturalTreeItem(tree, columns)
        tree.setSortingEnabled(True)
        tree.setColumnWidth(2, max(tree.columnWidth(2), 165))
        self.status.setText(f'{len(records)} source records in selection.')

    def start_index(self):
        if not self.db_files:
            QMessageBox.information(self, 'Open database', 'Open the full database folder first.')
            return
        if self.index_thread and self.index_thread.is_alive():
            QMessageBox.information(self, 'Index running', 'Database indexing is already in progress.')
            return
        folder = Path(self.db_files[0]).parent
        identity = hashlib.sha256(str(folder.resolve()).encode()).hexdigest()[:16]
        target = Path.home() / '.local' / 'share' / 'SDS100MonitorV17' / ('hpdb_' + identity + '.sqlite3')
        self.index_thread = threading.Thread(target=index_folder,
            args=(folder,target,self.index_events),daemon=True)
        self.index_thread.start()
        self.index_timer.start(200)
        self.status.setText('Building full database search index in the background…')

    def poll_index(self):
        try:
            while True:
                kind, message = self.index_events.get_nowait()
                if kind == 'progress':
                    self.status.setText(message)
                elif kind == 'done':
                    self.index_path = Path(message)
                    self.status.setText('Full database index ready. Enter a term and click Search ALL.')
                    self.index_timer.stop()
                elif kind == 'error':
                    self.index_timer.stop()
                    QMessageBox.warning(self,'Index failed',message)
        except queue.Empty:
            pass

    def search_all(self):
        term = self.search.text().strip()
        if not term:
            QMessageBox.information(self,'Search term','Enter a search term first.')
            return
        if len(term) < 2:
            QMessageBox.information(self,'Search term','Enter at least two characters.')
            return
        if not self.index_path or not self.index_path.exists():
            QMessageBox.information(self,'Index first','Click Index entire database first.')
            return
        try:
            con=sqlite3.connect(str(self.index_path))
            # Bound results and query only indexed local database, never scanner storage.
            hits=con.execute('SELECT file,line,system_line,kind,label FROM records '
                'WHERE instr(lower(label),lower(?))>0 LIMIT 501',(term,)).fetchall()
            con.close()
        except sqlite3.Error as exc:
            QMessageBox.warning(self,'Search failed',str(exc))
            return
        self.db_tree.clear()
        self.db_index = {}
        self.db_files = sorted(Path(self.source).glob('s_*.hpd')) if Path(self.source).is_dir() else self.db_files
        for file,line,system_line,kind,label in hits[:500]:
            node=QTreeWidgetItem([label or '(unnamed)',kind,f'{file}:{line}'])
            node.setData(0,Qt.ItemDataRole.UserRole,('search_hit',file,system_line))
            self.db_tree.addTopLevelItem(node)
        self.status.setText(f'Search found {len(hits) if len(hits)<=500 else "500+"} matching records; '
            'select a result and use Add selected system to copy its complete parent system to a draft.')

    def get_indexed_system(self, file, system_line):
        if not system_line or not self.index_path:
            return None
        con=sqlite3.connect(str(self.index_path))
        try:
            next_row=con.execute('SELECT MIN(line) FROM records WHERE file=? AND kind IN ("Conventional","Trunk") AND line>?',
                (file,system_line)).fetchone()[0]
            if next_row is None:
                rows=con.execute('SELECT content FROM records WHERE file=? AND line>=? ORDER BY line',
                    (file,system_line)).fetchall()
            else:
                rows=con.execute('SELECT content FROM records WHERE file=? AND line>=? AND line<? ORDER BY line',
                    (file,system_line,next_row)).fetchall()
        finally:
            con.close()
        sections=build_sections([r[0].split('\t') for r in rows])
        return sections[0] if sections else None

    def expand_db_item(self, item):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, tuple) or data[0] != 'file' or data[1] in self.db_index:
            return
        path = Path(data[1])
        try:
            sections = build_sections(read_hpd_records(path))
        except (OSError, UnicodeError, ValueError) as exc:
            QMessageBox.warning(self, 'State file unreadable', f'{path.name}: {exc}')
            return
        self.db_index[str(path)] = sections
        while item.childCount():
            item.removeChild(item.child(0))
        item.setText(2, str(len(sections)))
        for index, section in enumerate(sections):
            node = QTreeWidgetItem(item, [section['name'], section['kind'], '', '', '', ''])
            node.setData(0, Qt.ItemDataRole.UserRole, ('system', str(path), index))
            for child_index, child in enumerate(section['children']):
                child_node = QTreeWidgetItem(node, [child['name'], child['kind'], '', '', '', ''])
                child_node.setData(0, Qt.ItemDataRole.UserRole,
                                   ('group', str(path), index, child_index))
        self.status.setText(f'{path.name}: {len(sections)} systems loaded; {len(self.db_files)} state files available.')

    def show_db_details(self, current, previous):
        """Show source-backed records, never invented Sentinel settings."""
        self.detail_table.clear()
        if current is None:
            return
        data = current.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, tuple):
            return
        records = []
        if data[0] == 'system' and data[1] in self.db_index:
            sections = self.db_index[data[1]]
            if data[2] < len(sections):
                section = sections[data[2]]
                # System overview: its departments/sites first, or raw records
                records = section['records']
        elif data[0] == 'group' and data[1] in self.db_index:
            sections = self.db_index[data[1]]
            if data[2] < len(sections):
                children = sections[data[2]]['children']
                if data[3] < len(children):
                    records = children[data[3]]['records']
        if not records:
            return
        self._show_records(records)

    def open_favorites_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Choose Favorites Lists directory or scanner root')
        if not folder:
            return
        root = Path(folder)
        choices = [root / 'BCDx36HP' / 'favorites_lists', root / 'favorites_lists', root]
        directory = next((p for p in choices if p.is_dir() and any(p.glob('*.hpd'))), None)
        if not directory:
            QMessageBox.warning(self, 'Favorites not found', 'No .hpd files found in the favorites_lists folder.')
            return
        self.favorites_files = sorted(directory.glob('*.hpd'))
        self.refresh_draft()
        self.status.setText(f'Opened {len(self.favorites_files)} Favorites Lists from {directory}. '
                            'Existing lists are read-only; drafts remain separately editable.')

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Open HPDB state file', str(Path.home()),
                                              'HPDB state files (s_*.hpd);;HPD files (*.hpd)')
        if path:
            self.load_database(Path(path))

    def load_database(self, path):
        try:
            records = read_hpd_records(path)
            sections = build_sections(records)
            if not sections:
                raise ValueError('No Conventional or Trunk system records found in file')
        except (OSError, UnicodeError, ValueError) as exc:
            QMessageBox.critical(self, 'Unable to read database', str(exc))
            return
        self.source = str(path)
        self.sections = sections
        self.db_tree.clear()
        for index, section in enumerate(sections):
            node = QTreeWidgetItem([section['name'], section['kind'], '', '', '', ''])
            node.setData(0, Qt.ItemDataRole.UserRole, index)
            self.db_tree.addTopLevelItem(node)
            for child in section['children']:
                QTreeWidgetItem(node, [child['name'], child['kind'], '', '', '', ''])
        self.status.setText(f'{path.name}: {len(sections)} systems loaded. '
                            'Select a system (or one of its departments) to add the complete system.')
        self.apply_search(self.search.text())

    def apply_search(self, query):
        needle = query.casefold().strip()
        if self.db_files:
            if (self.db_tree.topLevelItemCount() and
                isinstance(self.db_tree.topLevelItem(0).data(0, Qt.ItemDataRole.UserRole), tuple) and
                self.db_tree.topLevelItem(0).data(0, Qt.ItemDataRole.UserRole)[0] == 'search_hit'):
                return
            # Recursively traverse category -> state -> system without eagerly reading files.
            def filter_node(node):
                data = node.data(0, Qt.ItemDataRole.UserRole)
                if isinstance(data, tuple) and data[0] == 'system':
                    section = self.db_index.get(data[1], [])[data[2]]
                    haystack = section['name'] + '\t' + '\t'.join('\t'.join(r) for r in section['records'])
                    visible = not needle or needle in haystack.casefold()
                    node.setHidden(not visible)
                    return visible
                any_child = False
                for j in range(node.childCount()):
                    any_child = filter_node(node.child(j)) or any_child
                own_match = needle in node.text(0).casefold()
                # Keep unexpanded states available for future loading.
                visible = not needle or own_match or any_child or (isinstance(data, tuple) and data[0] == 'file' and data[1] not in self.db_index)
                node.setHidden(not visible)
                if needle and any_child:
                    node.setExpanded(True)
                return visible
            for i in range(self.db_tree.topLevelItemCount()):
                filter_node(self.db_tree.topLevelItem(i))
            return
        for i, section in enumerate(self.sections):
            item = self.db_tree.topLevelItem(i)
            haystack = section['name'] + '\t' + '\t'.join('\t'.join(r) for r in section['records'])
            show = not needle or needle in haystack.casefold()
            item.setHidden(not show)
            if needle and show:
                item.setExpanded(True)

    def choose_draft(self, name):
        self.current_draft = name if name in self.drafts else None
        self.refresh_draft()

    def add_selected(self, selection=None):
        if not self.current_draft and not self._can_create_list():
            QMessageBox.information(self, 'Open a configuration first',
                'Open a scanner configuration (File → Open Scanner Configuration…, or File → New Scanner '
                'Configuration…) to add to its Favorites Lists or create a new one.')
            return
        if selection is not None:
            source, index = selection
            try:
                section = self.db_index[source][index]
            except (KeyError, IndexError, TypeError):
                QMessageBox.warning(self, 'Unavailable', 'Selected system is not loaded.')
                return
        else:
            node = self.db_tree.currentItem()
            if node is None:
                QMessageBox.information(self, 'Select a system',
                                        'Choose a system from the System dropdown.')
                return
            while node is not None:
                data = node.data(0, Qt.ItemDataRole.UserRole)
                if isinstance(data, tuple) and data[0] == 'search_hit':
                    source, index = str(Path(self.source) / data[1]), data[2]
                    section = self.get_indexed_system(data[1], data[2])
                    if section is None:
                        QMessageBox.warning(self, 'Unavailable', 'Could not resolve parent system.')
                        return
                    break
                if isinstance(data, tuple) and data[0] == 'system':
                    source, index = data[1], data[2]
                    section = self.db_index[source][index]
                    break
                if isinstance(data, int) and data < len(self.sections):
                    source, index = self.source, data
                    section = self.sections[index]
                    break
                node = node.parent()
            else:
                QMessageBox.information(self, 'Select a system', 'Expand a state and select a system or department.')
                return
        key = (source, index)
        new_list_name = None
        while True:
            chooser = AddDestinationDialog(section['name'], list(self.drafts), self.current_draft,
                                           self._can_create_list(), self)
            if chooser.exec() != QDialog.DialogCode.Accepted:
                return
            mode, value = chooser.result_choice()
            if mode == 'new':
                try:
                    self.new_list_hooks['check'](value)
                except ValueError as exc:
                    QMessageBox.warning(self, 'New Favorites List', str(exc))
                    continue
                new_list_name = value
            elif value in self.drafts:
                if value != self.current_draft:
                    self.draft_choice.setCurrentText(value)
                self.current_draft = value
            else:
                QMessageBox.information(self, 'Choose a list', 'Choose a destination Favorites List.')
                continue
            break
        if new_list_name is not None:
            self._add_to_new_list(section, new_list_name)
            return
        draft = self.drafts[self.current_draft]
        if favorites_clipboard.is_native(draft):
            self._add_to_native_list(section, draft)
            return
        try:
            existing_entry, matched_by_name = find_existing_system(
                draft, key, section['records'][0])
        except AmbiguousFavoritesMatch as exc:
            QMessageBox.warning(self, 'Ambiguous Favorites system', str(exc))
            return
        if (existing_entry is not None and not matched_by_name and
                tuple(existing_entry['records'][0]) != tuple(section['records'][0])):
            QMessageBox.warning(self, 'Source mismatch',
                'Existing system header differs from this database source. No merge performed.')
            return
        target_note = ('\n\nDestination: EXISTING system and departments in this Favorites List.\n'
                       'The original scanner system and department headers will be preserved.'
                       if matched_by_name else '')
        # Fail closed: any trunk-like section or Site/T-Group record requires
        # explicit selection, never the old complete-system fallback.
        trunk_markers = {'Trunk', 'Trunked', 'Site', 'T-Group', 'TGID', 'Tgid', 'T-Id'}
        is_trunk = (str(section['kind']).strip() in trunk_markers or
                    any(r and str(r[0]).strip() in trunk_markers
                        for r in section['records']))
        if is_trunk:
            dialog = SelectTrunkDialog(section, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            chosen = dialog.selected()
            sites = [g for g in chosen if g['kind'] == 'Site']
            departments = [g for g in chosen if g['kind'] == 'T-Group']
            has_site = bool(existing_entry and any(r and r[0].strip() == 'Site'
                         for r in existing_entry['records']))
            has_department = bool(existing_entry and any(r and r[0].strip() == 'T-Group'
                               for r in existing_entry['records']))
            if (not sites and not has_site) or (not departments and not has_department):
                QMessageBox.warning(self, 'Incomplete selection',
                    'The combined draft must contain at least one site and one talkgroup department. '
                    'No changes were saved.')
                return
            selected_tgids = [r[5] for group in departments for r in group['records'][1:]
                              if r and r[0].strip() == 'TGID' and len(r) > 5]
            preview = (f'System: {section["name"]}\n'
                       f'Sites: {len(sites)}\n'
                       f'Talkgroup departments: {len(departments)}\n'
                       f'Individual talkgroups: {len(selected_tgids)}\n\n'
                       'Selected sites:\n' +
                       '\n'.join('  • ' + g['name'] for g in sites[:30]) +
                       ('\n  …' if len(sites) > 30 else '') +
                       '\n\nSave Configuration keeps it. Continue?')
            if QMessageBox.question(self, 'Preview selective trunk import', preview,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    ) != QMessageBox.StandardButton.Yes:
                return
            records = [section['records'][0].copy()]
            for group in chosen:
                records.extend(r.copy() for r in group['records'])
            candidate = {'key': list(key), 'name': section['name'], 'kind': section['kind'],
                         'records': records, 'selection_mode': 'selective_trunk_v1',
                         'selected_sites': [g['name'] for g in sites],
                         'selected_departments': [g['name'] for g in departments]}
            if existing_entry is not None:
                try:
                    added = merge_draft_entry(existing_entry, candidate)
                except AmbiguousFavoritesMatch as exc:
                    QMessageBox.warning(self, 'Ambiguous Favorites department', str(exc))
                    return
                self.status.setText(f'Merged trunked selection: {added} new records; existing records preserved.')
            else:
                draft.append(candidate)
                self.status.setText(f'Added {len(sites)} sites and '
                                    f'{len(departments)} talkgroup departments selected.')
            self.refresh_draft()
            return
        # Conventional imports require explicit checkbox selection and preview.
        dialog = SelectConventionalDialog(section, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        chosen = dialog.selected()
        if not chosen:
            QMessageBox.information(self, 'No channels selected',
                'Select at least one conventional channel. Nothing was added.')
            return
        if any(r and r[0].strip() == 'Rectangle' for group in chosen for r in group['records'][1:]):
            QMessageBox.information(self, 'Rectangle location',
                'A selected department uses a rectangle location. Rectangle locations can be added only by '
                'creating a new Favorites List, not by adding to an existing list or draft.')
            return
        count = sum(1 for group in chosen for r in group['records'][1:] if r and r[0].strip() != 'Rectangle')
        candidate_records = [section['records'][0].copy()]
        for group in chosen:
            candidate_records.extend(r.copy() for r in group['records'])
        if existing_entry is not None:
            from favorites_merge import merge_records
            try:
                candidate_records = native_conventional_candidate(existing_entry, candidate_records)
                _, new_count = merge_records(existing_entry['records'], candidate_records)
            except (AmbiguousFavoritesMatch, ValueError) as exc:
                QMessageBox.warning(self, 'Cannot add channel to existing department', str(exc))
                return
            if new_count == 0:
                QMessageBox.information(self, 'Already in Favorites draft',
                    'All selected departments and channels are already in this Favorites draft. '
                    'No records were added.')
                return
        preview = (f'System: {section["name"]}\nDepartments: {len(chosen)}\n'
                   f'Channels: {count}\n\n'
                   'Only checked departments and channels will be included.\n'
                   'This saves the selected channel to the local Favorites draft. Continue?' + target_note +
                   ('\nNew channels inherit the existing department channel template settings; '
                    'name and frequency come from the database selection.'
                    if existing_entry is not None and existing_entry.get('origin') == 'native-copy' else ''))
        if QMessageBox.question(self, 'Preview conventional selection', preview,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                ) != QMessageBox.StandardButton.Yes:
            return
        candidate = {'key': list(key), 'name': section['name'], 'kind': section['kind'],
                     'records': candidate_records, 'selection_mode': 'selective_conventional_v1',
                     'selected_departments': [group['name'] for group in chosen]}
        if existing_entry is not None:
            try:
                added = merge_draft_entry(existing_entry, candidate)
            except AmbiguousFavoritesMatch as exc:
                QMessageBox.warning(self, 'Ambiguous Favorites department', str(exc))
                return
            self.status.setText(f'Merged conventional selection: {added} new records; existing records preserved.')
        else:
            draft.append(candidate)
            self.status.setText(f'Added {count} channels in {len(chosen)} conventional departments. Save Configuration keeps them.')
        self.refresh_draft()

    def _confirm_low_risk(self, title, text):
        """Honours the 'ask before low-risk actions' preference; plain Yes/No when the window has none."""
        window = self.window()
        ask = getattr(window, 'confirm_low_risk', None)
        if ask is not None:
            return ask(title, text)
        return QMessageBox.question(self, title, text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def selected_section(self):
        """The database system chosen in the System dropdown / Database Contents, or None (v0.1.7)."""
        node = self.db_tree.currentItem()
        while node is not None:
            data = node.data(0, Qt.ItemDataRole.UserRole)
            try:
                if isinstance(data, tuple) and data[0] == 'search_hit':
                    return self.get_indexed_system(data[1], data[2])
                if isinstance(data, tuple) and data[0] == 'system':
                    return self.db_index[data[1]][data[2]]
                if isinstance(data, int) and data < len(self.sections):
                    return self.sections[data]
            except (KeyError, IndexError, TypeError):
                return None
            node = node.parent()
        return None

    def _can_create_list(self):
        return bool(self.new_list_hooks and self.new_list_hooks['available']())

    def _add_to_native_list(self, section, draft):
        """Add database channels or talkgroups to an existing Favorites List of a scanner configuration
        (v0.1.24). They are written in the scanner's own format, exactly as for a new list, then merged like
        Paste: into the same system (same name and type) and department when the list has them, otherwise as
        a new system; nothing already there is replaced, and clashing quick keys and number tags move to
        free numbers. Before, this added rows in the database's own layout, which Save then refused."""
        import copy as _copy
        chosen = self._choose_database_records(section)
        if chosen is None:
            return
        records, _summary, _made = chosen
        try:
            clip = favorites_clipboard.database_clip(records)
            trial = _copy.deepcopy(draft)
            result = favorites_clipboard.paste(trial, clip, (None, None), 'free')
        except (ValueError, favorites_clipboard.ClipboardError) as exc:
            QMessageBox.warning(self, 'Add to Favorites', f'{exc}\n\nNothing was added.')
            return
        if result['added'] == 0 and not result['new_system'] and not result['sites'] and not result['departments']:
            QMessageBox.information(self, 'Add to Favorites', f'Everything selected is already in '
                                    f'{self.current_draft}. Nothing was added.')
            return
        text = favorites_clipboard.summary(clip, result, self.current_draft)
        clashes = result.get('clashes') or []
        if clashes:
            text += (f'\n\n{len(clashes)} quick key(s) or number tag(s) were already used in this list; '
                     'they go to the next free numbers.')
        if QMessageBox.question(self, 'Add to Favorites', text + '\n\nSave Configuration keeps it. Continue?',
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                                ) != QMessageBox.StandardButton.Yes:
            return
        self._snapshot()
        favorites_clipboard.paste(draft, clip, (None, None), 'free')
        self.status.setText(f'Added to {self.current_draft}: ' + text.splitlines()[0] +
                            ' Save Configuration to keep it.')
        self.refresh_draft()

    def _choose_database_records(self, section):
        """Select conventional channels, or trunked sites and talkgroups. Returns (records, summary, made) in
        the database's layout, ready for new_favorites_list.build_new_list_rows, or None."""
        trunk_markers = {'Trunk', 'Trunked', 'Site', 'T-Group', 'TGID', 'Tgid', 'T-Id'}
        is_trunk = (str(section['kind']).strip() in trunk_markers or
                    any(r and str(r[0]).strip() in trunk_markers for r in section['records']))
        if is_trunk:
            dialog = SelectTrunkDialog(section, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return None
            chosen = dialog.selected()
            sites = [g for g in chosen if g['kind'] == 'Site']
            departments = [g for g in chosen if g['kind'] == 'T-Group']
            talkgroups = sum(1 for g in departments for r in g['records'][1:] if r and r[0].strip() != 'Rectangle')
            if not sites or not talkgroups:
                QMessageBox.information(self, 'Incomplete selection',
                    'Select at least one site frequency and one talkgroup. Nothing was added.')
                return None
            records = [section['records'][0].copy()]
            for group in sites:
                records.append(group['records'][0].copy())
                records.extend(r.copy() for r in group.get('bandplans', []))
                records.extend(r.copy() for r in group.get('rectangles', []))
                records.extend(r.copy() for r in group['records'][1:])
            for group in departments:
                records.extend(r.copy() for r in group['records'])
            summary = (f'System: {section["name"]}\nSites: {len(sites)}\n'
                       f'Talkgroup departments: {len(departments)}\nTalkgroups: {talkgroups}')
            made = (f'{len(sites)} sites, {len(departments)} departments, {talkgroups} talkgroups')
        else:
            dialog = SelectConventionalDialog(section, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return None
            chosen = dialog.selected()
            count = sum(1 for group in chosen for r in group['records'][1:] if r and r[0].strip() != 'Rectangle')
            if not chosen or count == 0:
                QMessageBox.information(self, 'No channels selected',
                    'Select at least one conventional channel. Nothing was added.')
                return None
            records = [section['records'][0].copy()]
            for group in chosen:
                records.extend(r.copy() for r in group['records'])
            summary = f'System: {section["name"]}\nDepartments: {len(chosen)}\nChannels: {count}'
            made = f'{count} channels in {len(chosen)} departments'
        return records, summary, made

    def _add_to_new_list(self, section, list_name):
        """Select conventional channels, or trunked sites and talkgroups, then create the new native list."""
        chosen = self._choose_database_records(section)
        if chosen is None:
            return
        records, summary, made = chosen
        if not self._confirm_low_risk('Create new Favorites List',
                f'Create the new Favorites List {list_name!r}?\n\n{summary}\n\n'
                'Settings other than the database values are left at the scanner defaults, '
                'never copied from another item, and can be edited afterwards.\n'
                'This changes the LOCAL configuration only; the scanner is not touched until you export. '
                'If anything fails, no list is created.',
                ):
            return
        try:
            name = self.new_list_hooks['create'](list_name, records)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            QMessageBox.warning(self, 'Favorites List not created', str(exc) + '\n\nNothing was changed.')
            return
        self.status.setText(f'Created Favorites List {list_name!r} with {made} '
                            '(local configuration; scanner unchanged).')
        if name in self.drafts:
            self.draft_choice.setCurrentText(name)
        self.refresh_draft()

    def configure_columns(self, tree, key):
        dialog = QDialog(self)
        dialog.setWindowTitle('Visible columns — ' + key)
        layout = QVBoxLayout(dialog)
        checks = []
        for index, (field, title) in enumerate(FAVORITES_FIELDS if key == 'favorites' else DISPLAY_FIELDS):
            check = QCheckBox(title)
            check.setChecked(not tree.isColumnHidden(index))
            if index == 0: check.setEnabled(False)
            checks.append(check)
            layout.addWidget(check)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            for index, (field, _) in enumerate(FAVORITES_FIELDS if key == 'favorites' else DISPLAY_FIELDS):
                visible = checks[index].isChecked()
                tree.setColumnHidden(index, not visible)
                if key == 'database':
                    self.detail_table.setColumnHidden(index, not visible)
                self.display_settings.setValue(f'columns/{key}/{field}', visible)

    def refresh_draft(self):
        self.draft_tree.clear()
        if self.favorites_files:
            loaded = QTreeWidgetItem(['Existing Favorites Lists (read-only)', 'Folder', '', '', '', ''])
            self.draft_tree.addTopLevelItem(loaded)
            for path in self.favorites_files:
                QTreeWidgetItem(loaded, [path.stem, 'Favorites List', '', '', '', ''])
        for i, section in enumerate(self.drafts.get(self.current_draft, [])):
            item = QTreeWidgetItem([section['name'], section['kind'], '', '', '', ''])
            item.setData(0, Qt.ItemDataRole.UserRole, i)
            self.draft_tree.addTopLevelItem(item)
            if section.get('selection_mode') == 'selective_conventional_v1':
                parent = None
                for row_index, record in enumerate(section['records'][1:], 1):
                    kind = record[0].strip() if record else ''
                    if kind == 'C-Group':
                        parent = QTreeWidgetItem(item, [record[3] if len(record)>3 else 'Department', 'C-Group', ''])
                        parent.setData(0, Qt.ItemDataRole.UserRole, ('draft_row', row_index))
                    elif kind in ('C-Freq', 'C-Channel', 'C-Frequency') and parent is not None:
                        leaf = QTreeWidgetItem(parent, record_columns(record))
                        leaf.setData(0, Qt.ItemDataRole.UserRole, ('draft_row', row_index))
                item.setToolTip(0, 'Conventional system in this Favorites List.')
            if section.get('selection_mode') == 'selective_trunk_v1':
                parent = None
                for row_index, record in enumerate(section['records'][1:], 1):
                    kind = record[0].strip() if record else ''
                    if kind in ('Site', 'T-Group'):
                        parent = QTreeWidgetItem(item, [
                            record[3] if len(record) > 3 else kind,
                            'Site' if kind == 'Site' else 'Talkgroup department', ''])
                        parent.setData(0, Qt.ItemDataRole.UserRole, ('draft_row', row_index))
                    elif kind in ('T-Freq','T-Frequency','T-Channel') and parent is not None:
                        leaf = QTreeWidgetItem(parent, record_columns(record))
                        leaf.setData(0, Qt.ItemDataRole.UserRole, ('draft_row', row_index))
                    elif kind == 'TGID' and parent is not None:
                        leaf = QTreeWidgetItem(parent, record_columns(record))
                        leaf.setData(0, Qt.ItemDataRole.UserRole, ('draft_row', row_index))
                item.setToolTip(0, 'Offline selective import. Expand to review sites and TGIDs.')

    def delete_selected(self):
        node = self.draft_tree.currentItem()
        if node is None or not self.current_draft:
            return
        index = node.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(index, int):
            QMessageBox.information(self, 'Read-only list', 'Existing Favorites Lists cannot be deleted here. Select a system from a draft.')
            return
        name = self.drafts[self.current_draft][index]['name']
        if QMessageBox.question(self, 'Remove from draft', f'Remove {name} from this draft?',
             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        del self.drafts[self.current_draft][index]
        self.refresh_draft()

