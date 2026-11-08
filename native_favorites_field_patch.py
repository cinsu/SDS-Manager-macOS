# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Lossless, offline, field-aware HPD patcher for the EXISTING Favorites GUI.

Applies field substitutions only when native record order and tab widths match
the verified source. Unchanged fields, unknown extensions, and each individual
line ending remain byte-identical. No filesystem writes or Qt dependencies.
"""
from __future__ import annotations
from hashlib import sha256

MAX_BYTES = 25 * 1024 * 1024

class NativeStructureChanged(ValueError):
    """A row was added, removed, reordered, or changed width."""

class NativePatchError(ValueError):
    """An unsafe or ambiguous field substitution was requested."""

def _valid_field(kind, index, value, original, width):
    # Unknown fields and T-Freq extensions are intentionally opaque.
    if kind == 'T-Freq' and (index in (1, 2, 3, 4) or index >= 8):
        raise NativePatchError('Undocumented or reserved T-Freq field cannot be edited.')
    if kind in ('C-Freq', 'TGID') and index in (1, 2):
        raise NativePatchError('Native record identity/parent fields cannot be edited.')
    if kind in ('C-Freq', 'TGID') and index == 3:
        if not value.strip() or len(value) > 64:
            raise NativePatchError('Channel or talkgroup name must be 1–64 characters.')
    if kind in ('C-Freq', 'T-Freq') and index == 5:
        if not value.isascii() or not value.isdecimal() or not 100000 <= int(value) <= 1300000000:
            raise NativePatchError('Edited native frequency must be decimal Hz between 0.1 and 1300 MHz.')
    if kind == 'TGID' and index == 5:
        if not value.isascii() or not value.isdecimal() or not 0 <= int(value) <= 16777215:
            raise NativePatchError('Edited TGID must be decimal between 0 and 16777215.')
    if kind in ('C-Freq', 'TGID') and index == 4 and value.upper() not in ('ON', 'OFF'):
        raise NativePatchError('Edited Avoid value must be On or Off until other native encodings are validated.')
    if kind == 'C-Freq' and index == 6 and value.upper() not in ('AUTO', 'AM', 'NFM', 'FM'):
        raise NativePatchError('Edited modulation must match the documented native choices.')
    if kind == 'TGID' and index == 6 and value.upper() not in ('ALL', 'ANALOG', 'DIGITAL'):
        raise NativePatchError('Edited TGID audio type must match the documented native choices.')

def _lines(raw):
    """Split CRLF/LF/CR without ever normalizing the original terminators."""
    if b'\x00' in raw:
        raise NativePatchError('NUL-containing native file is not editable.')
    lines = raw.splitlines(keepends=True)
    if b''.join(lines) != raw:
        raise NativePatchError('Unrecognized native line terminators; refusing lossy edit.')
    result = []
    for line in lines:
        if line.endswith(b'\r\n'):
            result.append((line[:-2], b'\r\n'))
        elif line.endswith((b'\r', b'\n')):
            result.append((line[:-1], line[-1:]))
        else:
            result.append((line, b''))
    return result

def patch_native_fields(raw, desired_rows, encoding='cp1252', *, expected_sha256=None):
    """Return (new_bytes, changed_fields) or raise; never touches disk.

    A NativeStructureChanged exception signals a structural change, which
    requires separate handling. This function NEVER silently reflows rows.
    """
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise NativePatchError('Source is not bytes or exceeds 25 MiB.')
    if encoding not in ('cp1252', 'latin-1', 'utf-8-sig'):
        raise NativePatchError('Unrecognized native source encoding.')
    if expected_sha256 is not None and sha256(raw).hexdigest() != expected_sha256:
        raise NativePatchError('Native source changed since opening; reload before saving.')
    if not isinstance(desired_rows, list):
        raise NativePatchError('Expected a list of native records.')
    source_lines = _lines(raw)
    if len(source_lines) != len(desired_rows):
        raise NativeStructureChanged('Native record count changed; field-only patch is not applicable.')
    bom = b'\xef\xbb\xbf' if encoding == 'utf-8-sig' and raw.startswith(b'\xef\xbb\xbf') else b''
    codec = 'utf-8' if encoding == 'utf-8-sig' else encoding
    output = []
    edits = 0
    for lineno, ((line, ending), desired) in enumerate(zip(source_lines, desired_rows), 1):
        if not isinstance(desired, list) or not all(isinstance(x, str) for x in desired):
            raise NativePatchError(f'Line {lineno}: invalid edited record fields.')
        prefix = bom if lineno == 1 else b''
        if prefix and not line.startswith(prefix):
            raise NativePatchError('Source BOM mismatch.')
        original_fields = line[len(prefix):].split(b'\t')
        if len(original_fields) != len(desired):
            raise NativeStructureChanged(f'Line {lineno}: native column count changed.')
        try:
            decoded = [f.decode(codec, errors='strict') for f in original_fields]
        except UnicodeError as exc:
            raise NativePatchError(f'Line {lineno}: cannot decode native field.') from exc
        if decoded[0] != desired[0]:
            raise NativeStructureChanged(f'Line {lineno}: native record type/order changed.')
        if decoded == desired:
            output.append(line + ending)
            continue
        fields = list(original_fields)
        kind = decoded[0]
        for index, (before, after) in enumerate(zip(decoded, desired)):
            if before == after:
                continue
            if index == 0 or any(ch in after for ch in '\t\r\n\x00'):
                raise NativePatchError(f'Line {lineno}: unsafe native field characters.')
            _valid_field(kind, index, after, before, len(desired))
            try:
                fields[index] = after.encode(codec, errors='strict')
            except UnicodeError as exc:
                raise NativePatchError(f'Line {lineno}: value cannot be encoded in native charset.') from exc
            edits += 1
        output.append(prefix + b'\t'.join(fields) + ending)
    result = b''.join(output)
    if len(result) > MAX_BYTES:
        raise NativePatchError('Edited native file exceeds 25 MiB.')
    # Independent reconstruction check (including mixed newline and BOM).
    check = _lines(result)
    if len(check) != len(desired_rows):
        raise NativePatchError('Native patch round-trip line count mismatch.')
    for i, ((line, ending), wanted) in enumerate(zip(check, desired_rows), 1):
        content = line[len(bom):] if i == 1 and bom else line
        if [part.decode(codec) for part in content.split(b'\t')] != wanted:
            raise NativePatchError(f'Native patch round-trip mismatch at line {i}.')
        if ending != source_lines[i-1][1]:
            raise NativePatchError('Native patch changed a line terminator.')
    return result, edits
