# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Tools → RadioReference Account… (v0.1.0): sign in to RadioReference with your own Premium account.

v0.1.4: a package carries SDS-Manager's application key (added by add_rr_key.sh), so the window asks only
for the username and password. The key field is shown, under Advanced, only in a build without a key."""
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import (QCheckBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QVBoxLayout)

import rr_api


def rr_settings():
    return QSettings('SDS100DatabaseFavoritesManager', 'RadioReference')


class RRAccountDialog(QDialog):
    def __init__(self, main, account=None):
        super().__init__(main)
        self.main = main
        self.account = account or rr_api.Account(rr_settings())
        self.setWindowTitle('RadioReference Account')
        self.resize(620, 420)
        layout = QVBoxLayout(self)
        intro = QLabel(
            'SDS-Manager can look up systems, talkgroups and frequencies in the RadioReference database. '
            'Sign in with <b>your own RadioReference account</b>; it needs an active <b>Premium</b> '
            'subscription.<br><br>'
            'RadioReference data is used only to build and update the Favorites Lists of your own scanner, '
            'and only what you add is kept, in your scanner configuration.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        self.username = QLineEdit(self.account.username())
        form.addRow('Username', self.username)
        self.password = QLineEdit(self.account.secret('password'))
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow('Password', self.password)
        layout.addLayout(form)
        self.bundled = bool(self.account.bundled_key)
        self.app_key = QLineEdit('' if self.bundled else self.account.secret('appKey'))
        self.app_key.setEchoMode(QLineEdit.EchoMode.Password)
        if self.bundled:
            key_note = QLabel('Application key: built into this package.')
            key_note.setWordWrap(True)
            layout.addWidget(key_note)
            self.app_key.setVisible(False)
        else:
            advanced = QGroupBox('Advanced')
            box = QFormLayout(advanced)
            self.app_key.setPlaceholderText('The application key from your RadioReference API page')
            box.addRow('Application key', self.app_key)
            hint = QLabel('This build has no application key built in (for example, built from source). '
                          'Enter a RadioReference application key of your own. Packages with a key '
                          'built in don\'t ask for one.')
            hint.setWordWrap(True)
            box.addRow(hint)
            layout.addWidget(advanced)
        secret_words = 'password' if self.bundled else 'password and key'
        stored = self.account.secrets is not None
        self.remember = QCheckBox(f'Remember the {secret_words} in KDE Wallet' if stored else
                                  f'Remember the {secret_words} (no secret store found)')
        self.remember.setChecked(stored)
        self.remember.setEnabled(stored)
        layout.addWidget(self.remember)
        if not stored:
            note = QLabel('No KDE Wallet or other secret store is available (install <b>python3-keyring</b>), '
                          f'so the {secret_words} {"is" if self.bundled else "are"} kept only until SDS-Manager '
                          'closes, and never written to a settings file.')
            note.setWordWrap(True)
            layout.addWidget(note)
        self.status_label = QLabel('')
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        layout.addStretch(1)
        buttons = QHBoxLayout()
        self.test_btn = QPushButton('Save and Test Sign-in')
        self.test_btn.clicked.connect(lambda checked=False: self.save_and_test())
        forget = QPushButton('Forget Saved Password' if self.bundled else 'Forget Saved Password and Key')
        forget.clicked.connect(lambda checked=False: self.forget())
        close = QPushButton('Close')
        close.clicked.connect(self.accept)
        buttons.addWidget(self.test_btn)
        buttons.addWidget(forget)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def save(self):
        key = '' if self.bundled else self.app_key.text()
        kept = self.account.save(self.username.text(), self.password.text(), key, self.remember.isChecked())
        return kept

    def save_and_test(self):
        kept = self.save()
        where = 'saved in KDE Wallet' if kept else 'kept for this session'
        words = 'password' if self.bundled else 'password and key'
        self.status_label.setText(f'Signing in to RadioReference… ({words} {where})')
        self.test_btn.setEnabled(False)
        try:
            client = self.account.client()
        except rr_api.RRError as exc:
            self.tested(None, str(exc))
            return
        run = getattr(self.main, '_run_background', None)
        if run is None:
            try:
                self.tested(client.user_data(), None)
            except rr_api.RRError as exc:
                self.tested(None, str(exc))
            return
        run('RadioReference', 'Checking your RadioReference sign-in…', client.user_data,
            lambda result, error: self.tested(result, error))

    def tested(self, result, error):
        self.test_btn.setEnabled(True)
        if error or not isinstance(result, dict):
            self.status_label.setText(f'<span style="color:#ff9e91">✗ {error or "No answer from RadioReference."}</span>')
            return
        expires = result.get('subExpireDate') or 'unknown'
        self.status_label.setText(f'<span style="color:#7ee3a5">✓ Signed in as <b>{result.get("username", "?")}</b>. '
                            f'Premium subscription until {expires}.</span>')

    def forget(self):
        self.account.forget_stored()
        self.account.session = {}
        self.password.clear()
        self.app_key.clear()
        self.status_label.setText('The saved password was removed.' if self.bundled else
                                  'The saved password and key were removed.')
