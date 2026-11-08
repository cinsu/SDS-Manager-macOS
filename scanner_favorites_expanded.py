# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Validate bounded changes to an EXISTING native Favorites HPD before scanner export.

Accepted: existing leaf field edits and names, and insertion/deletion of individual
C-Freq, T-Freq or TGID records. Other records/opaque data cannot be changed.
This is a format/scope guard, not a substitute for testing scanner acceptance.
"""
from difflib import SequenceMatcher
from native_favorites_field_patch import _valid_field, NativePatchError

MAX_BYTES = 25 * 1024 * 1024
MAX_ROWS = 100_000
LEAF_PARENT = {'C-Freq': 'C-Group', 'T-Freq': 'Site', 'TGID': 'T-Group'}
WIDTHS = {'C-Freq': (18,), 'T-Freq': (8, 9), 'TGID': (17,)}
GROUPS = {'C-Group', 'Site', 'T-Group'}
SYSTEMS = {'Trunk', 'Conventional'}
# Quick key and number tag fields and their highest number (v0.1.13).
NUMBER_FIELDS = {('Trunk', 12): 99, ('Conventional', 7): 99, ('Trunk', 13): 99, ('Conventional', 8): 99,
                 ('C-Group', 9): 99, ('T-Group', 9): 99, ('Site', 16): 99, ('C-Freq', 16): 999, ('TGID', 14): 999}


def _records(raw):
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError('Native HPD is empty or exceeds 25 MiB')
    if any(ch in raw for ch in (b'\x00', b'\x0b', b'\x0c')):
        raise ValueError('Unsupported control character in native HPD')
    text = raw.decode('utf-8-sig') if raw.startswith(b'\xef\xbb\xbf') else raw.decode('cp1252')
    rows = [line.split('\t') for line in text.splitlines()]
    if len(rows) > MAX_ROWS or any(not row or not row[0] for row in rows):
        raise ValueError('Missing record type or too many native records')
    if any(any(any(ord(ch) < 32 or ord(ch) == 127 for ch in field) for field in row) for row in rows):
        raise ValueError('Unsupported native field control character')
    return rows


def _preamble(rows):
    first = next((i for i, row in enumerate(rows) if row[0] in SYSTEMS), len(rows))
    head = rows[:first]
    if not any(row[:2] == ['TargetModel', 'BCDx36HP'] for row in head):
        raise ValueError('Native HPD target header is missing or incorrect')
    if not any(row[0] == 'FormatVersion' and len(row) > 1 and row[1] for row in head):
        raise ValueError('Native HPD format version is missing')
    if first == len(rows):
        raise ValueError('Native HPD has no systems')
    return head


def _hierarchy(rows):
    """Return leaf parent indices; reject orphan leaves, mismatched parent IDs and empty sites."""
    system = group = None
    parents = {}
    site_counts = {}
    for i, row in enumerate(rows):
        kind = row[0]
        if kind in SYSTEMS:
            system, group = kind, None
        elif kind in GROUPS:
            if (kind == 'C-Group' and system != 'Conventional') or (kind in ('Site', 'T-Group') and system != 'Trunk'):
                raise ValueError(f'Line {i+1}: {kind} is outside its native system')
            group = (kind, i, row[1] if len(row) > 1 else '')
            if kind == 'Site':
                site_counts[i] = 0
        elif kind in LEAF_PARENT:
            if not group or group[0] != LEAF_PARENT[kind]:
                raise ValueError(f'Line {i+1}: {kind} is outside its native parent')
            if len(row) not in WIDTHS[kind]:
                raise ValueError(f'Line {i+1}: {kind} has unsupported column count')
            if len(row) > 2 and row[2] and group[2] and row[2] != group[2]:
                raise ValueError(f'Line {i+1}: {kind} parent ID does not match')
            parents[i] = group[1]
            if kind == 'T-Freq':
                site_counts[group[1]] += 1
    if any(not count for count in site_counts.values()):
        raise ValueError('A trunked site would have no frequency; delete the site using its protected workflow')
    return parents


def _check_leaf(row, line):
    kind = row[0]
    if kind not in LEAF_PARENT or len(row) not in WIDTHS[kind]:
        raise ValueError(f'Line {line}: unsupported added leaf layout')
    if kind in ('C-Freq', 'T-Freq'):
        if not row[5].isascii() or not row[5].isdecimal() or not 100000 <= int(row[5]) <= 1300000000:
            raise ValueError(f'Line {line}: invalid added frequency')
    else:
        if not row[5].isascii() or not row[5].isdecimal() or not 0 <= int(row[5]) <= 16777215:
            raise ValueError(f'Line {line}: invalid added TGID')
    if kind in ('C-Freq', 'TGID'):
        if not row[3].strip() or len(row[3]) > 64 or row[4].upper() not in ('ON', 'OFF'):
            raise ValueError(f'Line {line}: invalid added name or Avoid')
        if kind == 'C-Freq' and row[6].upper() not in ('AUTO', 'AM', 'NFM', 'FM'):
            raise ValueError(f'Line {line}: invalid added modulation')
        if kind == 'TGID' and row[6].upper() not in ('ALL', 'ANALOG', 'DIGITAL'):
            raise ValueError(f'Line {line}: invalid added audio type')
    elif not row[6].isascii() or not row[6].isdecimal():
        raise ValueError(f'Line {line}: invalid added site LCN')
    # Newly inserted records must use a new-record marker, not impersonate an imported ID.
    identifier = row[1]
    expected = {'C-Freq':'CFreqId=0', 'T-Freq':'TFreqId=0', 'TGID':'TgidId=0'}[kind]
    if kind != 'T-Freq' and identifier.casefold() != expected.casefold():
        raise ValueError(f'Line {line}: added {kind} must have {expected}')


def _check_field_edit(old, new, line):
    kind = old[0]
    if len(old) != len(new) or kind != new[0] or old[1:3] != new[1:3]:
        raise ValueError(f'Line {line}: native identity, type or layout changed')
    if kind == 'DQKs_Status':          # department quick keys switched On/Off (Keys & Tags, v0.1.13)
        if any(a != b and b not in ('On', 'Off') for a, b in zip(old[2:], new[2:])):
            raise ValueError(f'Line {line}: a department quick key status must be On or Off')
        return sum(1 for a, b in zip(old, new) if a != b)
    if kind not in LEAF_PARENT and kind not in SYSTEMS | GROUPS:
        raise ValueError(f'Line {line}: editing opaque native records is not supported')
    changes = 0
    for index, (before, after) in enumerate(zip(old, new)):
        if before == after:
            continue
        if kind == 'Trunk' and index in (7, 8):  # ID Search / Alert Tone, set back by the repair (v0.1.17)
            if after not in (('On', 'Off') if index == 7 else ('Off',) + tuple(str(n) for n in range(10))):
                raise ValueError(f'Line {line}: ID Search must be On/Off and Alert Tone Off or 0–9')
        elif (kind, index) in NUMBER_FIELDS:      # quick key / number tag (Keys & Tags, v0.1.13)
            top = NUMBER_FIELDS[(kind, index)]
            if not (after == 'Off' or (after.isascii() and after.isdecimal() and int(after) <= top)):
                raise ValueError(f'Line {line}: a quick key or number tag must be Off or 0–{top}')
        elif kind in SYSTEMS | GROUPS:
            if index != 3 or not after.strip() or len(after) > 64:
                raise ValueError(f'Line {line}: only a system/site/department name may change')
        else:
            try:
                _valid_field(kind, index, after, before, len(new))
            except NativePatchError as exc:
                raise ValueError(f'Line {line}: {exc}') from exc
        changes += 1
    return changes


def assess_expanded_hpd_replacement(original, proposed):
    """Return (valid, detail, counts). No filesystem writes."""
    counts = {'field_edits': 0, 'added': 0, 'deleted': 0}
    try:
        old, new = _records(original), _records(proposed)
        if _preamble(old) != _preamble(new):
            raise ValueError('Native header/preamble changed')
        _hierarchy(old)
        new_parents = _hierarchy(new)
        if old == new:
            raise ValueError('No native record changes (only file encoding or line endings differ)')
        # Prefer positional validation when no rows were added/removed. This also
        # preserves legitimate edits to T-Freq records with blank native IDs.
        if len(old) == len(new) and all(a[0] == b[0] and a[1:3] == b[1:3] for a,b in zip(old,new)):
            def terminators(raw):
                return [b'\r\n' if line.endswith(b'\r\n') else
                        b'\n' if line.endswith(b'\n') else
                        b'\r' if line.endswith(b'\r') else b''
                        for line in raw.splitlines(keepends=True)]
            if terminators(original) != terminators(proposed):
                raise ValueError('Field-only edit unexpectedly changed native line endings')
            for i,(a,b) in enumerate(zip(old,new),1):
                if a != b:
                    counts['field_edits'] += _check_field_edit(a,b,i)
        else:
            # Match unchanged rows; structural changes must be entire leaf records.
            # Mixed structural + field changes can be saved/exported in separate steps.
            matcher = SequenceMatcher(None, [tuple(row) for row in old],
                                      [tuple(row) for row in new], autojunk=True)
            for tag, a, b, c, d in matcher.get_opcodes():
                if tag == 'equal':
                    continue
                if tag == 'replace':
                    raise ValueError('Structural and field edits or replacements are mixed; export separately')
                if tag == 'delete':
                    for index in range(a,b):
                        if old[index][0] not in LEAF_PARENT:
                            raise ValueError('Deleting a system, site, department or opaque record is not yet supported')
                        counts['deleted'] += 1
                elif tag == 'insert':
                    for index in range(c,d):
                        _check_leaf(new[index], index+1)
                        # Existing leaf in same parent must supply a template;
                        # preserve the undocumented ninth T-Freq column.
                        parent_index = new_parents[index]
                        templates = [r for j,r in enumerate(new) if j != index and
                                     new_parents.get(j) == parent_index and r[0] == new[index][0]]
                        if not templates:
                            raise ValueError('Added leaf has no existing same-parent native template')
                        allowed = {
                            'C-Freq': {1, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15, 16, 17},
                            'T-Freq': {5},
                            'TGID': {1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16},
                        }[new[index][0]]
                        if not any(len(t) == len(new[index]) and all(
                                t[k] == new[index][k] for k in range(len(t)) if k not in allowed)
                                for t in templates):
                            raise ValueError('Added leaf differs from native template in reserved/opaque fields')
                        if any(t[5] == new[index][5] for t in templates):
                            raise ValueError('Added leaf duplicates an existing frequency or TGID in its parent')
                        counts['added'] += 1
        if not any(counts.values()):
            raise ValueError('No supported changes')
        return True, (f'{counts["field_edits"]} edited field(s), '
                      f'{counts["added"]} added leaf record(s), '
                      f'{counts["deleted"]} deleted leaf record(s)'), counts
    except (ValueError, UnicodeError, IndexError) as exc:
        return False, str(exc), counts
