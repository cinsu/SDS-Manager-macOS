# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Systems, departments, channels and talkgroups typed in by hand (v0.1.7).

New rows are made by the same builder that makes new Favorites Lists from the database
(new_favorites_list), so they have the layout the SDS100 accepts (confirmed on a real scanner) and the
scanner's default settings. Talkgroups copy the layout of a talkgroup already in the same system, because
it differs between trunk types (P25, DMR, NXDN ...). Pure functions, no Qt.
"""
import re
from decimal import Decimal, InvalidOperation

import new_favorites_list as nfl
import rr_convert as rc

MODULATIONS = ('AUTO', 'FM', 'NFM', 'AM')


class EntryError(ValueError):
    """The typed value can't be used; the text says why."""


def name(text, what):
    value = re.sub(r'\s+', ' ', str(text or '')).strip()
    if not value:
        raise EntryError(f'Enter a name for the {what}.')
    if len(value) > 64:
        raise EntryError(f'The {what} name can be at most 64 characters.')
    try:
        value.encode('cp1252')
    except UnicodeError:
        raise EntryError(f'The {what} name uses characters the scanner can\'t show.') from None
    return value


def frequency_hz(text):
    """Hertz text from MHz typed by the user (25–1300 MHz, up to 6 decimals)."""
    try:
        mhz = Decimal(str(text).strip().lower().replace('mhz', '').strip())
    except InvalidOperation:
        raise EntryError('Enter the frequency in MHz, for example 155.250.') from None
    if mhz != mhz.quantize(Decimal('0.000001')) or not Decimal(25) <= mhz <= Decimal(1300):
        raise EntryError('The frequency must be between 25 and 1300 MHz, with at most six decimals.')
    return str(int(mhz * 1_000_000))


def tone_option(text):
    """'' or a Uniden audio option from what was typed: 107.2, 023 DPL, NAC 293, CC1, RAN 4 ..."""
    if not str(text or '').strip():
        return ''
    value = rc.audio_option(text)
    if not value or not nfl.AUDIO_OPTION.fullmatch(value):
        raise EntryError('Tone not understood. Examples: 107.2 (CTCSS), 023 DPL, NAC 293, CC 1, RAN 4.')
    return value


def talkgroup_id(text):
    value = str(text or '').strip()
    if not re.fullmatch(r'\d{1,8}', value):
        raise EntryError('Enter the talkgroup ID as a number (decimal).')
    return str(int(value))


def _records(system, department, channels):
    """Database-layout records for a conventional system with one department."""
    records = [['Conventional', '', '', system, 'Off', '', 'Conventional'] + [''] * 8,
               ['C-Group', '', '', department, 'Off', '0.000000', '0.000000', '0.0', 'Circle', 'Off', 'Global']]
    for channel in channels:
        records.append(['C-Freq', '', '', channel['name'], 'Off', channel['hz'], channel['modulation'],
                        channel['tone'], channel.get('service', rc.OTHER)] + [''] * 9)
    return records


def channel(channel_name, mhz, modulation='AUTO', tone=''):
    if modulation not in MODULATIONS:
        raise EntryError('Choose AUTO, FM, NFM or AM.')
    return {'name': name(channel_name, 'channel'), 'hz': frequency_hz(mhz), 'modulation': modulation,
            'tone': tone_option(tone)}


def new_list_records(system, department, channels):
    """Records for a new Favorites List (through the same path as a database selection)."""
    if not channels:
        raise EntryError('Add at least one channel.')
    return _records(name(system, 'system'), name(department, 'department'), channels)


def native_rows(records):
    rows, _encoding, _newline = nfl.build_new_list_rows(records)
    return rows[2:]                                   # without TargetModel / FormatVersion


def conventional_system_rows(system, department, channels):
    """Rows of a new conventional system for an existing Favorites List."""
    return native_rows(new_list_records(system, department, channels))


def channel_row(item):
    """A native C-Freq row with the scanner's defaults."""
    rows = native_rows(_records('x', 'x', [item]))
    return next(r for r in rows if r[0] == 'C-Freq')


def conventional_department_rows(department, channels, like=None):
    """A native C-Group row and its channels; location copied from like (another department) if given."""
    rows = native_rows(_records('x', name(department, 'department'), channels))
    group = next(r for r in rows if r[0] == 'C-Group')
    if like is not None and len(like) >= 8:
        group[5:8] = like[5:8]
    return [group] + [r for r in rows if r[0] == 'C-Freq']


def talkgroup_row(template, tg_name, value, service=rc.OTHER):
    """A TGID row made from another talkgroup of the same system, with default settings."""
    if template is None or template[0] != 'TGID' or len(template) < 17:
        raise EntryError('Talkgroups can be added by hand to a system that already has one talkgroup '
                         '(its layout depends on the trunk type).')
    row = list(template)
    row[1], row[2] = '', ''
    row[3], row[4], row[5] = name(tg_name, 'talkgroup'), 'Off', talkgroup_id(value)
    defaults = {6: 'ALL', 7: service, 8: '2', 9: '0', 10: 'Off', 11: 'Auto', 12: 'Off', 13: 'On',
                14: 'Off', 15: 'Off', 16: 'Any'}
    for i, v in defaults.items():
        if i < len(row):
            row[i] = v
    return row


def talkgroup_department_rows(department, talkgroups, like=None):
    """A native T-Group row (location from like if given) and its talkgroups."""
    if not talkgroups:
        raise EntryError('Add at least one talkgroup.')
    group = ['T-Group', '', '', name(department, 'department'), 'Off', '0.000000', '0.000000', '0.0',
             'Circle', 'Off']
    if like is not None and len(like) >= 8:
        group[5:8] = like[5:8]
    return [group] + list(talkgroups)
