# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Read-only variable-width native decimal field mutation and exact restoration."""
from collections import Counter
from pathlib import Path

MAX_BYTES = 25 * 1024 * 1024
KINDS = ('C-Freq', 'T-Freq', 'TGID')

def _change_one_line(line, replacement):
    body = line.rstrip(b'\r\n')
    ending = line[len(body):]
    fields = body.split(b'\t')
    if len(fields) < 6 or not fields[5] or not fields[5].isascii() or not fields[5].isdigit():
        raise ValueError('invalid decimal field')
    original_field = fields[5]
    fields[5] = replacement
    changed = b'\t'.join(fields) + ending
    if changed == line or changed.count(b'\t') != line.count(b'\t'):
        raise ValueError('edit isolation failure')
    edited_body = changed[:-len(ending)] if ending else changed
    edited_fields = edited_body.split(b'\t')
    if edited_fields[:5] != body.split(b'\t')[:5] or edited_fields[6:] != body.split(b'\t')[6:]:
        raise ValueError('unrelated fields changed')
    edited_fields[5] = original_field
    if b'\t'.join(edited_fields) + ending != line:
        raise ValueError('line restoration failure')
    return changed

def audit_variable_length_edits(files):
    attempts = Counter(); passed = Counter(); skipped = Counter()
    warnings = []; inspected = 0
    for name, source in sorted(files.items()):
        if not (name.startswith('favorites_lists/') and name.lower().endswith('.hpd')):
            continue
        try:
            path = Path(source)
            if path.is_symlink() or path.stat().st_size > MAX_BYTES:
                raise ValueError('symlink or file larger than 25 MiB')
            original = path.read_bytes()
            if b'\x00' in original:
                raise ValueError('NUL-containing file')
            inspected += 1
            lines = original.splitlines(keepends=True)
            # Choose an eligible example separately for each mode and layout.
            # A one-digit TGID cannot be shortened to a positive decimal integer.
            candidates = {}
            for index, line in enumerate(lines):
                fields = line.rstrip(b'\r\n').split(b'\t')
                if not fields or fields[0] not in (b'C-Freq', b'T-Freq', b'TGID') or len(fields) < 6:
                    continue
                key = (fields[0].decode('ascii'), len(fields))
                old = fields[5]
                if not old or not old.isascii() or not old.isdigit():
                    warnings.append(f'{name}: line {index+1}: invalid target')
                    continue
                candidates.setdefault(key, {})
                candidates[key].setdefault('longer', (index, line, old))
                if len(old) > 1:
                    candidates[key].setdefault('shorter', (index, line, old))
            for key, modes in sorted(candidates.items()):
                for mode in ('shorter', 'longer'):
                    case = (key[0], key[1], mode)
                    if mode not in modes:
                        skipped[case] += 1
                        continue
                    index, line, old = modes[mode]
                    replacement = b'7' if mode == 'shorter' else b'1' + old + b'9'
                    attempts[case] += 1
                    try:
                        if (mode == 'shorter' and len(replacement) >= len(old)) or (mode == 'longer' and len(replacement) <= len(old)):
                            raise ValueError('no required length change')
                        changed_line = _change_one_line(line, replacement)
                        edited_lines = list(lines); edited_lines[index] = changed_line
                        edited = b''.join(edited_lines)
                        if len(edited) - len(original) != len(replacement) - len(old):
                            raise ValueError('unexpected file length delta')
                        prefix_length = sum(map(len, lines[:index]))
                        if edited[:prefix_length] != original[:prefix_length]:
                            raise ValueError('prefix changed')
                        if b''.join(edited_lines[index+1:]) != b''.join(lines[index+1:]):
                            raise ValueError('suffix changed')
                        edited_body = changed_line.rstrip(b'\r\n')
                        terminator = changed_line[len(edited_body):]
                        restored = edited_body.split(b'\t'); restored[5] = old
                        edited_lines[index] = b'\t'.join(restored) + terminator
                        if b''.join(edited_lines) != original:
                            raise ValueError('file restoration failure')
                        passed[case] += 1
                    except ValueError as exc:
                        warnings.append(f'{name}: line {index+1}: {mode}: {exc}')
        except (OSError, ValueError) as exc:
            warnings.append(f'{name}: {exc}')
    output = ['NATIVE FAVORITES VARIABLE-LENGTH FIELD EDIT AUDIT — READ ONLY', '',
              f'Favorites HPD files inspected: {inspected}',
              'Target: column 6 (1-based); one eligible record per observed layout per file and mode.',
              'Synthetic shorter and longer ASCII decimal substitutions, IN MEMORY only.',
              'Shorter probes choose a value with at least two digits; one-digit values cannot be shortened as positive integers.']
    for key in sorted(set(attempts) | set(skipped)):
        output.append(f'{key[0]} / {key[1]} columns / {key[2]}: {passed[key]} / {attempts[key]} passed'
                      + (f'; ineligible skipped: {skipped[key]}' if skipped[key] else ''))
    output += [f'Total probes passed: {sum(passed.values())} / {sum(attempts.values())}',
               f'Ineligible shorter cases skipped (no 2+-digit candidate in layout/file): {sum(skipped.values())}',
               f'Probe warnings: {len(warnings)}']
    output += ['WARNING: ' + w for w in warnings[:8]]
    output += ['Exact restoration of original file bytes verified for passing probes.',
               'Unrelated fields, line endings, tabs, trailing columns and other records preserved.',
               'Synthetic values are NOT validated for scanner range, meaning, or acceptance.',
               'No local configuration, scanner, or backup files were modified.',
               'Native SDS100 edited-file write compatibility: NOT VERIFIED',
               'Export action: DISABLED']
    return '\n'.join(output)
