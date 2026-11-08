# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Private XDG data storage. Never accesses scanner or Sentinel directories."""
from pathlib import Path
import os, json, shutil, tempfile, hashlib, re
from datetime import datetime, timezone

ROOT = Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share'))).expanduser() / 'SDS100DatabaseFavoritesManager'

def paths():
    return {key: ROOT/key for key in ('database','favorites','history','manifests')}

def initialize():
    for p in [ROOT, ROOT/'database', ROOT/'database'/'versions', ROOT/'database'/'downloads', ROOT/'database'/'backups', ROOT/'favorites'/'drafts', ROOT/'favorites'/'imports', ROOT/'favorites'/'exports', ROOT/'history', ROOT/'manifests']:
        p.mkdir(parents=True, exist_ok=True)
    return ROOT

def active_database():
    current = ROOT/'database'/'current'
    if not current.is_symlink():
        return None
    target = current.resolve()
    versions = (ROOT/'database'/'versions').resolve()
    if target.parent != versions or not target.is_dir() or not valid_package(target):
        return None
    return target

def valid_package(folder):
    folder = Path(folder)
    states = list(folder.glob('s_*.hpd'))
    return (len(states)==68 and (folder/'hpdb.cfg').is_file() and (folder/'MasterHpdb.hp1').is_file() and all(p.stat().st_size for p in states))

def activate_export(folder, version_name):
    """Adopt a completed export; retain previous version and switch one symlink atomically."""
    initialize()
    folder=Path(folder).resolve(strict=True)
    if not valid_package(folder):
        raise ValueError('Expected 68 nonempty states, hpdb.cfg and MasterHpdb.hp1')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}',version_name):
        raise ValueError('Invalid database version name')
    dest=ROOT/'database'/'versions'/version_name
    if dest.exists() or dest.is_symlink():
        raise FileExistsError('Managed database version already exists')
    # Move completed export if it is already under managed versions; otherwise copy to staging.
    stage=Path(tempfile.mkdtemp(prefix='.import-',dir=dest.parent))
    try:
        for p in folder.iterdir():
            if p.is_symlink(): raise ValueError('Symlinks in import are not allowed')
            if p.is_file(): shutil.copy2(p,stage/p.name)
        if not valid_package(stage): raise ValueError('Staged database incomplete')
        # Compare every copied file, not just sizes.
        for p in folder.iterdir():
            if p.is_file():
                with p.open('rb') as a, (stage/p.name).open('rb') as b:
                    while True:
                        x=a.read(1024*1024); y=b.read(1024*1024)
                        if x!=y: raise ValueError('Staged file checksum mismatch: '+p.name)
                        if not x: break
        stage.rename(dest)
    except BaseException:
        shutil.rmtree(stage,ignore_errors=True)
        raise
    current=ROOT/'database'/'current'
    if current.exists() and not current.is_symlink():
        raise RuntimeError('Refusing to replace a non-symlink current database')
    link=ROOT/'database'/('.current-'+version_name)
    try:
        link.symlink_to(Path('versions')/version_name, target_is_directory=True)
        os.replace(link,current)
    finally:
        if link.is_symlink(): link.unlink()
    history=ROOT/'history'/'database_updates.jsonl'
    with history.open('a',encoding='utf-8') as out:
        out.write(json.dumps({'utc':datetime.now(timezone.utc).isoformat(),'version':version_name,'location':str(dest)})+'\n')
    return dest


# ---- Version housekeeping (explicit user action only) -------------------------------------------
def list_versions():
    """[Path] of complete rebuilt database versions, oldest first by name."""
    versions = ROOT / 'database' / 'versions'
    if not versions.is_dir() or versions.is_symlink():
        return []
    return sorted((p for p in versions.iterdir() if p.is_dir() and not p.is_symlink() and valid_package(p)),
                  key=lambda p: p.name)


def plan_version_cleanup(keep, protected_dates=()):
    """Versions cleanup would delete.  Always kept: the newest `keep`, the current version, and any version whose
    hpdb.cfg DateModified is in protected_dates (for example the date on the user's scanner)."""
    from scanner_detect import local_database_date
    versions = list_versions()
    keep = max(int(keep), 1)
    current = (ROOT / 'database' / 'current')
    current_target = current.resolve() if current.is_symlink() else None
    protected = set(protected_dates)
    doomed = []
    for path in versions[:-keep] if len(versions) > keep else []:
        if current_target is not None and path.resolve() == current_target:
            continue
        if local_database_date(path) in protected:
            continue
        doomed.append(path)
    return doomed


def cleanup_versions(names, keep, protected_dates=()):
    """Delete the named versions if each is still in a fresh plan.  Returns the names deleted."""
    allowed = {p.name: p for p in plan_version_cleanup(keep, protected_dates)}
    removed = []
    for name in names:
        path = allowed.get(name)
        if path is None or path.is_symlink() or path.resolve().parent != (ROOT / 'database' / 'versions').resolve():
            continue
        shutil.rmtree(path)
        removed.append(name)
    return removed
