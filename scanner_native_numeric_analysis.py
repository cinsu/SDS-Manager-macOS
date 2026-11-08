# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Read-only numerical distribution of observed native HPD fields."""
from collections import Counter
from pathlib import Path

KINDS = ('C-Freq', 'T-Freq', 'TGID')
MAX_BYTES = 25 * 1024 * 1024


def inspect_numeric_representations(files):
    values = {kind: [] for kind in KINDS}
    widths = {kind: Counter() for kind in KINDS}
    warnings = []
    for name, path in sorted(files.items()):
        if not (name.startswith('favorites_lists/') and name.lower().endswith('.hpd')):
            continue
        try:
            path = Path(path)
            if path.is_symlink():
                raise ValueError('symlink not supported')
            if path.stat().st_size > MAX_BYTES:
                raise ValueError('file exceeds 25 MiB')
            raw = path.read_bytes()
            if b'\x00' in raw:
                raise ValueError('NUL byte in file')
            enc = 'utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'cp1252'
            for line in raw.decode(enc, errors='strict').splitlines():
                fields = line.split('\t')
                if not fields or fields[0].strip() not in KINDS:
                    continue
                kind = fields[0].strip()
                if len(fields) <= 5 or not (fields[5].strip().isascii() and fields[5].strip().isdecimal()):
                    continue  # already flagged by preceding format audit
                token = fields[5].strip()
                widths[kind][len(token)] += 1
                values[kind].append(int(token))
        except (OSError, UnicodeError, ValueError) as exc:
            warnings.append(f'{name}: {exc}')
    lines = ['NATIVE FAVORITES NUMERIC REPRESENTATION — READ ONLY', '',
             'Observed source: column 6 (index 5), decimal-only values.',
             'Frequency interpretation hypothesis: stored integer / 1,000,000 = MHz.',
             'This hypothesis is used by the existing read-only Favorites display; NOT independently scanner-verified.']
    for kind in KINDS:
        arr = values[kind]
        lines.append(f'{kind}: {len(arr)} decimal values')
        if not arr:
            lines.append('  No decimal values available for numerical analysis.')
            continue
        lines.append(f'  Raw integer range: {min(arr)} to {max(arr)}')
        lines.append('  Digit lengths (length: count): ' + ', '.join(f'{n}: {count}' for n,count in sorted(widths[kind].items())))
        if kind != 'TGID':
            lines.append(f'  Hypothetical MHz range (integer / 1,000,000): {min(arr)/1_000_000:.6f} to {max(arr)/1_000_000:.6f}')
        else:
            lines.append('  TGID values are identifiers, NOT frequencies; no MHz conversion applied.')
    lines.append(f'File read/decode warnings: {len(warnings)}')
    lines.extend('WARNING: ' + warning for warning in warnings[:15])
    lines.extend(['Ranges are descriptive only; no band-plan, modulation, or scanner limits are certified.',
                  'No field values or local/scanner files are changed.',
                  'Native SDS100 write compatibility: NOT VERIFIED',
                  'Export action: DISABLED'])
    return '\n'.join(lines)
