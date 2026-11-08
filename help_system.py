# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""About text, credits and Help-menu content (no Qt here, so it can be tested)."""
from pathlib import Path
import platform
import re
import sys

from edition import APP_NAME, APP_VERSION, PERSONAL
AUTHOR = 'J. Lynch'
COPYRIGHT = 'Copyright © 2026 J. Lynch'
LICENSE_ID = 'GPL-3.0-or-later'
HERE = Path(__file__).resolve().parent

ABOUT_LINES = (
    f'{APP_NAME}  v{APP_VERSION}' + ('  (personal build)' if PERSONAL else ''),
    '(formerly SDS100 Database & Favorites Manager)',
    'Scanner database updates, Favorites Lists and scanner settings for the Uniden SDS100.',
    '',
    f'Created by {AUTHOR}.',
    'AI was used in the build: this program was developed with the assistance of Claude, an AI assistant made by '
    'Anthropic. Its scanner writes are validated, backed up first and tested on a real SDS100, but you remain '
    'responsible for your scanner and your data.',
    '',
    f'{COPYRIGHT}. Free software released under the GNU General Public License, version 3 or (at your option) any '
    'later version. It comes with ABSOLUTELY NO WARRANTY; see Help → License.',
    '',
    'Not affiliated with or endorsed by Uniden. Uniden, SDS100 and Sentinel are trademarks of their owners.',
    'Built with Python and PyQt6 (GPL v3).',
)


def about_text():
    return '\n'.join(ABOUT_LINES)


def read_doc(name):
    """Text of a bundled document (USER_GUIDE.md, CHANGELOG.md, LICENSE, ...); None if it is missing."""
    if '/' in name or '\\' in name or name.startswith('.'):
        return None
    path = HERE / name
    try:
        if path.is_symlink() or not path.is_file():
            return None
        return path.read_text(encoding='utf-8')
    except (OSError, UnicodeError):
        return None


def headings(markdown):
    """[(level, title)] for '##' and '###' headings, ignoring fenced code."""
    found, fenced = [], False
    for line in markdown.splitlines():
        if line.startswith('```'):
            fenced = not fenced
        match = None if fenced else re.fullmatch(r'(#{2,3}) +(.+?) *', line)
        if match:
            found.append((len(match.group(1)), match.group(2)))
    return found


def diagnostic_report(configuration=None):
    """Plain text to paste into a problem report. Contains no scanner data or file contents."""
    lines = [f'{APP_NAME} v{APP_VERSION}', f'Python {platform.python_version()}', f'OS {platform.platform()}']
    try:
        from PyQt6.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
        lines.append(f'Qt {QT_VERSION_STR}, PyQt {PYQT_VERSION_STR}')
    except Exception:
        lines.append('Qt: not available')
    if configuration:
        lines.append(f'Active configuration: {configuration}')
    return '\n'.join(lines)


def changelog_version():
    """Newest version named in CHANGELOG.md, for consistency checks."""
    text = read_doc('CHANGELOG.md') or ''
    match = re.search(r'^## v([0-9][0-9.]*[a-z]?)\b', text, re.M)
    return match.group(1) if match else None
