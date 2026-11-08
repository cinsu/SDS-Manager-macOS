# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Rules for exporting NEW and DELETED Favorites List files (pure checks, no scanner I/O).

A list is added to the scanner as   favorites_lists/f_NNNNNN.hpd  plus one new row in
favorites_lists/f_list.cfg.  A list is removed only when the user deleted it in this program:
the deletion archive (written by scanner_configurations.delete_local_favorites_list) must hold a
record whose SHA-256 equals the file currently on the scanner.  Lists that merely exist on the
scanner but are unknown to the local configuration are never removed.
"""
import hashlib
import json
import re

import unit_aliases
from datetime import datetime, timezone
from pathlib import Path

from scanner_favorites_expanded import _records, _preamble, _hierarchy
from flist_settings import check_edits, read_lists, row_problem

LIST_FILE = re.compile(r'favorites_lists/f_\d{6}\.hpd', re.I)
INDEX_FILE = 'favorites_lists/f_list.cfg'
FLIST_FIELDS = 117          # F-List .. S-Qkey_99 (a real row has one more, empty, trailing field)
WIDTHS = {'Conventional': 15, 'DQKs_Status': 103, 'C-Group': 11, 'C-Freq': 18, 'Trunk': 22, 'Site': 19,
          'BandPlan_P25': 50, 'BandPlan_Mot': 26, 'T-Freq': 9, 'T-Group': 10, 'TGID': 17, 'Rectangle': 6}
TRUNK_TYPES = ('P25Standard', 'P25OneFrequency', 'Motorola', 'Edacs', 'Ltr', 'MotoTrbo', 'DmrOneFrequency', 'Nxdn')
ONOFF = ('On', 'Off')


LOCATIONS = ('Circle', 'Rectangles')
_COORD = re.compile(r'-?[0-9]{1,3}\.[0-9]{1,6}')


def rectangle_problem(row):
    """None if a native Rectangle row is well formed, else the reason."""
    if len(row) != 6 or row[0] != 'Rectangle' or row[1] != '':
        return 'unexpected Rectangle layout'
    for index, limit in ((2, 90), (3, 180), (4, 90), (5, 180)):
        if not _COORD.fullmatch(row[index]) or abs(float(row[index])) > limit:
            return 'invalid rectangle coordinate %r' % row[index]
    return None


def _rectangles_consistent(rows):
    """Rectangle rows belong to a Rectangles location and follow it directly (after band plans for a site);
    every Rectangles location has at least one."""
    parent = None            # [line number, kind, wants rectangles, rectangle rows so far, ended]
    for number, row in enumerate(rows, 1):
        kind = row[0]
        if kind in ('Site', 'T-Group', 'C-Group') and len(row) > 8:
            index = 11 if kind == 'Site' else 8
            if parent and parent[2] and not parent[3]:
                raise ValueError('Line %d: a Rectangles location has no Rectangle row' % parent[0])
            parent = [number, kind, row[index] == 'Rectangles', 0, False]
        elif kind == 'Rectangle':
            if parent is None or not parent[2] or parent[4]:
                raise ValueError('Line %d: Rectangle row is not directly after a Rectangles location' % number)
            problem = rectangle_problem(row)
            if problem:
                raise ValueError('Line %d: %s' % (number, problem))
            parent[3] += 1
            if parent[3] > 50:
                raise ValueError('Line %d: too many rectangles' % number)
        elif kind in ('Trunk', 'Conventional'):
            if parent and parent[2] and not parent[3]:
                raise ValueError('Line %d: a Rectangles location has no Rectangle row' % parent[0])
            parent = None
        elif kind not in ('BandPlan_P25', 'BandPlan_Mot') and parent is not None:
            parent[4] = True
    if parent and parent[2] and not parent[3]:
        raise ValueError('Line %d: a Rectangles location has no Rectangle row' % parent[0])


def is_list_file(relative):
    return bool(LIST_FILE.fullmatch(relative))


def _keyed(value, limit):
    return value == 'Off' or (value.isascii() and value.isdecimal() and 0 <= int(value) <= limit)


# Band plan lines are written by the scanner/Sentinel and copied unchanged. A real SDS100 list has been
# seen with a 34-column BandPlan_P25 line as well as the 50-column one (v0.1.16).
BANDPLAN_WIDTHS = {'BandPlan_P25': (34, 50), 'BandPlan_Mot': (26,)}


def assess_new_hpd(raw, original=None):
    """(valid, detail) for a complete Favorites List file (conventional or trunked systems).

    original: when an existing list is being replaced, the scanner's current copy. Band plan and other
    scanner-written lines that are exactly as they are there are accepted as the scanner wrote them, even
    in a layout this program hasn't seen before (v0.1.16)."""
    try:
        rows = _records(raw)
        unchanged = set()
        original_rows = []
        if original is not None:
            try:
                original_rows = _records(original)
                unchanged = {tuple(r) for r in original_rows}
            except ValueError:
                unchanged = set()
        current_system = None
        _preamble(rows)
        _hierarchy(rows)
        systems = 0
        quick_keys = set()
        for number, row in enumerate(rows, 1):
            kind = row[0]
            if kind in ('Trunk', 'Conventional'):
                current_system = kind
            if kind in ('TargetModel', 'FormatVersion'):
                continue
            if kind in BANDPLAN_WIDTHS and (len(row) in BANDPLAN_WIDTHS[kind] or tuple(row) in unchanged):
                continue
            if kind not in WIDTHS and tuple(row) in unchanged and kind not in ('Trunk', 'Conventional', 'Site',
                                                                                 'C-Group', 'T-Group'):
                continue                      # a scanner-written line kept exactly as it is on the scanner
            if kind == 'UnitIds':
                # Unit ID names (v0.1.19): only in the layout of a UnitIds row the scanner wrote in this list.
                widths = {len(r) for r in (original_rows or []) if r and r[0] == 'UnitIds'}
                problem = unit_aliases.row_problem(row)
                if len(row) not in widths:
                    raise ValueError('Line %d: UnitIds in a layout the scanner has not written in this list' % number)
                if problem or current_system != 'Trunk':
                    raise ValueError('Line %d: %s' % (number, problem or 'UnitIds outside a trunked system'))
                continue
            if kind not in WIDTHS:
                raise ValueError('Line %d: unsupported record type %r in a new list' % (number, kind))
            # A site frequency's last column (TDMA slot) is optional: lists confirmed working on a real SDS100
            # have it (P25, NXDN) or leave it out (DMR, and P25 in a Sentinel-written list) (v0.1.2).
            # Sentinel writes the department quick-key line without its trailing empty column (v0.1.3).
            if len(row) != WIDTHS[kind] and not (kind == 'T-Freq' and len(row) == 8) \
                    and not (kind == 'DQKs_Status' and len(row) == 102):
                raise ValueError('Line %d: %s has %d columns, expected %d' % (number, kind, len(row), WIDTHS[kind]))
            if kind in ('Trunk', 'Conventional'):
                quick_keys = set()            # department quick keys are numbered per system (v0.1.6)
            if kind == 'Trunk':
                systems += 1
                if not row[3].strip() or len(row[3]) > 64 or row[4] not in ONOFF or row[6] not in TRUNK_TYPES \
                        or row[21] not in ('NEXEDGE', 'IDAS') or not _keyed(row[12], 99) or not _keyed(row[13], 99):
                    raise ValueError('Line %d: invalid trunked system header' % number)
                if row[7] not in ONOFF or not _keyed(row[8], 9):
                    raise ValueError('Line %d: %s has a number in ID Search or Alert Tone (SDS-Manager 0.1.8–0.1.16 '
                                     'put quick keys and number tags there); open Favorites → Keys & Tags to repair it'
                                     % (number, row[3]))
            elif kind == 'Site':
                if not row[3].strip() or len(row[3]) > 64 or row[4] not in ONOFF or row[11] not in LOCATIONS:
                    raise ValueError('Line %d: invalid site' % number)
                if not _keyed(row[16], 99):
                    raise ValueError('Line %d: a site quick key must be Off or 0–99' % number)
            elif kind == 'T-Freq':
                f = row[5]
                if not (f.isascii() and f.isdecimal() and 100000 <= int(f) <= 1300000000) or row[4] not in ONOFF \
                        or not row[6].isdecimal():
                    raise ValueError('Line %d: invalid site frequency' % number)
            elif kind == 'T-Group':
                if not row[3].strip() or len(row[3]) > 64 or row[4] not in ONOFF or row[8] not in LOCATIONS \
                        or not _keyed(row[9], 99):
                    raise ValueError('Line %d: invalid talkgroup department' % number)
            elif kind == 'TGID':
                if not row[3].strip() or len(row[3]) > 64 or row[4] not in ONOFF or not row[5].isdecimal() \
                        or row[6] not in ('ALL', 'ANALOG', 'DIGITAL') or row[16] not in ('Any', '1', '2'):
                    raise ValueError('Line %d: invalid talkgroup' % number)
                if not (row[7].isdecimal() and (1 <= int(row[7]) <= 37 or 208 <= int(row[7]) <= 218)):
                    raise ValueError('Line %d: invalid service type' % number)
                if not _keyed(row[14], 999) or row[15] not in ONOFF:
                    raise ValueError('Line %d: invalid number tag/priority' % number)
            elif kind in ('BandPlan_P25', 'BandPlan_Mot', 'Rectangle'):
                pass
            elif kind == 'Conventional':
                systems += 1
                if not row[3].strip() or len(row[3]) > 64 or row[4] not in ONOFF or not _keyed(row[7], 99) \
                        or not _keyed(row[8], 99):
                    raise ValueError('Line %d: invalid system header' % number)
            elif kind == 'DQKs_Status':
                values = row[2:102]                 # 100 department quick keys; Sentinel omits the trailing ''
                if len(values) != 100 or any(v not in ONOFF for v in values) or (len(row) == 103 and row[-1] != ''):
                    raise ValueError('Line %d: invalid DQKs_Status' % number)
            elif kind == 'C-Group':
                if not row[3].strip() or len(row[3]) > 64 or row[4] not in ONOFF or not _keyed(row[9], 99) \
                        or row[8] not in LOCATIONS:
                    raise ValueError('Line %d: invalid department' % number)
                # Several departments may share a quick key (they switch together); Keys & Tags warns about it.
            elif kind == 'C-Freq':
                f = row[5]
                if not (f.isascii() and f.isdecimal() and 100000 <= int(f) <= 1300000000):
                    raise ValueError('Line %d: invalid frequency' % number)
                if not row[3].strip() or len(row[3]) > 64 or row[4] not in ONOFF or row[6] not in ('AUTO', 'AM', 'NFM', 'FM'):
                    raise ValueError('Line %d: invalid channel name/avoid/modulation' % number)
                if not (row[8].isdecimal() and (1 <= int(row[8]) <= 37 or 208 <= int(row[8]) <= 218)):
                    raise ValueError('Line %d: invalid service type' % number)
                if not _keyed(row[16], 999) or row[17] not in ONOFF:
                    raise ValueError('Line %d: invalid number tag/priority' % number)
        _rectangles_consistent(rows)
        if systems < 1:
            raise ValueError('new list has no system')
        return True, 'new list with %d system(s), %d rows' % (systems, len(rows))
    except (ValueError, UnicodeError, IndexError) as exc:
        return False, str(exc)


def _split(raw):
    text = raw.decode('cp1252')
    newline = '\r\n' if '\r\n' in text else '\n'
    return text.splitlines(), newline, text.endswith(('\r', '\n'))


def assess_flist_replacement(original, proposed, added_names, deleted_names):
    """(valid, detail, counts): the index may only gain rows for added lists and lose rows for deleted ones."""
    try:
        old, old_nl, old_end = _split(original)
        new, new_nl, new_end = _split(proposed)
        if old_nl != new_nl or old_end != new_end:
            raise ValueError('line endings of f_list.cfg changed')
        old_other = [l for l in old if not l.startswith('F-List\t')]
        new_other = [l for l in new if not l.startswith('F-List\t')]
        if old_other != new_other:
            raise ValueError('f_list.cfg header lines changed')
        old_rows = [l for l in old if l.startswith('F-List\t')]
        new_rows = [l for l in new if l.startswith('F-List\t')]
        added = {n.split('/')[-1].lower() for n in added_names}
        deleted = {n.split('/')[-1].lower() for n in deleted_names}
        removed = [l for l in old_rows if l.split('\t')[2].lower() in deleted]
        if {l.split('\t')[2].lower() for l in removed} != deleted:
            raise ValueError('a deleted list has no row in the scanner index')
        kept = [l for l in old_rows if l.split('\t')[2].lower() not in deleted]
        # v0.1.7: the lists may be put in a new order; every kept list must still be there, once.
        by_file = {l.split('\t')[2].lower(): l for l in new_rows}
        if len(by_file) != len(new_rows):
            raise ValueError('a list appears twice in the index')
        if any(l.split('\t')[2].lower() not in by_file for l in kept):
            raise ValueError('an existing list row was removed (only lists deleted here may go)')
        kept_files = {l.split('\t')[2].lower() for l in kept}
        reordered = [l for l in new_rows if l.split('\t')[2].lower() in kept_files]
        if [l.split('\t')[2].lower() for l in reordered] != [l.split('\t')[2].lower() for l in kept]:
            kept = sorted(kept, key=lambda l: [r.split('\t')[2].lower() for r in reordered].index(
                l.split('\t')[2].lower()))
        # Existing rows may differ only in validated per-list settings (flist_settings.py).
        edits = {}
        for old_line, new_line in zip(kept, reordered):
            if old_line == new_line:
                continue
            old_fields, new_fields = old_line.split('\t'), new_line.split('\t')
            if len(old_fields) != len(new_fields) or row_problem(old_fields) or row_problem(new_fields):
                raise ValueError('existing list rows changed layout')
            for position, (a, b) in enumerate(zip(old_fields, new_fields)):
                if a != b:
                    edits[(old_fields[2], position)] = b
        if edits:
            check_edits(read_lists(('\n'.join(kept) + '\n').encode('cp1252')), edits)
        kept = reordered                     # the rows as they will stand, edits included
        appended = [l for l in new_rows if l.split('\t')[2].lower() not in kept_files]
        if {l.split('\t')[2].lower() for l in appended} != added or len(appended) != len(added):
            raise ValueError('new index rows do not match the lists being added')
        names = {l.split('\t')[1].strip().casefold() for l in kept}
        quick = {l.split('\t')[5] for l in kept if l.split('\t')[5] != 'Off'}
        tags = {l.split('\t')[6] for l in kept if l.split('\t')[6] != 'Off'}
        for line in appended:
            f = line.split('\t')
            trailing = f[-1] == ''
            body = f[:-1] if trailing else f
            if len(body) != FLIST_FIELDS:
                raise ValueError('new index row has %d fields, expected %d' % (len(body), FLIST_FIELDS))
            if not f[1].strip() or len(f[1]) > 64 or f[1].strip().casefold() in names:
                raise ValueError('new list name is empty, too long or duplicated')
            names.add(f[1].strip().casefold())
            if f[3] not in ONOFF or f[4] not in ONOFF or any(v not in ONOFF for v in f[7:len(body)]):
                raise ValueError('new index row has unrecognised On/Off values')
            for value, used, limit in ((f[5], quick, 99), (f[6], tags, 99)):
                if not _keyed(value, limit):
                    raise ValueError('new index row has an invalid quick key or number tag')
                if value != 'Off':
                    if value in used:
                        raise ValueError('two lists would share quick key / number tag %s' % value)
                    used.add(value)
        return True, '%d list row(s) added, %d removed, %d setting(s) changed' % (
            len(appended), len(removed), len(edits)), \
            {'field_edits': len(edits), 'added': len(appended), 'deleted': len(removed)}
    except (ValueError, UnicodeError, IndexError) as exc:
        return False, str(exc), {'field_edits': 0, 'added': 0, 'deleted': 0}


def deletion_archive(config_root, library_parent=None):
    if library_parent is None:
        from scanner_configurations import library_path
        library_parent = library_path().parent
    return Path(library_parent) / 'scanner-configuration-backups' / Path(config_root).name / 'deleted-lists'


def recorded_deletions(config_root, library_parent=None):
    """{ 'favorites_lists/f_000002.hpd': sha256 } for deletions made here and not yet exported."""
    found = {}
    archive = deletion_archive(config_root, library_parent)
    if not archive.is_dir():
        return found
    for receipt in sorted(archive.glob('*.json')):
        try:
            data = json.loads(receipt.read_text(encoding='utf-8'))
            relative = data['relative']
            if data.get('exported_utc') or not relative.startswith('BCDx36HP/'):
                continue
            scanner_relative = relative[len('BCDx36HP/'):]
            if is_list_file(scanner_relative) and isinstance(data['sha256'], str) and len(data['sha256']) == 64:
                found[scanner_relative] = data['sha256']
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return found


def mark_deletions_exported(config_root, relatives, library_parent=None):
    """Stop a finished deletion from ever being applied again (best effort)."""
    archive = deletion_archive(config_root, library_parent)
    wanted = {'BCDx36HP/' + r for r in relatives}
    for receipt in archive.glob('*.json') if archive.is_dir() else ():
        try:
            data = json.loads(receipt.read_text(encoding='utf-8'))
            if data.get('relative') in wanted and not data.get('exported_utc'):
                data['exported_utc'] = datetime.now(timezone.utc).isoformat()
                receipt.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
        except (OSError, ValueError, TypeError):
            continue


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()
