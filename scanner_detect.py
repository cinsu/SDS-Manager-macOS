# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Read-only detection and summary of a mounted SDS100 SD card.  Never writes.

Detection only recognises a mounted FAT volume with a BCDx36HP folder.  It is a convenience for filling in
the Scanner panel and pre-selecting folders; every write path still checks the USB identity itself.
"""
from datetime import datetime
from pathlib import Path
import shutil

import mac_platform

FAT_TYPES = ('vfat', 'msdos', 'exfat', 'fuseblk')


def _unescape(path):
    return path.replace('\\040', ' ').replace('\\011', '\t').replace('\\134', '\\')


def mounts(proc='/proc/mounts'):
    """[(device, mountpoint, fstype)] from /proc/mounts (macOS: from `mount`)."""
    if mac_platform.IS_MAC and proc == '/proc/mounts':
        return mac_platform.mounts()
    found = []
    try:
        for line in Path(proc).read_text(encoding='utf-8', errors='replace').splitlines():
            parts = line.split()
            if len(parts) >= 3:
                found.append((_unescape(parts[0]), _unescape(parts[1]), parts[2]))
    except OSError:
        pass
    return found


def find_scanners(preferred_folder='', proc='/proc/mounts'):
    """Mount points holding a BCDx36HP folder, those under preferred_folder first."""
    hits = []
    for device, mountpoint, fstype in mounts(proc):
        if fstype not in FAT_TYPES or not device.startswith('/dev/'):
            continue
        root = Path(mountpoint)
        try:
            if (root / 'BCDx36HP').is_dir() and not (root / 'BCDx36HP').is_symlink():
                hits.append({'mountpoint': mountpoint, 'device': device, 'fstype': fstype})
        except OSError:
            continue
    if preferred_folder:
        pref = preferred_folder.rstrip('/') + '/'
        hits.sort(key=lambda h: not (h['mountpoint'] + '/').startswith(pref))
    return hits


def _read_first(path, tag):
    try:
        with open(path, 'rb') as stream:
            for raw in stream.read(65536).decode('cp1252', 'replace').splitlines():
                fields = raw.split('\t')
                if fields[0] == tag:
                    return fields
    except OSError:
        pass
    return None


def database_date(root):
    """DateModified of the card's hpdb.cfg as a datetime, or None."""
    fields = _read_first(Path(root) / 'BCDx36HP' / 'HPDB' / 'hpdb.cfg', 'DateModified')
    if fields and len(fields) > 1:
        try:
            return datetime.strptime(fields[1].strip(), '%m/%d/%Y %H:%M:%S')
        except ValueError:
            return None
    return None


def summarize(mountpoint):
    """Facts about the card for the Scanner panel (model, firmware, database date, free space, list count)."""
    root = Path(mountpoint)
    info = {'mountpoint': str(root), 'model': None, 'firmware': None, 'database_date': None,
            'free_bytes': None, 'total_bytes': None, 'favorites_lists': None, 'warnings': []}
    inf = _read_first(root / 'BCDx36HP' / 'scanner.inf', 'Scanner')
    if inf and len(inf) > 3:
        info['model'] = inf[1].strip() or None
        info['firmware'] = inf[3].strip() or None
    else:
        info['warnings'].append('scanner.inf not found or unreadable')
    info['database_date'] = database_date(root)
    if info['database_date'] is None:
        info['warnings'].append('no database date (HPDB/hpdb.cfg missing)')
    try:
        usage = shutil.disk_usage(root)
        info['free_bytes'], info['total_bytes'] = usage.free, usage.total
    except OSError:
        info['warnings'].append('free space unavailable')
    try:
        info['favorites_lists'] = len(list((root / 'BCDx36HP' / 'favorites_lists').glob('f_[0-9]*.hpd')))
    except OSError:
        pass
    return info


def local_database_date(version_folder):
    """DateModified of a rebuilt local database folder."""
    fields = _read_first(Path(version_folder) / 'hpdb.cfg', 'DateModified')
    if fields and len(fields) > 1:
        try:
            return datetime.strptime(fields[1].strip(), '%m/%d/%Y %H:%M:%S')
        except ValueError:
            return None
    return None


def human_bytes(n):
    if n is None:
        return 'unknown'
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024 or unit == 'TB':
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024
