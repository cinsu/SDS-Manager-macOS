# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Scanner Settings → Update Scanner Firmware… (the window; the work is in scanner_firmware.py)."""
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QFileDialog, QGroupBox, QHBoxLayout,
                             QHeaderView, QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
                             QVBoxLayout)

import scanner_firmware as sf
from edition import PERSONAL
from managed_storage import ROOT

DOWNLOADS = ROOT / 'firmware'
RECEIPTS = ROOT / 'firmware' / 'receipts'
STEPS = ('<b>What happens next.</b> The files are placed in the card\'s <code>BCDx36HP/firmware</code> folder — '
         'the same thing Sentinel does. Then:<ol>'
         '<li>Eject (safely remove) the scanner in your file manager and wait until it says it can be removed.</li>'
         '<li>Unplug the USB cable. The scanner starts from its own card, checks each file is for this model and '
         'that its checksum is good, and installs it. Follow any prompts on its screen.</li>'
         '<li><b>Do not turn the scanner off or let the battery run down while it updates.</b> If nothing happens, '
         'turn it off and on once.</li>'
         '<li>The scanner deletes the files when it has installed them. Connect it again and the Scanner panel '
         'shows the new version.</li></ol>')


class FirmwareDialog(QDialog):
    COLUMNS = ['Use', 'Type', 'Version', 'File', 'From', 'Compared with the scanner']

    def __init__(self, main):
        super().__init__(main)
        self.main = main          # (not self.window: that would hide QWidget.window())
        self.setWindowTitle('Update Scanner Firmware')
        self.resize(900, 620)
        self.location = ''
        self.info = None
        self.rows = []            # [{'kind','label','name','version', 'candidate' or None, 'from'}]
        layout = QVBoxLayout(self)

        box = QGroupBox('SCANNER')
        b = QVBoxLayout(box)
        self.scanner_label = QLabel('No scanner chosen.')
        self.scanner_label.setWordWrap(True)
        self.scanner_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        b.addWidget(self.scanner_label)
        row = QHBoxLayout()
        choose = QPushButton('Choose Scanner…')
        choose.clicked.connect(self.choose_scanner)
        row.addWidget(choose)
        row.addStretch(1)
        b.addLayout(row)
        layout.addWidget(box)

        files = QGroupBox('FIRMWARE FILES')
        f = QVBoxLayout(files)
        row = QHBoxLayout()
        add = QPushButton('Add File…')
        add.setToolTip('A .bin or .firm file, or the .zip from Uniden\'s support page')
        add.clicked.connect(self.add_file)
        row.addWidget(add)
        row.addStretch(1)
        f.addLayout(row)
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        f.addWidget(self.table, 1)
        self.list_note = QLabel('' if PERSONAL else
                                'Download the firmware from Uniden\'s support page (info.uniden.com → SDS100 '
                                'Firmware Update), then use Add File… with the .zip, .bin or .firm file.')
        self.list_note.setWordWrap(True)
        f.addWidget(self.list_note)
        layout.addWidget(files, 1)

        steps = QLabel(STEPS)
        steps.setWordWrap(True)
        steps.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(steps)
        row = QHBoxLayout()
        row.addStretch(1)
        self.write_btn = QPushButton('Write to Scanner…')
        self.write_btn.clicked.connect(self.write)
        row.addWidget(self.write_btn)
        close = QPushButton('Close')
        close.clicked.connect(self.reject)
        row.addWidget(close)
        layout.addLayout(row)
        self.update_buttons()

    # ---- scanner ---------------------------------------------------------------------------------
    def choose_scanner(self):
        location = self.main.pick_scanner_folder('Update Scanner Firmware — choose the SDS100 SD card')
        if not location:
            return
        try:
            info = sf.card_info(location)
        except (sf.FirmwareError, OSError) as exc:
            QMessageBox.warning(self, 'Update Scanner Firmware', str(exc))
            return
        self.location, self.info = location, info
        waiting = (f'<br><b>Already waiting in the firmware folder:</b> {", ".join(info["waiting"])}'
                   if info['waiting'] else '')
        if info.get('other_files'):
            waiting += (f'<br>Also in the firmware folder (not firmware, left alone): '
                        f'{", ".join(info["other_files"])}')
        self.scanner_label.setText(f'<b>{info["model"]}</b> • main firmware <b>{info["firmware"] or "unknown"}</b>'
                                   f' • card {Path(info["root"]).parent}{waiting}')
        self.rows = [r for r in self.rows if sf.parse_name(r['name'], info['model'])]
        self.fill()

    def ensure_scanner(self):
        if self.info is None:
            self.choose_scanner()
        return self.info is not None

    # ---- files -----------------------------------------------------------------------------------

    def tick_newest(self):
        current = self.info.get('version') if self.info else None
        for kind in ('main', 'sub'):
            options = [r for r in self.rows if r['kind'] == kind]
            if not options:
                continue
            newest = max(options, key=lambda r: r['version'])
            if any(r.get('ticked') for r in options):
                continue
            if kind == 'main' and current and newest['version'] <= current:
                continue
            newest['ticked'] = True

    def add_file(self):
        if not self.ensure_scanner():
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Add firmware file', str(Path.home() / 'Downloads'),
                                              'SDS firmware (*.bin *.firm *.zip)')
        if not path:
            return
        try:
            found = sf.load_local(path, self.info['model'])
        except (sf.FirmwareError, OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Add File', str(exc))
            return
        for c in found:
            self.rows = [r for r in self.rows if r['name'] != c['name']]
            self.rows.append({'kind': c['kind'], 'label': c['label'], 'name': c['name'], 'version': c['version'],
                              'candidate': c, 'origin': Path(path).name, 'ticked': True})
            for r in self.rows:                       # only one of each kind ticked
                if r['kind'] == c['kind'] and r['name'] != c['name']:
                    r['ticked'] = False
        self.fill()

    def fill(self):
        current = self.info.get('version') if self.info else None
        self.rows.sort(key=lambda r: (r['kind'], r['version']), reverse=True)
        t = self.table
        t.setRowCount(len(self.rows))
        for i, r in enumerate(self.rows):
            box = QCheckBox()
            box.setChecked(bool(r.get('ticked')))
            box.toggled.connect(lambda on, row=r: self.toggled(row, on))
            t.setCellWidget(i, 0, box)
            if r['kind'] == 'main' and current:
                compare = ('newer' if r['version'] > current else 'same version' if r['version'] == current
                           else 'OLDER (downgrade)')
            else:
                compare = 'sub firmware (current sub version not recorded on the card)' if r['kind'] == 'sub' else ''
            for c, value in enumerate(('Main' if r['kind'] == 'main' else 'Sub', r['label'], r['name'],
                                       r['origin'], compare), start=1):
                t.setItem(i, c, QTableWidgetItem(value))
        self.update_buttons()

    def toggled(self, row, on):
        row['ticked'] = on
        if on:
            for r in self.rows:
                if r is not row and r['kind'] == row['kind'] and r.get('ticked'):
                    r['ticked'] = False
            self.fill()
        self.update_buttons()

    def update_buttons(self):
        self.write_btn.setEnabled(any(r.get('ticked') for r in self.rows))

    # ---- writing ---------------------------------------------------------------------------------
    def write(self):
        if getattr(self.main, '_db_update_busy', False):
            QMessageBox.information(self, 'Update in progress', 'Wait for the current scanner operation to finish.')
            return
        if not self.ensure_scanner():
            return
        chosen = [r for r in self.rows if r.get('ticked')]
        missing = [r for r in chosen if r['candidate'] is None]
        if missing:
            QMessageBox.warning(self, 'Update Scanner Firmware', 'Add the firmware files with Add File… first.')
            return
        self.confirm(chosen)

    def downloaded(self, chosen, error):
        if error:
            for r in chosen:
                if r['origin'] == 'Uniden server':
                    r['candidate'] = None
            QMessageBox.warning(self, 'Update Scanner Firmware', error)
            return
        self.confirm(chosen)

    def confirm(self, chosen):
        candidates = [r['candidate'] for r in chosen]
        try:
            plan = sf.plan(self.location, candidates)
        except (sf.FirmwareError, OSError) as exc:
            QMessageBox.warning(self, 'Update Scanner Firmware — blocked', str(exc) + '\n\nNothing was written.')
            return
        files = ''.join(f'\n  • {c["name"]}  ({c["size"]:,} bytes, SHA-256 {c["sha256"][:16]}…)' for c in plan['files'])
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle('Update Scanner Firmware — confirm')
        box.setText('\n'.join(plan['notes']) + '\n\nThese files will be written to the scanner\'s firmware folder:'
                    + files + '\n\nThe scanner installs them the next time it starts from its own card, after you '
                    'eject it and unplug the USB cable. Do not turn it off while it updates.\n\nContinue?')
        if plan['leftovers']:
            leftover = QCheckBox('Remove the files already waiting in the firmware folder: '
                                 + ', '.join(plan['leftovers']) + ' (otherwise the scanner tries those too)')
            leftover.setChecked(True)
            box.setCheckBox(leftover)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        remove = box.checkBox().isChecked() if plan['leftovers'] else True
        if plan['downgrade']:
            answer = QMessageBox.warning(
                self, 'Update Scanner Firmware — older version',
                'You chose main firmware OLDER than the scanner has. Uniden doesn\'t support going back, and '
                'settings or the database may not suit the older version.\n\nWrite the older firmware anyway?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.main._db_update_busy = True
        self.main.statusBar().showMessage('Writing firmware files to the scanner. DO NOT DISCONNECT.')
        location = self.location
        self.main._run_background('Update Scanner Firmware — WRITING',
                                    'Writing and verifying the firmware files. DO NOT DISCONNECT THE SCANNER.',
                                    lambda: sf.execute(location, candidates, remove, log_folder=RECEIPTS),
                                    self.write_finished)

    def write_finished(self, result, error):
        self.main._db_update_busy = False
        self.main.statusBar().clearMessage()
        if error or not result:
            QMessageBox.critical(self, 'Update Scanner Firmware — FAILED',
                                 (error or 'Unknown result.') + '\n\nCheck the BCDx36HP/firmware folder on the card '
                                 'before ejecting: delete any partial firmware file there so the scanner doesn\'t '
                                 'try to install it.')
            return
        removed = (f'\nRemoved leftover file(s): {", ".join(result["removed"])}' if result['removed'] else '')
        box = QMessageBox(self)
        box.setWindowTitle('Update Scanner Firmware — ready')
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(f'Written and verified: <b>{", ".join(result["written"])}</b>{removed}<br><br>' + STEPS)
        box.exec()
        try:
            self.main.refresh_scanner_panel()
        except Exception:
            pass
        self.accept()
