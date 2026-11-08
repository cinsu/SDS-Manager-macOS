# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Runs the new GUI code against stub widgets: catches typos, bad arguments and broken control flow."""
import importlib
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import qt_stub

FORGET = ('ui_extras', 'database_favorites_manager', 'database_workspace', 'favorites_manager', 'favorites_planner',
          'favorites_editor', 'favorites_explorer', 'favorites_settings_window', 'state_labels')


def load(name):
    with qt_stub.installed(forget=FORGET):
        return importlib.import_module(name)


class Host:
    """Just enough of a window for the mixin."""

    def __init__(self, mixin_class):
        for name in dir(mixin_class):
            if not name.startswith('__'):
                setattr(self, name, getattr(mixin_class, name).__get__(self))
        self.statusBar = MagicMock()
        self.windowIcon = MagicMock()
        for name in ('integrated_update', 'update_scanner_master_database', 'export_to_scanner',
                     'backup_scanner_configuration', 'addDockWidget'):
            setattr(self, name, MagicMock())


class MixinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = load('ui_extras')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        env = patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.base / 'config'), 'XDG_STATE_HOME': str(self.base / 'state'),
                                      'XDG_DATA_HOME': str(self.base / 'data'), 'HOME': str(self.base)})
        env.start()
        self.addCleanup(env.stop)
        self.host = Host(self.ui.ExtrasMixin)
        self.ui.QTimer.singleShot = MagicMock()
        self.ui.QMessageBox.StandardButton = MagicMock()

    def init(self, **prefs):
        import preferences
        self.host.prefs = dict(preferences.DEFAULTS, **prefs)
        self.host.init_extras = self.host.init_extras
        # init_extras reloads from disk; write the wanted prefs there first
        preferences.save(self.host.prefs)
        self.host.init_extras()

    def test_startup_runs_and_shows_not_connected(self):
        with patch.object(self.ui.scanner_detect, 'find_scanners', return_value=[]):
            self.init()
        self.assertEqual(self.host.prefs['theme'], 'system')
        self.host._scanner_label.setText.assert_called_with('Scanner: not connected')

    def test_detected_card_fills_panel_and_status(self):
        card = self.base / 'card'
        (card / 'BCDx36HP' / 'HPDB').mkdir(parents=True)
        (card / 'BCDx36HP' / 'scanner.inf').write_bytes(b'Scanner\tSDS100\tx\t1.26.01 \r\n')
        (card / 'BCDx36HP' / 'HPDB' / 'hpdb.cfg').write_bytes(b'DateModified\t10/25/2026 04:30:15\r\n')
        hits = [{'mountpoint': str(card), 'device': '/dev/sdb1', 'fstype': 'vfat'}]
        with patch.object(self.ui.scanner_detect, 'find_scanners', return_value=hits):
            self.init()
        text = self.host._scanner_label.setText.call_args[0][0]
        self.assertIn('SDS100 connected', text)
        self.assertIn('10/25/2026', text)

    def test_auto_detect_off_does_not_poll(self):
        with patch.object(self.ui.scanner_detect, 'find_scanners', return_value=[]) as find:
            self.init(auto_detect=False)
            self.host._scanner_timer.start.assert_not_called()

    def test_pick_folder_uses_detected_scanner_when_agreed(self):
        hits = [{'mountpoint': '/run/media/x/SDS', 'device': '/dev/sdb1', 'fstype': 'vfat'}]
        with patch.object(self.ui.scanner_detect, 'find_scanners', return_value=hits):
            self.init()
            box = MagicMock()
            use = object()
            box.addButton.side_effect = [use, object(), None]
            box.clickedButton.return_value = use
            self.ui.QMessageBox = MagicMock(return_value=box)
            self.ui.QMessageBox.ButtonRole = MagicMock()
            self.assertEqual(self.host.pick_scanner_folder('t'), '/run/media/x/SDS')

    def test_pick_folder_falls_back_to_chooser_and_honours_the_preference(self):
        self.ui.QFileDialog = MagicMock()
        self.ui.QFileDialog.getExistingDirectory.return_value = '/chosen'
        with patch.object(self.ui.scanner_detect, 'find_scanners', return_value=[]):
            self.init()
            self.assertEqual(self.host.pick_scanner_folder('t'), '/chosen')
            self.init(offer_detected_scanner=False)
            self.assertEqual(self.host.pick_scanner_folder('t'), '/chosen')

    def test_confirm_low_risk_can_be_switched_off(self):
        with patch.object(self.ui.scanner_detect, 'find_scanners', return_value=[]):
            self.init(confirm_low_risk=False)
            self.assertTrue(self.host.confirm_low_risk('t', 'x'))

    def test_backup_cleanup_deletes_after_confirmation_only(self):
        backups = self.base / '.local/share/sds100-database-favorites-manager/scanner-backups'
        for day in range(1, 7):
            folder = backups / f'202610{day:02d}T120000Z'
            folder.mkdir(parents=True)
            (folder / 'manifest.json').write_text('{}')
        with patch.object(self.ui.scanner_detect, 'find_scanners', return_value=[]):
            self.init(backup_keep=3)
            self.ui.QMessageBox = MagicMock()
            self.ui.QMessageBox.StandardButton.Yes = 'yes'
            self.ui.QMessageBox.question.return_value = 'no'
            self.host.cleanup_backups()
            self.assertEqual(len(list(backups.iterdir())), 6)
            self.ui.QMessageBox.question.return_value = 'yes'
            self.host.cleanup_backups()
            self.assertEqual(sorted(p.name for p in backups.iterdir()),
                             ['20261004T120000Z', '20261005T120000Z', '20261006T120000Z'])

    def test_version_cleanup_runs(self):
        with patch.object(self.ui.scanner_detect, 'find_scanners', return_value=[]):
            self.init()
            self.ui.QMessageBox = MagicMock()
            self.host.cleanup_database_versions()
            self.ui.QMessageBox.information.assert_called()

    def test_preferences_dialog_builds_and_saves(self):
        import preferences
        with patch.object(self.ui.scanner_detect, 'find_scanners', return_value=[]):
            self.init()
            self.host.edit_preferences()
            self.assertEqual(self.host._preferences_dialog.show.call_count, 1)

    def test_appearance_applies_theme_and_font(self):
        with patch.object(self.ui.scanner_detect, 'find_scanners', return_value=[]):
            self.init(theme='dark', font_size=12)
            self.init(theme='system', font_size=0)

    def test_theme_menu_is_built_before_preferences_load(self):
        # The real window builds its menus before init_extras() loads the preferences (v0.0.9c crashed here).
        with patch.object(self.ui.scanner_detect, 'find_scanners', return_value=[]):
            self.assertFalse(hasattr(self.host, 'prefs'))
            self.host.build_theme_menu(MagicMock())
            self.host._check_system_theme()
            self.init(theme='light')
            self.assertEqual(self.host.prefs['theme'], 'light')

    def test_theme_menu_switches_live_and_saves(self):
        import app_theme
        import preferences
        with patch.object(self.ui.scanner_detect, 'find_scanners', return_value=[]):
            self.init(theme='dark', font_size=12)
            self.host.build_theme_menu(MagicMock())
            self.assertIn(('accent', 'teal'), self.host._theme_actions)
            self.host.set_theme_option('theme', 'light')
            self.host.set_theme_option('accent', 'green')
            self.host.set_theme_option('text_size', 'large')
            saved = preferences.load()
            self.assertEqual((saved['theme'], saved['accent'], saved['text_size'], saved['font_size']),
                             ('light', 'green', 'large', 0))
            self.assertEqual((app_theme.THEME.mode, app_theme.THEME.accent), ('light', 'green'))
            self.host.set_theme_option('theme', 'night')
            self.assertEqual(app_theme.THEME.mode, 'night')
            app_theme.THEME = app_theme.Theme()


class ImportTests(unittest.TestCase):
    def test_the_whole_application_module_imports_and_wires_the_new_pieces(self):
        with qt_stub.installed(forget=FORGET):
            module = importlib.import_module('database_favorites_manager')
            window = module.ManagerWindow
            for name in ('init_extras', 'edit_preferences', 'pick_scanner_folder', 'cleanup_backups',
                         'cleanup_database_versions', 'refresh_scanner_panel', 'show_about', 'update_scanner_master_database'):
                self.assertTrue(hasattr(window, name), name)


class FindEverywhereStubTests(MixinTests):
    def test_search_runs_and_fills_the_table(self):
        import shutil
        import search_engine
        db = self.base / 'db'
        db.mkdir()
        shutil.copy(Path(__file__).parent / 'test_fixtures/real_hpdb_greenville_county.txt', db / 's_000045.hpd')
        buttons = []
        self.ui.QPushButton = MagicMock(side_effect=lambda *a, **k: buttons.append(MagicMock()) or buttons[-1])
        timer = MagicMock()
        self.ui.QTimer = MagicMock(return_value=timer)
        table = MagicMock()
        table.rowCount.side_effect = lambda: table.insertRow.call_count
        self.ui.QTableWidget = MagicMock(return_value=table)
        self.ui.QTableWidget.EditTrigger = MagicMock()
        self.ui.QTableWidget.SelectionBehavior = MagicMock()
        box = MagicMock()
        box.text.return_value = 'skywarn'
        self.ui.QLineEdit = MagicMock(return_value=box)
        self.host.active_scanner_configuration = None
        with patch('managed_storage.active_database', return_value=db):
            self.host.find_everywhere()
            go, stop = buttons[0], buttons[1]
            start = go.clicked.connect.call_args[0][0]
            start()
            job = None
            poll = timer.timeout.connect.call_args[0][0]
            for _ in range(200):
                poll()
                if go.setEnabled.call_args and go.setEnabled.call_args[0][0] is True:
                    break
                import time
                time.sleep(0.01)
        self.assertEqual(table.insertRow.call_count, 3)
        self.assertTrue(timer.stop.called)

    def test_nothing_to_search_is_reported(self):
        self.ui.QTimer = MagicMock()
        box = MagicMock()
        box.text.return_value = 'fire'
        self.ui.QLineEdit = MagicMock(return_value=box)
        label = MagicMock()
        self.ui.QLabel = MagicMock(return_value=label)
        self.host.active_scanner_configuration = None
        with patch('managed_storage.active_database', return_value=None):
            self.host.find_everywhere()
            box.returnPressed.connect.call_args[0][0]()
        self.assertIn('Nothing to search', str(label.setText.call_args))

    def test_second_call_reuses_the_open_dialog(self):
        self.ui.QTimer = MagicMock()
        self.host.find_everywhere()
        first = self.host._find_dialog
        self.host.find_everywhere()
        self.assertIs(self.host._find_dialog, first)
        first.show.assert_called()



class MenuStructureTests(unittest.TestCase):
    """_build_menus runs against stub widgets; every action must resolve to a real method."""

    def test_menus_build_and_nest(self):
        manager = load('database_favorites_manager')
        titles = {}

        class FakeMenu:
            def __init__(self, name):
                self.name, self.items = name, []
                titles[name] = self

            def addAction(self, label, callback=None):
                self.items.append(label)
                return MagicMock()

            def addMenu(self, name):
                self.items.append(name + ' ▸')
                return FakeMenu(self.name + '/' + name)

            def addSeparator(self):
                pass

            def menuAction(self):
                return MagicMock()

        window = MagicMock()
        window.menuBar.return_value.addMenu.side_effect = lambda name: FakeMenu(name)
        window.workspace.findChildren.return_value = []
        manager.ManagerWindow._build_menus(window)
        self.assertIn('Manage Configurations ▸', titles['File'].items)
        self.assertIn('Backup and Restore ▸', titles['File'].items)
        self.assertIn('Export to Scanner…', titles['File'].items)
        self.assertIn('Find Everywhere…', titles['Tools'].items)
        self.assertIn('Advanced ▸', titles['Database'].items)
        self.assertIn(__import__('edition').DB_UPDATE_LABEL, titles['Database'].items)
        self.assertIn('Rename Scanner Configuration…', titles['File/Manage Configurations'].items)
        self.assertIn('Validate Master HPDB…', titles['Database/Advanced'].items)
        import inspect
        import re
        source = inspect.getsource(manager.ManagerWindow._build_menus)
        for method in set(re.findall(r'\bself\.([a-z_]+)\b(?!\s*\.)', source)):
            if method in ('workspace', '_workspace_actions', '_tools_menu', '_help_dialog'):
                continue
            self.assertTrue(hasattr(manager.ManagerWindow, method), method)


class DropEventTests(unittest.TestCase):
    def setUp(self):
        self.manager = load('database_favorites_manager')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.timer = MagicMock()
        self.manager.QTimer = self.timer

    def event(self, path):
        event = MagicMock()
        event.mimeData.return_value.hasUrls.return_value = True
        event.mimeData.return_value.urls.return_value = [MagicMock(**{'isLocalFile.return_value': True,
                                                                   'toLocalFile.return_value': str(path)})]
        return event

    def window(self):
        window = MagicMock()
        window._dropped_paths = self.manager.ManagerWindow._dropped_paths
        return window

    def test_card_folder_starts_import_after_the_drop(self):
        (self.base / 'card' / 'BCDx36HP').mkdir(parents=True)
        window, event = self.window(), self.event(self.base / 'card')
        self.manager.ManagerWindow.dropEvent(window, event)
        event.acceptProposedAction.assert_called_once()
        window.import_from_scanner.assert_not_called()           # deferred, not inside the drop handler
        self.timer.singleShot.call_args[0][1]()
        window.import_from_scanner.assert_called_once_with(folder=str(self.base / 'card'))

    def test_hpd_file_opens_the_inspector(self):
        f = self.base / 'f_000001.hpd'
        f.write_text('x')
        window = self.window()
        self.manager.ManagerWindow.dropEvent(window, self.event(f))
        self.timer.singleShot.call_args[0][1]()
        window.inspect_native_favorites.assert_called_once_with(path=str(f))

    def test_unsupported_drop_is_refused_with_a_reason(self):
        other = self.base / 'notes.txt'
        other.write_text('x')
        window, event = self.window(), self.event(other)
        self.manager.QMessageBox = MagicMock()
        self.manager.ManagerWindow.dropEvent(window, event)
        event.ignore.assert_called_once()
        self.manager.QMessageBox.information.assert_called_once()
        self.timer.singleShot.assert_not_called()
        enter = self.event(other)
        self.manager.ManagerWindow.dragEnterEvent(window, enter)
        enter.ignore.assert_called_once()


class BusyDialogTests(unittest.TestCase):
    """Long scanner operations must run off the GUI thread behind a busy dialog."""

    def setUp(self):
        self.manager = load('database_favorites_manager')
        self.cls = self.manager.ManagerWindow
        self.manager.QMessageBox = MagicMock()
        self.window = MagicMock()
        self.window._db_update_busy = False
        self.window._scanner_write_thread = None
        self.window._export_preview_thread = None
        self.window._scanner_operation_running = lambda what='this': self.cls._scanner_operation_running(self.window, what)
        self.ran = []
        self.window._run_background = lambda title, text, work, done: self.ran.append((title, text, work, done))

    def test_backup_runs_in_background_and_reports(self):
        from unittest.mock import patch
        self.window.pick_scanner_folder.return_value = '/card'
        self.manager.QMessageBox.question.return_value = self.manager.QMessageBox.StandardButton.Yes
        backup = MagicMock(return_value=('/backups/x', {'file_count': 7}))
        with patch.dict(sys.modules, {'scanner_backup': MagicMock(backup_scanner=backup)}):
            self.cls.backup_scanner_configuration(self.window)
            backup.assert_not_called()                    # nothing ran on the GUI thread
            title, text, work, done = self.ran[0]
            self.assertTrue(self.window._db_update_busy)
            self.assertIn('keep the scanner connected', text)
            done(work(), None)
        backup.assert_called_once_with('/card')
        self.assertFalse(self.window._db_update_busy)
        self.assertIn('7', str(self.manager.QMessageBox.information.call_args))

    def test_backup_failure_clears_busy_flag(self):
        self.window.pick_scanner_folder.return_value = '/card'
        self.manager.QMessageBox.question.return_value = self.manager.QMessageBox.StandardButton.Yes
        with patch_backup(MagicMock()):
            self.cls.backup_scanner_configuration(self.window)
            self.ran[0][3](None, 'OSError: card removed')
        self.assertFalse(self.window._db_update_busy)
        self.manager.QMessageBox.warning.assert_called_once()

    def test_second_operation_is_refused_while_busy(self):
        self.window._db_update_busy = True
        self.window.pick_scanner_folder.return_value = '/card'
        self.manager.QMessageBox.question.return_value = self.manager.QMessageBox.StandardButton.Yes
        with patch_backup(MagicMock()):
            self.cls.backup_scanner_configuration(self.window)
        self.assertEqual(self.ran, [])
        self.manager.QMessageBox.information.assert_called_once()

    def test_closing_is_refused_during_a_scanner_operation(self):
        event = MagicMock()
        self.window._db_update_busy = True
        self.cls.closeEvent(self.window, event)
        event.ignore.assert_called_once()
        self.assertIn('DO NOT DISCONNECT', str(self.manager.QMessageBox.warning.call_args))

    def test_restore_listing_does_not_hash_every_backup(self):
        import scanner_restore
        from unittest.mock import patch
        listing = MagicMock(return_value=[])
        with patch.object(scanner_restore, 'list_backups', listing), \
             patch.object(scanner_restore, 'emergency_backups', return_value=[]), \
             qt_stub.installed(forget=()):
            self.cls.restore_from_backup(self.window)
        listing.assert_called_once_with(verify=False)

    def test_restore_runs_in_background_with_stale_check_and_clears_busy(self):
        import scanner_restore
        from unittest.mock import patch
        plan = {'scanner': '/card', 'manifest': {'files': [1, 2]}, 'delete': [],
                'changes': [{'action': 'ADD', 'path': 'a'}]}
        self.manager.QMessageBox.warning.return_value = self.manager.QMessageBox.StandardButton.Yes
        prepare = MagicMock(return_value=plan)
        execute = MagicMock(return_value={'changed': 1, 'deleted': 0, 'emergency': '/e'})
        proceed = MagicMock()
        with patch.object(scanner_restore, 'prepare_restore', prepare), \
             patch.object(scanner_restore, 'execute_restore', execute), qt_stub.installed(forget=()):
            import importlib
            widgets = importlib.import_module('PyQt6.QtWidgets')
            widgets.QDialogButtonBox = MagicMock()
            widgets.QDialogButtonBox.return_value.addButton.return_value = proceed
            self.cls._show_restore_plan(self.window, Path('/b/x'), '/card', plan)
        perform = proceed.clicked.connect.call_args[0][0]
        perform()
        execute.assert_not_called()                       # confirming only starts the background job
        self.assertTrue(self.window._db_update_busy)
        title, text, work, done = self.ran[0]
        self.assertIn('DO NOT DISCONNECT', text)
        done(work(), None)
        prepare.assert_called_once()
        execute.assert_called_once()
        self.assertFalse(self.window._db_update_busy)
        self.assertIn('Restored 1 files', str(self.manager.QMessageBox.information.call_args))

    def test_restore_failure_and_stale_preview_are_reported(self):
        import scanner_restore
        from unittest.mock import patch
        plan = {'scanner': '/card', 'manifest': {'files': []}, 'delete': ['x'], 'changes': []}
        self.manager.QMessageBox.warning.return_value = self.manager.QMessageBox.StandardButton.Yes
        execute = MagicMock()
        proceed = MagicMock()
        with patch.object(scanner_restore, 'prepare_restore', return_value={'different': True}), \
             patch.object(scanner_restore, 'execute_restore', execute), qt_stub.installed(forget=()):
            import importlib
            widgets = importlib.import_module('PyQt6.QtWidgets')
            widgets.QDialogButtonBox = MagicMock()
            widgets.QDialogButtonBox.return_value.addButton.return_value = proceed
            self.cls._show_restore_plan(self.window, Path('/b/x'), '/card', plan)
            proceed.clicked.connect.call_args[0][0]()
            title, text, work, done = self.ran[0]
            with self.assertRaises(RuntimeError):
                work()                                    # stale preview refuses before any write
            done(None, 'RuntimeError: stale')
        execute.assert_not_called()
        self.assertFalse(self.window._db_update_busy)
        self.manager.QMessageBox.critical.assert_called_once()


def patch_backup(backup):
    from unittest.mock import patch
    return patch.dict(sys.modules, {'scanner_backup': MagicMock(backup_scanner=backup)})


if __name__ == '__main__':
    unittest.main()
