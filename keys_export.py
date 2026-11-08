# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Keys & Tags to and from a spreadsheet, and a printable key card (v0.1.11).

The spreadsheet (LibreOffice Calc .ods, or .xlsx) has one sheet per level with the quick keys and number
tags in yellow cells, check columns that flag a number used twice in the same set, and a 00-99 map of
Favorites List keys and tags. A hidden Ref column ties each row back to the configuration, so edits made
in Calc can be brought back into Keys & Tags (shown as changes to Apply, never written straight away).

Needs openpyxl (Ubuntu: python3-openpyxl); .ods goes through LibreOffice (soffice) when it is installed.
"""
import html
import shutil
import subprocess
import tempfile
from pathlib import Path

import keys_model as km

SHEETS = {'list': 'Favorites Lists', 'system': 'Systems', 'department': 'Departments', 'channel': 'Channels'}


class ExportError(RuntimeError):
    """Plain-words reason the spreadsheet can't be written or read."""


def _openpyxl():
    try:
        import openpyxl
        return openpyxl
    except ImportError:
        raise ExportError('Spreadsheets need the openpyxl module. Install it with:\n'
                          '  sudo apt install python3-openpyxl') from None


def soffice():
    return shutil.which('soffice') or shutil.which('libreoffice')


def ref_text(item):
    return ':'.join(str(p) for p in item['ref'])


def _path_names(model, item):
    names = []
    node = model.parent(item)
    while node is not None:
        names.append(node['name'])
        node = model.parent(node)
    return list(reversed(names))


def rows_for(model, level, also=()):
    """[(values, ref)] for one sheet, in tree order (also: more levels on the same sheet)."""
    out = []
    for item in model.items:
        kind = item['level']
        if kind != level and kind not in also:
            continue
        up = _path_names(model, item)
        scanned = model.scanned(item)[1] if kind != 'channel' else ''
        key = item['key'] if item['key'] is not None else 'Off'
        tag = item['tag'] if item['tag'] is not None else 'Off'
        if kind == 'list':
            values = [item['name'], 'On' if item.get('monitor') else 'Off', key, tag, scanned]
        elif kind == 'system':
            values = up + [item['name'], key, tag, scanned]
        elif kind == 'department':
            values = up + [item['name'], key, scanned]
        elif kind == 'site':                          # on the Departments sheet (v0.1.22)
            values = up + [item['name'] + ' (site)', key, scanned]
        else:
            values = up + [item['name'], item.get('detail', ''), tag]
        out.append((values, ref_text(item)))
    return out


def write_workbook(model, path, title=''):
    """Write the tracking spreadsheet. path ending in .ods is converted with LibreOffice."""
    openpyxl = _openpyxl()
    from openpyxl.formatting.rule import FormulaRule
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.worksheet.datavalidation import DataValidation
    path = Path(path)
    font, head = 'Arial', Font(name='Arial', bold=True, color='FFFFFF')
    head_fill, input_fill = PatternFill('solid', fgColor='1F3A5F'), PatternFill('solid', fgColor='FFF7CC')
    red, green = PatternFill('solid', fgColor='F8C9C4'), PatternFill('solid', fgColor='D5EDD5')
    side = Side(style='thin', color='C8CCD2')
    box = Border(top=side, bottom=side, left=side, right=side)
    body, blue = Font(name=font, size=10), Font(name=font, size=10, color='0000FF')
    wb = openpyxl.Workbook()

    def sheet(name, heading, note, headers, widths, rows, inputs, checks, limits):
        ws = wb.create_sheet(name)
        ws['A1'], ws['A2'] = heading, note
        ws['A1'].font, ws['A2'].font = Font(name=font, size=14, bold=True), Font(name=font, size=10, italic=True)
        headers = headers + ['Ref (keep)']
        for c, (h, w) in enumerate(zip(headers, widths + [12]), 1):
            cell = ws.cell(4, c, h)
            cell.font, cell.fill, cell.border = head, head_fill, box
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            ws.column_dimensions[cell.column_letter].width = w
        ws.column_dimensions[ws.cell(4, len(headers)).column_letter].hidden = True
        last = max(5, 4 + len(rows))
        for r, (values, ref) in enumerate(rows, 5):
            ws.cell(r, len(headers), ref).font = body
            for c, value in enumerate(values, 1):
                cell = ws.cell(r, c, value)
                cell.border = box
                cell.font = blue if c in inputs else body
                if c in inputs:
                    cell.fill = input_fill
                    cell.alignment = Alignment(horizontal='center')
                    cell.number_format = '00'
        for c, (formula, _scope) in checks.items():
            for r in range(5, last + 1):
                cell = ws.cell(r, c, formula.format(r=r, last=last))
                cell.font, cell.border, cell.alignment = body, box, Alignment(horizontal='center')
            col = ws.cell(4, c).column_letter
            rng = f'{col}5:{col}{last}'
            ws.conditional_formatting.add(rng, FormulaRule(formula=[f'LEFT({col}5,6)="Shared"'], fill=red))
            ws.conditional_formatting.add(rng, FormulaRule(formula=[f'{col}5="OK"'], fill=green))
        for c, top in limits.items():
            col = ws.cell(4, c).column_letter
            dv = DataValidation(type='custom', allow_blank=True, showErrorMessage=True, errorTitle='Not a valid value',
                                error=f'Enter Off or a whole number from 0 to {top}.',
                                formula1=f'OR({col}5="Off",AND(ISNUMBER({col}5),{col}5>=0,{col}5<={top},INT({col}5)={col}5))')
            dv.add(f'{col}5:{col}{last}')
            ws.add_data_validation(dv)
        ws.freeze_panes = 'A5'
        ws.auto_filter.ref = f'A4:{ws.cell(4, len(headers) - 1).column_letter}{last}'
        return ws, last

    def check(col, scope=''):
        same = ''.join(f'{s}$5:{s}${{last}},{s}{{r}},' for s in scope)
        return ('=IF(OR({c}{{r}}="",{c}{{r}}="Off"),"",IF(COUNTIFS({same}{c}$5:{c}${{last}},{c}{{r}})>1,'
                '"Shared – used twice","OK"))').format(c=col, same=same), scope

    lists, l_last = sheet('Favorites Lists', 'Favorites Lists — quick keys and number tags',
                          'One set for the whole scanner. Yellow cells are yours to change: a number, or Off.',
                          ['Favorites List', 'Monitor', 'Quick Key (00–99)', 'Number Tag (0–99)', 'Scanning',
                           'Quick key check', 'Number tag check'], [32, 10, 14, 14, 40, 20, 20],
                          rows_for(model, 'list'), {3, 4}, {6: check('C'), 7: check('D')}, {3: 99, 4: 99})
    sheet('Systems', 'Systems — quick keys and number tags', 'One set per Favorites List.',
          ['Favorites List', 'System', 'Quick Key (00–99)', 'Number Tag (0–99)', 'Scanning', 'Quick key check',
           'Number tag check'], [30, 30, 14, 14, 40, 20, 20], rows_for(model, 'system'), {3, 4},
          {6: check('C', 'A'), 7: check('D', 'A')}, {3: 99, 4: 99})
    sheet('Departments', 'Departments and sites — quick keys',
          'One set per system, shared by its departments and sites. They have no number tags.',
          ['Favorites List', 'System', 'Department / Site', 'Quick Key (00–99)', 'Scanning', 'Quick key check'],
          [28, 26, 40, 14, 40, 20], rows_for(model, 'department', ('site',)), {4}, {6: check('D', 'AB')}, {4: 99})
    sheet('Channels', 'Channels and talkgroups — number tags', 'One set per system (0–999).',
          ['Favorites List', 'System', 'Department', 'Channel / Talkgroup', 'Frequency / ID', 'Number Tag (0–999)',
           'Number tag check'], [24, 22, 32, 32, 16, 14, 20], rows_for(model, 'channel'), {6},
          {7: check('F', 'AB')}, {6: 999})
    # the 00-99 map of Favorites List numbers
    ws = wb.create_sheet('Key & Tag Map', 1)
    ws['A1'], ws['A1'].font = 'Favorites List quick keys and number tags, 00–99', Font(name=font, size=14, bold=True)
    names, keys, tags = (f"'Favorites Lists'!${c}$5:${c}${l_last}" for c in 'ACD')
    for c, (h, w) in enumerate(zip(['Number', 'Quick key: list', 'Lists', 'Key', 'Number tag: list', 'Lists', 'Tag'],
                                   [10, 32, 8, 10, 32, 8, 10]), 1):
        cell = ws.cell(3, c, h)
        cell.font, cell.fill, cell.border = head, head_fill, box
        ws.column_dimensions[cell.column_letter].width = w
    for n in range(100):
        r = 4 + n
        for c, value in enumerate([n, f'=IFERROR(INDEX({names},MATCH(A{r},{keys},0)),"")', f'=COUNTIF({keys},A{r})',
                                   f'=IF(C{r}=0,"Free",IF(C{r}=1,"Used","Shared"))',
                                   f'=IFERROR(INDEX({names},MATCH(A{r},{tags},0)),"")', f'=COUNTIF({tags},A{r})',
                                   f'=IF(F{r}=0,"Free",IF(F{r}=1,"Used","Shared"))'], 1):
            cell = ws.cell(r, c, value)
            cell.font, cell.border = body, box
        ws.cell(r, 1).number_format = '00'
    for col in 'DG':
        ws.conditional_formatting.add(f'{col}4:{col}103', FormulaRule(formula=[f'{col}4="Shared"'], fill=red))
        ws.conditional_formatting.add(f'{col}4:{col}103', FormulaRule(formula=[f'{col}4="Free"'], fill=green))
    ws.freeze_panes = 'A4'
    guide = wb['Sheet']
    guide.title = 'How to Use'
    for r, line in enumerate([
            f'Quick keys and number tags — {title}', '',
            'Yellow cells are yours to change: type a number, or Off. The check columns turn red when two items in '
            'the same set share a number.',
            'Favorites List numbers are one set for the scanner; system numbers one set per list; department keys '
            'and channel number tags one set per system.',
            'Quick key and number tag are separate settings: list quick key 1 is not number tag 1.', '',
            'To bring your changes back: SDS-Manager → Favorites → Keys & Tags… → Read Spreadsheet…. They appear as '
            'changes to check and Apply.',
            "Keep the hidden Ref column and don't add or move rows; rows that no longer match the configuration are "
            'skipped and listed.'], 1):
        guide.cell(r, 1, line).font = Font(name=font, size=14 if r == 1 else 10, bold=r == 1)
    guide.column_dimensions['A'].width = 120
    if path.suffix.lower() != '.ods':
        wb.save(path)
        return path
    office = soffice()
    if not office:
        fallback = path.with_suffix('.xlsx')
        wb.save(fallback)
        return fallback
    with tempfile.TemporaryDirectory() as tmp:
        xlsx = Path(tmp) / (path.stem + '.xlsx')
        wb.save(xlsx)
        _convert(office, xlsx, 'ods', Path(tmp))
        shutil.copyfile(Path(tmp) / (path.stem + '.ods'), path)
    return path


def _convert(office, source, kind, outdir):
    try:
        subprocess.run([office, '--headless', '--convert-to', kind, '--outdir', str(outdir), str(source)],
                       check=True, capture_output=True, timeout=180)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ExportError(f'LibreOffice could not convert the spreadsheet ({exc}).') from None
    if not (Path(outdir) / (Path(source).stem + '.' + kind)).exists():
        raise ExportError('LibreOffice did not write the converted spreadsheet.')


def read_values(path):
    """{ref: {'key': n|None, 'tag': n|None, 'monitor': bool, 'name': str}} from a spreadsheet made here."""
    openpyxl = _openpyxl()
    path = Path(path)
    with tempfile.TemporaryDirectory() as tmp:
        source = path
        if path.suffix.lower() == '.ods':
            office = soffice()
            if not office:
                raise ExportError('Reading .ods needs LibreOffice. Save it as .xlsx in Calc, or install LibreOffice.')
            copy = Path(tmp) / ('sheet' + path.suffix)
            shutil.copyfile(path, copy)
            _convert(office, copy, 'xlsx', Path(tmp))
            source = Path(tmp) / 'sheet.xlsx'
        try:
            wb = openpyxl.load_workbook(source, data_only=True)
        except Exception as exc:                                   # noqa: BLE001 - any unreadable file
            raise ExportError(f'{path.name} could not be read as a spreadsheet ({exc}).') from None
    layout = {'Favorites Lists': (1, {'monitor': 2, 'key': 3, 'tag': 4}),
              'Systems': (2, {'key': 3, 'tag': 4}), 'Departments': (3, {'key': 4}), 'Channels': (4, {'tag': 6})}
    found = {}
    for name, (name_col, cols) in layout.items():
        if name not in wb.sheetnames:
            raise ExportError(f'{path.name} has no {name} sheet; use a spreadsheet made by Keys & Tags.')
        ws = wb[name]
        ref_col = next((c for c in range(1, ws.max_column + 1) if ws.cell(4, c).value == 'Ref (keep)'), None)
        if ref_col is None:
            raise ExportError(f'The {name} sheet has lost its Ref column.')
        for r in range(5, ws.max_row + 1):
            ref = ws.cell(r, ref_col).value
            if not ref:
                continue
            entry = {'name': str(ws.cell(r, name_col).value or '')}
            for field, col in cols.items():
                value = ws.cell(r, col).value
                if field == 'monitor':
                    entry[field] = str(value).strip().lower() == 'on'
                else:
                    entry[field] = _cell_number(value)
            found[str(ref)] = entry
    return found


def _cell_number(value):
    if value is None or str(value).strip().lower() in ('', 'off', 'none', '—', '-'):
        return None
    try:
        number = float(str(value).strip())
    except ValueError:
        return 'bad'
    return int(number) if number == int(number) and number >= 0 else 'bad'


def apply_values(model, values):
    """Put spreadsheet values into the model (as changes to Apply). Returns (changed count, [problems])."""
    by_ref = {ref_text(i): i for i in model.items}
    problems, changed = [], 0
    for ref, entry in values.items():
        item = by_ref.get(ref)
        if item is None or item['name'] + (' (site)' if item['level'] == 'site' else '') != entry['name']:
            problems.append(f'{entry["name"] or ref}: not in the configuration any more (or renamed); skipped.')
            continue
        for field in ('key', 'tag'):
            if field not in entry or (item['key_scope'] if field == 'key' else item['tag_scope']) is None:
                continue
            value = entry[field]
            if value == 'bad':
                problems.append(f'{item["name"]}: the {"quick key" if field == "key" else "number tag"} is not a '
                                'whole number; skipped.')
                continue
            if value != item[field]:
                try:
                    model.set_number(item, field, value)
                    changed += 1
                except ValueError as exc:
                    problems.append(f'{item["name"]}: {exc}')
        if 'monitor' in entry and item['level'] == 'list' and entry['monitor'] != item.get('monitor'):
            model.set_monitor(item, entry['monitor'])
            changed += 1
    return changed, problems


# ---- the key card -------------------------------------------------------------------------------------------
def two(value):
    return '—' if value is None else f'{value:02d}'


def card_html(model, title=''):
    """A one-page reference: Favorites List keys and tags, each monitored list's system and department keys,
    and the number-tag directory."""
    e = html.escape
    rows = []
    rows.append(f'<h2 style="margin:0">Quick keys and number tags</h2><p style="margin:2px 0 8px">{e(title)}</p>')
    rows.append('<h3>Favorites Lists</h3><table cellspacing="0" cellpadding="2" border="1" width="100%">'
                '<tr><th>Key</th><th>Favorites List</th><th>Tag</th><th>Scanning</th></tr>')
    lists = sorted((i for i in model.items if i['level'] == 'list'),
                   key=lambda i: (i['key'] is None, i['key'] if i['key'] is not None else 0, i['name'].casefold()))
    for item in lists:
        if item['key'] is None and item['tag'] is None and not item.get('monitor'):
            continue
        scanned = 'yes' if model.scanned(item)[0] else 'no'
        rows.append(f'<tr><td align="center">{two(item["key"])}'
                    f'</td><td>{e(item["name"])}</td><td align="center">{two(item["tag"])}</td>'
                    f'<td align="center">{scanned}</td></tr>')
    rows.append('</table>')
    for item in lists:
        systems = [s for s in model.children(item['id']) if s['key'] is not None or s['tag'] is not None
                   or any(d['key'] is not None for d in model.children(s['id']))]
        if not systems or not item.get('monitor'):
            continue
        rows.append(f'<h3>{e(item["name"])}</h3><table cellspacing="0" cellpadding="2" border="1" width="100%">'
                    '<tr><th>System key</th><th>System</th><th>Tag</th><th>Department keys</th></tr>')
        for system in systems:
            departments = sorted((d for d in model.children(system['id']) if d['key'] is not None),
                                 key=lambda d: d['key'])
            listing = '; '.join(f'{d["key"]:02d} {e(d["name"])}' + (' (site)' if d['level'] == 'site' else '')
                                for d in departments)
            rows.append(f'<tr><td align="center">{two(system["key"])}</td><td>{e(system["name"])}</td>'
                        f'<td align="center">{two(system["tag"])}</td><td>{listing}</td></tr>')
        rows.append('</table>')
    tagged = [i for i in model.items if i['level'] == 'channel' and i['tag'] is not None]
    if tagged:
        rows.append('<h3>Channel number tags</h3><table cellspacing="0" cellpadding="2" border="1" width="100%">'
                    '<tr><th>Tag</th><th>Channel / talkgroup</th><th>System</th><th>Favorites List</th></tr>')
        for item in sorted(tagged, key=lambda i: (_path_names(model, i)[0], _path_names(model, i)[1], i['tag'])):
            up = _path_names(model, item)
            rows.append(f'<tr><td align="center">{item["tag"]}</td><td>{e(item["name"])}</td><td>{e(up[1])}</td>'
                        f'<td>{e(up[0])}</td></tr>')
        rows.append('</table>')
    return ('<html><head><meta charset="utf-8"><style>body{font-family:Arial,sans-serif;font-size:9pt}'
            'h3{margin:10px 0 3px}th{background:#dde3ea}</style></head><body>' + ''.join(rows) + '</body></html>')
