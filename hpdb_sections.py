# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Group database records into systems and departments (no Qt; shared by the panel and rr_convert)."""

SYSTEMS = {'Conventional', 'Trunk'}
GROUPS = {'C-Group', 'T-Group'}
CHILDREN = {'C-Freq', 'T-Freq', 'TGID', 'T-Group', 'C-Group', 'Site', 'C-Channel', 'T-Channel', 'C-Frequency', 'T-Frequency', 'Tgid', 'C-Freq', 'T-Id'}


def build_sections(records):
    """Preserve complete source record spans, including site/department children."""
    sections = []
    current = None
    for record in records:
        kind = record[0].strip() if record else ''
        if kind in SYSTEMS:
            current = {'name': record[3] if len(record) > 3 else '(unnamed system)',
                       'kind': kind, 'records': [], 'children': []}
            sections.append(current)
        if current is not None:
            current['records'].append(record)
            if kind in GROUPS:
                current['children'].append({'name': record[3] if len(record) > 3 else kind,
                                            'kind': kind, 'records': [record]})
            elif kind not in SYSTEMS and current['children']:
                current['children'][-1]['records'].append(record)
    return sections
