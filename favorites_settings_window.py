# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Dedicated offline Favorites List settings editor; main browser remains compact."""
from decimal import Decimal, InvalidOperation
import re
from PyQt6.QtCore import Qt, QSettings, QRegularExpression
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSplitter,
    QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem,
    QDialogButtonBox, QMessageBox, QSizePolicy, QComboBox, QPushButton, QHeaderView,
    QCheckBox, QGroupBox, QRadioButton, QGridLayout, QFormLayout, QLineEdit, QMenu, QInputDialog, QAbstractItemView)
from PyQt6.QtGui import QRegularExpressionValidator, QShortcut, QKeySequence
from database_workspace import favorites_record_columns

import bulk_edit
import favorites_clipboard as clipboard
import hand_entry
import monitor_activity
import unit_aliases
from keys_model import badge
from hand_entry_dialog import HandEntryDialog

ROLE = Qt.ItemDataRole.UserRole
COLUMNS = ['Channel Name', 'Type', 'Frequency (MHz)', 'TGID', 'Modulation',
           'Service Type', 'Avoid', 'Audio Option', 'Attenuator', 'Delay',
           'Alert Tone', 'Alert Volume', 'Alert Color', 'Alert Pattern', 'Volume Offset', 'Number Tag', 'Priority', 'TDMA Slot',
           'Heard (90 days)', 'Last Heard']
HEARD_COLUMN, LAST_HEARD_COLUMN = 18, 19        # from SDS100 Monitor's history (v0.1.19), read-only

# Native TGID records have their own field order (SDS Series File Specification
# v2.00, [TGID]). Do NOT reuse C-Freq offsets for talkgroups.
TGID_VISIBLE_NATIVE = {
    5: 7,    # Service Type: FuncTagId
    7: 6,    # Audio Type (ALL / ANALOG / DIGITAL), NOT C-Freq Audio Option
    9: 8,    # Delay
    10: 10,  # Alert Tone
    11: 11,  # Alert Volume
    12: 12,  # Alert Color
    13: 13,  # Alert Pattern
    14: 9,   # Volume Offset
    15: 14,  # Number Tag
    16: 15,  # Priority Channel
    17: 16,  # TDMA Slot
}
TGID_AUDIO_TYPE_CHOICES = ('ALL', 'ANALOG', 'DIGITAL')
TGID_TDMA_SLOT_CHOICES = ('Any', '1', '2')
# Trunked alert settings use their own native TGID field offsets.
TGID_EDIT_CHOICES = {
    10: ('Off', '1', '2', '3', '4', '5', '6', '7', '8', '9'),  # native TGID Alert Tone
    11: ('Auto',) + tuple(str(i) for i in range(1, 16)),
    12: ('Off', 'Blue', 'Red', 'Magenta', 'Green', 'Cyan', 'Yellow', 'White'),
    13: ('On', 'Slow Blink', 'Fast Blink'),
    15: ('Off',) + tuple(str(i) for i in range(1000)),
    5: None,  # FuncTagId: dynamically populated with SERVICE_TYPE_NAMES
    7: TGID_AUDIO_TYPE_CHOICES,
    9: ('30', '10', '5', '4', '3', '2', '1', '0', '-5', '-10'),
    14: ('-3', '-2', '-1', '0', '1', '2', '3'),
    16: ('Off', 'On'),
    17: TGID_TDMA_SLOT_CHOICES,
}
TGID_FIELD_LABELS = {
    10: 'Alert Tone', 11: 'Alert Volume', 12: 'Alert Color',
    13: 'Alert Pattern', 15: 'Number Tag',
    5: 'Service Type', 7: 'Audio Type', 9: 'Delay',
    14: 'Volume Offset', 16: 'Priority', 17: 'TDMA Slot',
}

def tgid_display_value(column, native):
    if column == 5:
        return service_label(native)
    if column == 7 and native == 'ALL':
        return 'All'
    return native

# Native BCDx36HP C-Freq modulation is field 6 (zero-based).
# Preserve unrecognized native values rather than silently rewriting them.
MODULATION_CHOICES = ('Auto', 'AM', 'FM', 'NFM', 'WFM', 'FMB')
# Native Avoid field index 4. Off is confirmed in imported HPD samples.
# Preserve any other native value; never translate an unknown value implicitly.
AVOID_CHOICES = ('Off', 'Temporary', 'On')
AVOID_LABELS = {'Off': 'Off', 'Temporary': 'Temporary Avoid', 'On': 'Permanent Avoid'}
# Native conventional C-Freq attenuator: index 9 (after service type at 8).
ATTENUATOR_CHOICES = ('Off', 'On')
# Native C-Freq field 10: seconds; negative values are resume delays.
DELAY_CHOICES = ('30', '10', '5', '4', '3', '2', '1', '0', '-5', '-10')
# Native C-Freq field 11: volume offset from -3 to +3.
VOLUME_OFFSET_CHOICES = ('-3', '-2', '-1', '0', '1', '2', '3')
# Native C-Freq field index 17: priority channel.
PRIORITY_CHOICES = ('Off', 'On')
# Native conventional C-Freq field index 16: Off or an integer from 0 to 999.
ALERT_TONE_CHOICES = ('Off', '1', '2', '3', '4', '5', '6', '7', '8', '9')
# Native C-Freq field index 13, immediately following Alert Tone.
ALERT_VOLUME_CHOICES = ('Auto',) + tuple(str(i) for i in range(1, 16))
# SDS Series File Specification v2.00: C-Freq alert color/pattern fields 14 and 15.
ALERT_COLOR_CHOICES = ('Off', 'Blue', 'Red', 'Magenta', 'Green', 'Cyan', 'Yellow', 'White')
ALERT_PATTERN_CHOICES = ('On', 'Slow Blink', 'Fast Blink')
# SDS Series File Specification v2.00, "Sub Audio" sheet.
# Preserve native strings exactly; display a friendlier description in the editor.
CTCSS_TONES = ('67.0','69.3','71.9','74.4','77.0','79.7','82.5','85.4',
 '88.5','91.5','94.8','97.4','100.0','103.5','107.2','110.9','114.8',
 '118.8','123.0','127.3','131.8','136.5','141.3','146.2','151.4',
 '156.7','159.8','162.2','165.5','167.9','171.3','173.8','177.3',
 '179.9','183.5','186.2','189.9','192.8','196.6','199.5','203.5',
 '206.5','210.7','218.1','225.7','229.1','233.6','241.8','250.3','254.1')
DCS_CODES = ('006','007','015','017','021','023','025','026','031','032',
 '036','043','047','050','051','053','054','065','071','072','073','074',
 '114','115','116','122','125','131','132','134','143','145','152','155',
 '156','162','165','172','174','205','212','223','225','226','243','244',
 '245','246','251','252','255','261','263','265','266','271','274','306',
 '311','315','325','331','332','343','346','351','356','364','365','371',
 '411','412','413','423','431','432','445','446','452','454','455','462',
 '464','465','466','503','506','516','523','526','532','546','565','606',
 '612','624','627','631','632','654','662','664','703','712','723','731',
 '732','734','743','754')
def audio_choices():
    choices = [('All (no code)', ''), ('Tone Search', 'TONE=Srch'),
               ('P25 NAC Search', 'NAC=Srch'),
               ('DMR Color Code Search', 'ColorCode=Srch'),
               ('NXDN RAN Search', 'RAN=Srch')]
    choices += [(f'CTCSS {v} Hz', f'TONE=C{v}') for v in CTCSS_TONES]
    choices += [(f'DCS {v}', f'TONE=D{v}') for v in DCS_CODES]
    choices += [(f'P25 NAC {v:03X}', f'NAC={v:X}') for v in range(4096)]
    choices += [(f'DMR Color Code {v}', f'ColorCode={v}') for v in range(16)]
    choices += [(f'NXDN RAN {v}', f'RAN={v}') for v in range(64)]
    choices += [(f'NXDN Area {v}', f'Area={v}') for v in range(2)]
    return choices

def audio_label(native):
    """Readable representation without silently altering the native field."""
    if not native: return 'All (no code)'
    if native == 'TONE=Srch': return 'Tone Search'
    if native == 'NAC=Srch': return 'P25 NAC Search'
    if native == 'ColorCode=Srch': return 'DMR Color Code Search'
    if native == 'RAN=Srch': return 'NXDN RAN/Area Search'
    suffix = ' (Tone L/O)' if native.endswith(',L/O') else ''
    tone = native[:-4] if suffix else native
    if tone.startswith('TONE=C'): return 'CTCSS ' + tone[6:] + ' Hz' + suffix
    if tone.startswith('TONE=D'): return 'DCS ' + tone[6:] + suffix
    if native.startswith('NAC='): return 'P25 NAC ' + native[4:].upper().zfill(3)
    if native.startswith('ColorCode='): return 'DMR Color Code ' + native[10:]
    if native.startswith('RAN='): return 'NXDN RAN ' + native[4:]
    if native.startswith('Area='): return 'NXDN Area ' + native[5:]
    return 'Imported: ' + native


def decode_audio_option(native):
    """Return (kind, value, tone_lockout) or ('imported', native, False).

    Recognize only valid Uniden settings. Unknown imported values remain untouched.
    """
    if native == '': return ('all', '', False)
    if native == 'TONE=Srch': return ('analog', 'TONE=Srch', False)
    if native in ('NAC=Srch', 'ColorCode=Srch', 'RAN=Srch'):
        return ('digital', native, False)
    match = re.fullmatch(r'TONE=([CD])([^,]+)(,L/O)?', native)
    if match:
        code_type, code, lockout = match.groups()
        if (code_type == 'C' and code in CTCSS_TONES) or (code_type == 'D' and code in DCS_CODES):
            return ('analog', f'TONE={code_type}{code}', bool(lockout))
    match = re.fullmatch(r'NAC=([0-9a-fA-F]{1,3})', native)
    if match and int(match.group(1), 16) <= 0xFFF:
        return ('digital', f'NAC={int(match.group(1),16):X}', False)
    for prefix, maximum in (('ColorCode=', 15), ('RAN=', 63), ('Area=', 1)):
        if native.startswith(prefix) and re.fullmatch(r'(?:0|[1-9][0-9]*)', native[len(prefix):]):
            if int(native[len(prefix):]) <= maximum:
                return ('digital', native, False)
    return ('imported', native, False)


class AudioOptionDialog(QDialog):
    """Sentinel-inspired analog/digital Audio Options editor; offline only."""
    def __init__(self, native_value, parent=None):
        super().__init__(parent)
        self._original = native_value
        original_kind, original_setting, tone_lo = decode_audio_option(native_value)
        self.setWindowTitle('Audio Options')
        self.setMinimumSize(640, 370)
        page = QVBoxLayout(self)
        type_line = QHBoxLayout()
        type_line.addWidget(QLabel('Audio Type'))
        self.audio_type = QComboBox()
        if original_kind == 'imported':
            self.audio_type.addItem('Keep imported value', 'imported')
        self.audio_type.addItem('All (no code)', 'all')
        self.audio_type.addItem('Analog', 'analog')
        self.audio_type.addItem('Digital', 'digital')
        idx = self.audio_type.findData(original_kind)
        self.audio_type.setCurrentIndex(idx)
        type_line.addWidget(self.audio_type)
        type_line.addStretch(1)
        page.addLayout(type_line)

        groups = QHBoxLayout()
        self.analog_group = QGroupBox('Analog Options')
        self.digital_group = QGroupBox('Digital Options')
        groups.addWidget(self.analog_group, 1)
        groups.addWidget(self.digital_group, 1)
        page.addLayout(groups, 1)
        analog = QVBoxLayout(self.analog_group)
        analog.addWidget(QLabel('CTCSS / DCS'))
        self.tone = QComboBox()
        self.tone.addItem('Tone Search', 'TONE=Srch')
        for hz in CTCSS_TONES:
            self.tone.addItem(f'CTCSS {hz} Hz', f'TONE=C{hz}')
        for code in DCS_CODES:
            self.tone.addItem(f'DCS {code}', f'TONE=D{code}')
        analog.addWidget(self.tone)
        self.tone_lo = QCheckBox('Tone L/O')
        self.tone_lo.setToolTip('Lock out the selected CTCSS or DCS tone')
        analog.addWidget(self.tone_lo)
        analog.addStretch(1)
        self.tone.currentIndexChanged.connect(self._update_enabled)

        digital = QGridLayout(self.digital_group)
        self.search_radio = QRadioButton('Digital Code Search')
        self.nac_radio = QRadioButton('P25 NAC')
        self.color_radio = QRadioButton('DMR Color Code')
        self.area_radio = QRadioButton('NXDN Area')
        self.ran_radio = QRadioButton('NXDN RAN')
        self.search_type = QComboBox()
        self.search_type.addItem('P25 NAC', 'NAC=Srch')
        self.search_type.addItem('DMR Color Code', 'ColorCode=Srch')
        self.search_type.addItem('NXDN RAN/Area', 'RAN=Srch')
        self.nac = QComboBox()
        for value in range(4096):
            self.nac.addItem(f'NAC {value:03X}', f'NAC={value:X}')
        self.color_code = QComboBox()
        for value in range(16):
            self.color_code.addItem(f'Color Code {value}', f'ColorCode={value}')
        self.area = QComboBox()
        for value in range(2):
            self.area.addItem(f'Area {value}', f'Area={value}')
        self.ran = QComboBox()
        for value in range(64):
            self.ran.addItem(f'RAN {value}', f'RAN={value}')
        for row, (radio, combo) in enumerate((
            (self.search_radio, self.search_type),
            (self.nac_radio, self.nac),
            (self.color_radio, self.color_code),
            (self.area_radio, self.area),
            (self.ran_radio, self.ran),
        )):
            digital.addWidget(radio, row, 0)
            digital.addWidget(combo, row, 1)
            radio.toggled.connect(self._update_enabled)
        digital.setColumnStretch(1, 1)
        digital.setRowStretch(5, 1)
        self.search_radio.setChecked(True)
        self.tone.setCurrentIndex(max(0, self.tone.findData('TONE=Srch')))
        if original_kind == 'analog':
            self.tone.setCurrentIndex(max(0, self.tone.findData(original_setting)))
            self.tone_lo.setChecked(tone_lo)
        if original_kind == 'digital':
            for prefix, radio, combo in (
                ('NAC=', self.nac_radio, self.nac),
                ('ColorCode=', self.color_radio, self.color_code),
                ('Area=', self.area_radio, self.area),
                ('RAN=', self.ran_radio, self.ran),
            ):
                if original_setting.startswith(prefix):
                    if original_setting.endswith('Srch'):
                        self.search_radio.setChecked(True)
                        self.search_type.setCurrentIndex(max(0, self.search_type.findData(original_setting)))
                    else:
                        radio.setChecked(True)
                        combo.setCurrentIndex(max(0, combo.findData(original_setting)))
                    break

        if original_kind == 'imported':
            warning = QLabel('Unrecognized imported value: ' + native_value)
            warning.setWordWrap(True)
            warning.setToolTip('Select another Audio Type to replace it, or Cancel to retain it.')
            page.addWidget(warning)
        self.audio_type.currentIndexChanged.connect(self._update_enabled)
        self._update_enabled()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        page.addWidget(buttons)

    def _update_enabled(self, *args):
        kind = self.audio_type.currentData()
        self.analog_group.setEnabled(kind == 'analog')
        self.digital_group.setEnabled(kind == 'digital')
        self.tone_lo.setEnabled(kind == 'analog' and self.tone.currentData() != 'TONE=Srch')
        for radio, combo in ((self.search_radio, self.search_type),
                             (self.nac_radio, self.nac),
                             (self.color_radio, self.color_code),
                             (self.area_radio, self.area),
                             (self.ran_radio, self.ran)):
            combo.setEnabled(kind == 'digital' and radio.isChecked())

    def selected_native_value(self):
        kind = self.audio_type.currentData()
        if kind == 'imported':
            return self._original
        if kind == 'all':
            result = ''
        elif kind == 'analog':
            result = self.tone.currentData()
            if result != 'TONE=Srch' and self.tone_lo.isChecked():
                result += ',L/O'
        elif kind == 'digital':
            for radio, combo in ((self.search_radio, self.search_type),
                                 (self.nac_radio, self.nac),
                                 (self.color_radio, self.color_code),
                                 (self.area_radio, self.area),
                                 (self.ran_radio, self.ran)):
                if radio.isChecked():
                    result = combo.currentData()
                    break
            else:
                raise ValueError('Choose a digital code option')
        else:
            raise ValueError('Choose an Audio Type')
        # Preserve original native spelling when no semantic change was made.
        original_kind, original_value, original_lockout = decode_audio_option(self._original)
        result_kind, result_value, result_lockout = decode_audio_option(result)
        if (original_kind, original_value, original_lockout) == \
                (result_kind, result_value, result_lockout):
            return self._original
        return result


NUMBER_TAG_CHOICES = ('Off', '0')  # Other tags are typed; avoid 1,000 options per row.


def valid_number_tag(value):
    """Reject out-of-range, signed, padded, or other non-native tag spellings."""
    return value == 'Off' or bool(re.fullmatch(r'(?:0|[1-9][0-9]{0,2})', value))
# Uniden SDS Series File Specification v2.00, Service Type chart.
# Keys are native FuncTagId strings, not display indices. "non" IDs are reserved.
SERVICE_TYPE_NAMES = {
    '1': 'Multi-Dispatch', '2': 'Law Dispatch', '3': 'Fire Dispatch',
    '4': 'EMS Dispatch', '6': 'Multi-Tac', '7': 'Law Tac',
    '8': 'Fire-Tac', '9': 'EMS-Tac', '11': 'Interop', '12': 'Hospital',
    '13': 'Ham', '14': 'Public Works', '15': 'Aircraft', '16': 'Federal',
    '17': 'Business', '20': 'Railroad', '21': 'Other',
    '22': 'Multi-Talk', '23': 'Law Talk', '24': 'Fire-Talk',
    '25': 'EMS-Talk', '26': 'Transportation', '29': 'Emergency Ops',
    '30': 'Military', '31': 'Media', '32': 'Schools', '33': 'Security',
    '34': 'Utilities', '37': 'Corrections',
    '208': 'Custom 1', '209': 'Custom 2', '210': 'Custom 3',
    '211': 'Custom 4', '212': 'Custom 5', '213': 'Custom 6',
    '214': 'Custom 7', '215': 'Custom 8',
    '216': 'Racing Officials', '217': 'Racing Teams',
}

def service_label(native):
    return SERVICE_TYPE_NAMES.get(native, 'Service ID ' + native if native else '(Unspecified)')

class NaturalTreeItem(QTreeWidgetItem):
    """Sort visible siblings naturally without altering native record positions."""
    def __lt__(self, other):
        column = self.treeWidget().sortColumn() if self.treeWidget() else 0
        def key(item):
            parts = re.split(r'(\d+)', item.text(column).casefold())
            return tuple((1, int(part)) if part.isdigit() else (0, part) for part in parts)
        return key(self) < key(other)


class NaturalTableItem(QTableWidgetItem):
    """Sort visible values naturally without modifying native scanner records."""
    def __lt__(self, other):
        def key(value):
            value = value.strip()
            if re.fullmatch(r'[+-]?\d+(?:\.\d+)?', value):
                return (0, Decimal(value))
            return (1, tuple((1, int(part)) if part.isdigit() else (0, part)
                             for part in re.split(r'(\d+)', value.casefold())))
        return key(self.text()) < key(other.text())


class FavoritesSettingsDialog(QDialog):
    def __init__(self, workspace, draft_name):
        super().__init__(workspace)
        self.workspace, self.draft_name = workspace, draft_name
        self.setWindowTitle('Edit Favorites List — ' + draft_name)
        self.resize(1260, 750)
        self._refreshing = False
        self._tag_confirmation_active = False
        self._layout_loading = True
        self._layout_settings = QSettings("SDS100DatabaseFavoritesManager", "FavoritesListEditor")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        note = QLabel('Edit existing settings here. Right-click (or Ctrl+X, Ctrl+C, Ctrl+V) to cut, copy and paste '
                      'systems, departments, channels and talkgroups between Favorites Lists.')
        note.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(note, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['System / Department / Site', 'Keys / Tag'])
        self.tree.setColumnWidth(0, 300)
        self.tree.setMinimumWidth(260)
        self.tree.setSortingEnabled(False)
        # v0.1.27: Ctrl+click adds one, Shift+click a range, in both panes.
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table = QTableWidget()
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSortingEnabled(False)
        self.table.setColumnWidth(0, 280)
        for col in range(1, len(COLUMNS)):
            self.table.setColumnWidth(col, 145)
        self.table.setColumnWidth(2, 175)
        header = self.table.horizontalHeader()
        header.setMinimumSectionSize(75)
        header.setSectionsMovable(True)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        saved_header = self._layout_settings.value('details_header_state')
        saved_count = self._layout_settings.value('details_header_columns_count', 16, type=int)
        if saved_header is not None:
            if saved_count == len(COLUMNS):
                header.restoreState(saved_header)
            elif saved_count in (16, 17):
                # Preserve the user's old visual order/widths when adding
                # Alert Volume (v0.0.6a) and Alert Pattern (v0.0.6b).
                legacy_table = QTableWidget(0, saved_count)
                legacy_header = legacy_table.horizontalHeader()
                legacy_header.setSectionsMovable(True)
                if legacy_header.restoreState(saved_header):
                    def new_position(old):
                        if saved_count == 17:
                            return old if old <= 12 else old + 1
                        return old if old <= 10 else old + 1 if old == 11 else old + 2
                    legacy_order = sorted(range(saved_count), key=legacy_header.visualIndex)
                    visual_order = []
                    for old_logical in legacy_order:
                        new_logical = new_position(old_logical)
                        visual_order.append(new_logical)
                        if saved_count == 16 and old_logical == 10:
                            visual_order.append(11)  # New Alert Volume
                        if old_logical == (12 if saved_count == 17 else 11):
                            visual_order.append(13)  # New Alert Pattern
                    for visual_position, logical in enumerate(visual_order):
                        header.moveSection(header.visualIndex(logical), visual_position)
                    for old_logical in range(saved_count):
                        self.table.setColumnWidth(new_position(old_logical), legacy_header.sectionSize(old_logical))
            elif saved_count == 18:
                # v0.1.19 added Heard and Last Heard at the end: keep the old order and widths.
                legacy_table = QTableWidget(0, 18)
                legacy_header = legacy_table.horizontalHeader()
                legacy_header.setSectionsMovable(True)
                if legacy_header.restoreState(saved_header):
                    for visual_position, logical in enumerate(sorted(range(18), key=legacy_header.visualIndex)):
                        header.moveSection(header.visualIndex(logical), visual_position)
                    for logical in range(18):
                        self.table.setColumnWidth(logical, legacy_header.sectionSize(logical))
        header.sectionMoved.connect(self._save_column_layout)
        header.sectionResized.connect(self._save_column_layout)
        header.sortIndicatorChanged.connect(self._save_sort_layout)
        self._layout_loading = False
        if saved_header is not None and saved_count in (16, 17, 18):
            self._save_column_layout()
        self._sort_column = self._layout_settings.value('details_sort_column', -1, type=int)
        self._sort_order = Qt.SortOrder(self._layout_settings.value('details_sort_order', 0, type=int))
        if 0 <= self._sort_column < len(COLUMNS):
            header.setSortIndicator(self._sort_column, self._sort_order)
        self.table.itemChanged.connect(self._changed)
        self.tree.currentItemChanged.connect(self._selected)
        splitter.addWidget(self.tree)
        splitter.addWidget(self.table)
        splitter.setSizes([340, 920])
        layout.addWidget(splitter, 1)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_context_menu)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_context_menu)
        self.tree.itemDoubleClicked.connect(self._tree_double_click)
        self.table.cellDoubleClicked.connect(self._table_double_click)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        reset_columns = QPushButton('Reset Columns')
        reset_columns.setToolTip('Restore the default column order and widths')
        reset_columns.clicked.connect(self._reset_column_layout)
        buttons.addButton(reset_columns, QDialogButtonBox.ButtonRole.ResetRole)
        undo_button = QPushButton('Undo')
        undo_button.setToolTip('Undo the last change to this list (Ctrl+Z). Applies to every open draft.')
        undo_button.clicked.connect(lambda: self._undo_redo('undo'))
        redo_button = QPushButton('Redo')
        redo_button.setToolTip('Redo the change just undone (Ctrl+Y)')
        redo_button.clicked.connect(lambda: self._undo_redo('redo'))
        bulk_button = QPushButton('Change Selected…')
        bulk_button.setToolTip('Set one value on all selected channels or talkgroups at once '
                               '(select rows with Ctrl+click or Shift+click on the row numbers)')
        bulk_button.clicked.connect(self._bulk_edit_selected)
        for extra in (undo_button, redo_button, bulk_button):
            buttons.addButton(extra, QDialogButtonBox.ButtonRole.ActionRole)
        for keys, mode in (('Ctrl+Z', 'undo'), ('Ctrl+Y', 'redo'), ('Ctrl+Shift+Z', 'redo')):
            QShortcut(QKeySequence(keys), self, activated=lambda m=mode: self._undo_redo(m))
        # Cut, Copy and Paste (v0.1.5): each pane has its own, so Ctrl+C while editing a cell still copies text.
        for widget, side in ((self.tree, 'tree'), (self.table, 'table')):
            for keys, action in (('Ctrl+X', 'cut'), ('Ctrl+C', 'copy'), ('Ctrl+V', 'paste')):
                shortcut = QShortcut(QKeySequence(keys), widget)
                shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
                shortcut.activated.connect(lambda s=side, a=action: self._clipboard_key(s, a))
        # Delete (v0.1.25): the selected system, site or department on the left; the selected rows on the right.
        for widget, handler in ((self.tree, self._delete_in_tree), (self.table, self._delete_selected_rows)):
            shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Delete), widget)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(handler)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons, 0)
        self._populate_tree()

    def _tree_context_menu(self, point):
        item = self.tree.itemAt(point)
        if item is None or item.data(0, ROLE) is None:
            menu = QMenu(self)
            self._add_clipboard_actions(menu, 'tree', None)
            menu.addSeparator()
            menu.addAction('New Conventional System…', self._new_conventional_system)
            menu.exec(self.tree.viewport().mapToGlobal(point))
            return
        picked = [i for i in self.tree.selectedItems() if i.data(0, ROLE) is not None]
        if item.isSelected() and len(picked) > 1:     # v0.1.27: right-click inside a multi-selection keeps it
            menu = QMenu(self)
            menu.addAction(f'Delete {len(picked)} Selected…\tDel', self._delete_in_tree)
            menu.exec(self.tree.viewport().mapToGlobal(point))
            return
        self.tree.setCurrentItem(item)  # Right-click always acts on the clicked item.
        entry_index, record_index = item.data(0, ROLE)
        if record_index is None:
            menu = QMenu(self)
            self._add_clipboard_actions(menu, 'tree', item)
            menu.addSeparator()
            menu.addAction('Rename System…', self._rename_selected_system)
            menu.addAction('New Department…', self._new_department)
            menu.addAction('New Conventional System…', self._new_conventional_system)
            menu.addAction('Delete System…\tDel', self._delete_selected_system)
            menu.addSeparator()
            menu.addAction('Add Unit Names from SDS100 Monitor…', self._add_monitor_unit_names)
            menu.addSeparator()
            menu.addAction('Expand All Departments', lambda: self._set_tree_children_expanded(item, True))
            menu.addAction('Collapse All Departments', lambda: self._set_tree_children_expanded(item, False))
            menu.exec(self.tree.viewport().mapToGlobal(point))
            return
        records = self.workspace.drafts[self.draft_name][entry_index]['records']
        kind = records[record_index][0]
        menu = QMenu(self)
        self._add_clipboard_actions(menu, 'tree', item)
        menu.addSeparator()
        if kind == 'Site':
            menu.addAction('Edit Site…', self._edit_selected_site)
            menu.addAction('Add Site Frequency…', self._add_site_frequency)
            menu.addAction('Delete Site…\tDel', self._delete_selected_site)
        elif kind == 'C-Group':
            menu.addAction('Rename Department…', self._rename_selected_department)
            menu.addAction('Add Conventional Frequency…', self._add_conventional_frequency)
            menu.addAction('New Department…', self._new_department)
            menu.addAction('Delete Department…\tDel', self._delete_selected_department)
        elif kind == 'T-Group':
            menu.addAction('Rename Department…', self._rename_selected_department)
            menu.addAction('Add Talkgroup…', self._add_talkgroup)
            menu.addAction('New Department…', self._new_department)
            menu.addAction('Delete Department…\tDel', self._delete_selected_department)
        if menu.actions():
            menu.exec(self.tree.viewport().mapToGlobal(point))

    @staticmethod
    def _set_tree_children_expanded(root, expanded):
        for index in range(root.childCount()):
            root.child(index).setExpanded(expanded)
        root.setExpanded(True)

    def _add_monitor_unit_names(self):
        """Unit ID names given in SDS100 Monitor onto this list's trunked systems, as one Undo step (v0.1.19)."""
        names = unit_aliases.load_names()
        if not names:
            QMessageBox.information(self, 'Unit Names from SDS100 Monitor',
                'SDS100 Monitor has no confirmed unit names yet (~/SDS100Monitor/unit_names.csv).\n\n'
                'Name units in the Monitor\'s Unit IDs window first; names marked Guess are left out.')
            return
        drafts = self.workspace.drafts[self.draft_name]
        result = unit_aliases.plan(drafts, names, unit_aliases.load_systems())
        text = unit_aliases.summary(result)
        if not (result['add'] or result['rename']):
            QMessageBox.information(self, 'Unit Names from SDS100 Monitor',
                (text or 'None of the named units was heard on a trunked system in this list.'))
            return
        if QMessageBox.question(self, 'Unit Names from SDS100 Monitor', text + '\n\nGo ahead?',
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.workspace._snapshot()
        count = unit_aliases.apply(drafts, result)
        self.workspace.refresh_draft()
        self.workspace.status.setText(f'{count} unit name(s) from SDS100 Monitor. '
                                      'Save Scanner Configuration, then Export to the scanner.')

    def _rename_selected_system(self):
        """Rename the native system header and its draft label together."""
        item = self.tree.currentItem()
        if item is None or item.data(0, ROLE) is None:
            return
        entry_index, record_index = item.data(0, ROLE)
        if record_index is not None:
            return
        entry = self.workspace.drafts[self.draft_name][entry_index]
        records = entry.get('records', [])
        if not records or records[0][0] not in ('Trunk', 'Conventional') or len(records[0]) <= 3:
            QMessageBox.warning(self, 'Rename unavailable', 'A complete native system header is required.')
            return
        original = records[0][3]
        name, accepted = QInputDialog.getText(self, 'Rename System', 'System Name:', text=original)
        if not accepted:
            return
        name = name.strip()
        if name == original:
            return
        if not name or len(name) > 64 or any(c in name for c in '\t\r\n\x00'):
            QMessageBox.warning(self, 'Invalid system name',
                                'Enter 1–64 characters without control characters.')
            return
        entries = self.workspace.drafts[self.draft_name]
        meta = entries[0] if entries and entries[0].get('scope') == 'metadata' else {}
        try:
            name.encode(meta.get('encoding', 'cp1252'))
        except (UnicodeError, LookupError):
            QMessageBox.warning(self, 'Unsupported characters',
                                'System name cannot be encoded in this Favorites List.')
            return
        if QMessageBox.question(self, 'Confirm system rename',
                f'Rename system {original} to {name}?\n\nAll sites, departments, frequencies, and talkgroups will be preserved.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.workspace._snapshot()
        records[0][3] = name
        entry['name'] = name
        self.workspace.refresh_draft()
        item.setText(0, name)
        self.workspace.status.setText('System renamed. Save Scanner Configuration to preserve this change.')

    def _rename_selected_department(self):
        """Rename only the native department Name Tag, preserving every child."""
        item = self.tree.currentItem()
        if item is None or item.data(0, ROLE) is None:
            return
        entry_index, record_index = item.data(0, ROLE)
        if record_index is None:
            return
        entry = self.workspace.drafts[self.draft_name][entry_index]
        records = entry['records']
        if not (0 <= record_index < len(records)):
            return
        row = records[record_index]
        if row[0] not in ('C-Group', 'T-Group') or len(row) <= 3:
            return
        original = row[3]
        name, accepted = QInputDialog.getText(self, 'Rename Department',
                                               'Department Name:', text=original)
        if not accepted:
            return
        name = name.strip()
        if name == original:
            return
        if not name or len(name) > 64 or any(c in name for c in '\t\r\n\x00'):
            QMessageBox.warning(self, 'Invalid department name',
                                'Enter a department name between 1 and 64 characters without control characters.')
            return
        entries = self.workspace.drafts[self.draft_name]
        meta = entries[0] if entries and entries[0].get('scope') == 'metadata' else {}
        try:
            name.encode(meta.get('encoding', 'cp1252'))
        except (UnicodeError, LookupError):
            QMessageBox.warning(self, 'Unsupported characters',
                                'Department name cannot be encoded in this Favorites List.')
            return
        if QMessageBox.question(self, 'Confirm department rename',
                f'Rename department {original} to {name}?\n\nAll channels and talkgroups will be preserved.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.workspace._snapshot()
        row[3] = name
        self.workspace.refresh_draft()
        # Avoid a full rebuild: the native record index and selected item are unchanged.
        item.setText(0, name)
        self.workspace.status.setText('Department renamed. Save Scanner Configuration to preserve this change.')

    def _table_context_menu(self, point):
        table_row = self.table.rowAt(point.y())
        clicked_column = self.table.columnAt(point.x())
        if table_row < 0 or self.table.item(table_row, 0) is None:
            menu = QMenu(self)
            self._add_clipboard_actions(menu, 'table', None)
            menu.exec(self.table.viewport().mapToGlobal(point))
            return
        selected_rows = {index.row() for index in self.table.selectedIndexes()}
        if table_row not in selected_rows or len(selected_rows) < 2:
            self.table.selectRow(table_row)   # a right-click inside a multi-row selection keeps it
            selected_rows = {table_row}
        entry_index, record_index = self.table.item(table_row, 0).data(ROLE)
        records = self.workspace.drafts[self.draft_name][entry_index]['records']
        kind = records[record_index][0]
        menu = QMenu(self)
        self._add_clipboard_actions(menu, 'table', table_row)
        menu.addSeparator()
        if len(selected_rows) > 1:
            menu.addAction(f'Change {len(selected_rows)} Selected Rows…', self._bulk_edit_selected)
            if kind in ('TGID', 'C-Freq'):
                menu.addAction(f'Delete {len(selected_rows)} Selected Rows…\tDel', self._delete_selected_rows)
            menu.exec(self.table.viewport().mapToGlobal(point))
            return
        if kind == 'T-Freq' and self._site_frequency_context() is not None:
            if record_index in self._site_frequency_context()[4]:
                menu.addAction('Edit Frequency…', self._edit_site_frequency)
                menu.addAction('Delete Frequency…', self._delete_selected_leaf)
        elif kind == 'TGID':
            menu.addAction('Edit Talkgroup Name…', lambda: self.table.editItem(self.table.item(table_row, 0)))
            menu.addAction('Edit TGID…', self._edit_tgid)
            menu.addAction('Delete Talkgroup…\tDel', self._delete_selected_leaf)
        elif kind == 'C-Freq':
            menu.addAction('Edit Channel Name…', lambda: self.table.editItem(self.table.item(table_row, 0)))
            menu.addAction('Edit Frequency…', lambda: self.table.editItem(self.table.item(table_row, 2)))
            menu.addAction('Delete Channel…\tDel', self._delete_selected_leaf)
        # Match double-click field editing without introducing a second edit path.
        # The existing per-field validation/confirmation remains authoritative.
        if kind in ('C-Freq', 'TGID') and clicked_column >= 0:
            cell = self.table.item(table_row, clicked_column)
            if cell is not None and (cell.flags() & Qt.ItemFlag.ItemIsEditable):
                menu.addAction('Edit Selected Field…',
                    lambda r=table_row, c=clicked_column: self._edit_table_field(r, c))
        if menu.actions():
            menu.exec(self.table.viewport().mapToGlobal(point))

    # ---- Cut, Copy and Paste (v0.1.5) -----------------------------------------------------------
    def _clipboard(self):
        return getattr(self.workspace, 'favorites_clipboard', None)

    def _set_clipboard(self, clip):
        self.workspace.favorites_clipboard = clip

    def _entries(self):
        return self.workspace.drafts.get(self.draft_name, [])

    def _add_clipboard_actions(self, menu, side, target):
        """Cut, Copy, Paste (and, in the left pane, Paste as New Favorites List) for a context menu."""
        native = clipboard.is_native(self._entries())
        clip = self._clipboard()
        if target is not None:
            for label, action in (('Cut', 'cut'), ('Copy', 'copy')):
                entry = menu.addAction(label + '\t' + ('Ctrl+X' if action == 'cut' else 'Ctrl+C'),
                                       lambda s=side, a=action: self._clipboard_key(s, a))
                entry.setEnabled(native)
        paste = menu.addAction('Paste' + (f' {clipboard.describe(clip)}' if clip else '') + '\tCtrl+V',
                               lambda s=side: self._clipboard_key(s, 'paste'))
        paste.setEnabled(native and clip is not None)
        if side == 'tree':
            new = menu.addAction('Paste as New Favorites List…', self._paste_as_new_list)
            hooks = getattr(self.workspace, 'new_list_hooks', None)
            new.setEnabled(bool(clip and clip['what'] != 'leaves' and hooks and 'create_native' in hooks
                                and hooks['available']()))

    def _clipboard_key(self, side, action):
        if not clipboard.is_native(self._entries()):
            QMessageBox.information(self, 'Cut, Copy and Paste',
                'Cut, Copy and Paste work in the Favorites Lists of a scanner configuration '
                '(opened with File → Open Scanner Configuration).')
            return
        try:
            if action == 'paste':
                self._paste(side)
            else:
                self._copy(side, cut=action == 'cut')
        except clipboard.ClipboardError as exc:
            QMessageBox.information(self, 'Cut, Copy and Paste', str(exc))

    def _selected_leaf_indices(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()} or
                      ({self.table.currentRow()} if self.table.currentRow() >= 0 else set()))
        found, entry_index = [], None
        for row in rows:
            cell = self.table.item(row, 0)
            data = cell.data(ROLE) if cell is not None else None
            if data is None:
                continue
            if entry_index is None:
                entry_index = data[0]
            if data[0] == entry_index:
                found.append(data[1])
        return entry_index, found

    def _copy(self, side, cut=False):
        entries = self._entries()
        if side == 'table':
            entry_index, indices = self._selected_leaf_indices()
            if not indices:
                raise clipboard.ClipboardError('Select the channels or talkgroups first.')
            clip = clipboard.copy_leaves(entries, entry_index, indices)
            start = None
        else:
            item = self.tree.currentItem()
            if item is None or item.data(0, ROLE) is None:
                raise clipboard.ClipboardError('Select a system or a department first.')
            entry_index, start = item.data(0, ROLE)
            if start is None:
                clip = clipboard.copy_system(entries, entry_index)
            elif entries[entry_index]['records'][start][0] == 'Site':
                raise clipboard.ClipboardError('Sites are copied with their system. Copy the system, or one of its '
                                               'talkgroup departments (which brings the sites along).')
            else:
                clip = clipboard.copy_department(entries, entry_index, start)
        clip['cut'] = cut
        if not cut:
            self._set_clipboard(clip)
            self.workspace.status.setText(f'Copied {clipboard.describe(clip)}. Paste it into this or another '
                                          'Favorites List.')
            return
        whole_system = False
        if clip['what'] != 'leaves':
            whole_system = clipboard.cut_check(entries, clip['what'], entry_index, start)
        note = ('\n\nIt is the last department of its system, so the system is removed from this list too.'
                if whole_system and clip['what'] == 'department' else '')
        if QMessageBox.question(self, 'Cut',
                f'Cut {clipboard.describe(clip)} from {self.draft_name}?{note}\n\n'
                'Paste puts it in this or another Favorites List. Undo brings it back here.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes) != QMessageBox.StandardButton.Yes:
            return
        self.workspace._snapshot()
        if clip['what'] == 'system':
            clipboard.remove_system(entries, entry_index)
        elif clip['what'] == 'department':
            clipboard.remove_department(entries, entry_index, start)
        else:
            clipboard.remove_leaves(entries, entry_index, indices)
        self._set_clipboard(clip)
        self._redraw(None if whole_system or clip['what'] == 'system' else
                     (entry_index, None if clip['what'] == 'department' else self._current_place()[1]))
        self.workspace.status.setText(f'Cut {clipboard.describe(clip)}. Paste it into a Favorites List, then '
                                      'Save Scanner Configuration.')

    def _current_place(self):
        item = self.tree.currentItem()
        return item.data(0, ROLE) if item is not None and item.data(0, ROLE) is not None else (None, None)

    def _redraw(self, place):
        self.workspace.refresh_draft()
        self._refreshing = True
        try:
            self.table.setRowCount(0)
        finally:
            self._refreshing = False
        if place is not None and place[0] is not None:
            self._restore_editor_selection(place[0], place[1])
        else:
            self.tree.clear()
            self._populate_tree()

    def _paste(self, side):
        import copy as _copy
        clip = self._clipboard()
        if clip is None:
            raise clipboard.ClipboardError('Nothing has been cut or copied yet.')
        target = self._current_place()
        if side == 'tree' and self.tree.currentItem() is None:
            target = (None, None)
        trial = _copy.deepcopy(self._entries())
        result = clipboard.paste(trial, clip, target)
        if result['added'] == 0 and not result['new_system'] and not result['sites'] and not result['departments']:
            QMessageBox.information(self, 'Paste', f'Everything in the {clipboard.describe(clip)} is already in '
                                    f'{self.draft_name}. Nothing was added.')
            return
        numbers = self._ask_numbers(clip, result)
        if numbers is None:
            return
        self.workspace._snapshot()
        entries = self._entries()
        before = len(entries)
        clipboard.paste(entries, clip, target, numbers)
        if clip.get('cut'):
            self._set_clipboard(None)             # a cut is pasted once; a copy can be pasted again
        place = (before, None) if len(entries) > before else target
        self._redraw(place)
        self.workspace.status.setText(f'Pasted {clipboard.describe(clip)} into {self.draft_name}. '
                                      'Save Scanner Configuration to keep it.')

    def _ask_numbers(self, clip, result):
        """Confirm a paste; when pasted quick keys or number tags clash with ones in the list, choose what
        to do with them. Returns 'keep', 'free' or 'clear', or None to cancel (v0.1.10)."""
        text = f'Paste {clipboard.describe(clip)}?\n\n' + clipboard.summary(clip, result, self.draft_name)
        clashes = result.get('clashes') or []
        if not clashes:
            if QMessageBox.question(self, 'Paste', text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.Yes) != QMessageBox.StandardButton.Yes:
                return None
            return 'keep'
        shown = '\n'.join(f'  • {name}: {word} {number:02d}' for name, word, number in clashes[:10])
        more = f'\n  … and {len(clashes) - 10} more' if len(clashes) > 10 else ''
        box = QMessageBox(self)
        box.setWindowTitle('Paste')
        box.setText(text + f'\n\n{len(clashes)} pasted number(s) are already used in {self.draft_name}:\n'
                    + shown + more)
        box.setInformativeText('Give them the next free numbers, set them Off, or keep them (used twice)?')
        free = box.addButton('Next Free Numbers', QMessageBox.ButtonRole.AcceptRole)
        clear = box.addButton('Set Them Off', QMessageBox.ButtonRole.AcceptRole)
        keep = box.addButton('Keep Them', QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(free)
        box.exec()
        return {free: 'free', clear: 'clear', keep: 'keep'}.get(box.clickedButton())

    def _paste_as_new_list(self):
        clip = self._clipboard()
        hooks = getattr(self.workspace, 'new_list_hooks', None)
        if clip is None or not hooks or 'create_native' not in hooks:
            return
        try:
            rows = clipboard.new_list_rows(clip)
        except clipboard.ClipboardError as exc:
            QMessageBox.information(self, 'Paste as New Favorites List', str(exc))
            return
        name, ok = QInputDialog.getText(self, 'Paste as New Favorites List',
                                        f'Name of the new Favorites List for the {clipboard.describe(clip)}:',
                                        text=clip.get('name', ''))
        name = name.strip()
        if not ok or not name:
            return
        try:
            hooks['check'](name)
            created = hooks['create_native'](name, rows, clip.get('encoding', 'cp1252'))
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Paste as New Favorites List', str(exc))
            return
        if clip.get('cut'):
            self._set_clipboard(None)
        QMessageBox.information(self, 'Paste as New Favorites List',
            f'Created the Favorites List {name} with the {clipboard.describe(clip)} in your scanner '
            f'configuration. It is open in the main window as {created}.'
            + ('\n\nSave Scanner Configuration to keep the cut from ' + self.draft_name + '.'
               if clip.get('cut') else ''))

    def _activity(self):
        """SDS100 Monitor's reception history, read once per window (v0.1.19)."""
        if getattr(self, '_activity_cache', None) is None:
            self._activity_cache = monitor_activity.load()
        return self._activity_cache

    def _undo_redo(self, mode):
        """Undo or redo through the workspace (one history for the whole session) and redraw."""
        item = self.tree.currentItem()
        place = item.data(0, ROLE) if item is not None else None
        history = self.workspace._undo if mode == 'undo' else self.workspace._redo
        if not history:
            self.workspace.status.setText('Nothing to ' + mode + '.')
            return
        (self.workspace.undo_change if mode == 'undo' else self.workspace.redo_change)()
        if self.draft_name not in self.workspace.drafts:
            QMessageBox.information(self, 'Draft no longer exists',
                                    'That change removed this draft, so the editor is closing.')
            self.reject()
            return
        self._refreshing = True
        try:
            self.table.setRowCount(0)
        finally:
            self._refreshing = False
        if place is not None:
            self._restore_editor_selection(place[0], place[1])
        else:
            self.tree.clear()
            self._populate_tree()
        self.workspace.status.setText(('Undid' if mode == 'undo' else 'Redid') + ' the last change.')

    def _bulk_edit_selected(self):
        """Set one enumerated value on every selected channel/talkgroup as a single undoable step."""
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        targets, entry_index = [], None
        for row in rows:
            cell = self.table.item(row, 0)
            data = cell.data(ROLE) if cell is not None else None
            if data is None:
                continue
            if entry_index is None:
                entry_index = data[0]
            if data[0] == entry_index:
                targets.append(data[1])
        if len(targets) < 2:
            QMessageBox.information(self, 'Change Selected',
                'Select two or more channels or talkgroups first (Ctrl+click or Shift+click the row numbers).')
            return
        records = self.workspace.drafts[self.draft_name][entry_index]['records']
        names = bulk_edit.field_names({records[i][0] for i in targets if records[i]})
        if not names:
            QMessageBox.information(self, 'Change Selected', 'None of the selected rows has a setting that can be changed together.')
            return
        field, ok = QInputDialog.getItem(self, 'Change Selected', f'Setting to change on {len(targets)} rows:', names, 0, False)
        if not ok:
            return
        values = bulk_edit.FIELDS[field][2]
        shown = [bulk_edit.label(field, v) for v in values]
        choice, ok = QInputDialog.getItem(self, 'Change Selected', f'New {field}:', shown, 0, False)
        if not ok:
            return
        value = values[shown.index(choice)]
        result = bulk_edit.plan(records, targets, field, value)
        if not result['changes']:
            QMessageBox.information(self, 'Change Selected', 'Nothing to change.\n\n' + bulk_edit.summary(field, value, result))
            return
        if QMessageBox.question(self, 'Confirm bulk change', bulk_edit.summary(field, value, result),
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.workspace._snapshot()
        count = bulk_edit.apply(records, result['changes'], field, value)
        item = self.tree.currentItem()
        place = item.data(0, ROLE) if item is not None else None
        self.workspace.refresh_draft()
        if place is not None:
            self._restore_editor_selection(place[0], place[1])
        self.workspace.status.setText(f'{field} changed on {count} item(s). Save Scanner Configuration to preserve it.')

    def _delete_selected_leaf(self):
        """Delete exactly one selected native leaf, never its parent or siblings."""
        selected = self.table.currentRow()
        if selected < 0 or self.table.item(selected, 0) is None:
            return
        entry_index, record_index = self.table.item(selected, 0).data(ROLE)
        records = self.workspace.drafts[self.draft_name][entry_index]['records']
        if not (0 <= record_index < len(records)):
            return
        record = records[record_index]
        kind = record[0]
        if kind not in ('C-Freq', 'TGID', 'T-Freq'):
            return
        parent = self.tree.currentItem()
        if parent is None or parent.data(0, ROLE) is None:
            return
        parent_entry, parent_index = parent.data(0, ROLE)
        if parent_entry != entry_index or parent_index is None:
            return
        parent_kind = records[parent_index][0]
        expected = {'C-Freq': 'C-Group', 'TGID': 'T-Group', 'T-Freq': 'Site'}
        if parent_kind != expected[kind]:
            return
        boundaries = {'C-Freq': ('C-Group', 'T-Group', 'Site', 'Trunk'),
                      'TGID': ('T-Group', 'C-Group', 'Site', 'Trunk'),
                      'T-Freq': ('Site', 'T-Group', 'Trunk')}
        end = parent_index + 1
        while end < len(records) and records[end][0] not in boundaries[kind]:
            end += 1
        siblings = [i for i in range(parent_index + 1, end) if records[i][0] == kind]
        if record_index not in siblings:
            return
        if kind == 'T-Freq' and len(siblings) == 1:
            QMessageBox.warning(self, 'Last site frequency',
                'Cannot delete the last frequency in a trunked site. '
                'Delete the site through its protected site-removal workflow instead.')
            return
        label = {'C-Freq': 'conventional channel', 'TGID': 'talkgroup',
                 'T-Freq': 'site frequency'}[kind]
        display = record[3] if kind != 'T-Freq' and len(record) > 3 else (
            f'{Decimal(record[5])/1000000:.6f} MHz' if len(record) > 5 else 'selected frequency')
        if QMessageBox.question(self, 'Confirm deletion',
                f'Delete only this {label}: {display}?\n\n'
                'Other records will be preserved. This change can be undone before saving.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        scroll_value = self.tree.verticalScrollBar().value()
        next_index = next((i for i in siblings if i > record_index), None)
        if next_index is None:
            next_index = next((i for i in reversed(siblings) if i < record_index), None)
        if next_index is not None and next_index > record_index:
            next_index -= 1
        self.workspace._snapshot()
        del records[record_index]
        self.workspace.refresh_draft()
        self._restore_editor_selection(entry_index, parent_index, next_index, scroll_value)
        self.workspace.status.setText(f'{label.capitalize()} deleted. Save Scanner Configuration to preserve this change.')

    def _edit_table_field(self, row, column):
        # Shared by the right-click menu and ordinary editable table cells.
        cell = self.table.item(row, column)
        if cell is not None and (cell.flags() & Qt.ItemFlag.ItemIsEditable):
            self.table.setCurrentCell(row, column)
            self.table.editItem(cell)

    def _tree_double_click(self, item, column):
        data = item.data(0, ROLE)
        if data is None:
            return
        if data[1] is None:
            self.tree.setCurrentItem(item)
            self._rename_selected_system()
            return
        entry_index, index = data
        kind = self.workspace.drafts[self.draft_name][entry_index]['records'][index][0]
        if kind == 'Site':
            self.tree.setCurrentItem(item)
            self._edit_selected_site()
        elif kind in ('C-Group', 'T-Group'):
            self.tree.setCurrentItem(item)
            self._rename_selected_department()

    def _table_double_click(self, row, column):
        cell = self.table.item(row, 0)
        if cell is None:
            return
        entry_index, index = cell.data(ROLE)
        record = self.workspace.drafts[self.draft_name][entry_index]['records'][index]
        if record[0] == 'T-Freq':
            self.table.selectRow(row)
            self._edit_site_frequency()
        elif record[0] == 'TGID' and column == 3:
            self.table.selectRow(row)
            self._edit_tgid()
        elif record[0] in ('C-Freq', 'TGID') and column == 0:
            self.table.editItem(self.table.item(row, 0))
        elif record[0] == 'C-Freq' and column == 2:
            self.table.editItem(self.table.item(row, 2))

    @staticmethod
    def _valid_tgid(value):
        # Native decimal talkgroup identifier; don't silently truncate/round.
        return bool(value) and len(value) <= 8 and value.isascii() and value.isdecimal() and 0 <= int(value) <= 16777215

    def _tgid_context(self):
        item = self.tree.currentItem()
        if item is None or item.data(0, ROLE) is None:
            return None
        entry_index, group_index = item.data(0, ROLE)
        records = self.workspace.drafts[self.draft_name][entry_index]['records']
        if group_index is None or records[group_index][0] != 'T-Group':
            return None
        end = group_index + 1
        while end < len(records) and records[end][0] not in ('T-Group', 'C-Group', 'Site', 'Trunk'):
            end += 1
        indices = [i for i in range(group_index + 1, end) if records[i][0] == 'TGID']
        return entry_index, records, group_index, end, indices

    def _tgid_system_indices(self, entry_index):
        # Each draft entry represents a native Favorites system; a TGID is
        # unique across all its talkgroup departments, not just one department.
        records = self.workspace.drafts[self.draft_name][entry_index]['records']
        return [i for i, row in enumerate(records) if row and row[0] == 'TGID' and len(row) > 5]

    def _tgid_dialog(self, title, name='', tgid=''):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        form = QFormLayout(dialog)
        name_edit = QLineEdit(name, dialog)
        name_edit.setMaxLength(64)
        id_edit = QLineEdit(tgid, dialog)
        id_edit.setPlaceholderText('Decimal TGID')
        form.addRow('Talkgroup Name:', name_edit)
        form.addRow('TGID:', id_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        name, value = name_edit.text().strip(), id_edit.text().strip()
        if not name or any(c in name for c in '\t\r\n\x00') or not self._valid_tgid(value):
            QMessageBox.warning(self, 'Invalid talkgroup', 'Enter a name (1–64 characters) and a decimal TGID between 0 and 16777215.')
            return None
        entries = self.workspace.drafts[self.draft_name]
        meta = entries[0] if entries and entries[0].get('scope') == 'metadata' else {}
        try:
            name.encode(meta.get('encoding', 'cp1252'))
        except (UnicodeError, LookupError):
            QMessageBox.warning(self, 'Unsupported characters', 'Talkgroup name cannot be encoded in this Favorites List.')
            return None
        return name, str(int(value))

    def _add_talkgroup(self):
        context = self._tgid_context()
        if context is None:
            return
        entry_index, records, group_index, end, indices = context
        # Only copy a verified complete native TGID record; never invent an
        # incomplete record with unknown positional metadata.
        templates = indices or self._tgid_system_indices(entry_index)
        templates = [i for i in templates if len(records[i]) >= 17]
        if not templates:
            QMessageBox.information(self, 'Template unavailable', 'No complete TGID record is available in this system as a safe template.')
            return
        result = self._tgid_dialog('Add Talkgroup')
        if result is None:
            return
        name, value = result
        if any(records[i][5] == value for i in self._tgid_system_indices(entry_index)):
            QMessageBox.information(self, 'Duplicate TGID', 'This TGID already exists in the selected trunked system.')
            return
        if QMessageBox.question(self, 'Confirm new talkgroup',
                f'Add {name} (TGID {value}) to {records[group_index][3]}?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        new = list(records[templates[0]])
        new[1] = 'TgidId=0'
        new[2] = records[group_index][1]  # Native parent group identifier
        new[3] = name
        new[4] = 'Off'
        new[5] = value
        defaults = {6:'ALL', 8:'2', 9:'0', 10:'Off', 11:'Auto', 12:'Off',
                    13:'On', 14:'Off', 15:'Off', 16:'Any'}
        for i, val in defaults.items():
            new[i] = val
        insert_at = indices[-1] + 1 if indices else end
        self.workspace._snapshot()
        records.insert(insert_at, new)
        self.workspace.refresh_draft()
        self._restore_editor_selection(entry_index, group_index, insert_at)
        self.workspace.status.setText('Talkgroup added. Save Scanner Configuration to preserve it.')

    def _edit_tgid(self):
        selected = self.table.currentRow()
        if selected < 0 or self.table.item(selected, 0) is None:
            return
        entry_index, index = self.table.item(selected, 0).data(ROLE)
        records = self.workspace.drafts[self.draft_name][entry_index]['records']
        row = records[index]
        if row[0] != 'TGID' or len(row) < 17:
            return
        result = self._tgid_dialog('Edit Talkgroup TGID', row[3], row[5])
        if result is None:
            return
        name, value = result
        if name == row[3] and value == row[5]:
            return
        if any(i != index and records[i][5] == value for i in self._tgid_system_indices(entry_index)):
            QMessageBox.information(self, 'Duplicate TGID', 'This TGID already exists in the selected trunked system.')
            return
        if QMessageBox.question(self, 'Confirm talkgroup changes',
                f'Change {row[3]} (TGID {row[5]}) to {name} (TGID {value})?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.workspace._snapshot()
        row[3], row[5] = name, value
        self.workspace.refresh_draft()
        # Refresh only the selected table; preserve tree and current position.
        self._selected(self.tree.currentItem(), None)
        for r in range(self.table.rowCount()):
            cell = self.table.item(r, 0)
            if cell is not None and cell.data(ROLE) == (entry_index, index):
                self.table.selectRow(r)
                break
        self.workspace.status.setText('TGID changed. Save Scanner Configuration to preserve it.')

    def _add_conventional_frequency(self):
        """v0.1.7: typed in with name, frequency, modulation and tone; made with the scanner's defaults."""
        item = self.tree.currentItem()
        if item is None or item.data(0, ROLE) is None:
            return
        entry_index, group_index = item.data(0, ROLE)
        records = self.workspace.drafts[self.draft_name][entry_index]['records']
        if group_index is None or records[group_index][0] != 'C-Group':
            return
        dialog = HandEntryDialog(self, 'Add Conventional Frequency', 'channel', department=False)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        channel = dialog.result_values['channel']
        row = hand_entry.channel_row(channel)
        end = clipboard.block_at(records, group_index)[2]
        if any(clipboard.leaf_key(records[i]) == clipboard.leaf_key(row) for i in range(group_index, end)):
            QMessageBox.information(self, 'Duplicate frequency',
                                    'This frequency (with the same tone) is already in this department.')
            return
        self.workspace._snapshot()
        records.insert(end, row)
        self.workspace.refresh_draft()
        self._restore_editor_selection(entry_index, group_index, end)
        self.workspace.status.setText(f'Added {channel["name"]}. Save Configuration keeps it.')

    # ---- systems and departments by hand (v0.1.7) ---------------------------------------------------
    def _system_of_selection(self):
        item = self.tree.currentItem()
        if item is None or item.data(0, ROLE) is None:
            return None
        return item.data(0, ROLE)[0]

    def _new_department(self):
        entry_index = self._system_of_selection()
        if entry_index is None:
            return
        records = self._entries()[entry_index]['records']
        trunk = clipboard.kind_of(records[0]) == 'Trunk'
        kind = 'T-Group' if trunk else 'C-Group'
        like = next((records[s] for k, s, _e in clipboard.blocks(records) if k == kind), None)
        dialog = HandEntryDialog(self, 'New Department — ' + clipboard.system_name(records),
                                 'talkgroup' if trunk else 'channel',
                                 note='A department starts with one ' + ('talkgroup' if trunk else 'channel') +
                                      '; add more afterwards.')
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.result_values
        try:
            if trunk:
                template = next((r for r in records if clipboard.kind_of(r) == 'TGID'), None)
                if values['tgid'] in {r[5] for r in records if clipboard.kind_of(r) == 'TGID'}:
                    raise hand_entry.EntryError('That talkgroup ID is already in this system.')
                rows = hand_entry.talkgroup_department_rows(
                    values['department'], [hand_entry.talkgroup_row(template, values['talkgroup'], values['tgid'])], like)
            else:
                rows = hand_entry.conventional_department_rows(values['department'], [values['channel']], like)
        except hand_entry.EntryError as exc:
            QMessageBox.information(self, 'New Department', str(exc))
            return
        self.workspace._snapshot()
        start = len(records)
        records.extend(rows)
        self._redraw((entry_index, start))
        self.workspace.status.setText(f'Added department {values["department"]}. Save Configuration keeps it.')

    def _new_conventional_system(self):
        if not clipboard.is_native(self._entries()):
            return
        dialog = HandEntryDialog(self, 'New Conventional System', 'channel', system=True,
                                 note='A conventional system starts with one department and one channel; '
                                      'add more afterwards. Trunked systems come from the database or '
                                      'RadioReference (their sites and talkgroups).')
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.result_values
        rows = hand_entry.conventional_system_rows(values['system'], values['department'], [values['channel']])
        entries = self._entries()
        self.workspace._snapshot()
        entries.append(clipboard._new_entry(entries, rows))
        self._redraw((len(entries) - 1, None))
        self.workspace.status.setText(f'Added system {values["system"]}. Save Configuration keeps it.')

    def _delete_selected_system(self):
        entry_index = self._system_of_selection()
        if entry_index is None:
            return
        entries = self._entries()
        name = clipboard.system_name(entries[entry_index]['records'])
        try:
            clipboard.cut_check(entries, 'system', entry_index)
        except clipboard.ClipboardError as exc:
            QMessageBox.information(self, 'Delete System', str(exc))
            return
        if QMessageBox.question(self, 'Delete System', f'Delete the system {name} and everything in it from '
                                f'{self.draft_name}?\n\nUndo brings it back.',
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.workspace._snapshot()
        clipboard.remove_system(entries, entry_index)
        self._redraw(None)
        self.workspace.status.setText(f'Deleted system {name}. Save Configuration keeps the change.')

    def _delete_in_tree(self):
        picked = [i.data(0, ROLE) for i in self.tree.selectedItems() if i.data(0, ROLE) is not None]
        if len(picked) > 1:                       # v0.1.27: several selected with Ctrl or Shift
            self._delete_many(picked)
            return
        item = self.tree.currentItem()
        if item is None or item.data(0, ROLE) is None:
            return
        entry_index, start = item.data(0, ROLE)
        if start is None:
            self._delete_selected_system()
            return
        kind = self._entries()[entry_index]['records'][start][0]
        if kind == 'Site':
            self._delete_selected_site()
        elif kind in ('C-Group', 'T-Group'):
            self._delete_selected_department()

    def _delete_many(self, picked):
        entries = self._entries()
        targets = [tuple(p) for p in picked]
        try:
            plan = clipboard.removal_plan(entries, targets)
        except clipboard.ClipboardError as exc:
            QMessageBox.information(self, 'Delete', str(exc))
            return
        if QMessageBox.question(self, 'Delete', clipboard.describe_plan(plan) + '\n\nUndo brings them back.',
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.workspace._snapshot()
        clipboard.remove_planned(entries, plan, targets)
        self._redraw(None)
        self.workspace.status.setText('Deleted ' + ', '.join(
            f'{len(plan[k])} {k}' for k in ('systems', 'sites', 'departments') if plan[k])
            + '. Save Configuration keeps the change.')

    def _delete_selected_site(self):
        """A trunked site with its frequencies (v0.1.25); never the last site of a system."""
        item = self.tree.currentItem()
        if item is None or item.data(0, ROLE) is None or item.data(0, ROLE)[1] is None:
            return
        entry_index, start = item.data(0, ROLE)
        entries = self._entries()
        records = entries[entry_index]['records']
        if records[start][0] != 'Site':
            return
        name = records[start][3]
        block = clipboard.block_at(records, start)
        frequencies = sum(1 for r in records[block[1]:block[2]] if r and r[0] == 'T-Freq')
        if clipboard.site_count(records) == 1:
            QMessageBox.information(self, 'Delete Site', f'{name} is the only site of '
                                    f'{clipboard.system_name(records)}; a trunked system needs at least one. '
                                    'Delete the system instead.')
            return
        if QMessageBox.question(self, 'Delete Site', f'Delete the site {name} and its {frequencies} '
                                f'frequenc{"y" if frequencies == 1 else "ies"} from '
                                f'{clipboard.system_name(records)}?\n\nUndo brings it back.',
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.workspace._snapshot()
        clipboard.remove_site(entries, entry_index, start)
        self._redraw((entry_index, None))
        self.workspace.status.setText(f'Deleted site {name}. Save Configuration keeps the change.')

    def _delete_selected_rows(self):
        """Delete the selected channels or talkgroups (v0.1.25: several at once, as one Undo step)."""
        entry_index, indices = self._selected_leaf_indices()
        if len(indices) <= 1:
            self._delete_selected_leaf()
            return
        entries = self._entries()
        try:
            rows = clipboard.leaves_check(entries, entry_index, indices)
        except clipboard.ClipboardError as exc:
            QMessageBox.information(self, 'Delete', str(exc))
            return
        if not rows:
            return
        if QMessageBox.question(self, 'Delete', f'Delete the {len(rows)} selected channels or talkgroups?'
                                '\n\nUndo brings them back.',
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.workspace._snapshot()
        clipboard.remove_leaves(entries, entry_index, rows)
        self._redraw(self._current_place())
        self.workspace.status.setText(f'Deleted {len(rows)} channels or talkgroups. '
                                      'Save Configuration keeps the change.')

    def _delete_selected_department(self):
        item = self.tree.currentItem()
        if item is None or item.data(0, ROLE) is None or item.data(0, ROLE)[1] is None:
            return
        entry_index, start = item.data(0, ROLE)
        entries = self._entries()
        records = entries[entry_index]['records']
        name = records[start][3]
        try:
            whole = clipboard.cut_check(entries, 'department', entry_index, start)
        except clipboard.ClipboardError as exc:
            QMessageBox.information(self, 'Delete Department', str(exc))
            return
        note = '\n\nIt is the last department, so the system goes too.' if whole else ''
        if QMessageBox.question(self, 'Delete Department', f'Delete the department {name} and its entries?'
                                f'{note}\n\nUndo brings it back.',
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.workspace._snapshot()
        gone = clipboard.remove_department(entries, entry_index, start)
        self._redraw(None if gone else (entry_index, None))
        self.workspace.status.setText(f'Deleted department {name}. Save Configuration keeps the change.')

    def _edit_selected_site(self):
        """Edit only verified native Site offsets; preserve all other fields."""
        item = self.tree.currentItem()
        if item is None or item.data(0, ROLE) is None:
            QMessageBox.information(self, 'Select a site', 'Select a trunked Site in the left tree first.')
            return
        entry_index, row_index = item.data(0, ROLE)
        if row_index is None:
            QMessageBox.information(self, 'Select a site', 'Select a trunked Site, not the system.')
            return
        row = self.workspace.drafts[self.draft_name][entry_index]['records'][row_index]
        if not row or row[0] != 'Site' or len(row) <= 18:
            QMessageBox.information(self, 'Site unavailable', 'Select a complete native Site record.')
            return
        fields = ((3, 'Site Name', None),
                  (4, 'Avoid', ('Off', 'On')),
                  (8, 'Modulation', ('AUTO', 'NFM', 'FM')),
                  (12, 'Attenuator', ('Off', 'On')),
                  (16, 'Quick Key', ('Off',) + tuple(str(n) for n in range(100))),   # department set (v0.1.22)
                  (18, 'Filter', ('Global', 'Normal', 'Invert', 'Auto',
                                  'Wide Normal', 'Wide Invert', 'Wide Auto', 'Off')))
        dialog = QDialog(self)
        dialog.setWindowTitle('Edit Trunked Site — ' + row[3])
        form = QFormLayout(dialog)
        controls = {}
        for index, label, choices in fields:
            if choices is None:
                control = QLineEdit(row[index], dialog)
                control.setMaxLength(64)
            else:
                control = QComboBox(dialog)
                options = list(choices)
                if row[index] not in options:
                    options.insert(0, row[index])
                control.addItems(options)
                control.setCurrentText(row[index])
            controls[index] = control
            form.addRow(label + ':', control)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        actions.accepted.connect(dialog.accept)
        actions.rejected.connect(dialog.reject)
        form.addRow(actions)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        changes = {}
        for index, label, choices in fields:
            new = controls[index].text().strip() if choices is None else controls[index].currentText()
            if choices is None:
                if not new or any(c in new for c in '\t\r\n\x00'):
                    QMessageBox.warning(self, 'Invalid site name', 'Enter a nonempty name without control characters.')
                    return
                entries = self.workspace.drafts[self.draft_name]
                meta = entries[0] if entries and entries[0].get('scope') == 'metadata' else {}
                try:
                    new.encode(meta.get('encoding', 'cp1252'))
                except (UnicodeError, LookupError):
                    QMessageBox.warning(self, 'Unsupported characters', 'Site name cannot be encoded in this Favorites List.')
                    return
            elif new not in choices and new != row[index]:
                return
            if new != row[index]:
                changes[index] = (label, row[index], new)
        if not changes:
            return
        summary = '\n'.join(f'{label}: {old} → {new}' for label, old, new in changes.values())
        answer = QMessageBox.question(self, 'Confirm trunked site changes',
            f'Apply these changes to site {row[3]}?\n\n{summary}',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.workspace._snapshot()
        for index, (_, _, new) in changes.items():
            row[index] = new
        if 3 in changes:
            item.setText(0, row[3])
        self.workspace.refresh_draft()
        self.workspace.status.setText('Trunked site settings changed. Save Scanner Configuration to preserve them.')

    def _site_frequency_context(self):
        """Return selected site and its bounded native frequency block."""
        item = self.tree.currentItem()
        if item is None or item.data(0, ROLE) is None:
            return None
        entry_index, site_index = item.data(0, ROLE)
        if site_index is None:
            return None
        records = self.workspace.drafts[self.draft_name][entry_index]['records']
        if not (0 <= site_index < len(records)) or records[site_index][0] != 'Site':
            return None
        end = site_index + 1
        while end < len(records) and records[end][0] not in ('Site', 'T-Group', 'Trunk'):
            end += 1
        indices = [i for i in range(site_index + 1, end) if records[i][0] == 'T-Freq']
        return entry_index, records, site_index, end, indices

    @staticmethod
    def _parse_site_mhz(value):
        """Exact decimal MHz to integer Hz; no floating point rounding."""
        try:
            mhz = Decimal(value.strip())
            hz = mhz * 1000000
            if not mhz.is_finite() or hz != hz.to_integral_value() or not (100000 <= hz <= 1300000000):
                return None
            return str(int(hz))
        except (InvalidOperation, ValueError):
            return None

    def _frequency_dialog(self, title, current=''):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        form = QFormLayout(dialog)
        frequency = QLineEdit(current, dialog)
        frequency.setPlaceholderText('e.g. 853.612500')
        form.addRow('Frequency (MHz):', frequency)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        actions.accepted.connect(dialog.accept)
        actions.rejected.connect(dialog.reject)
        form.addRow(actions)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        hz = self._parse_site_mhz(frequency.text())
        if hz is None:
            QMessageBox.warning(self, 'Invalid frequency', 'Enter a valid frequency in MHz, with at most six decimal places (0.1–1300 MHz).')
        return hz

    def _add_site_frequency(self):
        context = self._site_frequency_context()
        if context is None:
            QMessageBox.information(self, 'Select a site', 'Select a trunked Site in the left tree first.')
            return
        entry_index, records, site_index, end, indices = context
        if not indices:
            QMessageBox.information(self, 'Template unavailable', 'This site has no native T-Freq record to use as a safe template. No changes were made.')
            return
        hz = self._frequency_dialog('Add Frequency — ' + records[site_index][3])
        if hz is None:
            return
        if any(len(records[i]) > 5 and records[i][5] == hz for i in indices):
            QMessageBox.information(self, 'Duplicate frequency', 'This frequency is already present in the selected site.')
            return
        template = records[indices[0]]
        if len(template) not in (8, 9):
            QMessageBox.warning(self, 'Unsupported record', 'Expected a documented 8-column or observed 9-column T-Freq template.')
            return
        answer = QMessageBox.question(self, 'Confirm new site frequency',
            f'Add {Decimal(hz)/1000000:.6f} MHz to {records[site_index][3]}?\n\nOther site frequencies and talkgroups will be preserved.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        new_record = list(template)
        # T-Freq column 2 is reserved in the SDS specification: preserve the
        # observed native template value (blank in many Favorites files).
        new_record[1] = template[1]
        new_record[5] = hz
        self.workspace._snapshot()
        records.insert(indices[-1] + 1, new_record)
        self.workspace.refresh_draft()
        self._restore_editor_selection(entry_index, site_index, indices[-1] + 1)
        self.workspace.status.setText('Site frequency added. Save Scanner Configuration to preserve it.')

    def _edit_site_frequency(self):
        context = self._site_frequency_context()
        if context is None:
            QMessageBox.information(self, 'Select a site', 'Select a trunked Site in the left tree first.')
            return
        _, records, site_index, _, indices = context
        selected = self.table.currentRow()
        if selected < 0 or self.table.item(selected, 0) is None:
            QMessageBox.information(self, 'Select a frequency', 'Select a frequency row in the table first.')
            return
        _, record_index = self.table.item(selected, 0).data(ROLE)
        if record_index not in indices or len(records[record_index]) <= 5:
            QMessageBox.information(self, 'Select a frequency', 'Select a T-Freq row belonging to this site.')
            return
        old = records[record_index][5]
        hz = self._frequency_dialog('Edit Site Frequency', f'{Decimal(old)/1000000:.6f}')
        if hz is None or hz == old:
            return
        if any(i != record_index and len(records[i]) > 5 and records[i][5] == hz for i in indices):
            QMessageBox.information(self, 'Duplicate frequency', 'This frequency is already present in the selected site.')
            return
        answer = QMessageBox.question(self, 'Confirm site frequency change',
            f'Change {Decimal(old)/1000000:.6f} MHz to {Decimal(hz)/1000000:.6f} MHz in {records[site_index][3]}?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.workspace._snapshot()
        records[record_index][5] = hz
        self.workspace.refresh_draft()
        scroll_value = self.tree.verticalScrollBar().value()
        self._restore_editor_selection(context[0], site_index, record_index, scroll_value)
        self.workspace.status.setText('Site frequency changed. Save Scanner Configuration to preserve it.')

    def _save_sort_layout(self, column, order):
        if not self._layout_loading:
            self._sort_column, self._sort_order = column, order
            self._layout_settings.setValue('details_sort_column', column)
            self._layout_settings.setValue('details_sort_order', order.value)

    def _save_column_layout(self, *args):
        if not self._layout_loading:
            self._layout_settings.setValue('details_header_state', self.table.horizontalHeader().saveState())
            self._layout_settings.setValue('details_header_columns_count', len(COLUMNS))

    def _reset_column_layout(self):
        """Reset presentation only; never modify scanner records."""
        self._layout_loading = True
        try:
            header = self.table.horizontalHeader()
            for logical in range(len(COLUMNS)):
                visual = header.visualIndex(logical)
                if visual != logical:
                    header.moveSection(visual, logical)
            for col in range(len(COLUMNS)):
                self.table.setColumnWidth(col, 280 if col == 0 else 175 if col == 2 else 145)
        finally:
            self._layout_loading = False
        self._layout_settings.remove('details_header_state')
        self._layout_settings.remove('details_header_columns_count')
        self._layout_settings.remove('details_sort_column')
        self._layout_settings.remove('details_sort_order')
        self._sort_column = -1
        self.table.setSortingEnabled(False)

    def _restore_editor_selection(self, entry_index, group_index, frequency_index=None, scroll_value=None):
        """Rebuild without losing the active department/site or new frequency row."""
        if scroll_value is None:
            scroll_value = self.tree.verticalScrollBar().value()
        # Preserve user-expanded systems and their visual context across rebuilds.
        expanded = {}
        for i in range(self.tree.topLevelItemCount()):
            root = self.tree.topLevelItem(i)
            expanded[root.data(0, ROLE)] = root.isExpanded()
        self.tree.clear()
        self._populate_tree()
        for i in range(self.tree.topLevelItemCount()):
            root = self.tree.topLevelItem(i)
            if root.data(0, ROLE) in expanded:
                root.setExpanded(expanded[root.data(0, ROLE)])
        selected_item = None
        for root_index in range(self.tree.topLevelItemCount()):
            root = self.tree.topLevelItem(root_index)
            for item in [root] + [root.child(i) for i in range(root.childCount())]:
                if item.data(0, ROLE) == (entry_index, group_index):
                    selected_item = item
                    break
            if selected_item is not None:
                break
        if selected_item is None:
            return
        self.tree.setCurrentItem(selected_item)
        self.tree.verticalScrollBar().setValue(scroll_value)
        if frequency_index is not None:
            for table_row in range(self.table.rowCount()):
                cell = self.table.item(table_row, 0)
                if cell is not None and cell.data(ROLE) == (entry_index, frequency_index):
                    self.table.selectRow(table_row)
                    self.table.scrollToItem(cell)
                    break

    def _populate_tree(self):
        entries = self.workspace.drafts.get(self.draft_name, [])
        for index, entry in enumerate(entries):
            if entry.get('scope') == 'metadata':
                continue
            records = entry.get('records') or []
            root = NaturalTreeItem(self.tree, [entry.get('name', '(unnamed)'), badge(records[0]) if records else ''])
            root.setData(0, ROLE, (index, None))
            for row_index, row in enumerate(entry.get('records', [])):
                if row and row[0] in ('C-Group', 'T-Group', 'Site'):
                    node = NaturalTreeItem(root, [row[3] if len(row)>3 and row[3] else row[0], badge(row)])
                    node.setData(0, ROLE, (index, row_index))
            root.setExpanded(True)
        self.tree.setSortingEnabled(True)
        self.tree.sortItems(0, Qt.SortOrder.AscendingOrder)
        if self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def _selected(self, item, previous):
        self._refreshing = True
        self.table.setSortingEnabled(False)
        try:
            self.table.setRowCount(0)
            if item is None: return
            entry_index, group_index = item.data(0, ROLE)
            records = self.workspace.drafts[self.draft_name][entry_index].get('records', [])
            current_group = None
            for index, row in enumerate(records):
                if not row: continue
                kind = row[0]
                if kind in ('C-Group', 'T-Group', 'Site'):
                    current_group = index
                    continue
                if kind not in ('C-Freq','T-Freq','TGID','C-Channel','T-Channel',
                                'C-Frequency','T-Frequency','Tgid','T-Id'):
                    continue
                if group_index is not None and current_group != group_index:
                    continue
                values = favorites_record_columns(row) + [''] * (len(COLUMNS) - 6)
                if kind == 'C-Freq' and len(row)>4:
                    values[6] = row[4]
                if kind in ('TGID','Tgid','T-Id') and len(row)>4:
                    values[6] = row[4]
                if kind == 'TGID':
                    for logical_column, native_index in TGID_VISIBLE_NATIVE.items():
                        if len(row) > native_index:
                            values[logical_column] = tgid_display_value(logical_column, row[native_index])
                position = self.table.rowCount()
                self.table.insertRow(position)
                if kind == 'C-Freq' and len(row) > 6:
                    values[4] = row[6]
                if kind in ('C-Freq', 'TGID'):
                    values[HEARD_COLUMN], values[LAST_HEARD_COLUMN] = monitor_activity.columns(
                        self._activity(), records[0][3] if records and len(records[0]) > 3 else '', row)
                for col, value in enumerate(values):
                    cell = NaturalTableItem(str(value))
                    cell.setData(ROLE, (entry_index, index))
                    # Channel name/frequency, or canonical TGID talkgroup name.
                    if not ((col in (0, 2) and kind == 'C-Freq') or
                            (col == 0 and kind == 'TGID')):
                        cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(position, col, cell)
                if kind == 'TGID':
                    for logical_column, choices in TGID_EDIT_CHOICES.items():
                        native_index = TGID_VISIBLE_NATIVE[logical_column]
                        if len(row) <= native_index:
                            continue  # Incomplete imported record stays read-only.
                        original = row[native_index]
                        choice_values = list(SERVICE_TYPE_NAMES) if choices is None else list(choices)
                        if original not in choice_values:
                            choice_values.insert(0, original)  # Preserve unknown imports.
                        combo = QComboBox(self.table)
                        combo.setToolTip('Trunked talkgroup ' + TGID_FIELD_LABELS[logical_column])
                        if logical_column == 15:
                            combo.setMaxVisibleItems(15)
                            combo.setEditable(True)
                            combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
                            combo.setCompleter(None)
                            combo.setValidator(QRegularExpressionValidator(
                                QRegularExpression(r'(?:Off|0|[1-9][0-9]{0,2})'), combo))
                        for native in choice_values:
                            combo.addItem(tgid_display_value(logical_column, native), native)
                        combo.setCurrentIndex(choice_values.index(original))
                        if logical_column == 15:
                            combo.activated.connect(
                                lambda _i, ei=entry_index, ri=index, cb=combo:
                                self._change_tgid_number_tag(ei, ri, cb))
                            combo.lineEdit().editingFinished.connect(
                                lambda ei=entry_index, ri=index, cb=combo:
                                self._change_tgid_number_tag(ei, ri, cb))
                        else:
                            combo.currentIndexChanged.connect(
                                lambda _i, ei=entry_index, ri=index, cb=combo, col=logical_column:
                                self._change_tgid_setting(ei, ri, cb, col))
                        self.table.setCellWidget(position, logical_column, combo)
                if kind == 'C-Freq' and len(row) > 6:
                    combo = QComboBox(self.table)
                    old_mode = row[6]
                    choices = list(MODULATION_CHOICES)
                    if old_mode not in choices:
                        choices.insert(0, old_mode)
                    combo.addItems(choices)
                    combo.setCurrentText(old_mode)
                    combo.currentTextChanged.connect(
                        lambda new_mode, ei=entry_index, ri=index, cb=combo:
                        self._change_modulation(ei, ri, cb, new_mode))
                    self.table.setCellWidget(position, 4, combo)
                if kind in ('C-Freq', 'TGID', 'Tgid', 'T-Id') and len(row) > 4:
                    avoid_combo = QComboBox(self.table)
                    old_avoid = row[4]
                    choices = list(AVOID_CHOICES)
                    if old_avoid not in choices:
                        choices.insert(0, old_avoid)
                    for native in choices:
                        avoid_combo.addItem(AVOID_LABELS.get(native, native), native)
                    avoid_combo.setCurrentIndex(choices.index(old_avoid))
                    avoid_combo.currentIndexChanged.connect(
                        lambda _i, ei=entry_index, ri=index, cb=avoid_combo:
                        self._change_avoid(ei, ri, cb))
                    self.table.setCellWidget(position, 6, avoid_combo)
                if kind == 'C-Freq' and len(row) > 7:
                    audio_button = QPushButton(audio_label(row[7]), self.table)
                    audio_button.setToolTip('Edit Audio Option (CTCSS, DCS, NAC, Color Code, RAN, Area)')
                    audio_button.clicked.connect(
                        lambda _checked=False, ei=entry_index, ri=index, btn=audio_button:
                        self._change_audio_option(ei, ri, btn))
                    self.table.setCellWidget(position, 7, audio_button)
                if kind == 'C-Freq' and len(row) > 8:
                    old_service = row[8]
                    self.table.item(position, 5).setText(service_label(old_service))
                    service_combo = QComboBox(self.table)
                    service_combo.setToolTip('Service Type (Uniden SDS Series File Specification v2.00); native ID retained')
                    choices = list(SERVICE_TYPE_NAMES)
                    if old_service not in choices:
                        choices.insert(0, old_service)
                    for native in choices:
                        service_combo.addItem(service_label(native), native)
                    service_combo.setCurrentIndex(choices.index(old_service))
                    service_combo.currentIndexChanged.connect(
                        lambda _i, ei=entry_index, ri=index, cb=service_combo:
                        self._change_service_type(ei, ri, cb))
                    self.table.setCellWidget(position, 5, service_combo)
                if kind == 'C-Freq' and len(row) > 9:
                    attenuation = row[9]
                    values_item = self.table.item(position, 8)
                    values_item.setText(attenuation)
                    atten_combo = QComboBox(self.table)
                    choices = list(ATTENUATOR_CHOICES)
                    if attenuation not in choices:
                        choices.insert(0, attenuation)
                    atten_combo.addItems(choices)
                    atten_combo.setCurrentText(attenuation)
                    atten_combo.currentTextChanged.connect(
                        lambda new_value, ei=entry_index, ri=index, cb=atten_combo:
                        self._change_attenuator(ei, ri, cb, new_value))
                    self.table.setCellWidget(position, 8, atten_combo)
                if kind == 'C-Freq' and len(row) > 10:
                    old_delay = row[10]
                    self.table.item(position, 9).setText(old_delay)
                    delay_combo = QComboBox(self.table)
                    choices = list(DELAY_CHOICES)
                    if old_delay not in choices:
                        choices.insert(0, old_delay)
                    delay_combo.addItems(choices)
                    delay_combo.setCurrentText(old_delay)
                    delay_combo.currentTextChanged.connect(
                        lambda new_value, ei=entry_index, ri=index, cb=delay_combo:
                        self._change_delay(ei, ri, cb, new_value))
                    self.table.setCellWidget(position, 9, delay_combo)
                if kind == 'C-Freq' and len(row) > 11:
                    old_offset = row[11]
                    self.table.item(position, 14).setText(old_offset)
                    offset_combo = QComboBox(self.table)
                    choices = list(VOLUME_OFFSET_CHOICES)
                    if old_offset not in choices:
                        choices.insert(0, old_offset)
                    offset_combo.addItems(choices)
                    offset_combo.setCurrentText(old_offset)
                    offset_combo.currentTextChanged.connect(
                        lambda new_value, ei=entry_index, ri=index, cb=offset_combo:
                        self._change_volume_offset(ei, ri, cb, new_value))
                    self.table.setCellWidget(position, 14, offset_combo)
                if kind == 'C-Freq' and len(row) > 12:
                    old_alert = row[12]
                    self.table.item(position, 10).setText(old_alert)
                    alert_combo = QComboBox(self.table)
                    choices = list(ALERT_TONE_CHOICES)
                    if old_alert not in choices:
                        choices.insert(0, old_alert)  # Preserve unknown imported values.
                    alert_combo.addItems(choices)
                    alert_combo.setCurrentText(old_alert)
                    alert_combo.currentTextChanged.connect(
                        lambda new_value, ei=entry_index, ri=index, cb=alert_combo:
                        self._change_alert_tone(ei, ri, cb, new_value))
                    self.table.setCellWidget(position, 10, alert_combo)
                if kind == 'C-Freq' and len(row) > 13:
                    old_alert_volume = row[13]
                    self.table.item(position, 11).setText(old_alert_volume)
                    volume_combo = QComboBox(self.table)
                    choices = list(ALERT_VOLUME_CHOICES)
                    if old_alert_volume not in choices:
                        choices.insert(0, old_alert_volume)  # Preserve unknown imported values.
                    volume_combo.addItems(choices)
                    volume_combo.setCurrentText(old_alert_volume)
                    volume_combo.currentTextChanged.connect(
                        lambda new_value, ei=entry_index, ri=index, cb=volume_combo:
                        self._change_alert_volume(ei, ri, cb, new_value))
                    self.table.setCellWidget(position, 11, volume_combo)
                if kind == 'C-Freq' and len(row) > 14:
                    original = row[14]
                    self.table.item(position, 12).setText(original)
                    color_combo = QComboBox(self.table)
                    choices = list(ALERT_COLOR_CHOICES)
                    if original not in choices:
                        choices.insert(0, original)  # Keep unknown imported value intact.
                    color_combo.addItems(choices)
                    color_combo.setCurrentText(original)
                    color_combo.currentTextChanged.connect(
                        lambda value, ei=entry_index, ri=index, cb=color_combo:
                        self._change_alert_color(ei, ri, cb, value))
                    self.table.setCellWidget(position, 12, color_combo)
                if kind == 'C-Freq' and len(row) > 15:
                    original = row[15]
                    self.table.item(position, 13).setText(original)
                    pattern_combo = QComboBox(self.table)
                    choices = list(ALERT_PATTERN_CHOICES)
                    if original not in choices:
                        choices.insert(0, original)
                    pattern_combo.addItems(choices)
                    pattern_combo.setCurrentText(original)
                    pattern_combo.currentTextChanged.connect(
                        lambda value, ei=entry_index, ri=index, cb=pattern_combo:
                        self._change_alert_pattern(ei, ri, cb, value))
                    self.table.setCellWidget(position, 13, pattern_combo)
                if kind == 'C-Freq' and len(row) > 16:
                    old_tag = row[16]
                    self.table.item(position, 15).setText(old_tag)
                    tag_combo = QComboBox(self.table)
                    tag_combo.setEditable(True)
                    tag_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
                    tag_combo.setMaxVisibleItems(15)
                    tag_combo.setToolTip('Number Tag: choose Off or type a whole number from 0 to 999, then press Enter.')
                    choices = list(NUMBER_TAG_CHOICES)
                    if old_tag not in choices:
                        # Preserve imported nonstandard values unless explicitly changed.
                        choices.insert(0, old_tag)
                    tag_combo.addItems(choices)
                    tag_combo.setCurrentText(old_tag)
                    tag_combo.setCompleter(None)
                    tag_combo.setValidator(QRegularExpressionValidator(
                        QRegularExpression(r'(?:Off|0|[1-9][0-9]{0,2})'), tag_combo))
                    tag_combo.activated.connect(
                        lambda _i, ei=entry_index, ri=index, cb=tag_combo:
                        self._change_number_tag(ei, ri, cb))
                    tag_combo.lineEdit().editingFinished.connect(
                        lambda ei=entry_index, ri=index, cb=tag_combo:
                        self._change_number_tag(ei, ri, cb))
                    self.table.setCellWidget(position, 15, tag_combo)
                if kind == 'C-Freq' and len(row) > 17:
                    old_priority = row[17]
                    self.table.item(position, 16).setText(old_priority)
                    priority_combo = QComboBox(self.table)
                    choices = list(PRIORITY_CHOICES)
                    if old_priority not in choices:
                        choices.insert(0, old_priority)
                    priority_combo.addItems(choices)
                    priority_combo.setCurrentText(old_priority)
                    priority_combo.currentTextChanged.connect(
                        lambda new_value, ei=entry_index, ri=index, cb=priority_combo:
                        self._change_priority_channel(ei, ri, cb, new_value))
                    self.table.setCellWidget(position, 16, priority_combo)
        finally:
            if self._sort_column >= 0:
                self.table.sortItems(self._sort_column, self._sort_order)
            self.table.setSortingEnabled(True)
            self._refreshing = False

    def _change_tgid_number_tag(self, entry_index, row_index, combo):
        """Validate a typed TGID number tag, then use the common confirmation path."""
        if self._refreshing:
            return
        row = self.workspace.drafts[self.draft_name][entry_index]['records'][row_index]
        if row[0] != 'TGID' or len(row) <= 14:
            return
        previous = row[14]
        chosen = combo.currentText().strip()
        if chosen not in TGID_EDIT_CHOICES[15]:
            QMessageBox.warning(self, 'Invalid Number Tag',
                                'Choose Off or a whole number from 0 to 999.')
            self._restore_tgid_combo(combo, previous)
            return
        if chosen == previous:
            return
        index = combo.findData(chosen)
        if index < 0:
            self._restore_tgid_combo(combo, previous)
            return
        self._refreshing = True
        try:
            combo.setCurrentIndex(index)
        finally:
            self._refreshing = False
        self._change_tgid_setting(entry_index, row_index, combo, 15)

    def _change_tgid_setting(self, entry_index, row_index, combo, column):
        """Confirm a single native TGID field edit with no C-Freq side effects."""
        if self._refreshing or column not in TGID_EDIT_CHOICES:
            return
        row = self.workspace.drafts[self.draft_name][entry_index]['records'][row_index]
        native_index = TGID_VISIBLE_NATIVE[column]
        if row[0] != 'TGID' or len(row) <= native_index:
            return
        previous = row[native_index]
        chosen = combo.currentData()
        if previous == chosen:
            return
        choices = (tuple(SERVICE_TYPE_NAMES) if column == 5
                   else TGID_EDIT_CHOICES[column])
        # Reject choosing any unsupported value except retaining an imported one.
        if chosen not in choices:
            self._restore_tgid_combo(combo, previous)
            return
        field = TGID_FIELD_LABELS[column]
        answer = QMessageBox.question(
            self, 'Confirm talkgroup ' + field + ' change',
            f'Change this trunked talkgroup {field}?\n\n'
            f'Talkgroup: {row[3]}\n'
            f'Current: {tgid_display_value(column, previous)}\n'
            f'New: {tgid_display_value(column, chosen)}',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            self._restore_tgid_combo(combo, previous)
            return
        self.workspace._snapshot()
        row[native_index] = chosen
        self._refreshing = True
        try:
            for r in range(self.table.rowCount()):
                item = self.table.item(r, column)
                if item is not None and item.data(ROLE) == (entry_index, row_index):
                    item.setText(tgid_display_value(column, chosen))
                    break
        finally:
            self._refreshing = False
        self.workspace.refresh_draft()
        self.workspace.status.setText(
            'Talkgroup ' + field + ' changed. Save Scanner Configuration to preserve it.')

    def _restore_tgid_combo(self, combo, original):
        self._refreshing = True
        try:
            index = combo.findData(original)
            if index >= 0:
                combo.setCurrentIndex(index)
            elif combo.isEditable():
                combo.setCurrentText(original)
        finally:
            self._refreshing = False

    def _change_tgid_name(self, cell, row):
        """Validate and confirm only native TGID Name Tag (field 3)."""
        original, proposed = row[3], cell.text().strip()
        if original == proposed:
            return
        def revert():
            self._refreshing = True
            try:
                cell.setText(original)
            finally:
                self._refreshing = False
        if not proposed or len(proposed) > 64 or any(c in proposed for c in '\t\r\n\x00'):
            QMessageBox.warning(self, 'Invalid talkgroup name',
                                'Enter 1–64 characters without tabs or line breaks.')
            revert()
            return
        entries = self.workspace.drafts[self.draft_name]
        meta = entries[0] if entries and entries[0].get('scope') == 'metadata' else {}
        try:
            proposed.encode(meta.get('encoding', 'cp1252'))
        except (UnicodeError, LookupError):
            QMessageBox.warning(self, 'Unsupported characters',
                                'The name cannot be encoded in this Favorites List.')
            revert()
            return
        answer = QMessageBox.question(self, 'Confirm talkgroup name change',
            f'Change this trunked talkgroup name?\n\n'
            f'Current name: {original}\nNew name: {proposed}',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            revert()
            return
        self.workspace._snapshot()
        row[3] = proposed
        self.workspace.refresh_draft()
        self.workspace.status.setText(
            'Talkgroup name changed. Save Scanner Configuration to preserve it.')

    def _changed(self, cell):
        if self._refreshing or cell.column() not in (0, 2): return
        entry_index, row_index = cell.data(ROLE)
        row = self.workspace.drafts[self.draft_name][entry_index]['records'][row_index]
        if row[0] == 'TGID' and cell.column() == 0 and len(row) > 3:
            self._change_tgid_name(cell, row)
            return
        if row[0] != 'C-Freq' or len(row) <= 3: return
        if cell.column() == 2:
            self._change_frequency(cell, row)
            return
        old, new = row[3], cell.text().strip()
        if old == new: return
        def revert():
            self._refreshing = True
            try: cell.setText(old)
            finally: self._refreshing = False
        if not new or len(new) > 64 or any(c in new for c in '\t\r\n\x00'):
            QMessageBox.warning(self, 'Invalid channel name', 'Enter 1–64 characters without tabs or line breaks.')
            revert(); return
        entries = self.workspace.drafts[self.draft_name]
        meta = entries[0] if entries and entries[0].get('scope') == 'metadata' else {}
        try: new.encode(meta.get('encoding','cp1252'))
        except (UnicodeError, LookupError):
            QMessageBox.warning(self, 'Unsupported characters', 'The name cannot be encoded in this Favorites List.')
            revert(); return
        answer = QMessageBox.question(self, 'Confirm channel name change',
            f'Change this conventional channel name?\n\nCurrent name: {old}\nNew name: {new}',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            revert(); return
        self.workspace._snapshot()
        row[3] = new
        self.workspace.refresh_draft()
        self.workspace.status.setText('Channel name changed. Save Scanner Configuration to preserve it.')

    def _change_frequency(self, cell, row):
        """Edit only the verified native C-Freq hertz field (record index 5)."""
        if len(row) <= 5:
            QMessageBox.warning(self, 'Frequency unavailable',
                                'This channel has no native frequency field to edit.')
            self._selected(self.tree.currentItem(), None)
            return
        old_raw = row[5]
        old_display = favorites_record_columns(row)[2]
        entered = cell.text().strip()
        def revert():
            self._refreshing = True
            try: cell.setText(old_display)
            finally: self._refreshing = False
        # Six decimal places represent integer Hz without floating-point rounding.
        if not re.fullmatch(r'\d{2,4}(?:\.\d{1,6})?', entered):
            QMessageBox.warning(self, 'Invalid frequency',
                'Enter a frequency in MHz using up to six decimal places (for example, 155.250000).')
            revert()
            return
        try:
            mhz = Decimal(entered)
            hz = int(mhz * 1000000)
        except (InvalidOperation, ValueError, OverflowError):
            QMessageBox.warning(self, 'Invalid frequency', 'Enter a valid frequency in MHz.')
            revert()
            return
        if not 25000000 <= hz <= 1300000000:
            QMessageBox.warning(self, 'Frequency out of range',
                'The frequency must be between 25.000000 and 1300.000000 MHz.')
            revert()
            return
        new_display = f'{Decimal(hz) / Decimal(1000000):.6f}'
        # No-op, including originally stored decimal-MHz records.
        if old_display == new_display:
            self._refreshing = True
            try: cell.setText(old_display)
            finally: self._refreshing = False
            return
        answer = QMessageBox.question(self, 'Confirm channel frequency change',
            f'Change this conventional channel frequency?\n\n'
            f'Channel: {row[3]}\nCurrent frequency: {old_display or old_raw} MHz\n'
            f'New frequency: {new_display} MHz',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            revert()
            return
        self.workspace._snapshot()
        row[5] = str(hz)
        self._refreshing = True
        try: cell.setText(new_display)
        finally: self._refreshing = False
        self.workspace.refresh_draft()
        self.workspace.status.setText('Channel frequency changed. Save Scanner Configuration to preserve it.')

    def _change_modulation(self, entry_index, row_index, combo, new_mode):
        """Change only the native C-Freq modulation field after confirmation."""
        if self._refreshing:
            return
        row = self.workspace.drafts[self.draft_name][entry_index]['records'][row_index]
        if row[0] != 'C-Freq' or len(row) <= 6:
            return
        old_mode = row[6]
        if old_mode == new_mode:
            return
        answer = QMessageBox.question(
            self, 'Confirm channel modulation change',
            f'Change this conventional channel modulation?\n\n'
            f'Channel: {row[3]}\nCurrent modulation: {old_mode}\n'
            f'New modulation: {new_mode}',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            self._refreshing = True
            try:
                combo.setCurrentText(old_mode)
            finally:
                self._refreshing = False
            return
        self.workspace._snapshot()
        row[6] = new_mode
        self._refreshing = True
        try:
            for r in range(self.table.rowCount()):
                item = self.table.item(r, 4)
                if item is not None and item.data(ROLE) == (entry_index, row_index):
                    item.setText(new_mode)
                    break
        finally:
            self._refreshing = False
        self.workspace.refresh_draft()
        self.workspace.status.setText('Channel modulation changed. Save Scanner Configuration to preserve it.')

    def _change_avoid(self, entry_index, row_index, combo):
        """Confirm and update native channel/talkgroup Avoid field only."""
        if self._refreshing:
            return
        row = self.workspace.drafts[self.draft_name][entry_index]['records'][row_index]
        if row[0] not in ('C-Freq', 'TGID', 'Tgid', 'T-Id') or len(row) <= 4:
            return
        old_value = row[4]
        new_value = combo.currentData()
        if old_value == new_value:
            return
        old_label = AVOID_LABELS.get(old_value, old_value)
        new_label = AVOID_LABELS.get(new_value, new_value)
        answer = QMessageBox.question(
            self, 'Confirm Avoid change',
            f'Change this channel/talkgroup Avoid setting?\n\n'
            f'Channel/Talkgroup: {row[3]}\nCurrent Avoid: {old_label}\n'
            f'New Avoid: {new_label}',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            self._refreshing = True
            try:
                for i in range(combo.count()):
                    if combo.itemData(i) == old_value:
                        combo.setCurrentIndex(i)
                        break
            finally:
                self._refreshing = False
            return
        self.workspace._snapshot()
        row[4] = new_value
        self._refreshing = True
        try:
            for r in range(self.table.rowCount()):
                item = self.table.item(r, 6)
                if item is not None and item.data(ROLE) == (entry_index, row_index):
                    item.setText(service_label(new_value))
                    break
        finally:
            self._refreshing = False
        self.workspace.refresh_draft()
        self.workspace.status.setText('Avoid setting changed. Save Scanner Configuration to preserve it.')

    def _change_attenuator(self, entry_index, row_index, combo, new_value):
        """Confirm offline conventional-channel attenuator changes (C-Freq index 9)."""
        if self._refreshing:
            return
        row = self.workspace.drafts[self.draft_name][entry_index]['records'][row_index]
        if row[0] != 'C-Freq' or len(row) <= 9:
            return
        old_value = row[9]
        if old_value == new_value:
            return
        answer = QMessageBox.question(
            self, 'Confirm attenuator change',
            f'Change this conventional channel attenuator?\n\n'
            f'Channel: {row[3]}\nCurrent attenuator: {old_value}\n'
            f'New attenuator: {new_value}',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            self._refreshing = True
            try:
                combo.setCurrentText(old_value)
            finally:
                self._refreshing = False
            return
        self.workspace._snapshot()
        row[9] = new_value
        self._refreshing = True
        try:
            for r in range(self.table.rowCount()):
                item = self.table.item(r, 8)
                if item is not None and item.data(ROLE) == (entry_index, row_index):
                    item.setText(service_label(new_value))
                    break
        finally:
            self._refreshing = False
        self.workspace.refresh_draft()
        self.workspace.status.setText('Attenuator changed. Save Scanner Configuration to preserve it.')

    def _change_delay(self, entry_index, row_index, combo, new_value):
        """Edit the native conventional C-Freq delay (field index 10)."""
        if self._refreshing:
            return
        row = self.workspace.drafts[self.draft_name][entry_index]['records'][row_index]
        if row[0] != 'C-Freq' or len(row) <= 10:
            return
        old_value = row[10]
        if old_value == new_value:
            return
        answer = QMessageBox.question(
            self, 'Confirm channel delay change',
            f'Change this conventional channel delay?\n\n'
            f'Channel: {row[3]}\nCurrent delay: {old_value}\n'
            f'New delay: {new_value}',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            self._refreshing = True
            try:
                combo.setCurrentText(old_value)
            finally:
                self._refreshing = False
            return
        self.workspace._snapshot()
        row[10] = new_value
        self._refreshing = True
        try:
            for r in range(self.table.rowCount()):
                item = self.table.item(r, 9)
                if item is not None and item.data(ROLE) == (entry_index, row_index):
                    item.setText(new_value)
                    break
        finally:
            self._refreshing = False
        self.workspace.refresh_draft()
        self.workspace.status.setText('Channel delay changed. Save Scanner Configuration to preserve it.')

    def _change_volume_offset(self, entry_index, row_index, combo, new_value):
        """Edit native conventional C-Freq volume offset (field index 11)."""
        if self._refreshing:
            return
        row = self.workspace.drafts[self.draft_name][entry_index]['records'][row_index]
        if row[0] != 'C-Freq' or len(row) <= 11:
            return
        old_value = row[11]
        if old_value == new_value:
            return
        answer = QMessageBox.question(
            self, 'Confirm channel volume offset change',
            f'Change this conventional channel volume offset?\n\n'
            f'Channel: {row[3]}\nCurrent volume offset: {old_value}\n'
            f'New volume offset: {new_value}',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            self._refreshing = True
            try:
                combo.setCurrentText(old_value)
            finally:
                self._refreshing = False
            return
        self.workspace._snapshot()
        row[11] = new_value
        self._refreshing = True
        try:
            for r in range(self.table.rowCount()):
                item = self.table.item(r, 13)
                if item is not None and item.data(ROLE) == (entry_index, row_index):
                    item.setText(new_value)
                    break
        finally:
            self._refreshing = False
        self.workspace.refresh_draft()
        self.workspace.status.setText('Channel volume offset changed. Save Scanner Configuration to preserve it.')

    def _change_alert_tone(self, entry_index, row_index, combo, new_value):
        """Edit only the native conventional C-Freq Alert Tone (field 12)."""
        if self._refreshing:
            return
        row = self.workspace.drafts[self.draft_name][entry_index]['records'][row_index]
        if row[0] != 'C-Freq' or len(row) <= 12:
            return
        old_value = row[12]
        if old_value == new_value:
            return
        # An unrecognized original value may appear in the dropdown for display,
        # but only specification-supported values can be written as new edits.
        if new_value not in ALERT_TONE_CHOICES:
            self._refreshing = True
            try:
                combo.setCurrentText(old_value)
            finally:
                self._refreshing = False
            return
        answer = QMessageBox.question(
            self, 'Confirm channel Alert Tone change',
            f'Change this conventional channel Alert Tone?\n\n'
            f'Channel: {row[3]}\nCurrent Alert Tone: {old_value}\n'
            f'New Alert Tone: {new_value}',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            self._refreshing = True
            try:
                combo.setCurrentText(old_value)
            finally:
                self._refreshing = False
            return
        self.workspace._snapshot()
        row[12] = new_value
        self._refreshing = True
        try:
            for r in range(self.table.rowCount()):
                item = self.table.item(r, 10)
                if item is not None and item.data(ROLE) == (entry_index, row_index):
                    item.setText(new_value)
                    break
        finally:
            self._refreshing = False
        self.workspace.refresh_draft()
        self.workspace.status.setText('Channel Alert Tone changed. Save Scanner Configuration to preserve it.')

    def _change_alert_volume(self, entry_index, row_index, combo, new_value):
        """Edit only native C-Freq Alert Volume, zero-based field 13."""
        if self._refreshing:
            return
        row = self.workspace.drafts[self.draft_name][entry_index]['records'][row_index]
        if row[0] != 'C-Freq' or len(row) <= 13:
            return
        old_value = row[13]
        if old_value == new_value:
            return
        if new_value not in ALERT_VOLUME_CHOICES:
            self._refreshing = True
            try:
                combo.setCurrentText(old_value)
            finally:
                self._refreshing = False
            return
        answer = QMessageBox.question(
            self, 'Confirm channel Alert Volume change',
            f'Change this conventional channel Alert Volume?\n\n'
            f'Channel: {row[3]}\nCurrent Alert Volume: {old_value}\n'
            f'New Alert Volume: {new_value}',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            self._refreshing = True
            try:
                combo.setCurrentText(old_value)
            finally:
                self._refreshing = False
            return
        self.workspace._snapshot()
        row[13] = new_value
        self._refreshing = True
        try:
            for r in range(self.table.rowCount()):
                item = self.table.item(r, 11)
                if item is not None and item.data(ROLE) == (entry_index, row_index):
                    item.setText(new_value)
                    break
        finally:
            self._refreshing = False
        self.workspace.refresh_draft()
        self.workspace.status.setText('Channel Alert Volume changed. Save Scanner Configuration to preserve it.')

    def _change_audio_option(self, entry_index, row_index, button):
        """Edit native C-Freq field 7 only after dialog acceptance and confirmation."""
        if self._refreshing:
            return
        row = self.workspace.drafts[self.draft_name][entry_index]['records'][row_index]
        if row[0] != 'C-Freq' or len(row) <= 7:
            return
        old_value = row[7]
        dialog = AudioOptionDialog(old_value, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_value = dialog.selected_native_value()
        if new_value == old_value:
            return
        answer = QMessageBox.question(
            self, 'Confirm channel Audio Option change',
            f'Change this conventional channel Audio Option?\n\n'
            f'Channel: {row[3]}\nCurrent: {audio_label(old_value)}\n'
            f'New: {audio_label(new_value)}',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.workspace._snapshot()
        row[7] = new_value
        self._refreshing = True
        try:
            button.setText(audio_label(new_value))
            for r in range(self.table.rowCount()):
                item = self.table.item(r, 7)
                if item is not None and item.data(ROLE) == (entry_index, row_index):
                    item.setText(audio_label(new_value))
                    break
        finally:
            self._refreshing = False
        self.workspace.refresh_draft()
        self.workspace.status.setText(
            'Channel Audio Option changed. Save Scanner Configuration to preserve it.')

    def _change_alert_color(self, entry_index, row_index, combo, new_value):
        """Edit only conventional native C-Freq Alert Color field 14."""
        if self._refreshing:
            return
        row = self.workspace.drafts[self.draft_name][entry_index]['records'][row_index]
        if row[0] != 'C-Freq' or len(row) <= 14:
            return
        old_value = row[14]
        if old_value == new_value:
            return
        if new_value not in ALERT_COLOR_CHOICES:
            self._refreshing = True
            try:
                combo.setCurrentText(old_value)
            finally:
                self._refreshing = False
            return
        answer = QMessageBox.question(
            self, 'Confirm channel Alert Color change',
            f'Change this conventional channel Alert Color?\n\n'
            f'Channel: {row[3]}\nCurrent Alert Color: {old_value}\n'
            f'New Alert Color: {new_value}',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            self._refreshing = True
            try:
                combo.setCurrentText(old_value)
            finally:
                self._refreshing = False
            return
        self.workspace._snapshot()
        row[14] = new_value
        self._refreshing = True
        try:
            for r in range(self.table.rowCount()):
                item = self.table.item(r, 12)
                if item is not None and item.data(ROLE) == (entry_index, row_index):
                    item.setText(new_value)
                    break
        finally:
            self._refreshing = False
        self.workspace.refresh_draft()
        self.workspace.status.setText('Channel Alert Color changed. Save Scanner Configuration to preserve it.')

    def _change_alert_pattern(self, entry_index, row_index, combo, new_value):
        """Edit only conventional native C-Freq Alert Pattern field 15."""
        if self._refreshing:
            return
        row = self.workspace.drafts[self.draft_name][entry_index]['records'][row_index]
        if row[0] != 'C-Freq' or len(row) <= 15:
            return
        old_value = row[15]
        if old_value == new_value:
            return
        if new_value not in ALERT_PATTERN_CHOICES:
            self._refreshing = True
            try:
                combo.setCurrentText(old_value)
            finally:
                self._refreshing = False
            return
        answer = QMessageBox.question(
            self, 'Confirm channel Alert Pattern change',
            f'Change this conventional channel Alert Pattern?\n\n'
            f'Channel: {row[3]}\nCurrent Alert Pattern: {old_value}\n'
            f'New Alert Pattern: {new_value}',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            self._refreshing = True
            try:
                combo.setCurrentText(old_value)
            finally:
                self._refreshing = False
            return
        self.workspace._snapshot()
        row[15] = new_value
        self._refreshing = True
        try:
            for r in range(self.table.rowCount()):
                item = self.table.item(r, 13)
                if item is not None and item.data(ROLE) == (entry_index, row_index):
                    item.setText(new_value)
                    break
        finally:
            self._refreshing = False
        self.workspace.refresh_draft()
        self.workspace.status.setText('Channel Alert Pattern changed. Save Scanner Configuration to preserve it.')

    def _change_number_tag(self, entry_index, row_index, combo):
        """Confirm editing only C-Freq native field 16 (Number Tag)."""
        if self._refreshing or self._tag_confirmation_active:
            return
        row = self.workspace.drafts[self.draft_name][entry_index]['records'][row_index]
        if row[0] != 'C-Freq' or len(row) <= 16:
            return
        old_value = row[16]
        new_value = combo.currentText().strip()
        if new_value == old_value:
            return
        # Opening a confirmation dialog can shift keyboard focus and emit an
        # additional editingFinished signal. Guard it against a second prompt.
        self._tag_confirmation_active = True
        try:
            if not valid_number_tag(new_value):
                QMessageBox.warning(self, 'Invalid Number Tag',
                    'Enter Off or a whole number from 0 to 999 (without leading zeros).')
                self._refreshing = True
                try:
                    combo.setCurrentText(old_value)
                finally:
                    self._refreshing = False
                return
            answer = QMessageBox.question(
                self, 'Confirm channel Number Tag change',
                f'Change this conventional channel Number Tag?\n\n'
                f'Channel: {row[3]}\nCurrent Number Tag: {old_value}\n'
                f'New Number Tag: {new_value}',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                self._refreshing = True
                try:
                    combo.setCurrentText(old_value)
                finally:
                    self._refreshing = False
                return
            self.workspace._snapshot()
            row[16] = new_value
            self._refreshing = True
            try:
                for r in range(self.table.rowCount()):
                    item = self.table.item(r, 14)
                    if item is not None and item.data(ROLE) == (entry_index, row_index):
                        item.setText(new_value)
                        break
            finally:
                self._refreshing = False
            self.workspace.refresh_draft()
            self.workspace.status.setText('Channel Number Tag changed. Save Scanner Configuration to preserve it.')
        finally:
            self._tag_confirmation_active = False

    def _change_priority_channel(self, entry_index, row_index, combo, new_value):
        """Edit native conventional C-Freq priority channel (field index 17)."""
        if self._refreshing:
            return
        row = self.workspace.drafts[self.draft_name][entry_index]['records'][row_index]
        if row[0] != 'C-Freq' or len(row) <= 17:
            return
        old_value = row[17]
        if old_value == new_value:
            return
        answer = QMessageBox.question(
            self, 'Confirm priority channel change',
            f'Change this conventional channel priority setting?\n\n'
            f'Channel: {row[3]}\nCurrent priority: {old_value}\n'
            f'New priority: {new_value}',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            self._refreshing = True
            try:
                combo.setCurrentText(old_value)
            finally:
                self._refreshing = False
            return
        self.workspace._snapshot()
        row[17] = new_value
        self._refreshing = True
        try:
            for r in range(self.table.rowCount()):
                item = self.table.item(r, 15)
                if item is not None and item.data(ROLE) == (entry_index, row_index):
                    item.setText(new_value)
                    break
        finally:
            self._refreshing = False
        self.workspace.refresh_draft()
        self.workspace.status.setText('Priority channel changed. Save Scanner Configuration to preserve it.')

    def _change_service_type(self, entry_index, row_index, combo):
        """Confirm an offline change to native C-Freq service field (index 8)."""
        if self._refreshing:
            return
        row = self.workspace.drafts[self.draft_name][entry_index]['records'][row_index]
        if row[0] != 'C-Freq' or len(row) <= 8:
            return
        old_value = row[8]
        new_value = combo.currentData()
        if old_value == new_value:
            return
        answer = QMessageBox.question(
            self, 'Confirm Service Type change',
            f'Change this conventional channel Service Type?\n\n'
            f'Channel: {row[3]}\nCurrent Service Type: {service_label(old_value)} (ID {old_value})\n'
            f'New Service Type: {service_label(new_value)} (ID {new_value})',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            self._refreshing = True
            try:
                for i in range(combo.count()):
                    if combo.itemData(i) == old_value:
                        combo.setCurrentIndex(i)
                        break
            finally:
                self._refreshing = False
            return
        self.workspace._snapshot()
        row[8] = new_value
        self._refreshing = True
        try:
            for r in range(self.table.rowCount()):
                item = self.table.item(r, 5)
                if item is not None and item.data(ROLE) == (entry_index, row_index):
                    item.setText(service_label(new_value))
                    break
        finally:
            self._refreshing = False
        self.workspace.refresh_draft()
        self.workspace.status.setText('Service Type changed. Save Scanner Configuration to preserve it.')
