# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""How often SDS100 Monitor heard each channel and talkgroup (v0.1.19).

Reads the Monitor's daily reception history (~/SDS100Monitor/history/reception_history_YYYY-MM-DD.csv,
columns Start, End, Duration (s), System, Department, Channel, Frequency, Talkgroup, RSSI) for the last
so many days. Talkgroups are matched by system name and talkgroup ID, conventional channels by frequency.
The Monitor's files are only read. Pure apart from reading those files; no Qt.
"""
import csv
import re
from datetime import date, datetime, timedelta
from pathlib import Path

DAYS = 90


def history_dir():
    return Path.home() / 'SDS100Monitor' / 'history'


def _hz(text):
    match = re.search(r'\d+(?:\.\d+)?', str(text or ''))
    if not match:
        return None
    value = float(match.group(0))
    hz = value * 1_000_000 if value < 2000 else value
    return int(round(hz / 100.0)) * 100 if 25_000_000 <= hz <= 1_300_000_000 else None


def _tgid(text):
    match = re.search(r'\d+', str(text or ''))
    return match.group(0).lstrip('0') or '0' if match else None


class Activity:
    def __init__(self):
        self.talkgroups = {}            # (system casefold, tgid) -> [count, seconds, last datetime]
        self.frequencies = {}           # hz -> [count, seconds, last datetime]
        self.days = DAYS
        self.files = 0

    def _add(self, table, key, seconds, when):
        entry = table.setdefault(key, [0, 0.0, None])
        entry[0] += 1
        entry[1] += seconds
        if when and (entry[2] is None or when > entry[2]):
            entry[2] = when

    def lookup(self, system_name, row):
        """(count, seconds, last heard) for a TGID or C-Freq row of a Favorites List; zeros if never heard."""
        kind = row[0] if row else ''
        found = None
        if kind == 'TGID' and len(row) > 5:
            found = self.talkgroups.get((str(system_name or '').strip().casefold(), _tgid(row[5])))
        elif kind == 'C-Freq' and len(row) > 5:
            found = self.frequencies.get(_hz(row[5]))
        return tuple(found) if found else (0, 0.0, None)


def load(days=DAYS, folder=None, today=None):
    """Activity of the last `days` days (an empty Activity when the Monitor has no history here)."""
    activity = Activity()
    activity.days = days
    folder = Path(folder or history_dir())
    today = today or date.today()
    first = today - timedelta(days=days - 1)
    for path in sorted(folder.glob('reception_history_????-??-??.csv')) if folder.is_dir() else []:
        try:
            day = date.fromisoformat(path.stem.rsplit('_', 1)[1])
        except ValueError:
            continue
        if not first <= day <= today:
            continue
        activity.files += 1
        try:
            with path.open(newline='', encoding='utf-8-sig') as stream:
                for record in csv.DictReader(stream):
                    try:
                        seconds = float(record.get('Duration (s)') or 0)
                    except ValueError:
                        seconds = 0.0
                    try:
                        when = datetime.fromisoformat(str(record.get('Start') or '').strip())
                    except ValueError:
                        when = None
                    tgid = _tgid(record.get('Talkgroup'))
                    system = str(record.get('System') or '').strip().casefold()
                    if tgid and system:
                        activity._add(activity.talkgroups, (system, tgid), seconds, when)
                    else:
                        hz = _hz(record.get('Frequency'))
                        if hz:
                            activity._add(activity.frequencies, hz, seconds, when)
        except (OSError, csv.Error, UnicodeDecodeError):
            continue
    return activity


def columns(activity, system_name, row):
    """('12', '2026-11-05') for the list editor; ('0', 'not heard') when never heard."""
    count, _seconds, last = activity.lookup(system_name, row)
    return str(count), (last.strftime('%Y-%m-%d %H:%M') if last else 'not heard')
