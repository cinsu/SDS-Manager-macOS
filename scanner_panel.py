# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""What the Scanner panel and status bar say (pure Python, so the wording and the warnings are testable)."""
from datetime import datetime
import re

from scanner_detect import human_bytes

OK, NOTE, WARN = 'ok', 'note', 'warn'
ARCHIVE = re.compile(r'MasterHpdb_(\d{2})_(\d{2})_(\d{4})(?:\.gz)?')


def _date(d):
    return d.strftime('%m/%d/%Y') if d else 'unknown'


def panel_rows(info, local_date=None, backups=None, backup_warn_mb=2000, configuration=None):
    """[(label, value, severity)] for the panel.  info is scanner_detect.summarize() or None when not connected."""
    rows = []
    if info is None:
        rows.append(('Scanner', 'Not connected', NOTE))
    else:
        model = ' '.join(x for x in (info.get('model'), info.get('firmware') and 'firmware ' + info['firmware']) if x)
        rows.append(('Scanner', model or 'SD card detected (model unknown)', OK))
        scanner_date = info.get('database_date')
        severity = OK
        text = _date(scanner_date)
        if scanner_date and local_date:
            if local_date.date() > scanner_date.date():
                severity, text = NOTE, text + '  (a newer database is available locally)'
            elif local_date.date() < scanner_date.date():
                severity, text = WARN, text + '  (newer than your local database)'
        elif scanner_date is None:
            severity = WARN
        rows.append(('Database on scanner', text, severity))
        free = info.get('free_bytes')
        rows.append(('Free space', human_bytes(free) + (f' of {human_bytes(info.get("total_bytes"))}' if info.get('total_bytes') else ''),
                     WARN if free is not None and free < 64 * 1024 * 1024 else OK))
        if info.get('favorites_lists') is not None:
            rows.append(('Favorites lists on scanner', str(info['favorites_lists']), OK))
    rows.append(('Newest local database', _date(local_date) if local_date else 'none rebuilt yet',
                 NOTE if local_date is None else OK))
    if backups is not None:
        if backups['count']:
            text = f'{backups["count"]} backups, {human_bytes(backups["bytes"])}; newest {_stamp(backups["newest"])}'
            heavy = backups['bytes'] > backup_warn_mb * 1024 * 1024
            rows.append(('Backups', text + ('  (large: consider cleaning up)' if heavy else ''), WARN if heavy else OK))
        else:
            rows.append(('Backups', 'none yet (one is made automatically before every scanner write)', NOTE))
    rows.append(('Open configuration', configuration or 'none open', NOTE if not configuration else OK))
    return rows


def _stamp(name):
    try:
        return datetime.strptime(name[:16], '%Y%m%dT%H%M%SZ').strftime('%m/%d/%Y')
    except (TypeError, ValueError):
        return name or 'unknown'


def status_text(info):
    """Short text for the status bar."""
    if info is None:
        return 'Scanner: not connected'
    model = info.get('model') or 'SD card'
    date = info.get('database_date')
    return f'Scanner: {model} connected' + (f' • database {_date(date)}' if date else '')


def archive_date(name):
    m = ARCHIVE.fullmatch(name)
    if not m:
        return None
    try:
        return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    except ValueError:
        return None


def newest_archive(names):
    """(name, date) of the newest dated Uniden archive in names, or None."""
    dated = [(archive_date(n), n) for n in names]
    dated = [d for d in dated if d[0]]
    if not dated:
        return None
    date, name = max(dated)
    return name, date


def update_message(archive_names, local_date, scanner_date):
    """Text for 'a newer database is available', or None when nothing newer exists."""
    newest = newest_archive(archive_names)
    if newest is None:
        return None
    name, date = newest
    reference = max([d for d in (local_date, scanner_date) if d], default=None)
    if reference is not None and date.date() <= reference.date():
        return None
    return f'A newer Uniden database is available ({date:%m/%d/%Y}). Use Database → Update Database.'
