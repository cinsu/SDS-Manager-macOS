# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Quick keys, number tags and what the scanner scans, for every level of a configuration (v0.1.8).

Levels and where each value lives:

  Favorites List   quick key + number tag: f_list.cfg (one set for the scanner); key On/Off: profile.cfg
                   Monitor On/Off: f_list.cfg
  System           quick key (header col 7) + number tag (col 8) in the list's .hpd; one set per list;
                   key On/Off: the list's row in f_list.cfg
  Department       quick key (C-Group / T-Group col 9); one set per system; key On/Off: DQKs_Status
  Site             quick key (Site col 16), in the same set as the system's departments (v0.1.22)
  Channel          number tag (C-Freq col 16, TGID col 14) 0-999; one set per system

Which number an item is assigned to and whether that number is On are separate things, and are kept
apart here. Pure: no Qt, no I/O. The window (keys_window.py) shows and edits a Model; the export shows
its warnings.
"""
import copy

import flist_settings as fls

KEY_MAX, TAG_MAX, CHANNEL_TAG_MAX = 99, 99, 999
# System quick key and number tag columns (Uniden SDS Series File Specification v2.00). A trunked system's
# are further along: its columns 7 and 8 are ID Search and Alert Tone (v0.1.17 fix).
SYSTEM_COLUMNS = {'Conventional': (7, 8), 'Trunk': (12, 13)}
HEADER_KEY, HEADER_TAG, DEPARTMENT_KEY = 7, 8, 9          # conventional; see SYSTEM_COLUMNS
# A trunked site's quick key: Site record column 16 (Quick Key, between DigitalThresholdLevel and NAC). Sites
# share the system's department quick keys (DQKs_Status) with its departments (v0.1.22).
SITE_KEY = 16
CHANNEL_TAG = {'C-Freq': 16, 'TGID': 14}
LEVEL_WORD = {'list': 'Favorites List', 'system': 'system', 'department': 'department', 'site': 'site',
              'channel': 'channel'}


def number(value):
    text = str(value or '').strip()
    return int(text) if text.isdecimal() else None


def text(value):
    return 'Off' if value is None else str(int(value))


def badge(row):
    """Short text for a row's quick key / number tag, shown beside names: 'Key 03 · Tag 12', 'Key 04',
    'Tag 120', or '' when it has none (v0.1.10)."""
    kind = row[0] if row else ''
    parts = []
    if kind in SYSTEM_COLUMNS:
        kc, tc = SYSTEM_COLUMNS[kind]
        key, tag = (number(row[kc]) if len(row) > kc else None, number(row[tc]) if len(row) > tc else None)
    elif kind in ('C-Group', 'T-Group'):
        key, tag = (number(row[DEPARTMENT_KEY]) if len(row) > DEPARTMENT_KEY else None), None
    elif kind == 'Site':
        key, tag = (number(row[SITE_KEY]) if len(row) > SITE_KEY else None), None
    elif kind in CHANNEL_TAG:
        key, tag = None, (number(row[CHANNEL_TAG[kind]]) if len(row) > CHANNEL_TAG[kind] else None)
    else:
        return ''
    if key is not None:
        parts.append(f'Key {key:02d}')
    if tag is not None:
        parts.append(f'Tag {tag:02d}')
    return ' · '.join(parts)


# ---- repairing trunked systems numbered in the wrong columns (v0.1.17) ------------------------------------
def misplaced_numbers(row):
    """For a Trunk header that versions 0.1.8–0.1.16 numbered in the wrong columns: (key, tag) to move into
    the quick key / number tag columns, else None. ID Search (col 7) is only ever On/Off, so a number there
    came from this program; Alert Tone (col 8) is Off or 0–9, so any number there is listed too: every
    trunked system in the lists seen so far has it Off."""
    if not row or row[0] != 'Trunk' or len(row) < 14:
        return None
    key = row[7] if row[7] not in ('On', 'Off') else None
    tag = row[8] if row[8] != 'Off' else None
    if key is None and tag is None:
        return None
    return key, tag


def repair_row(row):
    """Move misplaced numbers to the quick key / number tag columns and set ID Search and Alert Tone Off.
    Returns a plain description, or '' if nothing was wrong."""
    found = misplaced_numbers(row)
    if found is None:
        return ''
    key, tag = found
    parts = []
    if key is not None:
        parts.append(f'quick key {key} (was in ID Search)')
        row[12], row[7] = key if number(key) is not None and number(key) <= 99 else 'Off', 'Off'
    if tag is not None:
        parts.append(f'number tag {tag} (was in Alert Tone)')
        row[13], row[8] = tag if number(tag) is not None and number(tag) <= 99 else 'Off', 'Off'
    return f'{row[3]}: ' + ', '.join(parts)


def entries_from_rows(rows):
    """Systems of a saved list, shaped like the editor's entries (records per system)."""
    entries, current = [{'scope': 'metadata', 'records': []}], None
    for row in rows:
        if row and row[0] in ('Conventional', 'Trunk'):
            current = {'scope': 'system', 'name': row[3] if len(row) > 3 else '', 'records': []}
            entries.append(current)
        (entries[0]['records'] if current is None else current['records']).append(row)
    return entries


class Model:
    """lists: flist_settings.read_lists(); fl_status: 100 bools from profile.cfg;
    entries_by_file: {filename: the list's entries} (lists not given show no systems)."""

    def __init__(self, lists, fl_status, entries_by_file):
        self.lists = lists
        self.entries = {f: copy.deepcopy(e) for f, e in entries_by_file.items()}
        self.items = []
        self.status = {('fl',): list(fl_status)}
        for l in lists:
            self.status[('sys', l['filename'])] = [v == 'On' for v in l['system_keys']]
            top = self._add(None, 'list', l['name'], number(l['quick_key']), number(l['number_tag']),
                            ('fl',), ('fl',), ('flist', l['filename']), monitor=l['monitor'] == 'On')
            for ei, entry in enumerate(self.entries.get(l['filename'], [])):
                records = entry.get('records') or []
                if entry.get('scope') == 'metadata' or not records or records[0][0] not in ('Conventional', 'Trunk'):
                    continue
                head = records[0]
                kc, tc = SYSTEM_COLUMNS[head[0]]
                system = self._add(top, 'system', head[3] if len(head) > 3 else '',
                                   number(head[kc]) if len(head) > kc else None,
                                   number(head[tc]) if len(head) > tc else None,
                                   ('sys', l['filename']), ('sys', l['filename']),
                                   ('row', l['filename'], ei, 0))
                dqk_scope = ('dept', l['filename'], ei)
                self.status[dqk_scope] = None
                department = None
                for ri, row in enumerate(records):
                    kind = row[0] if row else ''
                    if kind == 'DQKs_Status' and len(row) >= 102:
                        self.status[dqk_scope] = [v == 'On' for v in row[2:102]]
                        system['dqk_row'] = ri
                    elif kind == 'Site' and len(row) > SITE_KEY:
                        department = None
                        self._add(system, 'site', row[3] if len(row) > 3 else '', number(row[SITE_KEY]), None,
                                  dqk_scope, None, ('row', l['filename'], ei, ri), detail='Site')
                    elif kind in ('C-Group', 'T-Group'):
                        department = self._add(system, 'department', row[3] if len(row) > 3 else '',
                                               number(row[DEPARTMENT_KEY]) if len(row) > DEPARTMENT_KEY else None,
                                               None, dqk_scope, None, ('row', l['filename'], ei, ri))
                    elif kind in CHANNEL_TAG and department is not None:
                        column = CHANNEL_TAG[kind]
                        self._add(department, 'channel', row[3] if len(row) > 3 else '', None,
                                  number(row[column]) if len(row) > column else None,
                                  None, ('chan', l['filename'], ei), ('row', l['filename'], ei, ri),
                                  detail=(f'{int(row[5]) / 1e6:.4f} MHz' if kind == 'C-Freq' and row[5].isdigit()
                                          else f'TGID {row[5]}'))
        self.original = self._state()

    def _add(self, parent, level, name, key, tag, key_scope, tag_scope, ref, **extra):
        item = dict(id=len(self.items), parent=parent['id'] if parent else None, level=level, name=name,
                    key=key, tag=tag, key_scope=key_scope, tag_scope=tag_scope, ref=ref, **extra)
        self.items.append(item)
        return item

    def _state(self):
        return ([(i['key'], i['tag'], i.get('monitor')) for i in self.items],
                {k: list(v) if v is not None else None for k, v in self.status.items()})

    # ---- reading -------------------------------------------------------------------------------------
    def children(self, item_id):
        return [i for i in self.items if i['parent'] == item_id]

    def parent(self, item):
        return self.items[item['parent']] if item['parent'] is not None else None

    def maximum(self, field, item):
        if field == 'key':
            return KEY_MAX
        return CHANNEL_TAG_MAX if item['level'] == 'channel' else TAG_MAX

    def users(self, item, field, value):
        """Other items in the same set that use this number."""
        scope = item['key_scope' if field == 'key' else 'tag_scope']
        return [i for i in self.items if i is not item and i[field] == value and value is not None
                and i['key_scope' if field == 'key' else 'tag_scope'] == scope]

    def next_free(self, item, field):
        scope = item['key_scope' if field == 'key' else 'tag_scope']
        used = {i[field] for i in self.items if i['key_scope' if field == 'key' else 'tag_scope'] == scope}
        return next((n for n in range(self.maximum(field, item) + 1) if n not in used), None)

    def key_on(self, item):
        """True/False for an item with a quick key; None when it has no key (not switched by one)."""
        if item['key'] is None or item['key_scope'] is None:
            return None
        statuses = self.status.get(item['key_scope'])
        return True if statuses is None else statuses[item['key']]

    def scanned(self, item):
        """(True/False, plain reason) — whether the scanner scans this item, all levels above included."""
        chain = []
        node = item
        while node is not None:
            chain.append(node)
            node = self.parent(node)
        for node in reversed(chain):
            if node['level'] == 'channel':
                continue
            if node['level'] == 'list' and node.get('monitor') is False:
                return False, f'not scanned: Favorites List {node["name"]} has Monitor Off'
            if self.key_on(node) is False:
                where = '' if node is item else f' ({LEVEL_WORD[node["level"]]} {node["name"]})'
                return False, f'not scanned: {LEVEL_WORD[node["level"]]} key {node["key"]:02d} is Off{where}'
        if item['level'] == 'channel':
            return True, ''
        own = self.key_on(item)
        if own is None:
            return True, 'scanned (no quick key)'
        return True, f'scanned: key {item["key"]:02d} is On'

    # ---- changing -------------------------------------------------------------------------------------
    def set_number(self, item, field, value):
        if value is not None and not 0 <= int(value) <= self.maximum(field, item):
            raise ValueError(f'Use a number from 0 to {self.maximum(field, item)}, or Off.')
        if field == 'key' and item['key_scope'] is None or field == 'tag' and item['tag_scope'] is None:
            raise ValueError(f'A {LEVEL_WORD[item["level"]]} has no {"quick key" if field == "key" else "number tag"}.')
        item[field] = None if value is None else int(value)

    def set_on(self, item, on):
        """Switch the item's key On or Off (every item on that key in the same set follows)."""
        if item['key'] is None:
            raise ValueError('This item has no quick key to switch.')
        scope = item['key_scope']
        if self.status.get(scope) is None:
            self.status[scope] = [True] * 100
        self.status[scope][item['key']] = bool(on)

    def set_monitor(self, item, on):
        item['monitor'] = bool(on)

    def number_in_order(self, items, field, start=0, step=1):
        """Give the items numbers start, start+step, ... in the order given."""
        for n, item in enumerate(items):
            self.set_number(item, field, start + n * step)

    def tags_by_department(self, system, block=100, first=None):
        """Channel number tags in blocks per department of a system: the first department's channels
        get first, first+1, ...; the next department starts one block higher (v0.1.9)."""
        departments = [d for d in self.children(system['id']) if d['level'] == 'department']
        first = block if first is None else first
        for n, department in enumerate(departments):
            channels = self.children(department['id'])
            start = first + n * block
            if len(channels) > block or start + len(channels) - 1 > CHANNEL_TAG_MAX:
                raise ValueError(f'{department["name"]} has {len(channels)} channels; that doesn\'t fit in blocks of '
                                 f'{block} starting at {first}. Use a bigger block or a lower start.')
        for n, department in enumerate(departments):
            self.number_in_order(self.children(department['id']), 'tag', first + n * block)
        return len(departments)

    def match_tags_to_keys(self, items):
        """Number tag = quick key for each item that has a key (so one number to remember)."""
        changed = 0
        for item in items:
            if item['key'] is not None and item['tag_scope'] is not None and item['tag'] != item['key']:
                self.set_number(item, 'tag', item['key'])
                changed += 1
        return changed

    # ---- scan profiles (v0.1.9) ----------------------------------------------------------------------
    def profile(self):
        """The On/Off state of every key and every list's Monitor, by name, for saving as a scan profile."""
        out = {'fl': [bool(v) for v in self.status[('fl',)]], 'monitor': {}, 'sys': {}, 'dept': {}}
        for item in self.items:
            if item['level'] == 'list':
                out['monitor'][item['ref'][1]] = bool(item.get('monitor'))
            elif item['level'] == 'system':
                filename = item['ref'][1]
                out['sys'][filename] = [bool(v) for v in self.status[('sys', filename)]]
                dqk = self.status.get(('dept', filename, item['ref'][2]))
                if dqk is not None:
                    out['dept'][f'{filename}|{item["name"]}'] = [bool(v) for v in dqk]
        return out

    def apply_profile(self, profile):
        """Set keys and Monitor from a saved profile. Lists or systems it doesn't know are left as they
        are. Returns the names of the lists and systems it couldn't find."""
        missing = []
        if len(profile.get('fl', [])) == 100:
            self.status[('fl',)] = [bool(v) for v in profile['fl']]
        for item in self.items:
            if item['level'] == 'list':
                filename = item['ref'][1]
                if filename in profile.get('monitor', {}):
                    item['monitor'] = bool(profile['monitor'][filename])
                    states = profile.get('sys', {}).get(filename)
                    if states and len(states) == 100:
                        self.status[('sys', filename)] = [bool(v) for v in states]
                else:
                    missing.append(item['name'])
            elif item['level'] == 'system':
                filename = item['ref'][1]
                states = profile.get('dept', {}).get(f'{filename}|{item["name"]}')
                scope = ('dept', filename, item['ref'][2])
                if states and len(states) == 100 and self.status.get(scope) is not None:
                    self.status[scope] = [bool(v) for v in states]
        return missing

    # ---- problems -------------------------------------------------------------------------------------
    def warnings(self):
        """[(kind, text)]: kind 'shared' (a number used twice in one set) or 'skipped' (not scanned because
        a key is Off) or 'unused' (keys On with nothing on them, Favorites List level)."""
        out = []
        for field, word in (('key', 'quick key'), ('tag', 'number tag')):
            groups = {}
            for i in self.items:
                scope = i['key_scope' if field == 'key' else 'tag_scope']
                if scope is not None and i[field] is not None:
                    groups.setdefault((scope, i[field]), []).append(i)
            for (scope, value), members in sorted(groups.items(), key=lambda g: (str(g[0][0]), g[0][1])):
                if len(members) > 1:
                    where = self._where(members[0])
                    out.append(('shared', f'{LEVEL_WORD[members[0]["level"]].capitalize()} {word} {value:02d} is used '
                                          f'by {len(members)}{where}: ' + ', '.join(m['name'] for m in members)))
        for scope, statuses in self.status.items():
            if statuses is None:
                continue
            for key in range(100):
                if statuses[key]:
                    continue
                members = [i for i in self.items if i['key_scope'] == scope and i['key'] == key]
                if members:
                    where = self._where(members[0])
                    out.append(('skipped', f'{LEVEL_WORD[members[0]["level"]].capitalize()} key {key:02d} is Off'
                                           f'{where}: not scanned: ' + ', '.join(m['name'] for m in members)))
        used = {i['key'] for i in self.items if i['level'] == 'list' and i['key'] is not None}
        spare = [k for k in range(100) if self.status[('fl',)][k] and k not in used]
        if spare:
            out.append(('unused', f'{len(spare)} Favorites List keys are On with no list on them (that does nothing).'))
        return out

    def _where(self, item):
        parent = self.parent(item)
        if item['level'] == 'list' or parent is None:
            return ''
        if item['level'] == 'system':
            return f' in {parent["name"]}'
        top = self.parent(parent)
        return f' in {parent["name"]} ({top["name"]})' if top else f' in {parent["name"]}'

    # ---- what changed --------------------------------------------------------------------------------
    def changed(self):
        return self._state() != self.original

    def flist_edits(self):
        edits = {}
        before = self.original[0]
        for item, (key, tag, monitor) in zip(self.items, before):
            if item['level'] != 'list':
                continue
            filename = item['ref'][1]
            if item['key'] != key:
                edits[(filename, fls.POS_QUICK)] = text(item['key'])
            if item['tag'] != tag:
                edits[(filename, fls.POS_TAG)] = text(item['tag'])
            if item.get('monitor') != monitor:
                edits[(filename, fls.POS_MONITOR)] = 'On' if item['monitor'] else 'Off'
        for l in self.lists:
            scope = ('sys', l['filename'])
            for k, (old, new) in enumerate(zip(self.original[1][scope], self.status[scope])):
                if old != new:
                    edits[(l['filename'], fls.POS_SQK[0] + k)] = 'On' if new else 'Off'
        return edits

    def fl_status_changed(self):
        return self.original[1][('fl',)] != self.status[('fl',)]

    def row_edits(self):
        """[(filename, entry index, record index, column, value)] for the lists' rows."""
        edits = []
        for item, (key, tag, _m) in zip(self.items, self.original[0]):
            if item['ref'][0] != 'row':
                continue
            _r, filename, ei, ri = item['ref']
            if item['level'] == 'system':
                kc, tc = SYSTEM_COLUMNS[self.entries[filename][ei]['records'][0][0]]
                if item['key'] != key:
                    edits.append((filename, ei, ri, kc, text(item['key'])))
                if item['tag'] != tag:
                    edits.append((filename, ei, ri, tc, text(item['tag'])))
            elif item['level'] == 'department' and item['key'] != key:
                edits.append((filename, ei, ri, DEPARTMENT_KEY, text(item['key'])))
            elif item['level'] == 'site' and item['key'] != key:
                edits.append((filename, ei, ri, SITE_KEY, text(item['key'])))
            elif item['level'] == 'channel' and item['tag'] != tag:
                row = self.entries[filename][ei]['records'][ri]
                edits.append((filename, ei, ri, CHANNEL_TAG[row[0]], text(item['tag'])))
        for item in self.items:
            if item['level'] != 'system' or 'dqk_row' not in item:
                continue
            _r, filename, ei, _ri = item['ref']
            scope = ('dept', filename, ei)
            old, new = self.original[1].get(scope), self.status.get(scope)
            if old is not None and new is not None:
                for k in range(100):
                    if old[k] != new[k]:
                        edits.append((filename, ei, item['dqk_row'], 2 + k, 'On' if new[k] else 'Off'))
        return edits

    def describe_changes(self):
        lines = []
        for item, (key, tag, monitor) in zip(self.items, self.original[0]):
            path = self._path(item)
            if item['key'] != key:
                lines.append(f'{path}: quick key {text(key)} → {text(item["key"])}')
            if item['tag'] != tag:
                lines.append(f'{path}: number tag {text(tag)} → {text(item["tag"])}')
            if item.get('monitor') != monitor:
                lines.append(f'{path}: Monitor {"On" if item["monitor"] else "Off"}')
        for scope, statuses in self.status.items():
            old = self.original[1].get(scope)
            if statuses is None or old is None:
                continue
            for k in range(100):
                if old[k] != statuses[k]:
                    members = [i['name'] for i in self.items if i['key_scope'] == scope and i['key'] == k]
                    level = {'fl': 'Favorites List', 'sys': 'System', 'dept': 'Department/site'}[scope[0]]
                    lines.append(f'{level} key {k:02d} ({", ".join(members) or "nothing on it"}): '
                                 f'{"On" if statuses[k] else "Off"}')
        return lines

    def _path(self, item):
        names = []
        while item is not None:
            names.append(item['name'])
            item = self.parent(item)
        return ' › '.join(reversed(names))


def model_for_configuration(folder, entries_by_file=None):
    """A Model of a local configuration as saved (or with the given entries for some lists)."""
    from pathlib import Path
    from quick_keys_settings import read_quick_keys
    root = Path(folder) / 'BCDx36HP'
    lists = fls.read_lists((root / 'favorites_lists' / 'f_list.cfg').read_bytes())
    entries = dict(entries_by_file or {})
    for l in lists:
        if l['filename'] in entries:
            continue
        path = root / 'favorites_lists' / l['filename']
        if path.is_file():
            text_ = path.read_bytes().decode('cp1252', errors='replace')
            entries[l['filename']] = entries_from_rows([line.split('\t') for line in text_.splitlines()])
    try:
        statuses = read_quick_keys((root / 'profile.cfg').read_bytes())
    except (OSError, ValueError):
        statuses = [True] * 100                      # no readable QuickKeys line: the scanner's default
    return Model(lists, statuses, entries)


def export_summary(folder, limit=8):
    """Plain-words warnings for the export preview; '' when there is nothing to say."""
    try:
        found = model_for_configuration(folder).warnings()
    except (OSError, ValueError, UnicodeError):
        return ''
    found = [w for w in found if w[0] != 'unused']
    if not found:
        return ''
    shared = [t for k, t in found if k == 'shared']
    skipped = [t for k, t in found if k == 'skipped']
    lines = ['QUICK KEYS AND NUMBER TAGS (export is not blocked by these):']
    for title, group in (('Used twice', shared), ('Won\'t be scanned', skipped)):
        if group:
            lines.append(f'{title}:')
            lines.extend('  • ' + t for t in group[:limit])
            if len(group) > limit:
                lines.append(f'  … and {len(group) - limit} more (Favorites → Keys & Tags…)')
    return '\n'.join(lines)


# ---- scan profiles on disk ------------------------------------------------------------------------------
def profiles_path(folder):
    """Saved scan profiles of a configuration (kept beside the configuration library, not on the scanner)."""
    from pathlib import Path
    from scanner_configurations import library_path
    return library_path().parent / 'scan-profiles' / (Path(folder).name + '.json')


def load_profiles(folder):
    import json
    path = profiles_path(folder)
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_profiles(folder, profiles):
    import json
    import os
    path = profiles_path(folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(profiles, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    os.replace(temporary, path)



# ---- names and numbers for SDS100 Monitor (v0.1.12) ------------------------------------------------------
def monitor_file_path():
    from scanner_configurations import library_path
    return library_path().parent / 'monitor-keys.json'


def monitor_summary(model, name=''):
    """What the Monitor needs to name quick keys, offer number tags and apply scan profiles."""
    lists = []
    for item in model.items:
        if item['level'] != 'list':
            continue
        systems = []
        for system in model.children(item['id']):
            departments, channels = [], []
            for department in model.children(system['id']):
                departments.append({'name': department['name'] + (' (site)' if department['level'] == 'site' else ''),
                                    'key': department['key']})
                for channel in model.children(department['id']):
                    if channel['tag'] is not None:
                        channels.append({'name': channel['name'], 'tag': channel['tag'],
                                         'detail': channel.get('detail', ''), 'department': department['name']})
            systems.append({'name': system['name'], 'key': system['key'], 'tag': system['tag'],
                            'departments': departments, 'channels': channels})
        lists.append({'name': item['name'], 'filename': item['ref'][1], 'key': item['key'], 'tag': item['tag'],
                      'monitor': bool(item.get('monitor')), 'systems': systems})
    return {'version': 1, 'configuration': name, 'lists': lists}


def write_monitor_file(folder, name=''):
    """Share the saved configuration's keys, tags and scan profiles with SDS100 Monitor (read-only there).
    Best effort: a failure here never stops the Manager."""
    import datetime
    import json
    import os
    try:
        data = monitor_summary(model_for_configuration(folder), name)
        data['profiles'] = load_profiles(folder)
        data['written'] = datetime.datetime.now().isoformat(timespec='seconds')
        try:
            import export_state
            data['scanner'] = export_state.state(folder)       # v0.1.20: up to date or not
            data['scanner']['text'] = export_state.describe(data['scanner'])
        except Exception:
            pass
        path = monitor_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data, indent=1) + '\n', encoding='utf-8')
        os.replace(temporary, path)
        return path
    except (OSError, ValueError, UnicodeError):
        return None
