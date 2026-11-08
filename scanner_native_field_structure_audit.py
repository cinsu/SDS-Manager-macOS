# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Observational read-only per-column structural census. No scanner writes."""
from collections import Counter
from pathlib import Path

KINDS = ('C-Freq', 'T-Freq', 'TGID')
MAX_BYTES = 25 * 1024 * 1024

def audit_field_structure(files):
    layouts = {kind: Counter() for kind in KINDS}
    shapes = {kind: {} for kind in KINDS}
    warnings = []
    inspected = 0
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
            inspected += 1
            for line in raw.decode(encoding, errors='strict').splitlines():
                fields = line.split('	')
                kind = fields[0].strip() if fields else ''
                if kind not in KINDS:
                    continue
                layouts[kind][len(fields)] += 1
                for idx, token in enumerate(fields[1:], 2):
                    key = (len(fields), idx)
                    counter = shapes[kind].setdefault(key, Counter())
                    if token == '': shape = 'empty'
                    elif token.isascii() and token.isdecimal(): shape = 'decimal'
                    elif token.isascii() and token.lstrip('-').isdecimal() and token.startswith('-'): shape = 'signed-integer'
                    else: shape = 'text/other'
                    counter[shape] += 1
        except (OSError, ValueError, UnicodeError) as exc:
            warnings.append(f'{name}: {exc}')
    lines = ['NATIVE FAVORITES FIELD STRUCTURE AUDIT — READ ONLY', '',
             f'Favorites HPD files inspected: {inspected}',
             'Column numbers are 1-based, including the record-type column.',
             'Value classes are observational; they do NOT establish field meanings.']
    for kind in KINDS:
        lines.append(f'{kind}: {sum(layouts[kind].values())} records')
        for width, count in sorted(layouts[kind].items()):
            lines.append(f'  {width}-column layout: {count} records')
            for idx in range(2, width+1):
                c = shapes[kind].get((width, idx), Counter())
                classes = ', '.join(f'{label}={c[label]}' for label in ('empty','decimal','signed-integer','text/other') if c[label])
                lines.append(f'    Column {idx}: {classes or "no observations"}')
    lines.append(f'File read/decode warnings: {len(warnings)}')
    lines.extend('WARNING: '+w for w in warnings[:8])
    lines.extend(['Unknown field semantics and trailing empty columns must be preserved during future editing.',
                  'This audit does not verify TGID encoding, native serialization, or scanner acceptance.',
                  'No local configuration, backup or scanner files were modified.',
                  'Native SDS100 write compatibility: NOT VERIFIED', 'Export action: DISABLED'])
    return '\n'.join(lines)
