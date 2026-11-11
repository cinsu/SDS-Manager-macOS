# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""User preferences: a small validated JSON file. Pure Python (no Qt) so it can be tested.

Preferences never weaken a scanner-write safeguard: the checks, the verified backup and the confirmation before
every physical write are not preferences.  An unreadable or invalid file falls back to the defaults, and an
invalid single value falls back to its default; the program never refuses to start over a preference.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

CONFIG_DIR_NAME = 'sds100-database-favorites-manager'


def config_dir():
    base = os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
    return Path(base).expanduser() / CONFIG_DIR_NAME


def state_dir():
    base = os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local/state')
    return Path(base).expanduser() / CONFIG_DIR_NAME


def preferences_path():
    return config_dir() / 'preferences.json'


class Pref:
    def __init__(self, key, default, label, group, kind, values=(), low=0, high=0, help='', labels=None):
        self.key, self.default, self.label, self.group = key, default, label, group
        self.kind, self.values, self.low, self.high, self.help = kind, tuple(values), low, high, help
        self.labels = dict(labels or {})          # value → text shown in Settings (choices only)

    def display(self, value):
        return self.labels.get(value, value)

    def valid(self, value):
        if self.kind == 'bool':
            return isinstance(value, bool)
        if self.kind == 'int':
            return type(value) is int and self.low <= value <= self.high
        if self.kind == 'choice':
            return isinstance(value, str) and value in self.values
        if self.kind == 'folder':
            return isinstance(value, str) and len(value) <= 4096 and '\x00' not in value \
                and (value == '' or value.startswith('/'))
        return False


PREFS = (
    # Scanner connection
    Pref('mount_folder', '/Volumes' if sys.platform == 'darwin' else '/run/media', 'Folder where removable media appear', 'Scanner connection', 'folder',
         help='Where file dialogs start, and where the detector looks first. Empty = look in every mounted volume.'),
    Pref('auto_detect', True, 'Detect the SDS100 when it is connected', 'Scanner connection', 'bool',
         help='Reads the mounted volumes every few seconds (read-only) and fills in the Scanner panel.'),
    Pref('offer_detected_scanner', True, 'Offer the detected scanner in folder prompts', 'Scanner connection', 'bool',
         help='Asks "Use the detected scanner?" instead of making you browse. Every write still re-checks the USB identity.'),
    # Backups
    Pref('backup_keep', 20, 'Backups to keep when cleaning up', 'Backups', 'int', low=3, high=1000,
         help='Used by "Clean up old backups". Backups are never deleted automatically.'),
    Pref('backup_warn_mb', 2000, 'Warn when backups use more than (MB)', 'Backups', 'int', low=100, high=1_000_000),
    # Confirmations
    Pref('confirm_low_risk', True, 'Ask before low-risk actions', 'Confirmations', 'bool',
         help='Applies to creating a new local list and similar. Writes to the scanner are always confirmed; '
              'that cannot be turned off.'),
    # Database
    Pref('keep_database_versions', 3, 'Rebuilt database versions to keep when cleaning up', 'Database', 'int', low=1, high=50,
         help='Used by "Clean up old database versions". The current version and the one on your scanner are always kept.'),
    # Appearance (the same themes as SDS100 Monitor; also in Tools → Theme)
    Pref('theme', 'system', 'Theme', 'Appearance', 'choice', values=('system', 'dark', 'light', 'night'),
         labels={'system': 'System (follow KDE)', 'dark': 'Dark', 'light': 'Light', 'night': 'Night (red)'},
         help='System follows KDE\'s light or dark colour scheme. Night is dim red, to keep night vision.'),
    Pref('accent', 'blue', 'Accent colour', 'Appearance', 'choice',
         values=('blue', 'red', 'green', 'amber', 'purple', 'teal'),
         labels={'blue': 'Blue', 'red': 'Red', 'green': 'Green', 'amber': 'Amber', 'purple': 'Purple',
                 'teal': 'Teal'},
         help='Tabs, menu highlights, selections and accent buttons. Not used in Night.'),
    Pref('text_size', 'normal', 'Text size', 'Appearance', 'choice', values=('small', 'normal', 'large', 'xlarge'),
         labels={'small': 'Small', 'normal': 'Normal', 'large': 'Large', 'xlarge': 'Extra large'}),
    Pref('font_size', 0, 'Exact font size in points (0 = use Text size)', 'Appearance', 'int', low=0, high=24,
         help='Overrides Text size when set.'),
    # Diagnostics
    Pref('log_level', 'WARNING', 'Log detail', 'Diagnostics', 'choice', values=('ERROR', 'WARNING', 'INFO', 'DEBUG'),
         help='Takes effect the next time the program starts.'),
)
BY_KEY = {p.key: p for p in PREFS}
DEFAULTS = {p.key: p.default for p in PREFS}


def validate(values):
    """(clean dict with every key, list of keys that were invalid or unknown and were reset/ignored)."""
    clean, bad = dict(DEFAULTS), []
    if not isinstance(values, dict):
        return clean, ['(file)']
    for key, value in values.items():
        pref = BY_KEY.get(key)
        if pref is None:
            bad.append(key)
        elif pref.valid(value):
            clean[key] = value
        else:
            bad.append(key)
    return clean, bad


def load(path=None):
    path = Path(path) if path else preferences_path()
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
            return dict(DEFAULTS)
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError, UnicodeError):
        return dict(DEFAULTS)
    return validate(data)[0]


def save(values, path=None):
    """Validate and write atomically.  Raises ValueError for an invalid value, OSError if it cannot be written."""
    clean, bad = validate(values)
    if bad:
        raise ValueError('Invalid preference value(s): ' + ', '.join(bad))
    path = Path(path) if path else preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.prefs-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(clean, out, indent=2, sort_keys=True)
            out.write('\n')
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)
    return clean
