# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""The form for typing in a new system, department, channel or talkgroup (v0.1.7)."""
from PyQt6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QMessageBox

import hand_entry


class HandEntryDialog(QDialog):
    """mode: 'channel' or 'talkgroup'. system / department: ask for those names too."""

    def __init__(self, parent, title, mode='channel', system=False, department=True, note=''):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.mode = mode
        form = QFormLayout(self)
        if note:
            label = QLabel(note)
            label.setWordWrap(True)
            form.addRow(label)
        self.system = QLineEdit() if system else None
        self.department = QLineEdit() if department else None
        self.entry_name = QLineEdit()
        self.value = QLineEdit()
        if self.system is not None:
            form.addRow('System name', self.system)
        if self.department is not None:
            form.addRow('Department', self.department)
        for edit in (self.system, self.department, self.entry_name):
            if edit is not None:
                edit.setMaxLength(64)
        if mode == 'channel':
            self.value.setPlaceholderText('MHz, e.g. 155.250')
            self.modulation = QComboBox()
            self.modulation.addItems(hand_entry.MODULATIONS)
            self.tone = QLineEdit()
            self.tone.setPlaceholderText('optional: 107.2, 023 DPL, NAC 293, CC 1, RAN 4')
            form.addRow('Channel name' if not department else 'First channel', self.entry_name)
            form.addRow('Frequency', self.value)
            form.addRow('Modulation', self.modulation)
            form.addRow('Tone / NAC / colour code', self.tone)
        else:
            self.value.setPlaceholderText('decimal, e.g. 44358')
            form.addRow('Talkgroup name' if not department else 'First talkgroup', self.entry_name)
            form.addRow('Talkgroup ID', self.value)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._check)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.result_values = None

    def values(self):
        """{'system', 'department', 'channel' or ('talkgroup', 'tgid')}; raises hand_entry.EntryError."""
        out = {}
        if self.system is not None:
            out['system'] = hand_entry.name(self.system.text(), 'system')
        if self.department is not None:
            out['department'] = hand_entry.name(self.department.text(), 'department')
        if self.mode == 'channel':
            out['channel'] = hand_entry.channel(self.entry_name.text(), self.value.text(),
                                                self.modulation.currentText(), self.tone.text())
        else:
            out['talkgroup'] = hand_entry.name(self.entry_name.text(), 'talkgroup')
            out['tgid'] = hand_entry.talkgroup_id(self.value.text())
        return out

    def _check(self):
        try:
            self.result_values = self.values()
        except hand_entry.EntryError as exc:
            QMessageBox.information(self, self.windowTitle(), str(exc))
            return
        self.accept()
