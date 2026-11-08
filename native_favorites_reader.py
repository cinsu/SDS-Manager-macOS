# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Read-only parser for genuine Uniden BCDx36HP Favorites .hpd files."""
from pathlib import Path
def record_columns(row):
    kind = row[0].strip()
    name = row[3].strip() if len(row)>3 and row[3].strip() else kind
    frequency = ''
    if kind in ('C-Freq','T-Freq') and len(row)>5 and row[5].strip().isdigit():
        frequency = f'{int(row[5])/1_000_000:.6f}'
        if name == kind: name = frequency + ' MHz'
    tgid = row[5].strip() if kind == 'TGID' and len(row)>5 else ''
    return [name,kind,frequency,tgid,'','']

SYSTEMS = {'Trunk', 'Conventional'}
GROUPS = {'Site', 'T-Group', 'C-Group'}
LEAVES = {'T-Freq', 'C-Freq', 'TGID'}

def parse_native_favorites(path):
    path = Path(path)
    if path.stat().st_size > 25 * 1024 * 1024:
        raise ValueError('Favorites file exceeds 25 MB read-only inspection limit')
    raw = path.read_bytes()
    if b'\x00' in raw:
        raise ValueError('Binary data is not a supported text Favorites file')
    content = raw.decode('utf-8-sig') if raw.startswith(b'\xef\xbb\xbf') else raw.decode('cp1252')
    systems, warnings, header = [], [], {}
    system = group = None
    for number, line in enumerate(content.splitlines(), 1):
        if not line.strip(): continue
        row = line.split('\t')
        kind = row[0].strip()
        if kind in ('TargetModel', 'FormatVersion'):
            header[kind] = row[1].strip() if len(row)>1 else ''
        if kind in SYSTEMS:
            system = {'name':row[3] if len(row)>3 else kind, 'kind':kind, 'row':row, 'groups':[], 'other':[]}
            systems.append(system)
            group = None
        elif kind in GROUPS:
            if system is None:
                warnings.append(f'Line {number}: {kind} outside a system')
                continue
            group = {'name':row[3] if len(row)>3 else kind, 'kind':kind, 'row':row, 'leaves':[], 'other':[]}
            system['groups'].append(group)
        elif kind in LEAVES:
            if group is None:
                warnings.append(f'Line {number}: {kind} without a parent group/site')
                continue
            group['leaves'].append(row)
        elif system is not None:
            (group['other'] if group is not None else system['other']).append(row)
        elif kind not in ('TargetModel','FormatVersion'):
            pass  # preamble metadata is not a system record
    if not systems:
        warnings.append('No conventional or trunked systems found')
    return {'header':header, 'systems':systems, 'warnings':warnings, 'record_columns':record_columns}
