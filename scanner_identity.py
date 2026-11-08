# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Read-only Linux mass-storage/USB provenance report.

Never treat a folder name, scanner.inf, a user-entered path, or a USB product
string as authenticated SDS100 identity. No scanner I/O beyond existing
read-only directory inspection. This module reads Linux mountinfo and sysfs.
"""
from pathlib import Path
import os
import re

_OCTAL_ESCAPE = re.compile(r'\\([0-7]{3})')


def _unescape(value):
    return _OCTAL_ESCAPE.sub(lambda m: chr(int(m.group(1), 8)), value)


def _mounts(path):
    """Return mounted filesystem records; tolerate unavailable procfs."""
    entries = []
    for line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        if ' - ' not in line:
            continue
        before, after = line.split(' - ', 1)
        left, right = before.split(), after.split()
        if len(left) < 5 or len(right) < 2 or ':' not in left[2]:
            continue
        entries.append({'dev':left[2], 'root':_unescape(left[3]),
                        'mountpoint':_unescape(left[4]), 'fs':right[0],
                        'source':_unescape(right[1])})
    return entries


def _is_within(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _read_sysfs(path):
    try:
        return path.read_text(encoding='utf-8', errors='replace').strip()[:200]
    except (OSError, UnicodeError):
        return ''


def _usb_ancestor(device):
    """Find USB descriptors on an ancestor of a block device's sysfs node."""
    for ancestor in (device, *device.parents):
        if (ancestor/'idVendor').is_file() and (ancestor/'idProduct').is_file():
            return ancestor
    return None


def collect_identity_evidence(location, *, mountinfo='/proc/self/mountinfo',
                              sys_dev_block='/sys/dev/block'):
    """Return evidence only. No authorization or write decision is possible."""
    selected = Path(location).expanduser().resolve(strict=True)
    root = selected if selected.name.lower() == 'bcdx36hp' else selected/'BCDx36HP'
    if not root.is_dir():
        raise ValueError('BCDx36HP directory not found.')
    # Only a real mounted block device provides useful USB provenance.
    mounts = [m for m in _mounts(mountinfo)
              if _is_within(root, Path(m['mountpoint']))]
    if not mounts:
        return {'status':'NO_MOUNT', 'reason':'No enclosing mounted filesystem was found.'}
    mount = max(mounts, key=lambda m: len(Path(m['mountpoint']).parts))
    result = {'status':'NO_USB', 'mountpoint':mount['mountpoint'],
              'filesystem':mount['fs'], 'device':mount['dev'],
              'mount_root':mount['root'], 'source':mount['source']}
    # A synthetic bind mount or root filesystem is not scanner proof.
    if mount['root'] != '/':
        result['reason'] = 'Bind/subdirectory mount cannot establish device identity.'
        return result
    if not mount['source'].startswith('/dev/'):
        result['reason'] = 'Mount source is not a local block-device path.'
        return result
    try:
        node = (Path(sys_dev_block)/mount['dev']).resolve(strict=True)
    except (OSError, RuntimeError):
        result['reason'] = 'Linux sysfs block-device association is unavailable.'
        return result
    usb = _usb_ancestor(node)
    if usb is None:
        result['reason'] = 'No USB descriptors were associated with the mounted block device.'
        return result
    vendor = _read_sysfs(usb/'idVendor').lower()
    product = _read_sysfs(usb/'idProduct').lower()
    if not (re.fullmatch(r'[0-9a-f]{4}', vendor) and re.fullmatch(r'[0-9a-f]{4}', product)):
        result['reason'] = 'USB vendor/product identifiers are missing or malformed.'
        return result
    result.update({'status':'USB_CORRELATED', 'vid':vendor, 'pid':product,
                   'manufacturer':_read_sysfs(usb/'manufacturer'),
                   'product_name':_read_sysfs(usb/'product'),
                   'serial_present':bool(_read_sysfs(usb/'serial'))})
    return result


def inspect_scanner_identity(location, **kwargs):
    """Human-readable evidence, deliberately never marks identity authenticated."""
    lines = ['SCANNER USB IDENTITY EVIDENCE — READ ONLY', '']
    try:
        evidence = collect_identity_evidence(location, **kwargs)
    except (OSError, ValueError, RuntimeError) as exc:
        evidence = {'status':'UNAVAILABLE', 'reason':str(exc)}
    status = evidence['status']
    lines.append('Mounted USB device association: ' + (
        'FOUND' if status == 'USB_CORRELATED' else 'NOT ESTABLISHED'))
    for key, label in (('mountpoint','Mount point'),('filesystem','Filesystem'),
                       ('source','Mount source'),('device','Linux block device'),
                       ('vid','USB vendor ID'),('pid','USB product ID'),
                       ('manufacturer','USB manufacturer string'),
                       ('product_name','USB product string')):
        if evidence.get(key):
            lines.append(f'{label}: {evidence[key]}')
    if status == 'USB_CORRELATED':
        lines.append('USB serial descriptor: ' + (
            'present (value withheld)' if evidence['serial_present'] else 'not exposed'))
    if evidence.get('reason'):
        lines.append('Evidence limitation: ' + evidence['reason'])
    lines.extend(['SDS100 model identity: NOT YET VERIFIED',
                  'No trusted SDS100 USB VID/PID allowlist has been established.',
                  'USB strings and scanner.inf are not sufficient proof of scanner model.',
                  'Export authorization: BLOCKED; scanner writes remain disabled.',
                  'No scanner files were modified.'])
    return '\n'.join(lines)
