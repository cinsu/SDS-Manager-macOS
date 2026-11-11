# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Verified SDS100 export for supported edits to existing Favorites HPD files.

Multi-file batches are backed up, verified, and rolled back on caught failures.
"""
import mac_platform  # macOS: full flush to the SD card, no-overwrite rename
from pathlib import Path
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone

from scanner_backup import backup_scanner, digest
from scanner_configurations import list_configurations, verify_configuration
from scanner_export_preview import _files, _without_master_database
from scanner_favorites_expanded import assess_expanded_hpd_replacement
from scanner_profile_export import assess_profile_replacement
from scanner_identity import collect_identity_evidence
from scanner_preflight import inspect_scanner
from scanner_list_sync import (is_list_file, INDEX_FILE, assess_new_hpd, assess_flist_replacement,
                               recorded_deletions, mark_deletions_exported)

# Practical SDS100 USB identity established on the user's device. Not crypto.
SDS100_USB = ('1965', '001c', 'uniden america corp.', 'sds100')
SDS150_USB = ('1965', '001a', 'uniden america corp.', 'sds150')    # observed on a real SDS150 (macOS fork)
KNOWN_SCANNERS_USB = (SDS100_USB, SDS150_USB)
MIN_FREE_MARGIN = 32 * 1024 * 1024


class FirstWriteError(RuntimeError):
    pass


def _identity(scanner):
    evidence = collect_identity_evidence(scanner)
    if evidence.get('status') != 'USB_CORRELATED':
        raise ValueError('Scanner mount is not correlated to a USB block device.')
    observed = (evidence.get('vid', '').lower(), evidence.get('pid', '').lower(),
                evidence.get('manufacturer', '').strip().lower(),
                evidence.get('product_name', '').strip().lower())
    if observed not in KNOWN_SCANNERS_USB:
        raise ValueError('USB identity does not match a previously observed SDS100 or SDS150.')
    if evidence.get('filesystem', '').lower() != 'vfat':
        raise ValueError('Expected an SDS100 FAT32/vfat filesystem.')
    if not evidence.get('serial_present'):
        raise ValueError('SDS100 USB serial descriptor was not available.')
    if Path(evidence['mountpoint']).resolve() != scanner.parent.resolve():
        raise ValueError('Selected BCDx36HP is not at the root of the identified USB mount.')
    if evidence.get('mount_root') != '/' or not evidence.get('source', '').startswith('/dev/'):
        raise ValueError('Scanner location is not a full removable block-device mount.')
    return {key:evidence.get(key) for key in ('mountpoint', 'source', 'device', 'vid', 'pid')}


def _safe_root(location):
    selected = Path(location).expanduser().absolute()
    if selected.is_symlink():
        raise ValueError('Scanner mount symlinks are not allowed.')
    root = selected if selected.name.lower() == 'bcdx36hp' else selected/'BCDx36HP'
    if root.is_symlink() or root.parent.is_symlink():
        raise ValueError('Scanner folder or mount is a symbolic link.')
    return root.resolve(strict=True)


def prepare_first_write(configuration, location):
    """READ ONLY. Recomputed before and after fresh backup and just before write."""
    config = Path(configuration).expanduser().resolve(strict=True)
    recognized = {folder.resolve(): data for folder, data in list_configurations()}
    if config not in recognized or config.is_symlink():
        raise ValueError('Choose a saved configuration in the application library.')
    verify_configuration(config, recognized[config])
    scanner = _safe_root(location)
    report, valid = inspect_scanner(scanner)
    if not valid:
        raise ValueError('Scanner configuration preflight failed: ' + report[:700])
    identity = _identity(scanner)
    local = config/'BCDx36HP'
    if local.is_symlink() or not local.is_dir():
        raise ValueError('Local BCDx36HP folder missing or unsafe.')
    sources, targets = _without_master_database(_files(local)), _without_master_database(_files(scanner))
    if not sources or not targets:
        raise ValueError('Local/scanner configuration files missing.')
    # Lists created in this program are ADDED (file + index row); lists deleted in this program,
    # and still byte-identical on the scanner to what was deleted, are REMOVED. Anything else that
    # exists only on one side is not exported (scanner-only files are retained).
    added = sorted(name for name in sources if name not in targets and name != 'app_data.cfg')
    for name in added:
        if not is_list_file(name):
            raise ValueError('First write supports adding only new Favorites List .hpd files: ' + name)
    recorded = recorded_deletions(config)
    deleted = sorted(name for name in targets
                     if name not in sources and name in recorded and is_list_file(name)
                     and digest(targets[name]) == recorded[name])
    # app_data.cfg contains volatile scanner operating state, not an editable export target.
    changes = [name for name in sorted(sources)
               if name != 'app_data.cfg' and name in targets and digest(sources[name]) != digest(targets[name])]
    if not changes and not added and not deleted:
        raise ValueError('No changed scanner configuration files found.')
    if (added or deleted) and INDEX_FILE not in changes:
        raise ValueError('Added or deleted Favorites Lists require a matching change to f_list.cfg.')
    plans = []
    total_bytes = 0

    def common_checks(relative):
        for item in (sources.get(relative), targets.get(relative)):
            if item is not None and (item.is_symlink() or item.parent.is_symlink()):
                raise ValueError('Symlink file or directory is not supported.')

    for relative in added:  # 1. new list files first
        common_checks(relative)
        proposed = sources[relative].read_bytes()
        valid, detail = assess_new_hpd(proposed)
        if not valid:
            raise ValueError('Unsupported new Favorites List ' + relative + ': ' + detail)
        total_bytes += len(proposed)
        plans.append({'action': 'add', 'relative': relative,
                      'source_sha256': hashlib.sha256(proposed).hexdigest(), 'target_sha256': None,
                      'bytes': len(proposed), 'changes': {'field_edits': 0, 'added': 0, 'deleted': 0, 'new_file': 1}})
    ordered = [n for n in changes if n != INDEX_FILE] + ([INDEX_FILE] if INDEX_FILE in changes else [])
    for relative in ordered:  # 2. edits to existing files, then the list index
        is_hpd = (relative.startswith('favorites_lists/') and relative.count('/') == 1
                  and relative.lower().endswith('.hpd'))
        if not is_hpd and relative not in ('profile.cfg', INDEX_FILE):
            raise ValueError('Unsupported scanner settings file: ' + relative)
        common_checks(relative)
        original, proposed = targets[relative].read_bytes(), sources[relative].read_bytes()
        if is_hpd:
            valid, detail, counts = assess_expanded_hpd_replacement(original, proposed)
            if not valid:
                # v0.1.13: larger edits (new or deleted departments and systems, pasted entries, several
                # kinds of change at once) are checked as a complete Favorites List instead, with the same
                # checks as a brand-new list, which match lists confirmed working on a real SDS100.
                whole_ok, whole_detail = assess_new_hpd(proposed, original)
                if whole_ok:
                    valid, detail = True, 'checked as a complete Favorites List (' + whole_detail.replace(
                        'new list with ', '') + ')'
                    counts = {'field_edits': 0, 'added': 0, 'deleted': 0, 'whole_list': 1}
                else:
                    detail = whole_detail
        elif relative == INDEX_FILE:
            valid, detail, counts = assess_flist_replacement(original, proposed, added, deleted)
        else:
            valid, detail, counts = assess_profile_replacement(original, proposed)
        if not valid:
            label = {True: 'Unsupported Favorites HPD change'}.get(is_hpd) or (
                'Unsupported Favorites List index (f_list.cfg) change' if relative == INDEX_FILE
                else 'Only existing native Favorites HPD or supported profile.cfg edits allowed')
            raise ValueError(label + ' in ' + relative + ': ' + detail)
        total_bytes += len(proposed)
        plans.append({'action': 'replace', 'relative': relative,
                      'source_sha256': hashlib.sha256(proposed).hexdigest(),
                      'target_sha256': hashlib.sha256(original).hexdigest(),
                      'bytes': len(proposed), 'changes': counts})
    for relative in deleted:  # 3. removals last, only after the index no longer lists them
        common_checks(relative)
        plans.append({'action': 'delete', 'relative': relative, 'source_sha256': None,
                      'target_sha256': recorded[relative], 'bytes': 0,
                      'changes': {'field_edits': 0, 'added': 0, 'deleted': 0, 'removed_file': 1}})
    if shutil.disk_usage(scanner).free < total_bytes + MIN_FREE_MARGIN:
        raise ValueError('Insufficient FAT32 free space for staged writes and safety margin.')
    try:
        flags = os.statvfs(scanner).f_flag
        if flags & getattr(os, 'ST_RDONLY', 1):
            raise ValueError('Scanner filesystem is mounted read-only.')
    except OSError as exc:
        raise ValueError('Cannot inspect scanner mount flags: ' + str(exc)) from exc
    return {'configuration': str(config), 'scanner': str(scanner),
            'files': plans, 'identity': identity}


def first_write_eligibility(configuration, location):
    """Return a readable reason and authorization for the UI; never write."""
    try:
        plan = prepare_first_write(configuration, location)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return False, str(exc)
    descriptions = []
    for item in plan['files']:
        if item['action'] == 'add':
            descriptions.append(f'{item["relative"]}: NEW Favorites List file')
        elif item['action'] == 'delete':
            descriptions.append(f'{item["relative"]}: Favorites List REMOVED (deleted in this program)')
        elif item['changes'].get('whole_list'):
            descriptions.append(f'{item["relative"]}: changed list, checked as a complete Favorites List')
        else:
            descriptions.append(f'{item["relative"]}: {item["changes"]["field_edits"]} field edits, '
                                f'{item["changes"]["added"]} additions, {item["changes"]["deleted"]} deletions')
    if all(i['action'] == 'replace' and i['relative'].endswith('.hpd') for i in plan['files']):
        label = 'existing Favorites HPD file(s)'
    elif all(i['action'] == 'replace' for i in plan['files']):
        label = 'existing native configuration file(s)'
    else:
        label = 'file change(s) including new or removed Favorites Lists'
    return True, (f'Eligible: {len(descriptions)} {label}:\n' +
                  '\n'.join(descriptions) +
                  '\nFresh verified backup will be created BEFORE writing.')


def _sync_dir(directory):
    """Best-effort metadata sync; vfat directory fsync support varies."""
    try:
        fd = os.open(directory, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def _stage_and_replace(destination, payload, expected_hash):
    """Stage to same directory; verify; rename; verify final bytes."""
    fd, stage_name = tempfile.mkstemp(prefix='.sds100-export-', suffix='.tmp', dir=destination.parent)
    stage = Path(stage_name)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        if digest(stage) != expected_hash:
            raise OSError('Staged file SHA-256 mismatch; destination unchanged.')
        if destination.is_symlink():
            raise OSError('Destination became a symlink; replacement cancelled.')
        os.replace(stage, destination)
        _sync_dir(destination.parent)
        if digest(destination) != expected_hash:
            raise OSError('Post-write SHA-256 mismatch.')
    finally:
        stage.unlink(missing_ok=True)


def _remove_file(destination):
    if destination.is_symlink():
        raise OSError('Destination became a symlink; removal cancelled.')
    destination.unlink()
    _sync_dir(destination.parent)
    if destination.exists():
        raise OSError('File still present after removal.')


def _undo(item, destination, backup_folder):
    """Return one file to its state before this export."""
    if item['action'] == 'add':
        if destination.exists():
            _remove_file(destination)
        return
    original = (backup_folder/'BCDx36HP'/item['relative']).read_bytes()
    if hashlib.sha256(original).hexdigest() != item['target_sha256']:
        raise OSError('Backup checksum mismatch')
    if not destination.exists() or digest(destination) != item['target_sha256']:
        _stage_and_replace(destination, original, item['target_sha256'])


def execute_first_write(configuration, location):
    """Confirmed batch export. Verify all files before writing; roll back batch on failure.

    Order: new list files, edited files, f_list.cfg, then removed lists. An interruption therefore
    leaves at worst an unreferenced list file, never an index row pointing at a missing file.
    """
    first = prepare_first_write(configuration, location)
    backup_folder = None
    scanner = Path(first['scanner'])
    written = []
    try:
        backup_folder, manifest = backup_scanner(scanner)
        entries = {entry['path']: entry for entry in manifest['files']}
        for item in first['files']:
            relative = item['relative']
            if item['action'] == 'add':
                if relative in entries or (scanner/relative).exists():
                    raise FirstWriteError('A file named ' + relative + ' already exists on the scanner.')
                continue
            entry = entries.get(relative)
            backup_file = backup_folder/'BCDx36HP'/relative
            if entry is None or entry['sha256'] != item['target_sha256'] or digest(backup_file) != item['target_sha256']:
                raise FirstWriteError('Fresh scanner backup verification failed: ' + relative)
        second = prepare_first_write(configuration, location)
        if second != first:
            raise FirstWriteError('Scanner, configuration, or USB device changed during backup; write cancelled.')
        payloads = []
        for item in first['files']:
            relative = item['relative']
            destination = scanner/relative
            if item['action'] == 'delete':
                if digest(destination) != item['target_sha256']:
                    raise FirstWriteError('File changed before removal: ' + relative)
                payloads.append((item, destination, None))
                continue
            proposed = (Path(first['configuration'])/'BCDx36HP'/relative).read_bytes()
            if hashlib.sha256(proposed).hexdigest() != item['source_sha256']:
                raise FirstWriteError('File changed before write: ' + relative)
            if item['action'] == 'add':
                if destination.exists():
                    raise FirstWriteError('File appeared before write: ' + relative)
            elif digest(destination) != item['target_sha256']:
                raise FirstWriteError('File changed before write: ' + relative)
            payloads.append((item, destination, proposed))
        if _identity(scanner) != first['identity']:
            raise FirstWriteError('USB device changed before write.')
        receipt = backup_folder/'EXPORT_RECOVERY.txt'
        lines = []
        for item in first['files']:
            lines.append({'add': 'ADDED (delete to undo): ', 'delete': 'REMOVED (restore from backup): ',
                          'replace': 'REPLACED (restore from backup): '}[item['action']] + 'BCDx36HP/' + item['relative'] + '\n')
        receipt.write_text('Verified original scanner configuration backup: ' + str(backup_folder) + '\n'
                           'Changes in this export:\n' + ''.join(lines) +
                           'To recover, restore ALL listed replaced/removed files from the BCDx36HP folder in this backup '
                           'and delete the added files.\n', encoding='utf-8')
        with receipt.open('rb') as stream:
            os.fsync(stream.fileno())
        _sync_dir(backup_folder)
        try:
            for item, destination, proposed in payloads:
                # Include current file even if the change succeeds then verification fails.
                written.append((item, destination))
                if _identity(scanner) != first['identity']:
                    raise OSError('Scanner changed during batch export.')
                if item['action'] == 'add':
                    if destination.exists():
                        raise OSError('Scanner changed during batch export.')
                    _stage_and_replace(destination, proposed, item['source_sha256'])
                elif item['action'] == 'delete':
                    if digest(destination) != item['target_sha256']:
                        raise OSError('Scanner changed during batch export.')
                    _remove_file(destination)
                else:
                    if digest(destination) != item['target_sha256']:
                        raise OSError('Scanner changed during batch export.')
                    _stage_and_replace(destination, proposed, item['source_sha256'])
        except Exception as exc:
            errors = []
            for item, destination in reversed(written):
                try:
                    _undo(item, destination, backup_folder)
                except Exception as restore_error:
                    errors.append(item['relative'] + ': ' + str(restore_error))
            if errors:
                raise FirstWriteError('Batch write/rollback failed. DO NOT DISCONNECT; manually restore ALL '
                                      'files from ' + str(backup_folder) + ': ' + '; '.join(errors)) from exc
            raise FirstWriteError('Batch write failed; original HPD restored from verified backup (all changed files). '
                                  + str(exc)) from exc
        try:
            os.sync()       # push every cached write to the card now, not when the OS gets round to it
        except (AttributeError, OSError):
            pass
        removed = [item['relative'] for item in first['files'] if item['action'] == 'delete']
        if removed:
            mark_deletions_exported(first['configuration'], removed)
        result = {'file': first['files'][0]['relative'],
                  'files': [item['relative'] for item in first['files']],
                  'added': [item['relative'] for item in first['files'] if item['action'] == 'add'],
                  'removed': removed,
                  'backup': str(backup_folder),
                  'written_bytes': sum(item['bytes'] for item in first['files']),
                  'written_utc': datetime.now(timezone.utc).isoformat(),
                  'device': first['identity']['source']}
        if len(first['files']) == 1 and first['files'][0]['action'] == 'replace':
            result.update({key: first['files'][0][key] for key in
                           ('changes', 'source_sha256', 'target_sha256')})
            result['old_sha256'] = result['target_sha256']
            result['new_sha256'] = result['source_sha256']
        try:
            import export_state         # the scanner now matches this configuration (v0.1.20)
            export_state.record(first['configuration'], 'exported')
        except Exception:
            pass
        try:
            (backup_folder/'EXPORT_RESULT.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        except OSError:
            pass
        return result
    except Exception as exc:
        if isinstance(exc, FirstWriteError):
            raise
        raise FirstWriteError(str(exc) + (f'\nVerified backup: {backup_folder}' if backup_folder else
                                         '\nNo scanner write was attempted before backup verification.')) from exc
