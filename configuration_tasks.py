# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Managing scanner configurations and their Favorites Lists (v0.1.7).

New configuration (the settings of another one, with no Favorites Lists), duplicating a list, copying a
list to another configuration, importing a Favorites List file (.hpd) and putting the lists in a new order.
Everything here works on local configurations only and goes through the same checked, backed-up writes as
the rest of the program (scanner_configurations); nothing touches the scanner until Export to Scanner.
"""
import hashlib
import json
import os
from pathlib import Path

import scanner_configurations as sc

FAVORITES = 'BCDx36HP/favorites_lists/'


def _manifest(folder):
    root = Path(folder).expanduser().resolve(strict=True)
    manifest = json.loads((root / 'configuration.json').read_text(encoding='utf-8'))
    sc.verify_configuration(root, manifest)
    return root, manifest


def lists_in_order(folder):
    """[{'name', 'filename', 'relative'}] in the order of f_list.cfg (the scanner's order)."""
    root, manifest = _manifest(folder)
    raw, lines, _newline = sc._index_text(root)
    found = []
    for line in lines:
        fields = line.split('\t')
        if fields and fields[0] == 'F-List' and len(fields) > 2:
            relative = FAVORITES + fields[2]
            if relative in manifest['files']:
                found.append({'name': fields[1], 'filename': fields[2], 'relative': relative})
    return found


def read_list_rows(path):
    """(rows, encoding) of a Favorites List file, checked as a list the scanner accepts."""
    from scanner_list_sync import assess_new_hpd
    path = Path(path)
    if path.stat().st_size > 25 * 1024 * 1024:
        raise ValueError(f'{path.name} is larger than 25 MB.')
    data = path.read_bytes()
    for encoding in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            text = data.decode(encoding)
            break
        except UnicodeError:
            continue
    rows = [line.split('\t') for line in text.splitlines() if line != '']
    if not rows or rows[0][0] != 'TargetModel':
        raise ValueError(f'{path.name} is not an SDS100 Favorites List file.')
    if not any(r[0] in ('Conventional', 'Trunk') for r in rows):
        raise ValueError(f'{path.name} has no systems in it.')
    try:
        data = ('\r\n'.join('\t'.join(r) for r in rows) + '\r\n').encode('cp1252')
    except UnicodeError:
        raise ValueError(f'{path.name} uses characters an SDS100 list can\'t store.') from None
    valid, detail = assess_new_hpd(data)[:2]
    if not valid:
        raise ValueError(f'{path.name} did not pass the checks for a Favorites List: {detail}')
    return rows, 'cp1252'


def free_name(folder, wanted):
    """wanted, or 'wanted (2)', 'wanted (3)' ... if a list already has that name."""
    names = {l['name'].strip().casefold() for l in lists_in_order(folder)}
    wanted = wanted.strip()[:64] or 'Favorites List'
    if wanted.casefold() not in names:
        return wanted
    for n in range(2, 1000):
        candidate = f'{wanted[:58]} ({n})'
        if candidate.casefold() not in names:
            return candidate
    raise ValueError('No free name for the list.')


def add_list(folder, name, rows, encoding='cp1252'):
    """Add a Favorites List with these rows. Its quick key, number tag and startup keys start Off,
    so it never clashes with the lists already there."""
    return sc.create_local_favorites_list(folder, name, rows, encoding, '\r\n')


def duplicate_list(folder, relative, new_name, target=None):
    """Copy a saved list, under a new name, into this configuration or another one (target)."""
    root, manifest = _manifest(folder)
    if relative not in manifest['files']:
        raise ValueError('That Favorites List is not in the configuration.')
    rows, encoding = read_list_rows(root / relative)
    return add_list(target or root, new_name, rows, encoding)


def import_list_file(folder, path, name):
    rows, encoding = read_list_rows(path)
    return add_list(folder, name, rows, encoding)


def reorder_lists(folder, filenames):
    """Put the Favorites Lists in this order (all of them, each once). The previous index is backed up."""
    root, manifest = _manifest(folder)
    raw, lines, newline = sc._index_text(root)
    if raw is None or sc.INDEX_KEY not in manifest['files']:
        raise ValueError('This configuration has no Favorites List index.')
    rows = {l.split('\t')[2].lower(): l for l in lines if l.startswith('F-List\t')}
    present = {item['filename'].lower() for item in lists_in_order(root)}
    wanted = [f.lower() for f in filenames]
    if sorted(wanted) != sorted(present) or len(set(wanted)) != len(wanted):
        raise ValueError('The new order must list every Favorites List once.')
    other = [l for l in lines if not l.startswith('F-List\t')]
    absent = [l for f, l in rows.items() if f not in present]       # rows without a file stay at the end
    ending = raw.endswith((b'\r', b'\n'))
    payload = newline.join(other + [rows[f] for f in wanted] + absent) + (newline if ending else '')
    payload = payload.encode('cp1252')
    if payload == raw:
        return False
    digest = hashlib.sha256(raw).hexdigest()
    backups = sc.library_path().parent / 'scanner-configuration-backups' / root.name
    backups.mkdir(parents=True, exist_ok=True)
    saved = backups / ('f_list.' + digest[:12] + '.cfg')
    if not saved.exists():
        with saved.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    sc._commit_files(root, manifest, {sc.INDEX_KEY: payload})
    return True


def new_configuration(source, name):
    """A new local configuration with the settings of source and no Favorites Lists.

    It is made as a copy of source with every list then deleted the normal way: each deleted list is
    archived, and exporting the new configuration to the scanner it came from removes those lists there
    too (after the usual backup). Returns (folder, manifest)."""
    destination, _manifest_ = sc.save_configuration_as(source, name)
    try:
        for item in lists_in_order(destination):
            sc.delete_local_favorites_list(destination, item['relative'])
        root, manifest = _manifest(destination)
        manifest['created_without_lists_from'] = Path(source).name
        manifest_path = root / 'configuration.json'
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        return root, manifest
    except BaseException:
        sc.delete_local_configuration(destination)
        raise
