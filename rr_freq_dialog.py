# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Tools → Search Frequency in RadioReference… (v0.1.28), also opened by SDS100 Monitor.

Searches the county chosen in Database Contents, or the whole state, for a frequency: conventional
frequencies and (optionally) trunked site frequencies. A conventional result can be added to a Favorites List.
The search runs off the window's thread; RadioReference data stays in memory only.
"""
import threading

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

import rr_freq_search

COLUMNS = ('Type', 'Name', 'Where', 'Frequency (MHz)', 'Tone / NAC', 'Mode', 'Details')


class FrequencySearchDialog(QDialog):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setWindowTitle('Search Frequency in RadioReference')
        self.resize(980, 560)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel('Frequency (MHz)'))
        self.frequency = QLineEdit()
        self.frequency.setPlaceholderText('e.g. 154.2500')
        self.frequency.returnPressed.connect(lambda: self.run(whole_state=False))
        row.addWidget(self.frequency)
        row.addWidget(QLabel('Tone (optional)'))
        self.tone = QLineEdit()
        self.tone.setPlaceholderText('e.g. 107.2')
        self.tone.setMaximumWidth(120)
        row.addWidget(self.tone)
        self.trunked = QCheckBox('Include trunked site frequencies')
        self.trunked.setChecked(True)
        row.addWidget(self.trunked)
        layout.addLayout(row)
        # v0.1.29: the window has its own State and County (they start as Database Contents' choice)
        row = QHBoxLayout()
        row.addWidget(QLabel('State'))
        self.state_choice = QComboBox()
        self.state_choice.setMinimumWidth(220)
        self.state_choice.currentIndexChanged.connect(self.state_changed)
        row.addWidget(self.state_choice)
        row.addWidget(QLabel('County'))
        self.county_choice = QComboBox()
        self.county_choice.setMinimumWidth(240)
        self.county_choice.currentIndexChanged.connect(lambda _i: self.show_place())
        row.addWidget(self.county_choice)
        row.addStretch(1)
        layout.addLayout(row)
        self.area = QLabel()
        self.area.setWordWrap(True)
        layout.addWidget(self.area)
        row = QHBoxLayout()
        self.county_button = QPushButton('Search County')
        self.county_button.clicked.connect(lambda: self.run(whole_state=False))
        row.addWidget(self.county_button)
        self.state_button = QPushButton('Search Whole State')
        self.state_button.clicked.connect(lambda: self.run(whole_state=True))
        row.addWidget(self.state_button)
        self.stop_button = QPushButton('Stop')
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop)
        row.addWidget(self.stop_button)
        row.addStretch(1)
        layout.addLayout(row)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        for column, width in enumerate((110, 230, 260, 120, 100, 80)):
            self.table.setColumnWidth(column, width)
        self.table.doubleClicked.connect(lambda _i: self.add_selected())
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.message = QLabel()
        self.message.setWordWrap(True)
        row.addWidget(self.message, 1)
        self.add_button = QPushButton('Add to Favorites List…')
        self.add_button.clicked.connect(self.add_selected)
        row.addWidget(self.add_button)
        close = QPushButton('Close')
        close.clicked.connect(self.close)
        row.addWidget(close)
        layout.addLayout(row)
        self.rows = []
        self.job = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)

    # -- where to search --
    def background(self, work, done):
        """Run work() off the window's thread and call done(result, error) when it ends."""
        box = {}

        def run():
            try:
                box['result'] = work()
            except Exception as exc:                 # network or sign-in problems are shown, not raised
                box['error'] = str(exc)
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        timer = QTimer(self)

        def check():
            if not thread.is_alive():
                timer.stop()
                done(box.get('result'), box.get('error'))
        timer.timeout.connect(check)
        timer.start(120)

    def load_states(self):
        """The states, the first time; then Database Contents' state and county are chosen when it has them."""
        browser = self.main_window.workspace._rr_client_browser()
        if browser is None:
            self.area.setText('Sign in first: Tools → RadioReference Account…')
            return
        if self.state_choice.count() > 1:
            self.follow_database_contents()
            return
        workspace = self.main_window.workspace
        coid = workspace.country_choice.currentData() if workspace.rr_mode() else None
        coid = coid if isinstance(coid, int) else 1                       # 1 = USA on RadioReference
        self.state_choice.blockSignals(True)
        self.state_choice.clear()
        self.state_choice.addItem('Loading states…', None)
        self.state_choice.blockSignals(False)

        def done(states, error):
            self.state_choice.blockSignals(True)
            self.state_choice.clear()
            self.state_choice.addItem('Choose a state…', None)
            for stid, name in states or []:
                self.state_choice.addItem(name, stid)
            self.state_choice.blockSignals(False)
            if error:
                self.message.setText(f'RadioReference: {error}')
            self.follow_database_contents()
        self.background(lambda: browser.states(coid), done)

    def follow_database_contents(self):
        workspace = self.main_window.workspace
        data = workspace.region_choice.currentData() if workspace.rr_mode() else None
        if data and data[0] == 'rr-state':
            index = self.state_choice.findData(data[1])
            if index > 0:
                self.pending_county = workspace.county_choice.currentData()
                if index == self.state_choice.currentIndex():
                    self.choose_pending_county()
                self.state_choice.setCurrentIndex(index)
        self.show_place()

    def choose_pending_county(self):
        ctid = getattr(self, 'pending_county', None)
        if ctid is not None:
            index = self.county_choice.findData(ctid)
            if index >= 0:
                self.county_choice.setCurrentIndex(index)
                self.pending_county = None

    def state_changed(self, _index=None):
        stid = self.state_choice.currentData()
        self.county_choice.blockSignals(True)
        self.county_choice.clear()
        self.county_choice.addItem('Loading counties…' if stid else '—', None)
        self.county_choice.blockSignals(False)
        self.show_place()
        if not stid:
            return
        browser = self.main_window.workspace._rr_client_browser()
        if browser is None:
            return

        def done(counties, error):
            if self.state_choice.currentData() != stid:
                return
            self.county_choice.blockSignals(True)
            self.county_choice.clear()
            self.county_choice.addItem('No county (statewide systems only)', None)
            for ctid, name in counties or []:
                self.county_choice.addItem(f'{name} County', ctid)
            self.county_choice.blockSignals(False)
            if error:
                self.message.setText(f'RadioReference: {error}')
            self.choose_pending_county()
            self.show_place()
            if getattr(self, 'search_when_ready', False) and self.county_choice.currentData():
                self.search_when_ready = False
                self.run(whole_state=False)
        self.background(lambda: browser.counties(stid), done)

    def place(self):
        """(stid, ctid, state name, county name), or None until a state is chosen."""
        stid = self.state_choice.currentData()
        if not stid:
            return None
        ctid = self.county_choice.currentData()
        return (stid, ctid, self.state_choice.currentText(), self.county_choice.currentText() if ctid else '')

    def show_place(self):
        place = self.place()
        if place is None:
            self.area.setText('Choose a state, and a county for Search County.')
        else:
            self.area.setText(f'Search County looks in <b>{place[3] or "— (choose a county)"}</b>; '
                              f'Search Whole State in <b>{place[2]}</b>.')
        busy = self.job is not None
        self.county_button.setEnabled(place is not None and bool(place[1]) and not busy)
        self.state_button.setEnabled(place is not None and not busy)

    def start(self, frequency='', tone=''):
        if frequency:
            self.frequency.setText(rr_freq_search.mhz_text(frequency))
            self.tone.setText(tone)
        self.show()
        self.raise_()
        self.activateWindow()
        self.search_when_ready = bool(frequency)
        self.load_states()
        if frequency and self.job is None and self.place() is not None and self.place()[1] \
                and self.county_choice.count() > 1 and not str(self.county_choice.itemText(0)).startswith('Loading'):
            self.search_when_ready = False
            self.run(whole_state=False)

    # -- searching --
    def run(self, whole_state):
        place = self.place()
        if place is None or self.job is not None:
            self.show_place()
            return
        browser = self.main_window.workspace._rr_client_browser()
        if browser is None:
            self.message.setText('Sign in first: Tools → RadioReference Account…')
            return
        stid, ctid, state, county = place
        if not whole_state and not ctid:
            whole_state = True
        mhz, tone, trunked = self.frequency.text(), self.tone.text().strip(), self.trunked.isChecked()
        if not rr_freq_search.hz(mhz):
            self.message.setText('Enter a frequency between 25 and 1300 MHz.')
            return
        job = {'box': {}, 'progress': (0, 0), 'stop': False,
               'area': state if whole_state else county}

        def progress(done, total):
            job['progress'] = (done, total)

        def work():
            try:
                job['box']['rows'] = rr_freq_search.search(
                    browser, mhz, tone, stid=stid, ctid=None if whole_state else ctid, trunked=trunked,
                    progress=progress, cancel=lambda: job['stop'])
            except rr_freq_search.Cancelled:
                job['box']['error'] = 'Stopped.'
            except Exception as exc:                 # network, sign-in, or an unexpected reply
                job['box']['error'] = str(exc)
        self.job = job
        self.table.setRowCount(0)
        self.message.setText(f'Searching {job["area"]} for {rr_freq_search.mhz_text(mhz)} MHz…')
        job['thread'] = threading.Thread(target=work, daemon=True)
        job['thread'].start()
        self.stop_button.setEnabled(True)
        self.show_place()
        self.timer.start(150)

    def stop(self):
        if self.job is not None:
            self.job['stop'] = True
            self.message.setText('Stopping…')

    def poll(self):
        job = self.job
        if job is None:
            self.timer.stop()
            return
        if job['thread'].is_alive():
            done, total = job['progress']
            if total:
                self.message.setText(f'Searching {job["area"]}: trunked systems {done} of {total}…')
            return
        self.timer.stop()
        self.job = None
        self.stop_button.setEnabled(False)
        self.show_place()
        if 'error' in job['box']:
            self.message.setText(f'RadioReference: {job["box"]["error"]}')
            return
        self.fill(job['box'].get('rows') or [])
        place = self.place()
        self.message.setText(f'{len(self.rows)} match(es) in {job["area"]}.' if self.rows else
                             f'Nothing in RadioReference for this frequency in {job["area"]}.'
                             + (' Try Search Whole State.' if place and job['area'] != place[2] else ''))

    def fill(self, rows):
        self.rows = rows
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = (row['type'], row['name'], row['where'], f'{row["frequency"] / 1e6:.4f}', row['tone'],
                      row['mode'], ' · '.join(p for p in (row['description'] if row['description'] != row['name']
                                                          else '', row['tags']) if p))
            for c, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setData(Qt.ItemDataRole.UserRole, r)
                self.table.setItem(r, c, cell)
        self.table.setSortingEnabled(True)

    # -- adding --
    def add_selected(self):
        cells = self.table.selectedItems()
        if not cells:
            self.message.setText('Select a result first.')
            return
        row = self.rows[cells[0].data(Qt.ItemDataRole.UserRole)]
        if row['type'] != 'Conventional':
            QMessageBox.information(self, 'Add to Favorites List',
                                    f'{row["where"]} is a trunked system. Add it with Database Contents: choose '
                                    'the system there and use Add to Favorites.')
            return
        request = rr_freq_search.request_for(row)
        self.main_window.add_heard_entry(request, f'{row["name"] or "channel"} ({row["frequency"] / 1e6:.4f} MHz)')

    def closeEvent(self, event):
        self.stop()
        super().closeEvent(event)
