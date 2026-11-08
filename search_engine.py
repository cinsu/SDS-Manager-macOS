# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Find Everywhere: one query across the master database and a configuration's Favorites Lists.

Streams the raw tab-separated files (a whole 70-file database scans in a few seconds, no index
needed).  Pure functions plus file reads; never writes.

Query forms:
  text            case-insensitive substring of any system, department, site, channel, talkgroup
                  or list name
  154.9 / 460.025 megahertz; matches every frequency from that value up to the next digit
                  (154.9 -> 154.900000 to 154.999999; 460.025 -> exactly 460.025)
  12345           a talkgroup ID (exact), and also text containing 12345
  154900000       a frequency in hertz (exact), when 7 digits or more
"""
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import flist_settings

DEFAULT_CAP = 500
SYSTEM_KINDS = ('Conventional', 'Trunk')
DEPT_KINDS = ('C-Group', 'T-Group')
NAMED = {'Site': 'site', 'C-Freq': 'channel', 'TGID': 'talkgroup'}
NUMBER = re.compile(r'\d+(\.\d+)?')


class Query:
    def __init__(self, text):
        self.text = text.strip()
        self.needle = self.text.casefold()
        self.freq = None      # (low_hz, high_hz) half-open
        self.tgid = None
        if NUMBER.fullmatch(self.text):
            if '.' in self.text:
                places = len(self.text.split('.')[1])
                try:
                    low = int(Decimal(self.text) * 1000000)
                except InvalidOperation:  # pragma: no cover - regex already guarantees a number
                    return
                self.freq = (low, low + 10 ** max(0, 6 - places))
            elif len(self.text) >= 7:
                self.freq = (int(self.text), int(self.text) + 1)
            else:
                self.tgid = self.text.lstrip('0') or '0'

    @property
    def empty(self):
        return not self.text

    def matches_name(self, name):
        return bool(self.needle) and self.needle in name.casefold()

    def matches_freq(self, value):
        if self.freq is None or not value.isdigit():
            return False
        return self.freq[0] <= int(value) < self.freq[1]

    def matches_tgid(self, value):
        return self.tgid is not None and value.lstrip('0') == self.tgid


def _field(fields, index):
    return fields[index] if len(fields) > index else ''


def search_file(path, query, source, cancel=None, limit=DEFAULT_CAP):
    """Matches in one HPD file: list of dicts (source, system, department, kind, name, value)."""
    out = []
    system = department = site = ''
    try:
        raw = Path(path).read_bytes().decode('cp1252', 'replace')
    except OSError:
        return out
    for line in raw.splitlines():
        if cancel is not None and cancel():
            break
        fields = line.split('\t')
        kind = fields[0]
        name = _field(fields, 3)
        if kind in SYSTEM_KINDS:
            system, department, site = name, '', ''
            label, value = 'system', ''
        elif kind in DEPT_KINDS:
            department, site = name, ''
            label, value = 'department', ''
        elif kind == 'Site':
            site = name
            label, value = 'site', ''
        elif kind in NAMED:
            label, value = NAMED[kind], _field(fields, 5)
        elif kind == 'T-Freq':
            label, name, value = 'site frequency', site, _field(fields, 5)
        else:
            continue
        if kind in ('C-Freq', 'T-Freq'):
            hit = query.matches_freq(value) or (kind == 'C-Freq' and query.matches_name(name))
        elif kind == 'TGID':
            hit = query.matches_tgid(value) or query.matches_name(name)
        else:
            hit = query.matches_name(name)
        if hit:
            out.append({'source': source, 'system': system, 'department': department,
                        'kind': label, 'name': name, 'value': _display(kind, value)})
            if len(out) >= limit:
                break
    return out


def _display(kind, value):
    if kind in ('C-Freq', 'T-Freq') and value.isdigit():
        return '%.5f MHz' % (int(value) / 1000000)
    return value


def database_files(database_root):
    root = Path(database_root)
    return [(p, 'Database: ' + p.stem) for p in sorted(root.glob('s_*.hpd'))]


def favorites_files(configuration_root):
    """[(path, source label, list-name hit)] for every Favorites List in a saved configuration."""
    folder = Path(configuration_root) / 'BCDx36HP' / 'favorites_lists'
    try:
        lists = flist_settings.read_lists((folder / 'f_list.cfg').read_bytes())
    except (OSError, ValueError):
        lists = []
    names = {l['filename'].lower(): l['name'] for l in lists}
    return [(p, 'List: ' + names.get(p.name.lower(), p.name)) for p in sorted(folder.glob('f_*.hpd'))]


def search_all(text, database_root=None, configuration_root=None, cap=DEFAULT_CAP, cancel=None,
               progress=None):
    """Return (results, truncated).  Favorites Lists are searched first (usually fewer, more relevant)."""
    query = Query(text)
    if query.empty:
        return [], False
    files = []
    if configuration_root:
        files.extend(favorites_files(configuration_root))
    if database_root:
        files.extend(database_files(database_root))
    results = []
    for index, (path, label) in enumerate(files):
        if cancel is not None and cancel():
            break
        if progress is not None:
            progress(index, len(files), label)
        if label.startswith('List: ') and query.matches_name(label[6:]):
            results.append({'source': label, 'system': '', 'department': '', 'kind': 'list',
                            'name': label[6:], 'value': ''})
        room = cap - len(results)
        if room <= 0:
            return results[:cap], True
        results.extend(search_file(path, query, label, cancel, room))
        if len(results) >= cap:
            return results[:cap], True
    return results, False


def context(result):
    parts = [p for p in (result['system'], result['department']) if p]
    return ' › '.join(parts)


class SearchJob:
    """Runs search_all on a background thread; the GUI polls state from its own thread."""

    def __init__(self, text, database_root=None, configuration_root=None, cap=DEFAULT_CAP):
        import threading
        self.cancelled = False
        self.done = False
        self.error = None
        self.results, self.truncated = [], False
        self.progress = (0, 0, '')
        self._args = (text, database_root, configuration_root, cap)
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def cancel(self):
        self.cancelled = True

    def _run(self):
        try:
            text, database_root, configuration_root, cap = self._args
            self.results, self.truncated = search_all(
                text, database_root, configuration_root, cap, cancel=lambda: self.cancelled,
                progress=lambda i, n, label: setattr(self, 'progress', (i, n, label)))
        except Exception as exc:  # reported to the user by the dialog
            self.error = '%s: %s' % (type(exc).__name__, exc)
        finally:
            self.done = True

    def join(self, timeout=None):
        self._thread.join(timeout)
