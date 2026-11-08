# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""In-memory multi-record and multi-column reversibility checks; never writes files."""
from pathlib import Path

MAX_BYTES = 25 * 1024 * 1024
KINDS = ('C-Freq', 'T-Freq', 'TGID', 'Site', 'C-Group', 'T-Group')


def inspect_multifield_probe(files):
    checked = passed = attempted = changed_fields = 0
    kinds_seen = set()
    warnings = []
    for name, source in sorted(files.items()):
        if not (name.startswith('favorites_lists/') and name.lower().endswith('.hpd')):
            continue
        checked += 1
        try:
            source = Path(source)
            if source.stat().st_size > MAX_BYTES:
                raise ValueError('exceeds 25 MiB limit')
            original = source.read_bytes()
            if not original or b'\x00' in original:
                raise ValueError('empty or NUL-containing file')
            encoding = 'utf-8-sig' if original.startswith(b'\xef\xbb\xbf') else 'cp1252'
            lines = original.decode(encoding, errors='strict').splitlines(keepends=True)
            changes = []
            seen = set()
            for index, line in enumerate(lines):
                body = line.rstrip('\r\n')
                fields = body.split('\t')
                kind = fields[0].strip() if fields else ''
                if kind not in KINDS or kind in seen or len(fields) < 4:
                    continue
                seen.add(kind)
                # A name-like column, plus a second nonempty column when present.
                columns = [3]
                for column in range(1, len(fields)):
                    if column != 3 and fields[column] and '\r' not in fields[column] and '\n' not in fields[column]:
                        columns.append(column)
                        break
                changes.append((index, kind, columns))
            if not changes:
                continue
            attempted += 1
            modified = lines[:]
            for index, kind, columns in changes:
                original_line = lines[index]
                body = original_line.rstrip('\r\n')
                ending = original_line[len(body):]
                fields = body.split('\t')
                for column in columns:
                    fields[column] += ' [PROBE]'
                modified[index] = '\t'.join(fields) + ending
            edited_bytes = ''.join(modified).encode(encoding, errors='strict')
            edited_lines = edited_bytes.decode(encoding, errors='strict').splitlines(keepends=True)
            if len(edited_lines) != len(lines):
                raise ValueError('line count changed')
            changed_indexes = {index for index, _, _ in changes}
            for index, (before, after) in enumerate(zip(lines, edited_lines)):
                if index not in changed_indexes and before != after:
                    raise ValueError('unrelated record changed')
            for index, kind, columns in changes:
                before = lines[index].rstrip('\r\n').split('\t')
                after = edited_lines[index].rstrip('\r\n').split('\t')
                if len(before) != len(after):
                    raise ValueError('column count changed')
                if lines[index][len(lines[index].rstrip('\r\n')):] != edited_lines[index][len(edited_lines[index].rstrip('\r\n')):]:
                    raise ValueError('line ending changed')
                for column, (old, new) in enumerate(zip(before, after)):
                    if new != (old + ' [PROBE]' if column in columns else old):
                        raise ValueError('unintended column modification')
                kinds_seen.add(kind)
                changed_fields += len(columns)
            restored = edited_lines[:]
            for index, _, columns in changes:
                original_line = lines[index]
                body = original_line.rstrip('\r\n')
                ending = original_line[len(body):]
                fields = edited_lines[index].rstrip('\r\n').split('\t')
                for column in columns:
                    fields[column] = fields[column][:-len(' [PROBE]')]
                restored[index] = '\t'.join(fields) + ending
            if ''.join(restored).encode(encoding, errors='strict') != original:
                raise ValueError('restored bytes differ from source')
            passed += 1
        except (OSError, ValueError, UnicodeError) as exc:
            warnings.append(f'{name}: {exc}')
    output = ['NATIVE FAVORITES MULTI-FIELD PROBE — READ ONLY', '',
              f'Favorites HPD files inspected: {checked}',
              f'Files with eligible records: {attempted}',
              f'Files passing multi-record edit / restore: {passed}',
              f'Fields modified and restored in memory: {changed_fields}',
              f'Record types exercised: {", ".join(sorted(kinds_seen)) or "none"}',
              f'Multi-field probe warnings: {len(warnings)}']
    output.extend('WARNING: ' + warning for warning in warnings[:25])
    if len(warnings) > 25:
        output.append(f'... and {len(warnings)-25} more warnings')
    output.extend(['Edits are reversible synthetic text changes, NOT scanner-valid field values.',
                   'No local configuration, backup or scanner files are modified.',
                   'Native SDS100 write compatibility: NOT VERIFIED',
                   'Export action: DISABLED'])
    return '\n'.join(output)
