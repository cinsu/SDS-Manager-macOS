# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""v0.0.7m: durable-journal transaction rehearsal on an ISOLATED LOCAL MOCK.

The public entry point ONLY reads scanner/local configuration files. All
transactional writes target a newly created temporary LOCAL mock device.
This is not a FAT32 or physical SDS100 write test, and it cannot authorize one.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from scanner_export_readiness import assess_hpd_frequency_replacement
from scanner_staging_rehearsal import _safe_name

MAX_HPD = 25 * 1024 * 1024
CHUNK = 1024 * 1024


class SimulatedPowerLoss(Exception):
    """Raised without cleanup to emulate a process dying mid-transaction."""


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as inp:
        for chunk in iter(lambda: inp.read(CHUNK), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _sync_dir(path):
    fd = os.open(str(path), os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _copy_sync(source, destination):
    source, destination = Path(source), Path(destination)
    if source.is_symlink() or not source.is_file() or destination.is_symlink():
        raise ValueError('Symlink or missing file rejected in transaction rehearsal')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open('rb') as inp, destination.open('xb') as out:
        shutil.copyfileobj(inp, out, CHUNK)
        out.flush()
        os.fsync(out.fileno())
    _sync_dir(destination.parent)
    if sha(source) != sha(destination):
        raise IOError('Verified copy mismatch')


def _atomic_journal(path, entry):
    temp = path.with_suffix('.tmp')
    with temp.open('x', encoding='utf-8') as out:
        json.dump(entry, out, sort_keys=True)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temp, path)
    _sync_dir(path.parent)


class LocalMockTransaction:
    """Transactional mock restricted to an owned, temporary workspace.

    No API accepts a real scanner destination. The mock path is required to be
    a child of the workspace and is populated only with a verified local copy.
    """
    def __init__(self, workspace, relative):
        self.workspace = Path(workspace).resolve(strict=True)
        self.relative = _safe_name(relative)
        if not self.relative.startswith('favorites_lists/') or not self.relative.endswith('.hpd'):
            raise ValueError('Only a Favorites HPD replacement is supported')
        self.mock = self.workspace/'mock-device'
        self.backup = self.workspace/'recovery'/'original.hpd'
        self.journal = self.workspace/'recovery'/'transaction.json'
        self.target = self.mock/self.relative
        self.stage = self.target.with_name('.'+self.target.name+'.staged')
        # Reject symlinks in every mock path component, not just the leaf.
        for candidate in (self.mock, self.target.parent, self.target, self.stage,
                          self.backup.parent, self.backup, self.journal):
            node = candidate
            while node != self.workspace:
                if node.is_symlink():
                    raise ValueError('Symlinked mock transaction paths rejected')
                if self.workspace not in node.parents:
                    raise ValueError('Mock destination escapes temporary workspace')
                node = node.parent

    def prepare(self, original, proposed):
        if self.journal.exists() or self.target.exists() or self.backup.exists():
            raise ValueError('Existing transaction or mock data: refusing to overwrite')
        original, proposed = Path(original), Path(proposed)
        if original.is_symlink() or proposed.is_symlink():
            raise ValueError('Symlinked inputs rejected')
        old = original.read_bytes()
        new = proposed.read_bytes()
        passed, reason, _ = assess_hpd_frequency_replacement(old, new)
        if not passed:
            raise ValueError('Unsafe native candidate: '+reason)
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.backup.parent.mkdir(parents=True, exist_ok=True)
        _copy_sync(original, self.target)
        _copy_sync(original, self.backup)
        if sha(original) != sha(self.backup) or sha(self.target) != sha(self.backup):
            raise IOError('Fresh verified mock backup failed')
        return sha(self.backup), hashlib.sha256(new).hexdigest()

    def apply(self, proposed, expected_old, expected_new, fail_at=None):
        """Simulate prepared, staged, replaced, verified checkpoints."""
        if self.journal.exists() or self.stage.exists():
            raise ValueError('Unresolved transaction must be recovered first')
        if sha(self.target) != expected_old or sha(self.backup) != expected_old:
            raise IOError('Mock destination/backup changed since preparation')
        if sha(proposed) != expected_new:
            raise IOError('Proposed file changed since preparation')
        _atomic_journal(self.journal, {'relative': self.relative, 'old':expected_old,
                                       'new':expected_new, 'version':1})
        if fail_at == 'journal': raise SimulatedPowerLoss('after durable journal')
        _copy_sync(proposed, self.stage)
        if sha(self.stage) != expected_new or sha(self.target) != expected_old:
            raise IOError('Staged bytes or baseline changed before replacement')
        if fail_at == 'stage': raise SimulatedPowerLoss('after verified staging')
        os.replace(self.stage, self.target)
        _sync_dir(self.target.parent)
        if fail_at == 'replace': raise SimulatedPowerLoss('after atomic mock replacement')
        if sha(self.target) != expected_new or sha(self.backup) != expected_old:
            raise IOError('Mock write verification failed')
        # A successful commit is marked by removal of the recovery journal;
        # the verified backup remains available until the caller ends rehearsal.
        self.journal.unlink()
        _sync_dir(self.journal.parent)
        return True

    def recover(self):
        """Independent restart recovery; reject unknown/tampered data, fail closed."""
        if not self.journal.is_file() or self.journal.is_symlink():
            raise ValueError('No valid durable recovery journal')
        entry = json.loads(self.journal.read_text(encoding='utf-8'))
        if set(entry) != {'relative','old','new','version'} or entry['version'] != 1 or entry['relative'] != self.relative:
            raise ValueError('Invalid recovery journal; manual intervention required')
        if not all(isinstance(entry[key],str) and len(entry[key]) == 64 and
                   all(c in '0123456789abcdef' for c in entry[key]) for key in ('old','new')):
            raise ValueError('Malformed recovery checksums')
        if self.backup.is_symlink() or self.target.is_symlink() or self.stage.is_symlink():
            raise ValueError('Symlink in recovery path')
        if not self.backup.is_file() or sha(self.backup) != entry['old']:
            raise IOError('Recovery backup missing or corrupt; journal retained')
        if not self.target.is_file() or sha(self.target) not in (entry['old'],entry['new']):
            raise IOError('Unexpected mock target bytes; journal retained')
        if sha(self.target) != entry['old']:
            restore = self.target.with_name('.'+self.target.name+'.restore')
            if restore.exists() or restore.is_symlink():
                raise IOError('Unresolved restore file; journal retained')
            _copy_sync(self.backup, restore)
            os.replace(restore, self.target)
            _sync_dir(self.target.parent)
        if sha(self.target) != entry['old']:
            raise IOError('Recovery checksum mismatch; journal retained')
        if self.stage.exists():
            self.stage.unlink()
            _sync_dir(self.stage.parent)
        self.journal.unlink()
        _sync_dir(self.journal.parent)
        return True


def _synthetic_edit(raw):
    """One byte-shaped change, NEVER claimed scanner-valid or used for export."""
    lines = raw.splitlines(keepends=True)
    for i, line in enumerate(lines):
        cols = line.split(b'\t')
        kind = cols[0]
        if kind not in (b'C-Freq', b'T-Freq') or len(cols) < 6:
            continue
        field = cols[5].rstrip(b'\r\n')
        if not field.isascii() or not field.isdigit() or len(field) < 3:
            continue
        changed = field[:-1] + (b'5' if field[-1:] != b'5' else b'0')
        cols[5] = changed
        lines[i] = b'\t'.join(cols)
        candidate = b''.join(lines)
        if assess_hpd_frequency_replacement(raw,candidate)[0]:
            return candidate
    raise ValueError('No supported frequency record for a synthetic sandbox-only edit')


def _choose_candidate(source_files, target_files, changes):
    # Prefer a genuine narrow HPD candidate. Structural edits are never used
    # for mock writing; instead use a one-field synthetic copy of scanner bytes.
    for rel in changes.get('REPLACE', []):
        if rel in source_files and rel in target_files and rel.startswith('favorites_lists/') and rel.endswith('.hpd'):
            old, new = Path(target_files[rel]), Path(source_files[rel])
            if old.is_symlink() or new.is_symlink(): continue
            if old.stat().st_size > MAX_HPD or new.stat().st_size > MAX_HPD: continue
            if assess_hpd_frequency_replacement(old.read_bytes(), new.read_bytes())[0]:
                return rel, old, new, 'actual narrow candidate (sandbox copy only)'
    for rel, path in sorted(target_files.items()):
        if not rel.startswith('favorites_lists/') or not rel.endswith('.hpd'):
            continue
        path = Path(path)
        if path.is_symlink() or path.stat().st_size > MAX_HPD: continue
        try:
            payload = _synthetic_edit(path.read_bytes())
        except ValueError:
            continue
        return rel, path, payload, 'synthetic one-field edit (not scanner-validated)'
    raise ValueError('No eligible native HPD file for an isolated recovery rehearsal')


def rehearse_write_recovery(scanner_root, source_files, target_files, changes, *, workspace_base=None):
    """Read scanner bytes, test durable recovery on an isolated local mock only."""
    lines = ['DURABLE WRITE/RESTART RECOVERY REHEARSAL — LOCAL MOCK ONLY', '']
    try:
        scanner_root = Path(scanner_root).resolve(strict=True)
        base = Path(workspace_base or tempfile.gettempdir()).resolve(strict=True)
        if not base.is_dir() or os.stat(base).st_dev == os.stat(scanner_root).st_dev:
            raise ValueError('Local mock workspace must be on a DIFFERENT filesystem from scanner')
        rel, original, proposed, basis = _choose_candidate(source_files,target_files,changes)
        _safe_name(rel)
        original_hash = sha(original)
        with tempfile.TemporaryDirectory(prefix='sds100-durable-recovery-',dir=base) as tmp:
            work = Path(tmp)
            proposed_path = work/'proposed.hpd'
            if isinstance(proposed,bytes):
                with proposed_path.open('xb') as out:
                    out.write(proposed); out.flush(); os.fsync(out.fileno())
            else:
                _copy_sync(proposed,proposed_path)
            checks = []
            for failure in ('journal','stage','replace'):
                sandbox = work/('failure-'+failure)
                sandbox.mkdir()
                tx = LocalMockTransaction(sandbox,rel)
                old_hash,new_hash = tx.prepare(original,proposed_path)
                try:
                    tx.apply(proposed_path,old_hash,new_hash,fail_at=failure)
                except SimulatedPowerLoss:
                    pass
                else:
                    raise AssertionError('Failure injection was not triggered')
                # New instance emulates restart: no in-memory transaction state.
                recovered = LocalMockTransaction(sandbox,rel)
                recovered.recover()
                if sha(recovered.target) != old_hash or recovered.journal.exists():
                    raise IOError('Restart recovery did not restore original bytes')
                checks.append(failure)
            success = work/'success'; success.mkdir()
            tx = LocalMockTransaction(success,rel)
            old_hash,new_hash = tx.prepare(original,proposed_path)
            tx.apply(proposed_path,old_hash,new_hash)
            if sha(tx.target) != new_hash or sha(tx.backup) != old_hash or tx.journal.exists():
                raise IOError('Committed mock replacement failed verification')
            if sha(original) != original_hash:
                raise IOError('Scanner source changed during mock rehearsal')
        lines.extend([
            'Candidate basis: '+basis,
            'Mock file: '+rel,
            'Fresh local mock backup: SHA-256 VERIFIED',
            'Durable recovery journal: FSYNC + VERIFIED (local mock filesystem)',
            'Staged mock replacement: VERIFIED',
            'Successful mock commit and post-write SHA-256: PASSED',
            'Restart recovery after journal/stage/replacement interruption: PASSED (3/3)',
            'Recovery backup integrity: VERIFIED',
            'Temporary local mock workspace: REMOVED',
            'Scanner writes: 0',
            'Actual FAT32 interruption recovery, model authorization and scanner acceptance: NOT VERIFIED',
            'Export authorization: BLOCKED',
        ])
        return '\n'.join(lines),True
    except (OSError,ValueError,RuntimeError,AssertionError,TypeError) as exc:
        lines.extend(['Local mock rehearsal: BLOCKED — '+str(exc),
                      'Scanner writes: 0', 'Export authorization: BLOCKED'])
        return '\n'.join(lines),False
