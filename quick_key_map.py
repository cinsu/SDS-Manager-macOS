# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""What each quick key is assigned to (v0.1.6).

The SDS100 has three levels of quick keys, each numbered 00-99, and each with an On/Off status:

  Favorites List quick keys   status: profile.cfg QuickKeys (one set for the whole scanner)
                              assigned: each list's Quick Key in favorites_lists/f_list.cfg
  System quick keys           status: the list's own row in f_list.cfg (one set per Favorites List)
                              assigned: each system's Quick Key in the list's .hpd file (system header)
  Department quick keys       status: the system's DQKs_Status line in the .hpd (one set per system)
                              assigned: each department's Quick Key (C-Group / T-Group row)

Turning a key Off stops the scanner scanning everything assigned to that key; items without a key
are not affected by any key. Pure functions, no I/O.
"""

FL, SYSTEM, DEPARTMENT = 'Favorites List', 'System', 'Department'
HEADER_KEY, DEPARTMENT_KEY = 7, 9                  # columns in the .hpd rows (conventional system, department)
SYSTEM_KEY = {'Conventional': 7, 'Trunk': 12}       # a trunked system's quick key is column 12 (v0.1.17)


def key_number(value):
    """0-99 from a quick-key field, or None for 'Off' / blank / anything else."""
    text = str(value or '').strip()
    return int(text) if text.isdecimal() and 0 <= int(text) <= 99 else None


def key_label(number):
    return 'none' if number is None else f'{number:02d}'


def read_systems(rows):
    """[{'name', 'kind', 'type', 'key', 'status' [100 bools] or None, 'departments': [{'name', 'kind', 'key'}]}]
    from the rows of a Favorites List (.hpd split into fields)."""
    systems = []
    for row in rows:
        kind = row[0].strip() if row else ''
        if kind in ('Conventional', 'Trunk'):
            systems.append({'name': row[3] if len(row) > 3 else kind, 'kind': kind,
                            'type': row[6] if len(row) > 6 else '',
                            'key': key_number(row[SYSTEM_KEY[kind]]) if len(row) > SYSTEM_KEY[kind] else None,
                            'status': None, 'departments': []})
        elif not systems:
            continue
        elif kind == 'DQKs_Status':
            values = row[2:102]
            if len(values) == 100 and all(v in ('On', 'Off') for v in values):
                systems[-1]['status'] = [v == 'On' for v in values]
        elif kind == 'Site' and len(row) > 16 and key_number(row[16]) is not None:   # shares department keys (v0.1.22)
            systems[-1]['departments'].append({'name': (row[3] if len(row) > 3 else kind) + ' (site)', 'kind': kind,
                                               'key': key_number(row[16])})
        elif kind in ('C-Group', 'T-Group'):
            systems[-1]['departments'].append({
                'name': row[3] if len(row) > 3 else kind, 'kind': kind,
                'key': key_number(row[DEPARTMENT_KEY]) if len(row) > DEPARTMENT_KEY else None})
    return systems


def owners(items):
    """{key: [names]} for items with a 'key' and a 'name'."""
    found = {}
    for item in items:
        if item.get('key') is not None:
            found.setdefault(item['key'], []).append(item['name'])
    return found


def state(key, statuses):
    """Plain words for an item's key: what the scanner does with it."""
    if key is None:
        return 'No quick key: not switched by any key'
    if statuses is None:
        return f'Key {key:02d}'
    return f'Key {key:02d} is On: scanned' if statuses[key] else f'Key {key:02d} is Off: not scanned'


def key_rows(statuses, assigned):
    """For a grid of 100 keys: [(number, on, [names])]."""
    return [(n, bool(statuses[n]) if statuses else False, list(assigned.get(n, []))) for n in range(100)]


def shared(assigned):
    """Keys used by more than one item at the same level: {key: [names]}."""
    return {k: v for k, v in assigned.items() if len(v) > 1}


def summary(statuses, assigned):
    """One line: how many keys are used, On and Off."""
    used = sorted(assigned)
    on = sum(1 for k in used if statuses and statuses[k])
    spare_on = sum(1 for n in range(100) if statuses and statuses[n] and n not in assigned)
    text = f'{len(used)} key(s) assigned: {on} On, {len(used) - on} Off.'
    if spare_on:
        text += f' {spare_on} unassigned key(s) are On; that does nothing until something uses them.'
    return text
