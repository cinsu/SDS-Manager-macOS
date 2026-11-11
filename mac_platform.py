# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
# macOS support added in a fork by Justin Roberts, 2026.
"""macOS stand-ins for the Linux-only pieces: /proc/mounts, lsblk, /proc/self/mountinfo and /sys.

Read-only, apart from rename_noreplace (Save As) and the full-flush fsync below.
Uses Apple's own tools: /sbin/mount and ioreg (not diskutil, which can stall on a slow card).
On Linux nothing here is used (IS_MAC is False).
"""
from pathlib import Path
import os
import plistlib
import re
import subprocess
import sys

IS_MAC = sys.platform == 'darwin'

_MOUNT_LINE = re.compile(r'^(?P<dev>.+?) on (?P<mp>.+) \((?P<fs>[^,)]+)')
_WHOLE_DISK = re.compile(r'^/dev/(disk\d+)')


def _run(args, timeout=30):
    return subprocess.run(args, capture_output=True, check=True, timeout=timeout).stdout


def mounts():
    """[(device, mountpoint, fstype)] from macOS `mount` (fstype for FAT32 is 'msdos')."""
    found = []
    try:
        text = _run(['/sbin/mount']).decode('utf-8', 'replace')
    except (OSError, subprocess.SubprocessError):
        return found
    for line in text.splitlines():
        m = _MOUNT_LINE.match(line)
        if m:
            found.append((m['dev'], m['mp'], m['fs'].strip()))
    return found


def removable_mounts():
    """Mount points to treat as removable: every disk volume under /Volumes.

    Fails closed: the Mac's own disks mount at / and /System/Volumes, so anything under /Volumes
    (SD cards, USB drives, disk images) is kept out of reach of plain exports."""
    return sorted({mp for dev, mp, _fs in mounts()
                   if dev.startswith('/dev/disk') and mp.startswith('/Volumes/') and Path(mp).is_dir()})


def _containing_mount(root):
    """(device, mountpoint, fstype) of the deepest mount that contains root, or None."""
    root = Path(root)
    best = None
    for dev, mp, fs in mounts():
        p = Path(mp)
        if (root == p or p in root.parents) and (best is None or len(p.parts) > len(Path(best[1]).parts)):
            best = (dev, mp, fs)
    return best


def _usb_tree():
    tree = plistlib.loads(_run(['/usr/sbin/ioreg', '-a', '-r', '-l', '-c', 'IOUSBHostDevice']))
    return tree if isinstance(tree, list) else [tree]


def _device_strings(node):
    """Vendor, product and serial strings of a USB device node (top level or inside 'USB Device Info')."""
    info = node.get('USB Device Info') if isinstance(node.get('USB Device Info'), dict) else {}

    def pick(*keys):
        for source in (node, info):
            for key in keys:
                if source.get(key):
                    return str(source[key])
        return ''
    return (pick('USB Vendor Name', 'kUSBVendorString'), pick('USB Product Name', 'kUSBProductString'),
            pick('USB Serial Number', 'kUSBSerialNumberString'))


def _find_usb_device(nodes, bsd_names):
    """Deepest USB device node (it has a vendor name) whose subtree holds one of `bsd_names`.
    Hubs are shallower than the device; the device's interfaces carry no vendor name."""
    def owns(node):
        if node.get('BSD Name') in bsd_names:
            return True
        return any(owns(c) for c in node.get('IORegistryEntryChildren', []) or [] if isinstance(c, dict))
    best, best_depth = None, -1
    stack = [(n, 0) for n in nodes or []]
    while stack:
        node, depth = stack.pop()
        if not isinstance(node, dict):
            continue
        if ('idVendor' in node and 'idProduct' in node and _device_strings(node)[0]
                and depth > best_depth and owns(node)):
            best, best_depth = node, depth
        stack.extend((c, depth + 1) for c in node.get('IORegistryEntryChildren', []) or [])
    return best


def identity_evidence(root):
    """Same dict shape as scanner_identity.collect_identity_evidence on Linux."""
    found = _containing_mount(root)
    if found is None or found[1] == '/':
        return {'status': 'NO_MOUNT', 'reason': 'No mounted removable volume contains this folder.'}
    device, mountpoint, fs = found
    fs = fs.lower()
    result = {'status': 'NO_USB', 'mountpoint': mountpoint,
              'filesystem': 'vfat' if fs == 'msdos' else fs,   # Linux name, so existing checks match
              'device': device, 'mount_root': '/', 'source': device}
    whole = _WHOLE_DISK.match(device)
    if not whole:
        result['reason'] = 'Mount source is not a local block-device path.'
        return result
    try:
        tree = _usb_tree()
    except (OSError, subprocess.SubprocessError, plistlib.InvalidFileException, ValueError) as exc:
        result['reason'] = f'ioreg could not list USB devices: {exc}'
        return result
    usb = _find_usb_device(tree, {whole.group(1), Path(device).name})
    if usb is None:
        result['reason'] = 'No USB device was found holding the mounted disk.'
        return result
    vendor, product, serial = _device_strings(usb)
    result.update({'status': 'USB_CORRELATED',
                   'vid': f"{int(usb['idVendor']):04x}", 'pid': f"{int(usb['idProduct']):04x}",
                   'manufacturer': vendor[:200], 'product_name': product[:200],
                   'serial_present': bool(serial)})
    return result


# ---- Save As: atomic rename that never replaces an existing folder ------------------------------
RENAME_EXCL = 0x00000004        # <stdio.h>: renamex_np flag, fail if the destination exists


def rename_noreplace(src, dst):
    """macOS equivalent of Linux renameat2(RENAME_NOREPLACE)."""
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    fn = getattr(libc, 'renamex_np', None)
    if fn is None:
        raise OSError('Atomic no-overwrite rename is unavailable; Save As blocked.')
    fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    fn.restype = ctypes.c_int
    if fn(os.fsencode(str(src)), os.fsencode(str(dst)), RENAME_EXCL) != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err), str(dst))


# ---- Durable writes ---------------------------------------------------------------------------
# On macOS, fsync() can return while data is still in the drive's own cache. F_FULLFSYNC asks the
# drive to write it to the media, which is what the program's fsync calls mean on Linux. Every
# fsync in the program goes through this once this module is imported.
if IS_MAC:
    import fcntl
    _plain_fsync = os.fsync

    def _full_fsync(fd):
        if hasattr(fd, 'fileno'):
            fd = fd.fileno()
        try:
            fcntl.fcntl(fd, getattr(fcntl, 'F_FULLFSYNC', 51))
        except OSError:
            _plain_fsync(fd)          # e.g. a folder, or a file system without full flush

    if getattr(os.fsync, '__name__', '') != '_full_fsync':
        os.fsync = _full_fsync
