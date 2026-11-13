# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Windows and the local connection for the SDS100 Monitor link (see monitor_link.py)."""
import json
import threading

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
                             QDialogButtonBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                             QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

import monitor_link


def send_to_running(request, timeout_ms=800):
    """Hand a request to a Manager that is already running. True if it took it."""
    socket = QLocalSocket()
    socket.connectToServer(monitor_link.SERVER_NAME)
    if not socket.waitForConnected(timeout_ms):
        return False
    socket.write((json.dumps(request) + "\n").encode("utf-8"))
    socket.flush()
    socket.waitForBytesWritten(timeout_ms)
    answered = socket.waitForReadyRead(timeout_ms * 2)
    socket.disconnectFromServer()
    return answered


class LinkServer(QObject):
    """Listens for requests from SDS100 Monitor (this computer, this user only)."""
    received = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._connection)
        self.buffers = {}

    def start(self):
        if self.server.listen(monitor_link.SERVER_NAME):
            return True
        # A server left behind by a crashed Manager: only remove it if nobody answers on it.
        probe = QLocalSocket()
        probe.connectToServer(monitor_link.SERVER_NAME)
        if probe.waitForConnected(300):
            probe.disconnectFromServer()
            return False                          # another Manager is running and owns it
        QLocalServer.removeServer(monitor_link.SERVER_NAME)
        return self.server.listen(monitor_link.SERVER_NAME)

    def _connection(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            self.buffers[socket] = b""
            socket.readyRead.connect(lambda s=socket: self._read(s))
            socket.disconnected.connect(lambda s=socket: (self.buffers.pop(s, None), s.deleteLater()))

    def _read(self, socket):
        data = self.buffers.get(socket, b"") + bytes(socket.readAll())
        if len(data) > 8192:                      # nothing legitimate is this long
            socket.abort()
            return
        if b"\n" not in data:
            self.buffers[socket] = data
            return
        line = data.split(b"\n", 1)[0]
        request = monitor_link.clean_request(line.decode("utf-8", "replace"))
        socket.write(b"ok\n" if request else b"ignored\n")
        socket.flush()
        if request:
            self.received.emit(request)


class MonitorLinkMixin:
    """For ManagerWindow: answering the Monitor's Edit in Manager, and Name Unnamed Talkgroups."""

    def start_monitor_link(self):
        self._link_server = LinkServer(self)
        self._link_server.received.connect(lambda req: QTimer.singleShot(0, lambda: self.open_monitor_request(req)))
        if not self._link_server.start():
            self.statusBar().showMessage('Another Manager is answering SDS100 Monitor.', 8000)

    def open_monitor_request(self, request):
        """Open the Favorites List editor on the channel or talkgroup the Monitor asked about, or (v0.1.18)
        add one the Monitor heard to a Favorites List."""
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()
        if request.get('action') == 'show':
            return
        what = monitor_link.describe_request(request)
        if request.get('action') == 'add':
            self.add_heard_entry(request, what)
            return
        if request.get('action') == 'rr_freq':          # v0.1.28
            if request.get('frequency'):
                self.search_rr_frequency(request['frequency'], request.get('tone', ''))
            return
        if QApplication.activeModalWidget() is not None:
            QMessageBox.information(self, 'Edit in Manager',
                                    f'SDS100 Monitor asked for {what}.\n\nClose the window that is open in the '
                                    'Manager first, then use Edit in Manager again.')
            return
        drafts = self.workspace.drafts
        if not any(entries for entries in drafts.values()):
            if QMessageBox.question(self, 'Edit in Manager',
                                    f'SDS100 Monitor asked for {what}.\n\nOpen a scanner configuration to find it in?') \
                    != QMessageBox.StandardButton.Yes:
                return
            self.show_scanner_configurations()
            drafts = self.workspace.drafts
            if not any(entries for entries in drafts.values()):
                return
        matches = monitor_link.find_entries(drafts, request)
        if not matches:
            QMessageBox.information(self, 'Edit in Manager',
                                    f'{what[0].upper() + what[1:]} is not in the open configuration\'s Favorites '
                                    'Lists.\n\nTo add it, find it in the database (Tools → Find Everywhere…) and '
                                    'use Add to Favorites.')
            return
        match = monitor_link.pick_match(matches)
        if match is None:
            labels = [m['label'] for m in matches[:30]]
            choice, ok = QInputDialog.getItem(self, 'Edit in Manager', f'{what[0].upper() + what[1:]} is in '
                                              f'{len(matches)} places. Open which?', labels, 0, False)
            if not ok:
                return
            match = matches[labels.index(choice)]
        self.open_list_editor_at(match)

    def search_rr_frequency(self, frequency='', tone=''):
        """Tools → Search Frequency in RadioReference…, or SDS100 Monitor's request (v0.1.28)."""
        from rr_freq_dialog import FrequencySearchDialog
        dialog = getattr(self, '_rr_freq_dialog', None)
        if dialog is None:
            dialog = self._rr_freq_dialog = FrequencySearchDialog(self)
        dialog.start(frequency, tone)

    def add_heard_entry(self, request, what):
        title = 'Add to Favorites List'
        if QApplication.activeModalWidget() is not None:
            QMessageBox.information(self, title, f'SDS100 Monitor asked to add {what}.\n\nClose the window that is '
                                    'open in the Manager first, then try again.')
            return
        drafts = self.workspace.drafts
        if not any(entries for entries in drafts.values()):
            if QMessageBox.question(self, title, f'SDS100 Monitor asked to add {what}.\n\nOpen a scanner '
                                    'configuration to add it to?') != QMessageBox.StandardButton.Yes:
                return
            self.show_scanner_configurations()
            drafts = self.workspace.drafts
        existing = monitor_link.find_entries(drafts, request)
        if existing and QMessageBox.question(
                self, title, f'{what[0].upper() + what[1:]} is already in {existing[0]["label"]}'
                + (f' and {len(existing) - 1} other place(s)' if len(existing) > 1 else '') + '.\n\nAdd it again '
                'somewhere else?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        targets = monitor_link.add_targets(drafts, request)
        if not targets:
            QMessageBox.information(self, title, 'There is no ' + ('talkgroup department in a trunked system '
                                    'that already has a talkgroup' if request['tgid'] else 'conventional department')
                                    + ' in the open Favorites Lists. Make one in Edit Favorites List '
                                    '(New Department… or New Conventional System…), then try again.')
            return
        dialog = AddHeardDialog(self, request, what, targets)
        while dialog.exec() == QDialog.DialogCode.Accepted:
            target = targets[dialog.target.currentIndex()]
            try:
                self.workspace._snapshot()
                row = monitor_link.add_heard(drafts, target, request, dialog.name.text(),
                                             dialog.modulation.currentText(), dialog.tone.text())
            except (ValueError, StopIteration) as exc:
                if getattr(self.workspace, '_undo', None):
                    self.workspace._undo.pop()              # nothing changed: drop the Undo step again
                QMessageBox.information(self, title, str(exc) or 'It could not be added there.')
                continue
            self.workspace.refresh_draft()
            self._refresh_configuration_label()
            self.statusBar().showMessage(f'Added {dialog.name.text().strip()} to {target["label"]}. '
                                         'Save Configuration keeps it; Export to Scanner sends it.', 12000)
            if dialog.open_editor.isChecked():
                self.open_list_editor_at({'draft': target['draft'], 'entry_index': target['entry_index'],
                                          'group_index': target['group_index'], 'row_index': row,
                                          'label': target['label']})
            return

    def open_list_editor_at(self, match):
        from favorites_settings_window import FavoritesSettingsDialog
        workspace = self.workspace
        workspace.draft_choice.setCurrentText(match['draft'])
        workspace.current_draft = match['draft']
        dialog = FavoritesSettingsDialog(workspace, match['draft'])
        dialog._restore_editor_selection(match['entry_index'], match['group_index'], match['row_index'])
        self.statusBar().showMessage('Opened from SDS100 Monitor: ' + match['label'], 10000)
        dialog.exec()

    def name_unnamed_talkgroups(self):
        drafts = self.workspace.drafts
        if not any(entries for entries in drafts.values()):
            QMessageBox.information(self, 'Name Unnamed Talkgroups', 'Open a scanner configuration first '
                                    '(File → Open Scanner Configuration…).')
            return
        items = monitor_link.unnamed_talkgroups(drafts)
        if not items:
            QMessageBox.information(self, 'Name Unnamed Talkgroups',
                                    'Every talkgroup in the open Favorites Lists already has a name.')
            return
        UnnamedTalkgroupsDialog(self, items).exec()


class UnnamedTalkgroupsDialog(QDialog):
    """Tools → Name Unnamed Talkgroups…"""
    COLUMNS = ['Use', 'Favorites List', 'System', 'Department', 'TGID', 'Name now', 'New name', 'From']

    def __init__(self, window, items):
        super().__init__(window)
        self.window_ = window
        self.items = items
        self.result_names = {}
        self.setWindowTitle('Name Unnamed Talkgroups')
        self.resize(1250, 640)
        layout = QVBoxLayout(self)
        intro = QLabel(f'{len(items)} talkgroups in the open Favorites Lists have no real name (blank, or just '
                       'the ID). Suggestions come from the master database (same system first) and from what '
                       'SDS100 Monitor recorded: the name the scanner showed, and your Analyze notes. '
                       'Tick the ones to use; you can edit a name or pick another suggestion. Nothing changes '
                       'until you press Apply, it is one Undo step, and it reaches the scanner only through '
                       'Save Configuration and Export.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.status = QLabel('Looking up names…')
        layout.addWidget(self.status)
        self.table = QTableWidget(len(items), len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        for r, item in enumerate(items):
            for c, value in enumerate(('', monitor_link.list_label(item['draft']), item['system'],
                                       item['department'], item['tgid'], item['name'] or '(blank)')):
                cell = QTableWidgetItem(value)
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, c, cell)
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.only_suggested = QCheckBox('Show only talkgroups with a suggestion')
        self.only_suggested.setChecked(True)
        self.only_suggested.toggled.connect(self.filter_rows)
        row.addWidget(self.only_suggested)
        tick = QPushButton('Tick All With Suggestions')
        tick.clicked.connect(self.tick_suggested)
        row.addWidget(tick)
        row.addStretch(1)
        layout.addLayout(row)
        buttons = QDialogButtonBox()
        self.apply_btn = buttons.addButton('Apply Ticked Names', QDialogButtonBox.ButtonRole.AcceptRole)
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.apply)
        buttons.addButton(QDialogButtonBox.StandardButton.Close).clicked.connect(self.reject)
        layout.addWidget(buttons)
        self.cancelled = False
        self.lookup = {'done': False, 'db': {}, 'progress': (0, 0), 'error': ''}
        self.heard = monitor_link.monitor_heard_names()
        self.notes = monitor_link.monitor_notes()
        try:
            import managed_storage
            database = managed_storage.active_database()
        except Exception:
            database = None
        wanted = {i['tgid'] for i in items}
        self.lookup_thread = threading.Thread(target=self._lookup, args=(database, wanted), daemon=True)
        self.lookup_thread.start()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(200)
        self.finished.connect(self._closed)

    def _lookup(self, database, wanted):
        try:
            self.lookup['db'] = monitor_link.database_names(
                database, wanted, cancel=lambda: self.cancelled,
                progress=lambda i, n: self.lookup.__setitem__('progress', (i, n)))
        except Exception as exc:                  # a lookup must not take the window down
            self.lookup['error'] = str(exc)
        self.lookup['done'] = True

    def _poll(self):
        if not self.lookup['done']:
            i, n = self.lookup['progress']
            self.status.setText(f'Looking up names in the database… {i} of {n} files' if n else 'Looking up names…')
            return
        self.timer.stop()
        self.fill()

    def fill(self):
        suggested = 0
        self.choices = []
        for r, item in enumerate(self.items):
            options = monitor_link.suggest(item, self.lookup['db'], self.heard, self.notes)
            use = QCheckBox()
            combo = QComboBox()
            combo.setEditable(True)
            for name, source in options:
                combo.addItem(name, source)
            source = QTableWidgetItem(options[0][1] if options else 'No suggestion: type a name to use one')
            source.setFlags(source.flags() & ~Qt.ItemFlag.ItemIsEditable)
            combo.currentIndexChanged.connect(
                lambda i, cb=combo, cell=source: cell.setText(cb.itemData(i) or 'Typed by you'))
            combo.editTextChanged.connect(
                lambda text, cb=combo, cell=source, box=use: self._typed(text, cb, cell, box))
            use.setChecked(False)
            self.table.setCellWidget(r, 0, use)
            self.table.setCellWidget(r, 6, combo)
            self.table.setItem(r, 7, source)
            self.choices.append((use, combo, bool(options)))
            suggested += bool(options)
        self.table.resizeColumnsToContents()
        note = f' Database not searched: {self.lookup["error"]}' if self.lookup['error'] else ''
        self.status.setText(f'{suggested} of {len(self.items)} have a suggestion.{note}')
        self.apply_btn.setEnabled(True)
        self.filter_rows()

    @staticmethod
    def _typed(text, combo, cell, box):
        index = combo.findText(text)
        cell.setText(combo.itemData(index) if index >= 0 else ('Typed by you' if text.strip() else ''))
        if text.strip():
            box.setChecked(True)

    def tick_suggested(self):
        for use, _combo, has in getattr(self, 'choices', []):
            if has:
                use.setChecked(True)

    def filter_rows(self, *_):
        only = self.only_suggested.isChecked()
        for r, (_use, _combo, has) in enumerate(getattr(self, 'choices', [])):
            self.table.setRowHidden(r, only and not has)

    def ticked(self):
        """[(item, name)] for the ticked rows; raises ValueError for a bad name."""
        meta_encoding = {}
        out = []
        for item, (use, combo, _has) in zip(self.items, self.choices):
            if not use.isChecked():
                continue
            name = combo.currentText().strip()
            entries = self.window_.workspace.drafts[item['draft']]
            if item['draft'] not in meta_encoding:
                meta = entries[0] if entries and entries[0].get('scope') == 'metadata' else {}
                meta_encoding[item['draft']] = meta.get('encoding', 'cp1252')
            if not monitor_link.valid_name(name, meta_encoding[item['draft']]):
                raise ValueError(f'Talkgroup {item["tgid"]}: "{name}" is not a usable name '
                                 '(1–64 characters, no tabs or line breaks, characters the list can store).')
            out.append((item, name))
        return out

    def apply(self):
        try:
            changes = self.ticked()
        except ValueError as exc:
            QMessageBox.warning(self, 'Name Unnamed Talkgroups', str(exc))
            return
        if not changes:
            QMessageBox.information(self, 'Name Unnamed Talkgroups', 'Tick the talkgroups to name first.')
            return
        listing = '\n'.join(f'  {item["tgid"]}: {name}' for item, name in changes[:15])
        more = f'\n  …and {len(changes) - 15} more' if len(changes) > 15 else ''
        if QMessageBox.question(self, 'Name Unnamed Talkgroups',
                                f'Give {len(changes)} talkgroups these names?\n\n{listing}{more}') \
                != QMessageBox.StandardButton.Yes:
            return
        workspace = self.window_.workspace
        workspace._snapshot()
        try:
            count = monitor_link.apply_names(workspace.drafts, changes)
        except ValueError as exc:
            workspace.undo_change()
            QMessageBox.warning(self, 'Name Unnamed Talkgroups', str(exc))
            return
        workspace.refresh_draft()
        workspace.status.setText(f'{count} talkgroup names set. Save Scanner Configuration to preserve them.')
        self.accept()

    def _closed(self, *_):
        self.cancelled = True                     # stops the database lookup thread
        self.timer.stop()


class AddHeardDialog(QDialog):
    """Where to put a channel or talkgroup heard in SDS100 Monitor, and what to call it (v0.1.18)."""

    def __init__(self, parent, request, what, targets):
        super().__init__(parent)
        import hand_entry
        from PyQt6.QtWidgets import QCheckBox, QComboBox, QDialogButtonBox, QFormLayout, QLabel, QLineEdit
        self.setWindowTitle('Add to Favorites List')
        self.resize(640, 260)
        form = QFormLayout(self)
        heard = QLabel(('From RadioReference' if request.get('source') == 'rr' else 'Heard in SDS100 Monitor')
                       + f': <b>{what}</b>')
        heard.setWordWrap(True)
        form.addRow(heard)
        self.target = QComboBox()
        for target in targets:
            self.target.addItem(('★ ' if target['preferred'] else '') + target['label'])
        self.target.setToolTip('★ = the same system or department the scanner was playing')
        form.addRow('Department', self.target)
        self.name = QLineEdit(monitor_link.suggested_name(request))
        self.name.setMaxLength(64)
        self.name.setPlaceholderText('Name to show on the scanner')
        form.addRow('Name', self.name)
        self.modulation = QComboBox()
        self.modulation.addItems(hand_entry.MODULATIONS)
        self.modulation.setCurrentText(request.get('modulation') or 'AUTO')
        self.tone = QLineEdit()
        self.tone.setPlaceholderText('optional: 107.2, 023 DPL, NAC 293, CC 1')
        self.tone.setText(str(request.get('tone') or ''))
        if not request['tgid']:
            form.addRow('Frequency', QLabel(f'{float(request["frequency"]):.4f} MHz'))
            form.addRow('Modulation', self.modulation)
            form.addRow('Tone / NAC / colour code', self.tone)
        else:
            form.addRow('Talkgroup', QLabel(request['tgid']))
        self.open_editor = QCheckBox('Open the list editor on it afterwards')
        form.addRow('', self.open_editor)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._check)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _check(self):
        if not self.name.text().strip():
            QMessageBox.information(self, 'Add to Favorites List', 'Enter a name.')
            return
        self.accept()

