# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Plain-language summary of what an export to the scanner will change.

Input is the plan from scanner_first_write.prepare_first_write (the same plan the export executes).
The summary only reads the already-validated files; it never writes and never raises for a file it
cannot describe (that line falls back to the technical wording).
"""
from pathlib import Path

import flist_settings
import profile_schema

INDEX_FILE = 'favorites_lists/f_list.cfg'
SYSTEM_KINDS = {'Conventional': 'conventional', 'Trunk': 'trunked'}
COUNTED = (('C-Group', 'department'), ('T-Group', 'department'), ('C-Freq', 'channel'),
           ('TGID', 'talkgroup'), ('T-Freq', 'site frequency'), ('Site', 'site'))


def _rows(raw):
    for line in raw.decode('cp1252', 'replace').splitlines():
        if line:
            yield line.split('\t')


def hpd_counts(raw):
    """({'system': n, 'department': n, ...}, [system names]) for one Favorites List file."""
    counts, systems = {}, []
    for fields in _rows(raw):
        key = fields[0]
        if key in SYSTEM_KINDS:
            counts['system'] = counts.get('system', 0) + 1
            systems.append(fields[3] if len(fields) > 3 else '')
            continue
        for kind, label in COUNTED:
            if key == kind:
                counts[label] = counts.get(label, 0) + 1
    return counts, systems


def _plural(n, word):
    if n == 1:
        return '1 ' + word
    if word.endswith('y') and word[-2:] != 'ey':
        return '%d %sies' % (n, word[:-1])
    return '%d %ss' % (n, word)


def _count_text(counts):
    order = ('system', 'department', 'site', 'site frequency', 'channel', 'talkgroup')
    parts = [_plural(counts[k], k) for k in order if counts.get(k)]
    return ', '.join(parts) or 'no entries'


def _list_names(path):
    try:
        return {l['filename'].lower(): l['name'] for l in flist_settings.read_lists(Path(path).read_bytes())}
    except (OSError, ValueError):
        return {}


def _name(names, relative):
    base = relative.rsplit('/', 1)[-1]
    return names.get(base.lower()) or base


def _delta(old, new):
    out = []
    for key in ('system', 'department', 'site', 'site frequency', 'channel', 'talkgroup'):
        change = new.get(key, 0) - old.get(key, 0)
        if change:
            out.append('%+d %s' % (change, key if abs(change) == 1 else _plural(abs(change), key).split(' ', 1)[1]))
    return ', '.join(out)


def summarize(plan):
    """Return a tuple of readable lines.  Empty plan -> empty tuple."""
    config, scanner = Path(plan['configuration']) / 'BCDx36HP', Path(plan['scanner'])
    new_names = _list_names(config / INDEX_FILE)
    old_names = _list_names(scanner / INDEX_FILE)
    lines = []
    for item in plan['files']:
        relative, action = item['relative'], item['action']
        try:
            if relative == INDEX_FILE:
                lines.extend(_index_lines(scanner / relative, config / relative))
            elif relative == 'profile.cfg':
                lines.extend(_profile_lines(scanner / relative, config / relative))
            elif action == 'add':
                counts, _ = hpd_counts((config / relative).read_bytes())
                lines.append('NEW list "%s": %s' % (_name(new_names, relative), _count_text(counts)))
            elif action == 'delete':
                counts, _ = hpd_counts((scanner / relative).read_bytes())
                lines.append('REMOVE list "%s" (%s)' % (_name(old_names, relative), _count_text(counts)))
            else:
                old, _ = hpd_counts((scanner / relative).read_bytes())
                new, _ = hpd_counts((config / relative).read_bytes())
                c = item.get('changes', {})
                detail = '%s edited, %s added, %s removed' % (
                    _plural(c.get('field_edits', 0), 'field'), c.get('added', 0), c.get('deleted', 0))
                delta = _delta(old, new)
                lines.append('CHANGE list "%s": %s%s' % (_name(new_names or old_names, relative), detail,
                                                       ' (' + delta + ')' if delta else ''))
        except (OSError, ValueError, KeyError) as exc:
            lines.append('%s %s (details unavailable: %s)' % (action.upper(), relative, exc))
    return tuple(lines)


def _index_lines(old_path, new_path):
    old = flist_settings.read_lists(old_path.read_bytes())
    new = flist_settings.read_lists(new_path.read_bytes())
    common_old = [l for l in old if l['filename'].lower() in {n['filename'].lower() for n in new}]
    common_new = [l for l in new if l['filename'].lower() in {o['filename'].lower() for o in old}]
    out = []
    if [l['filename'] for l in common_old] == [l['filename'] for l in common_new]:
        edits = flist_settings.edits_between(common_old, common_new)
        out.extend('SETTING ' + line for line in flist_settings.describe(common_old, edits))
    else:
        out.append('Favorites List order changed')
    return out


def _profile_lines(old_path, new_path):
    old, new = old_path.read_bytes(), new_path.read_bytes()
    edits = profile_schema.diff_sections(old, new)
    return ['SETTING ' + line for line in profile_schema.describe(old, edits)]


def header(lines, limit=40):
    """Text block for the top of the export preview."""
    if not lines:
        return 'No changes.'
    text = 'What will change on the scanner:\n' + '\n'.join('  • ' + l for l in lines[:limit])
    if len(lines) > limit:
        text += '\n  … and %d more change(s); see technical details' % (len(lines) - limit)
    return text
