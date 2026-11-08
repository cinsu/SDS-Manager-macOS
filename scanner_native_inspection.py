# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Read-only lossless-byte and header inspection. NOT a native serializer certification."""
from pathlib import Path

MAX_FILE_BYTES = 25 * 1024 * 1024

def inspect_native_files(source_files):
    lines = ['NATIVE FILE INSPECTION — READ ONLY', '']
    hpd_count = 0
    lossless = 0
    warnings = []
    opaque = []
    for name, path in sorted(source_files.items()):
        if not name.lower().endswith('.hpd'):
            if name.lower().endswith(('.cfg', '.inf')):
                opaque.append(name)
            continue
        hpd_count += 1
        try:
            path = Path(path)
            if path.stat().st_size > MAX_FILE_BYTES:
                raise ValueError('exceeds 25 MiB inspection limit')
            raw = path.read_bytes()
            if not raw:
                raise ValueError('empty file')
            if b'\x00' in raw:
                raise ValueError('contains NUL bytes; not safely treated as text')
            encoding = 'utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'cp1252'
            decoded = raw.decode(encoding, errors='strict')
            if decoded.encode(encoding, errors='strict') != raw:
                raise ValueError('byte-for-byte decode/encode mismatch')
            lossless += 1
            rows = [line.split('\t') for line in decoded.splitlines() if line.strip()]
            if name.startswith('favorites_lists/'):
                keys = {row[0].strip(): row[1].strip() for row in rows if len(row) > 1 and row[0].strip() in ('TargetModel', 'FormatVersion')}
                if keys.get('TargetModel') != 'BCDx36HP':
                    warnings.append(f'{name}: BCDx36HP TargetModel header absent or unexpected')
                if not keys.get('FormatVersion'):
                    warnings.append(f'{name}: FormatVersion header absent')
        except (OSError, UnicodeError, ValueError) as exc:
            warnings.append(f'{name}: {exc}')
    lines.append(f'HPD files inspected: {hpd_count}')
    lines.append(f'HPD files with lossless byte decoding: {lossless}')
    lines.append(f'CFG/INF files preserved as opaque bytes (not interpreted): {len(opaque)}')
    lines.append(f'Inspection warnings: {len(warnings)}')
    lines.extend('WARNING: ' + item for item in warnings[:25])
    if len(warnings) > 25: lines.append(f'... and {len(warnings)-25} more warnings')
    lines.append('Lossless decoding does NOT validate SDS100 field semantics or edited-file serialization.')
    lines.append('CFG/INF native layout and SDS100 write compatibility: NOT VERIFIED')
    lines.append('Export action: DISABLED')
    return '\n'.join(lines)
