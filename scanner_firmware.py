# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""SDS100 firmware: find, download, check and place firmware files on the SD card.

How the SDS100 updates (the same way Sentinel does it): firmware files are put in the card's
BCDx36HP/firmware folder. When the scanner next starts up from its own card (after the USB cable is
unplugged), its protected boot loader checks each file is for this model and that its checksum is good,
installs it, and deletes it. This module never flashes anything itself; it only places verified files.

File names (Uniden):  main firmware  <MODEL>_V1_26_01.bin      (e.g. SDS100_V1_26_01.bin)
                      sub firmware   <MODEL>-SUB_V1_03_15.firm  (e.g. SDS100-SUB_V1_03_15.firm)
Uniden's support page also offers them zipped (SDS100_V1.23.20_Main.zip); zips are opened in memory.

Safety:
  * names must be exactly this scanner's model (SDS100 never matches SDS100E or SDS200);
  * size limits, and an HTML/text check so a saved error page can never be written as firmware;
  * at most one main and one sub file; an older version than the scanner's needs a separate confirmation;
  * the write uses the same USB identity check, SHA-256 staging and post-write verification as every
    other scanner write; leftover firmware files in the folder are listed and can be removed first,
    because the scanner would try to install them too.
"""
import mac_platform  # macOS: full flush to the SD card, no-overwrite rename
from datetime import datetime
import hashlib
import html
import io
import os
from pathlib import Path
import re
import shutil
import ssl
import tempfile
import urllib.error
import urllib.request
import zipfile

BASE = 'https://scannerfw.uniden.com/BCDx36HP/'
FIRMWARE_DIR = 'firmware'
MAX_LISTING = 1_000_000
LIMITS = {'main': (256 * 1024, 32 * 1024 * 1024), 'sub': (4 * 1024, 4 * 1024 * 1024)}
MAX_ZIP = 64 * 1024 * 1024
SPACE_MARGIN = 8 * 1024 * 1024
MODEL_RE = re.compile(r'^[A-Z0-9]{3,12}$')


class FirmwareError(RuntimeError):
    pass


# ---- names and versions ----------------------------------------------------------------------------
def _model_pattern(model):
    """'SDS100' also matches Uniden's server spelling 'SDS-100' (v0.0.9i), never 'SDS100E' or 'SDS200'."""
    return re.sub(r'(?<=[A-Za-z])(?=\d)', '-?', re.escape(model))


def _patterns(model):
    m = _model_pattern(model)
    return {'main': re.compile(rf'^{m}_V(\d+)[._](\d+)[._](\d+)([A-Za-z]?)\.bin$', re.I),
            'sub': re.compile(rf'^{m}-SUB_V(\d+)[._](\d+)[._](\d+)\.firm$', re.I)}


def parse_version(text):
    """'1.26.01' or '1.26.01 ' → (1, 26, 1); None if not a version."""
    m = re.fullmatch(r'\s*(\d+)\.(\d+)\.(\d+)\s*', str(text or ''))
    return tuple(int(x) for x in m.groups()) if m else None


def version_label(version):
    return f'{version[0]}.{version[1]:02d}.{version[2]:02d}' if version else '?'


def parse_name(name, model):
    """{'kind', 'version', 'label', 'name'} if name is firmware for exactly this model, else None."""
    if not MODEL_RE.fullmatch(str(model or '')):
        return None
    base = Path(str(name)).name
    for kind, pattern in _patterns(model).items():
        m = pattern.fullmatch(base)
        if m:
            version = tuple(int(x) for x in m.groups()[:3])
            suffix = m.group(4) if kind == 'main' else ''
            return {'kind': kind, 'version': version, 'label': version_label(version) + (suffix or ''),
                    'name': base}
    return None


def looks_like_firmware(name):
    """Any model's firmware name (for diagnostics only)."""
    return bool(re.search(r'_V\d+[._]\d+[._]\d+[A-Za-z]?\.(bin|firm)$', str(name), re.I))


# ---- the card -------------------------------------------------------------------------------------
def scanner_root(location):
    """The BCDx36HP folder for a mount point or the folder itself; refuses symlinks."""
    selected = Path(location).expanduser().absolute()
    root = selected if selected.name.lower() == 'bcdx36hp' else selected / 'BCDx36HP'
    if selected.is_symlink() or root.is_symlink() or not root.is_dir():
        raise FirmwareError('This is not an SDS100 SD card (no BCDx36HP folder), or it is a symbolic link.')
    return root.resolve(strict=True)


def card_info(location):
    """Model and main firmware from scanner.inf, plus what is already waiting in the firmware folder."""
    root = scanner_root(location)
    model = firmware = None
    try:
        for raw in (root / 'scanner.inf').read_bytes()[:65536].decode('cp1252', 'replace').splitlines():
            fields = raw.split('\t')
            if fields[0] == 'Scanner' and len(fields) > 3:
                model, firmware = fields[1].strip(), fields[3].strip()
                break
    except OSError:
        pass
    if not model or not MODEL_RE.fullmatch(model):
        raise FirmwareError('scanner.inf does not say which model this is, so firmware cannot be matched to it.')
    folder = root / FIRMWARE_DIR
    if folder.is_symlink():
        raise FirmwareError('The card\'s firmware folder is a symbolic link; refusing to use it.')
    files = sorted(p.name for p in folder.iterdir() if p.is_file()) if folder.is_dir() else []
    # Only firmware files are "waiting"; other files there (the scanner's CityTable/ZipTable .dat
    # location data, for example) are left alone (v0.0.9i).
    waiting = [n for n in files if looks_like_firmware(n)]
    return {'root': str(root), 'model': model, 'firmware': firmware, 'version': parse_version(firmware),
            'folder': str(folder), 'waiting': waiting, 'other_files': [n for n in files if n not in waiting]}


# ---- Uniden's update server -------------------------------------------------------------------------
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise FirmwareError('The firmware server tried to redirect; refused.')


def _open(name, username, password, timeout):
    import base64
    if not username or not password or '\n' in username or ':' in username:
        raise FirmwareError('No valid Uniden server credentials.')
    if name and '/' in name:
        raise FirmwareError('Invalid firmware file name.')
    token = base64.b64encode(f'{username}:{password}'.encode('utf-8')).decode('ascii')
    request = urllib.request.Request(BASE + name, headers={
        'Authorization': 'Basic ' + token, 'User-Agent': 'Mozilla/5.0', 'Accept': '*/*'})
    opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    try:
        return opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise FirmwareError(f'Uniden server: HTTP {exc.code}. Credentials were not logged.') from None
    except urllib.error.URLError as exc:
        raise FirmwareError(f'Could not reach Uniden\'s server ({exc.reason}).') from None


def listing_names(text):
    """File names linked from a directory listing page."""
    names = set()
    for href in re.findall(r'href\s*=\s*["\']([^"\']+)["\']', text, re.I):
        name = html.unescape(href).split('?')[0].rstrip('/').split('/')[-1]
        if name:
            names.add(urllib.request.url2pathname(name) if '%' in name else name)
    return names


def discover(model, username, password, timeout=15, fetch=None):
    """Firmware for this model on Uniden's server. fetch(name) → bytes is for tests."""
    if fetch is None:
        def fetch(name):
            with _open(name, username, password, timeout) as response:
                return response.read(MAX_LISTING + 1)
    data = fetch('')
    if len(data) > MAX_LISTING:
        raise FirmwareError('The server listing is unexpectedly large; refused.')
    names = listing_names(data.decode('utf-8', 'replace'))
    files = sorted((p for p in (parse_name(n, model) for n in names) if p),
                   key=lambda p: (p['kind'], p['version']), reverse=True)
    others = sorted(n for n in names if looks_like_firmware(n) and not parse_name(n, model))
    return {'files': files, 'others': others, 'entries': len(names)}


def download(name, model, username, password, directory, timeout=60, fetch=None):
    """Download one firmware file into directory (kept for reuse). Returns a candidate dict."""
    info = parse_name(name, model)
    if info is None:
        raise FirmwareError(f'{name} is not firmware for the {model}.')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / info['name']
    if target.is_file() and not target.is_symlink():
        candidate = candidate_from_bytes(info['name'], target.read_bytes(), model, source=str(target))
        return candidate
    low, high = LIMITS[info['kind']]
    if fetch is None:
        def fetch(n):
            chunks, size = [], 0
            with _open(n, username, password, timeout) as response:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    size += len(block)
                    if size > high:
                        raise FirmwareError('Download larger than any SDS firmware; refused.')
                    chunks.append(block)
            return b''.join(chunks)
    data = fetch(info['name'])
    candidate = candidate_from_bytes(info['name'], data, model, source='Uniden server')
    fd, temp = tempfile.mkstemp(prefix='.fw-', dir=directory)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, target)
    finally:
        Path(temp).unlink(missing_ok=True)
    candidate['source'] = str(target)
    return candidate


# ---- checking files ---------------------------------------------------------------------------------
def candidate_from_bytes(name, data, model, source=''):
    info = parse_name(name, model)
    if info is None:
        raise FirmwareError(f'{Path(name).name} is not firmware for the {model}. SDS100 files are named like '
                            f'{model}_V1_26_01.bin (main) or {model}-SUB_V1_03_15.firm (sub).')
    low, high = LIMITS[info['kind']]
    if not low <= len(data) <= high:
        raise FirmwareError(f'{info["name"]} is {len(data):,} bytes, outside the expected size for '
                            f'{info["kind"]} firmware; refused.')
    # A failed download is usually an HTML/JSON error page. (Plain text alone isn't refused: sub
    # firmware could be a text format such as Intel HEX.)
    head = data[:512].lstrip().lower()
    if head.startswith((b'<!doctype', b'<html', b'<?xml', b'{"', b'pk\x03\x04')) or b'<html' in head:
        raise FirmwareError(f'{info["name"]} is a web page or archive, not firmware (a failed download?); refused.')
    return dict(info, data=data, size=len(data), sha256=hashlib.sha256(data).hexdigest(), source=source)


def load_local(path, model):
    """Candidates from a .bin/.firm file or a Uniden .zip containing them (read in memory, never extracted)."""
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise FirmwareError(f'{path.name} is not a regular file.')
    if path.suffix.lower() == '.zip':
        if path.stat().st_size > MAX_ZIP:
            raise FirmwareError('Zip file too large.')
        found, rejected = [], []
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                base = Path(member.filename).name
                if member.is_dir() or not base.lower().endswith(('.bin', '.firm')):
                    continue
                if parse_name(base, model) is None:
                    rejected.append(base)
                    continue
                if member.file_size > LIMITS[parse_name(base, model)['kind']][1]:
                    raise FirmwareError(f'{base} in the zip is too large; refused.')
                found.append(candidate_from_bytes(base, archive.read(member), model, source=str(path)))
        if not found:
            extra = f' It contains: {", ".join(rejected)}.' if rejected else ''
            raise FirmwareError(f'{path.name} has no firmware for the {model}.{extra}')
        return found
    return [candidate_from_bytes(path.name, path.read_bytes(), model, source=str(path))]


# ---- planning and writing ----------------------------------------------------------------------------
def plan(location, candidates):
    """Read-only check of what would be written. Raises FirmwareError if it must not go ahead."""
    info = card_info(location)
    kinds = {}
    for c in candidates:
        if parse_name(c['name'], info['model']) is None:
            raise FirmwareError(f'{c["name"]} is not firmware for this scanner ({info["model"]}).')
        if c['kind'] in kinds:
            raise FirmwareError('Choose at most one main and one sub firmware file.')
        if hashlib.sha256(c['data']).hexdigest() != c['sha256']:
            raise FirmwareError(f'{c["name"]} changed in memory; refused.')
        kinds[c['kind']] = c
    if not kinds:
        raise FirmwareError('No firmware file chosen.')
    notes, downgrade = [], False
    main = kinds.get('main')
    if main and info['version']:
        if main['version'] < info['version']:
            downgrade = True
            notes.append(f'Main firmware {main["label"]} is OLDER than the scanner\'s {info["firmware"]} (a downgrade).')
        elif main['version'] == info['version']:
            notes.append(f'Main firmware {main["label"]} is the version the scanner already has (reinstall).')
        else:
            notes.append(f'Main firmware {info["firmware"]} → {main["label"]}.')
    elif main:
        notes.append(f'Main firmware {main["label"]} (the scanner\'s current version is unknown).')
    if 'sub' in kinds:
        notes.append(f'Sub firmware {kinds["sub"]["label"]} (the card does not record the current sub version).')
    names = {c['name'] for c in kinds.values()}
    leftovers = [n for n in info['waiting'] if n not in names]
    need = sum(c['size'] for c in kinds.values()) + SPACE_MARGIN
    free = shutil.disk_usage(info['root']).free
    if free < need:
        raise FirmwareError(f'Not enough free space on the card ({free:,} bytes free, {need:,} needed).')
    return {'info': info, 'files': sorted(kinds.values(), key=lambda c: c['kind']), 'notes': notes,
            'downgrade': downgrade, 'leftovers': leftovers}


def execute(location, candidates, remove_leftovers=True, identity=None, log_folder=None):
    """Write the firmware files. identity(root) must return the same value before and during the write
    (the USB check used by every scanner write); it raises if the card isn't the identified SDS100."""
    if identity is None:
        import scanner_first_write as fw
        identity = fw._identity
    first = plan(location, candidates)
    root = Path(first['info']['root'])
    expected = identity(root)
    folder = root / FIRMWARE_DIR
    if folder.is_symlink():
        raise FirmwareError('The firmware folder became a symbolic link; cancelled.')
    folder.mkdir(exist_ok=True)
    removed, written = [], []
    if remove_leftovers:
        for name in first['leftovers']:
            target = folder / name
            if target.is_symlink():
                raise FirmwareError(f'{name} is a symbolic link; cancelled.')
            if identity(root) != expected:
                raise FirmwareError('The scanner changed during the update; cancelled.')
            target.unlink()
            removed.append(name)
    import scanner_first_write as fw
    for c in first['files']:
        if identity(root) != expected:
            raise FirmwareError('The scanner changed during the update; cancelled.')
        destination = folder / c['name']
        fw._stage_and_replace(destination, c['data'], c['sha256'])   # stage, verify, rename, verify again
        written.append(c['name'])
    fw._sync_dir(folder)
    try:
        os.sync()
    except AttributeError:
        pass
    check = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()}
    for c in first['files']:
        if check.get(c['name']) != c['sha256']:
            raise FirmwareError(f'{c["name"]} did not read back correctly from the card.')
    receipt = None
    if log_folder:
        log_folder = Path(log_folder)
        log_folder.mkdir(parents=True, exist_ok=True)
        receipt = log_folder / f'firmware_{datetime.now():%Y%m%d_%H%M%S}.txt'
        receipt.write_text(
            f'Firmware placed on {first["info"]["model"]} at {root}\n'
            f'Scanner firmware before: {first["info"]["firmware"]}\n'
            + ''.join(f'WROTE {c["name"]}  {c["size"]} bytes  sha256 {c["sha256"]}  from {c["source"]}\n'
                      for c in first['files'])
            + ''.join(f'REMOVED leftover {n}\n' for n in removed), encoding='utf-8')
    return {'written': written, 'removed': removed, 'notes': first['notes'], 'folder': str(folder),
            'receipt': str(receipt) if receipt else None, 'model': first['info']['model'],
            'before': first['info']['firmware']}


if mac_platform.IS_MAC:  # macOS fork: clear ._ and .DS_Store clutter before and after card writes
    execute = mac_platform.with_card_cleanup(execute)
