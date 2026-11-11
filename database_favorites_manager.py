#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""SDS-Manager (formerly SDS100 Database & Favorites Manager)."""
import mac_platform  # macOS: full flush to the SD card, no-overwrite rename
import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QFileDialog, QMessageBox, QInputDialog, QProgressDialog, QPushButton, QLabel, QDialog, QVBoxLayout, QProgressBar, QToolTip
from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal, Qt, QUrl
from PyQt6.QtGui import QIcon, QAction, QDesktopServices, QTextCursor
from pathlib import Path
import hashlib, json, re, os, tempfile
from datetime import datetime, timezone
from managed_storage import ROOT, initialize, active_database, activate_export
from edition import APP_NAME, APP_VERSION, DB_UPDATE_LABEL
from ui_extras import ExtrasMixin
from monitor_link_ui import MonitorLinkMixin
from updates import UpdatesMixin
from master_hpdb_validator import validate
from favorites_manager import FavoritesManager
from manage_actions import ManageMixin


class RestorePreviewWorker(QObject):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, backup, scanner):
        super().__init__()
        self.backup, self.scanner = backup, scanner

    def run(self):
        try:
            from scanner_restore import prepare_restore
            self.completed.emit(prepare_restore(self.backup, self.scanner))
        except Exception as exc:
            self.failed.emit(f'{type(exc).__name__}: {exc}')
        finally:
            self.finished.emit()


class ScannerExportPreviewWorker(QObject):
    completed = pyqtSignal(str, bool, str)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, configuration, scanner):
        super().__init__()
        self.configuration = configuration
        self.scanner = scanner

    def run(self):
        try:
            from scanner_export_preview import preview_export
            report, _, _ = preview_export(self.configuration, self.scanner, compact=True)
            from scanner_first_write import first_write_eligibility
            eligible, reason = first_write_eligibility(self.configuration, self.scanner)
            if eligible:
                try:
                    from scanner_first_write import prepare_first_write
                    import export_summary
                    plan = prepare_first_write(self.configuration, self.scanner)
                    reason = export_summary.header(export_summary.summarize(plan)) + '\n\nTechnical details:\n' + reason
                except Exception:
                    pass  # the technical reason alone is still correct
            self.completed.emit(report, eligible, reason)
        except Exception as exc:
            self.failed.emit(f'{type(exc).__name__}: {exc}')
        finally:
            self.finished.emit()


class ScannerFirstWriteWorker(QObject):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, configuration, scanner):
        super().__init__()
        self.configuration, self.scanner = configuration, scanner

    def run(self):
        try:
            from scanner_first_write import execute_first_write
            self.completed.emit(execute_first_write(self.configuration, self.scanner))
        except Exception as exc:
            self.failed.emit(f'{type(exc).__name__}: {exc}')
        finally:
            self.finished.emit()


class ExportPreviewBusyDialog(QDialog):
    """Non-modal, non-dismissible busy window; never runs a nested event loop.

    It is hidden only after the native preview worker thread has terminated.
    Unlike the former modal QProgressDialog, it does not own worker teardown.
    """
    def __init__(self, parent, export_flow=False, writing=False):
        super().__init__(parent)
        self._writing = writing
        self._export_flow = export_flow
        self._finished = False
        self._elapsed_seconds = 0
        self.setWindowTitle('Export to Scanner — BACKING UP / WRITING' if writing else
                            ('Export to Scanner — Automatic Preview (READ ONLY)' if export_flow
                             else 'Scanner Export Preview — Working (READ ONLY)'))
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setMinimumWidth(490)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        layout = QVBoxLayout(self)
        self._status = QLabel(self)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        progress = QProgressBar(self)
        progress.setRange(0, 0)  # Unknown duration: animated busy indicator.
        progress.setTextVisible(False)
        layout.addWidget(progress)
        layout.addWidget(QLabel(('DO NOT DISCONNECT THE SCANNER. A verified backup is created first.\n'
                                 'Then exactly one Favorites HPD may be written and checked.' if writing else
                                 'Scanner and backup files are being READ only.\n'
                                 'No scanner data will be written or changed.'), self))
        self._ticker = QTimer(self)
        self._ticker.timeout.connect(self._tick)
        self._tick()
        self._ticker.start(1000)

    def _tick(self):
        self._status.setText(('Backing up, writing and verifying scanner…' if self._writing else
                              ('Preparing automatic export preview…' if self._export_flow
                               else 'Preparing read-only scanner export preview…')) + '\n'
                             f'Elapsed time: {self._elapsed_seconds} seconds. Please wait.')
        self._elapsed_seconds += 1

    def reject(self):
        # Escape must not dismiss the only progress feedback while work continues.
        if self._finished:
            super().reject()

    def closeEvent(self, event):
        if not self._finished:
            event.ignore()
            return
        super().closeEvent(event)

    def finish(self):
        """Called by GUI thread after QThread.wait confirms termination."""
        self._finished = True
        self._ticker.stop()
        self.hide()
        self.deleteLater()


class ScannerImportWorker(QObject):
    progress = pyqtSignal(str, int, int, str)
    completed = pyqtSignal(str, str, int)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, folder, name):
        super().__init__()
        import threading
        self.folder, self.name = folder, name
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        from scanner_configurations import import_configuration, ImportCancelled
        try:
            destination, manifest = import_configuration(
                self.folder, self.name, progress=self.progress.emit,
                cancelled=self.cancel_event.is_set)
            try:
                import export_state     # read from the scanner, so they match (v0.1.20)
                export_state.record(destination, 'read')
            except Exception:
                pass
            self.completed.emit(str(destination), manifest['name'], len(manifest['files']))
        except ImportCancelled:
            self.failed.emit('Import cancelled. No configuration was saved.')
        except Exception as exc:
            self.failed.emit(f'{type(exc).__name__}: {exc}')
        finally:
            self.finished.emit()


class UpdateWorker(QObject):
    status = pyqtSignal(str)
    finished = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, archive, download_dir, export_dir, local_path=None):
        super().__init__()
        self.archive = archive
        self.download_dir = download_dir
        self.export_dir = export_dir
        self.local_path = local_path          # an archive file chosen by the user (v0.1.0)

    def run(self):
        from hpdb_bulk_reconstruction import reconstruct_all_states
        try:
            result = {'path': str(self.local_path)} if self.local_path else None
            if result is None:
                raise ValueError('No database archive was chosen.')
            archive_path = Path(result['path'])
            self.status.emit('Calculating downloaded archive SHA-256')
            digest = hashlib.sha256()
            with archive_path.open('rb') as source:
                for block in iter(lambda: source.read(1024 * 1024), b''):
                    digest.update(block)
            exported = reconstruct_all_states(archive_path, self.export_dir,
                                              progress=self.status.emit)
            self.finished.emit({'download': result, 'archive_sha256': digest.hexdigest(),
                                'export': exported})
        except Exception as exc:
            # No credentials in exception text: HTTP module provides sanitized errors.
            self.failed.emit(f'{type(exc).__name__}: {exc}')

class ManagerWindow(ManageMixin, ExtrasMixin, MonitorLinkMixin, UpdatesMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1250, 850)
        self.setAcceptDrops(True)
        self.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / "assets/sds100-manager.svg")))
        self.workspace = FavoritesManager(self)
        self.workspace.new_list_hooks = self._new_list_hooks()
        self.setCentralWidget(self.workspace)
        initialize()
        self._configuration_label = QLabel('Configuration: None open')
        self._configuration_label.setToolTip('No local scanner configuration is open')
        self.statusBar().addPermanentWidget(self._configuration_label, 1)
        self._build_menus()
        self._load_managed_database()
        self.init_extras()
        self._recovery_timer = QTimer(self)
        self._recovery_timer.timeout.connect(self._checkpoint_unsaved)
        self._recovery_timer.timeout.connect(self._refresh_configuration_label)
        self._recovery_timer.start(300000)
        self._active_working_name = None
        self._active_working_source = None
        QTimer.singleShot(0, self._startup_recovery_check)


    def _refresh_configuration_label(self):
        """Show the selected local configuration, never a scanner HPD filename."""
        folder = getattr(self, 'active_scanner_configuration', None)
        if folder is None:
            self._configuration_label.setText('Configuration: None open')
            self._configuration_label.setToolTip('No local scanner configuration is open')
            return
        path = Path(folder).resolve()
        modified = False
        for entries in self.workspace.drafts.values():
            if not entries or entries[0].get('scope') != 'metadata':
                continue
            source = entries[0].get('source_path')
            if not source:
                continue
            source = Path(source).resolve()
            if not source.is_relative_to(path / 'BCDx36HP' / 'favorites_lists'):
                continue
            try:
                from native_favorites_export import build_native_bytes
                modified = build_native_bytes(entries)[0] != source.read_bytes()
            except (OSError, ValueError, KeyError, TypeError, UnicodeError):
                modified = True
            if modified:
                break
        try:
            import export_state
            scanner = export_state.state(path)
            scanner_text = export_state.describe(scanner)
        except Exception:
            scanner, scanner_text = {'state': 'unknown'}, ''
        mark = ' — not on scanner yet' if scanner.get('state') == 'changed' else ''
        self._configuration_label.setText('Configuration: ' + path.name + (' *' if modified else '') + mark)
        self._configuration_label.setToolTip(str(path) + ('\n* Unsaved working changes' if modified else '')
                                             + ('\n' + scanner_text if scanner_text else ''))
        # v0.1.12: share the saved keys, tags and scan profiles with SDS100 Monitor, when they changed.
        stamp = (str(path), tuple(sorted((p.name, p.stat().st_mtime_ns) for p in
                                         (path / 'BCDx36HP').glob('**/*') if p.is_file())))
        if stamp != getattr(self, '_monitor_keys_stamp', None):
            from keys_model import write_monitor_file
            if write_monitor_file(path, path.name):
                self._monitor_keys_stamp = stamp

    def open_native_in_favorites_panel(self):
        """Browse an existing .hpd directly in the main tree, strictly read-only."""
        path, _ = QFileDialog.getOpenFileName(self, 'Open Native Favorites in Main Panel (read-only)', str(Path.home()), 'Uniden Favorites (*.hpd)')
        if not path:
            return
        try:
            self.workspace.add_native_readonly_file(path)
        except (OSError, UnicodeError, ValueError) as exc:
            QMessageBox.warning(self, 'Unable to open native Favorites', str(exc))

    def inspect_native_favorites(self, checked=False, path=None):
        """Inspect a scanner Favorites file without importing or modifying it."""
        from PyQt6.QtWidgets import QFileDialog, QDialog, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem, QDialogButtonBox
        from native_favorites_reader import parse_native_favorites
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, 'Inspect Native Favorites (read-only)', str(Path.home()), 'Uniden Favorites (*.hpd)')
        if not path:
            return
        try:
            parsed = parse_native_favorites(path)
        except (OSError, UnicodeError, ValueError) as exc:
            QMessageBox.warning(self, 'Unable to inspect Favorites', str(exc))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('Native Favorites Inspector — Read-only — ' + Path(path).name)
        dialog.resize(1100, 700)
        layout = QVBoxLayout(dialog)
        header = parsed['header']
        layout.addWidget(QLabel(f"Target: {header.get('TargetModel', 'Unknown')}  |  Format: {header.get('FormatVersion', 'Unknown')}  |  Systems: {len(parsed['systems'])}  |  READ-ONLY"))
        tree = QTreeWidget(dialog)
        tree.setHeaderLabels(['Name', 'Type', 'Frequency (MHz)', 'TGID', 'Mode', 'Service'])
        tree.setColumnWidth(0, 390)
        tree.setColumnWidth(1, 120)
        tree.setColumnWidth(2, 180)
        tree.setColumnWidth(3, 110)
        tree.setSortingEnabled(True)
        for system in parsed['systems']:
            root = QTreeWidgetItem(tree, [system['name'], system['kind'], '', '', '', ''])
            for group in system['groups']:
                parent = QTreeWidgetItem(root, [group['name'], group['kind'], '', '', '', ''])
                for row in group['leaves']:
                    QTreeWidgetItem(parent, parsed['record_columns'](row))
        layout.addWidget(tree)
        if parsed['warnings']:
            layout.addWidget(QLabel('Validation notes: ' + '; '.join(parsed['warnings'][:4])))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def export_native_hpd(self):
        """Export native-origin working draft to a new local .hpd file only."""
        import os, tempfile
        from native_favorites_export import build_native_bytes, validate_export_file
        from favorites_explorer import detect_mounts
        name = self.workspace.current_draft
        if not name:
            QMessageBox.information(self, 'Select a draft', 'Select an editable native Favorites draft first.')
            return
        try:
            payload, rows = build_native_bytes(self.workspace.drafts[name])
        except (ValueError, UnicodeError, KeyError, TypeError) as exc:
            QMessageBox.warning(self, 'Native export blocked', str(exc))
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Export Native Favorites — LOCAL FILE ONLY',
            str(Path.home() / 'Documents' / 'sds100-export.hpd'), 'Uniden Favorites (*.hpd)')
        if not path:
            return
        target = Path(path).expanduser().resolve()
        if target.suffix.lower() != '.hpd':
            QMessageBox.warning(self, 'Invalid destination', 'Choose a .hpd filename.')
            return
        original = Path(self.workspace.drafts[name][0].get('source_path', '')).resolve()
        if target == original or target.exists():
            QMessageBox.warning(self, 'Export blocked', 'Export requires a NEW filename. Existing files and original native files cannot be overwritten.')
            return
        for forbidden in (Path('/run/media'), Path('/media'), Path('/Volumes')):
            if target == forbidden or forbidden in target.parents:
                QMessageBox.warning(self, 'Scanner write blocked', 'Removable media export is disabled. Choose a local directory.')
                return
        for mount in detect_mounts():
            mount = Path(mount).resolve()
            if target == mount or mount in target.parents:
                QMessageBox.warning(self, 'Scanner write blocked', 'Export to removable scanner storage is not supported yet. Choose a local directory.')
                return
        if not target.parent.is_dir():
            QMessageBox.warning(self, 'Invalid destination', 'Choose an existing local directory.')
            return
        if QMessageBox.question(self, 'Confirm offline native export',
                f'Create NEW local native Favorites file?\n\n{target}\n\n'
                f'{len(rows)} native records; {len(payload)} bytes.\n'
                'Original file will remain unchanged. This is NOT Export to Scanner.') != QMessageBox.StandardButton.Yes:
            return
        staged = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.sds100-hpd-', suffix='.tmp', delete=False) as f:
                staged = Path(f.name)
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            stats = validate_export_file(staged, rows)
            # Exclusive create: refuse overwrite even if file appeared since the dialog.
            with target.open('xb') as out:
                out.write(payload)
                out.flush()
                os.fsync(out.fileno())
            stats = validate_export_file(target, rows)
            QMessageBox.information(self, 'Native Favorites export validated',
                f'Created local file: {target}\nSystems: {stats["systems"]}\nSHA-256: {stats["sha256"]}\n'
                'Original scanner file unchanged. Scanner export remains disabled.')
        except (OSError, ValueError, UnicodeError) as exc:
            QMessageBox.warning(self, 'Export failed', str(exc))
        finally:
            if staged is not None:
                staged.unlink(missing_ok=True)

    def import_from_scanner(self, checked=False, folder=None):
        """Run verified import off the GUI thread with progress and safe cancellation."""
        folder = folder or self.pick_scanner_folder('Select SDS100 Mass Storage root (contains BCDx36HP)')
        if not folder:
            return
        name, ok = QInputDialog.getText(self, 'Import from Scanner', 'Name this saved scanner configuration:')
        if not ok or not name.strip():
            return
        if getattr(self, '_scanner_import_thread', None) is not None:
            QMessageBox.information(self, 'Import already running', 'Wait for the current scanner import to finish.')
            return
        self._scanner_import_outcome = None
        self._scanner_import_cancelling = False
        self._scanner_import_thread = QThread(self)
        self._scanner_import_worker = ScannerImportWorker(folder, name)
        self._scanner_import_worker.moveToThread(self._scanner_import_thread)
        dialog = QProgressDialog('Scanning scanner configuration…', 'Cancel import', 0, 0, self)
        dialog.setWindowTitle('Import from Scanner — ' + name.strip())
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumWidth(440)
        self._scanner_import_dialog = dialog
        # Cancellation must be set in the GUI thread. A queued call to a busy
        # worker QObject cannot run until its long-running run() returns.
        dialog.canceled.connect(self._request_scanner_import_cancel)
        self._scanner_import_thread.started.connect(self._scanner_import_worker.run)
        self._scanner_import_worker.progress.connect(self._scanner_import_progress)
        self._scanner_import_worker.completed.connect(self._scanner_import_complete)
        self._scanner_import_worker.failed.connect(self._scanner_import_failed)
        self._scanner_import_worker.finished.connect(self._scanner_import_thread.quit)
        # Qt worker-object pattern: dispose of the worker when its thread finishes.
        # Avoid entering a nested QMessageBox event loop until teardown completes.
        self._scanner_import_thread.finished.connect(self._scanner_import_worker.deleteLater)
        self._scanner_import_thread.finished.connect(self._scanner_import_cleanup)
        self._scanner_import_thread.finished.connect(self._scanner_import_thread.deleteLater)
        dialog.show()
        self._scanner_import_thread.start()

    def _request_scanner_import_cancel(self):
        worker = getattr(self, '_scanner_import_worker', None)
        if worker is None or self._scanner_import_cancelling:
            return
        self._scanner_import_cancelling = True
        # threading.Event.set() is safe from the GUI thread; the worker polls it
        # between files and during chunked copying and checksum verification.
        worker.cancel_event.set()
        dialog = self._scanner_import_dialog
        if dialog is not None:
            dialog.setCancelButtonText('Stopping…')
            dialog.setLabelText('Cancelling import… Cleaning up incomplete files. Please wait.')
            dialog.setRange(0, 0)

    def _scanner_import_progress(self, phase, completed, total, filename):
        if getattr(self, '_scanner_import_cancelling', False):
            return
        dialog = self._scanner_import_dialog
        if total > 0:
            if dialog.maximum() != total:
                dialog.setRange(0, total + 1)
            dialog.setValue(completed)
            dialog.setLabelText(f'{phase}: {completed} of {total} files\n{filename}')
        else:
            dialog.setLabelText(phase + '…')

    def _scanner_import_complete(self, destination, name, count):
        # Store outcome only: showing a modal message before QThread.finished can
        # re-enter Qt event processing while worker/thread objects are being freed.
        self._scanner_import_outcome = ('success', destination, name, count)

    def _scanner_import_failed(self, message):
        self._scanner_import_outcome = ('failed', message)

    def _scanner_import_cleanup(self):
        # Runs in the GUI thread after QThread.finished, never in the worker.
        outcome = self._scanner_import_outcome
        self._scanner_import_outcome = None
        self._scanner_import_cancelling = False
        dialog = self._scanner_import_dialog
        self._scanner_import_thread = None
        self._scanner_import_worker = None
        self._scanner_import_dialog = None
        if dialog is not None:
            dialog.close()
            dialog.deleteLater()
        if outcome is not None:
            QTimer.singleShot(0, lambda result=outcome: self._scanner_import_show_result(result))

    def _scanner_import_show_result(self, result):
        if result[0] == 'success':
            _, destination, name, count = result
            try:
                manifest = json.loads((Path(destination) / 'configuration.json').read_text(encoding='utf-8'))
                self._open_configuration(Path(destination), manifest)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, 'Import from Scanner', f'Imported, but could not open it: {exc}')
            QMessageBox.information(self, 'Scanner configuration imported',
                f'Saved configuration: {name}\nLocation: {destination}\nFiles verified: {count}\n\n'
                'Scanner contents were not modified.')
        else:
            QMessageBox.warning(self, 'Import from Scanner', result[1])

    def scanner_export_preflight(self):
        """Read-only structural check of an SDS100 mass-storage mount."""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QDialogButtonBox
        from scanner_preflight import inspect_scanner
        folder = self.pick_scanner_folder('Select SDS100 Mass Storage root for READ-ONLY preflight')
        if not folder:
            return
        if self._scanner_operation_running('a preflight check'):
            return
        self._db_update_busy = True
        self._run_background('Scanner Preflight — in progress', 'Checking the scanner structure (read only)…',
                             lambda: inspect_scanner(folder),
                             lambda result, error: self._show_preflight(result, error))

    def _show_preflight(self, result, error):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QDialogButtonBox
        self._db_update_busy = False
        if error or not result:
            QMessageBox.warning(self, 'Scanner Preflight', error or 'The check produced no result.')
            return
        report, ready = result
        dialog = QDialog(self)
        dialog.setWindowTitle('Scanner Export Preflight — READ ONLY')
        dialog.resize(750, 560)
        layout = QVBoxLayout(dialog)
        view = QPlainTextEdit(dialog)
        view.setReadOnly(True)
        view.setPlainText(report)
        layout.addWidget(view)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def backup_scanner_configuration(self):
        """Read scanner configuration, verify local backup; never write scanner."""
        from scanner_backup import backup_scanner
        folder = self.pick_scanner_folder('Select SDS100 Mass Storage root for READ-ONLY backup')
        if not folder:
            return
        choice = QMessageBox.question(self, 'Verified Scanner Backup',
            'Create a local verified backup of the scanner configuration?\n\n'
            'The scanner will be read only. This may take several minutes.')
        if choice != QMessageBox.StandardButton.Yes:
            return
        if self._scanner_operation_running('a backup'):
            return
        self._db_update_busy = True

        def finished(result, error):
            self._db_update_busy = False
            self.statusBar().clearMessage()
            if error:
                QMessageBox.warning(self, 'Scanner Backup Failed', error)
                return
            destination, manifest = result
            QMessageBox.information(self, 'Scanner Backup Verified',
                f'Backup location: {destination}\nFiles verified: {manifest["file_count"]}\n'
                'SHA-256 verified against scanner originals.\n'
                'No scanner files were modified.')
            if hasattr(self, 'refresh_scanner_panel'):
                self.refresh_scanner_panel()
        self.statusBar().showMessage('Backing up the scanner configuration (read only)…')
        self._run_background('Scanner Backup — in progress',
            'Copying and verifying every scanner configuration file against its SHA-256 (read only). '
            'This can take several minutes. Please keep the scanner connected.',
            lambda: backup_scanner(folder), finished)

    def restore_from_backup(self):
        """Select verified backup, inspect restore-specific preview, then confirm."""
        from scanner_restore import list_backups, prepare_restore, execute_restore, emergency_backups, remove_emergency, recover_emergency
        from PyQt6.QtWidgets import QDialogButtonBox, QPlainTextEdit
        emergencies=emergency_backups()
        if emergencies:
            choice=QMessageBox.question(self,'Pending Emergency Backup',
                'An emergency backup from an earlier restore is still retained.\n\n'
                'YES: scanner has been physically tested and works; delete an emergency backup.\n'
                'NO: keep backup and continue to recovery/normal restore.\n'
                'Cancel: exit.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel)
            if choice==QMessageBox.StandardButton.Cancel:return
            labels=[str(x) for x in emergencies]
            selected,ok=QInputDialog.getItem(self,'Emergency Backup', 'Choose emergency backup:',labels,0,False)
            if not ok:return
            selected_path=emergencies[labels.index(selected)]
            if choice==QMessageBox.StandardButton.Yes:
                if QMessageBox.question(self,'Confirm Physical Scanner Working',
                    'Have you safely ejected, booted and physically tested the SDS100, and reconnected it?\n'
                    'Delete this temporary emergency backup permanently?',
                    QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No)==QMessageBox.StandardButton.Yes:
                    remove_emergency(selected_path)
                    QMessageBox.information(self,'Emergency Backup Deleted','Temporary emergency backup deleted.')
                return
            if QMessageBox.question(self,'Recover Using Emergency Backup',
                'Restore the pre-restore scanner configuration from the selected emergency backup?\n'
                'Choose No to continue to ordinary backup selection.',
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)==QMessageBox.StandardButton.Yes:
                target=self.pick_scanner_folder('Reconnect SDS100 and select Mass Storage root')
                if target:
                    if self._scanner_operation_running('a recovery'):
                        return
                    self._db_update_busy = True

                    def recovered(result, error):
                        self._db_update_busy = False
                        if error:
                            QMessageBox.critical(self, 'Recovery Failed', error)
                            return
                        QMessageBox.information(self,'Emergency Recovery Verified',
                            'Emergency configuration restored and hashes verified.\n'
                            'Safely eject and physically test the scanner.\n'
                            'Emergency backups retained until confirmation.')
                    self._run_background('Emergency Recovery — in progress',
                        'Verifying the emergency backup and restoring the scanner configuration. '
                        'DO NOT DISCONNECT THE SCANNER or close the application.',
                        lambda: recover_emergency(selected_path, target), recovered)
                return
        if self._scanner_operation_running('a restore'):
            return
        backups = list_backups(verify=False)   # instant; every file is SHA-256 checked before it is used
        if not backups:
            QMessageBox.information(self, 'Restore from Backup',
                                    'No usable scanner backups were found.')
            return
        labels = [f'{manifest.get("created_utc", folder.name)} — {manifest["file_count"]} files — {folder.name}'
                  for folder, manifest in backups]
        selected, ok = QInputDialog.getItem(self, 'Restore from Backup',
                                             'Choose a verified backup:', labels, 0, False)
        if not ok: return
        backup = backups[labels.index(selected)][0]
        scanner = self.pick_scanner_folder('Select SDS100 Mass Storage root for restore preview')
        if not scanner: return
        # Preparing a full scanner inventory and hashes may take 30+ seconds.
        # Keep Qt's main event loop responsive while the read-only comparison runs.
        busy = QProgressDialog('Comparing backup and scanner files (read only)…', '', 0, 0, self)
        busy.setWindowTitle('Restore from Backup — Preparing Preview')
        busy.setCancelButton(None)
        busy.setMinimumDuration(0)
        busy.setWindowModality(Qt.WindowModality.ApplicationModal)
        thread = QThread(self)
        worker = RestorePreviewWorker(backup, scanner)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        def ready(plan):
            busy.close()
            self._show_restore_plan(backup, scanner, plan)
        def failed(message):
            busy.close()
            QMessageBox.warning(self, 'Restore Preview Blocked', message)
        worker.completed.connect(ready)
        worker.failed.connect(failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        # Retain thread references until teardown to avoid premature destruction.
        self._restore_preview_thread = thread
        self._restore_preview_worker = worker
        thread.start()
        busy.show()

    def _show_restore_plan(self, backup, scanner, plan):
        from scanner_restore import prepare_restore, execute_restore
        from PyQt6.QtWidgets import QPlainTextEdit, QDialogButtonBox
        dialog = QDialog(self)
        dialog.setWindowTitle('Restore to Scanner — Preview & Confirmation')
        dialog.resize(820, 570)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel('Selected verified backup: '+backup.name+'\n'
                                'An EMERGENCY PRE-RESTORE backup will be created before restoring.\n'
                                'Scanner configuration files absent from the backup WILL BE DELETED.'))
        detail = QPlainTextEdit(dialog)
        detail.setReadOnly(True)
        changes = plan['changes']
        detail.setPlainText('RESTORE PREVIEW — READ ONLY\n\nBackup: '+str(backup)+
            '\nScanner: '+plan['scanner']+'\n\nADD: '+str(sum(c['action']=='ADD' for c in changes))+
            '\nREPLACE: '+str(sum(c['action']=='REPLACE' for c in changes))+
            '\nUNCHANGED IN BACKUP: '+str(len(plan['manifest']['files'])-len(changes))+
            '\nDELETE FROM SCANNER: '+str(len(plan['delete']))+
            '\n\nCHANGES:\n'+'\n'.join(c['action']+' '+c['path'] for c in changes)+
            '\n\nDELETE:\n'+'\n'.join(plan['delete']))
        layout.addWidget(detail)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, parent=dialog)
        proceed = buttons.addButton('Restore Selected Backup', QDialogButtonBox.ButtonRole.AcceptRole)
        proceed.setEnabled(bool(changes or plan["delete"]))
        buttons.rejected.connect(dialog.reject)
        def perform():
            answer = QMessageBox.warning(self, 'Confirm Physical SDS100 Restore',
                'Restore '+str(len(changes))+' files and DELETE '+str(len(plan['delete']))+' extra configuration files?\n\n'
                'The scanner will first receive a temporary EMERGENCY backup. '
                'Do not disconnect the scanner during restoration.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes: return
            dialog.accept()
            if self._scanner_operation_running('the restore'):
                return
            self._db_update_busy = True

            def work():
                if prepare_restore(backup, scanner) != plan:
                    raise RuntimeError('Restore preview is stale; reopen Restore from Backup.')
                return execute_restore(backup, scanner)

            def finished(result, error):
                self._db_update_busy = False
                self.statusBar().clearMessage()
                if error:
                    QMessageBox.critical(self, 'Scanner Restore Failed', error)
                    return
                QMessageBox.information(self, 'Scanner Restore Verified',
                    f'Restored {result["changed"]} files, deleted {result["deleted"]}; inventory and hashes verified.\n'
                    f'Emergency backup retained: {result["emergency"]}\n\n'
                    'Safely eject, boot and physically test the SDS100. Reconnect and open Restore from Backup to confirm and delete emergency backup.')
                if hasattr(self, 'refresh_scanner_panel'):
                    self.refresh_scanner_panel()
            self.statusBar().showMessage('Restoring the scanner configuration. DO NOT DISCONNECT.')
            self._run_background('Restoring Scanner — in progress',
                'Creating the emergency backup, restoring files and verifying every one against its SHA-256. '
                'DO NOT DISCONNECT THE SCANNER or close the application.',
                work, finished)
        proceed.clicked.connect(perform)
        layout.addWidget(buttons)
        dialog.exec()

    def export_to_scanner(self):
        """Single entry point: mandatory preview, explicit confirmation, backed-up export."""
        self.preview_scanner_export(export_flow=True)

    def preview_scanner_export(self, export_flow=False):
        """Run automatic comparison in a worker; diagnostic mode is read-only too."""
        from scanner_configurations import list_configurations
        configs = list_configurations()
        if not configs:
            QMessageBox.information(self, 'Scanner Export Preview', 'No saved local configurations are available.')
            return
        if (getattr(self, '_export_preview_thread', None) is not None or getattr(self, '_scanner_write_thread', None) is not None
                or getattr(self, '_db_update_busy', False)):
            QMessageBox.information(self, 'Export in progress', 'Wait for the current scanner operation to finish.')
            return
        labels = [f'{data["name"]} ({folder.name})' for folder, data in configs]
        choice, ok = QInputDialog.getItem(self, 'Export to Scanner' if export_flow else 'Scanner Export Preview — READ ONLY',
            'Choose saved local configuration:', labels, 0, False)
        if not ok: return
        index = labels.index(choice)
        folder = self.pick_scanner_folder('Select SDS100 Mass Storage root — READ ONLY')
        if not folder: return
        if export_flow and not self._keep_scanner_avoids(configs[index][0], folder):
            return
        self._export_preview_selection = (str(configs[index][0]), folder)
        self._export_preview_outcome = None
        self._export_preview_mode = bool(export_flow)
        self._export_preview_thread = QThread(self)
        self._export_preview_worker = ScannerExportPreviewWorker(str(configs[index][0]), folder)
        self._export_preview_worker.moveToThread(self._export_preview_thread)
        # Keep progress VISIBLE for the entire read-only operation. This custom
        # NON-MODAL busy dialog has no nested exec() loop and is not torn down
        # until the worker thread has been joined. The old modal progress dialog
        # was implicated in a Qt/Wayland abort during result-window creation.
        self._export_preview_busy_dialog = ExportPreviewBusyDialog(self, export_flow=export_flow)
        self._export_preview_busy_dialog.show()
        self.statusBar().showMessage(
            'Read-only scanner export preview running; progress window is open…')
        self._export_preview_thread.started.connect(self._export_preview_worker.run)
        self._export_preview_worker.completed.connect(self._export_preview_completed)
        self._export_preview_worker.failed.connect(self._export_preview_failed)
        # Delete the worker in its own thread, before the QThread stops.
        self._export_preview_worker.finished.connect(self._export_preview_worker.deleteLater)
        self._export_preview_worker.finished.connect(self._export_preview_thread.quit)
        # Do not destroy the QThread or open a dialog inside finished delivery.
        self._export_preview_thread.finished.connect(self._export_preview_cleanup)
        self._export_preview_thread.start()

    def _keep_scanner_avoids(self, configuration, folder):
        """v0.1.21: offer to keep avoids made on the scanner (or from SDS100 Monitor) before exporting.
        False cancels the export."""
        try:
            import export_state
            import scanner_avoids
            from scanner_configurations import scanner_root
            found = scanner_avoids.differences(configuration, scanner_root(folder),
                                               export_state.matched_avoids(configuration))
        except Exception:
            return True                     # the export's own checks still run
        found = [f for f in found if f['made_on'] != 'SDS-Manager']
        if not found:
            return True
        from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QDialogButtonBox
        dialog = QDialog(self)
        dialog.setWindowTitle('Avoids on the scanner')
        dialog.resize(820, 460)
        layout = QVBoxLayout(dialog)
        intro = QLabel(f'{len(found)} avoid(s) on the scanner differ from the configuration. They were probably '
                       'set on the SDS100 or from SDS100 Monitor; exporting as it is would undo them.\n\n'
                       'Ticked ones are copied into the configuration (saved) before the export. Ticked to begin '
                       'with: those changed on the scanner since it last matched, or, when that isn\'t known, '
                       'the ones the scanner has avoided.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        listing = QListWidget()
        for item in found:
            row = QListWidgetItem(scanner_avoids.describe(item))
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            tick = item['made_on'] == 'scanner' or (not item['made_on'] and item['scanner'] == 'On')
            row.setCheckState(Qt.CheckState.Checked if tick else Qt.CheckState.Unchecked)
            listing.addItem(row)
        layout.addWidget(listing, 1)
        buttons = QDialogButtonBox()
        keep = buttons.addButton('Keep Ticked and Continue', QDialogButtonBox.ButtonRole.AcceptRole)
        skip = buttons.addButton('Continue Without', QDialogButtonBox.ButtonRole.DestructiveRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        clicked = {}
        buttons.clicked.connect(lambda button: (clicked.update(button=button), dialog.accept()))
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()
        button = clicked.get('button')
        if button is skip:
            return True
        if button is not keep:
            return False
        chosen = [found[i] for i in range(listing.count())
                  if listing.item(i).checkState() == Qt.CheckState.Checked]
        if not chosen:
            return True
        active = getattr(self, 'active_scanner_configuration', None)
        is_open = active is not None and Path(active).resolve() == Path(configuration).resolve()
        if is_open and not self._ask_unsaved('Export to Scanner'):
            return False
        try:
            count = scanner_avoids.keep_scanner_avoids(configuration, chosen)
        except Exception as exc:
            QMessageBox.warning(self, 'Avoids on the scanner', f'The avoids could not be saved: {exc}')
            return False
        if is_open:
            import json
            manifest = json.loads((Path(configuration) / 'configuration.json').read_text(encoding='utf-8'))
            self._open_configuration(configuration, manifest, check_unsaved=False)
        self.statusBar().showMessage(f'{count} avoid(s) from the scanner kept in the configuration.', 10000)
        return True

    def _export_preview_completed(self, report, eligible, reason):
        self._export_preview_outcome = ('success', report, eligible, reason)

    def _export_preview_failed(self, message):
        self._export_preview_outcome = ('failed', message)

    def _export_preview_cleanup(self):
        """Reap the stopped worker thread before constructing report widgets."""
        thread = getattr(self, '_export_preview_thread', None)
        if thread is None:
            return
        # Qt's finished signal can precede the final native thread cleanup.
        # Never construct another window while this thread is still exiting.
        if not thread.wait(2000):
            self.statusBar().showMessage('Preview worker cleanup pending…')
            QTimer.singleShot(250, self._export_preview_cleanup)
            return
        outcome = self._export_preview_outcome
        export_flow = getattr(self, '_export_preview_mode', False)
        self._export_preview_mode = False
        self._export_preview_outcome = None
        self._export_preview_worker = None
        self._export_preview_thread = None
        # Hide the progress window only AFTER the native thread has stopped;
        # defer widget deletion and report construction to later event turns.
        busy = getattr(self, '_export_preview_busy_dialog', None)
        self._export_preview_busy_dialog = None
        if busy is not None:
            busy.finish()
        thread.deleteLater()
        self.statusBar().showMessage('Read-only scanner preview finished.', 5000)
        if outcome is not None:
            # Delay to a later event-loop turn so Qt/Wayland can finish
            # processing all worker and thread deletion events.
            selection = self._export_preview_selection
            QTimer.singleShot(300, lambda result=outcome, flow=export_flow, selected=selection: self._export_preview_show_result(result, flow, selected))

    def _export_preview_show_result(self, outcome, export_flow=False, selection=None):
        if outcome[0] != 'success':
            QMessageBox.warning(self, 'Scanner Export Preview', outcome[1])
            return
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QDialogButtonBox
        dialog = QDialog(self)
        dialog.setWindowTitle('Export to Scanner — Preview & Confirmation' if export_flow
                              else 'Scanner Export Preview — READ ONLY')
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.resize(850, 620)
        layout = QVBoxLayout(dialog)
        if export_flow:
            import re
            report = outcome[1]
            eligible, reason = outcome[2], outcome[3]
            summary = []
            for key in ('ADD', 'REPLACE', 'REMOVE FROM SCANNER', 'UNCHANGED', 'RETAIN ON SCANNER'):
                match = re.search(r'^' + re.escape(key) + r': (\d+)$', report, re.M)
                summary.append(f'{key}: {match.group(1) if match else "unknown"}')
            header = QLabel('Automatic export preview complete.\n' +
                            '   |   '.join(summary) + '\n\n' +
                            ('READY FOR CONTROLLED CONFIGURATION EXPORT\n' if eligible else 'EXPORT BLOCKED\n') +
                            reason + '\n\n' +
                            ('Proceed creates a NEW verified scanner backup, then writes and verifies '
                             'the listed supported configuration files. Scanner acceptance must still '
                             'be tested after restart.\n' if eligible else
                             'No scanner files have been changed.\n') +
                            'Full details are available below.', dialog)
            header.setWordWrap(True)
            layout.addWidget(header)
            if selection:
                from keys_model import export_summary
                keys_note = export_summary(selection[0])
                if keys_note:
                    keys_label = QLabel(keys_note, dialog)
                    keys_label.setWordWrap(True)
                    keys_label.setStyleSheet('color: #e0a040;')
                    layout.addWidget(keys_label)
            toggle = QPushButton('Show technical details', dialog)
            layout.addWidget(toggle)
            view = QPlainTextEdit(dialog)
            view.setReadOnly(True)
            view.setPlainText(report + '\n\nCONTROLLED CONFIGURATION EXPORT ELIGIBILITY\n' + reason)
            view.setVisible(False)
            def toggle_details():
                visible = not view.isVisible()
                view.setVisible(visible)
                toggle.setText('Hide technical details' if visible else 'Show technical details')
            toggle.clicked.connect(toggle_details)
            layout.addWidget(view)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, parent=dialog)
            proceed = buttons.addButton('Proceed with Export', QDialogButtonBox.ButtonRole.AcceptRole)
            proceed.setEnabled(bool(eligible))
            if eligible:
                proceed.clicked.connect(lambda checked=False, selected=selection, window=dialog:
                                        self._confirm_first_scanner_write(selected, window))
            else:
                proceed.setToolTip('Blocked: ' + reason)
        else:
            view = QPlainTextEdit(dialog)
            view.setReadOnly(True)
            view.setPlainText(outcome[1])
            layout.addWidget(view)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        # No nested event loop; keep prior Qt/Wayland worker-teardown safeguards.
        dialog.show()

    def _confirm_first_scanner_write(self, selection, dialog):
        if getattr(self, '_scanner_write_thread', None) is not None or getattr(self, '_db_update_busy', False):
            return
        configuration, scanner = selection
        answer = QMessageBox.warning(
            self, 'Confirm Physical SDS100 Favorites Export',
            'This is a REAL write to the SDS100 SD card, not a simulation.\n\n'
            'The app will first create and SHA-256-verify a fresh full configuration backup, '
            'then replace ONLY ONE existing Favorites HPD file with the listed supported changes.\n\n'
            'Do not unplug the scanner or exit the application while writing. '
            'Afterwards, safely eject/restart the SDS100 and verify the change. '
            'The original HPD can be restored from the saved backup.\n\n'
            'Continue with the physical scanner write?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        dialog.reject()
        self._scanner_write_outcome = None
        self._scanner_write_thread = QThread(self)
        self._scanner_write_worker = ScannerFirstWriteWorker(configuration, scanner)
        self._scanner_write_worker.moveToThread(self._scanner_write_thread)
        self._scanner_write_busy = ExportPreviewBusyDialog(self, writing=True)
        self._scanner_write_busy.show()
        self.statusBar().showMessage('Physical scanner export in progress. DO NOT DISCONNECT.')
        self._scanner_write_thread.started.connect(self._scanner_write_worker.run)
        self._scanner_write_worker.completed.connect(self._scanner_write_completed)
        self._scanner_write_worker.failed.connect(self._scanner_write_failed)
        self._scanner_write_worker.finished.connect(self._scanner_write_worker.deleteLater)
        self._scanner_write_worker.finished.connect(self._scanner_write_thread.quit)
        self._scanner_write_thread.finished.connect(self._scanner_write_cleanup)
        self._scanner_write_thread.start()

    def _scanner_write_completed(self, result):
        self._scanner_write_outcome = ('success', result)

    def _scanner_write_failed(self, error):
        self._scanner_write_outcome = ('failed', error)

    def _scanner_write_cleanup(self):
        thread = getattr(self, '_scanner_write_thread', None)
        if thread is None:
            return
        if not thread.wait(2000):
            QTimer.singleShot(250, self._scanner_write_cleanup)
            return
        outcome = self._scanner_write_outcome
        self._scanner_write_thread = None
        self._scanner_write_worker = None
        self._scanner_write_outcome = None
        busy = self._scanner_write_busy
        self._scanner_write_busy = None
        busy.finish()
        thread.deleteLater()
        QTimer.singleShot(300, lambda result=outcome: self._show_scanner_write_result(result))

    def _show_scanner_write_result(self, outcome):
        if outcome is None or outcome[0] != 'success':
            error = outcome[1] if outcome else 'Unknown write result. Check the scanner and verified backup.'
            self.statusBar().showMessage('Scanner export failed; see recovery instructions.')
            QMessageBox.critical(self, 'Scanner Export — FAILED',
                str(error) + '\n\nDo not assume the scanner file is intact. '
                'Check the fresh backup and recovery instructions before disconnecting.')
            return
        result = outcome[1]
        self._monitor_keys_stamp = None          # v0.1.20: tell SDS100 Monitor the scanner is up to date
        try:
            self._refresh_configuration_label()
        except Exception:
            pass
        self.statusBar().showMessage(f'{len(result["files"])} scanner HPD file(s) written and SHA-256 verified.', 15000)
        QMessageBox.information(self, 'Scanner Export — File Verified',
            f'{len(result["files"])} scanner Favorites HPD file(s) were written and read back with matching SHA-256.\n\n'
            'Files: ' + ', '.join(result['files']) + '\nFresh backup: ' + result['backup'] + '\n\n'
            'Data was flushed to the card. Now unmount/eject the SDS100 in your file manager and wait for the '
            '"safe to remove" message BEFORE powering the scanner off or unplugging it - powering off early can '
            'lose the new files. Then restart it and confirm the Favorites changes '
            'are recognized. The app cannot verify scanner acceptance until you test it.')

    def validate_scanner_configuration(self):
        """Inspect a saved offline configuration without changing any files."""
        from scanner_configurations import list_configurations
        from scanner_configuration_validator import validate_configuration
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QDialogButtonBox
        configs = list_configurations()
        if not configs:
            QMessageBox.information(self, 'Validate Scanner Configuration',
                                    'No saved configurations are available.')
            return
        labels = [f'{manifest["name"]} ({folder.name})' for folder, manifest in configs]
        choice, ok = QInputDialog.getItem(self, 'Validate Scanner Configuration',
            'Select a saved local configuration to inspect (read-only):', labels, 0, False)
        if not ok:
            return
        folder, manifest = configs[labels.index(choice)]
        report = validate_configuration(folder, manifest)
        lines = [f'Configuration: {manifest["name"]}',
                 f'Native Favorites files inspected: {report["files"]}',
                 f'Errors: {len(report["errors"])}    Warnings: {len(report["warnings"])}',
                 '', 'ERRORS']
        lines.extend(report['errors'] or ['None detected'])
        lines.extend(['', 'WARNINGS'])
        lines.extend(report['warnings'] or ['None detected'])
        lines.extend(['', 'Read-only structural review only. This is NOT a certification',
                      'of scanner-native format compatibility or export safety.',
                      'No scanner or saved configuration files were changed.'])
        dialog = QDialog(self)
        dialog.setWindowTitle('Scanner Configuration Validation — ' + manifest['name'])
        dialog.resize(820, 560)
        layout = QVBoxLayout(dialog)
        output = QPlainTextEdit(dialog)
        output.setReadOnly(True)
        output.setPlainText('\n'.join(lines))
        layout.addWidget(output)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def show_scanner_configurations(self):
        """Choose an offline configuration; edit via native-origin working drafts."""
        from scanner_configurations import list_configurations, library_path, verify_configuration
        configs = list_configurations()
        if not configs:
            QMessageBox.information(self, 'Open Scanner Configuration',
                f'No saved scanner configurations yet.\nLibrary: {library_path()}')
            return
        labels = [f'{data["name"]} ({len(data["files"])} files)' for path, data in configs]
        choice, ok = QInputDialog.getItem(self, 'Open Scanner Configuration',
            'Open which scanner configuration?', labels, 0, False)
        if not ok:
            return
        path, manifest = configs[labels.index(choice)]
        try:
            if self._open_configuration(path, manifest):
                self._offer_recovery()
        except (OSError, ValueError, UnicodeError) as exc:
            QMessageBox.warning(self, 'Unable to open configuration', str(exc))

    def save_scanner_configuration_as(self):
        """Save all current native working edits into a NEW local configuration."""
        from scanner_configurations import (library_path, list_configurations,
                                            save_configuration_as, verify_configuration)
        from native_favorites_export import build_native_bytes
        folder = getattr(self, 'active_scanner_configuration', None)
        if folder is None:
            QMessageBox.information(self, 'Open configuration first',
                'Open a local scanner configuration before choosing Save As.')
            return
        source = Path(folder).resolve()
        if source.parent != library_path().resolve():
            QMessageBox.warning(self, 'Save As blocked', 'Only local scanner configurations can be copied.')
            return
        try:
            verify_configuration(source)
            edits = {}
            for draft_name, entries in self.workspace.drafts.items():
                if not entries or entries[0].get('scope') != 'metadata':
                    continue
                path = entries[0].get('source_path')
                if not path:
                    continue
                native = Path(path).resolve()
                if not native.is_relative_to(source / 'BCDx36HP' / 'favorites_lists'):
                    continue
                if not str(entries[0].get('key', [''])[0]).startswith('native-copy-meta'):
                    raise ValueError(f'Cannot Save As: {draft_name} is not a verified native working copy.')
                payload, rows = build_native_bytes(entries)
                if payload != native.read_bytes():
                    edits[str(native.relative_to(source))] = (payload, rows)
            original_name = next((manifest['name'] for p, manifest in list_configurations()
                                  if p.resolve() == source), source.name)
            name, ok = QInputDialog.getText(self, 'Save Scanner Configuration As…',
                'New independent LOCAL configuration name:', text=original_name + ' Copy')
            if not ok:
                return
            if QMessageBox.question(self, 'Confirm Save As',
                    f'Create an independent local configuration named {name.strip()!r}?\n\n'
                    f'Includes {len(edits)} edited Favorites List(s) from the current workspace.\n'
                    'Original local configuration remains unchanged.\n'
                    'The physical scanner will NOT be changed.',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
            destination, manifest = save_configuration_as(source, name, edits)
            # The edits are in the new configuration's files now; open it fresh.
            self._open_configuration(destination, manifest, check_unsaved=False)
            self.statusBar().showMessage(f'Saved independent local configuration: {manifest["name"]}')
            QMessageBox.information(self, 'Save As completed',
                f'Created and opened: {manifest["name"]}\n'
                f'Verified files: {len(manifest["files"])}\n'
                f'Working Favorites edits included: {len(edits)}\n\n'
                'Original configuration and scanner unchanged.')
        except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
            QMessageBox.warning(self, 'Save As blocked', str(exc))

    def rename_scanner_configuration(self):
        from scanner_configurations import list_configurations, rename_local_configuration
        configs = list_configurations()
        if not configs:
            QMessageBox.information(self, 'Rename Scanner Configuration', 'No saved configurations.')
            return
        labels = [f'{m["name"]} ({p.name})' for p, m in configs]
        choice, ok = QInputDialog.getItem(self, 'Rename Scanner Configuration',
            'Choose a local configuration:', labels, 0, False)
        if not ok: return
        folder, manifest = configs[labels.index(choice)]
        name, ok = QInputDialog.getText(self, 'Rename Scanner Configuration',
            'New display name:', text=manifest['name'])
        if not ok or name == manifest['name']: return
        try:
            new_name = rename_local_configuration(folder, name)
            QMessageBox.information(self, 'Configuration renamed',
                f'Local configuration renamed to {new_name}.\nScanner unchanged.')
        except (OSError, ValueError, KeyError) as exc:
            QMessageBox.warning(self, 'Rename blocked', str(exc))

    def delete_scanner_configuration(self):
        from scanner_configurations import list_configurations, delete_local_configuration
        configs = list_configurations()
        if not configs:
            QMessageBox.information(self, 'Delete Scanner Configuration', 'No saved configurations.')
            return
        labels = [f'{m["name"]} ({p.name})' for p, m in configs]
        choice, ok = QInputDialog.getItem(self, 'Delete Scanner Configuration',
            'Select a saved LOCAL configuration to delete:', labels, 0, False)
        if not ok: return
        folder, manifest = configs[labels.index(choice)]
        active = getattr(self, 'active_scanner_configuration', None)
        if active is not None and Path(active).resolve() == folder.resolve():
            QMessageBox.warning(self, 'Deletion blocked',
                'This configuration is currently open. Open another configuration or '
                'restart the application without opening this configuration before deleting it.\n'
                'This protects unsaved working changes.')
            return
        answer = QMessageBox.warning(self, 'Confirm local configuration deletion',
            f'Delete the saved LOCAL configuration?\n\n{manifest["name"]}\n'
            f'Folder: {folder}\n\nThis removes its local configuration files. '
            'Verified backups and recovery checkpoints are retained separately.\n'
            'The physical scanner will NOT be changed.\n\nThis cannot be undone from this dialog.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes: return
        try:
            delete_local_configuration(folder)
            QMessageBox.information(self, 'Configuration deleted',
                f'Deleted local configuration: {manifest["name"]}\n'
                'Verified backup history retained. Scanner unchanged.')
        except (OSError, ValueError, KeyError) as exc:
            QMessageBox.warning(self, 'Deletion blocked', str(exc))

    def inspect_scanner_settings(self):
        """Read-only inspection of imported configuration metadata; never interpret unknown fields."""
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QTabWidget, QTextEdit,
                                     QDialogButtonBox, QLabel)
        from scanner_configurations import list_configurations, verify_configuration
        configs = list_configurations()
        if not configs:
            QMessageBox.information(self, 'Scanner Settings',
                                    'Import a scanner configuration first.')
            return
        active = getattr(self, 'active_scanner_configuration', None)
        if active is not None:
            matches = [(p, m) for p, m in configs if p.resolve() == Path(active).resolve()]
        else:
            matches = []
        if matches:
            folder, manifest = matches[0]
        else:
            labels = [f'{m["name"]} ({len(m["files"])} files)' for _, m in configs]
            chosen, ok = QInputDialog.getItem(self, 'Inspect Scanner Settings',
                                              'Select a local configuration:', labels, 0, False)
            if not ok: return
            folder, manifest = configs[labels.index(chosen)]
        try:
            verify_configuration(folder, manifest)
            dlg = QDialog(self)
            dlg.setWindowTitle(f'Scanner Settings — {manifest["name"]} (read-only)')
            dlg.resize(960, 650)
            layout = QVBoxLayout(dlg)
            layout.addWidget(QLabel('Imported scanner configuration files — inspection only. '
                                    'Unknown fields are preserved unchanged.'))
            tabs = QTabWidget(dlg)
            names = ('profile.cfg', 'app_data.cfg', 'scanner.inf', 'discovery.cfg')
            for name in names:
                file = folder / 'BCDx36HP' / name
                editor = QTextEdit(dlg)
                editor.setReadOnly(True)
                editor.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
                if not file.is_file():
                    editor.setPlainText('File not present in this imported configuration.')
                else:
                    data = file.read_bytes()
                    if len(data) > 2_000_000:
                        editor.setPlainText('File exceeds the 2 MB inspection limit; no changes made.')
                    elif b'\x00' in data:
                        editor.setPlainText(f'Binary configuration file ({len(data)} bytes). '
                                            'Raw text display is disabled to avoid misinterpreting it.')
                    else:
                        editor.setPlainText(data.decode('utf-8', errors='replace'))
                tabs.addTab(editor, name)
            layout.addWidget(tabs)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dlg)
            buttons.rejected.connect(dlg.reject)
            layout.addWidget(buttons)
            dlg.exec()
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Scanner Settings', str(exc))

    def inspect_favorites_list_relationships(self):
        """Inspect native Favorites Lists and quick-key statuses without guessing .hpd fields."""
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QTableWidget,
                                     QTableWidgetItem, QDialogButtonBox)
        from scanner_configurations import list_configurations, verify_configuration
        from quick_keys_settings import read_quick_keys
        from native_favorites_reader import parse_native_favorites
        from favorites_manager import FavoritesManager
        configs = list_configurations()
        if not configs:
            QMessageBox.information(self, 'Favorites List Relationships',
                                    'Import a scanner configuration first.')
            return
        active = getattr(self, 'active_scanner_configuration', None)
        matching = [(p,m) for p,m in configs if active and p.resolve()==Path(active).resolve()]
        if matching:
            folder, manifest = matching[0]
        else:
            labels = [m['name'] for _,m in configs]
            choice, ok = QInputDialog.getItem(self, 'Favorites List Relationships',
                                              'Local configuration:', labels, 0, False)
            if not ok: return
            folder, manifest = configs[labels.index(choice)]
        try:
            verify_configuration(folder, manifest)
            statuses = read_quick_keys((folder/'BCDx36HP'/'profile.cfg').read_bytes())
            favorites_dir = folder/'BCDx36HP'/'favorites_lists'
            favorites = sorted(favorites_dir.glob('*.hpd'))
            names = FavoritesManager.favorites_names(favorites_dir)
            dlg = QDialog(self)
            dlg.setWindowTitle('Favorites List Relationships — ' + manifest['name'])
            dlg.resize(900, 570)
            layout = QVBoxLayout(dlg)
            layout.addWidget(QLabel(
                'Favorites Lists and their systems (read-only). Favorites → Keys & Tags… shows which list, '
                'system and department each quick key switches.'))
            table = QTableWidget(len(favorites), 3, dlg)
            table.setHorizontalHeaderLabels(['Favorites List Name', 'Systems', 'System Names'])
            for row, path in enumerate(favorites):
                parsed = parse_native_favorites(path)
                systems = parsed['systems']
                display_name = names.get(path.name.casefold())
                if not display_name:
                    display_name = 'Unnamed Favorites List (name unavailable)'
                values = (display_name, str(len(systems)),
                          ', '.join(item['name'] for item in systems))
                for col, value in enumerate(values):
                    table.setItem(row, col, QTableWidgetItem(value))
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            table.setColumnWidth(0, 300)
            table.setColumnWidth(1, 90)
            table.setColumnWidth(2, 465)
            layout.addWidget(table)
            on_count = sum(statuses)
            layout.addWidget(QLabel(
                f'Favorites List quick keys: {on_count} On, {100-on_count} Off (00–99). '
                'Favorites → Keys & Tags… shows what each one is assigned to.'))
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dlg)
            buttons.rejected.connect(dlg.reject)
            layout.addWidget(buttons)
            dlg.exec()
        except (OSError, ValueError, UnicodeError) as exc:
            QMessageBox.warning(self, 'Favorites List Relationships', str(exc))

    def edit_quick_keys_settings(self):
        """Favorites → Quick Keys… (v0.1.6): what each quick key is assigned to, at all three levels."""
        from scanner_configurations import list_configurations, verify_configuration
        from quick_keys_window import QuickKeysWindow
        configs = list_configurations()
        if not configs:
            QMessageBox.information(self, 'Quick Keys', 'Import a scanner configuration first.')
            return
        active = getattr(self, 'active_scanner_configuration', None)
        matches = [(p,m) for p,m in configs if active and p.resolve()==Path(active).resolve()]
        if matches:
            folder, manifest = matches[0]
        else:
            labels = [m['name'] for _,m in configs]
            choice, ok = QInputDialog.getItem(self, 'Quick Keys', 'Local configuration:', labels, 0, False)
            if not ok: return
            folder, manifest = configs[labels.index(choice)]
        try:
            verify_configuration(folder, manifest)
            QuickKeysWindow(self, folder, manifest).exec()
        except (OSError, ValueError, UnicodeError) as exc:
            QMessageBox.warning(self, 'Quick Keys', str(exc))

    def _edit_profile_settings(self, window_title, kinds):
        """Edit the validated profile.cfg records in `kinds` (one tab each); retain all other bytes."""
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QTableWidget, QTabWidget,
                                     QTableWidgetItem, QDialogButtonBox, QComboBox, QLineEdit)
        from scanner_configurations import list_configurations, verify_configuration
        from profile_schema import SCHEMA, check_layout, patch_fields, describe, fields_of
        from location_settings import save_profile
        active = getattr(self, 'active_scanner_configuration', None)
        matches = [(folder, manifest) for folder, manifest in list_configurations()
                   if active and folder.resolve() == Path(active).resolve()]
        if not matches:
            QMessageBox.information(self, window_title, 'Open a local scanner configuration first.')
            return
        folder, manifest = matches[0]
        try:
            verify_configuration(folder, manifest)
            original = (folder / 'BCDx36HP' / 'profile.cfg').read_bytes()
            dlg = QDialog(self)
            dlg.setWindowTitle(window_title + ' — ' + manifest['name'])
            dlg.resize(860, 660)
            layout = QVBoxLayout(dlg)
            layout.addWidget(QLabel('Settings with a dropdown or text box can be changed. Reserved and '
                                    'unsupported fields are read-only and preserved exactly. Values are '
                                    'checked against Uniden\'s file specification.'))
            tabs = QTabWidget(dlg)
            layout.addWidget(tabs, 1)
            all_tabs = (('GlobalSetting', 'Global'), ('CloseCall', 'Close Call'),
                          ('SearchCommon', 'Search (common)'), ('Weather', 'Weather'),
                          ('WxSameList', 'Weather SAME groups'), ('LimitSearch', 'Limit Search'),
                          ('ToneOut', 'Tone-Out'), ('Waterfall', 'Waterfall'),
                          ('CustomWfBand', 'Waterfall bands'), ('WfColors', 'Waterfall colours'),
                          ('BandDefault', 'Band defaults'), ('PresetBroadcastScreen', 'Broadcast screen'),
                          ('CustomBroadcastScreen', 'Custom broadcast screen'), ('DisplayOption', 'Display'),
                          ('Backlight', 'Backlight'), ('Battery', 'Battery'), ('OwnerInfo', 'Owner info'),
                          ('ClockOption', 'Clock'), ('RecordingOption', 'Recording'),
                          ('StandbyOption', 'Standby (read-only)'),
                          ('DispOptItems', 'Screen items'), ('DispColors', 'Screen colours'))
            tab_titles = tuple(tab for tab in all_tabs if tab[0] in kinds)
            controls = {}      # (kind, row, position) -> (widget, original value)
            for kind, title in tab_titles:
                try:
                    rows = check_layout(original, kind)
                except ValueError as exc:
                    note = QLabel(f'{title} is not shown: {exc}')
                    note.setWordWrap(True)
                    tabs.addTab(note, title)
                    continue
                fields = SCHEMA[kind].get('fields')

                def make_widget(field, value, parent):
                    choices = field.choices()
                    if field.editable and choices is not None and value in choices:
                        widget = QComboBox(parent)
                        widget.addItems(choices)
                        widget.setCurrentText(value)
                        return widget
                    if field.editable and choices is None and field.valid(value):
                        return QLineEdit(value, parent)
                    return None

                if 'fields_for' in SCHEMA[kind]:
                    # Display layouts/colours: records differ in length. One grid row per record; the
                    # identifier columns are read-only and the record length never changes.
                    width = max(len(row) for row in rows)
                    table = QTableWidget(len(rows), width, dlg)
                    table.setHorizontalHeaderLabels(['Row / set', 'Layout'] + ['Slot %d' % n for n in range(1, width - 1)])
                    for column in range(width):
                        table.setColumnWidth(column, 120 if column < 2 else 130)
                    for row_index, row in enumerate(rows):
                        row_fields = fields_of(kind, row)
                        for column, (field, value) in enumerate(zip(row_fields, row)):
                            widget = make_widget(field, value, table)
                            if widget is None:
                                cell = QTableWidgetItem(value if value else '(empty)')
                                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                                table.setItem(row_index, column, cell)
                            else:
                                widget.setToolTip(field.label)
                                table.setCellWidget(row_index, column, widget)
                                controls[(kind, row_index, column + 1)] = (widget, value)
                    tabs.addTab(table, title)
                    continue
                if len(rows) > 1:
                    # One grid row per record (Limit Search, Tone-Out, band defaults, ...); reserved
                    # columns are left out but preserved exactly.
                    shown = [i for i, f in enumerate(fields) if f.editable or not f.label.startswith('Reserved')]
                    table = QTableWidget(len(rows), len(shown), dlg)
                    table.setHorizontalHeaderLabels([fields[i].label for i in shown])
                    for column, i in enumerate(shown):
                        table.setColumnWidth(column, 150 if fields[i].kind in ('choice', 'int') else 190)
                    for row_index, row in enumerate(rows):
                        for column, i in enumerate(shown):
                            position, field, value = i + 1, fields[i], row[i]
                            widget = make_widget(field, value, table)
                            if widget is None:
                                cell = QTableWidgetItem(value if value else '(empty)')
                                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                                table.setItem(row_index, column, cell)
                            else:
                                table.setCellWidget(row_index, column, widget)
                                controls[(kind, row_index, position)] = (widget, value)
                    tabs.addTab(table, title)
                    continue
                table = QTableWidget(len(fields), 3, dlg)
                table.setHorizontalHeaderLabels(['Position', 'Setting', 'Value'])
                table.setColumnWidth(0, 80)
                table.setColumnWidth(1, 330)
                table.setColumnWidth(2, 330)
                row = rows[0]
                for line, (field, value) in enumerate(zip(fields, row)):
                    position = line + 1
                    for column, content in ((0, str(position)), (1, field.label)):
                        cell = QTableWidgetItem(content)
                        cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        table.setItem(line, column, cell)
                    widget = make_widget(field, value, table)
                    if widget is None:
                        cell = QTableWidgetItem(value if value else '(empty)')
                        cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        table.setItem(line, 2, cell)
                    else:
                        table.setCellWidget(line, 2, widget)
                        controls[(kind, 0, position)] = (widget, value)
                tabs.addTab(table, title)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                       QDialogButtonBox.StandardButton.Cancel, parent=dlg)
            buttons.rejected.connect(dlg.reject)

            def current(widget):
                return widget.currentText() if isinstance(widget, QComboBox) else widget.text()

            def commit():
                try:
                    changes = {key: current(widget) for key, (widget, old) in controls.items()
                               if current(widget) != old}
                    if not changes:
                        dlg.accept()
                        return
                    payload = patch_fields(original, changes)
                    from scanner_profile_export import assess_profile_replacement
                    valid, detail, _ = assess_profile_replacement(original, payload)
                    if not valid:
                        raise ValueError('Export validation rejected settings: ' + detail)
                    if QMessageBox.question(dlg, 'Review Scanner Settings Changes',
                        'The following validated changes will be saved locally:\n\n'
                        + '\n'.join(describe(original, changes))
                        + '\n\nThe physical scanner will not be changed until you export. Continue?'
                        ) != QMessageBox.StandardButton.Yes:
                        return
                    changed = save_profile(folder, payload)
                    QMessageBox.information(dlg, window_title,
                        'Local configuration saved with backup.' if changed else 'No changes to save.')
                    dlg.accept()
                except (OSError, ValueError, UnicodeError) as exc:
                    QMessageBox.warning(dlg, window_title + ' not saved', str(exc))
            buttons.accepted.connect(commit)
            layout.addWidget(buttons)
            dlg.exec()
        except (OSError, ValueError, UnicodeError) as exc:
            QMessageBox.warning(self, window_title, str(exc))

    def edit_global_settings(self):
        self._edit_profile_settings('Global Settings', ('GlobalSetting',))

    def edit_search_settings(self):
        self._edit_profile_settings('Search Settings', (
            'SearchCommon', 'CloseCall', 'LimitSearch', 'ToneOut', 'BandDefault', 'Waterfall',
            'CustomWfBand', 'WfColors', 'PresetBroadcastScreen', 'CustomBroadcastScreen'))

    def edit_weather_settings(self):
        self._edit_profile_settings('Weather Settings', ('Weather', 'WxSameList'))

    def edit_display_settings(self):
        self._edit_profile_settings('Display Settings', ('DisplayOption', 'Backlight'))

    def edit_display_layouts(self):
        self._edit_profile_settings('Display Layouts and Colours', ('DispOptItems', 'DispColors'))

    def edit_hardware_settings(self):
        self._edit_profile_settings('Hardware Settings', (
            'Battery', 'OwnerInfo', 'ClockOption', 'RecordingOption', 'StandbyOption'))

    def edit_favorites_list_settings(self):
        """Edit per-list settings (name, quick key, number tag, monitor, startup/system keys) locally."""
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QGridLayout, QTableWidget, QTableWidgetItem,
                                     QDialogButtonBox, QComboBox, QLineEdit, QPushButton, QCheckBox,
                                     QScrollArea, QWidget)
        from scanner_configurations import (list_configurations, verify_configuration,
                                            save_local_flist_settings, INDEX_KEY)
        import flist_settings as fls
        active = getattr(self, 'active_scanner_configuration', None)
        matches = [(folder, manifest) for folder, manifest in list_configurations()
                   if active and folder.resolve() == Path(active).resolve()]
        if not matches:
            QMessageBox.information(self, 'Favorites List Settings', 'Open a local scanner configuration first.')
            return
        folder, manifest = matches[0]
        try:
            verify_configuration(folder, manifest)
            original = (folder / INDEX_KEY).read_bytes()
            lists = fls.read_lists(original)
            if not lists:
                raise ValueError('This configuration has no Favorites Lists.')
            dlg = QDialog(self)
            dlg.setWindowTitle('Favorites List Settings — ' + manifest['name'])
            dlg.resize(1000, 640)
            layout = QVBoxLayout(dlg)
            layout.addWidget(QLabel('Two lists cannot share a quick key or a number tag. Changes are saved to the '
                                    'local configuration; use Export to Scanner to send them to the scanner.'))
            headers = ['Name', 'Location Control', 'Monitor', 'Quick Key', 'Number Tag', 'Startup / System Keys']
            table = QTableWidget(len(lists), len(headers), dlg)
            table.setHorizontalHeaderLabels(headers)
            table.setColumnWidth(0, 330)
            for column, width in ((1, 120), (2, 90), (3, 90), (4, 100), (5, 170)):
                table.setColumnWidth(column, width)
            numbers = ('Off',) + tuple(str(i) for i in range(100))
            rows = []      # per list: widgets and key state
            for index, item in enumerate(lists):
                name = QLineEdit(item['name'], table)
                name.setMaxLength(fls.NAME_MAX)
                table.setCellWidget(index, 0, name)
                combos = []
                for column, choices, value in ((1, fls.ONOFF, item['location']), (2, fls.ONOFF, item['monitor']),
                                               (3, numbers, item['quick_key']), (4, numbers, item['number_tag'])):
                    box = QComboBox(table)
                    box.addItems(choices)
                    box.setCurrentText(value)
                    table.setCellWidget(index, column, box)
                    combos.append(box)
                state = {'startup': list(item['startup']), 'system_keys': list(item['system_keys'])}
                button = QPushButton('Edit keys…', table)

                def open_keys(_=False, item=item, state=state):
                    import quick_key_map as qk
                    from favorites_explorer import read_text
                    try:
                        text, _enc = read_text(folder / 'BCDx36HP' / 'favorites_lists' / item['filename'])
                        system_names = qk.owners(qk.read_systems([l.split('\t') for l in text.splitlines()]))
                    except (OSError, ValueError, UnicodeError):
                        system_names = {}
                    sub = QDialog(dlg)
                    sub.setWindowTitle('Keys — ' + item['name'])
                    sub.resize(900, 620)
                    outer = QVBoxLayout(sub)
                    note = QLabel('<b>Startup keys 0–9:</b> ticked keys include this list when the scanner starts '
                                  'with that startup key held.<br><b>System quick keys 00–99</b> of this list: each '
                                  'shows the systems assigned to it; ticked = On (scanned), unticked = Off. Keys '
                                  'marked — have no system. Favorites → Keys & Tags… shows all three levels.')
                    note.setWordWrap(True)
                    outer.addWidget(note)
                    scroll = QScrollArea(sub)
                    scroll.setWidgetResizable(True)
                    holder = QWidget()
                    grid = QGridLayout(holder)
                    boxes = {'startup': [], 'system_keys': []}
                    for number in range(10):
                        check = QCheckBox('Startup %d' % number)
                        check.setChecked(state['startup'][number] == 'On')
                        grid.addWidget(check, number // 5, number % 5)
                        boxes['startup'].append(check)
                    for number in range(100):
                        names = system_names.get(number, [])
                        check = QCheckBox('%02d  %s' % (number, ', '.join(names) if names else '—'))
                        check.setChecked(state['system_keys'][number] == 'On')
                        grid.addWidget(check, 3 + number // 4, number % 4)
                        boxes['system_keys'].append(check)
                    scroll.setWidget(holder)
                    outer.addWidget(scroll, 1)
                    ok = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                          QDialogButtonBox.StandardButton.Cancel, parent=sub)
                    ok.rejected.connect(sub.reject)

                    def accept_keys():
                        for key in ('startup', 'system_keys'):
                            state[key] = ['On' if c.isChecked() else 'Off' for c in boxes[key]]
                        sub.accept()
                    ok.accepted.connect(accept_keys)
                    outer.addWidget(ok)
                    sub.exec()
                button.clicked.connect(open_keys)
                table.setCellWidget(index, 5, button)
                rows.append((name, combos, state))
            layout.addWidget(table, 1)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                       QDialogButtonBox.StandardButton.Cancel, parent=dlg)
            buttons.rejected.connect(dlg.reject)

            def commit():
                try:
                    updated = []
                    for item, (name, combos, state) in zip(lists, rows):
                        updated.append({'filename': item['filename'], 'name': name.text(),
                                        'location': combos[0].currentText(), 'monitor': combos[1].currentText(),
                                        'quick_key': combos[2].currentText(), 'number_tag': combos[3].currentText(),
                                        'startup': state['startup'], 'system_keys': state['system_keys']})
                    edits = fls.edits_between(lists, updated)
                    if not edits:
                        dlg.accept()
                        return
                    fls.check_edits(lists, edits)
                    summary = fls.describe(lists, edits)
                    shown = '\n'.join(summary[:25]) + (f'\n… and {len(summary) - 25} more' if len(summary) > 25 else '')
                    if QMessageBox.question(dlg, 'Review Favorites List Settings Changes',
                        'The following validated changes will be saved locally:\n\n' + shown +
                        '\n\nThe physical scanner will not be changed until you export. Continue?'
                        ) != QMessageBox.StandardButton.Yes:
                        return
                    save_local_flist_settings(folder, edits)
                    QMessageBox.information(dlg, 'Favorites List Settings',
                                            'Saved to the local configuration (previous index backed up).')
                    dlg.accept()
                except (OSError, ValueError, UnicodeError) as exc:
                    QMessageBox.warning(dlg, 'Favorites List Settings not saved', str(exc))
            buttons.accepted.connect(commit)
            layout.addWidget(buttons)
            dlg.exec()
        except (OSError, ValueError, UnicodeError) as exc:
            QMessageBox.warning(self, 'Favorites List Settings', str(exc))

    def edit_service_type_settings(self):
        """Edit documented ServiceType flags in the active offline profile."""
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QGridLayout, QCheckBox,
                                     QDialogButtonBox, QScrollArea, QWidget)
        from scanner_configurations import list_configurations, verify_configuration
        from location_settings import save_profile
        from scanner_profile_records import read_service_types, patch_service_types, read_custom_service_types, patch_custom_service_types
        configs = list_configurations()
        if not configs:
            QMessageBox.information(self, 'Service Types', 'Import a scanner configuration first.')
            return
        active = getattr(self, 'active_scanner_configuration', None)
        matches = [(folder, manifest) for folder, manifest in configs
                   if active and folder.resolve() == Path(active).resolve()]
        if not matches:
            QMessageBox.warning(self, 'Service Types', 'Open a scanner configuration before editing service types.')
            return
        folder, manifest = matches[0]
        try:
            verify_configuration(folder, manifest)
            original = (folder / 'BCDx36HP' / 'profile.cfg').read_bytes()
            states = read_service_types(original)
            custom_states = read_custom_service_types(original)
            labels = ('Multi-Dispatch', 'Law Dispatch', 'Fire Dispatch', 'EMS Dispatch',
                      'Reserved 05', 'Multi-Tac', 'Law Tac', 'Fire-Tac', 'EMS-Tac',
                      'Reserved 10', 'Interop', 'Hospital', 'Ham', 'Public Works',
                      'Aircraft', 'Federal', 'Business', 'Reserved 18', 'Reserved 19',
                      'Railroad', 'Other', 'Multi-Talk', 'Law Talk', 'Fire-Talk',
                      'EMS-Talk', 'Transportation', 'Reserved 27', 'Reserved 28',
                      'Emergency Ops', 'Military', 'Media', 'Schools', 'Security',
                      'Utilities', 'Reserved 35', 'Reserved 36', 'Corrections')
            dlg = QDialog(self)
            dlg.setWindowTitle('Service Types — ' + manifest['name'])
            dlg.resize(650, 590)
            layout = QVBoxLayout(dlg)
            layout.addWidget(QLabel('Standard 01–37 and Custom 1–8 / Racing — local profile only. Scanner unchanged until export.\n'
                                    'Reserved entries are shown but cannot be changed.'))
            scroll = QScrollArea(dlg)
            scroll.setWidgetResizable(True)
            holder = QWidget(scroll)
            grid = QGridLayout(holder)
            boxes = []
            for index, (label, enabled) in enumerate(zip(labels, states)):
                box = QCheckBox(f'{index + 1:02d} — {label}', holder)
                box.setChecked(enabled)
                if label.startswith('Reserved'):
                    box.setEnabled(False)
                grid.addWidget(box, index // 2, index % 2)
                boxes.append(box)
            # CustomServiceType contains ten fixed On/Off flags, not editable names.
            custom_heading = QLabel('Custom Service Types — Custom 1–8 and Racing', holder)
            grid.addWidget(custom_heading, 19, 0, 1, 2)
            custom_boxes = []
            for index, enabled in enumerate(custom_states):
                label = f'Custom {index + 1}' if index < 8 else ('Racing Officials', 'Racing Teams')[index - 8]
                box = QCheckBox(f'{208 + index} — {label}', holder)
                box.setChecked(enabled)
                grid.addWidget(box, 20 + index // 2, index % 2)
                custom_boxes.append(box)
            scroll.setWidget(holder)
            layout.addWidget(scroll)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                       QDialogButtonBox.StandardButton.Cancel, parent=dlg)
            buttons.rejected.connect(dlg.reject)
            def commit():
                try:
                    payload = patch_service_types(original, [box.isChecked() for box in boxes])
                    payload = patch_custom_service_types(payload, [box.isChecked() for box in custom_boxes])
                    if payload != original:
                        if QMessageBox.question(dlg, 'Save Service Types',
                            'Save Service Types to the LOCAL scanner configuration?\n'
                            'A verified profile backup will be retained.\n'
                            'The physical scanner will not be changed.') != QMessageBox.StandardButton.Yes:
                            return
                    changed = save_profile(folder, payload)
                    QMessageBox.information(dlg, 'Service Types',
                        'Local configuration saved with backup.' if changed else 'No changes to save.')
                    dlg.accept()
                except (OSError, ValueError, UnicodeError) as exc:
                    QMessageBox.warning(dlg, 'Service Types not saved', str(exc))
            buttons.accepted.connect(commit)
            layout.addWidget(buttons)
            dlg.exec()
        except (OSError, ValueError, UnicodeError) as exc:
            QMessageBox.warning(self, 'Service Types', str(exc))

    def edit_location_settings(self):
        """Edit recognized GPS/location profile fields, preserving other native records."""
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit,
                                     QComboBox, QTableWidget, QTableWidgetItem,
                                     QHBoxLayout, QDialogButtonBox, QPushButton)
        from scanner_configurations import list_configurations, verify_configuration
        from location_settings import read_location_settings, patch_profile, save_profile, format_coordinate, parse_display_coordinate, display_coordinate
        configs = list_configurations()
        if not configs:
            QMessageBox.information(self, 'GPS and Location Settings', 'Import a scanner configuration first.')
            return
        active = getattr(self, 'active_scanner_configuration', None)
        matches = [(p,m) for p,m in configs if active and p.resolve()==Path(active).resolve()]
        if matches: folder, manifest = matches[0]
        else:
            labels=[m['name'] for _,m in configs]
            choice,ok=QInputDialog.getItem(self,'GPS and Location Settings','Local configuration:',labels,0,False)
            if not ok:return
            folder,manifest=configs[labels.index(choice)]
        try:
            verify_configuration(folder,manifest)
            original=(folder/'BCDx36HP'/'profile.cfg').read_bytes()
            current,gps,saved=read_location_settings(original)
            dlg=QDialog(self);dlg.setWindowTitle('GPS and Location Settings — '+manifest['name']);dlg.resize(760,540)
            layout=QVBoxLayout(dlg)
            layout.addWidget(QLabel('Offline profile settings only — no live GPS or scanner communication.'))
            form=QFormLayout();fields=[]
            for title,value in zip(('Current latitude','Current longitude','Current range'),current):
                field=QLineEdit(display_coordinate(value, len(fields)==0, gps[0]) if len(fields)<2 else value,dlg);form.addRow(title,field);fields.append(field)
            fmt=QComboBox(dlg);fmt.addItems(['DMS','DEG']);fmt.setCurrentText(gps[0]);form.addRow('GPS coordinate format',fmt)
            baud=QComboBox(dlg);baud.addItems(['4800','9600','19200','38400','57600','115200']);baud.setCurrentText(gps[1]);form.addRow('GPS serial baud rate',baud)
            layout.addLayout(form)
            layout.addWidget(QLabel('Saved locations (name, latitude, longitude, range):'))
            table=QTableWidget(len(saved),4,dlg);table.setHorizontalHeaderLabels(['Name','Latitude','Longitude','Range'])
            for i,entry in enumerate(saved):
                for j,value in enumerate(entry):table.setItem(i,j,QTableWidgetItem(display_coordinate(value, j==1, gps[0]) if j in (1,2) else value))
            def convert_view(new_format):
                old_format = getattr(dlg, '_coordinate_view_format', gps[0])
                if new_format == old_format: return
                try:
                    replacements = []
                    for index in range(2):
                        decimal = parse_display_coordinate(fields[index].text(), index == 0, old_format)
                        replacements.append((fields[index], display_coordinate(decimal, index == 0, new_format)))
                    for i in range(table.rowCount()):
                        for j in (1, 2):
                            item = table.item(i, j)
                            if item and item.text().strip():
                                decimal = parse_display_coordinate(item.text(), j == 1, old_format)
                                replacements.append((item, display_coordinate(decimal, j == 1, new_format)))
                    for widget, value in replacements: widget.setText(value)
                    dlg._coordinate_view_format = new_format
                except ValueError as exc:
                    QMessageBox.warning(dlg, 'Invalid coordinate', str(exc) + '\nCorrect the coordinate before changing format.')
                    fmt.blockSignals(True);fmt.setCurrentText(old_format);fmt.blockSignals(False)
            dlg._coordinate_view_format = gps[0]
            fmt.currentTextChanged.connect(convert_view)
            table.horizontalHeader().setStretchLastSection(True);layout.addWidget(table)
            row=QHBoxLayout();add=QPushButton('Add Location');remove=QPushButton('Remove Selected')
            add.clicked.connect(lambda:table.insertRow(table.rowCount()))
            remove.clicked.connect(lambda:table.removeRow(table.currentRow()) if table.currentRow()>=0 else None)
            row.addWidget(add);row.addWidget(remove);row.addStretch();layout.addLayout(row)
            buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel,dlg)
            buttons.rejected.connect(dlg.reject)
            def commit():
                try:
                    entries=[[table.item(i,j).text().strip() if table.item(i,j) else '' for j in range(4)] for i in range(table.rowCount())]
                    view_format = dlg._coordinate_view_format
                    for entry in entries:
                        if entry[1]: entry[1] = parse_display_coordinate(entry[1], True, view_format)
                        if entry[2]: entry[2] = parse_display_coordinate(entry[2], False, view_format)
                    current_values = [parse_display_coordinate(fields[0].text(), True, view_format), parse_display_coordinate(fields[1].text(), False, view_format), fields[2].text().strip()]
                    payload=patch_profile(original,current_values,[fmt.currentText(),baud.currentText()],entries)
                    if payload!=original and QMessageBox.question(dlg,'Save GPS and location settings','Update the LOCAL scanner configuration?\nA verified backup of profile.cfg will be retained.\nNo scanner files will be written.')!=QMessageBox.StandardButton.Yes:return
                    changed=save_profile(folder,payload)
                    QMessageBox.information(dlg,'Location settings', 'Local configuration saved with backup.' if changed else 'No changes to save.')
                    dlg.accept()
                except (OSError,ValueError,UnicodeError) as exc: QMessageBox.warning(dlg,'Settings not saved',str(exc))
            buttons.accepted.connect(commit);layout.addWidget(buttons);dlg.exec()
        except (OSError,ValueError,UnicodeError) as exc: QMessageBox.warning(self,'GPS and Location Settings',str(exc))

    def _new_list_hooks(self):
        """Callbacks letting Add to Favorites create a native list in the active configuration."""
        def available():
            return bool(getattr(self, 'active_scanner_configuration', None))

        def check(name):
            from scanner_configurations import prepare_new_favorites_list
            if not available():
                raise ValueError('Open a scanner configuration first.')
            prepare_new_favorites_list(self.active_scanner_configuration, name)

        def create(name, database_rows):
            from scanner_configurations import create_local_favorites_list
            from new_favorites_list import build_new_list_rows
            check(name)
            rows, encoding, newline = build_new_list_rows(database_rows)
            result = create_local_favorites_list(self.active_scanner_configuration, name,
                                                 rows, encoding, newline)
            before = set(self.workspace.drafts)
            self.workspace.create_editable_native_copy(result['path'])
            self._refresh_configuration_label()
            created = set(self.workspace.drafts) - before
            return created.pop() if len(created) == 1 else self.workspace.current_draft

        def create_native(name, rows, encoding='cp1252'):
            """A new list from rows already in the scanner's format (Paste as New Favorites List, v0.1.5)."""
            from scanner_configurations import create_local_favorites_list
            check(name)
            result = create_local_favorites_list(self.active_scanner_configuration, name, rows, encoding, '\r\n')
            before = set(self.workspace.drafts)
            self.workspace.create_editable_native_copy(result['path'])
            self._refresh_configuration_label()
            created = set(self.workspace.drafts) - before
            return created.pop() if len(created) == 1 else self.workspace.current_draft

        return {'available': available, 'check': check, 'create': create, 'create_native': create_native}

    def delete_favorites_list_from_configuration(self):
        """Remove a local Favorites List; export synchronization is a separate step."""
        from scanner_configurations import (verify_configuration,
                                            delete_local_favorites_list)
        folder = getattr(self, 'active_scanner_configuration', None)
        if not folder:
            QMessageBox.information(self, 'Open configuration first',
                'Open a saved scanner configuration before deleting a Favorites List.')
            return
        try:
            root = Path(folder).resolve()
            manifest = __import__('json').loads((root / 'configuration.json').read_text(encoding='utf-8'))
            verify_configuration(root, manifest)
            paths = sorted(k for k in manifest['files']
                           if k.startswith('BCDx36HP/favorites_lists/')
                           and k.count('/') == 2 and k.lower().endswith('.hpd'))
            if not paths:
                QMessageBox.information(self, 'Delete Favorites List',
                    'This configuration has no Favorites Lists to delete.')
                return
            from favorites_manager import FavoritesManager
            names = FavoritesManager.favorites_names(root / 'BCDx36HP' / 'favorites_lists')
            labels = []
            for relative in paths:
                filename = Path(relative).name
                display_name = names.get(filename.casefold()) or 'Unnamed Favorites List'
                labels.append(f'{display_name} ({filename})')
            selected_label, ok = QInputDialog.getItem(self, 'Delete Favorites List…',
                'Select the Favorites List to remove from this LOCAL configuration:',
                labels, 0, False)
            if not ok:
                return
            selected_index = labels.index(selected_label)
            selected = paths[selected_index]
            if QMessageBox.question(self, 'Confirm Favorites List deletion',
                    f'Delete {selected_label} from the current local configuration?\n\n'
                    'The physical scanner is NOT changed now. A later authoritative '
                    'export will remove this list from the scanner.\n\n'
                    'This action cannot be undone with the normal Undo command.',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
            delete_local_favorites_list(root, selected)
            # Drop the open working copy of the deleted list so Save Configuration and
            # Save As do not try to read a file that no longer exists. Planning
            # drafts (no native source file) are unaffected.
            deleted_path = (root / selected).resolve()
            workspace = self.workspace
            for draft_name, entries in list(workspace.drafts.items()):
                source_path = entries[0].get('source_path') if entries else None
                if source_path and Path(source_path).resolve() == deleted_path:
                    del workspace.drafts[draft_name]
                    position = workspace.draft_choice.findText(draft_name)
                    if position >= 0:
                        workspace.draft_choice.removeItem(position)
                    if workspace.current_draft == draft_name:
                        workspace.current_draft = next(iter(workspace.drafts), None)
            if str(getattr(self, '_active_working_source', '')) and \
                    Path(self._active_working_source).resolve() == deleted_path:
                self._active_working_name = workspace.current_draft
                self._active_working_source = None
            workspace.refresh_draft()
            self._refresh_configuration_label()
            QMessageBox.information(self, 'Favorites List removed',
                f'{selected_label} was removed from the LOCAL configuration.\n'
                'No scanner files have been changed.')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            QMessageBox.warning(self, 'Deletion blocked', str(exc))

    def save_draft_to_configuration(self):
        """Commit every changed native Favorites draft in the active configuration."""
        from native_favorites_export import build_native_bytes
        from scanner_configurations import save_local_favorites, verify_configuration
        folder = getattr(self, 'active_scanner_configuration', None)
        if not folder:
            QMessageBox.information(self, 'Open configuration first',
                'Open a saved configuration before saving its Favorites Lists.')
            return
        try:
            folder = Path(folder).resolve()
            verify_configuration(folder)
            changes = []
            for name, entries in self.workspace.drafts.items():
                if not entries or entries[0].get('scope') != 'metadata':
                    continue
                meta = entries[0]
                source_path = meta.get('source_path')
                if not source_path:
                    continue
                source = Path(source_path).resolve()
                if not source.is_relative_to(folder / 'BCDx36HP' / 'favorites_lists'):
                    continue
                if not str(meta.get('key', [''])[0]).startswith('native-copy-meta'):
                    raise ValueError(f'{name} is not a verified native working copy.')
                relative = source.relative_to(folder)
                payload, rows = build_native_bytes(entries)
                if payload != source.read_bytes():
                    changes.append((name, entries, relative, payload, rows))
            if not changes:
                self._clear_recovery()
                QMessageBox.information(self, 'No changes',
                    'All loaded Favorites Lists already match the local configuration.')
                return
            filenames = '\n'.join('  ' + str(item[2]) for item in changes)
            if QMessageBox.question(self, 'Save local configuration',
                    f'Update {len(changes)} LOCAL Favorites List file(s)?\n\n'
                    f'Configuration: {folder.name}\n{filenames}\n\n'
                    'Existing local files will be backed up and verified.\n'
                    'The physical scanner will NOT be changed.',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
            saved = []
            for name, entries, relative, payload, rows in changes:
                result = save_local_favorites(folder, relative, payload, rows)
                if result['changed']:
                    entries[0]['source_sha256'] = result['sha256']
                    saved.append(str(relative))
            self._refresh_configuration_label()
            self._clear_recovery()
            QMessageBox.information(self, 'Configuration saved',
                f'{len(saved)} Favorites List file(s) saved and verified locally.\n'
                'The physical scanner is unchanged.')
        except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
            QMessageBox.warning(self, 'Configuration save blocked',
                f'{exc}\n\nIf some files were saved before this error, their verified backups '
                'are retained. Reopen the configuration to review the saved state.')

    def _startup_recovery_check(self):
        """Offer recovery at launch; never silently replace a saved configuration."""
        from scanner_configurations import library_path
        folder = library_path().parent / 'scanner-configuration-recovery'
        if not folder.is_dir():
            return
        for checkpoint in sorted(folder.glob('*.json')):
            try:
                if checkpoint.stat().st_size > 25 * 1024 * 1024:
                    raise ValueError('Checkpoint exceeds 25 MB limit')
                record = json.loads(checkpoint.read_text(encoding='utf-8'))
                if record.get('format') != 'sds100-working-recovery-v1':
                    continue
                config = Path(record['configuration']).resolve()
                source = Path(record['source']).resolve()
                root = library_path().resolve()
                if config.parent != root or not source.is_relative_to(config / 'BCDx36HP' / 'favorites_lists') or source.suffix.lower() != '.hpd':
                    raise ValueError('Recovery references an invalid configuration or source')
                if not source.is_file():
                    raise ValueError('Original Favorites file no longer exists')
                if hashlib.sha256(source.read_bytes()).hexdigest() != record.get('base_sha256'):
                    QMessageBox.warning(self, 'Recovery conflict',
                        f'{config.name} / {source.name} has changed since its checkpoint.\n'
                        'The checkpoint is retained for manual review.')
                    continue
                message = QMessageBox(self)
                message.setWindowTitle('Unsaved configuration recovery')
                message.setText(f'Unsaved work was found at startup for:\n{config.name} / {source.name}')
                message.setInformativeText('Open and restore now, leave for later, or discard the checkpoint?')
                restore = message.addButton('Restore Now', QMessageBox.ButtonRole.AcceptRole)
                later = message.addButton('Later', QMessageBox.ButtonRole.RejectRole)
                discard = message.addButton('Discard Recovery', QMessageBox.ButtonRole.DestructiveRole)
                message.exec()
                clicked = message.clickedButton()
                if clicked is discard:
                    checkpoint.unlink(missing_ok=True)
                elif clicked is restore:
                    # Preserve edits from a previously restored configuration.
                    self._checkpoint_unsaved()
                    manifest = json.loads((config / 'configuration.json').read_text(encoding='utf-8'))
                    self._open_configuration(config, manifest, check_unsaved=False)
                    self._active_working_source = str(source)
                    self._active_working_name = self._draft_for(source.relative_to(config))
                    self._offer_recovery()
                    self.statusBar().showMessage('Startup recovery restored; Save Configuration to commit.')
                elif clicked is later:
                    continue
            except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
                QMessageBox.warning(self, 'Recovery checkpoint unavailable',
                    f'{checkpoint.name}: {exc}\nCheckpoint was retained.')

    def _recovery_path(self):
        folder = getattr(self, 'active_scanner_configuration', None)
        source = getattr(self, '_active_working_source', None)
        if not folder or not source:
            return None
        from scanner_configurations import library_path
        root = Path(folder).resolve()
        if root.parent != library_path().resolve():
            return None
        digest = hashlib.sha256(str(Path(source).resolve()).encode()).hexdigest()[:20]
        recovery = library_path().parent / 'scanner-configuration-recovery'
        recovery.mkdir(parents=True, exist_ok=True)
        return recovery / (root.name + '-' + digest + '.json')

    def _working_entries(self):
        name = getattr(self, '_active_working_name', None)
        if name and name in self.workspace.drafts:
            return self.workspace.drafts[name]
        return None

    def _checkpoint_unsaved(self):
        entries = self._working_entries()
        target = self._recovery_path()
        if not entries or target is None:
            return
        try:
            from native_favorites_export import build_native_bytes
            payload, _ = build_native_bytes(entries)
            source = Path(self._active_working_source)
            if hashlib.sha256(payload).hexdigest() == hashlib.sha256(source.read_bytes()).hexdigest():
                return
            record = {'format': 'sds100-working-recovery-v1',
                      'configuration': str(Path(self.active_scanner_configuration).resolve()),
                      'source': str(source.resolve()),
                      'base_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                      'saved_utc': datetime.now(timezone.utc).isoformat(),
                      'name': self._active_working_name, 'systems': entries}
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=target.parent,
                    prefix='.sds100-recovery-', suffix='.tmp', delete=False) as stream:
                temp = Path(stream.name)
                try:
                    json.dump(record, stream, indent=2)
                    stream.flush()
                    os.fsync(stream.fileno())
                except BaseException:
                    temp.unlink(missing_ok=True)
                    raise
            os.replace(temp, target)
            self.statusBar().showMessage('Unsaved configuration changes checkpointed for recovery.', 5000)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.statusBar().showMessage('Recovery checkpoint failed: ' + str(exc), 12000)

    def _clear_recovery(self):
        path = self._recovery_path()
        if path is not None:
            path.unlink(missing_ok=True)

    def _offer_recovery(self):
        path = self._recovery_path()
        if path is None or not path.is_file():
            return
        try:
            if path.stat().st_size > 25 * 1024 * 1024:
                raise ValueError('Recovery file exceeds size limit')
            record = json.loads(path.read_text(encoding='utf-8'))
            source = Path(self._active_working_source)
            if (record.get('format') != 'sds100-working-recovery-v1' or
                record.get('source') != str(source.resolve()) or
                record.get('configuration') != str(Path(self.active_scanner_configuration).resolve())):
                raise ValueError('Recovery belongs to another configuration')
            if hashlib.sha256(source.read_bytes()).hexdigest() != record['base_sha256']:
                QMessageBox.warning(self, 'Recovery conflict',
                    'The saved configuration has changed since this checkpoint. Recovery was retained but not applied.')
                return
            answer = QMessageBox.question(self, 'Unsaved configuration recovery',
                f'Unsaved changes were found for {source.name}\nCheckpoint: {record.get("saved_utc", "unknown")}\n\n'
                'Restore the unsaved working changes? No discards this recovery checkpoint.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer == QMessageBox.StandardButton.Yes:
                entries = record['systems']
                if not isinstance(entries, list) or not entries or entries[0].get('scope') != 'metadata':
                    raise ValueError('Invalid recovery entries')
                self.workspace.drafts[self._active_working_name] = entries
                self.workspace.refresh_draft()
                self.statusBar().showMessage('Unsaved working changes restored. Save Configuration to commit.')
            else:
                path.unlink(missing_ok=True)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            QMessageBox.warning(self, 'Recovery unavailable', str(exc))

    def _scanner_operation_running(self, what='this'):
        """True (after telling the user) while another scanner operation is in progress."""
        if (getattr(self, '_db_update_busy', False) or getattr(self, '_scanner_write_thread', None) is not None
                or getattr(self, '_export_preview_thread', None) is not None):
            QMessageBox.information(self, 'Scanner operation in progress',
                f'Wait for the current scanner operation to finish before starting {what}.')
            return True
        return False

    def closeEvent(self, event):
        if getattr(self, '_db_update_busy', False):
            QMessageBox.warning(self, 'Scanner operation in progress',
                'DO NOT DISCONNECT. A scanner operation is still running. Wait for it to finish before closing.')
            event.ignore()
            return
        if getattr(self, '_scanner_write_thread', None) is not None:
            QMessageBox.warning(self, 'Scanner export in progress',
                'DO NOT DISCONNECT. Wait for backup/write verification before closing.')
            event.ignore()
            return
        if getattr(self, '_export_preview_thread', None) is not None:
            QMessageBox.information(self, 'Preview still running',
                'Wait for the read-only export preview to finish before closing.')
            event.ignore()
            return
        self._checkpoint_unsaved()
        super().closeEvent(event)

    def _build_menus(self):
        """Move existing workspace toolbar actions into accessible native menus.

        Keep the underlying workspace and signal connections unchanged; its
        old toolbar buttons are hidden, not destroyed.
        """
        menus = {name: self.menuBar().addMenu(name) for name in
                 ('File', 'Edit', 'Database', 'Favorites', 'Scanner Settings', 'Tools', 'Help')}
        menus['File'].addAction('New Scanner Configuration…', self.new_scanner_configuration)
        menus['File'].addAction('Import from Scanner…', self.import_from_scanner)
        menus['File'].addAction('Open Scanner Configuration…', self.show_scanner_configurations)
        menus['File'].addAction('Save Configuration', self.save_draft_to_configuration).setShortcut('Ctrl+S')
        menus['File'].addAction('Save Configuration As…', self.save_scanner_configuration_as)
        manage = menus['File'].addMenu('Manage Configurations')
        manage.addAction('Rename Scanner Configuration…', self.rename_scanner_configuration)
        manage.addAction('Delete Scanner Configuration…', self.delete_scanner_configuration)
        manage.addAction('Validate Scanner Configuration…', self.validate_scanner_configuration)
        backup = menus['File'].addMenu('Backup and Restore')
        backup.addAction('Scanner Export Preflight (Read-only)…', self.scanner_export_preflight)
        backup.addAction('Back Up Scanner Configuration (Read-only)…', self.backup_scanner_configuration)
        backup.addAction('Restore from Backup…', self.restore_from_backup)
        menus['File'].addAction('Export to Scanner…', self.export_to_scanner)
        self._tools_menu = menus['Tools']
        settings = menus['Tools'].addAction('Settings…', self.edit_preferences)
        settings.setShortcut('Ctrl+,')
        find = menus['Tools'].addAction('Find Everywhere…', self.find_everywhere)
        find.setShortcut('Ctrl+F')
        menus['Tools'].addAction('Name Unnamed Talkgroups…', self.name_unnamed_talkgroups)
        menus['Tools'].addAction('RadioReference Account…', self.open_rr_account)
        tools_advanced = menus['Tools'].addMenu('Advanced')
        tools_advanced.addAction('Diagnostic Export Preview (Read-only)…', self.preview_scanner_export)
        menus['Scanner Settings'].addAction('Inspect Scanner Settings (Read-only)…', self.inspect_scanner_settings)
        menus['Scanner Settings'].addAction('GPS and Location Settings…', self.edit_location_settings)
        menus['Scanner Settings'].addAction('Service Types…', self.edit_service_type_settings)
        menus['Scanner Settings'].addAction('Global Settings…', self.edit_global_settings)
        menus['Scanner Settings'].addAction('Search Settings…', self.edit_search_settings)
        menus['Scanner Settings'].addAction('Weather Settings…', self.edit_weather_settings)
        menus['Scanner Settings'].addAction('Display Settings…', self.edit_display_settings)
        menus['Scanner Settings'].addAction('Display Layouts and Colours…', self.edit_display_layouts)
        menus['Scanner Settings'].addAction('Hardware Settings…', self.edit_hardware_settings)
        menus['Scanner Settings'].addSeparator()
        menus['Scanner Settings'].addAction('Update Scanner Firmware…', self.update_scanner_firmware)
        storage = menus['File'].addMenu('Storage')
        storage.addAction('Import Existing Database into Managed Storage…', self.import_managed_database)
        storage.addAction('Open Managed Data Folder…', self.show_managed_path)
        menus['File'].addSeparator()
        menus['File'].addAction('Exit', self.close)
        workspace_actions = {
            'Open Database': ('Database', 'Open Database…'),
            'Build Index': ('Database', 'Build Search Index'),
            'Search All': ('Database', 'Search All States'),
            'Import HPDB': ('Database', 'Import Local HPDB…'),
            'Database Info': ('Database', 'Database Information'),
            'Compare HPDB': ('Tools', 'Compare Local HPDB…'),
            'Source Status': ('Tools', 'Uniden Source Status'),
            'Undo change': ('Edit', 'Undo'),
            'Redo change': ('Edit', 'Redo'),
        }
        # Primary actions first; draft toolbar actions are bound below.
        favorites = menus['Favorites']
        favorites.addAction('New Favorites List…', self.new_favorites_list).setShortcut('Ctrl+N')
        favorites.addAction('Edit Favorites List…', self.edit_favorites_list).setShortcut('Ctrl+E')
        favorites.addAction('Duplicate Favorites List…', self.duplicate_favorites_list)
        favorites.addAction('Copy Favorites List to Another Configuration…', self.copy_list_to_configuration)
        favorites.addAction('Reorder Favorites Lists…', self.reorder_favorites_lists)
        favorites.addAction('Delete Favorites List…', self.delete_favorites_list_from_configuration)
        favorites.addSeparator()
        favorites.addAction('Import Favorites List File (.hpd)…', self.import_favorites_list_file)
        favorites.addAction('Save Favorites List as File (.hpd)…', self.export_native_hpd)
        favorites.addSeparator()
        favorites.addAction('Favorites List Settings…', self.edit_favorites_list_settings)
        favorites.addAction('Keys && Tags…', self.open_keys_and_tags).setShortcut('Ctrl+K')
        favorites_advanced = menus['Favorites'].addMenu('Advanced')
        favorites_advanced.addAction('Favorites List Relationships (Read-only)…', self.inspect_favorites_list_relationships)
        favorites_advanced.addAction('Inspect Native .hpd (Read-only)…', self.inspect_native_favorites)
        self._workspace_actions = {}
        for button in self.workspace.findChildren(QPushButton):
            if button.text() not in workspace_actions:
                continue  # Keep context-sensitive Add/Remove buttons visible.
            group, label = workspace_actions[button.text()]
            action = menus[group].addAction(label)
            action.setToolTip(button.toolTip())
            action.triggered.connect(lambda checked=False, target=button: target.click())
            self._workspace_actions[button.text()] = action
            button.hide()
        for key, keys in (('Undo change', ('Ctrl+Z',)), ('Redo change', ('Ctrl+Y', 'Ctrl+Shift+Z'))):
            if key in self._workspace_actions:
                self._workspace_actions[key].setShortcuts(list(keys))
        menus['Edit'].addAction('Undo All Changes…', self.workspace.undo_all_changes)
        # Hide labels belonging to the now-empty original toolbar rows.
        for label in self.workspace.findChildren(QLabel):
            if label.text() in ('DATABASE:', 'FAVORITES:', 'FAVORITES', 'BROWSE', 'MASTER HPDB'):
                label.hide()
        self.build_theme_menu(menus['Tools'].addMenu('Theme'))
        preferences = menus['Tools'].addMenu('Preferences')
        preferences.addAction('Database Contents columns…', lambda: self.workspace.configure_columns(self.workspace.detail_table, 'database'))
        preferences.addAction('Favorites List columns…', lambda: self.workspace.configure_columns(self.workspace.draft_tree, 'favorites'))
        menus['Database'].addSeparator()
        for label, callback in (
            (DB_UPDATE_LABEL, self.integrated_update),
            ('Update Scanner\'s Master Database…', self.update_scanner_master_database),
        ):
            menus['Database'].addAction(label, callback)
        database_advanced = menus['Database'].addMenu('Advanced')
        for label, callback in (
            ('Validate Master HPDB…', self.validate_master),
            ('Validate Master HPDB .gz…', self.validate_master_archive),
            ('Export One State File…', self.reconstruct_one_state),
            ('Rebuild Full Database to a Folder…', self.reconstruct_full_states),
        ):
            database_advanced.addAction(label, callback)
        help_menu = menus['Help']
        guide = help_menu.addAction('User Guide', lambda: self.show_document('User Guide', 'USER_GUIDE.md'))
        guide.setShortcut('F1')
        help_menu.addAction('Recovery and Troubleshooting', lambda: self.show_document(
            'User Guide — Recovery and Troubleshooting', 'USER_GUIDE.md', 'If something goes wrong'))
        help_menu.addAction("What's New (Change Log)", lambda: self.show_document("What's New", 'CHANGELOG.md'))
        help_menu.addAction('Check for Updates…', self.check_for_updates)
        help_menu.addSeparator()
        help_menu.addAction('Open Scanner Backups Folder', self.open_backups_folder)
        help_menu.addAction('Copy Diagnostic Information', self.copy_diagnostics)
        help_menu.addAction('Open Log Folder', self.open_log_folder)
        help_menu.addSeparator()
        help_menu.addAction('License', lambda: self.show_document('License — GNU GPL v3', 'LICENSE'))
        help_menu.addAction('About…', self.show_about)
        self.statusBar().showMessage('Offline editing • Every scanner write is checked, backed up and reversible')

    # ---- Drag and drop -----------------------------------------------------------------------
    @staticmethod
    def _dropped_paths(event):
        mime = event.mimeData()
        return [url.toLocalFile() for url in mime.urls() if url.isLocalFile()] if mime.hasUrls() else []

    def dragEnterEvent(self, event):
        import drop_targets
        action = drop_targets.classify(self._dropped_paths(event))[0]
        if action:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """An SD card folder starts the normal verified import; a .hpd file opens the read-only inspector."""
        import drop_targets
        action, path, message = drop_targets.classify(self._dropped_paths(event))
        if not action:
            QMessageBox.information(self, 'Drag and drop', message)
            event.ignore()
            return
        event.acceptProposedAction()
        # Run after the drop finishes so a dialog never opens inside the drag-and-drop handler.
        if action == 'scanner':
            QTimer.singleShot(0, lambda: self.import_from_scanner(folder=path))
        else:
            QTimer.singleShot(0, lambda: self.inspect_native_favorites(path=path))

    # ---- Help ---------------------------------------------------------------------------------
    def show_document(self, title, name, jump=None):
        """Show a bundled document (Markdown rendered; plain text for LICENSE), with a heading list."""
        from PyQt6.QtWidgets import QTextBrowser, QListWidget, QHBoxLayout, QDialogButtonBox, QLineEdit
        import help_system
        text = help_system.read_doc(name)
        if text is None:
            QMessageBox.warning(self, title, f'{name} was not found next to the application files.')
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(980, 720)
        layout = QVBoxLayout(dialog)
        search = QLineEdit(dialog)
        search.setPlaceholderText('Find in this document (Enter for next match)…')
        layout.addWidget(search)
        row = QHBoxLayout()
        layout.addLayout(row, 1)
        browser = QTextBrowser(dialog)
        browser.setOpenExternalLinks(True)
        if name.endswith('.md'):
            browser.setMarkdown(text)
            index = QListWidget(dialog)
            index.setMaximumWidth(260)
            for level, heading in help_system.headings(text):
                index.addItem(('    ' if level == 3 else '') + heading)
            row.addWidget(index)

            def go(item):
                browser.moveCursor(QTextCursor.MoveOperation.Start)
                browser.find(item.text().strip())
            index.itemClicked.connect(go)
        else:
            browser.setPlainText(text)
        row.addWidget(browser, 1)

        def find_next():
            if not search.text():
                return
            if not browser.find(search.text()):
                browser.moveCursor(QTextCursor.MoveOperation.Start)
                browser.find(search.text())
        search.returnPressed.connect(find_next)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if jump:
            browser.find(jump)
        dialog.show()
        self._help_dialog = dialog          # keep a reference while it is open

    def show_about(self):
        import help_system
        box = QMessageBox(self)
        box.setWindowTitle('About ' + help_system.APP_NAME)
        box.setIconPixmap(self.windowIcon().pixmap(64, 64))
        box.setText(help_system.about_text())
        box.setTextFormat(Qt.TextFormat.PlainText)
        licence = box.addButton('View License', QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if box.clickedButton() is licence:
            self.show_document('License — GNU GPL v3', 'LICENSE')

    def open_backups_folder(self):
        folder = Path.home() / '.local/share/sds100-database-favorites-manager/scanner-backups'
        if not folder.is_dir():
            QMessageBox.information(self, 'Scanner backups',
                f'No backups exist yet. They are created automatically before the first scanner write, in:\n{folder}')
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            QMessageBox.warning(self, 'Scanner backups', f'Could not open the folder:\n{folder}')

    def copy_diagnostics(self):
        import help_system
        active = getattr(self, 'active_scanner_configuration', None)
        report = help_system.diagnostic_report(Path(active).name if active else None)
        QApplication.clipboard().setText(report)
        QMessageBox.information(self, 'Diagnostic information copied',
            'Copied to the clipboard (no scanner data or file contents are included):\n\n' + report)

    # ---- Update Scanner's Master Database ---------------------------------------------------
    def open_rr_account(self):
        """Tools → RadioReference Account… (v0.1.0)."""
        from rr_account_dialog import RRAccountDialog
        RRAccountDialog(self).exec()
        changed = getattr(self.workspace, 'rr_account_changed', None)
        if changed:
            changed()

    def _run_background(self, title, text, work, done):
        """Run work() on a plain Python thread; poll from the GUI thread (no Qt thread objects)."""
        import threading
        box = {}

        def target():
            try:
                box['result'] = work()
            except Exception as exc:
                box['error'] = f'{type(exc).__name__}: {exc}'
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setMinimumWidth(480)
        dialog.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        layout = QVBoxLayout(dialog)
        label = QLabel(text, dialog)
        label.setWordWrap(True)
        layout.addWidget(label)
        bar = QProgressBar(dialog)
        bar.setRange(0, 0)
        bar.setTextVisible(False)
        layout.addWidget(bar)
        dialog.show()
        thread = threading.Thread(target=target, daemon=False)
        timer = QTimer(self)
        started = [0]

        def poll():
            started[0] += 1
            label.setText(text + f'\n\nElapsed: {started[0] // 4} seconds.')
            if thread.is_alive():
                return
            timer.stop()
            dialog.hide()
            dialog.deleteLater()
            timer.deleteLater()
            QTimer.singleShot(200, lambda: done(box.get('result'), box.get('error')))
        timer.timeout.connect(poll)
        thread.start()
        timer.start(250)

    def update_scanner_firmware(self):
        """Find or add SDS100 firmware and place it in the card's firmware folder (added in v0.0.9a)."""
        if getattr(self, '_db_update_busy', False):
            QMessageBox.information(self, 'Update in progress', 'Wait for the current scanner operation to finish.')
            return
        from firmware_dialog import FirmwareDialog
        dialog = FirmwareDialog(self)
        dialog.choose_scanner()
        dialog.exec()

    def update_scanner_master_database(self):
        """Replace the SDS100's whole HPDB from a rebuilt local database version."""
        if getattr(self, '_db_update_busy', False):
            QMessageBox.information(self, 'Update in progress', 'Wait for the current scanner operation to finish.')
            return
        from managed_storage import valid_package
        initialize()
        versions = ROOT / 'database' / 'versions'
        folders = sorted((p for p in versions.iterdir() if p.is_dir() and not p.is_symlink() and valid_package(p)),
                         key=lambda p: p.name, reverse=True) if versions.is_dir() else []
        if not folders:
            QMessageBox.information(self, "Update Scanner's Master Database",
                'No rebuilt database is available yet.\n\nUse Database → Update Database… first. It downloads the '
                'Uniden master database and rebuilds the 70 files offline; this command then writes that '
                'database to the scanner.')
            return
        active = active_database()
        labels = [p.name + ('   (current)' if active and p.resolve() == active else '') for p in folders]
        choice, ok = QInputDialog.getItem(self, "Update Scanner's Master Database",
            'Choose the rebuilt database to put on the scanner:', labels, 0, False)
        if not ok:
            return
        package = folders[labels.index(choice)]
        scanner = self.pick_scanner_folder('Select SDS100 Mass Storage root — READ ONLY check first')
        if not scanner:
            return
        from scanner_database_update import database_update_eligibility
        self._db_update_busy = True
        self._run_background("Update Scanner's Master Database — checking (READ ONLY)",
            'Comparing the new database with the scanner. Nothing is written.',
            lambda: database_update_eligibility(package, scanner),
            lambda result, error: self._master_update_checked(package, scanner, result, error))

    def _master_update_checked(self, package, scanner, result, error):
        self._db_update_busy = False
        if error or not result:
            QMessageBox.warning(self, "Update Scanner's Master Database", error or 'The check produced no result.')
            return
        eligible, reason = result
        if not eligible:
            QMessageBox.warning(self, "Update Scanner's Master Database — blocked",
                reason + '\n\nNo scanner files have been changed.')
            return
        answer = QMessageBox.warning(self, "Update Scanner's Master Database — confirm",
            reason + '\n\nThis is a REAL write to the SDS100 SD card. It replaces the whole system database '
            '(the HPDB folder) with the new version. Your favorites lists, settings and everything else are not touched.\n\n'
            'Do not unplug the scanner or exit the application while writing. When it finishes, eject the SD card '
            'from your computer before turning the scanner on, then check the Favorites and database on the scanner.\n\n'
            'Continue?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        from scanner_database_update import execute_database_update
        self._db_update_busy = True
        self.statusBar().showMessage('Writing the master database to the scanner. DO NOT DISCONNECT.')
        self._run_background("Update Scanner's Master Database — BACKING UP / WRITING",
            'Creating a verified backup, then writing and verifying the database files. DO NOT DISCONNECT THE SCANNER.',
            lambda: execute_database_update(package, scanner), self._master_update_done)

    def _master_update_done(self, result, error):
        self._db_update_busy = False
        self.statusBar().clearMessage()
        if error or not result:
            QMessageBox.critical(self, "Update Scanner's Master Database — FAILED",
                (error or 'Unknown result. Check the scanner and the verified backup.') +
                '\n\nDo not assume the scanner database is intact. Recovery files are in the backup folder named above.')
            return
        QMessageBox.information(self, "Update Scanner's Master Database — complete",
            f"{len(result['files'])} database file(s) written and verified (database dated {result['new_date']}).\n\n"
            f"Verified backup of the previous card contents:\n{result['backup']}\n\n"
            'Eject the SD card from your computer and wait for it to finish before powering on the scanner.')

    def _choose_database_archive(self):
        """(archive name, local file or None), or (None, None) if cancelled."""
        path, _ = QFileDialog.getOpenFileName(
            self, 'Choose a Uniden master database archive (MasterHpdb_MM_DD_YYYY.gz)', str(Path.home()),
            'Master database archives (MasterHpdb_*.gz);;All files (*)')
        if not path:
            return None, None
        if not re.fullmatch(r'MasterHpdb_\d\d_\d\d_\d{4}\.gz', Path(path).name):
            QMessageBox.warning(self, 'Not a master database archive',
                                'Choose a file named like MasterHpdb_10_25_2026.gz.')
            return None, None
        return Path(path).name, Path(path)

    def integrated_update(self):
        """Rebuild the database from an archive (downloaded in the personal build, or a file the
        user chooses); never touches the scanner or Sentinel."""
        name, local_path = self._choose_database_archive()
        if not name:
            return
        initialize()
        parent = str(ROOT / 'database' / 'downloads')
        export_parent = ROOT / 'database' / 'versions'
        export_name = 'HPDB-Experimental-' + name.removeprefix('MasterHpdb_').removesuffix('.gz')
        download_path = Path(parent) / name
        export_path = export_parent / export_name
        if (not local_path and (download_path.exists() or download_path.is_symlink())) \
                or export_path.exists() or export_path.is_symlink():
            QMessageBox.warning(self, 'Existing files protected',
                'This database version already exists in managed storage. Existing files will not be overwritten.')
            return
        action = f'Use {local_path}' if local_path else f'Download {name}'
        if QMessageBox.question(self, 'Confirm database rebuild',
             f'{action}, validate it, then reconstruct 70 database files in:\n{export_path}\n\n'
             'No Sentinel/scanner installation. The operation may take several minutes.') != QMessageBox.StandardButton.Yes:
            return
        self._update_thread = QThread(self)
        self._update_worker = UpdateWorker(name, parent, export_path, local_path)
        self._update_worker.moveToThread(self._update_thread)
        self._update_thread.started.connect(self._update_worker.run)
        self._progress = QProgressDialog('Preparing database update…', '', 0, 0, self)
        self._progress.setWindowTitle('Integrated database update — offline')
        self._progress.setCancelButton(None)
        self._progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._progress.setMinimumDuration(0)
        self._update_worker.status.connect(self._progress.setLabelText)
        self._update_worker.finished.connect(self._update_success)
        self._update_worker.failed.connect(self._update_failure)
        self._update_worker.finished.connect(self._update_thread.quit)
        self._update_worker.failed.connect(self._update_thread.quit)
        self._update_thread.finished.connect(self._update_worker.deleteLater)
        self._update_thread.finished.connect(self._update_thread.deleteLater)
        self._update_thread.start()
        self._progress.show()

    def _update_success(self, result):
        self._progress.close()
        report = result['export']
        try:
            self._activate_completed_export(Path(report['path']))
        except Exception as exc:
            QMessageBox.warning(self, 'Export completed, activation not performed',
                f'Export is preserved, but the active database was not changed: {type(exc).__name__}: {exc}')
        QMessageBox.information(self, 'Offline database update complete',
            f"Archive: {result['download']['path']}\n"
            f"Archive SHA-256: {result['archive_sha256']}\n"
            f"Export: {report['path']}\n"
            f"State files: {report['states']}\nRecords: {report['records']:,}\n"
            f"Master SHA-256: {report['master_sha256']}\n"
            f"hpdb.cfg SHA-256: {report['config_sha256']}\n\n"
            'The rebuilt database is stored locally. Nothing has been written to the scanner; use\nDatabase → Update Scanner\'s Master Database… to put it on the card.')

    def _load_managed_database(self):
        database = active_database()
        if database is not None:
            self.workspace.open_database_path(database)
            self.statusBar().showMessage(f'Managed database loaded: {database.name} • 68 states • Offline only')
        else:
            self.statusBar().showMessage('No managed database yet • Import a verified package or run Integrated Database Update')

    def show_managed_path(self):
        try:
            folder = Path(ROOT).expanduser().resolve()
            folder.mkdir(parents=True, exist_ok=True)
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
                raise RuntimeError('KDE did not accept the folder-open request.')
        except Exception as exc:
            QMessageBox.warning(self, 'Open Managed Data Folder',
                                f'Could not open the managed data folder:\n{ROOT}\n\n{exc}')

    def import_managed_database(self):
        folder = QFileDialog.getExistingDirectory(self, 'Choose existing complete 70-file database', str(Path.home()))
        if not folder: return
        if QMessageBox.question(self, 'Import offline database',
            'Copy this database into private application storage and activate it?\n'
            'Existing managed versions and Favorites Lists will be preserved.') != QMessageBox.StandardButton.Yes:
            return
        try:
            name = 'import-' + __import__('datetime').datetime.now().strftime('%Y%m%d-%H%M%S')
            activate_export(folder, name)
            self._load_managed_database()
            QMessageBox.information(self, 'Database imported', 'Managed database imported and loaded successfully.')
        except Exception as exc:
            QMessageBox.critical(self, 'Import failed', f'{type(exc).__name__}: {exc}')

    def _activate_completed_export(self, folder):
        # Reconstruction has already created the version inside the managed versions directory.
        # Activation uses a temporary symlink and atomic replace, preserving previous versions.
        import os
        folder = folder.resolve(strict=True)
        versions = (ROOT / 'database' / 'versions').resolve()
        if folder.parent != versions:
            raise ValueError('Export is outside managed versions directory')
        from managed_storage import valid_package
        if not valid_package(folder): raise ValueError('Incomplete database export')
        current = ROOT / 'database' / 'current'
        if current.exists() and not current.is_symlink():
            raise RuntimeError('Current database is not a managed symlink')
        temp = ROOT / 'database' / ('.current-'+folder.name)
        try:
            temp.symlink_to(Path('versions') / folder.name, target_is_directory=True)
            os.replace(temp, current)
        finally:
            if temp.is_symlink(): temp.unlink()
        self._load_managed_database()

    def _update_failure(self, message):
        self._progress.close()
        QMessageBox.critical(self, 'Integrated database update failed', message)


    def reconstruct_full_states(self):
        """Rebuild the 68 state files, master and hpdb.cfg into a new local folder."""
        from pathlib import Path
        from hpdb_bulk_reconstruction import reconstruct_all_states
        master, _ = QFileDialog.getOpenFileName(
            self, 'Select local Master HPDB', str(Path.home() / 'SDS100-Research'),
            'Master databases (*.hp1 *.gz MasterHpdb_*);;All files (*)')
        if not master:
            return
        parent = QFileDialog.getExistingDirectory(self, 'Choose parent directory for NEW export folder', str(Path.home()))
        if not parent:
            return
        from PyQt6.QtWidgets import QInputDialog
        folder, ok = QInputDialog.getText(self, 'New export folder name',
                                          'New folder (must not already exist):', text='HPDB-Export')
        if not ok or not folder:
            return
        if folder in ('.', '..') or '/' in folder or '\\' in folder:
            QMessageBox.warning(self, 'Invalid name', 'Enter a simple folder name.')
            return
        destination = Path(parent) / folder
        if destination.exists():
            QMessageBox.warning(self, 'Export refused', 'Folder already exists.')
            return
        if QMessageBox.question(self, 'Rebuild database to a folder',
                'Generate 68 state files, master and hpdb.cfg in a NEW local folder?\n'
                'The scanner is not touched. This operation may take some time.') != QMessageBox.StandardButton.Yes:
            return
        try:
            result = reconstruct_all_states(master, destination)
        except (OSError, UnicodeError, ValueError, EOFError) as exc:
            QMessageBox.critical(self, 'Bulk reconstruction failed', str(exc))
            return
        QMessageBox.information(self, 'Database rebuild complete',
            f"Created: {result['path']}\nState files: {result['states']}\n"
            f"Records: {result['records']:,}\n"
            f"hpdb.cfg SHA-256: {result['config_sha256']}\n\n"
            'The scanner was not touched. To put a rebuilt database on the card use\nDatabase → Update Scanner\'s Master Database… (do not copy files by hand).')

    def reconstruct_one_state(self):
        """Explicit offline export, never modifies source database or scanner."""
        from PyQt6.QtWidgets import QInputDialog
        from hpdb_state_reconstruction import reconstruct_state
        filename, _ = QFileDialog.getOpenFileName(
            self, 'Select local Master HPDB (uncompressed or gzip)',
            str(__import__('pathlib').Path.home() / 'SDS100-Research'),
            'Master databases (*.hp1 *.gz MasterHpdb_*);;All files (*)')
        if not filename:
            return
        state_id, ok = QInputDialog.getInt(self, 'State identifier',
                                           'Enter numeric StateId:', 45, 1, 999999)
        if not ok:
            return
        destination, _ = QFileDialog.getSaveFileName(
            self, 'Export state file (new file only)',
            str(__import__('pathlib').Path.home() / f's_{state_id:06d}_rebuilt.hpd'),
            'HPD files (*.hpd)')
        if not destination:
            return
        from pathlib import Path
        if Path(destination).exists():
            QMessageBox.warning(self, 'Export refused', 'File already exists. Choose a new filename.')
            return
        try:
            result = reconstruct_state(filename, state_id, destination)
        except (OSError, UnicodeError, ValueError, EOFError) as exc:
            QMessageBox.critical(self, 'State reconstruction failed', str(exc))
            return
        QMessageBox.information(self, 'State file export complete',
            f"Created: {result['path']}\nRecords: {result['records']:,}\n"
            f"Bytes: {result['bytes']:,}\n\n"
            'Single-state export for inspection. No scanner access.')

    def validate_master(self):
        filename, _ = QFileDialog.getOpenFileName(self, 'Select decompressed Master HPDB',
                                                  str(__import__('pathlib').Path.home() / 'SDS100-Research'))
        if not filename:
            return
        try:
            report = validate(filename)
        except (OSError, UnicodeError, ValueError, EOFError) as exc:
            QMessageBox.critical(self, 'Unable to read master database', str(exc))
            return
        lines = [f'File: {filename}', f'Valid: {report["valid"]}',
                 f'Lines: {report["lines"]:,}', f'Bytes: {report["bytes"]:,}',
                 f'Header: {report["header"]}', '', 'Record types:']
        lines += [f'{tag}: {count:,}' for tag, count in report['counts'].items()]
        lines += ['', 'Errors:'] + (report['errors'] or ['None'])
        box = QMessageBox(self)
        box.setWindowTitle('Master HPDB validation')
        box.setIcon(QMessageBox.Icon.Information if report['valid'] else QMessageBox.Icon.Warning)
        box.setText('Master database passed basic structural checks.' if report['valid']
                    else 'Master database has structural errors.')
        box.setDetailedText('\n'.join(lines))
        box.exec()

    def validate_master_archive(self):
        """Read-only, bounded gzip inspection; never extracts or installs files."""
        filename, _ = QFileDialog.getOpenFileName(
            self, 'Select downloaded Uniden Master HPDB gzip archive',
            str(__import__('pathlib').Path.home() / 'SDS100-Research'),
            'Gzip archives (*.gz)')
        if not filename:
            return
        from master_hpdb_validator import validate
        try:
            report = validate(filename)
        except (OSError, UnicodeError, ValueError, EOFError) as exc:
            QMessageBox.critical(self, 'Master archive validation failed', str(exc))
            return
        lines = [f'Archive: {filename}', f'Valid: {report["valid"]}',
                 f'Records: {report["lines"]:,}',
                 f'Uncompressed bytes: {report["bytes"]:,}',
                 f'Header: {report["header"]}', '', 'Record types:']
        lines += [f'{tag}: {count:,}' for tag, count in report['counts'].items()]
        lines += ['', 'Errors:'] + (report['errors'] or ['None'])
        box = QMessageBox(self)
        box.setWindowTitle('Master HPDB gzip archive validation')
        box.setIcon(QMessageBox.Icon.Information if report['valid'] else QMessageBox.Icon.Warning)
        box.setText('Gzip archive passed basic master structure checks.' if report['valid']
                    else 'Gzip archive has master structure errors.')
        box.setInformativeText('Read-only inspection. No extraction or database installation.')
        box.setDetailedText('\n'.join(lines))
        box.exec()

def configure_logging():
    """Rotating log file in the state folder; level from Preferences. Never stops the program starting."""
    import logging
    from logging.handlers import RotatingFileHandler
    try:
        import preferences
        folder = preferences.state_dir()
        folder.mkdir(parents=True, exist_ok=True)
        level = getattr(logging, preferences.load().get('log_level', 'WARNING'), logging.WARNING)
        handler = RotatingFileHandler(folder / 'application.log', maxBytes=1_000_000, backupCount=3, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
        logging.basicConfig(level=level, handlers=[handler])
        previous = sys.excepthook

        def log_exception(kind, value, trace):
            logging.getLogger('uncaught').error('Unhandled exception', exc_info=(kind, value, trace))
            previous(kind, value, trace)
        sys.excepthook = log_exception
    except Exception:
        pass


def monitor_request_from_args(argv):
    """--open-entry <JSON> from SDS100 Monitor's Edit in Manager, or None."""
    import monitor_link
    if '--open-entry' in argv:
        at = argv.index('--open-entry')
        if at + 1 < len(argv):
            return monitor_link.clean_request(argv[at + 1])
    return None


if __name__ == "__main__":
    configure_logging()
    app = QApplication(sys.argv)
    request = monitor_request_from_args(sys.argv)
    if request is not None:
        from monitor_link_ui import send_to_running
        if send_to_running(request):
            os._exit(0)                     # the Manager already open has it
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / "assets/sds100-manager.svg")))
    window = ManagerWindow()
    window.start_monitor_link()
    window.start_update_checks()
    window.show()
    if request is not None:
        QTimer.singleShot(800, lambda: window.open_monitor_request(request))
    sys.exit(app.exec())
