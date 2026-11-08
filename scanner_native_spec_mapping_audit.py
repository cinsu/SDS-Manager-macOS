# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Read-only positional cross-check of Favorites fields with Uniden SDS spec v2.00.

Reference: SDS Series File Specification v2.00, PDF pages 16-17,
[C-Freq], [TGID], [T-Freq]. 1-based indices include record type.
The documented T-Freq layout has eight fields; observed nine-field
variants are preserved and reported as an *unverified* extension.
No data is serialized, saved, or written to scanner media.
"""
from collections import Counter
from pathlib import Path

MAX_BYTES = 25 * 1024 * 1024

# Names and positions are transcribed from the published specification.
# These are schema references, not evidence of scanner write compatibility.
SPEC_FIELDS = {
    'C-Freq': ('Record type', 'MyId', 'ParentId', 'Name Tag', 'Avoid',
               'Frequency (Hz)', 'Modulation', 'Audio Option', 'FuncTagId',
               'Attenuator', 'Delay', 'Volume Offset', 'Alert Tone',
               'Alert Volume', 'Alert Color', 'Alert Pattern',
               'Number tag', 'Priority Channel'),
    'TGID': ('Record type', 'MyId', 'ParentId', 'Name Tag', 'Avoid',
             'TGID string', 'Audio Type', 'FuncTagId', 'Delay',
             'Volume Offset', 'Alert Tone', 'Alert Volume', 'Alert Color',
             'Alert Pattern', 'Number tag', 'Priority Channel', 'TDMA Slot'),
    'T-Freq': ('Record type', 'Reserve(MyId)', 'ParentId', 'Reserve',
               'Reserve(Avoid)', 'Frequency (Hz)', 'LCN', 'Color Code/RAN/Area'),
}


def _ascii_decimal(value):
    return bool(value) and value.isascii() and value.isdigit()


def audit_spec_field_mapping(files):
    counts = Counter()
    widths = {kind: Counter() for kind in SPEC_FIELDS}
    warnings = []
    inspected = 0
    for name, source in sorted(files.items()):
        if not (name.startswith('favorites_lists/') and name.lower().endswith('.hpd')):
            continue
        try:
            p = Path(source)
            if p.is_symlink() or p.stat().st_size > MAX_BYTES:
                raise ValueError('symlink or Favorites file larger than 25 MiB')
            raw = p.read_bytes()
            if b'\x00' in raw:
                raise ValueError('NUL-containing Favorites file')
            inspected += 1
            for lineno, line in enumerate(raw.splitlines(), 1):
                # Ignore CR/LF without normalizing any other bytes.
                fields = line.rstrip(b'\r\n').split(b'\t')
                if not fields:
                    continue
                try:
                    kind = fields[0].decode('ascii')
                except UnicodeError:
                    continue
                if kind not in SPEC_FIELDS:
                    continue
                counts[kind] += 1
                widths[kind][len(fields)] += 1
                expected = len(SPEC_FIELDS[kind])
                if len(fields) < expected:
                    counts['short layouts'] += 1
                    warnings.append(f'{name}: line {lineno}: {kind} has {len(fields)} columns; spec shows {expected}')
                    continue
                if len(fields) > expected:
                    counts[kind + ' extra columns'] += 1
                    # Preserve and report, not an error: observed scanner files
                    # can carry columns absent from the documented layout.
                if not _ascii_decimal(fields[5]):
                    if kind == 'TGID':
                        counts['TGID nondecimal strings'] += 1
                    else:
                        counts['invalid frequency formats'] += 1
                        warnings.append(f'{name}: line {lineno}: {kind} column 6 is not ASCII decimal Hz')
                else:
                    counts[kind + ' decimal column 6'] += 1
                # Check only values whose permitted spellings are explicit in spec.
                avoid = fields[4].upper()
                if kind != 'T-Freq' and avoid not in (b'ON', b'OFF'):
                    counts['avoid exceptions'] += 1
                    warnings.append(f'{name}: line {lineno}: {kind} column 5 Avoid is not On/Off')
                elif kind != 'T-Freq':
                    counts[kind + ' avoid matches'] += 1
                if kind == 'C-Freq':
                    if fields[6].upper() in (b'AUTO', b'AM', b'NFM', b'FM'):
                        counts['C-Freq modulation matches'] += 1
                    else:
                        counts['C-Freq modulation exceptions'] += 1
                        warnings.append(f'{name}: line {lineno}: C-Freq column 7 modulation needs review')
                elif kind == 'TGID':
                    if fields[6].upper() in (b'ALL', b'ANALOG', b'DIGITAL'):
                        counts['TGID audio matches'] += 1
                    else:
                        counts['TGID audio exceptions'] += 1
                        warnings.append(f'{name}: line {lineno}: TGID column 7 audio type needs review')
                else:
                    if _ascii_decimal(fields[6]):
                        counts['T-Freq LCN decimal'] += 1
                    else:
                        counts['T-Freq LCN nondecimal'] += 1
                        warnings.append(f'{name}: line {lineno}: T-Freq column 7 LCN needs review')
        except (OSError, ValueError) as exc:
            warnings.append(f'{name}: {exc}')

    def layout(kind):
        return ', '.join(f'{width}: {num}' for width, num in sorted(widths[kind].items())) or 'none'

    lines = [
        'NATIVE FAVORITES SPEC FIELD MAPPING AUDIT — READ ONLY', '',
        'Reference: Uniden SDS Series File Specification v2.00, PDF pages 16-17 ([C-Freq], [TGID], [T-Freq]).',
        '1-based field positions include the record-type column.',
        f'Favorites HPD files inspected: {inspected}',
        'Official mapping: C-Freq col 4=Name, 5=Avoid, 6=Frequency (Hz), 7=Modulation; 18 documented columns.',
        'Official mapping: T-Freq col 5=Reserve(Avoid), 6=Frequency (Hz), 7=LCN, 8=Color Code/RAN/Area; 8 documented columns.',
        'Official mapping: TGID col 4=Name, 5=Avoid, 6=TGID string, 7=Audio Type; 17 documented columns.',
        f'C-Freq: {counts["C-Freq"]} records; observed column counts: {layout("C-Freq")}',
        f'  Column 6 decimal Hz: {counts["C-Freq decimal column 6"]} / {counts["C-Freq"]}; modulation enum: {counts["C-Freq modulation matches"]} / {counts["C-Freq"]}',
        f'T-Freq: {counts["T-Freq"]} records; observed column counts: {layout("T-Freq")}',
        f'  Column 6 decimal Hz: {counts["T-Freq decimal column 6"]} / {counts["T-Freq"]}; column 7 decimal LCN: {counts["T-Freq LCN decimal"]} / {counts["T-Freq"]}',
        f'  Extra undocumented T-Freq columns: {counts["T-Freq extra columns"]} records (preserve as opaque, do NOT infer their meaning).',
        f'TGID: {counts["TGID"]} records; observed column counts: {layout("TGID")}',
        f'  Column 6 decimal-only TGID strings: {counts["TGID decimal column 6"]} / {counts["TGID"]}; audio type enum: {counts["TGID audio matches"]} / {counts["TGID"]}',
        f'  Nondecimal TGID strings: {counts["TGID nondecimal strings"]} (permitted as strings; not automatically an error).',
        f'Column 5 Avoid On/Off (C-Freq and TGID only): {counts["C-Freq avoid matches"] + counts["TGID avoid matches"]} / {counts["C-Freq"] + counts["TGID"]}',
        f'Layouts shorter than documented: {counts["short layouts"]}',
        f'Format/field warnings: {len(warnings)}',
    ]
    lines.extend('WARNING: ' + warning for warning in warnings[:12])
    lines.extend([
        'This cross-check confirms published field POSITIONS and observed value shapes; it does not certify scanner acceptance.',
        'Undocumented trailing columns, all other fields, CFG/INF data, and original file bytes remain untouched.',
        'No local configuration, scanner, or backup files were modified.',
        'Native SDS100 edited-file write compatibility: NOT VERIFIED',
        'Export action: DISABLED',
    ])
    return '\n'.join(lines)
