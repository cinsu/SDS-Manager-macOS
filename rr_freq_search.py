# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Search RadioReference for a frequency (v0.1.28), for Tools → Search Frequency in RadioReference… and
SDS100 Monitor's "Search Frequency in RadioReference".

- Conventional frequencies: RadioReference's searchCountyFreq for one county, or searchStateFreq for a whole
  state (if that call is refused, each county of the state is searched instead).
- Trunked systems: the site frequencies of the trunked systems in the county, or in the state and all its
  counties, read with getTrsSites. Sites already read stay in memory for this session only.

Nothing here is saved; results are shown and, if you choose, one is added to a Favorites List. No Qt.
"""
import re

import rr_api

TOLERANCE_HZ = 600          # 12.5 kHz channels are listed to 100 Hz; allow for rounding


def hz(value):
    """Hz from '154.2500', 154.25, '154250000' or '154.25 MHz'; None if it isn't a frequency."""
    match = re.search(r'\d+(?:\.\d+)?', str(value or ''))
    if not match:
        return None
    number = float(match.group(0))
    result = number * 1_000_000 if number < 2000 else number
    return int(round(result)) if 25_000_000 <= result <= 1_300_000_000 else None


def mhz_text(value):
    value = hz(value)
    return f'{value / 1_000_000:.4f}' if value else ''


def _items(value):
    """RadioReference sends a one-item list as a plain value (as rr_source._items)."""
    if value is None or value == '':
        return []
    return value if isinstance(value, list) else [value]


def _text(value):
    return '' if value is None else str(value).strip()


class Cancelled(Exception):
    pass


def conventional_rows(found, where_names=None):
    """Result rows from searchCountyFreq / searchStateFreq replies (their fields as RadioReference names them)."""
    rows = []
    for f in _items(found):
        if not isinstance(f, dict):
            continue
        out = hz(f.get('out'))
        if not out:
            continue
        where = ''
        for key, kind in (('ctid', 'county'), ('aid', 'agency'), ('stid', 'state')):
            ident = _text(f.get(key))
            if ident and ident != '0':
                where = (where_names or {}).get((kind, ident)) or ''
                if where:
                    break
        rows.append({'type': 'Conventional', 'name': _text(f.get('alpha')) or _text(f.get('descr')),
                     'description': _text(f.get('descr')), 'where': where, 'frequency': out,
                     'tone': _text(f.get('tone')), 'mode': _text(f.get('mode')),
                     'input': hz(f.get('in')) or 0, 'tags': _text(f.get('tags'))})
    return rows


def search_conventional(browser, mhz, tone='', stid=None, ctid=None, cancel=None):
    """Conventional matches in the county (ctid) or across the state (stid)."""
    client = browser.client
    names = {}
    if stid:
        names.update({('county', str(c)): f'{n} County' for c, n in browser.counties(stid)})
    if ctid:
        info = browser.county(ctid)
        names[('county', str(ctid))] = f'{info.get("countyName", "")} County'.strip()
        rows = conventional_rows(client.search_county_freq(ctid, mhz, tone), names)
        for row in rows:
            row['where'] = row['where'] or names[('county', str(ctid))]
        return rows
    try:
        return conventional_rows(client.search_state_freq(stid, mhz, tone), names)
    except rr_api.RRError:
        rows = []                                        # fall back to every county, one at a time
        for county, name in browser.counties(stid):
            if cancel and cancel():
                raise Cancelled()
            for row in conventional_rows(client.search_county_freq(county, mhz, tone), names):
                row['where'] = row['where'] or f'{name} County'
                rows.append(row)
        return rows


def trunked_systems(browser, stid=None, ctid=None):
    """[(sid, name)] of the trunked systems in a county, or in a state and all its counties."""
    infos = [browser.county(ctid)] if ctid else [browser.state(stid)] + [browser.county(c)
                                                                          for c, _n in browser.counties(stid)]
    seen = {}
    for info in infos:
        for trs in _items((info or {}).get('trsList')):
            if isinstance(trs, dict) and str(trs.get('sid', '')).isdigit():
                seen.setdefault(int(trs['sid']), _text(trs.get('sName')) or str(trs['sid']))
    return sorted(seen.items(), key=lambda s: s[1].casefold())


def site_rows(system_name, sites, wanted_hz):
    rows = []
    for site in _items(sites):
        if not isinstance(site, dict):
            continue
        for f in _items(site.get('siteFreqs')):
            if not isinstance(f, dict):
                continue
            value = hz(f.get('freq'))
            if value and abs(value - wanted_hz) <= TOLERANCE_HZ:
                use = _text(f.get('use'))
                extra = [f'LCN {f["lcn"]}' if _text(f.get('lcn')) else '',
                         {'a': 'control', 'd': 'alternate control'}.get(use.lower(), use)]
                nac = _text(site.get('nac'))
                color = _text(f.get('colorCode'))
                rows.append({'type': 'Trunked site', 'name': system_name,
                             'description': ' · '.join(p for p in extra if p),
                             'where': f'{system_name} › {_text(site.get("siteDescr")) or "site"}',
                             'frequency': value,
                             'tone': f'NAC {nac}' if nac and nac != '0' else (f'CC {color}' if color else ''),
                             'mode': '', 'input': 0, 'tags': ''})
    return rows


def search_trunked(browser, mhz, stid=None, ctid=None, progress=None, cancel=None):
    """Site frequencies of the area's trunked systems that match. progress(done, total) is called as it goes."""
    wanted = hz(mhz)
    systems = trunked_systems(browser, stid, ctid)
    rows = []
    for number, (sid, name) in enumerate(systems):
        if cancel and cancel():
            raise Cancelled()
        if progress:
            progress(number, len(systems))
        sites = browser._get(('sites', sid), lambda s=sid: browser.client.trs_sites(s))
        rows += site_rows(name, sites, wanted)
    if progress:
        progress(len(systems), len(systems))
    return rows


def name_modes(browser, rows):
    """RadioReference gives modes as numbers (getMode names them)."""
    numbers = [{'mode': r['mode']} for r in rows if r['mode'].isdigit()]
    if numbers:
        names = browser.mode_names(numbers)
        for row in rows:
            if row['mode'].isdigit():
                row['mode'] = names.get(int(row['mode']), row['mode'])
    return rows


def search(browser, mhz, tone='', stid=None, ctid=None, trunked=True, progress=None, cancel=None):
    """Everything that matches, conventional first. Raises ValueError for a frequency that isn't one."""
    if not hz(mhz):
        raise ValueError('Enter a frequency between 25 and 1300 MHz.')
    if not (stid or ctid):
        raise ValueError('Choose a state (and county) first.')
    rows = name_modes(browser, search_conventional(browser, f'{hz(mhz) / 1e6:.5f}', tone,
                                                    stid if not ctid else None, ctid, cancel))
    if trunked:
        rows += search_trunked(browser, mhz, stid if not ctid else None, ctid, progress, cancel)
    return rows


def request_for(row):
    """The add-to-list request (monitor_link layout) for a conventional result."""
    modulation = row.get('mode', '').upper()
    return {'system': '', 'department': row.get('where', ''), 'channel': row.get('name', '')[:64],
            'frequency': f'{row["frequency"] / 1e6:.6f}', 'tgid': '', 'action': 'add', 'source': 'rr',
            'modulation': modulation if modulation in ('FM', 'NFM', 'AM') else 'AUTO',
            'tone': re.sub(r'\s*(PL|DPL|NAC|CSQ)\s*$', '', row.get('tone', ''), flags=re.I) if row.get('tone') else ''}
