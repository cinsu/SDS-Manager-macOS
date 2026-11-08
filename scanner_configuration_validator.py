# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Read-only, conservative structural checks for locally saved scanner configurations.

Findings are advisory; scanner-native compatibility is NOT certified by this module.
"""
from collections import Counter
from pathlib import Path
from native_favorites_reader import parse_native_favorites
from scanner_configurations import verify_configuration


def validate_configuration(folder, manifest=None):
    folder = Path(folder)
    errors, warnings = [], []
    try:
        verify_configuration(folder, manifest)
    except (OSError, ValueError, KeyError) as exc:
        errors.append(f'Configuration integrity: {exc}')
        return {'errors': errors, 'warnings': warnings, 'files': 0}
    files = sorted((folder / 'BCDx36HP' / 'favorites_lists').glob('*.hpd'))
    if not files:
        errors.append('No native Favorites .hpd files found.')
    for file in files:
        try:
            result = parse_native_favorites(file)
        except (OSError, ValueError, UnicodeError) as exc:
            errors.append(f'{file.name}: Cannot inspect file: {exc}')
            continue
        prefix = file.name
        warnings.extend(f'{prefix}: {message}' for message in result['warnings'])
        if not result['header'].get('TargetModel'):
            warnings.append(f'{prefix}: TargetModel header not found (compatibility not established).')
        if not result['header'].get('FormatVersion'):
            warnings.append(f'{prefix}: FormatVersion header not found (compatibility not established).')
        for system in result['systems']:
            name = system['name'].strip()
            label = f'{prefix} / {name or "(unnamed system)"}'
            if not name:
                errors.append(f'{label}: System name is empty.')
            groups = system['groups']
            if system['kind'] == 'Trunk':
                sites = [g for g in groups if g['kind'] == 'Site']
                tg_groups = [g for g in groups if g['kind'] == 'T-Group']
                if not sites:
                    errors.append(f'{label}: Trunked system has no sites.')
                for site in sites:
                    if not any(row[0].strip() == 'T-Freq' for row in site['leaves']):
                        errors.append(f'{label} / {site["name"]}: Site has no frequencies.')
                tgids = [row[5].strip() for g in tg_groups for row in g['leaves']
                         if row[0].strip() == 'TGID' and len(row) > 5 and row[5].strip()]
                for value, count in Counter(tgids).items():
                    if count > 1:
                        errors.append(f'{label}: Duplicate TGID {value} ({count} occurrences).')
            for group in groups:
                glabel = f'{label} / {group["name"] or "(unnamed group)"}'
                if not group['name'].strip():
                    warnings.append(f'{glabel}: Group/site name is empty.')
                if group['kind'] in ('Site', 'C-Group'):
                    freqkind = 'T-Freq' if group['kind'] == 'Site' else 'C-Freq'
                    frequencies = [row[5].strip() for row in group['leaves']
                                   if row[0].strip() == freqkind and len(row) > 5 and row[5].strip()]
                    for value, count in Counter(frequencies).items():
                        if count > 1:
                            warnings.append(f'{glabel}: Repeated frequency {value} ({count} occurrences); review whether intentional.')
                for row in group['leaves']:
                    kind = row[0].strip()
                    if kind in ('T-Freq', 'C-Freq', 'TGID'):
                        if len(row) <= 5 or not row[5].strip():
                            errors.append(f'{glabel}: {kind} record has no frequency/TGID value.')
                        elif kind in ('T-Freq', 'C-Freq'):
                            try:
                                value = int(row[5].strip())
                                if not 0 < value <= 2_000_000_000:
                                    raise ValueError()
                            except ValueError:
                                errors.append(f'{glabel}: Invalid frequency value {row[5]!r}.')
                        elif not row[5].strip().isdigit():
                            errors.append(f'{glabel}: Invalid TGID value {row[5]!r}.')
    return {'errors': errors, 'warnings': warnings, 'files': len(files)}
