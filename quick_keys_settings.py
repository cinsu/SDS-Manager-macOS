# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Offline Favorites List quick-key status editing for native profile.cfg."""

def read_quick_keys(data):
    matches = [line for line in data.splitlines() if line.split(b'\t', 1)[0] == b'QuickKeys']
    if len(matches) != 1:
        raise ValueError('Expected exactly one QuickKeys record')
    fields = matches[0].decode('utf-8').split('\t')
    # Scanner samples have 100 statuses and may end with a trailing empty field.
    statuses = fields[1:101]
    if len(statuses) != 100 or any(value not in ('On', 'Off') for value in statuses):
        raise ValueError('Unexpected QuickKeys layout; refusing to edit')
    return [value == 'On' for value in statuses]


def patch_quick_keys(original, enabled):
    read_quick_keys(original)
    if len(enabled) != 100 or any(type(value) is not bool for value in enabled):
        raise ValueError('Expected 100 boolean quick-key statuses')
    result = []
    for line in original.splitlines(keepends=True):
        if line.split(b'\t', 1)[0] != b'QuickKeys':
            result.append(line)
            continue
        suffix = b'\r\n' if line.endswith(b'\r\n') else b'\n' if line.endswith(b'\n') else b''
        fields = line.rstrip(b'\r\n').split(b'\t')
        fields[1:101] = [b'On' if value else b'Off' for value in enabled]
        result.append(b'\t'.join(fields) + suffix)
    return b''.join(result)
