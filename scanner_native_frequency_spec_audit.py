# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Read-only audit against Uniden SDS Series File Specification v2.00, basic rules p.6."""
from pathlib import Path
from collections import Counter

KINDS = ('C-Freq', 'T-Freq')
MAX_BYTES = 25 * 1024 * 1024
SPEC = 'Uniden SDS100/150/200 File Specification v2.00, Basic Rule (page 6): 1 = 1 Hz; 851.0125 MHz => 851012500'


def hz_to_mhz(hz):
    """Exact integer arithmetic, never float."""
    if type(hz) is not int or hz < 0:
        raise ValueError('nonnegative integer Hz required')
    return f'{hz // 1_000_000}.{hz % 1_000_000:06d}'


def mhz_to_hz(value):
    """Require an exact Hz quantity, with no rounding."""
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError('MHz must be a canonical decimal string')
    parts = value.split('.')
    if len(parts) > 2 or not parts[0].isascii() or not parts[0].isdecimal():
        raise ValueError('invalid MHz digits')
    fraction = parts[1] if len(parts) == 2 else ''
    if fraction and (not fraction.isascii() or not fraction.isdecimal()):
        raise ValueError('invalid MHz fraction')
    if len(parts) == 2 and not fraction:
        raise ValueError('empty MHz fraction')
    if len(fraction) > 6:
        raise ValueError('sub-Hz precision unsupported; no rounding permitted')
    return int(parts[0]) * 1_000_000 + int(fraction.ljust(6, '0'))


def inspect_frequency_spec(files):
    counts = Counter()
    warnings = []
    examples = []
    for name, source in sorted(files.items()):
        if not (name.startswith('favorites_lists/') and name.lower().endswith('.hpd')):
            continue
        try:
            p = Path(source)
            if p.is_symlink() or p.stat().st_size > MAX_BYTES:
                raise ValueError('symlink or oversized file')
            raw = p.read_bytes()
            if b'\x00' in raw:
                raise ValueError('NUL byte')
            enc = 'utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'cp1252'
            for lineno, line in enumerate(raw.decode(enc, errors='strict').splitlines(), 1):
                fields = line.split('\t')
                if not fields or fields[0].strip() not in KINDS:
                    continue
                kind = fields[0].strip()
                counts[kind + ' records'] += 1
                if len(fields) < 6 or not fields[5].isascii() or not fields[5].isdecimal():
                    counts['unverified numeric formats'] += 1
                    continue
                token = fields[5]
                hz = int(token)
                mhz = hz_to_mhz(hz)
                if mhz_to_hz(mhz) != hz:
                    counts['conversion mismatches'] += 1
                else:
                    counts[kind + ' exact conversions'] += 1
                if len(examples) < 4:
                    examples.append(f'  {kind}: {token} Hz => {mhz} MHz => {hz} Hz')
        except (OSError, UnicodeError, ValueError) as exc:
            warnings.append(f'{name}: {exc}')
    lines = ['NATIVE FREQUENCY SPECIFICATION AUDIT — READ ONLY', '',
             'Reference: ' + SPEC,
             'Uniden specifies 1 Hz units for frequency fields; this replaces the earlier unverified unit hypothesis.',
             'Conversion uses integer arithmetic; no floating-point rounding.',
             f'C-Freq: {counts["C-Freq exact conversions"]} / {counts["C-Freq records"]} exact Hz-to-MHz-to-Hz conversions',
             f'T-Freq: {counts["T-Freq exact conversions"]} / {counts["T-Freq records"]} exact Hz-to-MHz-to-Hz conversions',
             f'Conversion mismatches: {counts["conversion mismatches"]}',
             f'Unverified numeric formats: {counts["unverified numeric formats"]}',
             'Representative source values (not scanner-readback verification):'] + examples
    lines += [f'File read/decode warnings: {len(warnings)}']
    lines += ['WARNING: ' + w for w in warnings[:15]]
    lines += ['TGID is not a frequency; no conversion attempted.',
              'This verifies exact unit conversion, NOT field position, band limits, modulation, TGID rules, or scanner acceptance.',
              'No local configuration, backup or scanner files were modified.',
              'Native SDS100 edited-file write compatibility: NOT VERIFIED',
              'Export action: DISABLED']
    return '\n'.join(lines)
