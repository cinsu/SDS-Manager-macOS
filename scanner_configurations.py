# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Local SDS100 configurations, verified import and safeguarded offline edits."""
from pathlib import Path
import hashlib
import ctypes
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone

CONFIG_DIRS = ('favorites_lists', 'HPDB')
CONFIG_FILES = ('profile.cfg', 'app_data.cfg', 'scanner.inf', 'discovery.cfg', 'f_list.cfg')
# Only supported configuration material; never touch firmware, GPS, audio, logs.

def scanner_root(path):
    base = Path(path).expanduser().resolve()
    if base.name.lower() == 'bcdx36hp':
        base = base.parent
    folder = base / 'BCDx36HP'
    if not folder.is_dir() or not (folder / 'favorites_lists').is_dir():
        raise ValueError('Select the scanner drive root containing BCDx36HP/favorites_lists.')
    if not any((folder / x).is_file() for x in ('profile.cfg', 'scanner.inf')):
        raise ValueError('Scanner identification/configuration files were not found.')
    return folder

def library_path():
    return Path.home() / '.local' / 'share' / 'sds100-database-favorites-manager' / 'scanner-configurations'

class ImportCancelled(Exception):
    """The user cancelled an import; staged local files are discarded."""


def import_configuration(scanner_path, name, library=None, progress=None, cancelled=None):
    """Copy a read-only scanner snapshot with file-by-file progress and cancellation.

    progress(phase, completed, total, relative_path) is invoked on the calling
    thread; GUI callers must use a background worker and queued Qt signals.
    """
    def check_cancel():
        if cancelled is not None and cancelled():
            raise ImportCancelled('Import cancelled. No configuration was saved.')

    def notify(phase, completed, total, filename=''):
        if progress is not None:
            progress(phase, completed, total, filename)

    if not name.strip() or len(name) > 90 or any(c in name for c in '/\\\0'):
        raise ValueError('Choose a valid configuration name (up to 90 characters).')
    source = scanner_root(scanner_path)
    library = Path(library) if library else library_path()
    library.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r'[^a-zA-Z0-9_-]+', '-', name.strip()).strip('-')[:70]
    if not slug: raise ValueError('Configuration name must contain letters or numbers.')
    destination = library / slug
    if destination.exists(): raise FileExistsError('A configuration with this name already exists. Choose another name.')
    planned = []
    notify('Scanning scanner configuration', 0, 0)
    for foldername in CONFIG_DIRS:
        origin = source / foldername
        if not origin.is_dir(): continue
        for entry in sorted(origin.rglob('*')):
            check_cancel()
            if entry.is_symlink(): raise ValueError('Scanner contains a symbolic link; import stopped for safety.')
            if not entry.is_file(): continue
            if foldername == 'favorites_lists' and entry.suffix.lower() not in ('.hpd', '.cfg'):
                continue
            planned.append((entry, Path('BCDx36HP') / foldername / entry.relative_to(origin)))
    for filename in CONFIG_FILES:
        origin = source / filename
        if origin.is_symlink(): raise ValueError('Scanner configuration symlink rejected.')
        if origin.is_file(): planned.append((origin, Path('BCDx36HP') / filename))
    if not any(rel.parent == Path('BCDx36HP/favorites_lists') and rel.suffix.lower() == '.hpd'
               for _, rel in planned):
        raise ValueError('No native .hpd Favorites Lists found; import stopped.')
    total = len(planned)
    notify('Copying and verifying', 0, total)
    stage = Path(tempfile.mkdtemp(prefix='.sds100-import-', dir=library))
    try:
        manifest_files = {}
        for index, (origin, relative) in enumerate(planned, 1):
            check_cancel()
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            size = 0
            with origin.open('rb') as source_file, target.open('wb') as dest_file:
                while True:
                    check_cancel()
                    chunk = source_file.read(1024 * 1024)
                    if not chunk: break
                    dest_file.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
            check_cancel()
            copied_hash = hashlib.sha256()
            with target.open('rb') as copied:
                while True:
                    check_cancel()
                    chunk = copied.read(1024 * 1024)
                    if not chunk: break
                    copied_hash.update(chunk)
            if digest.hexdigest() != copied_hash.hexdigest() or size != target.stat().st_size:
                raise ValueError('Imported file failed checksum verification: ' + str(relative))
            manifest_files[str(relative)] = {'size': size, 'sha256': digest.hexdigest()}
            notify('Copying and verifying', index, total, str(relative))
        check_cancel()
        manifest = {'format': 'sds100-configuration-snapshot-v1', 'name': name.strip(),
                    'imported_utc': datetime.now(timezone.utc).isoformat(),
                    'files': manifest_files}
        (stage / 'configuration.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
        check_cancel()
        os.rename(stage, destination)
        # Close the final cancellation race without removing a pre-existing
        # configuration: destination did not exist before this import.
        if cancelled is not None and cancelled():
            shutil.rmtree(destination, ignore_errors=True)
            raise ImportCancelled('Import cancelled. No configuration was saved.')
        notify('Complete', total, total)
        return destination, manifest
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise

def list_configurations(library=None):
    base = Path(library) if library else library_path()
    result = []
    if base.is_dir():
        for file in sorted(base.glob('*/configuration.json')):
            try:
                data = json.loads(file.read_text(encoding='utf-8'))
                if data.get('format') == 'sds100-configuration-snapshot-v1':
                    result.append((file.parent, data))
            except (OSError, ValueError):
                continue
    return result


def delete_local_configuration(folder, library=None):
    """Remove exactly one inactive local configuration; retain external backups/recovery."""
    root = Path(folder).expanduser().resolve()
    base = (Path(library) if library else library_path()).expanduser().resolve()
    if root.parent != base or root == base or root.is_symlink():
        raise ValueError('Only a named local configuration may be deleted.')
    manifest_file = root / 'configuration.json'
    if manifest_file.is_symlink() or not manifest_file.is_file():
        raise ValueError('Configuration manifest missing or unsafe.')
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    if manifest.get('format') != 'sds100-configuration-snapshot-v1':
        raise ValueError('Not a recognized scanner configuration.')
    # Never recursively follow links or remove unexpected linked files.
    if any(entry.is_symlink() for entry in root.rglob('*')):
        raise ValueError('Configuration contains symbolic links; deletion blocked.')
    shutil.rmtree(root)


def rename_local_configuration(folder, new_name):
    """Change only the display name, not the folder or any scanner-native file."""
    root = Path(folder).expanduser().resolve()
    if root.parent != library_path().resolve() or root.is_symlink():
        raise ValueError('Not a local scanner configuration.')
    name = new_name.strip()
    if not name or len(name) > 90 or any(c in name for c in '/\\\0'):
        raise ValueError('Invalid configuration name.')
    if any(other != root and data['name'].casefold() == name.casefold()
           for other, data in list_configurations()):
        raise ValueError('Another saved configuration already uses that name.')
    manifest_file = root / 'configuration.json'
    if manifest_file.is_symlink():
        raise ValueError('Unsafe configuration manifest.')
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    verify_configuration(root, manifest)
    manifest['name'] = name
    fd, temp_name = tempfile.mkstemp(prefix='.rename-', dir=root)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(manifest, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, manifest_file)
    finally:
        Path(temp_name).unlink(missing_ok=True)
    return name

def verify_configuration(folder, manifest=None):
    """Reject missing or modified snapshot files before opening them."""
    root = Path(folder).resolve()
    if manifest is None:
        manifest = json.loads((root / 'configuration.json').read_text(encoding='utf-8'))
    if manifest.get('format') != 'sds100-configuration-snapshot-v1':
        raise ValueError('Unsupported configuration snapshot format.')
    for relative, info in manifest['files'].items():
        candidate = root / relative
        if not candidate.resolve().is_relative_to(root) or candidate.is_symlink() or not candidate.is_file():
            raise ValueError('Missing or unsafe snapshot file: ' + relative)
        digest = hashlib.sha256()
        with candidate.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        if candidate.stat().st_size != info['size'] or digest.hexdigest() != info['sha256']:
            raise ValueError('Snapshot checksum mismatch: ' + relative)
    return True



INDEX_KEY = 'BCDx36HP/favorites_lists/f_list.cfg'


def _index_text(root):
    """Return (raw bytes or None, lines, newline) for the local f_list.cfg index."""
    index = root / INDEX_KEY
    if index.is_symlink():
        raise ValueError('Favorites List index is unsafe.')
    if not index.is_file():
        return None, [], '\r\n'
    raw = index.read_bytes()
    try:
        lines = raw.decode('cp1252').splitlines()
    except UnicodeError as exc:
        raise ValueError('Unsupported Favorites List index encoding.') from exc
    return raw, lines, ('\r\n' if b'\r\n' in raw else '\n')


def _commit_files(root, manifest, writes, deletes=()):
    """Apply file writes/deletes plus the manifest as one rolled-back-on-failure unit.

    writes: {relative: bytes}; deletes: [relative]. Local configuration only.
    """
    root = Path(root)
    manifest_path = root / 'configuration.json'
    old_manifest = manifest_path.read_bytes()
    updated = dict(manifest)
    updated['files'] = dict(manifest['files'])
    for key, payload in writes.items():
        updated['files'][key] = {'size': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}
    for key in deletes:
        updated['files'].pop(key, None)
    updated['last_saved_utc'] = datetime.now(timezone.utc).isoformat()
    originals = {}
    stage = Path(tempfile.mkdtemp(prefix='.sds100-commit-', dir=root))
    try:
        for number, (key, payload) in enumerate(writes.items()):
            target = root / key
            originals[key] = target.read_bytes() if target.is_file() else None
            with (stage / str(number)).open('wb') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        for key in deletes:
            originals[key] = (root / key).read_bytes()
        (stage / 'manifest').write_text(json.dumps(updated, indent=2) + '\n', encoding='utf-8')
        try:
            for number, key in enumerate(writes):
                os.replace(stage / str(number), root / key)
            for key in deletes:
                (root / key).unlink()
            os.replace(stage / 'manifest', manifest_path)
            verify_configuration(root, updated)
        except BaseException:
            for key, data in originals.items():
                if data is None:
                    (root / key).unlink(missing_ok=True)
                else:
                    (root / key).write_bytes(data)
            manifest_path.write_bytes(old_manifest)
            raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return updated


def delete_local_favorites_list(folder, relative):
    """Delete one local Favorites List: its .hpd, its f_list.cfg row and manifest entry.

    Everything is committed together (or rolled back). The deleted file and
    index row are first archived permanently under scanner-configuration-backups
    so a deletion can always be reversed by hand. Never touches a scanner mount.
    """
    root = Path(folder).expanduser().resolve(strict=True)
    if root.parent != library_path().resolve():
        raise ValueError('Only managed local scanner configurations may be edited.')
    key = Path(relative).as_posix()
    if (not key.startswith('BCDx36HP/favorites_lists/')
            or key.count('/') != 2 or not key.lower().endswith('.hpd')
            or '..' in Path(key).parts):
        raise ValueError('Select a Favorites List .hpd file within this configuration.')
    manifest = json.loads((root / 'configuration.json').read_text(encoding='utf-8'))
    verify_configuration(root, manifest)
    if key not in manifest['files']:
        raise ValueError('Favorites List is not registered in the configuration.')
    target = root / key
    if target.is_symlink() or not target.is_file():
        raise ValueError('Favorites List file is missing or unsafe.')
    filename = Path(key).name
    old_data = target.read_bytes()
    digest = hashlib.sha256(old_data).hexdigest()
    raw, lines, newline = _index_text(root)
    kept, removed = [], []
    for line in lines:
        fields = line.split('\t')
        if fields and fields[0] == 'F-List' and len(fields) > 2 and fields[2].strip().lower() == filename.lower():
            removed.append(line)
        else:
            kept.append(line)
    archive = library_path().parent / 'scanner-configuration-backups' / root.name / 'deleted-lists'
    archive.mkdir(parents=True, exist_ok=True)
    saved = archive / f'{Path(filename).stem}.{digest[:12]}.hpd'
    if not saved.exists():
        with saved.open('xb') as stream:
            stream.write(old_data)
            stream.flush()
            os.fsync(stream.fileno())
    if hashlib.sha256(saved.read_bytes()).hexdigest() != digest:
        raise ValueError('Deletion archive failed verification; nothing was deleted.')
    saved.with_suffix('.json').write_text(json.dumps({
        'configuration': root.name, 'relative': key, 'sha256': digest,
        'f_list_rows': removed, 'deleted_utc': datetime.now(timezone.utc).isoformat()}, indent=2) + '\n',
        encoding='utf-8')
    writes = {}
    if raw is not None and removed:
        writes[INDEX_KEY] = (newline.join(kept) + newline).encode('cp1252')
    _commit_files(root, manifest, writes, deletes=[key])
    return key


def save_local_favorites(folder, relative, payload, expected_rows):
    """Safely update ONE local Favorites file, preserving a verified previous version.

    Never accepts a scanner mount as destination. No scanner export occurs here.
    """
    from native_favorites_export import validate_export_file
    root = Path(folder).expanduser().resolve()
    library = library_path().resolve()
    if root.parent != library or root.is_symlink():
        raise ValueError('Only a named configuration in the local configuration library can be edited.')
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts or len(relative.parts) != 3 or relative.parts[:2] != ('BCDx36HP', 'favorites_lists') or relative.suffix.lower() != '.hpd':
        raise ValueError('Only an existing local BCDx36HP/favorites_lists/*.hpd may be saved.')
    target = root / relative
    if target.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(root):
        raise ValueError('Local Favorites file missing or unsafe.')
    manifest_file = root / 'configuration.json'
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    verify_configuration(root, manifest)
    key = str(relative)
    if key not in manifest['files']:
        raise ValueError('Favorites file is not registered in the configuration manifest.')
    if not isinstance(payload, bytes) or not payload:
        raise ValueError('Invalid Favorites data.')
    if target.read_bytes() == payload:
        return {'changed': False, 'backup': None}
    backup_root = library.parent / 'scanner-configuration-backups' / root.name
    backup_root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.sds100-save-', dir=root))
    try:
        candidate = stage / 'candidate.hpd'
        candidate.write_bytes(payload)
        validate_export_file(candidate, expected_rows)
        old_data = target.read_bytes()
        old_hash = hashlib.sha256(old_data).hexdigest()
        # Content-addressed backup avoids storing the same previous bytes twice.
        backup = backup_root / (old_hash + '.hpd')
        if backup.exists():
            if hashlib.sha256(backup.read_bytes()).hexdigest() != old_hash:
                raise ValueError('Existing backup failed verification; refusing save.')
        else:
            tmp_backup = stage / 'backup.hpd'
            tmp_backup.write_bytes(old_data)
            if hashlib.sha256(tmp_backup.read_bytes()).hexdigest() != old_hash:
                raise ValueError('Backup verification failed.')
            # Exclusive creation; never overwrite an existing backup.
            try:
                with backup.open('xb') as stream:
                    stream.write(old_data)
                    stream.flush()
                    os.fsync(stream.fileno())
            except FileExistsError:
                if hashlib.sha256(backup.read_bytes()).hexdigest() != old_hash:
                    raise ValueError('Backup collision or corruption.')
        new_manifest = dict(manifest)
        new_manifest['files'] = dict(manifest['files'])
        new_manifest['files'][key] = {'size': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}
        new_manifest['last_saved_utc'] = datetime.now(timezone.utc).isoformat()
        new_manifest['format'] = 'sds100-configuration-snapshot-v1'  # backwards compatible
        next_manifest = stage / 'configuration.json'
        next_manifest.write_text(json.dumps(new_manifest, indent=2) + '\n', encoding='utf-8')
        # Store recovery metadata before replacement; never touch mounted media.
        receipt = backup_root / (old_hash + '.json')
        if not receipt.exists():
            receipt.write_text(json.dumps({'configuration': root.name, 'relative': key, 'sha256': old_hash, 'saved_utc': new_manifest['last_saved_utc']}, indent=2) + '\n', encoding='utf-8')
        os.replace(candidate, target)
        try:
            os.replace(next_manifest, manifest_file)
        except Exception:
            # Roll back the file if manifest replacement failed.
            target.write_bytes(old_data)
            raise
        verify_configuration(root)
        return {'changed': True, 'backup': str(backup), 'sha256': new_manifest['files'][key]['sha256']}
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def save_configuration_as(folder, new_name, edited_favorites=None, library=None):
    """Create an independent, verified offline configuration (never scanner media).

    edited_favorites maps existing manifest-relative HPD paths to
    (serialized_bytes, expected_native_rows). Changes apply ONLY to the new copy.
    The source configuration, its manifest, and its backup history stay intact.
    """
    from native_favorites_export import validate_export_file

    base = (Path(library) if library is not None else library_path()).expanduser().resolve()
    original_path = Path(folder).expanduser()
    if original_path.is_symlink():
        raise ValueError('Symbolic-link configurations are not supported.')
    source = original_path.resolve()
    if source.parent != base or not source.is_dir():
        raise ValueError('Save As requires a named local scanner configuration.')
    name = new_name.strip() if isinstance(new_name, str) else ''
    if not name or len(name) > 90 or any(c in name for c in '/\\\0'):
        raise ValueError('Choose a valid new configuration name (up to 90 characters).')
    slug = re.sub(r'[^a-zA-Z0-9_-]+', '-', name).strip('-')[:70]
    if not slug:
        raise ValueError('Configuration name must contain letters or numbers.')
    destination = base / slug
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('A configuration with this folder name already exists.')
    if any(manifest.get('name', '').casefold() == name.casefold()
           for _, manifest in list_configurations(base)):
        raise FileExistsError('A configuration with this display name already exists.')
    if any(entry.is_symlink() for entry in source.rglob('*')):
        raise ValueError('Source configuration contains a symbolic link; Save As blocked.')
    manifest_file = source / 'configuration.json'
    if not manifest_file.is_file():
        raise ValueError('Configuration manifest is missing.')
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    verify_configuration(source, manifest)
    registered = manifest['files']
    if not isinstance(registered, dict) or not registered:
        raise ValueError('Configuration contains no registered files.')
    overrides = edited_favorites if edited_favorites is not None else {}
    if not isinstance(overrides, dict):
        raise ValueError('Invalid edited Favorites mapping.')
    for relative, edit in overrides.items():
        path = Path(relative)
        if (relative not in registered or path.is_absolute() or '..' in path.parts
                or len(path.parts) != 3 or path.parts[:2] != ('BCDx36HP', 'favorites_lists')
                or path.suffix.lower() != '.hpd'):
            raise ValueError('Edited Favorites is not a registered native HPD file: ' + str(relative))
        if not isinstance(edit, tuple) or len(edit) != 2 or not isinstance(edit[0], bytes):
            raise ValueError('Invalid native Favorites edit for ' + relative)
    stage = Path(tempfile.mkdtemp(prefix='.sds100-save-as-', dir=base))
    try:
        new_manifest = dict(manifest)
        new_manifest['name'] = name
        new_manifest['files'] = {}
        new_manifest['saved_as_utc'] = datetime.now(timezone.utc).isoformat()
        new_manifest['derived_from'] = source.name
        for relative, info in registered.items():
            path = Path(relative)
            if path.is_absolute() or '..' in path.parts or not path.parts:
                raise ValueError('Unsafe registered file path.')
            old = source / path
            if not old.is_file() or old.is_symlink() or not old.resolve().is_relative_to(source):
                raise ValueError('Missing or unsafe registered source: ' + relative)
            new = stage / path
            new.parent.mkdir(parents=True, exist_ok=True)
            if relative in overrides:
                payload, rows = overrides[relative]
                if not payload or len(payload) > 25 * 1024 * 1024:
                    raise ValueError('Edited Favorites is empty or exceeds size limit.')
                with new.open('xb') as output:
                    output.write(payload)
                    output.flush()
                    os.fsync(output.fileno())
                validate_export_file(new, rows)
            else:
                digest = hashlib.sha256()
                with old.open('rb') as inp, new.open('xb') as out:
                    for chunk in iter(lambda: inp.read(1024 * 1024), b''):
                        out.write(chunk)
                        digest.update(chunk)
                    out.flush()
                    os.fsync(out.fileno())
                if digest.hexdigest() != info['sha256'] or new.stat().st_size != info['size']:
                    raise ValueError('Source changed while creating independent configuration: ' + relative)
            new_manifest['files'][relative] = {
                'size': new.stat().st_size, 'sha256': hashlib.sha256(new.read_bytes()).hexdigest()}
        with (stage / 'configuration.json').open('x', encoding='utf-8') as out:
            json.dump(new_manifest, out, indent=2)
            out.write('\n')
            out.flush()
            os.fsync(out.fileno())
        verify_configuration(stage, new_manifest)
        # Linux atomic no-replace publish. Ordinary os.rename() can replace an
        # empty directory created concurrently; never allow that for Save As.
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, 'renameat2', None)
        if renameat2 is None:
            raise OSError('Atomic no-overwrite rename is unavailable; Save As blocked.')
        renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                              ctypes.c_char_p, ctypes.c_uint]
        renameat2.restype = ctypes.c_int
        if renameat2(-100, os.fsencode(stage), -100, os.fsencode(destination), 1) != 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err), str(destination))
        verify_configuration(destination, new_manifest)
        return destination, new_manifest
    except BaseException:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        raise


def prepare_new_favorites_list(folder, name):
    """Validate a new list name and allocate its filename without changing files."""
    root = Path(folder).expanduser().resolve(strict=True)
    if root.parent != library_path().resolve() or root.is_symlink():
        raise ValueError('Only managed local scanner configurations are supported.')
    name = str(name).strip()
    if not name or len(name) > 64 or any(ch in name for ch in '\r\n\t\x00'):
        raise ValueError('Choose a Favorites List name of 1–64 characters without control characters.')
    try:
        name.encode('cp1252')
    except UnicodeEncodeError as exc:
        raise ValueError('Favorites List name contains characters unsupported by SDS100.') from exc
    manifest = json.loads((root / 'configuration.json').read_text(encoding='utf-8'))
    verify_configuration(root, manifest)
    raw, lines, _newline = _index_text(root)
    if raw is None:
        raise ValueError('The configuration has no BCDx36HP/favorites_lists/f_list.cfg index.')
    existing_names, reserved = set(), set()
    for line in lines:
        row = line.split('\t')
        if row and row[0] == 'F-List':
            if len(row) < 3 or not re.fullmatch(r'f_\d+\.hpd', row[2], re.I):
                raise ValueError('Unrecognized f_list.cfg entry; creation blocked.')
            existing_names.add(row[1].strip().casefold())
            reserved.add(row[2].lower())
    if name.casefold() in existing_names:
        raise ValueError('A Favorites List with this name already exists.')
    favorites_dir = root / 'BCDx36HP' / 'favorites_lists'
    if not favorites_dir.is_dir() or favorites_dir.is_symlink():
        raise ValueError('Native Favorites List directory is missing or unsafe.')
    reserved.update(p.name.lower() for p in favorites_dir.glob('*.hpd'))
    # A list deleted here but not yet removed from the scanner keeps its filename reserved, so a new
    # list can never be exported on top of the old scanner file.
    from scanner_list_sync import recorded_deletions
    reserved.update(Path(name).name.lower() for name in recorded_deletions(root))
    for number in range(1, 10000):
        filename = f'f_{number:06d}.hpd'
        if filename.lower() not in reserved:
            return {'name': name, 'filename': filename}
    raise ValueError('No unused Favorites List filename is available.')


# f_list.cfg row layout (Uniden File Specification V2.00, confirmed on a real SDS100 file):
def save_local_flist_settings(folder, edits):
    """Apply validated per-list settings edits to the LOCAL f_list.cfg (never touches a scanner).

    edits: {(filename, position): value} as understood by flist_settings.  The previous index is
    kept under scanner-configuration-backups; the write and manifest update are one rolled-back unit.
    """
    from flist_settings import patch_lists
    from scanner_list_sync import assess_flist_replacement
    root = Path(folder).expanduser().resolve(strict=True)
    if root.parent != library_path().resolve():
        raise ValueError('Only managed local scanner configurations may be edited.')
    manifest = json.loads((root / 'configuration.json').read_text(encoding='utf-8'))
    verify_configuration(root, manifest)
    raw, _, _ = _index_text(root)
    if raw is None or INDEX_KEY not in manifest['files']:
        raise ValueError('This configuration has no Favorites List index.')
    payload = patch_lists(raw, edits)
    valid, detail, _ = assess_flist_replacement(raw, payload, [], [])
    if not valid:
        raise ValueError('List settings rejected: ' + detail)
    digest = hashlib.sha256(raw).hexdigest()
    backups = library_path().parent / 'scanner-configuration-backups' / root.name
    backups.mkdir(parents=True, exist_ok=True)
    saved = backups / ('f_list.' + digest[:12] + '.cfg')
    if not saved.exists():
        with saved.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    if hashlib.sha256(saved.read_bytes()).hexdigest() != digest:
        raise ValueError('Backup of the previous index failed verification; nothing was changed.')
    _commit_files(root, manifest, {INDEX_KEY: payload})
    return payload


# F-List, UserName, Filename, LocationControl, Monitor, QuickKey(Off/0-99), NumberTag,
# StartupKey0..9, S-Qkey_00..99, then one trailing empty field.
# A new list starts with Location Control Off, Monitor On, and Quick Key, Number Tag, startup
# keys and system-quick-key flags all Off (the same as the user's own unassigned lists).
def new_flist_row(template_fields, name, filename):
    """Build a new index row with the same width as an existing one (validated)."""
    fields = list(template_fields)
    trailing = 0
    while fields and fields[-1] == '':
        fields.pop()
        trailing += 1
    if len(fields) != 117:
        raise ValueError('Unsupported f_list.cfg row layout; creation blocked.')
    onoff = ('On', 'Off')
    keyed = lambda v: v == 'Off' or v.isdecimal()
    if (fields[3] not in onoff or fields[4] not in onoff or not keyed(fields[5])
            or not keyed(fields[6]) or any(v not in onoff for v in fields[7:])):
        raise ValueError('f_list.cfg row values are not recognised; creation blocked.')
    fields[1], fields[2] = name, filename
    fields[3], fields[4] = 'Off', 'On'
    fields[5:] = ['Off'] * len(fields[5:])
    return fields + [''] * trailing


def create_local_favorites_list(folder, name, rows, encoding='cp1252', newline='\r\n'):
    """Create a native list that ALREADY contains content; local only.

    Called only from the Add to Favorites workflow with the rows built by
    new_favorites_list.build_new_list_rows.  An empty list is refused.  The .hpd,
    the f_list.cfg row and the manifest are committed together or not at all.
    """
    from native_favorites_export import validate_export_file
    if encoding not in ('cp1252', 'latin-1', 'utf-8-sig') or newline not in ('\r\n', '\n'):
        raise ValueError('Unsupported native encoding or line ending.')
    if not any(r and r[0] in ('Conventional', 'Trunk') for r in rows):
        raise ValueError('A Favorites List is never created empty.')
    prepared = prepare_new_favorites_list(folder, name)
    root = Path(folder).expanduser().resolve(strict=True)
    manifest = json.loads((root / 'configuration.json').read_text(encoding='utf-8'))
    verify_configuration(root, manifest)
    raw, lines, index_newline = _index_text(root)
    template = next((l.split('\t') for l in lines if l.startswith('F-List\t')), None)
    if template is None:  # every list was deleted: use the specification's row shape
        template = ['F-List', '', '', 'Off', 'On', 'Off', 'Off'] + ['Off'] * 110 + ['']
    row = new_flist_row(template, prepared['name'], prepared['filename'])
    index_bytes = (index_newline.join(lines + ['\t'.join(row)]) + index_newline).encode('cp1252')
    hpd_bytes = (newline.join('\t'.join(r) for r in rows) + newline).encode(encoding)
    hpd_key = 'BCDx36HP/favorites_lists/' + prepared['filename']
    target = root / hpd_key
    if target.exists() or target.is_symlink():
        raise FileExistsError('Allocated Favorites List filename is no longer free.')
    probe = Path(tempfile.mkdtemp(prefix='.sds100-newlist-', dir=root))
    try:
        (probe / 'candidate.hpd').write_bytes(hpd_bytes)
        validate_export_file(probe / 'candidate.hpd', [list(r) for r in rows])
    finally:
        shutil.rmtree(probe, ignore_errors=True)
    _commit_files(root, manifest, {hpd_key: hpd_bytes, INDEX_KEY: index_bytes})
    prepared['path'] = str(target)
    return prepared
