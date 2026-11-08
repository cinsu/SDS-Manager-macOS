# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Generate hpdb.cfg from a validated Master HPDB; offline-only."""
from pathlib import Path
import gzip
import re

TAGS = {b'TargetModel', b'FormatVersion', b'DateModified', b'StateInfo', b'CountyInfo', b'LM', b'LM_Frequency'}

def generate_config(master, destination):
    """Write config to a new file, preserving source bytes and StateInfo county order."""
    master, destination = Path(master), Path(destination)
    opener = gzip.open if master.suffix.lower() == '.gz' else open
    header, states, counties, lm = [], [], [], []
    with opener(master, 'rb') as source:
        for line in source:
            tag = line.split(b'\t', 1)[0]
            if tag in (b'TargetModel', b'FormatVersion', b'DateModified'):
                header.append(line)
            elif tag == b'StateInfo':
                states.append(line)
            elif tag == b'CountyInfo':
                counties.append(line)
            elif tag in (b'LM', b'LM_Frequency'):
                lm.append(line)
    if len(header) != 3 or len(states) != 68 or not counties:
        raise ValueError('Invalid HPDB configuration metadata; refusing export')
    order = {}
    for index, line in enumerate(states):
        match = re.search(rb'(?:^|\t)StateId=(\d+)(?:\t|\r|\n|$)', line)
        if not match: raise ValueError('Malformed StateInfo')
        sid = int(match.group(1))
        if sid in order: raise ValueError('Duplicate StateInfo')
        order[sid] = index
    def county_order(line):
        match = re.search(rb'(?:^|\t)StateId=(\d+)(?:\t|\r|\n|$)', line)
        if not match or int(match.group(1)) not in order:
            raise ValueError('CountyInfo references unknown state')
        return order[int(match.group(1))]
    counties.sort(key=county_order)  # stable sort retains original within-state order
    payload = b''.join(header + states + counties + lm)
    with destination.open('xb') as target:
        target.write(payload)
    return {'records': len(header)+len(states)+len(counties)+len(lm), 'bytes':len(payload)}
