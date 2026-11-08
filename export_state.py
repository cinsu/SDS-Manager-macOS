# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Is the scanner up to date with a saved configuration? (v0.1.20)

SDS-Manager remembers a fingerprint of a configuration's Favorites Lists (f_list.cfg and the
favorites_lists/*.hpd files) whenever the scanner and the configuration are known to match: after it
was read from the scanner, and after a successful Export to Scanner. If the saved lists differ from that
fingerprint, they have been saved but not exported. Kept beside the configuration library in
export-state.json, never on the scanner. Pure; no Qt. Best effort: a failure never stops the Manager.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path


def state_path():
    from scanner_configurations import library_path
    return library_path().parent / 'export-state.json'


def fingerprint(configuration):
    """sha256 over the configuration's Favorites Lists; '' when it has none."""
    root = Path(configuration) / 'BCDx36HP'
    files = [root / 'favorites_lists' / 'f_list.cfg'] if (root / 'favorites_lists' / 'f_list.cfg').is_file() else []
    files += sorted((root / 'favorites_lists').glob('*.hpd'), key=lambda p: p.name.casefold())
    if not files:
        return ''
    total = hashlib.sha256()
    for path in files:
        total.update(path.name.casefold().encode() + b'\0')
        total.update(hashlib.sha256(path.read_bytes()).digest())
    return total.hexdigest()


def _key(configuration):
    return str(Path(configuration).resolve())


def _load(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def record(configuration, how, path=None, when=None):
    """Remember that the scanner now matches this configuration ('read' or 'exported')."""
    path = Path(path or state_path())
    try:
        data = _load(path)
        try:
            import scanner_avoids                 # v0.1.21: the avoids when they matched
            avoids = scanner_avoids.configuration_avoids(configuration)
        except Exception:
            avoids = None
        data[_key(configuration)] = {'fingerprint': fingerprint(configuration), 'how': how,
                                     'when': (when or datetime.datetime.now()).isoformat(timespec='seconds'),
                                     'avoids': avoids}
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data, indent=1) + '\n', encoding='utf-8')
        os.replace(temporary, path)
        return True
    except (OSError, ValueError, UnicodeError):
        return False


def state(configuration, path=None):
    """{'state': 'exported' | 'changed' | 'unknown', 'how': 'read'/'exported'/'', 'when': iso or '',
        'saved': iso of the newest saved list file or ''} for SDS100 Monitor and the status bar."""
    entry = _load(path or state_path()).get(_key(configuration)) or {}
    root = Path(configuration) / 'BCDx36HP' / 'favorites_lists'
    try:
        newest = max((p.stat().st_mtime for p in root.glob('*') if p.is_file()), default=None)
        current = fingerprint(configuration)
    except OSError:
        newest, current = None, ''
    saved = datetime.datetime.fromtimestamp(newest).isoformat(timespec='seconds') if newest else ''
    if not entry.get('fingerprint'):
        kind = 'unknown'
    else:
        kind = 'exported' if entry['fingerprint'] == current else 'changed'
    return {'state': kind, 'how': entry.get('how', ''), 'when': entry.get('when', ''), 'saved': saved}


def matched_avoids(configuration, path=None):
    """{filename: {key: avoid}} from when scanner and configuration last matched, or None (v0.1.21)."""
    avoids = (_load(path or state_path()).get(_key(configuration)) or {}).get('avoids')
    return avoids if isinstance(avoids, dict) else None


def describe(info):
    """One line for SDS-Manager's status bar and SDS100 Monitor."""
    when = (info.get('when') or '').replace('T', ' ')[:16]
    if info.get('state') == 'exported':
        return 'Scanner is up to date (%s %s).' % ('read from the scanner' if info.get('how') == 'read'
                                                    else 'exported', when)
    if info.get('state') == 'changed':
        return ('Saved changes not exported to the scanner yet (last %s %s).'
                % ('read from the scanner' if info.get('how') == 'read' else 'export', when))
    return 'Not known whether the scanner matches this configuration (no export recorded yet).'
