# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Read-only, in-memory reversible field edit probe. Not scanner format certification."""
from pathlib import Path

MAX_BYTES = 25 * 1024 * 1024
EDIT_KINDS = {'C-Freq', 'T-Freq', 'TGID'}

def _encode(text, encoding):
    return text.encode(encoding, errors='strict')

def inspect_edit_probe(files):
    checked = attempted = passed = 0
    warnings = []
    for name, path in sorted(files.items()):
        if not (name.startswith('favorites_lists/') and name.lower().endswith('.hpd')):
            continue
        checked += 1
        try:
            path = Path(path)
            if path.stat().st_size > MAX_BYTES:
                raise ValueError('file exceeds inspection limit')
            original = path.read_bytes()
            if not original or b'\x00' in original:
                raise ValueError('empty file or NUL byte')
            encoding = 'utf-8-sig' if original.startswith(b'\xef\xbb\xbf') else 'cp1252'
            lines = original.decode(encoding, errors='strict').splitlines(keepends=True)
            candidate = None
            for i, line in enumerate(lines):
                body = line.rstrip('\r\n')
                fields = body.split('\t')
                if len(fields) > 3 and fields[0].strip() in EDIT_KINDS:
                    candidate = (i, fields, line[len(body):])
                    break
            if candidate is None:
                continue  # no editable leaf record in this file
            attempted += 1
            i, fields, ending = candidate
            old = fields[3]
            # Use a reversible ASCII-only name edit; no disk writes and no scanner writes.
            replacement = old + ' [OFFLINE PROBE]'
            fields[3] = replacement
            edited_line = '\t'.join(fields) + ending
            if edited_line == lines[i]:
                raise ValueError('probe did not change selected field')
            edited = list(lines)
            edited[i] = edited_line
            edited_raw = _encode(''.join(edited), encoding)
            decoded = edited_raw.decode(encoding, errors='strict').splitlines(keepends=True)
            if len(decoded) != len(lines):
                raise ValueError('record count changed')
            if any(a != b for j, (a,b) in enumerate(zip(lines, decoded)) if j != i):
                raise ValueError('unrelated record changed')
            modified_fields = decoded[i].rstrip('\r\n').split('\t')
            if len(modified_fields) != len(fields) or modified_fields[3] != replacement:
                raise ValueError('edited record field/column mismatch')
            restored_fields = modified_fields[:]
            restored_fields[3] = old
            decoded[i] = '\t'.join(restored_fields) + ending
            if _encode(''.join(decoded), encoding) != original:
                raise ValueError('restoration differs from original bytes')
            passed += 1
        except (OSError, ValueError, UnicodeError) as exc:
            warnings.append(f'{name}: {exc}')
    lines = ['NATIVE FAVORITES EDIT PROBE — READ ONLY', '',
             f'Favorites HPD files inspected: {checked}',
             f'Files with eligible leaf-name records: {attempted}',
             f'In-memory edit / restore probes passed: {passed}',
             f'Edit probe warnings: {len(warnings)}']
    lines.extend('WARNING: ' + item for item in warnings[:25])
    if len(warnings)>25:
        lines.append(f'... and {len(warnings)-25} more warnings')
    lines.extend(['Only one name field per eligible file is changed IN MEMORY and restored.',
                  'Original files, scanner files and backups are NEVER modified by this probe.',
                  'This does NOT validate SDS100 edited-file semantics or CFG/INF serialization.',
                  'Native SDS100 write compatibility: NOT VERIFIED',
                  'Export action: DISABLED'])
    return '\n'.join(lines)
