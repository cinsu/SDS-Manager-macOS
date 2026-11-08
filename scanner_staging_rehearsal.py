# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Read-only, local-only rehearsal of staged scanner configuration replacement.

Copies candidate and existing bytes to a TEMPORARY LOCAL directory, exercises
success and injected-failure rollback there, then removes that directory.
Never opens the scanner for writing and NEVER authorizes scanner export.
"""
from pathlib import Path, PurePosixPath
import hashlib
import os
import shutil
import tempfile

CHUNK = 1024 * 1024
FAT32_MAX_FILE = 2**32 - 1


def _hash(path):
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b''):
            sha.update(chunk)
    return sha.hexdigest()


def _safe_name(name):
    if not isinstance(name, str) or not name or '\\' in name or '\x00' in name:
        raise ValueError('Unsafe or invalid file path in export plan.')
    parts = PurePosixPath(name).parts
    if not parts or any(part in ('', '.', '..') for part in parts) or name.startswith('/'):
        raise ValueError('Unsafe relative file path in export plan: ' + repr(name))
    if PurePosixPath(name).as_posix() != name:
        raise ValueError('Non-canonical export path: ' + repr(name))
    return name


def _copy_verified(src, dest):
    src = Path(src)
    if src.is_symlink() or not src.is_file():
        raise ValueError('Unsafe or missing source file: ' + str(src))
    before = _hash(src)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # No follows through destination symlinks: workspace is newly created.
    with src.open('rb') as inp, dest.open('xb') as out:
        shutil.copyfileobj(inp, out, CHUNK)
        out.flush()
    after = _hash(src)
    if before != after or _hash(dest) != before or dest.stat().st_size != src.stat().st_size:
        raise IOError('Source changed or staging verification failed: ' + str(src))
    return before


def _restore_simulation(sim, baseline, added):
    for rel in added:
        target = sim/rel
        if target.exists(): target.unlink()
    for rel, source in baseline.items():
        target = sim/rel
        if target.exists(): target.unlink()
        _copy_verified(source, target)


def _simulate(stage, baseline, names, additions, workspace, *, fail_after=None):
    sim = workspace/('sim-failure' if fail_after is not None else 'sim-success')
    sim.mkdir()
    for rel, backup in baseline.items():
        _copy_verified(backup, sim/rel)
    try:
        for index, rel in enumerate(names, 1):
            destination = sim/rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists(): destination.unlink()
            _copy_verified(stage/rel, destination)
            if fail_after is not None and index >= fail_after:
                raise IOError('SIMULATED interruption (local files only)')
        if fail_after is None:
            for rel in names:
                if _hash(sim/rel) != _hash(stage/rel):
                    raise IOError('Simulated staged file mismatch: '+rel)
    except IOError as exc:
        if fail_after is None or not str(exc).startswith('SIMULATED interruption'):
            raise
    finally:
        _restore_simulation(sim, baseline, additions)
    if any((sim/rel).exists() for rel in additions):
        raise IOError('Rollback failed to remove simulated addition.')
    if any(_hash(sim/rel) != _hash(backup) for rel,backup in baseline.items()):
        raise IOError('Rollback failed to restore simulated replacement.')


def rehearse_staging(scanner_root, source_files, target_files, changes, *, workspace_base=None):
    """Return a report. This is NOT an actual on-device staging/rollback test.

    `source_files` and `target_files` are read-only paths keyed by scanner-relative
    POSIX paths. `changes` comes from a prior read-only preview comparison.
    """
    scanner_root = Path(scanner_root).resolve(strict=True)
    lines = ['LOCAL STAGING AND ROLLBACK REHEARSAL — READ ONLY', '']
    try:
        if not scanner_root.is_dir(): raise ValueError('Scanner directory missing.')
        base = Path(workspace_base or tempfile.gettempdir()).resolve(strict=True)
        if not base.is_dir(): raise ValueError('Local temporary directory missing.')
        # A workspace on the same filesystem as the scanner would WRITE to it.
        if os.stat(base).st_dev == os.stat(scanner_root).st_dev:
            raise ValueError('Temporary workspace shares the scanner filesystem; refusing rehearsal.')
        if set(changes) != {'ADD', 'REPLACE', 'UNCHANGED', 'RETAIN ON SCANNER'}:
            raise ValueError('Unexpected preview change categories.')
        all_names = list(source_files) + list(target_files)
        for rel in all_names: _safe_name(rel)
        if len({n.casefold() for n in set(all_names)}) != len(set(all_names)):
            raise ValueError('Case-insensitive filename collision (unsafe for FAT32).')
        if any(Path(p).is_symlink() for p in list(source_files.values())+list(target_files.values())):
            raise ValueError('Symlinked source or target file is not allowed.')
        additions = sorted(changes['ADD'])
        replacements = sorted(changes['REPLACE'])
        names = additions + replacements
        if len(names) != len(set(names)):
            raise ValueError('Duplicate changed-file path.')
        if any(rel not in source_files or rel in target_files for rel in additions):
            raise ValueError('ADD plan does not match existing scanner files.')
        if any(rel not in source_files or rel not in target_files for rel in replacements):
            raise ValueError('REPLACE plan does not match existing scanner files.')
        for rel in names:
            if source_files[rel].stat().st_size > FAT32_MAX_FILE:
                raise ValueError('Candidate file exceeds FAT32 file-size limit: ' + rel)
        usage = shutil.disk_usage(scanner_root)
        statvfs = os.statvfs(scanner_root)
        cluster = max(1, statvfs.f_frsize)
        payload = sum(source_files[n].stat().st_size for n in names)
        allocated = sum(((source_files[n].stat().st_size + cluster - 1)//cluster)*cluster for n in names)
        # Conservative planning margin, NOT proof of adequate on-device space.
        margin = max(64*1024*1024, allocated//10 + len(names)*1024*1024)
        estimated = allocated + margin
        lines += [f'Candidate files to stage: {len(names)} ({len(additions)} add, {len(replacements)} replace)',
                  f'Candidate payload: {payload:,} bytes',
                  f'Estimated staged allocation: {allocated:,} bytes (reported block size {cluster:,})',
                  f'Planning margin: {margin:,} bytes',
                  f'Estimated scanner free-space requirement: {estimated:,} bytes',
                  f'Reported scanner free space: {usage.free:,} bytes',
                  'Free-space estimate: '+('SUFFICIENT FOR ESTIMATE ONLY' if usage.free >= estimated else 'INSUFFICIENT / BLOCKED')]
        if usage.free < estimated:
            raise ValueError('Insufficient free space for conservative staging estimate.')
        if not names:
            lines += ['No ADD/REPLACE files in this preview; actual-file rehearsal skipped.',
                      'Scanner writes: 0', 'Export authorization: BLOCKED']
            return '\n'.join(lines), True
        with tempfile.TemporaryDirectory(prefix='sds100-export-rehearsal-', dir=base) as tmp:
            workspace = Path(tmp)
            stage = workspace/'stage'; stage.mkdir()
            backups = workspace/'rollback'; backups.mkdir()
            original_hashes = {rel: _hash(target_files[rel]) for rel in replacements}
            for rel in names: _copy_verified(source_files[rel], stage/rel)
            baseline = {}
            for rel in replacements:
                dest = backups/rel
                _copy_verified(target_files[rel], dest)
                baseline[rel] = dest
            _simulate(stage, baseline, names, additions, workspace)
            _simulate(stage, baseline, names, additions, workspace, fail_after=1)
            if any(_hash(target_files[rel]) != expected for rel, expected in original_hashes.items()):
                raise IOError('Scanner file changed during rehearsal: abort.')
        lines += ['Local staged copies: SHA-256 VERIFIED',
                  'Simulated apply/restore: PASSED (local workspace only)',
                  'Injected interruption and simulated rollback: PASSED (local workspace only)',
                  'Temporary local workspace: REMOVED',
                  'Scanner writes: 0',
                  'On-device FAT32 atomicity, interruption recovery, and actual rollback: NOT VERIFIED',
                  'Export authorization: BLOCKED']
        return '\n'.join(lines), True
    except (OSError, ValueError, RuntimeError) as exc:
        lines += ['Rehearsal: BLOCKED — ' + str(exc), 'Scanner writes: 0',
                  'Export authorization: BLOCKED']
        return '\n'.join(lines), False
