# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Read-only, byte-preserving inspection of native GlobalSetting records.

No field is considered editable until its documented type and position are mapped.
"""


def read_global_setting(data: bytes):
    if len(data) > 2_000_000 or b"\x00" in data:
        raise ValueError("Unsupported profile size or binary data")
    records = [line.split(b"\t") for line in data.splitlines()
               if line.split(b"\t", 1)[0] == b"GlobalSetting"]
    if len(records) != 1:
        raise ValueError("Expected exactly one GlobalSetting record")
    fields = records[0][1:]
    if not fields or any(b"\r" in field or b"\n" in field for field in fields):
        raise ValueError("Invalid GlobalSetting field layout")
    return tuple(field.decode("utf-8", errors="replace") for field in fields)


# One-based positions from Uniden SDS Series File Specification v2.00; see profile_schema.py for the
# per-field validators.  Position 21 text values are verified against real SDS100 profile.cfg captures.
from profile_schema import SCHEMA, patch_fields

_FIELDS = SCHEMA['GlobalSetting']['fields']
GLOBAL_LABELS = tuple(f.label for f in _FIELDS)
EDITABLE_GLOBAL_CHOICES = {i + 1: f.choices() for i, f in enumerate(_FIELDS) if f.choices() is not None}


def patch_global_setting(data: bytes, changes: dict[int, str]) -> bytes:
    """Losslessly patch only validated, documented field positions."""
    current = read_global_setting(data)
    if not changes or any(type(k) is not int or k not in EDITABLE_GLOBAL_CHOICES
                          or type(v) is not str or v not in EDITABLE_GLOBAL_CHOICES[k]
                          for k, v in changes.items()):
        raise ValueError('Unsupported GlobalSetting edit')
    if len(current) < max(changes):
        raise ValueError('GlobalSetting record is shorter than requested field')
    return patch_fields(data, {('GlobalSetting', 0, k): v for k, v in changes.items()})


def describe_global_changes(original: bytes, changes: dict[int, str]) -> tuple[str, ...]:
    """Build a human-readable, position-aware change list for pre-save review."""
    before = read_global_setting(original)
    after = read_global_setting(patch_global_setting(original, changes))
    result = []
    for position, (old, new) in enumerate(zip(before, after), start=1):
        if old != new:
            label = GLOBAL_LABELS[position - 1] if position <= len(GLOBAL_LABELS) else 'Undocumented'
            result.append(f'{position:02d} — {label}: {old!r} → {new!r}')
    return tuple(result)
