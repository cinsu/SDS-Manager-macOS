# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Cut, Copy and Paste between Favorites Lists (v0.1.5).

Works on the editable copies of Favorites Lists in a scanner configuration ('native-copy' drafts), whose
records are the scanner's own rows. Rows are copied verbatim, so every setting (quick keys, alerts, audio
options, locations, rectangles) travels with them. What can be copied:

- a whole system (header, sites and departments);
- a department with its channels or talkgroups; a trunked department brings its system's sites along, so it
  can start that system in a list that doesn't have it;
- selected channels (C-Freq) or talkgroups (TGID).

Pasting adds to what is there and never replaces anything: a department with the same name in the same
system takes the new channels or talkgroups, and channels or talkgroups already there are skipped.
Talkgroups only go into a trunked system of the same type (P25, DMR, ...), because their IDs are written
differently for each type.

Pure functions, no Qt; the editor shows the summary and asks before anything changes.
"""
import copy

HEADERS = ('Conventional', 'Trunk')
DEPARTMENTS = ('C-Group', 'T-Group')
BLOCKS = DEPARTMENTS + ('Site',)
LEAF_OF = {'C-Group': 'C-Freq', 'T-Group': 'TGID'}
DEPARTMENT_OF = {'C-Freq': 'C-Group', 'TGID': 'T-Group'}


class ClipboardError(ValueError):
    """The operation isn't possible; the text says why, in plain words."""


# ---- reading a system's records -----------------------------------------------------------------
def is_native(entries):
    """True for the editable copy of a Favorites List in a scanner configuration."""
    return bool(entries) and entries[0].get('scope') == 'metadata' and \
        str((entries[0].get('key') or [''])[0]).startswith('native-copy-meta')


def kind_of(row):
    return row[0].strip() if row else ''


def blocks(records):
    """[(kind, start, end)] for each site and department: its row and everything under it."""
    starts = [i for i, row in enumerate(records) if kind_of(row) in BLOCKS + HEADERS]
    found = []
    for n, start in enumerate(starts):
        kind = kind_of(records[start])
        if kind in BLOCKS:
            end = starts[n + 1] if n + 1 < len(starts) else len(records)
            found.append((kind, start, end))
    return found


def block_at(records, start):
    return next((b for b in blocks(records) if b[1] == start), None)


def system_type(records):
    """'Conventional', or the trunked system's type ('P25Standard', 'DmrOneFrequency', ...)."""
    head = records[0] if records else []
    if kind_of(head) == 'Trunk':
        return head[6] if len(head) > 6 else ''
    return kind_of(head)


def system_name(records):
    head = records[0] if records else []
    return head[3] if len(head) > 3 else ''


def same_system(a, b):
    return (system_type(a) == system_type(b) and kind_of(a[0]) == kind_of(b[0])
            and system_name(a).strip().casefold() == system_name(b).strip().casefold())


def department_count(records):
    return sum(1 for kind, *_ in blocks(records) if kind in DEPARTMENTS)


def leaf_key(row):
    """What makes two channels (frequency and tone/NAC/colour code) or talkgroups (ID) the same."""
    if kind_of(row) == 'C-Freq':
        return ('C-Freq', row[5] if len(row) > 5 else '', row[7] if len(row) > 7 else '')
    return ('TGID', row[5].strip() if len(row) > 5 else '')


def _system_part(records):
    """The system without its departments: header, quick-key line, sites and anything else."""
    skip = set()
    for kind, start, end in blocks(records):
        if kind in DEPARTMENTS:
            skip.update(range(start, end))
    return [row for i, row in enumerate(records) if i not in skip]


def _source(entries):
    meta = entries[0]
    return {'preamble': copy.deepcopy(meta.get('records', [])), 'encoding': meta.get('encoding', 'cp1252')}


# ---- copying --------------------------------------------------------------------------------------
def copy_system(entries, entry_index):
    records = entries[entry_index]['records']
    return dict(_source(entries), what='system', name=system_name(records), records=copy.deepcopy(records))


def copy_department(entries, entry_index, start):
    records = entries[entry_index]['records']
    block = block_at(records, start)
    if block is None or block[0] not in DEPARTMENTS:
        raise ClipboardError('Choose a department, or the system itself.')
    return dict(_source(entries), what='department', name=records[start][3] if len(records[start]) > 3 else '',
                system=copy.deepcopy(_system_part(records)), rows=copy.deepcopy(records[block[1]:block[2]]))


def copy_leaves(entries, entry_index, indices):
    records = entries[entry_index]['records']
    rows = [records[i] for i in sorted(set(indices)) if 0 <= i < len(records)]
    kinds = {kind_of(r) for r in rows}
    if not rows or not kinds <= set(DEPARTMENT_OF):
        raise ClipboardError('Only channels and talkgroups can be copied from this side. '
                             'Site frequencies stay with their site.')
    if len(kinds) > 1:
        raise ClipboardError('Copy channels and talkgroups separately.')
    return dict(_source(entries), what='leaves', kind=kinds.pop(), system_type=system_type(records),
                system_name=system_name(records), rows=copy.deepcopy(rows))


def describe(clip):
    if clip['what'] == 'system':
        return f'system {clip["name"]}'
    if clip['what'] == 'department':
        return f'department {clip["name"]}'
    count = len(clip['rows'])
    noun = 'channel' if clip['kind'] == 'C-Freq' else 'talkgroup'
    return f'{count} {noun}{"s" if count != 1 else ""}'


# ---- cutting -----------------------------------------------------------------------------------
def cut_check(entries, clip_what, entry_index, start=None):
    """Refuse a cut that would leave a Favorites List with nothing in it (the scanner needs one system)."""
    systems = [e for e in entries if e.get('scope') != 'metadata']
    records = entries[entry_index]['records']
    whole_system = clip_what == 'system' or (clip_what == 'department' and department_count(records) == 1)
    if whole_system and len(systems) == 1:
        raise ClipboardError('That would leave this Favorites List empty. Use Copy instead, or delete the '
                             'list from the configuration.')
    return whole_system


def remove_system(entries, entry_index):
    del entries[entry_index]


def remove_department(entries, entry_index, start):
    """Remove one department; the system goes too when it was its last department. True if it did."""
    records = entries[entry_index]['records']
    block = block_at(records, start)
    del records[block[1]:block[2]]
    if department_count(records) == 0:
        del entries[entry_index]
        return True
    _note_selection(entries[entry_index])
    return False


def remove_leaves(entries, entry_index, indices):
    records = entries[entry_index]['records']
    for i in sorted(set(indices), reverse=True):
        if kind_of(records[i]) in DEPARTMENT_OF:
            del records[i]


def _note_selection(entry):
    records = entry['records']
    if 'selected_sites' in entry:
        entry['selected_sites'] = [r[3] for r in records if kind_of(r) == 'Site' and len(r) > 3]
    if 'selected_departments' in entry:
        entry['selected_departments'] = [r[3] for r in records if kind_of(r) in DEPARTMENTS and len(r) > 3]


# ---- pasting ------------------------------------------------------------------------------------
def _check_encoding(clip, entries):
    encoding = entries[0].get('encoding', 'cp1252') if entries else 'cp1252'
    rows = clip.get('records') or (clip.get('system', []) + clip.get('rows', []))
    try:
        for row in rows:
            '\t'.join(row).encode(encoding)
    except (UnicodeError, LookupError):
        raise ClipboardError('Some names use characters this Favorites List can\'t store.') from None


def _new_entry(entries, records):
    source = entries[0].get('source_path', '') if entries else ''
    name = system_name(records)
    return {'key': ['native-copy', source, len(entries)], 'name': name, 'kind': kind_of(records[0]),
            'scope': 'system', 'parent_system': name, 'records': records, 'origin': 'native-copy'}


def _find_system(entries, like, preferred=None):
    """The entry index of the same system (name, kind and type), the selected one first."""
    order = ([preferred] if preferred is not None else []) + list(range(len(entries)))
    for i in order:
        if 0 <= i < len(entries) and entries[i].get('scope') != 'metadata' and same_system(entries[i]['records'], like):
            return i
    return None


def _system_leaf_keys(records):
    return {leaf_key(r) for r in records if kind_of(r) in DEPARTMENT_OF}


def _merge_leaves(records, start, rows, result):
    """Add rows to the department starting at start, after its last row; skip those already there.
    Talkgroups are skipped when the system has them anywhere, as when adding one by hand."""
    block = block_at(records, start)
    if kind_of(records[start]) == 'T-Group':
        have = _system_leaf_keys(records)
    else:
        have = {leaf_key(r) for r in records[block[1]:block[2]] if kind_of(r) == 'C-Freq'}
    new = []
    for row in rows:
        key = leaf_key(row)
        if key in have:
            result['skipped'] += 1
            continue
        have.add(key)
        new.append(copy.deepcopy(row))
    records[block[2]:block[2]] = new
    result['added'] += len(new)


def _merge_department(records, rows, result):
    """Merge into a department of the same name, or add the department at the end of the system."""
    name = (rows[0][3] if len(rows[0]) > 3 else '').strip().casefold()
    kind = kind_of(rows[0])
    same = [s for k, s, _e in blocks(records)
            if k == kind and len(records[s]) > 3 and records[s][3].strip().casefold() == name]
    leaves = [r for r in rows[1:] if kind_of(r) == LEAF_OF[kind]]
    if same:
        result['merged'].append(rows[0][3])
        _merge_leaves(records, same[0], leaves, result)
        return
    have = _system_leaf_keys(records) if kind == 'T-Group' else set()
    kept = [copy.deepcopy(rows[0])]
    for row in rows[1:]:
        if kind_of(row) == LEAF_OF[kind] and kind == 'T-Group' and leaf_key(row) in have:
            result['skipped'] += 1
            continue
        kept.append(copy.deepcopy(row))
    records.extend(kept)
    result['departments'].append(rows[0][3])
    result['added'] += sum(1 for r in kept if kind_of(r) == LEAF_OF[kind])


def _merge_sites(records, source, result):
    """Sites of the copied system that the list's system doesn't have (by name) go before its departments."""
    have = {records[s][3].strip().casefold() for k, s, _e in blocks(records) if k == 'Site' and len(records[s]) > 3}
    first_department = next((s for k, s, _e in blocks(records) if k in DEPARTMENTS), len(records))
    insert = []
    for kind, start, end in blocks(source):
        if kind == 'Site' and source[start][3].strip().casefold() not in have:
            insert.extend(copy.deepcopy(source[start:end]))
            result['sites'].append(source[start][3])
    records[first_department:first_department] = insert


def _paste(entries, clip, target=(None, None)):
    """Paste into a list. target: (entry index, record index) of what is selected in the list, or (None, None).
    Changes entries and returns a summary: {'system', 'new_system', 'departments', 'merged', 'sites', 'added',
    'skipped'}."""
    if not is_native(entries):
        raise ClipboardError('Paste works in the Favorites Lists of a scanner configuration.')
    _check_encoding(clip, entries)
    entry_index, record_index = target if target else (None, None)
    if entry_index is not None and not (0 <= entry_index < len(entries)) or \
            entry_index is not None and entries[entry_index].get('scope') == 'metadata':
        entry_index, record_index = None, None
    result = {'system': '', 'new_system': False, 'departments': [], 'merged': [], 'sites': [], 'added': 0,
              'skipped': 0}

    if clip['what'] == 'leaves':
        if entry_index is None or record_index is None:
            raise ClipboardError(f'Select the department to paste the {describe(clip)} into.')
        records = entries[entry_index]['records']
        wanted = DEPARTMENT_OF[clip['kind']]
        if kind_of(records[record_index]) != wanted:
            raise ClipboardError('Channels go into a conventional department, talkgroups into a talkgroup department.')
        if clip['kind'] == 'TGID' and system_type(records) != clip['system_type']:
            raise ClipboardError(f'These talkgroups are from a {clip["system_type"]} system and can only go into '
                                 f'a {clip["system_type"]} system; this one is {system_type(records)}.')
        result['system'] = system_name(records)
        result['merged'].append(records[record_index][3])
        _merge_leaves(records, record_index, clip['rows'], result)
        _note_selection(entries[entry_index])
        return result

    source = clip['records'] if clip['what'] == 'system' else clip['system']
    if clip['what'] == 'department' and kind_of(source[0]) == 'Conventional' and entry_index is not None and \
            kind_of(entries[entry_index]['records'][0]) == 'Conventional':
        found = entry_index                       # conventional departments can go into any conventional system
    else:
        found = _find_system(entries, source, entry_index)
    if found is None:
        records = copy.deepcopy(source) if clip['what'] == 'system' else copy.deepcopy(source)
        if clip['what'] == 'department':
            records.extend(copy.deepcopy(clip['rows']))
            result['departments'].append(clip['name'])
            result['added'] += sum(1 for r in clip['rows'] if kind_of(r) in DEPARTMENT_OF)
        else:
            result['departments'] = [r[3] for r in records if kind_of(r) in DEPARTMENTS]
            result['added'] += sum(1 for r in records if kind_of(r) in DEPARTMENT_OF)
        result['sites'] = [r[3] for r in records if kind_of(r) == 'Site']
        result['new_system'] = True
        result['system'] = system_name(records)
        entries.append(_new_entry(entries, records))
        return result
    records = entries[found]['records']
    result['system'] = system_name(records)
    if kind_of(records[0]) == 'Trunk':
        _merge_sites(records, source, result)
    if clip['what'] == 'department':
        _merge_department(records, clip['rows'], result)
    else:
        for kind, start, end in blocks(clip['records']):
            if kind in DEPARTMENTS:
                _merge_department(records, clip['records'][start:end], result)
    _note_selection(entries[found])
    return result


# ---- quick keys and number tags of pasted rows (v0.1.10) --------------------------------------------------
# (kind, column) -> the set the number belongs to: 'sys-key'/'sys-tag' per list, 'dept-key' and 'chan-tag'
# per system. Channel and talkgroup number tags share one set.
NUMBER_FIELDS = {('Conventional', 7): 'sys-key', ('Trunk', 12): 'sys-key', ('Conventional', 8): 'sys-tag',
                 ('Trunk', 13): 'sys-tag', ('C-Group', 9): 'dept-key', ('T-Group', 9): 'dept-key',
                 ('Site', 16): 'dept-key',                  # sites share the department keys (v0.1.22)
                 ('C-Freq', 16): 'chan-tag', ('TGID', 14): 'chan-tag'}
NUMBER_MAX = {'sys-key': 99, 'sys-tag': 99, 'dept-key': 99, 'chan-tag': 999}
FIELD_WORDS = {'sys-key': 'system quick key', 'sys-tag': 'system number tag',
               'dept-key': 'department quick key', 'chan-tag': 'channel number tag'}


def _numbered(entries):
    """[(row, column, field, set id)] for every quick key / number tag field in a list."""
    out = []
    for ei, entry in enumerate(entries):
        if entry.get('scope') == 'metadata':
            continue
        for row in entry.get('records', []):
            for (kind, column), field in NUMBER_FIELDS.items():
                if row and row[0] == kind and len(row) > column:
                    out.append((row, column, field, 'list' if field.startswith('sys') else ei))
    return out


def _number(value):
    text = str(value or '').strip()
    return int(text) if text.isdecimal() else None


def renumber(entries, old_ids, numbers='keep'):
    """For rows added by a paste: 'keep' leaves their numbers, 'clear' sets clashing ones Off, 'free' moves
    clashing ones to the next free number of their set. Returns [(name, field word, number)] of clashes."""
    fields = _numbered(entries)
    used = {}
    for row, column, field, scope in fields:
        if id(row) in old_ids and _number(row[column]) is not None:
            used.setdefault((field, scope), set()).add(_number(row[column]))
    clashes = []
    for row, column, field, scope in fields:
        if id(row) in old_ids:
            continue
        value = _number(row[column])
        if value is None:
            continue
        taken = used.setdefault((field, scope), set())
        if value in taken:
            clashes.append((row[3] if len(row) > 3 else row[0], FIELD_WORDS[field], value))
            if numbers == 'clear':
                row[column] = 'Off'
                continue
            if numbers == 'free':
                free = next((n for n in range(NUMBER_MAX[field] + 1) if n not in taken), None)
                row[column] = 'Off' if free is None else str(free)
                value = free
        if value is not None:
            taken.add(value)
    return clashes


def paste(entries, clip, target=(None, None), numbers='keep'):
    """Paste (see _paste), then deal with quick keys and number tags that clash with ones already in the
    list (numbers: 'keep', 'clear' or 'free'). The result also lists the clashes found."""
    old_ids = {id(r) for e in entries if e.get('scope') != 'metadata' for r in e.get('records', [])}
    result = _paste(entries, clip, target)
    result['clashes'] = renumber(entries, old_ids, numbers)
    return result


def summary(clip, result, list_name):
    """The confirmation text for a paste (worked out on a copy of the list first)."""
    lines = []
    where = f'in {list_name}'
    if result['new_system']:
        lines.append(f'Adds system {result["system"]} {where}.')
    else:
        lines.append(f'Adds to system {result["system"]} {where}.')
    if result['sites'] and not (result['new_system'] and clip['what'] == 'system'):
        lines.append(f'Sites: {", ".join(result["sites"])}' + ('' if result['new_system'] else ' (new)'))
    if result['departments']:
        lines.append('New departments: ' + ', '.join(result['departments']))
    if result['merged']:
        lines.append('Into existing department(s): ' + ', '.join(result['merged']))
    noun = 'channels or talkgroups'
    lines.append(f'{result["added"]} {noun} added' +
                 (f'; {result["skipped"]} already there, skipped.' if result['skipped'] else '.'))
    return '\n'.join(lines)


def new_list_rows(clip):
    """A complete Favorites List (the rows of an .hpd file) holding what was copied."""
    if clip['what'] == 'leaves':
        raise ClipboardError('A new Favorites List needs a system or a department. Copy the department instead.')
    preamble = [r for r in clip.get('preamble', []) if kind_of(r) in ('TargetModel', 'FormatVersion')]
    if not any(kind_of(r) == 'TargetModel' for r in preamble):
        preamble = [['TargetModel', 'BCDx36HP'], ['FormatVersion', '1.00']]
    body = clip['records'] if clip['what'] == 'system' else clip['system'] + clip['rows']
    return copy.deepcopy(preamble) + copy.deepcopy(body)
