# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Spec-driven, lossless editing and validation of simple profile.cfg records.

Positions are one-based and exclude the record keyword, as in Uniden's SDS Series File
Specification V2.00.  Where a real SDS100 profile.cfg differs from the specification (an extra
GlobalSetting field 21, "Audio Off Time" text values) the real file wins; reserved positions are
preserved exactly and can never be edited.

Only records listed in SCHEMA are covered.  Every other byte of the file must stay identical.
"""
import re

ONOFF = ('Off', 'On')
DELAYS = ('30', '10', '5', '4', '3', '2', '1', '0', '-5', '-10')
MODULATIONS = ('AUTO', 'AM', 'NFM', 'FM', 'WFM', 'FMB')
FILTERS = ('Global', 'Normal', 'Invert', 'Auto', 'Wide Normal', 'Wide Invert', 'Wide Auto', 'Off')
SEARCH_KEYS = ('Off',) + tuple('Custom%d' % i for i in range(10)) + ('ToneOut', 'CloseCall', 'Waterfall')
ALERT_COLORS = ('Off', 'Blue', 'Red', 'Magenta', 'Green', 'Cyan', 'Yellow', 'White')
_INT = re.compile(r'0|[1-9][0-9]*')
_FIPS = re.compile(r'[0-9]{6}|-{6}')
_HEX6 = re.compile(r'[0-9a-f]{6}')


class Field:
    """kind: 'choice' | 'int' | 'text' | 'fips' | 'fixed'."""

    def __init__(self, label, kind='fixed', values=(), low=0, high=0, maxlen=0, allow_empty=False, free=False,
                 zero_ok=False):
        self.label, self.kind, self.values = label, kind, tuple(values)
        self.low, self.high, self.maxlen = low, high, maxlen
        self.allow_empty, self.free = allow_empty, free     # free: spaces at either end are allowed
        self.zero_ok = zero_ok                              # int: 0 is also accepted below `low`

    @property
    def editable(self):
        return self.kind != 'fixed'

    def choices(self):
        if self.kind == 'choice':
            return self.values
        if self.kind == 'int':
            return tuple(str(i) for i in range(self.low, self.high + 1))
        return None

    def valid(self, value):
        if not isinstance(value, str) or not value.isascii() or any(c in value for c in '\t\r\n\x00'):
            return False
        if self.kind == 'choice':
            return value in self.values
        if self.kind == 'int':
            return bool(_INT.fullmatch(value)) and (self.low <= int(value) <= self.high or
                                                    (self.zero_ok and value == '0'))
        if self.kind == 'freq':       # Hz, canonical integer, inside the scanner's overall range
            return bool(_INT.fullmatch(value)) and 25_000_000 <= int(value) <= 1_300_000_000
        if self.kind == 'color':      # six lowercase hex digits, as the scanner writes them
            return bool(_HEX6.fullmatch(value))
        if self.kind == 'mhz':        # broadcast screen band edge: MHz, zero-padded to three digits
            return bool(re.fullmatch(r'[0-9]{3,4}', value)) and int(value) <= 1300 and value == '%03d' % int(value)
        if self.kind == 'text':
            if not all(' ' <= c <= '~' for c in value) or len(value) > self.maxlen:
                return False
            if not value.strip():
                return self.allow_empty and value == ''
            return self.free or value == value.strip()
        if self.kind == 'fips':
            return bool(_FIPS.fullmatch(value))
        return False


def C(label, values):
    return Field(label, 'choice', values)


def I(label, low, high):
    return Field(label, 'int', low=low, high=high)


def R(label='Reserved'):
    return Field(label)


def F(label):
    return Field(label, 'freq')


def T(label, maxlen=16, allow_empty=False):
    return Field(label, 'text', maxlen=maxlen, allow_empty=allow_empty)


def ID(label='ID'):
    return Field(label)


STEPS = ('Auto', '5000', '6250', '7500', '8333', '10000', '12500', '15000', '20000', '25000', '50000', '100000')
WF_STEPS = ('Auto', '5000', '6250', '8333', '10000', '12500', '20000', '25000', '50000', '100000')
WF_SPANS = ('0.36', '0.72', '1.44', '2.88', '5.76', '8.64', '17.28')
TONE_DELAYS = ('0', '1', '2', '3', '4', '5', '10', '30', 'Infinite')
ALERT_TYPES = ('Off',) + tuple(str(i) for i in range(1, 10))
ALERT_VOLUMES = ('Auto',) + tuple(str(i) for i in range(1, 16))
PATTERNS = ('On', 'Slow Blink', 'Fast Blink')


def _limit_search_check(row):
    if int(row[2]) > int(row[3]):
        return 'lower frequency is above the upper frequency'
    return None


# Volume and squelch use the handheld (SDS100) ranges 0-15.
SCHEMA = {
    'GlobalSetting': {'rows': 1, 'fields': [
        C('Scan Full Database', ONOFF), C('Global Attenuator', ONOFF), R(),
        C('Priority Scan Mode', ('Off', 'DND', 'Priority')),
        C('Close Call Mode', ('Off', 'DND', 'Priority')),
        C('Weather Priority', ('Off', 'Priority')),
        I('Priority Interval (seconds)', 1, 10), I('Priority Maximum Channels', 1, 100),
        C('Search Key 1', SEARCH_KEYS), C('Search Key 2', SEARCH_KEYS), C('Search Key 3', SEARCH_KEYS),
        C('Key Lock', ONOFF), C('Key Beep Volume', ('Off',) + tuple(str(i) for i in range(1, 16)) + ('Auto',)),
        I('Volume', 0, 15), I('Squelch', 0, 15),
        C('Search with Scan List', ONOFF), C('Search with Scan System Avoid', ONOFF),
        C('Site NAC Operation', ('Ignore', 'Compare')),
        C('Global Auto Filter', FILTERS[1:]),
        C('Audio Off Time (ms, 0 = never)', ('0', '100', '500', '1000', '2000', '3000', '4000', '5000',
                                              '10000', '30000')),
        C('Headphone Audio Output Phase', ('In Phase', 'Invert Phase'))]},
    'SearchCommon': {'rows': 1, 'fields': [
        R(), C('Repeater Find', ONOFF), C('Attenuator', ONOFF), C('Delay (seconds)', DELAYS),
        C('Modulation', MODULATIONS), C('Analog AGC', ONOFF), C('Digital AGC', ONOFF),
        I('Digital Waiting Time (ms)', 0, 1000), C('Digital Threshold Mode', ('Auto', 'Manual', 'Default')),
        I('Digital Threshold Level', 5, 13), C('Filter', FILTERS)]},
    'CloseCall': {'rows': 1, 'fields': [
        R(), R(), C('Avoid (search with scan)', ONOFF),
        C('Pause Time (seconds)', ('3', '5', '10', '15', '30', '45', '60', 'Infinite')),
        C('Alert Type', ('Off',) + tuple(str(i) for i in range(1, 10))),
        C('Alert Volume', ('Auto',) + tuple(str(i) for i in range(1, 16))),
        C('Alert Color', ALERT_COLORS), C('Alert Pattern', ('On', 'Slow Blink', 'Fast Blink')),
        C('Band VHF Low 1', ONOFF), C('Band VHF Low 2', ONOFF), C('Band Air', ONOFF),
        C('Band VHF High 1', ONOFF), C('Band VHF High 2', ONOFF), C('Band UHF', ONOFF),
        C('Band 800 MHz', ONOFF), R(), R(), I('Hold Time (search with scan)', 0, 255)]},
    'Weather': {'rows': 1, 'fields': [
        R(), C('Delay (seconds)', DELAYS), C('Attenuator', ONOFF), C('Analog AGC', ONOFF)]},
    # --- display and hardware (SDS100 layouts; positions the specification calls reserved stay read-only) ---
    # A real SDS100 DisplayOption has 13 fields (the specification lists 14): the three trailing fields
    # sit one position earlier than the specification's numbering.
    'DisplayOption': {'rows': 1, 'fields': [
        R(), R(), R(), R(), R(), C('Motorola TGID Format', ('DEC', 'HEX')), R(), R(), R(), R(),
        C('Simple Mode (3-line)', ONOFF), C('EDACS TGID Format', ('AFS', 'DEC')),
        C('Colour Mode', ('COLOR', 'BLACK', 'WHITE'))]},
    # A real SDS100 Backlight record has 11 fields; spec positions 12-18 are SDS200-only and absent.
    'Backlight': {'rows': 1, 'fields': [
        R(), R(), R(), R(), R(), C('Brightness (%)', tuple(str(i) for i in range(10, 101, 10))),
        C('Key Backlight', ONOFF), C('Flash LED', ONOFF), C('External Power Light', ONOFF),
        C('Squelch Light (seconds)', ('Off', '5', '10', '15', 'OpenSquelch')),
        C('Key Light (seconds)', ('15', '30', '60', '120', 'Infinite'))]},
    'Battery': {'rows': 1, 'fields': [
        C('Battery Save', ONOFF), R(), R(), I('Alert Interval (minutes)', 1, 60),
        C('Alert Tone (Hz)', ('640', '780', '920', '1060', '1200')),
        C('Alert Volume', ('Off',) + tuple(str(i) for i in range(1, 16)) + ('Auto',))]},
    'OwnerInfo': {'rows': 1, 'fields': [
        Field('Message line %d' % i, 'text', maxlen=24, allow_empty=True, free=True) for i in range(1, 5)]},
    # Position 1 is "reserved" in the specification but holds the 12/24-hour setting on a real SDS100
    # (only '24H' seen), so it is shown read-only until a '12H' capture confirms the spelling.
    'ClockOption': {'rows': 1, 'fields': [
        R('Hour format (read-only)'), C('Time Zone (hours from UTC)', tuple('%.1f' % (i / 2) for i in range(-28, 29))),
        C('Daylight Saving', ONOFF)]},
    'RecordingOption': {'rows': 1, 'fields': [
        C('Replay Duration (seconds, 0 = off)', ('0',) + tuple(str(i) for i in range(30, 241, 30))),
        C('User Recording', ONOFF)]},
    'StandbyOption': {'rows': 1, 'fields': [R('Standby mode (not in specification)'), R('Standby option (not in specification)')]},
    # --- searches and tools ---
    'LimitSearch': {'rows': 10, 'rowcheck': _limit_search_check, 'fields': [
        ID('Search ID'), T('Name'), F('Lower Frequency (Hz)'), F('Upper Frequency (Hz)'),
        C('Modulation', MODULATIONS), C('Step (Hz)', STEPS), C('Delay (seconds)', DELAYS),
        C('Attenuator', ONOFF), C('Bank Status', ONOFF), C('Avoid', ONOFF), R(), R(), R(), R(),
        I('Hold Time', 0, 255), C('Analog AGC', ONOFF), C('Digital AGC', ONOFF),
        I('Digital Waiting Time (ms)', 0, 1000), C('Digital Threshold Mode', ('Auto', 'Manual', 'Default')),
        I('Digital Threshold Level', 5, 13)]},
    'ToneOut': {'rows': 32, 'fields': [
        ID('Tone-Out ID'), T('Name'), R(), F('Frequency (Hz)'), C('Modulation', ('AUTO', 'NFM', 'FM')),
        Field('Tone A (0.1 Hz)', 'int', low=2500, high=35000, zero_ok=True),
        Field('Tone B (0.1 Hz)', 'int', low=2500, high=35000, zero_ok=True),
        C('Attenuator', ONOFF), C('Delay (seconds)', TONE_DELAYS), C('Analog AGC', ONOFF),
        C('Alert Type', ALERT_TYPES), C('Alert Volume', ALERT_VOLUMES), C('Alert Color', ALERT_COLORS),
        C('Alert Pattern', PATTERNS)]},
    'Waterfall': {'rows': 1, 'fields': [
        R(), T('Name', allow_empty=True), F('Center Frequency (Hz)'), R(), C('Modulation', MODULATIONS),
        C('Step (Hz)', WF_STEPS), C('Span (MHz)', WF_SPANS), R(), R(), R(), R(), R(),
        C('FFT Graph', ('Line', 'Bar')), C('FFT Display (%)', ('25', '50', '75', '100')),
        C('Max Hold', ONOFF), C('Max Hold Time (seconds)', ('3', '10', 'Infinite')),
        C('Marker Position', ('Shift', 'Fixed')), C('RF Gain', ('Auto',) + tuple(str(i) for i in range(16))),
        C('Marker Width', ('Narrow', 'Normal', 'Wide')), C('First Message', ONOFF)]},
    # A real SDS100 CustomWfBand row has 9 fields (the specification lists 7); the last two are empty.
    'CustomWfBand': {'rows': 10, 'fields': [
        ID('Band ID'), T('Name'), F('Center Frequency (Hz)'), R(), C('Modulation', MODULATIONS),
        C('Step (Hz)', WF_STEPS), C('Span (MHz)', WF_SPANS), R(), R()]},
    'WfColors': {'rows': 1, 'fields': [Field('Colour %s' % n, 'color') for n in
                                       ('Level 1', 'Level 2', 'Level 3', 'Level 4', 'Level 5', 'Marker')]},
    'BandDefault': {'rows': 31, 'fields': [
        ID('Band ID'), C('Modulation', ('AM', 'NFM', 'FM', 'WFM', 'FMB')), C('Step (Hz)', STEPS[1:])]},
    'PresetBroadcastScreen': {'rows': 1, 'fields': [
        C('Pager', ONOFF), C('FM Broadcast', ONOFF), C('UHF TV', ONOFF), C('VHF TV', ONOFF), C('NOAA Weather', ONOFF)]},
    'CustomBroadcastScreen': {'rows': 1, 'fields': sum((
        [C('Band %d Enable' % n, ONOFF), Field('Band %d Lower (MHz)' % n, 'mhz'),
         Field('Band %d Upper (MHz)' % n, 'mhz')] for n in range(10)), [])},
    'WxSameList': {'rows': 5, 'fields': [R('Same ID')] + [Field('Group Name', 'text', maxlen=16)]
                   + [Field('FIPS %d' % i, 'fips') for i in range(8)]},
}


# Display layouts: DispOptItems lists the items shown in one screen row; DispColors lists colour pairs.
# Item names are the ones a real SDS100 profile.cfg uses for that row; nothing else is accepted.
# Record lengths never change (the scanner decides how many items a row holds).
DISP_ITEMS = {
    '1': ('FL_Name', 'Empty', 'Frequency', 'SiteName', 'TGID'),
    '2': ('ServiceType', 'Rssi', 'CTCSS/DCS', 'SystemId', 'TGID', 'SysSubID', 'SiteId', 'WACN', 'BattVoltage',
          'UnitId', 'Volume&Squelch', 'NumberTag', 'Frequency', 'Rssi Bar', 'Empty'),
    '3': ('ATT', 'Empty', 'Day', 'Time', 'Volume', 'Squelch', 'P25Status', 'TdmaSlot'),
    '4': ('Modulation', 'P_Ch', 'IFX', 'LVL', 'Empty', 'REC', 'GPS', 'PRI', 'CC', 'WxPRI', 'SCR', 'REP'),
}
_DISP_ID = re.compile(r'DispOptId=([1-4])')
_DISP_LAYOUT = re.compile(r'DispLayoutId=([1-9][0-9]?)')
_COLOR_ID = re.compile(r'DispColorId=([1-9])')
_COLOR_LAYOUT = re.compile(r'ColorLayoutId=([1-9][0-9]?)')


def _disp_items_fields(row):
    if len(row) < 3 or len(row) > 14 or not _DISP_ID.fullmatch(row[0]) or not _DISP_LAYOUT.fullmatch(row[1]):
        raise ValueError('unexpected display item record layout')
    allowed = DISP_ITEMS[_DISP_ID.fullmatch(row[0]).group(1)]
    return [ID('Item row'), ID('Layout')] + [C('Item %d' % (n + 1), allowed) for n in range(len(row) - 2)]


def _disp_items_check(row):
    named = [item for item in row[2:] if item != 'Empty']
    if len(set(named)) != len(named):
        return 'an item is shown twice in one row'
    return None


def _disp_colors_fields(row):
    rest = len(row) - 2
    if rest < 2 or rest > 24 or rest % 2 or not _COLOR_ID.fullmatch(row[0]) or not _COLOR_LAYOUT.fullmatch(row[1]):
        raise ValueError('unexpected display colour record layout')
    return [ID('Colour set'), ID('Layout')] + [
        Field('Colour %d %s' % (n // 2 + 1, ('(first)', '(second)')[n % 2]), 'color') for n in range(rest)]


VARIABLE = {
    'DispOptItems': {'rows': None, 'fields_for': _disp_items_fields, 'rowcheck': _disp_items_check},
    'DispColors': {'rows': None, 'fields_for': _disp_colors_fields},
}
SCHEMA.update(VARIABLE)


def fields_of(kind, row):
    """Field definitions for one row; raises ValueError if the row does not fit the known layout."""
    spec = SCHEMA[kind]
    return spec['fields_for'](row) if 'fields_for' in spec else spec['fields']


def _lines(data):
    if not isinstance(data, bytes) or b'\x00' in data:
        raise ValueError('Unsupported profile data')
    return data.splitlines(keepends=True)


def _split(line):
    ending = b'\r\n' if line.endswith(b'\r\n') else (b'\n' if line.endswith(b'\n') else (b'\r' if line.endswith(b'\r') else b''))
    body = line[:-len(ending)] if ending else line
    return body.split(b'\t'), ending


def read_section(data, kind):
    """List of rows (tuples of field strings, keyword excluded) for one record kind."""
    rows = []
    for line in _lines(data):
        fields, _ = _split(line)
        if fields[0] == kind.encode('ascii'):
            rows.append(tuple(f.decode('cp1252') for f in fields[1:]))
    return rows


def check_layout(data, kind):
    spec = SCHEMA[kind]
    rows = read_section(data, kind)
    if 'fields_for' in spec:
        if not rows:
            raise ValueError('%s: no records found' % kind)
        for row in rows:
            fields_of(kind, row)
        return rows
    if len(rows) != spec['rows']:
        raise ValueError('%s: expected %d record(s), found %d' % (kind, spec['rows'], len(rows)))
    count = len(spec['fields'])
    for row in rows:
        # A real SDS100 GlobalSetting has one more field than the specification lists; accept only the
        # documented length and trust nothing beyond it.
        if len(row) != count:
            raise ValueError('%s: expected %d fields, found %d' % (kind, count, len(row)))
    return rows


def patch_fields(data, edits):
    """edits: {(kind, row_index, position): value}.  Returns new bytes; raises ValueError on any problem."""
    if not edits:
        raise ValueError('No edits')
    for kind, row, position in edits:
        if kind not in SCHEMA:
            raise ValueError('Unsupported record %r' % (kind,))
        rows = check_layout(data, kind)
        if type(row) is not int or type(position) is not int or not 0 <= row < len(rows) \
                or not 1 <= position <= len(fields_of(kind, rows[row])):
            raise ValueError('%s: position out of range' % kind)
        field = fields_of(kind, rows[row])[position - 1]
        if not field.editable:
            raise ValueError('%s field %d (%s) is not editable' % (kind, position, field.label))
        if not field.valid(edits[(kind, row, position)]):
            raise ValueError('%s field %d (%s): invalid value %r' % (kind, position, field.label,
                                                                     edits[(kind, row, position)]))
    seen = {}
    out = []
    for line in _lines(data):
        fields, ending = _split(line)
        kind = fields[0].decode('cp1252')
        if kind in SCHEMA:
            row = seen.get(kind, 0)
            seen[kind] = row + 1
            for (k, r, position), value in edits.items():
                if k == kind and r == row:
                    fields[position] = value.encode('ascii')
            line = b'\t'.join(fields) + ending
        out.append(line)
    result = b''.join(out)
    for kind, row, position in edits:
        if read_section(result, kind)[row][position - 1] != edits[(kind, row, position)]:
            raise ValueError('Round-trip verification failed')
    for kind in {k for k, _, _ in edits}:
        if len(check_layout(result, kind)) != len(check_layout(data, kind)):
            raise ValueError('%s: record count changed' % kind)
    for kind, row in {(k, r) for k, r, _ in edits}:
        check = SCHEMA[kind].get('rowcheck')
        problem = check(read_section(result, kind)[row]) if check else None
        if problem:
            raise ValueError('%s #%d: %s' % (kind, row + 1, problem))
    return result


def diff_sections(original, proposed):
    """Edits that turn original into proposed, restricted to SCHEMA records.

    Raises ValueError if a covered record changes shape or a non-editable field changes; the caller
    still has to prove that nothing outside these records changed.
    """
    edits = {}
    for kind, spec in SCHEMA.items():
        before = read_section(original, kind)
        after = read_section(proposed, kind)
        if before == after:
            continue                 # untouched records are never judged, whatever their layout
        before = check_layout(original, kind)
        after = check_layout(proposed, kind)
        if len(before) != len(after):
            raise ValueError('%s: record count changed' % kind)
        for r, (old_row, new_row) in enumerate(zip(before, after)):
            if len(old_row) != len(new_row):
                raise ValueError('%s #%d: record length changed' % (kind, r + 1))
            for index, (old, new) in enumerate(zip(old_row, new_row)):
                if old != new:
                    edits[(kind, r, index + 1)] = new
    return edits


def describe(original, edits):
    lines = []
    for (kind, row, position), value in sorted(edits.items()):
        old_row = read_section(original, kind)[row]
        field = fields_of(kind, old_row)[position - 1]
        old = old_row[position - 1]
        where = kind if SCHEMA[kind]['rows'] == 1 else '%s #%d (%s, %s)' % (kind, row + 1, old_row[0], old_row[1]) \
            if 'fields_for' in SCHEMA[kind] else '%s #%d' % (kind, row + 1)
        lines.append('%s — %s: %r → %r' % (where, field.label, old, value))
    return tuple(lines)
