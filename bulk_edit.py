# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Apply one setting to many selected channels or talkgroups (pure, works on draft record lists).

Only simple enumerated fields are offered; every value is checked against the same choices the
single-row editor uses.  Rows the field does not apply to are skipped and reported, never changed.
"""

AVOID_LABELS = {'Off': 'Off', 'Temporary': 'Temporary Avoid', 'On': 'Permanent Avoid'}

# name -> (record kinds, field index in the native record, allowed values)
FIELDS = {
    'Avoid': (('C-Freq', 'TGID'), 4, ('Off', 'Temporary', 'On')),
    'Attenuator': (('C-Freq',), 9, ('Off', 'On')),
    'Delay': (('C-Freq',), 10, ('30', '10', '5', '4', '3', '2', '1', '0', '-5', '-10')),
    'Volume Offset': (('C-Freq',), 11, ('-3', '-2', '-1', '0', '1', '2', '3')),
}


def field_names(kinds):
    """Fields that apply to at least one of the given record kinds."""
    kinds = set(kinds)
    return [name for name, (applies, _, _) in FIELDS.items() if kinds & set(applies)]


def label(field, value):
    return AVOID_LABELS.get(value, value) if field == 'Avoid' else value


def plan(records, targets, field, value):
    """Work out a bulk change without touching the records.

    targets: record indices.  Returns {'changes': [(index, name, old)], 'unchanged': n,
    'skipped': [(index, name, reason)]}.  Raises ValueError for an unknown field or value.
    """
    if field not in FIELDS:
        raise ValueError('Unknown field: %r' % (field,))
    kinds, position, allowed = FIELDS[field]
    if value not in allowed:
        raise ValueError('%s cannot be set to %r' % (field, value))
    result = {'changes': [], 'unchanged': 0, 'skipped': []}
    for index in sorted(set(targets)):
        if not 0 <= index < len(records):
            result['skipped'].append((index, '', 'no such record'))
            continue
        row = records[index]
        name = row[3] if len(row) > 3 else ''
        if not row or row[0] not in kinds:
            result['skipped'].append((index, name, '%s does not apply to %s records' % (
                field, row[0] if row else 'empty')))
        elif len(row) <= position:
            result['skipped'].append((index, name, 'record has no %s field' % field))
        elif row[position] == value:
            result['unchanged'] += 1
        else:
            result['changes'].append((index, name, row[position]))
    return result


def apply(records, changes, field, value):
    """Write a plan's changes into the records.  Returns how many fields changed."""
    _, position, allowed = FIELDS[field]
    if value not in allowed:
        raise ValueError('%s cannot be set to %r' % (field, value))
    for index, _, _ in changes:
        records[index][position] = value
    return len(changes)


def summary(field, value, result, limit=10):
    """Readable confirmation text."""
    changes, skipped = result['changes'], result['skipped']
    lines = ['Set %s to "%s" on %d item(s).' % (field, label(field, value), len(changes))]
    if result['unchanged']:
        lines.append('%d already have this value.' % result['unchanged'])
    if skipped:
        lines.append('%d skipped (%s).' % (len(skipped), skipped[0][2]))
    lines.append('')
    for index, name, old in changes[:limit]:
        lines.append('  %s: %s → %s' % (name or '(unnamed)', label(field, old), label(field, value)))
    if len(changes) > limit:
        lines.append('  … and %d more' % (len(changes) - limit))
    lines.append('')
    lines.append('This is one step; Undo restores every item at once.')
    return '\n'.join(lines)
