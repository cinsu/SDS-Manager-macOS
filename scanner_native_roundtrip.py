# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Read-only structural and record preservation checks. Not an SDS100 serializer certification."""
from pathlib import Path
from native_favorites_reader import parse_native_favorites

MAX_BYTES = 25 * 1024 * 1024

def inspect_roundtrip(files):
    checked = 0
    byte_exact = 0
    structural = 0
    records = 0
    warnings = []
    for name, path in sorted(files.items()):
        if not name.startswith('favorites_lists/') or not name.lower().endswith('.hpd'):
            continue
        checked += 1
        try:
            path = Path(path)
            if path.stat().st_size > MAX_BYTES:
                raise ValueError('exceeds 25 MiB inspection limit')
            raw = path.read_bytes()
            if not raw or b'\x00' in raw:
                raise ValueError('empty or contains NUL bytes')
            encoding = 'utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'cp1252'
            text = raw.decode(encoding, errors='strict')
            # Keep each original line terminator, trailing tabs, empty fields and final newline.
            physical_lines = text.splitlines(keepends=True)
            reconstructed = ''.join(physical_lines).encode(encoding, errors='strict')
            if reconstructed != raw:
                raise ValueError('byte-exact reconstruction failed')
            byte_exact += 1
            parsed = parse_native_favorites(path)
            header = parsed['header']
            if header.get('TargetModel') != 'BCDx36HP' or not header.get('FormatVersion'):
                raise ValueError('required native header missing')
            if parsed['warnings']:
                raise ValueError('; '.join(parsed['warnings'][:3]))
            structural += 1
            records += sum(bool(line.strip()) for line in physical_lines)
        except (OSError, ValueError, UnicodeError) as exc:
            warnings.append(f'{name}: {exc}')
    lines = ['NATIVE FAVORITES RECORD ROUND-TRIP — READ ONLY', '',
             f'Favorites HPD files inspected: {checked}',
             f'Byte-exact unmodified reconstructions: {byte_exact}',
             f'Files passing basic parser/header checks: {structural}',
             f'Nonblank records in structurally valid files: {records}',
             f'Round-trip inspection warnings: {len(warnings)}']
    lines.extend('WARNING: '+warning for warning in warnings[:25])
    if len(warnings) > 25:
        lines.append(f'... and {len(warnings)-25} more warnings')
    lines.extend(['This reconstructs UNMODIFIED text only; edited field serialization is NOT VERIFIED.',
                  'CFG/INF files are not parsed or rewritten.',
                  'Native SDS100 write compatibility: NOT VERIFIED',
                  'Export action: DISABLED'])
    return '\n'.join(lines)
