# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""RadioReference data as Uniden database records (v0.1.1).

The Database Contents panel, the site/talkgroup and channel selectors and the new-list builder all
work on Uniden master-database records (tab-separated rows such as Trunk, Site, T-Freq, T-Group,
TGID, Conventional, C-Group, C-Freq). This module turns RadioReference replies into rows with the
same layout as the real database rows in test_fixtures, so everything after the panel works the
same way and keeps the same checks. The database ID columns are left blank: favorites lists keep
them blank anyway.

Pure functions, no I/O. Trunked systems: the types with a list confirmed on a real SDS100 — P25,
DMR (one frequency per site, v0.1.2; several, as MotoTrbo, v0.1.3) and NXDN in NEXEDGE format (v0.1.2).
"""
import re

from hpdb_sections import build_sections

NAME_MAX = 64
# Uniden FuncTagId by service-type name (Uniden SDS Series File Specification v2.00). RadioReference's
# service tags use the same names, so tags are matched by name; anything else is "Other".
SERVICE_TYPES = {
    'multi-dispatch': '1', 'law dispatch': '2', 'fire dispatch': '3', 'ems dispatch': '4', 'multi-tac': '6',
    'law tac': '7', 'fire-tac': '8', 'ems-tac': '9', 'interop': '11', 'hospital': '12', 'ham': '13',
    'public works': '14', 'aircraft': '15', 'federal': '16', 'business': '17', 'railroad': '20', 'other': '21',
    'multi-talk': '22', 'law talk': '23', 'fire-talk': '24', 'ems-talk': '25', 'transportation': '26',
    'emergency ops': '29', 'military': '30', 'media': '31', 'schools': '32', 'security': '33',
    'utilities': '34', 'corrections': '37',
}
OTHER = '21'


def _norm(text):
    return re.sub(r'[\s_-]+', ' ', str(text or '')).strip().casefold().replace('tactical', 'tac')


SERVICE_BY_NORM = {_norm(k): v for k, v in SERVICE_TYPES.items()}


def service_type(tags):
    """Uniden FuncTagId for a RadioReference tags list ([{'tagId', 'tagDescr'}])."""
    for tag in tags or []:
        if isinstance(tag, dict):
            value = SERVICE_BY_NORM.get(_norm(tag.get('tagDescr')))
            if value:
                return value
    return OTHER


def clip(name, fallback):
    name = re.sub(r'\s+', ' ', str(name or '')).strip() or fallback
    return name[:NAME_MAX]


def hz(mhz):
    """Hertz text from a RadioReference frequency in MHz ('' if it isn't one)."""
    try:
        value = int(round(float(mhz) * 1_000_000))
    except (TypeError, ValueError):
        return ''
    return str(value) if 25_000_000 <= value <= 1_300_000_000 else ''


def _coord(value):
    try:
        return f'{float(value):.6f}'
    except (TypeError, ValueError):
        return '0.000000'


def _range(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return '0.0'
    return f'{number:.1f}' if number > 0 else '0.0'


def location(item, fallback=None):
    """(lat, lon, range) of a RadioReference item, or the fallback's when it has none."""
    for source in (item, fallback or {}):
        if source and source.get('lat') not in (None, '', 0, '0') and source.get('range') not in (None, '', 0, '0'):
            return _coord(source.get('lat')), _coord(source.get('lon')), _range(source.get('range'))
    return '0.000000', '0.000000', '0.0'


# ---- conventional ------------------------------------------------------------------------------
MODULATION = {'FM': 'FM', 'FMN': 'NFM', 'NFM': 'NFM', 'AM': 'AM', 'AMN': 'AM'}


def modulation(mode_name):
    """'FM', 'NFM', 'AM', or 'AUTO' (digital and anything else; the scanner works it out)."""
    return MODULATION.get(str(mode_name or '').strip().upper(), 'AUTO')


def audio_option(tone, color_code=None):
    """Uniden audio option from a RadioReference tone: 'TONE=C107.2', 'TONE=D023', 'NAC=293', 'ColorCode=1',
    'RAN=1', or '' (none / not understood)."""
    text = str(tone or '').strip().upper()
    m = re.fullmatch(r'(\d{2,3}\.\d)\s*(PL|CTCSS)?', text)
    if m:
        return f'TONE=C{m.group(1)}'
    m = re.fullmatch(r'(\d{3})\s*(DPL|DCS|N)', text) or re.fullmatch(r'D(\d{3})N?', text)
    if m:
        return f'TONE=D{m.group(1)}'
    m = re.fullmatch(r'NAC\s*([0-9A-F]{1,3})', text) or re.fullmatch(r'([0-9A-F]{3})\s*NAC', text)
    if m:
        return f'NAC={m.group(1)}'
    m = re.fullmatch(r'(?:CC|COLOR CODE)\s*(\d{1,2})', text)
    if m:
        return f'ColorCode={int(m.group(1))}'
    m = re.fullmatch(r'RAN\s*(\d{1,2})', text)
    if m:
        return f'RAN={int(m.group(1))}'
    if str(color_code or '').strip().isdigit():
        return f'ColorCode={int(str(color_code).strip())}'
    return ''


def conventional_section(name, groups, area=None, mode_names=None):
    """A conventional 'system' (a county or an agency) as a database section.

    groups: [(subcategory dict with scName/lat/lon/range, [freq dicts]), ...] in RadioReference's order.
    mode_names: {mode id: mode name} when RadioReference gives modes as numbers."""
    mode_names = mode_names or {}
    records = [['Conventional', '', '', clip(name, 'RadioReference'), 'Off', '', 'Conventional'] + [''] * 8]
    for sub, freqs in groups:
        rows = []
        for f in freqs or []:
            frequency = hz(f.get('out'))
            if not frequency:
                continue
            mode = f.get('mode')
            mode_name = mode_names.get(int(mode), '') if str(mode).isdigit() else mode
            label = clip(f.get('descr') or f.get('alpha'), f'{int(frequency) / 1e6:.4f} MHz')
            rows.append(['C-Freq', '', '', label, 'Off', frequency, modulation(mode_name),
                         audio_option(f.get('tone'), f.get('colorCode')), service_type(f.get('tags'))] + [''] * 9)
        if rows:
            lat, lon, rng = location(sub, area)
            records.append(['C-Group', '', '', clip(sub.get('scName'), 'Channels'), 'Off', lat, lon, rng,
                            'Circle', 'Off', 'Global'])
            records.extend(rows)
    sections = build_sections(records)
    return sections[0] if sections and sections[0]['children'] else None


# ---- trunked -----------------------------------------------------------------------------------
def trunk_family(type_description):
    """'p25', 'dmr', 'nxdn' or None (a type lists can't be built for yet) from RadioReference's description."""
    text = str(type_description or '').casefold()
    if 'project 25' in text or 'p25' in text or 'apco' in text:
        return 'p25'
    if any(word in text for word in ('dmr', 'trbo', 'capacity plus', 'connect plus', 'xpt')):
        return 'dmr'
    if 'nxdn' in text or 'nexedge' in text or 'idas' in text:
        return 'nxdn'
    return None


def trunk_type(type_description, sites=None):
    """(Uniden system type, TGID format) or (None, why not). DMR must have one frequency per site and NXDN
    must be NEXEDGE: those are the forms confirmed on a real SDS100."""
    family = trunk_family(type_description)
    if family == 'p25':
        return 'P25Standard', 'IDAS'
    if family == 'dmr':
        counts = [len({hz(f.get('freq')) for f in site.get('siteFreqs') or [] if hz(f.get('freq'))})
                  for site in sites or []]
        counts = [c for c in counts if c]
        if counts and max(counts) == 1:
            return 'DmrOneFrequency', 'IDAS'
        if counts:
            # Several frequencies per site (Capacity Plus, Connect Plus, Tier III): MotoTrbo, which needs every
            # frequency's logical channel number.
            if all(str(f.get('lcn') or '').isdigit() and int(f.get('lcn')) > 0
                   for site in sites for f in site.get('siteFreqs') or [] if hz(f.get('freq'))):
                return 'MotoTrbo', 'NEXEDGE'
            return None, ('a DMR system with several frequencies per site, but RadioReference has no logical channel '
                          'number (LCN) for some of them; the scanner needs them for this kind of system')
        return None, "a DMR system with no site frequencies on RadioReference"
    if family == 'nxdn':
        text = str(type_description or '').casefold()
        if 'idas' in text and 'nexedge' not in text:
            return None, 'an NXDN system in IDAS format. Only NEXEDGE format is supported for now'
        return 'Nxdn', 'NEXEDGE'
    return None, f'a {type_description or "unknown"} system. Lists can be built for P25, DMR and NXDN systems for now'


def talkgroup_row(tg, system_type):
    """A TGID row; DMR talkgroups keep their timeslot (1 or 2) from RadioReference."""
    slot = str(tg.get('tgSlot') or '').strip()
    slot = slot if system_type == 'DmrOneFrequency' and slot in ('1', '2') else 'Any'
    return (['TGID', '', '', clip(tg.get('tgDescr') or tg.get('tgAlpha'), f'TGID {tg["tgDec"]}'), 'Off',
             str(tg['tgDec']).strip(), 'ALL', service_type(tg.get('tags'))] + [''] * 8 + [slot])


def trunk_section(details, type_description, sites, categories, talkgroups):
    """A P25 trunked system as a database section, or (None, reason) if it can't be used yet.

    details: getTrsDetails; sites: getTrsSites; categories: getTrsTalkgroupCats; talkgroups: getTrsTalkgroups.
    Fully encrypted talkgroups (enc 2) are left out: the scanner can't play them."""
    name = clip(details.get('sName'), 'RadioReference system')
    system_type, detail = trunk_type(type_description, sites)
    if system_type is None:
        return None, f'{name} is {detail}.'
    tgid_format = detail
    records = [['Trunk', '', '', name, 'Off', '', system_type] + [''] * 14 + [tgid_format]]
    site_count = 0
    for site in sites or []:
        freqs = []
        for sf in site.get('siteFreqs') or []:
            frequency = hz(sf.get('freq'))
            if frequency and all(frequency != r[5] for r in freqs):
                lcn = str(sf.get('lcn') or '0')
                code = str(sf.get('colorCode') if sf.get('colorCode') is not None else '').strip()
                if system_type in ('DmrOneFrequency', 'MotoTrbo'):   # bare colour code, as in the confirmed lists
                    audio = str(int(code)) if code.isdigit() else 'Srch'
                elif system_type == 'Nxdn':                 # RAN, kept by RadioReference as the colour code
                    audio = f'RAN={int(code)}' if code.isdigit() else 'Srch'
                else:
                    audio = 'Srch'
                freqs.append(['T-Freq', '', '', '', '', frequency, lcn if lcn.isdigit() else '0', audio, 'Any'])
        if not freqs:
            continue
        lat, lon, rng = location(site, details)
        nac = str(site.get('nac') or '').strip().upper() if system_type == 'P25Standard' else ''
        records.append(['Site', '', '', clip(site.get('siteDescr'), f'Site {site.get("siteNumber", "")}'.strip()),
                        'Off', lat, lon, rng, 'AUTO', 'Standard', 'Wide', 'Circle', '', '', '', '', '',
                        nac if re.fullmatch(r'[0-9A-F]{1,3}', nac) else 'Srch', 'Global',
                        'TDMA' if str(site.get('tdma_cc') or '0') not in ('0', '', 'False') else 'FDMA'])
        records.extend(freqs)
        site_count += 1
    by_category = {}
    for tg in talkgroups or []:
        if str(tg.get('enc') or '0') == '2':
            continue
        dec = str(tg.get('tgDec') or '').strip()
        if not dec.isdigit():
            continue
        by_category.setdefault(tg.get('tgCid'), []).append(tg)
    department_count = 0
    for cat in categories or []:
        tgs = by_category.pop(cat.get('tgCid'), [])
        if not tgs:
            continue
        lat, lon, rng = location(cat, details)
        records.append(['T-Group', '', '', clip(cat.get('tgCname'), 'Talkgroups'), 'Off', lat, lon, rng, 'Circle', ''])
        for tg in tgs:
            records.append(talkgroup_row(tg, system_type))
        department_count += 1
    leftovers = [tg for tgs in by_category.values() for tg in tgs]
    if leftovers:                                    # talkgroups whose category wasn't listed
        lat, lon, rng = location(details)
        records.append(['T-Group', '', '', 'Other talkgroups', 'Off', lat, lon, rng, 'Circle', ''])
        for tg in leftovers:
            records.append(talkgroup_row(tg, system_type))
        department_count += 1
    if not site_count or not department_count:
        return None, f'{name} has no sites with frequencies or no talkgroups on RadioReference.'
    sections = build_sections(records)
    return sections[0], None
