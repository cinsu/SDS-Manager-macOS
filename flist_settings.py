# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Per-list settings stored in favorites_lists/f_list.cfg (one F-List row per Favorites List).

Row layout, positions one-based after the keyword (Uniden SDS Series File Specification V2.00;
a real SDS100 row also ends with one empty trailing field):

   1 UserName            2 Filename (fixed)       3 Location Control On/Off   4 Monitor On/Off
   5 Quick Key Off/0-99  6 Number Tag Off/0-99    7-16 Startup Key 0-9 On/Off
   17-116 System Quick Key 00-99 status On/Off

The row order, filenames, field count and trailing field never change here.  Two lists may not
share a quick key or a number tag.  Pure functions, no I/O.
"""
import re

ONOFF = ('Off', 'On')
FIELD_COUNT = 116
NAME_MAX = 64
_NUMBER = re.compile(r'0|[1-9][0-9]?')
POS_NAME, POS_FILE, POS_LOCATION, POS_MONITOR, POS_QUICK, POS_TAG = 1, 2, 3, 4, 5, 6
POS_STARTUP = range(7, 17)
POS_SQK = range(17, 117)
EDITABLE = {POS_NAME, POS_LOCATION, POS_MONITOR, POS_QUICK, POS_TAG, *POS_STARTUP, *POS_SQK}


def valid_value(position, value):
    """True if value is acceptable at this one-based position."""
    if not isinstance(value, str) or not value.isascii() or any(c in value for c in '\t\r\n\x00'):
        return False
    if position == POS_NAME:
        return 0 < len(value) <= NAME_MAX and value == value.strip() and all(' ' <= c <= '~' for c in value)
    if position in (POS_LOCATION, POS_MONITOR) or position in POS_STARTUP or position in POS_SQK:
        return value in ONOFF
    if position in (POS_QUICK, POS_TAG):
        return value == 'Off' or (bool(_NUMBER.fullmatch(value)) and 0 <= int(value) <= 99)
    return False


def _split(line):
    return line.split('\t')


def row_problem(fields):
    """None when a split F-List row has the expected layout, else a reason."""
    body = list(fields)
    trailing = 0
    while body and body[-1] == '':
        body.pop()
        trailing += 1
    if len(body) != FIELD_COUNT + 1 or body[0] != 'F-List' or trailing > 1:
        return 'unexpected f_list.cfg row layout'
    return None


def read_lists(raw):
    """[{filename, name, location, monitor, quick_key, number_tag, startup[10], system_keys[100]}]."""
    out = []
    for line in raw.decode('cp1252').splitlines():
        if not line.startswith('F-List\t'):
            continue
        fields = _split(line)
        problem = row_problem(fields)
        if problem:
            raise ValueError(problem)
        out.append({'filename': fields[POS_FILE], 'name': fields[POS_NAME], 'location': fields[POS_LOCATION],
                    'monitor': fields[POS_MONITOR], 'quick_key': fields[POS_QUICK], 'number_tag': fields[POS_TAG],
                    'startup': fields[7:17], 'system_keys': fields[17:117]})
    return out


def edits_between(old_lists, new_lists):
    """{(filename, position): value} turning old_lists into new_lists (same lists, same order)."""
    if [l['filename'] for l in old_lists] != [l['filename'] for l in new_lists]:
        raise ValueError('The set or order of Favorites Lists cannot change here.')
    edits = {}
    for old, new in zip(old_lists, new_lists):
        flat_old = [old['name'], old['filename'], old['location'], old['monitor'], old['quick_key'],
                    old['number_tag']] + list(old['startup']) + list(old['system_keys'])
        flat_new = [new['name'], new['filename'], new['location'], new['monitor'], new['quick_key'],
                    new['number_tag']] + list(new['startup']) + list(new['system_keys'])
        for index, (a, b) in enumerate(zip(flat_old, flat_new), 1):
            if a != b:
                edits[(old['filename'], index)] = b
    return edits


def check_edits(old_lists, edits):
    """Validate edits against the resulting full set of lists. Raises ValueError with the reason."""
    known = {l['filename'].lower() for l in old_lists}
    for (filename, position), value in edits.items():
        if filename.lower() not in known:
            raise ValueError('No Favorites List %s in the index.' % filename)
        if position not in EDITABLE:
            raise ValueError('Field %d of the list index is not editable.' % position)
        if not valid_value(position, value):
            raise ValueError('%s: invalid value %r for field %d.' % (filename, value, position))
    final = []
    for l in old_lists:
        row = _flat(l)
        for (filename, position), value in edits.items():
            if filename.lower() == l['filename'].lower():
                row[position - 1] = value
        final.append((l['filename'], row))
    changed_quick = {f for (f, p) in edits if p == POS_QUICK}
    changed_tag = {f for (f, p) in edits if p == POS_TAG}
    changed_name = {f for (f, p) in edits if p == POS_NAME}
    for position, label, changed in ((POS_QUICK, 'quick key', changed_quick), (POS_TAG, 'number tag', changed_tag)):
        seen = {}
        for filename, row in final:
            value = row[position - 1]
            if value != 'Off':
                seen.setdefault(value, []).append(filename)
        for value, owners in seen.items():
            if len(owners) > 1 and any(o in changed for o in owners):
                raise ValueError('Two lists would share %s %s (%s).' % (label, value, ', '.join(owners)))
    seen_names = {}
    for filename, row in final:
        seen_names.setdefault(row[0].casefold(), []).append(filename)
    for name, owners in seen_names.items():
        if len(owners) > 1 and any(o in changed_name for o in owners):
            raise ValueError('Two lists would have the same name (%s).' % ', '.join(owners))


def _flat(l):
    return [l['name'], l['filename'], l['location'], l['monitor'], l['quick_key'], l['number_tag']] \
        + list(l['startup']) + list(l['system_keys'])


def patch_lists(raw, edits):
    """Apply validated edits to f_list.cfg bytes, changing nothing else (order, endings, trailing field)."""
    if not edits:
        raise ValueError('No edits.')
    check_edits(read_lists(raw), edits)
    text = raw.decode('cp1252')
    by_file = {}
    for (filename, position), value in edits.items():
        by_file.setdefault(filename.lower(), {})[position] = value
    out = []
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip('\r\n')
        ending = line[len(stripped):]
        if stripped.startswith('F-List\t'):
            fields = stripped.split('\t')
            for position, value in by_file.get(fields[POS_FILE].lower(), {}).items():
                fields[position] = value
            line = '\t'.join(fields) + ending
        out.append(line)
    result = ''.join(out).encode('cp1252')
    verify = {(f.lower(), p): v for (f, p), v in edits_between(read_lists(raw), read_lists(result)).items()}
    if verify != {(f.lower(), p): v for (f, p), v in edits.items()}:
        raise ValueError('Round-trip verification failed.')
    return result


def describe(old_lists, edits):
    names = {l['filename'].lower(): l for l in old_lists}
    labels = {POS_NAME: 'Name', POS_LOCATION: 'Location Control', POS_MONITOR: 'Monitor',
              POS_QUICK: 'Quick Key', POS_TAG: 'Number Tag'}
    lines = []
    for (filename, position), value in sorted(edits.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        row = _flat(names[filename.lower()])
        if position in labels:
            label = labels[position]
        elif position in POS_STARTUP:
            label = 'Startup Key %d' % (position - 7)
        else:
            label = 'System Quick Key %02d' % (position - 17)
        lines.append('%s (%s) — %s: %r → %r' % (row[0], filename, label, row[position - 1], value))
    return tuple(lines)
