# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Read-only byte-level, single-field edit and reversal audit of local Favorites."""
from collections import Counter
from pathlib import Path

KINDS = ('C-Freq', 'T-Freq', 'TGID')
MAX_BYTES = 25 * 1024 * 1024

def audit_lossless_field_edits(files):
    attempts = Counter()
    passed = Counter()
    warnings = []
    inspected = 0
    for name, source in sorted(files.items()):
        if not (name.startswith('favorites_lists/') and name.lower().endswith('.hpd')):
            continue
        try:
            p = Path(source)
            if p.is_symlink() or p.stat().st_size > MAX_BYTES:
                raise ValueError('symlink or file larger than 25 MiB')
            original = p.read_bytes()
            if b'\x00' in original: raise ValueError('NUL-containing file')
            inspected += 1
            # Keep the exact original line terminator bytes and all blank lines.
            lines = original.splitlines(keepends=True)
            tested_in_file = set()
            for line_no, line in enumerate(lines):
                body = line.rstrip(b'\r\n')
                terminator = line[len(body):]
                fields = body.split(b'\t')
                try: kind = fields[0].decode('ascii')
                except UnicodeError: continue
                if kind not in KINDS or len(fields) < 6: continue
                key = (kind, len(fields))
                if key in tested_in_file: continue
                tested_in_file.add(key)
                attempts[key] += 1
                old = fields[5]
                if not old or not old.isascii() or not old.isdigit():
                    warnings.append(f'{name}: line {line_no+1}: nondecimal target')
                    continue
                # Same-width ASCII digit substitution, never written to disk.
                replacement = bytes([48 + ((old[0] - 48 + 1) % 10)]) + old[1:]
                changed_fields = list(fields)
                changed_fields[5] = replacement
                changed_line = b'\t'.join(changed_fields) + terminator
                if changed_line == line or changed_line.split(b'\t')[:5] != line.split(b'\t')[:5]:
                    warnings.append(f'{name}: line {line_no+1}: edit isolation failed')
                    continue
                if changed_line.split(b'\t')[6:] != line.split(b'\t')[6:]:
                    warnings.append(f'{name}: line {line_no+1}: untouched fields changed')
                    continue
                edited_lines = list(lines)
                edited_lines[line_no] = changed_line
                edited = b''.join(edited_lines)
                if edited == original or len(edited) != len(original):
                    warnings.append(f'{name}: line {line_no+1}: unexpected byte edit')
                    continue
                restored_fields = changed_line[:-len(terminator)].split(b'\t') if terminator else changed_line.split(b'\t')
                restored_fields[5] = old
                edited_lines[line_no] = b'\t'.join(restored_fields) + terminator
                if b''.join(edited_lines) != original:
                    warnings.append(f'{name}: line {line_no+1}: exact restoration failed')
                    continue
                passed[key] += 1
        except (OSError, ValueError) as exc:
            warnings.append(f'{name}: {exc}')
    lines = ['NATIVE FAVORITES LOSSLESS FIELD EDIT AUDIT — READ ONLY', '',
             f'Favorites HPD files inspected: {inspected}',
             'Target: column 6 (1-based), tested once per observed record layout per file.',
             'Edits use same-width ASCII decimal substitution IN MEMORY only.']
    for key in sorted(attempts):
        lines.append(f'{key[0]} / {key[1]} columns: {passed[key]} / {attempts[key]} exact edit-and-restore probes passed')
    lines.extend([f'Total probes passed: {sum(passed.values())} / {sum(attempts.values())}',
                  f'Probe warnings: {len(warnings)}'])
    lines.extend('WARNING: '+warning for warning in warnings[:8])
    lines.extend(['Original tabs, line endings, other fields and trailing empty columns remain byte-exact.',
                  'These are synthetic byte-level probes, NOT scanner-valid edits or verified field semantics.',
                  'No local configuration, scanner, or backup files were modified.',
                  'Native SDS100 edited-file write compatibility: NOT VERIFIED',
                  'Export action: DISABLED'])
    return '\n'.join(lines)
