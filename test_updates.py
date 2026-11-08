# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Help → Check for Updates…: versions, .debs in Downloads, GitHub releases, the window."""
import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import qt_stub

FORGET = ('updates', 'help_system')


def load():
    with qt_stub.installed(forget=FORGET):
        return importlib.import_module('updates')


class Store(dict):
    def value(self, key, default=None):
        return self.get(key, default)

    def setValue(self, key, value):
        self[key] = value


def release(*names):
    return json.dumps({'body': 'notes', 'assets': [
        {'name': n, 'browser_download_url': 'https://github.com/x/y/releases/download/v1/' + n} for n in names]})


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.u = load()

    def test_versions_and_names(self):
        k = self.u.version_key
        self.assertLess(k('0.0.9f'), k('0.0.9g'))
        self.assertLess(k('0.0.9g'), k('0.0.10'))
        self.assertLess(k('0.0.9i'), k('0.1.0-personal'))
        self.assertEqual(k('0.1.0-personal'), k('0.1.0'))
        self.assertEqual(self.u.deb_version(self.u.PACKAGE_NAME + '_0.0.9h_all.deb'), '0.0.9h')
        self.assertIsNone(self.u.deb_version('sds100-monitor_1.1.60_all.deb'))

    def test_downloads(self):
        folder = Path(tempfile.mkdtemp())
        for n in (self.u.PACKAGE_NAME + '_0.0.9f_all.deb', self.u.PACKAGE_NAME + '_0.0.9h_all.deb', self.u.PACKAGE_NAME + '_0.0.10_all.deb',
                  'sds100-monitor_9.9.9_all.deb'):
            (folder / n).write_text('x')
        self.assertEqual([v for v, _p in self.u.local_updates('0.0.9g', folder)], ['0.0.10', '0.0.9h'])

    def test_github(self):
        got = self.u.github_latest('jl/sds', fetch=lambda url: release(self.u.PACKAGE_NAME + '_0.0.9h_all.deb',
                                                                          'sds100-monitor_1.1.60_all.deb'))
        self.assertEqual(got[0], '0.0.9h')
        self.assertIsNone(self.u.github_latest('bad repo', fetch=lambda url: release()))

    def test_checker_and_skip(self):
        store = Store()
        checker = self.u.UpdateChecker(store=store)
        got = []
        checker.found = MagicMock()
        checker.found.emit = got.append
        with patch.object(self.u, 'local_updates', return_value=[('0.0.99', Path('/tmp/' + self.u.PACKAGE_NAME + '_0.0.99_all.deb'))]), \
                patch.object(self.u, 'deb_notes', return_value='new'):
            checker.check(quiet=True)
            self.assertEqual(got[-1]['version'], '0.0.99')
            store['skip_version'] = '0.0.99'
            checker.check(quiet=True)
            self.assertIsNone(got[-1])
            checker.check(quiet=False)
            self.assertEqual(got[-1]['notes'], 'new')

    def test_dialog_install(self):
        u = self.u
        checker = u.UpdateChecker(store=Store())
        u.UpdateDialog._get_child_mock = lambda _self, **kw: MagicMock(**kw)
        dialog = u.UpdateDialog(MagicMock(), checker)
        deb = Path(tempfile.mkdtemp()) / (self.u.PACKAGE_NAME + '_0.0.99_all.deb')
        deb.write_text('x')
        dialog.show_result({'version': '0.0.99', 'source': 'Downloads', 'path': deb, 'notes': '', 'name': deb.name})
        with patch.object(u.shutil, 'which', return_value='/usr/bin/pkexec'), patch.object(u, 'QProcess') as proc:
            dialog.install()
        args = proc.return_value.start.call_args[0]
        self.assertEqual([args[0]] + args[1][:2], ['pkexec', '/usr/bin/apt-get', 'install'])
        staged = Path(args[1][-1])
        self.assertNotEqual(staged.parent, deb.parent)
        self.assertEqual(staged.stat().st_mode & 0o777, 0o644)
        dialog.process = None
        dialog.installed(126)
        dialog.result_label.setText.assert_called_with('Not installed (cancelled).')


if __name__ == '__main__':
    unittest.main()
