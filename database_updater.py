# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Safe offline HPDB import into a managed local cache; no network endpoints guessed."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone

def find_hpdb(path):
    base = Path(path).expanduser().resolve()
    for folder in (base / "BCDx36HP" / "HPDB", base / "HPDB", base):
        if folder.is_dir() and (folder / "hpdb.cfg").is_file() and any(folder.glob("s_*.hpd")):
            return folder
    raise ValueError("Select a complete Uniden HPDB folder containing hpdb.cfg and s_*.hpd files")

def import_hpdb(source, destination):
    """Import an already-obtained HPDB; never writes to original or scanner.
    Atomic local directory replacement; previous import kept as .previous.
    """
    source = find_hpdb(source)
    dest = Path(destination).expanduser().resolve()
    if source == dest or dest in source.parents or source in dest.parents:
        raise ValueError("Import destination must be separate from source")
    files = sorted([p for p in source.iterdir() if p.is_file() and
                    (p.name == "hpdb.cfg" or
                     (p.name.startswith("s_") and p.suffix.lower() in (".hpd", ".avd")))])
    state_files = [p for p in files if p.suffix.lower() == ".hpd"]
    if not state_files:
        raise ValueError("No state HPD files found")
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".hpdb-import-", dir=dest.parent))
    try:
        manifest = {"imported_utc": datetime.now(timezone.utc).isoformat(),
                    "source": str(source), "file_count": len(files),
                    "state_count": len(state_files), "files": {}}
        for path in files:
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"Refusing symbolic link: {path.name}")
            h = hashlib.sha256()
            with path.open("rb") as inp, (staging / path.name).open("xb") as out:
                while True:
                    data = inp.read(1024 * 1024)
                    if not data:
                        break
                    out.write(data)
                    h.update(data)
            check = hashlib.sha256((staging / path.name).read_bytes()).hexdigest()
            if check != h.hexdigest():
                raise IOError(f"Checksum mismatch: {path.name}")
            manifest["files"][path.name] = {"bytes": path.stat().st_size, "sha256": check}
        (staging / "import_manifest.json").write_text(json.dumps(manifest, indent=2))
        backup = dest.with_name(dest.name + ".previous")
        if backup.exists():
            # Do not silently erase prior backup.
            backup = dest.with_name(dest.name + "." + datetime.now().strftime("%Y%m%d_%H%M%S") + ".previous")
        if dest.exists():
            dest.rename(backup)
        try:
            staging.rename(dest)
        except BaseException:
            if backup.exists() and not dest.exists():
                backup.rename(dest)
            raise
        return manifest
    finally:
        if staging.exists():
            shutil.rmtree(staging)
