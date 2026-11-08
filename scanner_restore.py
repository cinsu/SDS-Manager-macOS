# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Verified exact configuration restoration with temporary emergency recovery."""
from pathlib import Path
import json
import hashlib
import os
import shutil
from scanner_backup import backup_scanner, digest
from datetime import datetime, timezone
from scanner_first_write import _safe_root, _identity, _stage_and_replace, MIN_FREE_MARGIN
from scanner_preflight import inspect_scanner
from scanner_export_preview import _files

BACKUPS = Path.home()/'.local/share/sds100-database-favorites-manager/scanner-backups'
EMERGENCY = Path.home()/'.local/share/sds100-database-favorites-manager/emergency-restore-backups'


def verify_backup(folder, backup_root=None, hash_files=True):
    folder = Path(folder).expanduser().absolute()
    if folder.is_symlink() or folder.parent.resolve() != (Path(backup_root) if backup_root is not None else BACKUPS).resolve():
        raise ValueError('Select a direct child of the application scanner-backups folder.')
    manifest_path = folder/'manifest.json'
    if manifest_path.is_symlink(): raise ValueError('Unsafe manifest symlink.')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    entries = manifest.get('files')
    if not manifest.get('verified') or not isinstance(entries, list) or not entries or manifest.get('file_count') != len(entries):
        raise ValueError('Invalid backup manifest.')
    found = set()
    for entry in entries:
        rel = entry['path']
        p = Path(rel)
        if p.is_absolute() or '..' in p.parts or rel in found or not rel or '\\' in rel:
            raise ValueError('Unsafe or duplicate backup path.')
        found.add(rel)
        source = folder/'BCDx36HP'/p
        if any(part.is_symlink() for part in (source, *source.parents) if part == folder or folder in part.parents):
            raise ValueError('Backup symlink detected.')
        if not source.is_file() or source.stat().st_size != entry['size'] or (hash_files and digest(source) != entry['sha256']):
            raise ValueError('Backup file missing or checksum mismatch: '+rel)
    return manifest


def list_backups(verify=True):
    """Backups with a valid manifest.  verify=False checks structure and sizes only (instant);
    prepare_restore and execute_restore always re-verify every SHA-256 before anything is used."""
    if not BACKUPS.is_dir(): return []
    result = []
    for folder in sorted(BACKUPS.iterdir(), reverse=True):
        if not folder.is_dir() or folder.is_symlink(): continue
        try: result.append((folder, verify_backup(folder, hash_files=verify)))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError): continue
    return result


def prepare_restore(folder, location, backup_root=None):
    manifest = verify_backup(folder, backup_root)
    scanner = _safe_root(location)
    report, valid = inspect_scanner(scanner)
    if not valid: raise ValueError('Scanner preflight failed: '+report[:500])
    identity = _identity(scanner)
    current = _files(scanner)
    desired = {e['path']: e for e in manifest['files']}
    changed = []
    for rel, entry in sorted(desired.items()):
        target = scanner/rel
        if target.is_symlink() or target.parent.is_symlink(): raise ValueError('Unsafe scanner target: '+rel)
        if rel not in current or digest(current[rel]) != entry['sha256']:
            changed.append({'path':rel, 'action':'REPLACE' if rel in current else 'ADD',
                            'new_sha256':entry['sha256'],
                            'old_sha256':digest(current[rel]) if rel in current else None,
                            'size':entry['size']})
    delete = sorted(set(current)-set(desired))
    if shutil.disk_usage(scanner).free < sum(e['size'] for e in changed) + MIN_FREE_MARGIN:
        raise ValueError('Insufficient scanner free space for restoration.')
    if os.statvfs(scanner).f_flag & getattr(os, 'ST_RDONLY', 1):
        raise ValueError('Scanner mount is read-only.')
    return {'backup':str(Path(folder).resolve()), 'scanner':str(scanner), 'identity':identity,
            'changes':changed, 'delete':delete, 'manifest':manifest}


def emergency_backups():
    if not EMERGENCY.is_dir(): return []
    result=[]
    for folder in sorted(EMERGENCY.iterdir(), reverse=True):
        if folder.is_dir() and not folder.is_symlink() and (folder/'manifest.json').is_file():
            result.append(folder)
    return result


def remove_emergency(folder):
    folder=Path(folder).absolute()
    if folder.parent.resolve()!=EMERGENCY.resolve() or folder.is_symlink() or not folder.name.startswith('EMERGENCY-PRE-RESTORE-'):
        raise ValueError('Not an application emergency backup')
    shutil.rmtree(folder)


def execute_restore(folder, location, backup_root=None):
    first=prepare_restore(folder, location, backup_root)
    if not first['changes'] and not first['delete']:
        return {'changed':0,'deleted':0,'emergency':None}
    scanner=Path(first['scanner'])
    emergency, manifest=backup_scanner(scanner, backup_base=EMERGENCY)
    labelled=emergency.with_name('EMERGENCY-PRE-RESTORE-'+emergency.name)
    emergency.rename(labelled)
    emergency=labelled
    try:
        if prepare_restore(folder,location,backup_root)!=first:
            raise RuntimeError('Scanner or selected backup changed during emergency backup.')
        original={e['path']:e for e in manifest['files']}
        for change in first['changes']:
            if change['old_sha256'] is not None and original.get(change['path'],{}).get('sha256')!=change['old_sha256']:
                raise RuntimeError('Emergency backup mismatch: '+change['path'])
        for rel in first['delete']:
            if rel not in original: raise RuntimeError('Emergency backup missing: '+rel)
        for change in first['changes']:
            if _identity(scanner)!=first['identity']: raise RuntimeError('Scanner identity changed.')
            rel=change['path'];target=scanner/rel
            if (digest(target) if target.is_file() else None)!=change['old_sha256']:
                raise RuntimeError('Scanner file changed: '+rel)
            source=Path(first['backup'])/'BCDx36HP'/rel
            payload=source.read_bytes()
            if hashlib.sha256(payload).hexdigest()!=change['new_sha256']:
                raise RuntimeError('Restore source changed: '+rel)
            target.parent.mkdir(parents=True,exist_ok=True)
            _stage_and_replace(target,payload,change['new_sha256'])
        for rel in first['delete']:
            if _identity(scanner)!=first['identity']: raise RuntimeError('Scanner identity changed.')
            target=scanner/rel
            if target.is_symlink() or digest(target)!=original[rel]['sha256']:
                raise RuntimeError('Unexpected file before deletion: '+rel)
            target.unlink()
        expected={e['path']:e['sha256'] for e in first['manifest']['files']}
        actual=_files(scanner)
        if set(actual)!=set(expected) or any(digest(actual[rel])!=sha for rel,sha in expected.items()):
            raise RuntimeError('Post-restore inventory or SHA-256 verification failed.')
        return {'changed':len(first['changes']),'deleted':len(first['delete']),
                'emergency':str(emergency)}
    except Exception as exc:
        raise RuntimeError('Restore failed. KEEP emergency backup: '+str(emergency)+
            '. Reconnect scanner and use Recover Using Emergency Backup. Reason: '+str(exc)) from exc


def recover_emergency(folder, location):
    folder=Path(folder).absolute()
    if folder.parent.resolve()!=EMERGENCY.resolve() or not folder.name.startswith('EMERGENCY-PRE-RESTORE-'):
        raise ValueError('Invalid emergency backup location')
    # Recovery uses the same validated restoration engine, without mutating global
    # backup configuration or affecting the permanent verified backup history.
    verify_backup(folder, EMERGENCY)
    return execute_restore(folder, location, backup_root=EMERGENCY)
