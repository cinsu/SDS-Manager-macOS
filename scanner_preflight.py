# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Read-only SDS100 mass-storage preflight. Never writes to the selected drive."""
from pathlib import Path
from scanner_configurations import CONFIG_FILES, CONFIG_DIRS
from scanner_identity import inspect_scanner_identity

def inspect_scanner(path):
    selected = Path(path).expanduser().resolve()
    root = selected if selected.name.lower() == 'bcdx36hp' else selected / 'BCDx36HP'
    lines = ['SCANNER EXPORT PREFLIGHT — READ ONLY', '', f'Selected location: {selected}', f'Configuration folder: {root}', '']
    errors, warnings = [], []
    if not root.is_dir():
        errors.append('BCDx36HP directory not found.')
    else:
        favorites = root / 'favorites_lists'
        if not favorites.is_dir(): errors.append('BCDx36HP/favorites_lists directory not found.')
        if not any((root / x).is_file() for x in ('profile.cfg','scanner.inf')):
            errors.append('Neither profile.cfg nor scanner.inf identification/configuration file was found.')
        for name in CONFIG_FILES:
            f = root / name
            lines.append(f'{name}: {"present" if f.is_file() else "not present"}')
            if f.is_symlink(): errors.append(f'Symbolic link not supported: {name}')
        for name in CONFIG_DIRS:
            d = root / name
            lines.append(f'{name}/: {"present" if d.is_dir() else "not present"}')
            if d.is_symlink(): errors.append(f'Symbolic link not supported: {name}/')
        if favorites.is_dir() and not favorites.is_symlink():
            hpd = sorted(favorites.glob('*.hpd'))
            cfg = sorted(favorites.glob('*.cfg'))
            lines.extend([f'Favorites .hpd files: {len(hpd)}',f'Favorites .cfg files: {len(cfg)}'])
            if not hpd: errors.append('No native Favorites .hpd files found.')
            if any(x.is_symlink() for x in hpd+cfg): errors.append('Symbolic links found in Favorites files.')
    lines.extend(['', f'Preflight errors: {len(errors)}',f'Preflight warnings: {len(warnings)}'])
    lines.extend('ERROR: '+e for e in errors)
    lines.extend('WARNING: '+w for w in warnings)
    lines.extend(['', inspect_scanner_identity(root), '',
                  'No scanner files were opened for writing or modified.',
                  'USB mount evidence is diagnostic only; SDS100 model identity is NOT verified. Free space, native export compatibility, and write safety are not established.',
                  'Export to Scanner is NOT enabled in this release.'])
    return '\n'.join(lines), not errors
