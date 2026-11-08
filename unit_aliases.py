# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Unit ID names from SDS100 Monitor onto the scanner's trunked systems (v0.1.19).

The Monitor keeps the names you gave radios in ~/SDS100Monitor/unit_names.csv (Unit ID, Name, Status,
Notes, Updated) and logs which system each unit was heard on in ~/SDS100Monitor/unit_ids/unit_ids_*.csv
(Time, Unit ID, Unit Name, System, ...). A trunked system in a Favorites List keeps its unit names as
UnitIds rows (SDS Series File Specification v2.00):

    UnitIds  Reserve  Reserve  NameTag  UnitID  AlertTone  AlertVolume  AlertColor  AlertPattern

The specification doesn't say exactly where these rows sit or what the scanner puts in the reserved
columns, so new rows are only ever copied from a UnitIds row the scanner itself wrote in the same
system: same column count, same reserved fields (an "X=n" record ID becomes the new-record "X=0"),
same alert settings, placed straight after the system's last UnitIds row. A system with no UnitIds row
yet is reported, not guessed at. The Monitor's files are only read. Pure; no Qt.
"""
import csv
import re
from pathlib import Path

MAX_UNIT = 16777215
NAME_LIMIT = 64
ALERT_TONES = ('Off',) + tuple(str(n) for n in range(1, 10))
ALERT_VOLUMES = ('Auto',) + tuple(str(n) for n in range(1, 16))
ALERT_COLORS = ('Off', 'Blue', 'Red', 'Magenta', 'Green', 'Cyan', 'Yellow', 'White')
ALERT_PATTERNS = ('On', 'Slow', 'Fast')


def monitor_dir():
    return Path.home() / 'SDS100Monitor'


def unit_number(text):
    """'UID:1234567' / '1234567' -> 1234567; None for anything that isn't a radio ID the scanner takes."""
    text = str(text or '').strip()
    text = re.sub(r'^(?:UID|UNIT|RID)\s*[:=]?\s*', '', text, flags=re.I)
    if not (text.isascii() and text.isdecimal()):
        return None
    value = int(text)
    return value if 1 <= value <= MAX_UNIT else None


def clean_name(text):
    name = ' '.join(''.join(ch if ord(ch) >= 32 and ord(ch) != 127 else ' ' for ch in str(text or '')).split())
    try:
        name.encode('cp1252')
    except UnicodeEncodeError:
        name = name.encode('cp1252', 'replace').decode('cp1252').replace('?', '')
    return name[:NAME_LIMIT].strip()


def load_names(folder=None, guesses=False):
    """{unit: name} from the Monitor's unit names (Confirmed only unless guesses=True)."""
    path = Path(folder or monitor_dir()) / 'unit_names.csv'
    names = {}
    try:
        with path.open(newline='', encoding='utf-8-sig') as stream:
            for record in csv.DictReader(stream):
                unit, name = unit_number(record.get('Unit ID')), clean_name(record.get('Name'))
                status = str(record.get('Status') or 'Confirmed').strip().casefold()
                if unit and name and (guesses or status != 'guess'):
                    names[unit] = name
    except (OSError, csv.Error, UnicodeDecodeError):
        pass
    return names


def load_systems(folder=None):
    """{unit: {system name casefolded, ...}} from the Monitor's unit ID logs."""
    systems = {}
    for path in sorted((Path(folder or monitor_dir()) / 'unit_ids').glob('unit_ids_????-??-??.csv')):
        try:
            with path.open(newline='', encoding='utf-8-sig') as stream:
                for record in csv.DictReader(stream):
                    unit, system = unit_number(record.get('Unit ID')), str(record.get('System') or '').strip()
                    if unit and system:
                        systems.setdefault(unit, set()).add(system.casefold())
        except (OSError, csv.Error, UnicodeDecodeError):
            continue
    return systems


def _new_marker(value):
    match = re.fullmatch(r'([A-Za-z]+)=\d+', value or '')
    return match.group(1) + '=0' if match else value


def _system_spans(records):
    """[(start, end)] of every Trunk system in an entry's records."""
    spans, start = [], None
    for index, row in enumerate(records):
        if row and row[0] in ('Trunk', 'Conventional'):
            if start is not None:
                spans.append((start, index))
            start = index if row[0] == 'Trunk' else None
    if start is not None:
        spans.append((start, len(records)))
    return spans


def plan(drafts, names, systems, rename=True):
    """What adding the Monitor's unit names would do.

    drafts: the editor's entries ({'records': [...]}, one per system or list).
    Returns {'add': [(entry index, after record index, row)], 'rename': [(entry index, record index, name)],
             'no_template': [system name], 'systems': {system name: count}, 'skipped': int}."""
    result = {'add': [], 'rename': [], 'no_template': [], 'systems': {}, 'skipped': 0}
    for entry_index, entry in enumerate(drafts):
        records = entry.get('records') or []
        for start, end in _system_spans(records):
            header = records[start]
            system = header[3].strip() if len(header) > 3 else ''
            units = sorted(u for u, heard in systems.items() if u in names and system.casefold() in heard)
            if not units:
                continue
            existing = {}
            last = None
            for index in range(start + 1, end):
                row = records[index]
                if row and row[0] == 'UnitIds' and len(row) >= 9:
                    last = index
                    number = unit_number(row[4])
                    if number:
                        existing[number] = index
            if last is None:
                if system not in result['no_template']:
                    result['no_template'].append(system)
                continue
            template = records[last]
            count = 0
            for unit in units:
                name = names[unit]
                if unit in existing:
                    row = records[existing[unit]]
                    if rename and row[3] != name:
                        result['rename'].append((entry_index, existing[unit], name))
                        count += 1
                    else:
                        result['skipped'] += 1
                    continue
                row = list(template)
                row[1], row[2] = _new_marker(template[1]), _new_marker(template[2])
                row[3], row[4] = name, str(unit)
                result['add'].append((entry_index, last, row))
                count += 1
            if count:
                result['systems'][system] = result['systems'].get(system, 0) + count
    return result


def apply(drafts, result):
    """Make the planned changes (insert from the bottom up so record indices stay valid). Returns count."""
    for entry_index, index, name in result['rename']:
        drafts[entry_index]['records'][index][3] = name
    # bottom up so earlier indices stay valid; reversed so rows after one template end up in unit order
    for entry_index, after, row in reversed(sorted(result['add'], key=lambda a: (a[0], a[1]))):
        drafts[entry_index]['records'].insert(after + 1, [*row])
    return len(result['add']) + len(result['rename'])


def summary(result):
    lines = []
    for system, count in sorted(result['systems'].items()):
        lines.append(f'{system}: {count} unit name(s)')
    if result['add'] or result['rename']:
        lines.insert(0, f"Add {len(result['add'])} and rename {len(result['rename'])} unit ID(s):")
    if result['skipped']:
        lines.append(f"{result['skipped']} unit(s) are already there with the same name.")
    if result['no_template']:
        lines.append('')
        lines.append('No unit IDs yet in: ' + ', '.join(result['no_template']) + '.')
        lines.append('The file format doesn\'t fully say how the scanner stores unit IDs, so SDS-Manager copies '
                     'one the scanner wrote. On the SDS100, add one unit ID to that system (menu → Manage '
                     'Favorites → the list → the system → Edit Unit IDs → New Unit ID), read the configuration '
                     'from the scanner again, then run this again.')
    return '\n'.join(lines)


def row_problem(row):
    """None if a UnitIds row is well formed (v0.1.19 export check), else the reason."""
    if len(row) < 9:
        return 'UnitIds has %d columns, expected 9' % len(row)
    if not row[3].strip() or len(row[3]) > NAME_LIMIT:
        return 'invalid unit name'
    if unit_number(row[4]) is None or row[4] != str(unit_number(row[4])):
        return 'invalid unit ID %r' % row[4]
    if row[5] not in ALERT_TONES or row[6] not in ALERT_VOLUMES:
        return 'invalid unit alert tone/volume'
    return None
