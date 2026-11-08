# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Experimental isolated one-state HPDB reconstruction. Never touches scanner."""
from pathlib import Path

def transform_record(fields):
    fields = fields.copy()
    # TGID decimal normalization (experimental)
    # Sentinel's October 2025 reference converts 125.1 to 0.
    # Preserve integer and hyphenated TGID identifiers.
    if fields and fields[0] == "TGID" and len(fields) > 5:
        value = fields[5]

        parts = value.split(".")

        if (
            len(parts) == 2
            and parts[0].isdigit()
            and parts[1].isdigit()
        ):
            fields[5] = "0"

    """Apply transformations observed in the 2025 South Carolina reference."""

    fields = fields.copy()
    record_type = fields[0]

    if record_type == "Conventional":
        if len(fields) != 7:
            raise ValueError("Unexpected Conventional record width")
        fields[5] = ""
        fields.extend([""] * 8)

    elif record_type == "Trunk":
        if len(fields) != 22:
            raise ValueError("Unexpected Trunk record width")
        fields[5] = ""

    elif record_type == "C-Group":
        if len(fields) != 9:
            raise ValueError("Unexpected C-Group record width")
        fields.extend(["Off", "Global"])

    elif record_type == "C-Freq":
        if len(fields) != 9:
            raise ValueError("Unexpected C-Freq record width")
        if fields[7] == "NAC=SRCH":
            fields[7] = "NAC=Srch"
        fields.extend([""] * 9)

    elif record_type == "Site":
        if len(fields) != 18:
            raise ValueError("Unexpected Site record width")
        if fields[17] == "SRCH":
            fields[17] = "Srch"
        fields.extend(["Global", "FDMA"])

    elif record_type == "T-Freq":
        if len(fields) != 8:
            raise ValueError("Unexpected T-Freq record width")
        fields[4] = ""
        fields.append("Any")

    elif record_type == "T-Group":
        if len(fields) != 9:
            raise ValueError("Unexpected T-Group record width")
        fields.append("")

    elif record_type == "BandPlan_P25":
        if len(fields) != 34:
            raise ValueError("Unexpected BandPlan_P25 record width")
        fields.extend(["0"] * 16)

    elif record_type == "Rectangle":
        if len(fields) != 6:
            raise ValueError("Unexpected Rectangle record width")
        fields[1] = ""

    return fields

def reconstruct_state(master, state_id, destination):
    master = Path(master).expanduser().resolve(strict=True)
    destination = Path(destination).expanduser().resolve()
    if not (1 <= state_id <= 999999):
        raise ValueError('Invalid state identifier')
    if master == destination:
        raise ValueError('Destination cannot be the master')
    from master_hpdb_validator import validate
    report = validate(master)
    if not report['valid']:
        raise ValueError('Master database failed structural validation')
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Output already exists; overwrite refused')
    selected = False
    count = 0
    # Exclusive creation: do not overwrite existing files.
    with destination.open('x', encoding='utf-8', newline='') as output:
        try:
            output.write('TargetModel\tBCDx36HP\r\nFormatVersion\t1.00\r\n')
            import gzip
            opener = gzip.open if master.suffix.lower() == '.gz' else open
            with opener(master, 'rt', encoding='utf-8-sig', newline='') as stream:
                for raw in stream:
                    fields = raw.rstrip('\r\n').split('\t')
                    tag = fields[0]
                    if tag in ('Conventional', 'Trunk'):
                        selected = len(fields) >= 3 and fields[2] == f'StateId={state_id}'
                    elif tag in ('LM', 'LM_Frequency', 'File'):
                        selected = False
                    if selected:
                        output.write('\t'.join(transform_record(fields)) + '\r\n')
                        count += 1
            if not count:
                raise ValueError('No systems found for this state ID')
        except BaseException:
            output.close()
            destination.unlink(missing_ok=True)
            raise
    return {'records': count + 2, 'bytes': destination.stat().st_size, 'path': str(destination)}
