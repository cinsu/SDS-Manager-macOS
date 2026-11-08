# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Fail-closed, READ-ONLY native export candidate assessment.

This checks whether an HPD replacement is a narrow field-only edit. It is
NOT scanner acceptance testing and never authorizes a write. CFG/INF and
structural HPD edits are deliberately excluded from the first-write subset.
"""
from pathlib import Path
import re

# Index is zero-based; documented frequency field is column 6.
_FREQUENCY_INDEX = 5
_SUPPORTED_WIDTHS = {'C-Freq': {18}, 'T-Freq': {8, 9}}
_MAX_INSPECTION_BYTES = 25 * 1024 * 1024


def _split_record(line):
    if line.endswith(b'\r\n'):
        return line[:-2].split(b'\t'), b'\r\n'
    if line.endswith((b'\r', b'\n')):
        return line[:-1].split(b'\t'), line[-1:]
    return line.split(b'\t'), b''


def assess_hpd_frequency_replacement(original, proposed):
    """Check that only documented C-Freq/T-Freq Hz fields changed.

    Returns (passed, detail, changed_field_count). Preserves every other byte
    by comparing raw fields and exact record terminators, not reserializing.
    """
    if len(original) > _MAX_INSPECTION_BYTES or len(proposed) > _MAX_INSPECTION_BYTES:
        return False, 'HPD exceeds conservative inspection size limit', 0
    before, after = original.splitlines(keepends=True), proposed.splitlines(keepends=True)
    if len(before) != len(after):
        return False, 'HPD record count changed (structural edit)', 0
    edits = 0
    for line_number, (old_line, new_line) in enumerate(zip(before, after), 1):
        if old_line == new_line:
            continue
        old, old_end = _split_record(old_line)
        new, new_end = _split_record(new_line)
        if old_end != new_end:
            return False, f'Line {line_number}: record terminator changed', edits
        if len(old) != len(new) or not old or old[0] != new[0]:
            return False, f'Line {line_number}: record layout/type changed', edits
        try:
            kind = old[0].decode('ascii')
        except UnicodeDecodeError:
            return False, f'Line {line_number}: unsupported record type', edits
        if kind not in _SUPPORTED_WIDTHS or len(old) not in _SUPPORTED_WIDTHS[kind]:
            return False, f'Line {line_number}: unsupported edited record {kind}', edits
        differences = [index for index, (a, b) in enumerate(zip(old, new)) if a != b]
        if differences != [_FREQUENCY_INDEX]:
            return False, f'Line {line_number}: changes outside documented frequency field', edits
        frequency = new[_FREQUENCY_INDEX]
        if not re.fullmatch(rb'[0-9]+', frequency):
            return False, f'Line {line_number}: nondecimal frequency', edits
        value = int(frequency)
        if not (1 <= value <= 2_000_000_000):
            return False, f'Line {line_number}: frequency outside conservative representation limit', edits
        edits += 1
    if not edits:
        return False, 'No modified native frequency fields found', 0
    return True, f'{edits} documented frequency field(s); unrelated bytes unchanged', edits


def audit_native_export_candidates(source_files, target_files, changes):
    """Inspect only changed candidate files; no scanner write, no authorization."""
    lines = ['NATIVE EXPORT CANDIDATE AUDIT — READ ONLY', '']
    blockers = []
    accepted = 0
    candidates = changes.get('ADD', []) + changes.get('REPLACE', [])
    for name in candidates:
        if name in changes.get('ADD', []):
            blockers.append(f'{name}: new-file/structural serialization not certified')
            continue
        if not (name.startswith('favorites_lists/') and name.lower().endswith('.hpd')):
            blockers.append(f'{name}: unsupported first-write file type (CFG/INF/settings are opaque)')
            continue
        try:
            source, target = Path(source_files[name]), Path(target_files[name])
            if source.is_symlink() or target.is_symlink():
                raise ValueError('symlink candidate rejected')
            valid, detail, edits = assess_hpd_frequency_replacement(
                target.read_bytes(), source.read_bytes())
            if valid:
                accepted += 1
                lines.append(f'FORMAT CHECK PASSED: {name}: {detail}')
            else:
                blockers.append(f'{name}: {detail}')
        except (OSError, ValueError, KeyError) as exc:
            blockers.append(f'{name}: could not inspect candidate: {exc}')
    lines.append(f'Changed files assessed: {len(candidates)}')
    lines.append(f'Narrow HPD field-only format checks passed: {accepted}')
    lines.append(f'Unsupported/failed candidates: {len(blockers)}')
    lines.extend('CANDIDATE BLOCKER: ' + reason for reason in blockers)
    if not candidates:
        lines.append('No file differences: there is nothing to export.')
    lines.extend(['A passing format check is NOT proof of SDS100 acceptance or safe on-device writing.',
                  'CFG/INF semantics, new files, deleted records and other edits are not certified.',
                  'Scanner writes: 0'])
    return '\n'.join(lines), (bool(candidates) and not blockers)


def readiness_summary(source_files, target_files, changes, backup_ok, rehearsal_ok):
    candidate_report, candidate_ok = audit_native_export_candidates(source_files, target_files, changes)
    blockers = []
    if not candidate_ok:
        blockers.append('Proposed files are not all certified narrow native HPD frequency changes, or there are no changes.')
    if not backup_ok:
        blockers.append('Current scanner contents do not match a verified backup.')
    if not rehearsal_ok:
        blockers.append('Local staging/rollback rehearsal did not pass.')
    # These gates are not solved by USB strings, local simulation or byte probes.
    blockers.extend([
        'Trusted SDS100 identity authorization has not been established.',
        'On-device FAT32 staging, rollback, interruption recovery and revalidation are not verified.',
        'Edited native HPD scanner acceptance is not verified; CFG/INF semantics remain opaque.',
        'Fresh immediately-prewrite backup and final verification are not implemented in the write path.',
    ])
    lines = ['EXPORT READINESS — AUTOMATIC PREVIEW (READ ONLY)', '',
             f'Candidate field-format check: {"PASSED" if candidate_ok else "BLOCKED"}',
             f'Existing matching backup: {"FOUND" if backup_ok else "NOT VERIFIED"}',
             f'Local rehearsal: {"PASSED" if rehearsal_ok else "NOT VERIFIED"}',
             f'Unresolved export blockers: {len(blockers)}']
    lines.extend('BLOCKER: ' + item for item in blockers)
    lines.extend(['', 'Proceed with Export: DISABLED',
                  'Cancel leaves scanner unchanged; this build performs no scanner writes.',
                  '', candidate_report])
    return '\n'.join(lines), False
