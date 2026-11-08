# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Read-only observation of native HPD frequency and TGID representations.

Does not certify SDS100 semantic limits or serialize edited files.
"""
from collections import Counter
from pathlib import Path

MAX_BYTES = 25 * 1024 * 1024
KINDS = ('C-Freq', 'T-Freq', 'TGID')


def inspect_native_values(files):
    inspected = Counter()
    accepted = Counter()
    blank = Counter()
    examples = []
    warnings = []
    for name, source in sorted(files.items()):
        if not (name.startswith('favorites_lists/') and name.lower().endswith('.hpd')):
            continue
        try:
            source = Path(source)
            if source.stat().st_size > MAX_BYTES:
                raise ValueError('exceeds 25 MiB limit')
            raw = source.read_bytes()
            if b'\x00' in raw:
                raise ValueError('NUL-containing file')
            encoding = 'utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'cp1252'
            for line_no, line in enumerate(raw.decode(encoding, errors='strict').splitlines(), 1):
                fields = line.split('\t')
                kind = fields[0].strip() if fields else ''
                if kind not in KINDS:
                    continue
                inspected[kind] += 1
                if len(fields) <= 5:
                    if len(examples) < 15:
                        examples.append(f'{name}:{line_no}: {kind} lacks column 6')
                    continue
                value = fields[5].strip()
                if not value:
                    blank[kind] += 1
                elif value.isascii() and value.isdecimal():
                    accepted[kind] += 1
                elif len(examples) < 15:
                    examples.append(f'{name}:{line_no}: {kind} non-decimal value {value[:48]!r}')
        except (OSError, ValueError, UnicodeError) as exc:
            warnings.append(f'{name}: {exc}')
    out = ['NATIVE FAVORITES FIELD-VALUE AUDIT — READ ONLY', '',
           'Field inspected: column 6 (index 5) for C-Freq, T-Freq and TGID',
           'Observed format check: ASCII decimal digits only (not scanner range validation)']
    for kind in KINDS:
        out.append(f'{kind}: {inspected[kind]} records; {accepted[kind]} decimal values; {blank[kind]} blanks; {inspected[kind]-accepted[kind]-blank[kind]} other/missing')
    out.append(f'Value-format examples requiring review: {len(examples)}' + (' (first 15 only)' if len(examples) == 15 else ''))
    out.extend('REVIEW: ' + x for x in examples)
    out.append(f'File read/decode warnings: {len(warnings)}')
    out.extend('WARNING: ' + x for x in warnings[:15])
    out.extend(['This is a format survey, NOT proof that numeric values are valid for SDS100.',
                'Other native columns, unknown records, CFG/INF semantics and edited-file serialization are NOT VERIFIED.',
                'No local configuration, backup or scanner files are modified.',
                'Native SDS100 write compatibility: NOT VERIFIED',
                'Export action: DISABLED'])
    return '\n'.join(out)
