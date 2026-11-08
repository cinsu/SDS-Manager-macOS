# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Offline-only loss-minimizing raw .hpd editor; never writes to source."""
from pathlib import Path
from dataclasses import dataclass
import hashlib
import os
import tempfile
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QMessageBox, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QLineEdit, QHeaderView)
from favorites_explorer import read_text, MAX_BYTES, detect_mounts

@dataclass
class Snapshot:
    rows: list

def is_on_removable(path):
    """Fail closed when output is within a currently detected USB mount."""
    resolved = Path(path).resolve()
    for mount in detect_mounts():
        root = Path(mount).resolve()
        if resolved == root or root in resolved.parents:
            return True
    return False

class FavoritesEditor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.source = None
        self.encoding = "utf-8"
        self.newline = "\n"
        self.final_newline = True
        self.original_hash = None
        self.rows = []
        self.history = []
        self.history_index = -1
        self.updating = False
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setMinimumSectionSize(85)
        self.table.itemChanged.connect(self.cell_changed)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Find rows by any field (view filter only)")
        self.filter.textChanged.connect(self.filter_rows)
        self.status = QLabel("Offline editor: open a local .hpd file. Saves only to a new local path.")
        self.status.setWordWrap(True)
        root = QVBoxLayout(self)
        actions = QHBoxLayout()
        for name, callback in (
            ("Open local .hpd", self.open_file),
            ("Save As…", self.save_as),
            ("Undo", self.undo),
            ("Redo", self.redo),
            ("Add row", self.add_row),
            ("Delete selected", self.delete_rows),
            ("Validate", self.validate_dialog),
        ):
            btn = QPushButton(name)
            btn.clicked.connect(callback)
            actions.addWidget(btn)
        root.addLayout(actions)
        note = QLabel("Edit raw tab-separated fields. Field 1 is record type. "
                      "Unknown fields are preserved; this is not yet a schema-aware channel editor. "
                      "The source file and scanner SD card are never written.")
        note.setWordWrap(True)
        root.addWidget(note)
        root.addWidget(self.filter)
        root.addWidget(self.table, 1)
        root.addWidget(self.status)

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open offline Favorites List", str(Path.home()),
            "Favorites Lists (*.hpd);;All files (*)")
        if not path:
            return
        if self.source and self.is_dirty():
            result = QMessageBox.question(self, "Discard unsaved edits?",
                "Opening another file discards unsaved edits. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if result != QMessageBox.StandardButton.Yes:
                return
        try:
            source = Path(path).resolve(strict=True)
            text, encoding = read_text(source)
            # splitlines() preserves field data; recognize original line-ending convention
            newline = "\r\n" if "\r\n" in text else "\r" if "\r" in text else "\n"
            lines = text.splitlines()
            rows = [line.split("\t") for line in lines]
            if any("\x00" in line for line in lines):
                raise ValueError("Binary/NUL data is not a valid text Favorites List")
            self.source = source
            self.original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            self.encoding = encoding
            self.newline = newline
            self.final_newline = text.endswith(("\r", "\n"))
            self.rows = rows
            self.history = []
            self.history_index = -1
            self.push_history()
            self.rebuild()
        except (OSError, ValueError, UnicodeError) as exc:
            QMessageBox.critical(self, "Unable to open", str(exc))

    def push_history(self):
        snap = Snapshot([row.copy() for row in self.rows])
        if self.history_index >= 0 and snap.rows == self.history[self.history_index].rows:
            return
        self.history = self.history[:self.history_index + 1]
        self.history.append(snap)
        if len(self.history) > 80:
            self.history.pop(0)
        self.history_index = len(self.history) - 1

    def is_dirty(self):
        return bool(self.history and self.rows != self.history[0].rows)

    def rebuild(self):
        self.updating = True
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.rows))
        columns = max((len(r) for r in self.rows), default=1)
        self.table.setColumnCount(columns)
        self.table.setHorizontalHeaderLabels(
            ["Record type" if i == 0 else f"Field {i+1}" for i in range(columns)])
        for r, fields in enumerate(self.rows):
            for c in range(columns):
                value = fields[c] if c < len(fields) else ""
                item = QTableWidgetItem(value)
                if c >= len(fields):
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    item.setToolTip("Field not present in this record; add a row to define fields")
                self.table.setItem(r, c, item)
        self.table.blockSignals(False)
        self.updating = False
        self.filter_rows(self.filter.text())
        self.update_status()

    def cell_changed(self, item):
        if self.updating or not self.source:
            return
        r, c = item.row(), item.column()
        if r >= len(self.rows) or c >= len(self.rows[r]):
            return
        value = item.text()
        if any(char in value for char in ("\r", "\n", "\t", "\x00")):
            QMessageBox.warning(self, "Invalid field", "Tabs, newlines and NUL bytes are not allowed within a field.")
            self.rebuild()
            return
        self.rows[r][c] = value
        self.push_history()
        self.update_status()

    def add_row(self):
        if not self.source:
            QMessageBox.information(self, "Open a file", "Open a local Favorites List first.")
            return
        if self.filter.text():
            self.filter.clear()
        selection = self.table.currentRow()
        pos = selection + 1 if selection >= 0 else len(self.rows)
        self.rows.insert(pos, ["", ""])
        self.push_history()
        self.rebuild()
        self.table.selectRow(pos)

    def delete_rows(self):
        selected = sorted({x.row() for x in self.table.selectedIndexes()}, reverse=True)
        if not selected:
            return
        if QMessageBox.question(self, "Delete records",
            f"Delete {len(selected)} selected raw record(s)? This may break .hpd structure.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        for i in selected:
            del self.rows[i]
        self.push_history()
        self.rebuild()

    def undo(self):
        if self.history_index > 0:
            self.history_index -= 1
            self.rows = [r.copy() for r in self.history[self.history_index].rows]
            self.rebuild()

    def redo(self):
        if self.history_index + 1 < len(self.history):
            self.history_index += 1
            self.rows = [r.copy() for r in self.history[self.history_index].rows]
            self.rebuild()

    def filter_rows(self, text):
        needle = text.casefold().strip()
        for index, row in enumerate(self.rows):
            self.table.setRowHidden(index, bool(needle and
                needle not in "\t".join(row).casefold()))

    def validate(self):
        issues = []
        if not self.source:
            return ["No file loaded"]
        if not self.rows:
            issues.append("File has no records")
        for i, row in enumerate(self.rows, 1):
            if not row or not row[0].strip():
                issues.append(f"Line {i}: missing record type")
            if any("\t" in x or "\r" in x or "\n" in x or "\x00" in x for x in row):
                issues.append(f"Line {i}: invalid control character")
        return issues

    def validate_dialog(self):
        issues = self.validate()
        QMessageBox.information(self, "Basic validation",
            "\n".join(issues[:25]) + ("\n…and more" if len(issues) > 25 else "")
            if issues else "Basic raw-record checks passed. "
            "This does NOT guarantee that the file is valid for the SDS100.")

    def save_as(self):
        if not self.source:
            QMessageBox.information(self, "Open a file", "Open a local Favorites List first.")
            return
        issues = self.validate()
        if issues:
            QMessageBox.warning(self, "Validation errors",
                "Cannot save until basic validation errors are fixed:\n" +
                "\n".join(issues[:15]))
            return
        suggested = self.source.with_name(self.source.stem + "_edited.hpd")
        path, _ = QFileDialog.getSaveFileName(self, "Save edited copy (local disk only)",
                                              str(suggested), "Favorites Lists (*.hpd)")
        if not path:
            return
        output = Path(path).expanduser().resolve()
        if output.suffix.lower() != ".hpd":
            QMessageBox.warning(self, "File extension", "Output must have a .hpd extension.")
            return
        if output == self.source or output.exists():
            QMessageBox.warning(self, "Choose a new filename",
                "For safety, Save As requires a new filename and never overwrites files.")
            return
        if is_on_removable(output):
            QMessageBox.warning(self, "Scanner/USB storage blocked",
                "Offline editor cannot save to a removable USB mount. Save to your local disk.")
            return
        try:
            current_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
            if current_hash != self.original_hash:
                QMessageBox.warning(self, "Source changed",
                    "The source file changed since opening. Reload it before saving.")
                return
            content = self.newline.join("\t".join(row) for row in self.rows)
            if self.final_newline:
                content += self.newline
            payload = content.encode(self.encoding)
            if len(payload) > MAX_BYTES:
                raise ValueError("Edited file exceeds 25 MB safety limit")
            # Exclusive creation ensures a file cannot be silently overwritten.
            fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                output.unlink(missing_ok=True)
                raise
            self.status.setText(f"Saved offline copy: {output} (source unchanged)")
            QMessageBox.information(self, "Saved", f"Created edited copy:\n{output}\n\n"
                "Do not copy it to the scanner until its structure is validated.")
        except (OSError, UnicodeError, ValueError) as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def update_status(self):
        if self.source:
            self.status.setText(f"{self.source.name} | {len(self.rows)} records | "
                f"{self.encoding} | {'Modified' if self.is_dirty() else 'Unmodified'} | "
                "Save As creates a new local file only.")
