# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Read-only export comparison. No scanner writes or export serialization."""
from pathlib import Path
import json
from scanner_preflight import inspect_scanner
from scanner_backup import digest
from scanner_export_safety import audit_export_safety
from scanner_staging_rehearsal import rehearse_staging
from scanner_write_recovery_rehearsal import rehearse_write_recovery
from scanner_export_readiness import readiness_summary
from scanner_native_inspection import inspect_native_files
from scanner_native_roundtrip import inspect_roundtrip
from scanner_native_edit_probe import inspect_edit_probe
from scanner_native_multifield_probe import inspect_multifield_probe
from scanner_native_value_audit import inspect_native_values
from scanner_native_numeric_analysis import inspect_numeric_representations
from scanner_native_frequency_spec_audit import inspect_frequency_spec
from scanner_native_layout_audit import inspect_record_layout
from scanner_native_field_structure_audit import audit_field_structure
from scanner_native_lossless_edit_audit import audit_lossless_field_edits
from scanner_native_variable_length_audit import audit_variable_length_edits
from scanner_native_spec_mapping_audit import audit_spec_field_mapping
from scanner_configurations import list_configurations, CONFIG_FILES, CONFIG_DIRS


def _files(root):
    found = {}
    for name in CONFIG_FILES:
        p = root / name
        if p.is_symlink(): raise ValueError('Symlink rejected: ' + name)
        if p.is_file(): found[name] = p
    for name in CONFIG_DIRS:
        d = root / name
        if d.is_symlink(): raise ValueError('Symlink rejected: ' + name)
        if d.is_dir():
            for p in d.rglob('*'):
                if p.is_symlink(): raise ValueError('Symlink rejected: ' + str(p))
                if p.is_file() and (name != 'favorites_lists' or p.suffix.lower() in ('.hpd', '.cfg')):
                    found[p.relative_to(root).as_posix()] = p
    return found


def _without_master_database(files):
    """The master database (HPDB/) is replaced only by Update Scanner's Master Database, never by this export.

    A saved configuration keeps the HPDB it was taken with, which is older than the card after an update."""
    return {name: path for name, path in files.items() if not name.startswith('HPDB/')}


def _backup_status(scanner_root, scanner_files, backup_base=None):
    base = Path(backup_base) if backup_base else Path.home()/'.local/share/sds100-database-favorites-manager/scanner-backups'
    if not base.is_dir(): return 'No verified local scanner backup found', False
    for folder in sorted(base.iterdir(), reverse=True):
        manifest_path = folder/'manifest.json'
        if not manifest_path.is_file() or manifest_path.is_symlink(): continue
        try:
            data = json.loads(manifest_path.read_text(encoding='utf-8'))
            if data.get('verified') is not True or data.get('source') != str(scanner_root): continue
            entries = data.get('files', [])
            if not isinstance(entries,list) or len(entries) != len(scanner_files): continue
            by_path = {e['path']:e for e in entries}
            if set(by_path) != set(scanner_files): continue
            if all((folder/'BCDx36HP'/name).is_file() and
                   (folder/'BCDx36HP'/name).stat().st_size == entry['size'] and
                   digest(folder/'BCDx36HP'/name) == entry['sha256'] and
                   digest(scanner_files[name]) == entry['sha256']
                   for name,entry in by_path.items()):
                return 'Current scanner contents match verified backup: ' + str(folder), True
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return 'No backup matches and verifies the CURRENT scanner contents', False


def preview_export(configuration_folder, scanner_location, backup_base=None, compact=False):
    config = Path(configuration_folder).expanduser().resolve()
    valid_configs = {folder.resolve(): data for folder,data in list_configurations()}
    if config not in valid_configs: raise ValueError('Select a recognized saved local configuration.')
    name = valid_configs[config]['name']
    report, valid = inspect_scanner(scanner_location)
    if not valid: raise ValueError('Scanner preflight failed.\n'+report)
    selected = Path(scanner_location).expanduser().resolve()
    scanner = selected if selected.name.lower() == 'bcdx36hp' else selected/'BCDx36HP'
    local = config/'BCDx36HP'
    if not local.is_dir(): raise ValueError('Local configuration has no BCDx36HP directory.')
    source_files = _without_master_database(_files(local))
    target_files = _without_master_database(_files(scanner))
    if not source_files: raise ValueError('No supported local configuration files found.')
    if not any(n.startswith('favorites_lists/') and n.endswith('.hpd') for n in source_files):
        raise ValueError('Local configuration has no Favorites .hpd files.')
    results = {'ADD':[], 'REPLACE':[], 'UNCHANGED':[], 'RETAIN ON SCANNER':[]}
    # Scanner-owned volatile operating state is intentionally never exported.
    # It may differ after an ordinary power cycle without any user edit.
    for namepath, source in sorted(source_files.items()):
        if namepath == 'app_data.cfg' and namepath in target_files:
            results['UNCHANGED'].append(namepath)
            continue
        if namepath not in target_files: category = 'ADD'
        elif source.stat().st_size == target_files[namepath].stat().st_size and digest(source) == digest(target_files[namepath]): category = 'UNCHANGED'
        else: category = 'REPLACE'
        results[category].append(namepath)
    results['RETAIN ON SCANNER'] = sorted(set(target_files)-set(source_files))
    if compact:
        lines = ['SCANNER EXPORT PREVIEW — READ ONLY', '',
                 'Local configuration: ' + name, 'Scanner folder: ' + str(scanner),
                 'Scanner structure preflight: PASSED',
                 'Practical USB identity and one-field eligibility are checked separately.',
                 'A fresh full configuration backup will be created after confirmation, before writing.',
                 'Scanner-owned app_data.cfg is excluded from export and preserved on the scanner.', '']
        from scanner_list_sync import recorded_deletions, is_list_file
        recorded = recorded_deletions(config)
        removable = [n for n in results['RETAIN ON SCANNER']
                     if n in recorded and is_list_file(n) and digest(target_files[n]) == recorded[n]]
        for category, paths in results.items():
            if category == 'RETAIN ON SCANNER':
                lines.append(f'REMOVE FROM SCANNER: {len(removable)}  (Favorites Lists deleted in this program)')
                lines.extend('  ' + p for p in removable)
                lines.append('')
                paths = [p for p in paths if p not in removable]
            lines.append(f'{category}: {len(paths)}')
            lines.extend('  ' + p for p in paths)
            lines.append('')
        lines.append('Preview is read-only. Scanner writes: 0.')
        return '\n'.join(lines), results, False
    backup_text, backup_ok = _backup_status(scanner,target_files,backup_base)
    lines = ['SCANNER EXPORT PREVIEW — READ ONLY', '',
             'DIAGNOSTIC ONLY: historical audits below are conservative and do not govern the live',
             'File → Export to Scanner eligibility check. This diagnostic performs ZERO writes.',
             '', 'Local configuration: '+name,
             'Local folder: '+str(config),'Scanner folder: '+str(scanner),'',
             report, '',
             'Backup check: '+backup_text,
             'NOTE: Backup matching is a point-in-time check; a fresh verified backup is required immediately before any future write.',
             'Native export compatibility: NOT VERIFIED',
             'Configuration validation: NOT A SUBSTITUTE FOR NATIVE FORMAT VERIFICATION','']
    for category, paths in results.items():
        lines.append(f'{category}: {len(paths)}')
        lines.extend('  '+p for p in paths)
        lines.append('')
    lines.append(audit_export_safety(local, scanner, source_files, target_files, results))
    lines.append('')
    rehearsal_report, rehearsal_ok = rehearse_staging(scanner, source_files, target_files, results)
    lines.append(rehearsal_report)
    lines.append('')
    recovery_report, _recovery_ok = rehearse_write_recovery(scanner, source_files, target_files, results)
    lines.append(recovery_report)
    lines.append('')
    readiness_report, _write_allowed = readiness_summary(
        source_files, target_files, results, backup_ok, rehearsal_ok)
    lines.append(readiness_report)
    lines.append('')
    lines.append(inspect_native_files(source_files))
    lines.append('')
    lines.append(inspect_roundtrip(source_files))
    lines.append('')
    lines.append(inspect_edit_probe(source_files))
    lines.append('')
    lines.append(inspect_multifield_probe(source_files))
    lines.append('')
    lines.append(inspect_native_values(source_files))
    lines.append('')
    lines.append(inspect_numeric_representations(source_files))
    lines.append('')
    lines.append(inspect_frequency_spec(source_files))
    lines.append('')
    lines.append(inspect_record_layout(source_files))
    lines.append('')
    lines.append(audit_field_structure(source_files))
    lines.append('')
    lines.append(audit_lossless_field_edits(source_files))
    lines.append("\n\n" + audit_variable_length_edits(source_files))
    lines.append('')
    lines.append(audit_spec_field_mapping(source_files))
    lines.append('')
    lines.extend(['No scanner files were opened for writing, changed, or deleted.',
                  'Scanner-only files would be RETAINED, not removed.',
                  'This DIAGNOSTIC is read-only and cannot authorize writing. Use File → Export to Scanner for current eligibility.'])
    return '\n'.join(lines), results, backup_ok
