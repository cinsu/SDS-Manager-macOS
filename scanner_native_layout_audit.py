# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Read-only native Favorites record layout census; no native edit capability implied."""
from collections import Counter
from pathlib import Path

KINDS = ('C-Freq', 'T-Freq', 'TGID')
MAX_BYTES = 25 * 1024 * 1024


def inspect_record_layout(files):
    counts = {kind: Counter() for kind in KINDS}
    noncanonical = {kind: 0 for kind in KINDS}
    warnings = []
    examples = []
    inspected_files = 0
    for name, source in sorted(files.items()):
        if not (name.startswith('favorites_lists/') and name.lower().endswith('.hpd')):
            continue
        try:
            p = Path(source)
            if p.is_symlink() or p.stat().st_size > MAX_BYTES:
                raise ValueError('symlink or file larger than 25 MiB')
            raw = p.read_bytes()
            if b'\x00' in raw:
                raise ValueError('NUL-containing file')
            encoding = 'utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'cp1252'
            inspected_files += 1
            for lineno, line in enumerate(raw.decode(encoding, errors='strict').splitlines(), 1):
                fields = line.split('\t')
                kind = fields[0].strip() if fields else ''
                if kind not in KINDS:
                    continue
                counts[kind][len(fields)] += 1
                token = fields[5] if len(fields) > 5 else None
                if token is None or not token.isascii() or not token.isdecimal():
                    noncanonical[kind] += 1
                    if len(examples) < 8:
                        examples.append(f'{name}:{lineno}: {kind} has {len(fields)} columns; column 6 is missing/non-decimal')
        except (OSError, ValueError, UnicodeError) as exc:
            warnings.append(f'{name}: {exc}')
    lines = ['NATIVE FAVORITES RECORD LAYOUT AUDIT — READ ONLY', '',
             f'Favorites HPD files inspected: {inspected_files}',
             'Column counts include the record-type column; trailing empty tab-separated fields are retained.']
    for kind in KINDS:
        dist = ', '.join(f'{n}: {c}' for n,c in sorted(counts[kind].items())) or 'none'
        lines.append(f'{kind}: {sum(counts[kind].values())} records; column counts (columns: records): {dist}')
        lines.append(f'  Missing/non-decimal column 6 values: {noncanonical[kind]}')
    lines.append(f'Layout exceptions requiring review: {sum(noncanonical.values())} (numeric column only)')
    lines.extend('REVIEW: ' + e for e in examples)
    lines.append(f'File read/decode warnings: {len(warnings)}')
    lines.extend('WARNING: ' + w for w in warnings[:8])
    lines.extend(['This is an observational layout census, NOT proof that column 6 or any other field has correct native semantics.',
                  'Other record types, per-column meaning, TGID encoding rules, CFG/INF files and edited-file serialization are NOT VERIFIED.',
                  'No local configuration, backup or scanner files were modified.',
                  'Native SDS100 write compatibility: NOT VERIFIED', 'Export action: DISABLED'])
    return '\n'.join(lines)
