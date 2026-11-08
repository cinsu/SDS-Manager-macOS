# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Avoids made on the scanner (or from SDS100 Monitor) kept at Export to Scanner (v0.1.21).

A permanent avoid set on the SDS100 itself, or from SDS100 Monitor (AVD … status 1), is written by the
scanner into its own Favorites List file, in the Avoid column (index 4) of the system, site, department,
channel or talkgroup line. A configuration saved earlier still has the old value, so exporting it would
quietly undo those avoids. Before an export, the scanner's avoids are compared with the configuration's:

- lines are matched by where they are (system › department › name and frequency or TGID), because the
  scanner leaves the record ID columns empty;
- when SDS-Manager knows the avoids at the time scanner and configuration last matched (export-state.json,
  v0.1.21), a difference where only the scanner changed is marked as made on the scanner (suggested);
  where only the configuration changed, it's your edit in SDS-Manager and is exported as it is.

Pure apart from reading the files; no Qt. Applying writes the configuration through its checked commit.
"""
import json
import re
from pathlib import Path

AVOID = 4
SYSTEMS = ('Conventional', 'Trunk')
GROUPS = ('Site', 'C-Group', 'T-Group')
LEAVES = ('C-Freq', 'TGID')
WORDS = {'Conventional': 'system', 'Trunk': 'system', 'Site': 'site', 'C-Group': 'department',
         'T-Group': 'department', 'C-Freq': 'channel', 'TGID': 'talkgroup'}


def _rows(raw):
    text = raw.decode('utf-8-sig') if raw.startswith(b'\xef\xbb\xbf') else raw.decode('cp1252')
    return [line.split('\t') for line in text.splitlines()]


def avoid_map(raw):
    """{key: (line number, avoid, label)} for every line that has an Avoid column."""
    found, seen = {}, {}
    system = group = ''
    for number, row in enumerate(_rows(raw)):
        kind = row[0] if row else ''
        if kind not in SYSTEMS + GROUPS + LEAVES or len(row) <= AVOID:
            continue
        name = row[3].strip() if len(row) > 3 else ''
        if kind in SYSTEMS:
            system, group = f'{kind}:{name}', ''
            path, label = system, name
        elif kind in GROUPS:
            group = f'{kind}:{name}'
            path, label = f'{system} / {group}', f'{system.split(":", 1)[1]} › {name}'
        else:
            value = row[5].strip() if len(row) > 5 else ''
            path = f'{system} / {group} / {kind}:{name}={value}'
            shown = f'{int(value) / 1e6:.4f} MHz' if kind == 'C-Freq' and value.isdecimal() else f'TGID {value}'
            label = f'{system.split(":", 1)[1]} › {group.split(":", 1)[-1]} › {name} ({shown})'
        seen[path] = seen.get(path, 0) + 1
        key = path if seen[path] == 1 else f'{path} #{seen[path]}'
        found[key] = (number, row[AVOID], f'{WORDS[kind].capitalize()} {label}')
    return found


def _list_names(folder):
    names = {}
    try:
        text = (Path(folder) / 'f_list.cfg').read_bytes().decode('cp1252')
    except (OSError, UnicodeError):
        return names
    for line in text.splitlines():
        fields = line.split('\t')
        if fields[0] == 'F-List' and len(fields) > 2:
            for value in fields:
                if re.fullmatch(r'f_\d{6}\.hpd', value or '', re.I):
                    names[value.lower()] = fields[1] or value
    return names


def configuration_avoids(configuration):
    """{filename: {key: avoid}} of a configuration, for export-state.json."""
    result = {}
    for path in sorted((Path(configuration) / 'BCDx36HP' / 'favorites_lists').glob('*.hpd')):
        try:
            result[path.name.lower()] = {k: v[1] for k, v in avoid_map(path.read_bytes()).items()}
        except (OSError, UnicodeError):
            continue
    return result


def differences(configuration, scanner_folder, base=None):
    """Every line whose Avoid differs between the scanner and the configuration.

    scanner_folder: the scanner's BCDx36HP folder. base: {filename: {key: avoid}} from when they last
    matched, or None. Each difference: {'file', 'list', 'key', 'label', 'scanner', 'configuration',
    'made_on': 'scanner' | 'SDS-Manager' | ''}."""
    found = []
    config_lists = Path(configuration) / 'BCDx36HP' / 'favorites_lists'
    scanner_lists = Path(scanner_folder) / 'favorites_lists'
    names = _list_names(config_lists)
    for path in sorted(config_lists.glob('*.hpd')):
        other = scanner_lists / path.name
        if not other.is_file():
            continue
        try:
            mine, theirs = avoid_map(path.read_bytes()), avoid_map(other.read_bytes())
        except (OSError, UnicodeError):
            continue
        before = (base or {}).get(path.name.lower(), {}) if base is not None else None
        for key, (_number, scanner_value, label) in theirs.items():
            if key not in mine or mine[key][1] == scanner_value:
                continue
            made = ''
            if before is not None and key in before:
                if before[key] == mine[key][1]:
                    made = 'scanner'
                elif before[key] == scanner_value:
                    made = 'SDS-Manager'
            found.append({'file': path.name, 'list': names.get(path.name.lower(), path.name), 'key': key,
                          'label': label, 'scanner': scanner_value, 'configuration': mine[key][1], 'made_on': made})
    return found


def describe(item):
    state = {'On': 'avoided', 'Off': 'not avoided'}
    return '%s: %s — scanner %s, configuration %s%s' % (
        item['list'], item['label'], state.get(item['scanner'], item['scanner']),
        state.get(item['configuration'], item['configuration']),
        {'scanner': ' (changed on the scanner)', 'SDS-Manager': ' (changed in SDS-Manager)'}.get(item['made_on'], ''))


def new_bytes(raw, changes):
    """raw with Avoid set per {line number: value}, line endings and everything else kept."""
    lines = raw.split(b'\n')
    for number, value in changes.items():
        line = lines[number]
        end = b'\r' if line.endswith(b'\r') else b''
        fields = (line[:-1] if end else line).split(b'\t')
        fields[AVOID] = value.encode('cp1252')
        lines[number] = b'\t'.join(fields) + end
    return b'\n'.join(lines)


def keep_scanner_avoids(configuration, chosen):
    """Copy the chosen scanner avoids into the configuration (one checked commit). Returns how many."""
    from scanner_configurations import _commit_files
    root = Path(configuration)
    manifest = json.loads((root / 'configuration.json').read_text(encoding='utf-8'))
    writes = {}
    by_file = {}
    for item in chosen:
        by_file.setdefault(item['file'], []).append(item)
    count = 0
    for filename, items in by_file.items():
        relative = f'BCDx36HP/favorites_lists/{filename}'
        raw = (root / relative).read_bytes()
        lines = avoid_map(raw)
        changes = {lines[i['key']][0]: i['scanner'] for i in items if i['key'] in lines}
        if changes:
            writes[relative] = new_bytes(raw, changes)
            count += len(changes)
    if writes:
        _commit_files(root, manifest, writes)
    return count
