#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Review and remove old SDS100 app installs. Never remove user data."""
from pathlib import Path
import re, shutil, sys
home=Path.home(); appdir=home/'.local/share/applications'
pattern=re.compile(r'^SDS100DatabaseFavoritesManager-0\.0\.[0-9]+[a-z]?$')
entrypat=re.compile(r'^sds100-database-favorites-0\.0\.[0-9]+[a-z]\.desktop$')
roots=[p for p in home.iterdir() if pattern.fullmatch(p.name) and p.is_dir() and not p.is_symlink() and (p/'launch.sh').is_file() and (p/'database_favorites_manager.py').is_file()]
entries=[p for p in appdir.glob('sds100-database-favorites-*.desktop') if entrypat.fullmatch(p.name) and p.is_file() and not p.is_symlink() and 'SDS100DatabaseFavoritesManager-' in p.read_text(errors='replace')]
print('SDS100 installed application cleanup (preview only)')
print('Application folders:'); [print('  '+str(p)) for p in roots]
print('Application-menu launchers:'); [print('  '+str(p)) for p in entries]
print('\nExcluded: scanner configurations, Favorites Lists, databases, backups, settings, and extracted ZIPs.')
if not roots and not entries:
 print('Nothing matching the known installer pattern was found.'); sys.exit(0)
print('\nWARNING: some older installers reused the 0.0.4r directory. Review the list carefully.')
if input('Type REMOVE to delete ONLY the listed application folders and launchers: ').strip()!='REMOVE':
 print('Cancelled; nothing deleted.'); sys.exit(0)
for p in entries:
 if p.is_file() and not p.is_symlink(): p.unlink(); print('Removed launcher:',p)
for p in roots:
 if p.is_dir() and not p.is_symlink(): shutil.rmtree(p); print('Removed app folder:',p)
print('Finished. Personal application data was not targeted.')
