# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""RadioReference as a source for the Database Contents panel (v0.1.1).

Lists states, counties and systems, and loads a system as a database section (rr_convert). Replies
are kept in memory for this session only, so browsing back and forth doesn't ask again; nothing is
written to disk. Each method makes network calls: run them off the GUI thread.
"""
import rr_convert

COUNTRIES = (('USA', 1), ('Canada', 2))


def _items(value):
    """RadioReference sends one-element arrays as plain values sometimes; always give a list."""
    if value is None or value == '':
        return []
    return value if isinstance(value, list) else [value]


class RRBrowser:
    def __init__(self, client):
        self.client = client
        self.cache = {}

    def _get(self, key, fetch):
        if key not in self.cache:
            self.cache[key] = fetch()
        return self.cache[key]

    # -- places --
    def states(self, coid):
        info = self._get(('country', coid), lambda: self.client.country(coid)) or {}
        states = [(int(s['stid']), str(s.get('stateName') or s.get('stateCode') or s['stid']))
                  for s in _items(info.get('stateList')) if isinstance(s, dict) and str(s.get('stid', '')).isdigit()]
        return sorted(states, key=lambda s: s[1].casefold())

    def state(self, stid):
        return self._get(('state', stid), lambda: self.client.state(stid)) or {}

    def counties(self, stid):
        counties = [(int(c['ctid']), str(c.get('countyName') or c['ctid']))
                    for c in _items(self.state(stid).get('countyList'))
                    if isinstance(c, dict) and str(c.get('ctid', '')).isdigit()]
        return sorted(counties, key=lambda c: c[1].casefold())

    def county(self, ctid):
        return self._get(('county', ctid), lambda: self.client.county(ctid)) or {}

    def systems(self, stid, ctid=None):
        """[(label, kind, key)] for a county, or for the whole state (statewide systems and agencies)."""
        if ctid:
            info = self.county(ctid)
            name = str(info.get('countyName') or 'County')
            entries = [(f'{name} County (conventional)', 'Conventional', ('county', int(ctid)))] \
                if _items(info.get('cats')) else []
        else:
            info = self.state(stid)
            entries = []
        for trs in _items(info.get('trsList')):
            if isinstance(trs, dict) and str(trs.get('sid', '')).isdigit():
                entries.append((str(trs.get('sName') or trs['sid']), 'Trunk', ('trs', int(trs['sid']))))
        for agency in _items(info.get('agencyList')):
            if isinstance(agency, dict) and str(agency.get('aid', '')).isdigit():
                entries.append((str(agency.get('aName') or agency['aid']), 'Conventional',
                                ('agency', int(agency['aid']))))
        return entries

    # -- loading one system --
    def type_description(self, type_id):
        rows = self._get(('trstype', type_id), lambda: _items(self.client.trs_type(type_id)))
        for row in rows:
            if isinstance(row, dict) and str(row.get('sType')) == str(type_id):
                return str(row.get('sTypeDescr') or '')
        return str(rows[0].get('sTypeDescr') or '') if rows and isinstance(rows[0], dict) else ''

    def mode_names(self, freqs):
        names = {}
        for mode in {f.get('mode') for f in freqs if str(f.get('mode', '')).isdigit()}:
            rows = self._get(('mode', int(mode)), lambda m=int(mode): _items(self.client.mode(m)))
            for row in rows:
                if isinstance(row, dict) and str(row.get('mode', '')).isdigit():
                    names[int(row['mode'])] = str(row.get('modeName') or '')
        return names

    def _conventional(self, name, cats, area):
        groups = []
        for cat in _items(cats):
            for sub in _items(cat.get('subcats') if isinstance(cat, dict) else None):
                if isinstance(sub, dict) and str(sub.get('scid', '')).isdigit():
                    freqs = [f for f in _items(self._get(('subcat', int(sub['scid'])),
                                                         lambda s=int(sub['scid']): self.client.subcat_freqs(s)))
                             if isinstance(f, dict)]
                    label = sub.get('scName') or cat.get('cName')
                    groups.append((dict(sub, scName=label), freqs))
        all_freqs = [f for _sub, freqs in groups for f in freqs]
        section = rr_convert.conventional_section(name, groups, area, self.mode_names(all_freqs))
        return (section, None) if section else (None, f'{name} has no frequencies on RadioReference.')

    def load(self, key):
        """(section, None) or (None, why it can't be used)."""
        kind, ident = key
        if kind == 'county':
            info = self.county(ident)
            return self._conventional(f'{info.get("countyName", "County")} County', info.get('cats'), info)
        if kind == 'agency':
            info = self._get(('agency', ident), lambda: self.client.agency(ident)) or {}
            return self._conventional(str(info.get('agencyName') or 'Agency'), info.get('cats'), info)
        if kind == 'trs':
            details = self._get(('trs', ident), lambda: self.client.trs_details(ident)) or {}
            description = self.type_description(details.get('sType')) if str(details.get('sType', '')).isdigit() else ''
            if rr_convert.trunk_family(description) is None:
                return rr_convert.trunk_section(details, description, [], [], [])
            sites = _items(self._get(('sites', ident), lambda: self.client.trs_sites(ident)))
            cats = _items(self._get(('cats', ident), lambda: self.client.trs_talkgroup_cats(ident)))
            tgs = _items(self._get(('tgs', ident), lambda: self.client.trs_talkgroups(ident)))
            for site in sites:
                if isinstance(site, dict):
                    site['siteFreqs'] = _items(site.get('siteFreqs'))
            return rr_convert.trunk_section(details, description, sites, cats, tgs)
        raise ValueError(f'Unknown RadioReference item {key!r}')
