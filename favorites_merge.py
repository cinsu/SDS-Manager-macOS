# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Safe, offline incremental merge of database selections into Favorites drafts.

Scanner-imported Favorites systems have native-copy keys, not HPDB source keys.
Match a unique system by kind/name (with user confirmation in the UI), and
merge a unique existing department by kind/name while retaining its native row.
"""

HEADERS = {'C-Group', 'T-Group', 'Site'}
LEAVES = {'C-Freq', 'T-Freq', 'TGID'}


class AmbiguousFavoritesMatch(ValueError):
    """Several existing items have the same apparent identity; do not guess."""


def _kind(row):
    return row[0].strip() if row else ''


def _name(row):
    return ' '.join(row[3].split()).casefold() if len(row) > 3 else ''


def _matching_header(rows, header):
    """Return the unique matching header's index, or None if absent.

    Prefer exact native rows; fall back to unique type/name when source IDs or
    other native metadata differ. Never guess among duplicate department names.
    """
    indices = [i for i, row in enumerate(rows) if _kind(row) in HEADERS]
    exact = [i for i in indices if tuple(rows[i]) == tuple(header)]
    if len(exact) > 1:
        raise AmbiguousFavoritesMatch('Duplicate identical department/site headers; cannot choose a target.')
    if exact:
        return exact[0]
    name = _name(header)
    if not name:
        return None
    matches = [i for i in indices if _kind(rows[i]) == _kind(header) and _name(rows[i]) == name]
    if len(matches) > 1:
        raise AmbiguousFavoritesMatch(
            f'Multiple {_kind(header)} entries named {header[3]!r}; select a unique target before adding.')
    return matches[0] if matches else None


def _leaf_identity(row):
    """Identify a leaf without requiring every editable setting to be identical.

    A channel's name AND frequency distinguish it; a trunked frequency uses
    its frequency and LCN, and a talkgroup uses its TGID. The existing native
    row always wins when the same leaf is already present.
    """
    kind = _kind(row)
    if kind == 'C-Freq' and len(row) > 5:
        return kind, _name(row), row[5].strip()
    if kind == 'T-Freq' and len(row) > 6:
        return kind, row[5].strip(), row[6].strip()
    if kind == 'TGID' and len(row) > 5:
        return kind, row[5].strip()
    return None


def _already_present(existing, incoming):
    if tuple(incoming) in {tuple(row) for row in existing}:
        return True
    identity = _leaf_identity(incoming)
    return identity is not None and any(_leaf_identity(row) == identity for row in existing)


def find_existing_system(entries, source_key, source_header):
    """Return (entry, matched_by_name), or (None, False).

    Source keys take precedence. A different scanner-import key can match only
    one existing system of the same type and normalized name. Caller must show
    the name-based target in the confirmation preview before changing records.
    """
    key = tuple(source_key)
    exact = [entry for entry in entries if tuple(entry.get('key', [])[:2]) == key]
    if len(exact) > 1:
        raise AmbiguousFavoritesMatch('Multiple Favorites systems have the same database source key.')
    if exact:
        return exact[0], False
    kind = _kind(source_header)
    name = _name(source_header)
    if not name or kind not in ('Conventional', 'Trunk'):
        return None, False
    matches = [entry for entry in entries
               if entry.get('scope') != 'metadata' and entry.get('records')
               and _kind(entry['records'][0]) == kind and _name(entry['records'][0]) == name]
    if len(matches) > 1:
        raise AmbiguousFavoritesMatch(
            f'Multiple {kind} systems named {source_header[3]!r} exist in this Favorites List. '
            'No system was modified; resolve the duplicate names first.')
    return (matches[0], True) if matches else (None, False)


def merge_records(existing, incoming):
    """Return (merged records, count added), retaining existing native headers.

    System names/kinds must match. The caller explicitly confirms cross-source
    merges. No existing row is overwritten, and ambiguous group names abort.
    """
    if not existing or not incoming:
        raise ValueError('Missing system header')
    if (_kind(existing[0]) != _kind(incoming[0]) or
            _name(existing[0]) != _name(incoming[0]) or not _name(existing[0])):
        raise ValueError('Cannot merge different Favorites systems')
    merged = [list(row) for row in existing]
    active_index = None
    added = 0
    for row in incoming[1:]:
        if not row:
            continue
        kind = _kind(row)
        if kind in HEADERS:
            active_index = _matching_header(merged, row)
            if active_index is None:
                if kind == 'Site':
                    active_index = next((i for i, old in enumerate(merged)
                                         if _kind(old) == 'T-Group'), len(merged))
                    merged.insert(active_index, list(row))
                else:
                    active_index = len(merged)
                    merged.append(list(row))
                added += 1
        elif active_index is not None:
            end = active_index + 1
            while end < len(merged) and _kind(merged[end]) not in HEADERS:
                end += 1
            if not _already_present(merged[active_index + 1:end], row):
                merged.insert(end, list(row))
                added += 1
    return merged, added



def native_conventional_candidate(existing_entry, incoming_records):
    """Build safe new-channel records for an existing scanner-native department.

    Database HPDB records carry database IDs and different opaque settings.
    New native C-Freq rows instead inherit a real channel template in the
    destination department, changing only new-record ID, name and frequency.
    Native export's structural validator then independently checks the result.
    """
    if existing_entry.get('origin') != 'native-copy':
        return [list(row) for row in incoming_records]
    if _kind(existing_entry['records'][0]) != 'Conventional':
        return [list(row) for row in incoming_records]
    old = existing_entry['records']
    output = [list(incoming_records[0])]
    active_index = None
    for row in incoming_records[1:]:
        kind = _kind(row)
        if kind == 'C-Group':
            active_index = _matching_header(old, row)
            if active_index is None:
                raise ValueError('The selected department does not exist in this native Favorites List. '
                                 'Adding a whole department is not supported by the current scanner export.')
            output.append(list(old[active_index]))
        elif kind == 'C-Freq':
            if active_index is None:
                raise ValueError('Selected conventional channel has no matching department.')
            end = active_index + 1
            while end < len(old) and _kind(old[end]) not in HEADERS:
                end += 1
            native_channels = [r for r in old[active_index + 1:end] if _kind(r) == 'C-Freq']
            if _already_present(native_channels, row):
                # Keep a source row for duplicate detection; merge will skip it.
                output.append(list(row))
                continue
            if len(row) <= 5 or not row[5].isascii() or not row[5].isdecimal():
                raise ValueError('Selected database channel has no valid native Hz frequency.')
            if any(len(r) > 5 and r[5] == row[5] for r in native_channels):
                raise ValueError('An existing channel in this department already uses that frequency. '
                                 'Review the channel before adding another record.')
            template = next((r for r in native_channels if len(r) == 18), None)
            if template is None:
                raise ValueError('This department has no native channel template. '
                                 'Adding its first channel is not supported by the current scanner export.')
            replacement = list(template)
            replacement[1] = 'CFreqId=0'
            replacement[3] = row[3]
            replacement[5] = row[5]
            # Identity of the radio channel comes from the database (real SDS100 database rows
            # carry modulation, tone/NAC/colour code and service type in columns 6-8); the
            # remaining settings follow the destination department's template. Two items
            # cannot share a number tag, and a copied Priority/Avoid would be surprising.
            # Database value when valid, otherwise blank (never another channel's value). The
            # format does not allow a blank modulation (AUTO is the neutral choice) or a blank
            # service type (the channel is refused rather than guessed).
            from new_favorites_list import AUDIO_OPTION, MODULATIONS, valid_func_tag
            modulation = row[6].strip() if len(row) > 6 else ''
            audio = row[7].strip() if len(row) > 7 else ''
            func = row[8].strip() if len(row) > 8 else ''
            replacement[6] = modulation if modulation.upper() in MODULATIONS else 'AUTO'
            replacement[7] = audio if AUDIO_OPTION.fullmatch(audio) else ''
            if not valid_func_tag(func):
                raise ValueError(f'Database channel {row[3]!r} has no valid service type; not added.')
            replacement[8] = func
            replacement[4], replacement[16], replacement[17] = 'Off', 'Off', 'Off'
            output.append(replacement)
        else:
            raise ValueError(f'Unsupported database record type {kind!r} for native channel addition.')
    return output


def merge_draft_entry(existing_entry, incoming_entry):
    """Merge into an existing system without changing its origin/identity."""
    merged, added = merge_records(existing_entry['records'], incoming_entry['records'])
    if added:
        existing_entry['records'] = merged
        for field in ('selected_sites', 'selected_departments'):
            names = existing_entry.get(field, [])
            for name in incoming_entry.get(field, []):
                if name not in names:
                    names.append(name)
            if names:
                existing_entry[field] = names
    return added
