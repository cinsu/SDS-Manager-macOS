# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Read display labels from the active database's StateInfo records (read-only)."""
from pathlib import Path
import re

_STATE_ID = re.compile(r'^StateId=(\d+)$', re.I)
_NAME_KEYS = ('StateName=', 'Name=')


def load_state_names(database_folder):
    """Return {numeric StateId: name}; tolerate missing/malformed metadata."""
    master = Path(database_folder) / 'MasterHpdb.hp1'
    if not master.is_file():
        return {}
    names = {}
    with master.open('r', encoding='cp1252', errors='replace', newline='') as source:
        for line in source:
            if not line.startswith('StateInfo\t'):
                continue
            fields = line.rstrip('\r\n').split('\t')[1:]
            ids = [int(m.group(1)) for field in fields if (m := _STATE_ID.fullmatch(field))]
            if len(ids) != 1:
                continue
            candidates = []
            for field in fields:
                if _STATE_ID.fullmatch(field):
                    continue
                if any(field.startswith(prefix) for prefix in _NAME_KEYS):
                    candidates.insert(0, field.split('=', 1)[1].strip())
                elif '=' not in field and field.strip():
                    candidates.append(field.strip())
            if candidates:
                names[ids[0]] = candidates[0]
    return names


def state_display_name(path, names):
    identifier = int(Path(path).stem[2:])
    if identifier == 0:
        return 'Nationwide Systems (000000)'
    name = names.get(identifier)
    return f'{name} ({identifier:06d})' if name else f'State Database ({identifier:06d})'
