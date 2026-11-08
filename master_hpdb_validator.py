# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Read-only streaming validation of Uniden BCDx36HP MasterHpdb text files."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime
import json
import gzip
from pathlib import Path

TAGS = frozenset('AreaCounty AreaState BandPlan_Mot BandPlan_P25 C-Freq C-Group Conventional CountyInfo DateModified File FleetMap FormatVersion LM LM_Frequency Rectangle Site StateInfo TargetModel T-Freq TGID T-Group Trunk'.split())
HEADER = ('TargetModel', 'FormatVersion', 'DateModified')
TRAILER = 'File'
MAX_ERRORS = 30
MAX_UNCOMPRESSED_BYTES = 300 * 1024 * 1024
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024


def validate(path):
    path = Path(path).expanduser()
    compressed = path.suffix.lower() == '.gz'
    if compressed and path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError('Gzip archive exceeds 100 MB safety limit')
    if not compressed and path.stat().st_size > MAX_UNCOMPRESSED_BYTES:
        raise ValueError('Master database exceeds 300 MB safety limit')
    result = {'file': str(path.resolve()), 'bytes': 0,
              'header': {}, 'counts': {}, 'lines': 0, 'errors': [], 'warnings': []}
    counts = Counter()
    opener = gzip.open if compressed else open
    with opener(path, 'rt', encoding='cp1252', errors='strict', newline='') as stream:
        for number, raw in enumerate(stream, 1):
            result['bytes'] += len(raw.encode('cp1252'))
            if result['bytes'] > MAX_UNCOMPRESSED_BYTES:
                raise ValueError('Decompressed master exceeds 300 MB safety limit')
            result['lines'] = number
            fields = raw.rstrip('\r\n').split('\t')
            tag = fields[0]
            counts[tag] += 1
            if not tag or tag not in TAGS:
                _issue(result, 'errors', f'Line {number}: unknown record type {tag!r}')
            if number <= 3:
                expected = HEADER[number - 1]
                if tag != expected:
                    _issue(result, 'errors', f'Line {number}: expected {expected}, found {tag!r}')
            if tag in HEADER:
                if len(fields) != 2:
                    _issue(result, 'errors', f'Line {number}: {tag} must have two tab-separated fields')
                elif tag in result['header']:
                    _issue(result, 'errors', f'Line {number}: duplicate header {tag}')
                else:
                    result['header'][tag] = fields[1]
            elif tag == TRAILER:
                if len(fields) != 2 or fields[1] != 'HomePatrol Database':
                    _issue(result, 'errors', f'Line {number}: invalid File trailer')
                if counts[TRAILER] > 1 or number <= 3:
                    _issue(result, 'errors', f'Line {number}: unexpected File trailer')
            elif len(fields) < 3:
                _issue(result, 'errors', f'Line {number}: {tag} has fewer than three fields')
    result['counts'] = dict(sorted(counts.items()))
    if not result['lines']:
        _issue(result, 'errors', 'Empty master database')
        tag = None
    if counts[TRAILER] != 1:
        _issue(result, 'errors', f'Expected one File trailer; found {counts[TRAILER]}')
    if tag != TRAILER:
        _issue(result, 'errors', 'Last record must be File trailer')
    for key in HEADER:
        if counts[key] != 1:
            _issue(result, 'errors', f'Expected one {key} record; found {counts[key]}')
    if result['header'].get('TargetModel') != 'BCDx36HP':
        _issue(result, 'errors', 'TargetModel is not BCDx36HP')
    if result['header'].get('FormatVersion') != '1.00':
        _issue(result, 'errors', 'Unsupported FormatVersion (expected 1.00)')
    stamp = result['header'].get('DateModified')
    if stamp:
        try:
            datetime.strptime(stamp, '%m/%d/%Y %H:%M:%S')
        except ValueError:
            _issue(result, 'errors', 'Invalid DateModified timestamp')
    result['valid'] = not result['errors']
    return result


def _issue(result, category, message):
    if len(result[category]) < MAX_ERRORS:
        result[category].append(message)
    elif len(result[category]) == MAX_ERRORS:
        result[category].append('Further issues omitted')


def compare(left, right):
    return {tag: {'reference': left['counts'].get(tag, 0),
                  'candidate': right['counts'].get(tag, 0),
                  'difference': right['counts'].get(tag, 0) - left['counts'].get(tag, 0)}
            for tag in sorted(set(left['counts']) | set(right['counts']))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('master', help='MasterHpdb.hp1 or decompressed MasterHpdb_MM_DD_YYYY')
    parser.add_argument('--compare', metavar='REFERENCE', help='Optional second master database')
    parser.add_argument('--json', action='store_true', help='Machine-readable report')
    args = parser.parse_args()
    try:
        candidate = validate(args.master)
        reference = validate(args.compare) if args.compare else None
    except (OSError, UnicodeError, ValueError, EOFError) as exc:
        parser.exit(2, f'Cannot read database: {exc}\n')
    if args.json:
        print(json.dumps({'candidate': candidate, 'reference': reference,
                          'comparison': compare(reference, candidate) if reference else None}, indent=2))
    else:
        for label, report in [('Candidate', candidate), ('Reference', reference)]:
            if report is None:
                continue
            print(f'\n{label}: {report["file"]}\nValid: {report["valid"]}  Lines: {report["lines"]:,}  Bytes: {report["bytes"]:,}')
            print('Header:', report['header'])
            for tag, count in report['counts'].items():
                print(f'  {tag:<18} {count:>9,}')
            for error in report['errors']:
                print('ERROR:', error)
        if reference:
            print('\nRecord count changes (candidate - reference):')
            for tag, item in compare(reference, candidate).items():
                print(f'  {tag:<18} {item["difference"]:+,}')
    raise SystemExit(0 if candidate['valid'] and (reference is None or reference['valid']) else 1)


if __name__ == '__main__':
    main()
