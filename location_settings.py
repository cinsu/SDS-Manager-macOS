# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Lossless edits of known SDS100 profile.cfg location records; offline only."""
from pathlib import Path
import hashlib, json, os, tempfile
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime, timezone
from scanner_configurations import library_path, verify_configuration

RECORDS = ('CurrentLocation', 'GpsOption', 'InterestingLocation')

def read_location_settings(data):
    lines = data.decode('utf-8').splitlines()
    current = None; gps = None; saved = []
    for line in lines:
        fields = line.split('\t')
        if fields[0] == 'CurrentLocation':
            if len(fields) < 4 or current is not None: raise ValueError('Unexpected CurrentLocation record')
            current = fields[1:4]
        elif fields[0] == 'GpsOption':
            if len(fields) < 3 or gps is not None: raise ValueError('Unexpected GpsOption record')
            gps = fields[1:3]
        elif fields[0] == 'InterestingLocation':
            if len(fields) < 5: raise ValueError('Unexpected InterestingLocation record')
            saved.append(fields[1:5])
    if current is None or gps is None: raise ValueError('Required location records missing')
    return current, gps, saved

def format_coordinate(value, latitude=True):
    """Canonical signed decimal degrees, six fractional digits; reject invalid input."""
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError('Invalid latitude or longitude') from None
    bound = Decimal('90') if latitude else Decimal('180')
    if not number.is_finite() or not -bound <= number <= bound:
        raise ValueError('Latitude or longitude outside allowed limits')
    number = number.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
    if number == 0: number = abs(number)
    return format(number, '.6f')

def valid_coords(lat, lon, radius):
    a, b, r = float(lat), float(lon), float(radius)
    if not (-90 <= a <= 90 and -180 <= b <= 180 and 0 <= r <= 9999):
        raise ValueError('Latitude, longitude or range outside allowed limits')
    return a, b, r

def patch_profile(original, current, gps, saved):
    valid_coords(*current)
    current = [format_coordinate(current[0], True), format_coordinate(current[1], False), current[2]]
    saved = [[entry[0], format_coordinate(entry[1], True), format_coordinate(entry[2], False), entry[3]] for entry in saved]
    if gps[0] not in ('DMS', 'DEG') or gps[1] not in ('4800','9600','19200','38400','57600','115200'):
        raise ValueError('Unsupported GPS format or baud rate; no changes saved')
    if len(saved) > 200: raise ValueError('Too many saved locations')
    for entry in saved:
        if not entry[0].strip() or any(c in entry[0] for c in '\r\n\t') or len(entry[0]) > 60:
            raise ValueError('Invalid saved location name')
        valid_coords(*entry[1:])
    read_location_settings(original)
    newline = b'\r\n' if b'\r\n' in original else b'\n'
    lines = original.splitlines(keepends=True)
    output=[]; inserted=False
    for line in lines:
        name=line.split(b'\t',1)[0].strip().decode('ascii',errors='replace')
        if name == 'CurrentLocation':
            fields=line.rstrip(b'\r\n').decode('utf-8').split('\t')
            fields[1:4]=list(current)
            output.append(('\t'.join(fields)).encode('utf-8')+newline)
        elif name == 'GpsOption':
            fields=line.rstrip(b'\r\n').decode('utf-8').split('\t')
            fields[1:3]=list(gps)
            output.append(('\t'.join(fields)).encode('utf-8')+newline)
        elif name == 'InterestingLocation':
            if not inserted:
                output.extend(('InterestingLocation\t'+'\t'.join(entry)).encode('utf-8')+newline for entry in saved)
                inserted=True
        else: output.append(line)
    if not inserted and saved: raise ValueError('No existing saved-location section; refusing to guess placement')
    return b''.join(output)

def save_profile(folder, payload):
    root=Path(folder).resolve(); library=library_path().resolve()
    if root.parent != library or root.is_symlink(): raise ValueError('Not a local configuration')
    key='BCDx36HP/profile.cfg'; target=root/key; manifest_file=root/'configuration.json'
    manifest=json.loads(manifest_file.read_text(encoding='utf-8'))
    verify_configuration(root,manifest)
    if key not in manifest['files'] or target.is_symlink(): raise ValueError('Profile not registered or unsafe')
    old=target.read_bytes(); read_location_settings(payload)
    if old == payload: return False
    digest=hashlib.sha256(old).hexdigest()
    backup_dir=library.parent/'scanner-configuration-backups'/root.name
    backup_dir.mkdir(parents=True,exist_ok=True)
    backup=backup_dir/(digest+'.cfg')
    if backup.exists():
        if hashlib.sha256(backup.read_bytes()).hexdigest()!=digest: raise ValueError('Backup integrity failure')
    else:
        with backup.open('xb') as f: f.write(old);f.flush();os.fsync(f.fileno())
    new_manifest=dict(manifest);new_manifest['files']=dict(manifest['files'])
    new_manifest['files'][key]={'size':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
    new_manifest['last_saved_utc']=datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix='.location-save-',dir=root) as temp:
        staged=Path(temp); (staged/'profile.cfg').write_bytes(payload)
        (staged/'configuration.json').write_text(json.dumps(new_manifest,indent=2)+'\n',encoding='utf-8')
        os.replace(staged/'profile.cfg',target)
        try: os.replace(staged/'configuration.json',manifest_file)
        except Exception: target.write_bytes(old);raise
    verify_configuration(root)
    return True

# UI-only coordinate representations. Native profile values remain decimal degrees.
import re

def parse_display_coordinate(value, latitude=True, display_format='DEG'):
    raw = str(value).strip()
    if display_format == 'DEG':
        return format_coordinate(raw, latitude)
    if display_format != 'DMS':
        raise ValueError('Unsupported coordinate format')
    match = re.fullmatch(r'''\s*([+-])?\s*(\d{1,3})\s*(?:°|\s)\s*(\d{1,2})\s*(?:['′]|\s)\s*(\d{1,2}(?:\.\d+)?)\s*(?:["″])?\s*([NSEW])?\s*''', raw, re.I)
    if not match:
        raise ValueError('Enter DMS as 82° 32′ 24.76″ W (or -82 32\'24.76)')
    sign, deg, minute, second, hemisphere = match.groups()
    deg, minute, second = int(deg), int(minute), Decimal(second)
    if minute >= 60 or second >= 60:
        raise ValueError('DMS minutes and seconds must be less than 60')
    hemisphere = (hemisphere or '').upper()
    if hemisphere and hemisphere not in (('NS') if latitude else ('EW')):
        raise ValueError('Incorrect hemisphere for coordinate')
    if hemisphere and sign and ((sign == '-' and hemisphere in 'NE') or (sign == '+' and hemisphere in 'SW')):
        raise ValueError('Conflicting sign and hemisphere')
    negative = sign == '-' or hemisphere in 'SW'
    number = Decimal(deg) + Decimal(minute)/60 + second/3600
    if negative: number = -number
    return format_coordinate(number, latitude)

def display_coordinate(value, latitude=True, display_format='DEG'):
    decimal = Decimal(format_coordinate(value, latitude))
    if display_format == 'DEG':
        return format_coordinate(decimal, latitude)
    if display_format != 'DMS':
        raise ValueError('Unsupported coordinate format')
    negative = decimal < 0
    total = (abs(decimal) * 3600).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    degrees = int(total // 3600)
    rest = total - degrees * 3600
    minutes = int(rest // 60)
    seconds = rest - minutes * 60
    hemisphere = ('S' if negative else 'N') if latitude else ('W' if negative else 'E')
    return f'{degrees}° {minutes:02d}′ {seconds:05.2f}″ {hemisphere}'
