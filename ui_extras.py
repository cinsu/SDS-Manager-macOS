# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Window features added around the original application: preferences, Scanner panel, detection,
housekeeping dialogs and appearance.  A mixin for ManagerWindow; the logic lives in plain modules
(preferences, scanner_detect, scanner_panel, scanner_backup, managed_storage) and is unit tested there."""
from pathlib import Path
import threading

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDockWidget,
                             QHeaderView, QTableWidget, QTableWidgetItem,
                             QFileDialog, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                             QMessageBox, QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

import app_theme
from edition import DB_UPDATE_LABEL, PERSONAL
import preferences
import scanner_detect
import scanner_panel
from scanner_backup import backup_usage, plan_prune, prune_backups
from scanner_detect import human_bytes

SEVERITY_STYLE = {scanner_panel.OK: '', scanner_panel.NOTE: f'color: {app_theme.MUTED};',
                  scanner_panel.WARN: f'color: {app_theme.WARN}; font-weight: bold;'}   # theme colour keys


def _select_data(combo, value):
    """Select the combo entry whose stored value is ``value`` (the first entry if there is none)."""
    index = combo.findData(value)
    combo.setCurrentIndex(index if isinstance(index, int) and index >= 0 else 0)


class ExtrasMixin:
    # ---- setup ----------------------------------------------------------------------------------
    def init_extras(self):
        self.prefs = preferences.load()
        self.detected_scanners = []
        self._scanner_info = None
        self._scanner_signature = None
        self._scanner_label = QLabel('Scanner: not connected')
        self.statusBar().addPermanentWidget(self._scanner_label)
        self._build_scanner_dock()
        self.apply_appearance()
        self._scanner_timer = QTimer(self)
        self._scanner_timer.timeout.connect(self._poll_scanner)
        self.restart_scanner_polling()
        self.refresh_scanner_panel()

    def restart_scanner_polling(self):
        self._scanner_timer.stop()
        if self.prefs.get('auto_detect'):
            self._poll_scanner()
            self._scanner_timer.start(3000)

    def confirm_low_risk(self, title, text):
        """Low-risk confirmation that the user may switch off.  Scanner writes never use this."""
        if not self.prefs.get('confirm_low_risk', True):
            return True
        return QMessageBox.question(self, title, text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    # ---- appearance -----------------------------------------------------------------------------
    def apply_appearance(self):
        """The theme (shared with SDS100 Monitor) for the whole application, applied live."""
        app = QApplication.instance()
        if app is None:
            return
        if getattr(self, '_default_font', None) is None:
            self._default_font = app.font()
            try:
                self._desktop_lightness = app.palette().color(QPalette.ColorRole.Window).lightness()
            except Exception:
                self._desktop_lightness = None
        theme = app_theme.resolve(self.prefs.get('theme', 'system'), self.prefs.get('accent', 'blue'),
                                  self.prefs.get('text_size', 'normal'), getattr(self, '_desktop_lightness', None))
        app_theme.THEME = theme
        app.setStyle('Fusion')
        palette = QPalette()
        colours = app_theme.palette_colours(theme)
        for role, colour in colours.items():
            if role != 'Disabled' and hasattr(QPalette.ColorRole, role):
                palette.setColor(getattr(QPalette.ColorRole, role), QColor(colour))
        for role in ('WindowText', 'Text', 'ButtonText'):
            palette.setColor(QPalette.ColorGroup.Disabled, getattr(QPalette.ColorRole, role),
                             QColor(colours['Disabled']))
        app.setPalette(palette)
        app.setStyleSheet(app_theme.stylesheet(theme))
        app_theme.reapply(app.allWidgets())
        font = QFont(self._default_font)
        size = int(self.prefs.get('font_size', 0))
        base = self._default_font.pointSizeF()
        if not isinstance(base, (int, float)):
            base = 0                            # no usable point size (pixel-sized fonts)
        if size:
            font.setPointSize(size)
        elif base > 0:
            font.setPointSizeF(round(base * theme.scale, 1))
        app.setFont(font)
        self._update_theme_menu()

    # ---- Tools → Theme (the same choices as SDS100 Monitor's View → Theme) -----------------------
    def build_theme_menu(self, menu):
        self._theme_actions = {}
        for key, title, options in (
                ('theme', 'Mode', list(app_theme.THEME_MODES.items())),
                ('accent', 'Accent', [(k, v[0]) for k, v in app_theme.THEME_ACCENTS.items()]),
                ('text_size', 'Text size', [(k, v[0]) for k, v in app_theme.TEXT_SIZES.items()])):
            heading = menu.addAction(title)
            heading.setEnabled(False)
            for value, label in options:
                action = menu.addAction(label)
                action.setCheckable(True)
                action.triggered.connect(lambda checked=False, k=key, v=value: self.set_theme_option(k, v))
                self._theme_actions[(key, value)] = action
            menu.addSeparator()
        menu.aboutToShow.connect(self._update_theme_menu)
        self._update_theme_menu()
        self._theme_timer = QTimer(self)
        self._theme_timer.timeout.connect(self._check_system_theme)
        self._theme_timer.start(4000)

    def _update_theme_menu(self):
        actions = getattr(self, '_theme_actions', None)
        prefs = getattr(self, 'prefs', None)
        if not actions or prefs is None:
            return                              # menus are built before preferences load; init_extras updates it
        night = app_theme.THEME.mode == 'night'
        for (key, value), action in actions.items():
            current = prefs.get(key, preferences.DEFAULTS.get(key))
            if key == 'text_size' and int(prefs.get('font_size', 0)):
                current = None                  # an exact font size overrides the text size
            action.setChecked(current == value)
            if key == 'accent':
                action.setEnabled(not night)

    def set_theme_option(self, key, value):
        if getattr(self, 'prefs', None) is None:
            self.prefs = preferences.load()
        try:
            changed = dict(self.prefs, **{key: value})
            if key == 'text_size':
                changed['font_size'] = 0
            self.prefs = preferences.save(changed)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, 'Theme not saved', str(exc))
            return
        self.apply_appearance()
        mode = app_theme.THEME_MODES.get(self.prefs['theme'], '')
        accent = ('' if app_theme.THEME.mode == 'night'
                  else f", {app_theme.THEME_ACCENTS[app_theme.THEME.accent][0]} accent")
        size = app_theme.TEXT_SIZES[app_theme.THEME.size][0].lower()
        self.statusBar().showMessage(f'Theme: {mode}{accent}, {size} text', 6000)

    def _check_system_theme(self):
        """System mode: follow KDE switching between light and dark."""
        if getattr(self, 'prefs', {}).get('theme') != 'system':
            return
        dark = app_theme.system_is_dark(getattr(self, '_desktop_lightness', None))
        if dark != (app_theme.THEME.mode == 'dark'):
            self.apply_appearance()

    # ---- Scanner panel and detection -------------------------------------------------------------
    def _build_scanner_dock(self):
        self._scanner_dock = QDockWidget('Scanner', self)
        self._scanner_dock.setObjectName('ScannerDock')
        body = QWidget()
        layout = QVBoxLayout(body)
        self._panel_form = QFormLayout()
        layout.addLayout(self._panel_form)
        self._panel_values = {}
        for text, callback in (('Refresh', self.refresh_scanner_panel),
                               (DB_UPDATE_LABEL, self.integrated_update),
                               ("Update Scanner's Master Database…", self.update_scanner_master_database),
                               ('Export to Scanner…', self.export_to_scanner),
                               ('Back Up Scanner Now…', self.backup_scanner_configuration),
                               ('Clean Up Old Backups…', self.cleanup_backups)):
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, cb=callback: cb())
            layout.addWidget(button)
        layout.addStretch(1)
        self._scanner_dock.setWidget(body)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._scanner_dock)
        action = self._scanner_dock.toggleViewAction()
        action.setText('Show Scanner Panel')
        tools = getattr(self, '_tools_menu', None)
        if tools is not None:
            tools.addAction(action)

    def _local_database_date(self):
        try:
            from managed_storage import active_database, list_versions
            active = active_database()
            if active is not None:
                return scanner_detect.local_database_date(active)
            versions = list_versions()
            return scanner_detect.local_database_date(versions[-1]) if versions else None
        except Exception:
            return None

    def refresh_scanner_panel(self):
        """Re-read the card (if one is detected) and redraw the panel and status bar."""
        self.detected_scanners = scanner_detect.find_scanners(self.prefs.get('mount_folder', ''))
        info = None
        if self.detected_scanners:
            try:
                info = scanner_detect.summarize(self.detected_scanners[0]['mountpoint'])
            except Exception:
                info = None
        self._scanner_info = info
        active = getattr(self, 'active_scanner_configuration', None)
        try:
            usage = backup_usage()
        except Exception:
            usage = None
        rows = scanner_panel.panel_rows(info, self._local_database_date(), usage,
                                        self.prefs.get('backup_warn_mb', 2000), Path(active).name if active else None)
        for _ in range(int(self._panel_form.rowCount())):
            self._panel_form.removeRow(0)
        for label, value, severity in rows:
            widget = QLabel(value)
            widget.setWordWrap(True)
            app_theme.set_css(widget, SEVERITY_STYLE.get(severity, ''))
            self._panel_form.addRow(label + ':', widget)
        self._scanner_label.setText(scanner_panel.status_text(info))
        self._scanner_signature = tuple(h['mountpoint'] for h in self.detected_scanners)

    def _poll_scanner(self):
        try:
            found = tuple(h['mountpoint'] for h in scanner_detect.find_scanners(self.prefs.get('mount_folder', '')))
        except Exception:
            return
        if found != self._scanner_signature:
            self.refresh_scanner_panel()
            if found:
                self.statusBar().showMessage('SDS100 detected. Nothing has been read or written beyond its identity files.', 8000)

    def pick_scanner_folder(self, title):
        """The SD card root to use: the detected scanner when the user agrees, otherwise a folder chooser."""
        start = self.prefs.get('mount_folder') or '/run/media'
        if not Path(start).is_dir():
            start = str(Path.home())
        if self.prefs.get('offer_detected_scanner', True):
            hits = scanner_detect.find_scanners(self.prefs.get('mount_folder', ''))
            if len(hits) == 1:
                box = QMessageBox(self)
                box.setWindowTitle(title)
                box.setText(f'An SDS100 SD card was detected at:\n{hits[0]["mountpoint"]}\n\nUse it?')
                use = box.addButton('Use detected scanner', QMessageBox.ButtonRole.AcceptRole)
                other = box.addButton('Choose another folder…', QMessageBox.ButtonRole.ActionRole)
                box.addButton(QMessageBox.StandardButton.Cancel)
                box.exec()
                if box.clickedButton() is use:
                    return hits[0]['mountpoint']
                if box.clickedButton() is not other:
                    return ''
            elif len(hits) > 1:
                labels = [h['mountpoint'] for h in hits] + ['Choose another folder…']
                choice, ok = QInputDialog.getItem(self, title, 'More than one SD card with a BCDx36HP folder was found:',
                                                  labels, 0, False)
                if not ok:
                    return ''
                if choice != labels[-1]:
                    return choice
        return QFileDialog.getExistingDirectory(self, title, start)


    def cleanup_backups(self):
        keep = int(self.prefs.get('backup_keep', 20))
        try:
            doomed = plan_prune(keep)
            usage = backup_usage()
        except OSError as exc:
            QMessageBox.warning(self, 'Clean up backups', str(exc))
            return
        if not doomed:
            QMessageBox.information(self, 'Clean up backups',
                f'{usage["count"]} backups ({human_bytes(usage["bytes"])}). Nothing to clean up: '
                f'the newest {max(keep, 3)} are kept.')
            return
        size = sum(b['bytes'] for b in doomed)
        listing = '\n'.join(f'{b["name"]}  ({human_bytes(b["bytes"])})' for b in doomed[:30])
        more = f'\n… and {len(doomed) - 30} more' if len(doomed) > 30 else ''
        answer = QMessageBox.question(self, 'Clean up old backups',
            f'Delete {len(doomed)} old backups ({human_bytes(size)})?\n\nThe newest {max(keep, 3)} are kept.\n\n{listing}{more}\n\n'
            'This cannot be undone.', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        removed = prune_backups([b['name'] for b in doomed], keep)
        QMessageBox.information(self, 'Clean up old backups', f'Deleted {len(removed)} backups.')
        self.refresh_scanner_panel()

    def cleanup_database_versions(self):
        from managed_storage import plan_version_cleanup, cleanup_versions
        keep = int(self.prefs.get('keep_database_versions', 3))
        protected = set()
        if self._scanner_info and self._scanner_info.get('database_date'):
            protected.add(self._scanner_info['database_date'])
        try:
            doomed = plan_version_cleanup(keep, protected)
        except OSError as exc:
            QMessageBox.warning(self, 'Clean up database versions', str(exc))
            return
        if not doomed:
            QMessageBox.information(self, 'Clean up database versions',
                f'Nothing to clean up: the newest {keep}, the current version'
                + (' and the version on your scanner' if protected else '') + ' are kept.')
            return
        answer = QMessageBox.question(self, 'Clean up old database versions',
            f'Delete {len(doomed)} rebuilt database versions?\n\n' + '\n'.join(p.name for p in doomed[:30])
            + f'\n\nThe newest {keep}, the current version and the version on the scanner are kept. '
              'You can download and rebuild any of them again.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        removed = cleanup_versions([p.name for p in doomed], keep, protected)
        QMessageBox.information(self, 'Clean up database versions', f'Deleted {len(removed)} versions.')
        self.refresh_scanner_panel()

    # ---- Preferences dialog -----------------------------------------------------------------------
    def edit_preferences(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Preferences')
        dialog.resize(720, 560)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel('Preferences never change the safety checks: every write to the scanner is still '
                                'validated, backed up first, confirmed by you and reversible.'))
        tabs = QTabWidget(dialog)
        layout.addWidget(tabs, 1)
        editors, forms = {}, {}
        for pref in preferences.PREFS:
            if pref.group not in forms:
                page = QWidget()
                forms[pref.group] = QFormLayout(page)
                forms[pref.group].setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
                tabs.addTab(page, pref.group)
            value = self.prefs.get(pref.key, pref.default)
            if pref.kind == 'bool':
                widget = QCheckBox()
                widget.setChecked(bool(value))
            elif pref.kind == 'int':
                widget = QSpinBox()
                widget.setRange(pref.low, pref.high)
                widget.setValue(int(value))
            elif pref.kind == 'choice':
                widget = QComboBox()
                for choice in pref.values:
                    widget.addItem(pref.display(choice), choice)
                _select_data(widget, value)
            else:
                widget = QLineEdit(value)
            if pref.help:
                widget.setToolTip(pref.help)
            label = QLabel(pref.label)
            label.setToolTip(pref.help)
            label.setWordWrap(True)
            forms[pref.group].addRow(label, widget)
            if pref.help:
                note = QLabel(pref.help)
                note.setWordWrap(True)
                app_theme.set_css(note, f'color: {app_theme.MUTED};')
                forms[pref.group].addRow('', note)
            editors[pref.key] = widget
        for group, text, callback in (('Backups', 'Clean Up Old Backups…', self.cleanup_backups),
                                      ('Database', 'Clean Up Old Database Versions…', self.cleanup_database_versions),
                                      ('Diagnostics', 'Open Log Folder', self.open_log_folder)):
            if group in forms:
                button = QPushButton(text)
                button.clicked.connect(lambda checked=False, cb=callback: cb())
                forms[group].addRow('', button)

        def collect():
            values = {}
            for pref in preferences.PREFS:
                widget = editors[pref.key]
                if pref.kind == 'bool':
                    values[pref.key] = widget.isChecked()
                elif pref.kind == 'int':
                    values[pref.key] = widget.value()
                elif pref.kind == 'choice':
                    values[pref.key] = widget.currentData()
                else:
                    values[pref.key] = widget.text().strip()
            return values

        def reset():
            for pref in preferences.PREFS:
                widget = editors[pref.key]
                if pref.kind == 'bool':
                    widget.setChecked(pref.default)
                elif pref.kind == 'int':
                    widget.setValue(pref.default)
                elif pref.kind == 'choice':
                    _select_data(widget, pref.default)
                else:
                    widget.setText(pref.default)

        def save():
            try:
                self.prefs = preferences.save(collect())
            except (ValueError, OSError) as exc:
                QMessageBox.warning(dialog, 'Preferences not saved', str(exc))
                return
            self.apply_appearance()
            self.restart_scanner_polling()
            self.refresh_scanner_panel()
            dialog.accept()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
                                   | QDialogButtonBox.StandardButton.RestoreDefaults, parent=dialog)
        buttons.accepted.connect(save)
        buttons.rejected.connect(dialog.reject)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(reset)
        layout.addWidget(buttons)
        dialog.show()
        self._preferences_dialog = dialog

    def open_log_folder(self):
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices
        folder = preferences.state_dir()
        folder.mkdir(parents=True, exist_ok=True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            QMessageBox.warning(self, 'Log folder', f'Could not open:\n{folder}')

    # ---- Find Everywhere ---------------------------------------------------------------------------
    def find_everywhere(self):
        """Non-modal search over the active database and the open configuration's Favorites Lists."""
        import managed_storage
        import search_engine
        existing = getattr(self, '_find_dialog', None)
        if existing is not None:
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('Find Everywhere')
        dialog.resize(900, 560)
        layout = QVBoxLayout(dialog)
        row = QHBoxLayout()
        box = QLineEdit(dialog)
        box.setPlaceholderText('Name, frequency in MHz (154.9), or talkgroup ID (44042)')
        in_database = QCheckBox('Master database', dialog)
        in_database.setChecked(True)
        in_lists = QCheckBox('Open configuration\'s Favorites Lists', dialog)
        in_lists.setChecked(True)
        go = QPushButton('Find', dialog)
        stop = QPushButton('Stop', dialog)
        stop.setEnabled(False)
        for widget in (box, in_database, in_lists, go, stop):
            row.addWidget(widget, 1 if widget is box else 0)
        layout.addLayout(row)
        status = QLabel('Type a name, a frequency in MHz (154.9 matches 154.900 to 154.999) or a talkgroup ID.', dialog)
        status.setWordWrap(True)
        layout.addWidget(status)
        headers = ('Where', 'Type', 'Name', 'Value', 'In')
        table = QTableWidget(0, len(headers), dialog)
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table, 1)
        buttons = QDialogButtonBox(dialog)
        copy = buttons.addButton('Copy Results', QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Close).clicked.connect(dialog.close)
        layout.addWidget(buttons)
        state = {'job': None}
        timer = QTimer(dialog)
        timer.setInterval(150)

        def finish():
            timer.stop()
            job = state['job']
            go.setEnabled(True)
            stop.setEnabled(False)
            if job.error:
                status.setText('Search failed: ' + job.error)
                return
            table.setRowCount(0)
            for result in job.results:
                at = table.rowCount()
                table.insertRow(at)
                for column, value in enumerate((result['source'], result['kind'], result['name'],
                                                result['value'], search_engine.context(result))):
                    table.setItem(at, column, QTableWidgetItem(value))
            table.resizeColumnsToContents()
            note = ' (stopped)' if job.cancelled else ''
            if job.truncated:
                note = ' — showing the first %d; narrow the search' % len(job.results)
            status.setText('%d match%s%s' % (len(job.results), '' if len(job.results) == 1 else 'es', note))

        def poll():
            job = state['job']
            if job is None:
                return
            if job.done:
                finish()
            else:
                index, total, label = job.progress
                status.setText('Searching… %d of %d  %s' % (index, total, label))

        def start():
            text = box.text().strip()
            if not text:
                return
            database = managed_storage.active_database() if in_database.isChecked() else None
            configuration = getattr(self, 'active_scanner_configuration', None) if in_lists.isChecked() else None
            if database is None and configuration is None:
                status.setText('Nothing to search: no database is active and no configuration is open, '
                               'or both sources are switched off.')
                return
            table.setRowCount(0)
            go.setEnabled(False)
            stop.setEnabled(True)
            state['job'] = search_engine.SearchJob(text, database, configuration).start()
            timer.start()

        def copy_results():
            lines = []
            for at in range(int(table.rowCount())):
                lines.append('\t'.join(table.item(at, c).text() for c in range(len(headers))))
            QApplication.clipboard().setText('\n'.join(lines))

        def closed(*_):
            job = state['job']
            if job is not None:
                job.cancel()
            timer.stop()
            self._find_dialog = None
        timer.timeout.connect(poll)
        go.clicked.connect(start)
        box.returnPressed.connect(start)
        stop.clicked.connect(lambda: state['job'] and state['job'].cancel())
        copy.clicked.connect(copy_results)
        dialog.finished.connect(closed)
        dialog.show()
        box.setFocus()
        self._find_dialog = dialog
