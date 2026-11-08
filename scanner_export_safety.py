# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Conservative read-only export safety audit. Never authorizes writing."""
from pathlib import Path
import os
import shutil

def audit_export_safety(local_root, scanner_root, source_files, target_files, changes):
    local_root, scanner_root = Path(local_root), Path(scanner_root)
    lines = ['EXPORT SAFETY AUDIT — READ ONLY', '']
    blockers = []
    # Device identity is intentionally not inferred from a folder name or presence of scanner.inf.
    blockers.append('Scanner model and device identity are not authenticated.')
    lines.append('Scanner identity: NOT VERIFIED (scanner.inf presence is not proof of SDS100 identity)')
    try:
        usage = shutil.disk_usage(scanner_root)
        changed = changes['ADD'] + changes['REPLACE']
        required = sum(source_files[name].stat().st_size for name in changed)
        lines.append(f'Scanner filesystem free space: {usage.free:,} bytes')
        lines.append(f'Changed-file payload size: {required:,} bytes')
        if required > usage.free:
            blockers.append('Changed-file payload exceeds reported free space.')
        # Free-space checks alone cannot prove sufficient space for safe atomic staging.
        lines.append('Space safety: NOT VERIFIED (filesystem overhead and rollback staging not established)')
        blockers.append('Actual on-device staging, rollback and filesystem overhead remain unverified (local rehearsal does not authorize writes).')
    except OSError as exc:
        lines.append(f'Free-space inspection failed: {exc}')
        blockers.append('Scanner free space could not be inspected.')
    native_files = [name for name in source_files if name.lower().endswith(('.hpd', '.cfg', '.inf'))]
    empty = [name for name in native_files if source_files[name].stat().st_size == 0]
    lines.append(f'Native-looking configuration files found: {len(native_files)}')
    if empty:
        lines.append('Empty native-looking files: ' + ', '.join(empty[:20]))
        blockers.append('One or more native-looking files are empty; manual review required.')
    lines.append('Native serialization / round-trip compatibility: NOT VERIFIED')
    blockers.append('SDS100 native export serialization has not been validated.')
    lines.append('Export action: DISABLED')
    lines.append('')
    lines.append(f'Unresolved safety gates: {len(blockers)}')
    lines.extend('BLOCKER: ' + item for item in blockers)
    lines.append('No scanner files were written or changed by this audit.')
    return '\n'.join(lines)
