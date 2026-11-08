# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Help → Check for Updates… (v0.0.9g).

Installed from the sds-manager (or sds-manager-personal) .deb into /opt/sds-manager. Looks for a newer
<package>_<version>_all.deb in ~/Downloads and, when a GitHub repository is set, in its latest
release. INSTALL runs apt-get on the file through pkexec (KDE asks for your password). Nothing is
installed or downloaded without you pressing INSTALL.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.request
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, QSettings, QTimer, pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                             QMessageBox, QPushButton, QTextEdit, QVBoxLayout)

from help_system import APP_VERSION
from edition import APP_NAME, PACKAGE_NAME, PROGRAM_COMMAND


def settings():
    return QSettings('SDS100DatabaseFavoritesManager', 'Updates')


def version_key(version):
    text = str(version).strip().lower().replace('-personal', '')
    return tuple((0, int(t)) if t.isdigit() else (1, t) for t in re.findall(r'\d+|[a-z]+', text))


def deb_version(filename, package=PACKAGE_NAME):
    m = re.fullmatch(re.escape(package) + r'_([0-9][0-9A-Za-z.+~]*)_(?:all|amd64)\.deb', Path(filename).name)
    return m.group(1) if m else None


def installed_from_deb():
    return str(Path(__file__).resolve()).startswith('/opt/')


def local_updates(current=APP_VERSION, folder=None, package=PACKAGE_NAME):
    folder = Path(folder or Path.home() / 'Downloads')
    found = []
    try:
        files = list(folder.glob('*.deb'))
    except OSError:
        return []
    for path in files:
        version = deb_version(path.name, package)
        if version and version_key(version) > version_key(current) and path.is_file() and not path.is_symlink():
            found.append((version, path))
    found.sort(key=lambda f: version_key(f[0]), reverse=True)
    return found


def github_latest(repo, package=PACKAGE_NAME, fetch=None):
    repo = str(repo or '').strip().strip('/')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        return None
    if fetch is None:
        def fetch(address):
            request = urllib.request.Request(address, headers={
                'Accept': 'application/vnd.github+json', 'User-Agent': f'SDS100-Manager/{APP_VERSION}'})
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.read(2_000_000)
    data = json.loads(fetch(f'https://api.github.com/repos/{repo}/releases/latest'))
    best = None
    for asset in data.get('assets') or []:
        name = str(asset.get('name', ''))
        version = deb_version(name, package)
        link = str(asset.get('browser_download_url', ''))
        if version and link.startswith('https://') and (best is None or version_key(version) > version_key(best[0])):
            best = (version, link, str(data.get('body') or '')[:4000], name)
    return best


def deb_notes(path):
    try:
        out = subprocess.run(['dpkg-deb', '-f', str(path), 'Description'], capture_output=True, text=True,
                             timeout=15)
    except (OSError, subprocess.SubprocessError):
        return ''
    lines = out.stdout.splitlines()[1:]
    return '\n'.join('' if l.strip() == '.' else l[1:] if l.startswith(' ') else l for l in lines).strip()


def staged_copy(path):
    """A copy of the .deb that apt's "_apt" user can read: it can't enter your home folder, so apt
    otherwise says "Download is performed unsandboxed as root…"."""
    folder = Path(tempfile.mkdtemp(prefix='sds100-update-'))
    folder.chmod(0o755)
    target = folder / Path(path).name
    shutil.copy2(path, target)
    target.chmod(0o644)
    return target


def install_command(path):
    return ['pkexec', '/usr/bin/apt-get', 'install', '-y', str(Path(path).resolve())]


class UpdateChecker(QObject):
    found = pyqtSignal(object)
    github_done = pyqtSignal(object)

    def __init__(self, parent=None, store=None):
        super().__init__(parent)
        self.store = store if store is not None else settings()
        self.latest = None
        self.quiet = False
        self.github_error = ''
        self.github_done.connect(self._github_result)

    def setting(self, key, default=''):
        return str(self.store.value(key, default) or '')

    def check(self, quiet=False):
        self.quiet = quiet
        local = local_updates()
        self.latest = ({'version': local[0][0], 'source': 'Downloads', 'path': local[0][1],
                        'notes': deb_notes(local[0][1]), 'name': local[0][1].name} if local else None)
        repo = self.setting('github_repo')
        if repo:
            threading.Thread(target=self._github, args=(repo,), daemon=True).start()
        else:
            self._announce()

    def _github(self, repo):
        try:
            result = github_latest(repo)
        except Exception as exc:
            result = {'error': str(exc)}
        self.github_done.emit(result)

    def _github_result(self, result):
        self.github_error = result.get('error') if isinstance(result, dict) else ''
        if isinstance(result, tuple) and version_key(result[0]) > version_key(APP_VERSION):
            if self.latest is None or version_key(result[0]) > version_key(self.latest['version']):
                self.latest = {'version': result[0], 'source': 'GitHub', 'url': result[1], 'notes': result[2],
                               'name': result[3]}
        self._announce()

    def _announce(self):
        latest = self.latest
        if latest and self.quiet and latest['version'] == self.setting('skip_version'):
            latest = None
        self.found.emit(latest)


class UpdateDialog(QDialog):
    def __init__(self, window, checker):
        super().__init__(window)
        self.main = window
        self.checker = checker
        self.latest = None
        self.process = None
        self.setWindowTitle('Check for Updates')
        self.resize(640, 520)
        layout = QVBoxLayout(self)
        how = ('installed from a .deb package' if installed_from_deb()
               else 'run from a folder (installing an update adds the .deb version alongside)')
        intro = QLabel(f'{APP_NAME} v{APP_VERSION} ({PACKAGE_NAME}), {how}.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.result_label = QLabel('Checking…')
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)
        self.notes = QTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setPlaceholderText("What's new appears here.")
        layout.addWidget(self.notes, 1)
        form = QFormLayout()
        self.startup = QCheckBox('Check when the Manager starts')
        self.startup.setChecked(checker.setting('at_startup', 'true') == 'true')
        self.startup.toggled.connect(lambda on: checker.store.setValue('at_startup', 'true' if on else 'false'))
        form.addRow('', self.startup)
        self.repo = QLineEdit(checker.setting('github_repo'))
        self.repo.setPlaceholderText('owner/repository (leave empty until the project is on GitHub)')
        self.repo.editingFinished.connect(lambda: checker.store.setValue('github_repo', self.repo.text().strip()))
        form.addRow('GitHub', self.repo)
        layout.addLayout(form)
        where = QLabel(f'Also looks in {Path.home() / "Downloads"} for {PACKAGE_NAME}_<version>_all.deb.')
        where.setWordWrap(True)
        layout.addWidget(where)
        buttons = QHBoxLayout()
        self.check_btn = QPushButton('Check Now')
        self.check_btn.clicked.connect(self.check)
        self.install_btn = QPushButton('Install')
        self.install_btn.clicked.connect(self.install)
        self.skip_btn = QPushButton('Skip This Version')
        self.skip_btn.clicked.connect(self.skip)
        self.close_btn = QPushButton('Close')
        self.close_btn.clicked.connect(self.accept)
        for b in (self.check_btn, self.install_btn, self.skip_btn):
            buttons.addWidget(b)
        buttons.addStretch(1)
        buttons.addWidget(self.close_btn)
        layout.addLayout(buttons)
        checker.found.connect(self.show_result)
        self.finished.connect(self._closed)
        self.install_btn.setEnabled(False)
        self.skip_btn.setEnabled(False)
        QTimer.singleShot(0, self.check)

    def _closed(self, *_):
        try:
            self.checker.found.disconnect(self.show_result)
        except (TypeError, RuntimeError):
            pass

    def check(self):
        self.checker.store.setValue('github_repo', self.repo.text().strip())
        self.result_label.setText('Checking…')
        self.install_btn.setEnabled(False)
        self.skip_btn.setEnabled(False)
        self.checker.check(quiet=False)

    def show_result(self, latest):
        self.latest = latest
        error = self.checker.github_error
        if latest is None:
            self.result_label.setText(f'You have the newest version (v{APP_VERSION}).'
                                      + (f" GitHub couldn't be checked: {error}" if error else ''))
            self.notes.clear()
        else:
            self.result_label.setText(f"Version {latest['version']} is available ({latest['source']}: {latest['name']}).")
            self.notes.setPlainText(latest.get('notes') or '')
        self.install_btn.setEnabled(latest is not None)
        self.skip_btn.setEnabled(latest is not None)

    def skip(self):
        if self.latest:
            self.checker.store.setValue('skip_version', self.latest['version'])
            self.result_label.setText(f"Version {self.latest['version']} won't be offered at startup again.")

    def install(self):
        latest = self.latest
        if not latest:
            return
        if 'url' in latest:
            target = Path.home() / 'Downloads' / latest['name']
            self.result_label.setText(f"Downloading {latest['name']}…")
            self.install_btn.setEnabled(False)

            def download():
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    tmp = target.with_name(target.name + '.part')
                    with urllib.request.urlopen(latest['url'], timeout=60) as response, tmp.open('wb') as out:
                        shutil.copyfileobj(response, out)
                    os.replace(tmp, target)
                    QTimer.singleShot(0, lambda: self.run_install(target))
                except Exception as exc:
                    QTimer.singleShot(0, lambda: self.result_label.setText(f'Download failed: {exc}'))
            threading.Thread(target=download, daemon=True).start()
        else:
            self.run_install(latest['path'])

    def run_install(self, path):
        if shutil.which('pkexec') is None:
            QMessageBox.information(self, 'Install', 'Install it from a terminal with:\n\n'
                                    f'sudo apt install {Path(path).resolve()}')
            return
        self.result_label.setText(f'Installing {Path(path).name}… (KDE asks for your password)')
        self.install_btn.setEnabled(False)
        self.close_btn.setEnabled(False)
        try:
            path = staged_copy(path)
        except OSError as exc:
            QMessageBox.warning(self, 'Install', f"Couldn't prepare the package: {exc}")
            return
        argv = install_command(path)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.finished.connect(lambda code, _status: self.installed(code))
        self.process.start(argv[0], argv[1:])

    def installed(self, code):
        output = bytes(self.process.readAll()).decode(errors='replace') if self.process else ''
        self.process = None
        self.close_btn.setEnabled(True)
        if code != 0:
            self.result_label.setText('Not installed' + (' (cancelled).' if code in (126, 127)
                                                         else f' (apt-get exit {code}).'))
            self.notes.setPlainText(output[-4000:])
            self.install_btn.setEnabled(True)
            return
        self.result_label.setText('Installed. Restart the Manager to use the new version.')
        if QMessageBox.question(self, 'Update installed', 'Restart the Manager now? (Save your work first.)') \
                == QMessageBox.StandardButton.Yes:
            QProcess.startDetached('/bin/sh', ['-c', f'sleep 3; exec {PROGRAM_COMMAND}'])
            self.accept()
            self.main.close()

    def reject(self):
        if self.process is not None:
            return                                  # never leave apt-get half-way by closing
        super().reject()


class UpdatesMixin:
    """For ManagerWindow."""

    def start_update_checks(self):
        self._updates = UpdateChecker(self)
        self._updates.found.connect(self._update_found)
        if self._updates.setting('at_startup', 'true') == 'true':
            QTimer.singleShot(20000, lambda: self._updates.check(quiet=True))

    def _update_found(self, latest):
        if latest and self._updates.quiet:
            self.statusBar().showMessage(f"Update {latest['version']} available: Help → Check for Updates…", 30000)

    def check_for_updates(self):
        if getattr(self, '_updates', None) is None:
            self.start_update_checks()
        UpdateDialog(self, self._updates).exec()
