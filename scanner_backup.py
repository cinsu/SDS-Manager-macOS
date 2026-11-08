# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Verified read-only scanner configuration backup, no scanner writes."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import shutil
import tempfile
from scanner_configurations import CONFIG_FILES, CONFIG_DIRS
from scanner_preflight import inspect_scanner

CHUNK = 1024 * 1024

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b''):
            h.update(chunk)
    return h.hexdigest()

def backup_scanner(path, backup_base=None):
    report, valid = inspect_scanner(path)
    if not valid:
        raise ValueError('Scanner preflight failed.\n' + report)
    selected = Path(path).expanduser().resolve()
    root = selected if selected.name.lower() == 'bcdx36hp' else selected / 'BCDx36HP'
    if root.is_symlink():
        raise ValueError('Symbolic-link scanner root is not supported.')
    files = []
    for name in CONFIG_FILES:
        f = root / name
        if f.is_symlink(): raise ValueError('Symlink rejected: ' + name)
        if f.is_file(): files.append(f)
    for name in CONFIG_DIRS:
        folder = root / name
        if folder.is_symlink(): raise ValueError('Symlink rejected: ' + name)
        if not folder.exists(): continue
        for item in sorted(folder.rglob('*')):
            if item.is_symlink(): raise ValueError('Symlink rejected: ' + str(item.relative_to(root)))
            if item.is_file():
                if name == 'favorites_lists' and item.suffix.lower() not in ('.hpd', '.cfg'):
                    continue
                files.append(item)
    if not files: raise ValueError('No configuration files available to back up.')
    base = Path(backup_base) if backup_base else Path.home()/'.local/share/sds100-database-favorites-manager/scanner-backups'
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    stage = Path(tempfile.mkdtemp(prefix='.backup-in-progress-', dir=base))
    try:
        entries = []
        for source in files:
            rel = source.relative_to(root)
            target = stage / 'BCDx36HP' / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            source_hash_before = digest(source)
            shutil.copyfile(source, target)
            copied_hash = digest(target)
            source_hash_after = digest(source)
            if source_hash_before != copied_hash or source_hash_after != copied_hash:
                raise IOError('Verification failed or scanner file changed: ' + str(rel))
            entries.append({'path':str(rel), 'size':target.stat().st_size, 'sha256':copied_hash})
        manifest = {'created_utc':datetime.now(timezone.utc).isoformat(), 'source':str(root), 'file_count':len(entries), 'files':entries, 'verified':True}
        (stage/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
        for entry in entries:
            target = stage/'BCDx36HP'/entry['path']
            if digest(target) != entry['sha256'] or target.stat().st_size != entry['size']:
                raise IOError('Final backup verification failed: '+entry['path'])
        destination = base/stamp
        i = 2
        while destination.exists():
            destination = base/f'{stamp}-{i}'
            i += 1
        os.rename(stage, destination)
        return destination, manifest
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


# ---- Backup housekeeping (never automatic; always an explicit user action) -------------------------
import re as _re

_STAMP = _re.compile(r'\d{8}T\d{6}Z(-\d+)?')


def backup_base():
    return Path.home() / '.local/share/sds100-database-favorites-manager/scanner-backups'


def _tree_size(folder):
    total = 0
    for item in folder.rglob('*'):
        try:
            if item.is_file() and not item.is_symlink():
                total += item.stat().st_size
        except OSError:
            pass
    return total


def list_backups(base=None):
    """[{'name', 'path', 'bytes'}] oldest first; only real backup folders (timestamp name + manifest.json)."""
    base = Path(base) if base else backup_base()
    found = []
    if not base.is_dir() or base.is_symlink():
        return found
    for item in sorted(base.iterdir(), key=lambda p: p.name):
        if item.is_dir() and not item.is_symlink() and _STAMP.fullmatch(item.name) \
                and (item / 'manifest.json').is_file():
            found.append({'name': item.name, 'path': item, 'bytes': _tree_size(item)})
    return found


def backup_usage(base=None):
    backups = list_backups(base)
    return {'count': len(backups), 'bytes': sum(b['bytes'] for b in backups),
            'newest': backups[-1]['name'] if backups else None}


def plan_prune(keep, base=None):
    """Backups that cleanup would delete: everything but the newest `keep` (at least 3 are always kept)."""
    keep = max(int(keep), 3)
    backups = list_backups(base)
    return backups[:-keep] if len(backups) > keep else []


def prune_backups(names, keep, base=None):
    """Delete the named backups, but only if each is still in a fresh plan for `keep`. Returns names deleted."""
    import shutil
    base = Path(base) if base else backup_base()
    allowed = {b['name']: b for b in plan_prune(keep, base)}
    removed = []
    for name in names:
        entry = allowed.get(name)
        if entry is None:
            continue
        path = entry['path']
        if path.is_symlink() or path.resolve().parent != base.resolve():
            continue
        shutil.rmtree(path)
        removed.append(name)
    return removed
