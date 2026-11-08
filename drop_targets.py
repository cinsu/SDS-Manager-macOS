# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""What a drag-and-drop onto the main window means (pure; only looks at names and folders)."""
from pathlib import Path


def classify(paths):
    """Return (action, path, message).  action: 'scanner' | 'hpd' | None (message says why)."""
    paths = [Path(p) for p in paths if str(p)]
    if len(paths) != 1:
        return None, None, 'Drop one SD card folder or one .hpd file at a time.'
    path = paths[0]
    if path.is_symlink():
        return None, None, 'Symbolic links are not accepted.'
    if path.is_dir():
        for root in (path, path.parent) if path.name == 'BCDx36HP' else (path,):
            if (root / 'BCDx36HP').is_dir():
                return 'scanner', str(root), ''
        return None, None, 'That folder does not contain a BCDx36HP folder (the SD card root does).'
    if path.is_file() and path.suffix.lower() == '.hpd':
        return 'hpd', str(path), ''
    return None, None, 'Only an SDS100 SD card folder or a Favorites List (.hpd) file can be dropped here.'
