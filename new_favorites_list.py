# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Build the rows of a NEW native Favorites List from a database selection.

Layouts and defaults come from real SDS100 files (a Sentinel-written Favorites list and
the master HPDB) and Uniden's SDS Series File Specification V2.00:

* Favorites records keep MyId/ParentId blank.
* Database system / department / channel rows share the favorites column layout; the
  user-input columns are blank in the database and hold defaults in a favorites list.
* Every system header is followed by a DQKs_Status record (department quick-key status).
* Quick keys, number tags, Avoid and Priority start unassigned/Off, because two items
  cannot share a quick key or number tag.

Pure functions, no I/O.  Conventional and trunked systems (trunk layout verified against a
Sentinel-written Palmetto 800 list; Motorola/EDACS band types are copied from the database, unverified).
"""
import re

PREAMBLE = [['TargetModel', 'BCDx36HP'], ['FormatVersion', '1.00']]
SYSTEM_DEFAULTS = ['0', 'Off', 'Off', '400', 'Auto', '8']     # hold, analog/digital AGC, wait, mode, level
# C-Freq columns 9-17: Attenuator, Delay, Volume Offset, Alert Tone, Alert Volume,
# Alert Color, Alert Pattern, Number tag, Priority Channel (observed in every real channel row)
CHANNEL_DEFAULTS = ['Off', '2', '0', 'Off', 'Auto', 'Off', 'On', 'Off', 'Off']
MODULATIONS = ('AUTO', 'AM', 'NFM', 'FM')
GROUP_FILTERS = ('Global', 'Normal', 'Invert', 'Auto', 'Wide Normal', 'Wide Invert', 'Wide Auto', 'Off')
AUDIO_OPTION = re.compile(
    r'(TONE=(C\d+(\.\d)?|D\d{3}|CSrch|DSrch|NoTone)|NAC=([0-9A-Fa-f]{1,3}|Srch)|ColorCode=\d+|RAN=\d+|Area=\d+)?')


def _kind(row):
    return row[0].strip() if row else ''


def valid_func_tag(value):
    return value.isascii() and value.isdecimal() and (1 <= int(value) <= 37 or 208 <= int(value) <= 218)


def native_channel_fields(row):
    """Return (modulation, audio option, FuncTagId) from a database C-Freq row, validated.

    Used for new native channels so the database's real modulation, tone/NAC/colour code
    and service type are kept instead of a template channel's.
    """
    modulation = row[6].strip() if len(row) > 6 else ''
    audio = row[7].strip() if len(row) > 7 else ''
    func = row[8].strip() if len(row) > 8 else ''
    if modulation.upper() not in MODULATIONS:
        raise ValueError(f'Channel {row[3]!r} has no valid modulation in the database.')
    if not AUDIO_OPTION.fullmatch(audio):
        raise ValueError(f'Channel {row[3]!r} has an unrecognised audio option {audio!r}.')
    if not valid_func_tag(func):
        raise ValueError(f'Channel {row[3]!r} has no valid service type in the database.')
    return modulation, audio, func


TRUNK_TYPES = ('P25Standard', 'P25OneFrequency', 'Motorola', 'Edacs', 'Ltr', 'MotoTrbo', 'DmrOneFrequency', 'Nxdn')
TGID_FORMATS = ('NEXEDGE', 'IDAS')
AUDIO_TYPES = ('ALL', 'ANALOG', 'DIGITAL')
TDMA_SLOTS = ('Any', '1', '2')
# Band plan Sentinel writes for a P25 Standard site when the database holds none (identical on every
# site of the real Palmetto 800 list).
DEFAULT_P25_BANDPLAN = ['BandPlan_P25', '', '851006250', '6250', '762006250', '6250', '851012500', '12500', '762006250', '12500', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '3', '3', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0']


def _col(row, index):
    return row[index].strip() if len(row) > index else ''


def _name(row, what):
    name = _col(row, 3)
    if not name or len(name) > 64:
        raise ValueError(f'A selected {what} needs a name of 1–64 characters.')
    return name


def _location(row, what):
    """'Circle' or 'Rectangles' (the database leaves a circle's type blank only in odd rows)."""
    kind = _col(row, 8) if what in ('T-Group', 'C-Group') else _col(row, 11)
    if kind not in ('Circle', 'Rectangles', ''):
        raise ValueError(f'{what} {row[3]!r} uses location type {kind!r}; only Circle and Rectangles are supported.')
    return kind or 'Circle'


def _rectangle(row):
    """Native Rectangle row from a database Rectangle row (same layout: two corners, latitude then longitude)."""
    native = ['Rectangle', ''] + [_col(row, i) for i in range(2, 6)]
    from scanner_list_sync import rectangle_problem
    problem = rectangle_problem(native)
    if problem:
        raise ValueError('A selected location has a bad rectangle: ' + problem + '.')
    return native


def build_new_trunk_rows(candidate_records):
    """Rows for a new native list from [Trunk, Site, (BandPlan), T-Freq.., T-Group, TGID..]."""
    header = candidate_records[0]
    name = _name(header, 'system')
    system_type = _col(header, 6)
    if system_type not in TRUNK_TYPES:
        raise ValueError(f'System {name!r} has unsupported type {system_type!r}.')
    tgid_format = _col(header, 21)
    if system_type != 'Nxdn' or tgid_format not in TGID_FORMATS:
        tgid_format = 'IDAS'          # what Sentinel wrote for the real Palmetto 800 list; only NXDN uses it
    rows = [list(r) for r in PREAMBLE]
    header = ['Trunk', '', '', name, 'Off', '', system_type, 'Off', 'Off', 'Auto', 'Ignore', '', 'Off', 'Off',
              '0', 'Off', 'Off', 'Ignore', 'Off', 'Off', 'On', tgid_format]
    if system_type == 'MotoTrbo':
        # As in the Sentinel-written MotoTrbo list confirmed on a real SDS100 (v0.1.3).
        header[11], header[17], header[21] = 'Srch', 'Analog', 'NEXEDGE'
    rows.append(header)
    rows.append(['DQKs_Status', ''] + ['Off'] * 100 + [''])
    sites = departments = tgids = 0
    site = None            # [site_row, band_rows, freq_rows]
    blocks = []
    group = None
    seen_f = seen_t = set()
    owner = None           # (rows list, wants rectangles) of the latest Site / T-Group
    for row in candidate_records[1:]:
        kind = _kind(row)
        if kind == 'Site':
            site_location = _location(row, 'Site')
            mod = _col(row, 8)
            if mod not in ('AUTO', 'AM', 'NFM', 'FM'):
                mod = 'AUTO'
            native = ['Site', '', '', _name(row, 'site'), 'Off', _col(row, 5), _col(row, 6), _col(row, 7), mod,
                      '', '', site_location, 'Off', '400', 'Auto', '8', 'Off',
                      _col(row, 17) if system_type in ('P25Standard', 'P25OneFrequency') else '0',
                      _col(row, 18) if _col(row, 18) in GROUP_FILTERS else 'Global']
            if system_type in ('Motorola', 'Edacs'):
                native[9], native[10] = _col(row, 9), _col(row, 10)
            if system_type == 'MotoTrbo':          # the confirmed Sentinel-written MotoTrbo list (v0.1.3)
                native[9], native[10], native[17] = 'Standard', 'Wide', 'Srch'
            site = [native, [], [], []]            # row, band plans, frequencies, rectangles
            owner = (site[3], site_location == 'Rectangles')
            blocks.append(('Site', site))
            seen_f = set()
            group = None
        elif kind in ('BandPlan_P25', 'BandPlan_Mot'):
            if site is None:
                raise ValueError('Band plan row has no site.')
            site[1].append([kind, ''] + [c.strip() for c in row[2:]])
        elif kind == 'T-Freq':
            if site is None:
                raise ValueError('Selected frequency has no site.')
            f = _col(row, 5)
            if not f.isascii() or not f.isdecimal() or not 100000 <= int(f) <= 1300000000:
                raise ValueError(f'Site frequency {f!r} is not a valid frequency in Hz.')
            if f in seen_f:
                continue
            seen_f.add(f)
            lcn = '0' if system_type in ('P25Standard', 'P25OneFrequency', 'DmrOneFrequency') else _col(row, 6) or '0'
            if not lcn.isdecimal():
                raise ValueError(f'Site frequency {f} has an invalid channel number.')
            audio = _col(row, 7) or 'Srch'
            # DMR channels carry a bare colour code ('8'), P25 'Srch'/NAC=, NXDN 'RAN=n'; all kept as in the database
            if not (AUDIO_OPTION.fullmatch(audio) or audio == 'Srch' or (audio.isascii() and audio.isdecimal())):
                raise ValueError(f'Site frequency {f} has an unrecognised audio option {audio!r}.')
            freq_row = ['T-Freq', '', '', '', 'Off', f, lcn, audio, 'Any']
            if system_type in ('DmrOneFrequency', 'MotoTrbo'):
                freq_row = freq_row[:8]          # as in the DMR lists confirmed on a real SDS100 (v0.1.2, v0.1.3)
            site[2].append(freq_row)
        elif kind == 'Rectangle':
            if owner is None:
                raise ValueError('A rectangle row has no location.')
            if not owner[1]:
                raise ValueError('A rectangle row belongs to a location that is not a rectangle location.')
            owner[0].append(_rectangle(row))
        elif kind == 'T-Group':
            group_location = _location(row, 'T-Group')
            group = ['T-Group', '', '', _name(row, 'talkgroup department'), 'Off', _col(row, 5), _col(row, 6),
                     _col(row, 7), group_location, 'Off']
            blocks.append(('Group', [group, [], []]))          # row, talkgroups, rectangles
            owner = (blocks[-1][1][2], group_location == 'Rectangles')
            seen_t = set()
        elif kind == 'TGID':
            if group is None:
                raise ValueError('Selected talkgroup has no department.')
            tgid = _col(row, 5)
            if not tgid.isascii() or not tgid.isdecimal():
                raise ValueError(f'Talkgroup {_col(row, 3)!r} has no valid TGID.')
            audio = _col(row, 6)
            func = _col(row, 7)
            if audio not in AUDIO_TYPES:
                raise ValueError(f'Talkgroup {_col(row, 3)!r} has no valid audio type.')
            if not valid_func_tag(func):
                raise ValueError(f'Talkgroup {_col(row, 3)!r} has no valid service type in the database.')
            if tgid in seen_t:
                continue
            seen_t.add(tgid)
            slot = _col(row, 16) if _col(row, 16) in TDMA_SLOTS else 'Any'
            blocks[-1][1][1].append(['TGID', '', '', _name(row, 'talkgroup'), 'Off', tgid, audio, func,
                                     '2', '0', 'Off', 'Auto', 'Off', 'On', 'Off', 'Off', slot])
        elif kind:
            raise ValueError(f'Unsupported database record type {kind!r} for a new native list.')
    for what, block in blocks:
        if what == 'Site':
            if not block[2]:
                raise ValueError(f'Site {block[0][3]!r} has no frequencies selected.')
            if system_type == 'P25Standard' and not block[1]:
                block[1].append(list(DEFAULT_P25_BANDPLAN))
            if block[0][11] == 'Rectangles' and not block[3]:
                raise ValueError(f'Site {block[0][3]!r} is a rectangle site but has no rectangle.')
            # Sentinel order (real list): Site, band plan(s), Rectangle(s), frequencies
            rows.append(block[0]); rows.extend(block[1]); rows.extend(block[3]); rows.extend(block[2]); sites += 1
        elif block[1]:
            if block[0][8] == 'Rectangles' and not block[2]:
                raise ValueError(f'Department {block[0][3]!r} is a rectangle department but has no rectangle.')
            rows.append(block[0]); rows.extend(block[2]); rows.extend(block[1]); departments += 1; tgids += len(block[1])
    if sites == 0 or tgids == 0:
        raise ValueError('A trunked list needs at least one site with frequencies and one talkgroup. '
                         'A Favorites List is never created incomplete.')
    return rows, 'cp1252', '\r\n'


def build_new_list_rows(candidate_records):
    """Return (rows, encoding, newline) for a new list holding candidate_records.

    candidate_records: database rows [Conventional header, C-Group, C-Freq, ...] or
    [Trunk header, Site, BandPlan.., T-Freq.., T-Group, TGID..].
    """
    if candidate_records and _kind(candidate_records[0]) == 'Trunk':
        return build_new_trunk_rows(candidate_records)
    if not candidate_records or _kind(candidate_records[0]) != 'Conventional':
        raise ValueError('A new Favorites List can be created only from a conventional or trunked system.')
    header = candidate_records[0]
    system_name = header[3].strip() if len(header) > 3 else ''
    if not system_name or len(system_name) > 64:
        raise ValueError('The selected system needs a name of 1–64 characters.')
    rows = [list(r) for r in PREAMBLE]
    rows.append(['Conventional', '', '', system_name, 'Off', '', 'Conventional', 'Off', 'Off'] + SYSTEM_DEFAULTS)
    rows.append(['DQKs_Status', ''] + ['Off'] * 100 + [''])
    group = None
    channels = 0
    seen = set()
    departments_found = []
    owner = None
    for row in candidate_records[1:]:
        kind = _kind(row)
        if kind == 'C-Group':
            name = row[3].strip() if len(row) > 3 else ''
            if not name or len(name) > 64:
                raise ValueError('A selected department needs a name of 1–64 characters.')
            location = list(row[5:9]) + [''] * (4 - len(row[5:9]))
            location[3] = _location(row, 'C-Group')
            owner = (None, location[3] == 'Rectangles')
            filter_value = row[10] if len(row) > 10 and row[10] in GROUP_FILTERS else 'Global'
            group = ['C-Group', '', '', name, 'Off'] + location + ['Off', filter_value]
            departments_found.append([group, [], []])           # row, rectangles, channels
            seen = set()
        elif kind == 'Rectangle':
            if group is None or not owner[1]:
                raise ValueError('A rectangle row belongs to a location that is not a rectangle location.')
            departments_found[-1][1].append(_rectangle(row))
        elif kind == 'C-Freq':
            if group is None:
                raise ValueError('Selected channel has no department.')
            if len(row) <= 5 or not row[5].isascii() or not row[5].isdecimal() \
                    or not 100000 <= int(row[5]) <= 1300000000:
                raise ValueError(f'Channel {row[3] if len(row) > 3 else ""!r} has no valid frequency in Hz.')
            name = row[3].strip()
            if not name or len(name) > 64:
                raise ValueError('A selected channel needs a name of 1–64 characters.')
            if (name, row[5]) in seen:
                continue
            seen.add((name, row[5]))
            modulation, audio, func = native_channel_fields(row)
            departments_found[-1][2].append(['C-Freq', '', '', name, 'Off', row[5], modulation, audio, func] + CHANNEL_DEFAULTS)
            channels += 1
        elif kind:
            raise ValueError(f'Unsupported database record type {kind!r} for a new native list.')
    if channels == 0:
        raise ValueError('No channels selected. A Favorites List is never created empty.')
    # Drop departments that ended up with no channel (e.g. all duplicates).
    for dept in departments_found:
        if not dept[2]:
            continue                      # a department whose channels were all duplicates is dropped
        if dept[0][8] == 'Rectangles' and not dept[1]:
            raise ValueError(f'Department {dept[0][3]!r} is a rectangle department but has no rectangle.')
        rows.append(dept[0]); rows.extend(dept[1]); rows.extend(dept[2])
    return rows, 'cp1252', '\r\n'
