# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Read-only SDS100 Favorites List explorer. Never writes to source media."""
from pathlib import Path
from datetime import datetime
import csv
import os
import shutil
import subprocess
import json
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QFileDialog, QMessageBox, QLineEdit, QComboBox)
from PyQt6.QtCore import Qt

MAX_BYTES = 25 * 1024 * 1024


def detect_mounts():
    """List likely removable mount points, without automatically reading/writing them."""
    import mac_platform
    if mac_platform.IS_MAC:
        return mac_platform.removable_mounts()
    found = []
    try:
        result = subprocess.run(['lsblk', '-J', '-o', 'NAME,TRAN,RM,MOUNTPOINTS,LABEL'],
                                capture_output=True, text=True, timeout=4, check=True)
        def walk(dev, inherited=False):
            removable = inherited or dev.get('tran') == 'usb' or str(dev.get('rm')) == '1'
            for mount in dev.get('mountpoints') or []:
                if removable and mount and Path(mount).is_dir():
                    found.append(mount)
            for child in dev.get('children') or []:
                walk(child, removable)
        for dev in json.loads(result.stdout).get('blockdevices', []):
            walk(dev)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return sorted(set(found))


def find_favorites(root):
    """Search known SD-card programming locations without unbounded recursion."""
    root = Path(root)
    candidates = [root / 'BCDx36HP' / 'favorite_lists',
                  root / 'BCDx36HP' / 'Favorites_Lists',
                  root / 'favorite_lists', root / 'Favorites_Lists', root]
    for folder in candidates:
        if folder.is_dir():
            files = sorted(x for x in folder.iterdir() if x.is_file() and x.suffix.lower() == '.hpd')
            if files:
                return folder, files
    return None, []


def read_text(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('File exceeds 25 MB safety limit')
    raw = path.read_bytes()
    for encoding in ('utf-8-sig', 'cp1252'):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode('latin-1'), 'latin-1'


def parse_hpd(path):
    """Conservative, non-mutating tab-separated record browser; no semantic rewriting."""
    text, encoding = read_text(path)
    records = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        columns = line.split('\t')
        # Preserve every field; only label types when explicit first token exists.
        kind = columns[0].strip() or '(blank type)'
        name = next((c.strip() for c in columns[1:] if c.strip()), '')
        records.append((number, kind, name, columns))
    return records, encoding


class FavoritesExplorer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.files = []
        self.source_root = None
        self.mounts = QComboBox()
        self.mounts.setMinimumWidth(220)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['Record / file', 'Name / first field', 'Details'])
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Filter filenames, records and fields...')
        self.search.textChanged.connect(self.filter_tree)
        self.status = QLabel('Read-only mode. Choose local .hpd files or a scanner mount.')
        self.status.setWordWrap(True)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        refresh = QPushButton('Detect USB storage')
        refresh.clicked.connect(self.refresh_mounts)
        top.addWidget(refresh)
        top.addWidget(self.mounts, 1)
        load = QPushButton('Read selected storage')
        load.clicked.connect(self.load_mount)
        top.addWidget(load)
        layout.addLayout(top)
        row = QHBoxLayout()
        local = QPushButton('Open local .hpd files')
        local.clicked.connect(self.open_files)
        row.addWidget(local)
        folder = QPushButton('Open folder / mounted SD card')
        folder.clicked.connect(self.open_folder)
        row.addWidget(folder)
        backup = QPushButton('Back up loaded files')
        backup.clicked.connect(self.backup)
        row.addWidget(backup)
        layout.addLayout(row)
        layout.addWidget(self.search)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.status)
        self.refresh_mounts()

    def refresh_mounts(self):
        self.mounts.clear()
        mounts = detect_mounts()
        self.mounts.addItems(mounts)
        if not mounts:
            self.mounts.addItem('(No removable mounted storage detected)')

    def load_mount(self):
        root = Path(self.mounts.currentText())
        if root.is_dir():
            self.load_folder(root)
        else:
            QMessageBox.information(self, 'No mounted device',
                'Connect the scanner in Mass Storage mode and mount its card, '
                'or choose Open folder to browse it manually.')

    def open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Choose Favorites List folder or SD card mount')
        if folder:
            self.load_folder(Path(folder))

    def open_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Open Favorites Lists', '',
                                               'Favorites Lists (*.hpd);;All files (*)')
        if paths:
            self.source_root = None
            self.load_files([Path(x) for x in paths])

    def load_folder(self, root):
        folder, files = find_favorites(root)
        if not files:
            QMessageBox.information(self, 'No .hpd files found',
                'No Favorites List .hpd files were found in the standard folder locations. '
                'You can open individual files manually.')
            return
        self.source_root = root
        self.load_files(files)

    def load_files(self, paths):
        self.tree.clear()
        self.files = []
        errors = []
        record_count = 0
        for path in paths:
            try:
                records, encoding = parse_hpd(path)
                self.files.append(path)
                parent = QTreeWidgetItem([path.name, f'{len(records)} records', encoding])
                parent.setData(0, Qt.ItemDataRole.UserRole, ' '.join([path.name, str(path)]).lower())
                self.tree.addTopLevelItem(parent)
                for line_no, kind, name, cols in records:
                    item = QTreeWidgetItem([f'{line_no}: {kind}', name, ' | '.join(cols[2:])[:350]])
                    item.setToolTip(2, ' | '.join(cols))
                    item.setData(0, Qt.ItemDataRole.UserRole, ' '.join(cols).lower())
                    parent.addChild(item)
                record_count += len(records)
            except (OSError, ValueError) as exc:
                errors.append(f'{path.name}: {exc}')
        self.status.setText(f'Read-only: {len(self.files)} file(s), {record_count} raw records. '
            'Record fields are shown without assuming undocumented column meanings. '
            + ('Errors: ' + '; '.join(errors) if errors else ''))
        self.filter_tree(self.search.text())

    def filter_tree(self, query):
        needle = query.casefold().strip()
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            any_visible = False
            for j in range(parent.childCount()):
                child = parent.child(j)
                show = not needle or needle in child.data(0, Qt.ItemDataRole.UserRole).casefold()
                child.setHidden(not show)
                any_visible |= show
            matched_parent = needle in parent.data(0, Qt.ItemDataRole.UserRole).casefold()
            parent.setHidden(not (any_visible or matched_parent))
            parent.setExpanded(bool(needle))

    def backup(self):
        if not self.files:
            QMessageBox.information(self, 'Nothing loaded', 'Open Favorites Lists first.')
            return
        destination = QFileDialog.getExistingDirectory(self, 'Choose backup destination (not scanner storage)')
        if not destination:
            return
        target = Path(destination).resolve()
        # Prevent source/destination overlap, including selecting a parent of scanner mount.
        for source in self.files:
            source = source.resolve()
            if target == source.parent or target in source.parents or source.parent == target:
                QMessageBox.warning(self, 'Unsafe destination',
                    'Select a separate local backup directory, not the source location.')
                return
        if self.source_root:
            mount = self.source_root.resolve()
            if target == mount or mount in target.parents:
                QMessageBox.warning(self, 'Unsafe destination',
                    'Do not back up onto the scanner SD card. Choose a local directory.')
                return
        backup_dir = target / ('SDS100_Favorites_Backup_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
        backup_dir.mkdir(parents=True, exist_ok=False)
        try:
            for source in self.files:
                shutil.copy2(source, backup_dir / source.name)
        except OSError as exc:
            QMessageBox.critical(self, 'Backup incomplete', str(exc))
            return
        QMessageBox.information(self, 'Backup created', f'Copied {len(self.files)} files to:\n{backup_dir}')
