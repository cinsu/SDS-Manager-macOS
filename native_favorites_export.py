# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Conservative offline native HPD export; never writes to mounted scanner media."""
from pathlib import Path
import hashlib
from native_favorites_reader import parse_native_favorites
from native_favorites_field_patch import patch_native_fields, NativeStructureChanged, NativePatchError


def build_native_bytes(entries):
    if not entries or entries[0].get('scope') != 'metadata':
        raise ValueError('Only drafts created from a native .hpd file can be exported.')
    meta = entries[0]
    if not str(meta.get('key', [''])[0]).startswith('native-copy-meta'):
        raise ValueError('Draft has no verified native .hpd origin metadata.')
    systems = entries[1:]
    if not systems or any(e.get('origin') != 'native-copy' or e.get('kind') not in ('Trunk', 'Conventional') for e in systems):
        raise ValueError('Draft includes non-native or unsupported system records; export blocked to prevent data loss.')
    rows = list(meta.get('records', []))
    for system in systems:
        records = system.get('records', [])
        if not records or records[0][0] != system['kind']:
            raise ValueError('System header is missing or inconsistent: ' + system.get('name', 'unnamed'))
        rows.extend(records)
    if any(not isinstance(row, list) or not all(isinstance(field, str) for field in row) for row in rows):
        raise ValueError('Invalid native record data; export blocked.')
    if not any(row[0] == 'TargetModel' and len(row) > 1 and row[1] == 'BCDx36HP' for row in rows):
        raise ValueError('Missing supported BCDx36HP target header.')
    if not any(row[0] == 'FormatVersion' for row in rows):
        raise ValueError('Missing native format version.')
    newline = meta.get('newline', '\r\n')
    if newline not in ('\r\n', '\n', '\r'):
        raise ValueError('Invalid newline metadata.')
    text = newline.join('\t'.join(row) for row in rows)
    if meta.get('final_newline', True):
        text += newline
    encoding = meta.get('encoding', 'cp1252')
    if encoding not in ('cp1252', 'latin-1', 'utf-8-sig'):
        raise ValueError('Unsupported source encoding.')
    # Existing GUI edits already operate on native record lists. For field-only
    # edits, patch the VERIFIED original bytes instead of rebuilding whole lines.
    # This preserves mixed CR/LF, BOM, undocumented columns and untouched bytes.
    source = Path(meta.get('source_path', ''))
    if not source.is_file() or source.is_symlink():
        raise ValueError('Native source file missing or unsafe; reopen configuration.')
    expected_digest = meta.get('source_sha256')
    if not isinstance(expected_digest, str) or len(expected_digest) != 64:
        raise ValueError('Missing native source checksum; reopen configuration before saving.')
    original = source.read_bytes()
    try:
        payload, _changed_fields = patch_native_fields(
            original, rows, encoding, expected_sha256=expected_digest)
        return payload, rows
    except NativeStructureChanged:
        # Existing editor also supports adding/deleting rows. Keep that prior
        # LOCAL-only behavior; structural serialization is not yet byte-proven.
        # Scanner export remains disabled until independently validated.
        if not meta.get('source_sha256') or hashlib.sha256(original).hexdigest() != meta['source_sha256']:
            raise ValueError('Native source changed since opening; reload before saving.')
        return text.encode(encoding), rows


def validate_export_file(path, expected_rows):
    data = Path(path).read_bytes()
    if len(data) > 25 * 1024 * 1024:
        raise ValueError('Export exceeds native file size limit.')
    decoded = None
    for enc in ('utf-8-sig', 'cp1252'):
        try:
            decoded = data.decode(enc)
            break
        except UnicodeDecodeError:
            pass
    if decoded is None:
        raise ValueError('Cannot decode exported file.')
    actual = [line.split('\t') for line in decoded.splitlines()]
    if actual != expected_rows:
        raise ValueError('Exported record round-trip mismatch.')
    parsed = parse_native_favorites(path)
    if parsed['warnings']:
        raise ValueError('Native parser validation warnings: ' + '; '.join(parsed['warnings'][:3]))
    return {'systems':len(parsed['systems']), 'sha256':hashlib.sha256(data).hexdigest(), 'bytes':len(data)}
