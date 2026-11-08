# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Offline, experimental bulk HPDB state reconstruction; no scanner operations."""
from pathlib import Path
import gzip, hashlib, json, os, re, shutil, tempfile
from contextlib import ExitStack
from hpdb_state_reconstruction import transform_record
from hpdb_cfg_generator import generate_config
from master_hpdb_validator import validate


def reconstruct_all_states(master, output_directory, progress=None):
    master = Path(master).expanduser().resolve(strict=True)
    output_directory = Path(output_directory).expanduser().absolute()
    if output_directory.exists() or output_directory.is_symlink():
        raise FileExistsError('Destination must not already exist')
    if not output_directory.parent.is_dir():
        raise FileNotFoundError('Destination parent directory does not exist')
    if output_directory == master or master.is_relative_to(output_directory):
        raise ValueError('Output directory cannot contain the master')
    if progress: progress("Validating master database")
    report = validate(master)
    if not report['valid']:
        raise ValueError('Master failed structural validation')
    opener = gzip.open if master.suffix.lower() == '.gz' else open
    if progress: progress("Reading state identifiers")
    ids = set()
    with opener(master, 'rt', encoding='cp1252', newline='') as source:
        for line in source:
            if line.startswith('StateInfo\t'):
                match = re.search(r'(?:^|\t)StateId=(\d+)(?:\t|$)', line.rstrip('\r\n'))
                if match:
                    ids.add(int(match.group(1)))
    if len(ids) != 68:
        raise ValueError(f'Expected 68 standard StateInfo IDs; found {len(ids)}. Export refused.')
    if progress: progress("Reconstructing 68 state files")
    stage = Path(tempfile.mkdtemp(prefix='.hpdb-staging-', dir=output_directory.parent))
    try:
        counts = {sid: 2 for sid in ids}
        with ExitStack() as stack:
            handles = {sid: stack.enter_context((stage / f's_{sid:06d}.hpd').open('x', encoding='cp1252', newline='')) for sid in sorted(ids)}
            for out in handles.values():
                out.write('TargetModel\tBCDx36HP\r\nFormatVersion\t1.00\r\n')
            selected = None
            with opener(master, 'rt', encoding='cp1252', newline='') as source:
                for line in source:
                    fields = line.rstrip('\r\n').split('\t')
                    tag = fields[0]
                    if tag in ('Conventional', 'Trunk'):
                        match = re.fullmatch(r'StateId=(\d+)', fields[2]) if len(fields) >= 3 else None
                        selected = int(match.group(1)) if match and int(match.group(1)) in ids else None
                    elif tag in ('LM', 'LM_Frequency', 'File'):
                        selected = None
                    if selected is not None:
                        handles[selected].write('\t'.join(transform_record(fields)) + '\r\n')
                        counts[selected] += 1
        if progress: progress("Copying master and generating hpdb.cfg")
        # Include the original master in an offline-only staging package.
        with opener(master, 'rb') as source, (stage / 'MasterHpdb.hp1').open('xb') as target:
            shutil.copyfileobj(source, target, length=1024*1024)
        config_info = generate_config(master, stage / "hpdb.cfg")
        if progress: progress("Calculating SHA-256 verification manifest")
        manifest = {'source': str(master), 'master_header': report['header'], 'states': {}, 'config': {**config_info, 'sha256': hashlib.sha256((stage / 'hpdb.cfg').read_bytes()).hexdigest()}, 'note': 'Rebuilt offline database package. Put it on the scanner only with Update Scanner\'s Master Database.'}
        for file in sorted(stage.glob('*.hpd')):
            sid = int(file.stem.split('_')[1])
            manifest['states'][str(sid)] = {'records': counts[sid], 'bytes': file.stat().st_size, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()}
        file = stage / 'MasterHpdb.hp1'
        manifest['master_sha256'] = hashlib.sha256(file.read_bytes()).hexdigest()
        (stage / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        (stage / 'README.txt').write_text('Rebuilt offline database package (68 state files, hpdb.cfg, master copy).\nInstall it only with Database > Update Scanner\'s Master Database in the application; do not copy files onto the card by hand or into Sentinel folders.\n')
        if output_directory.exists() or output_directory.is_symlink():
            raise FileExistsError('Destination appeared during export; refusing overwrite')
        stage.rename(output_directory)
        if progress: progress("Offline export verified and completed")
        return {'path': str(output_directory), 'states': len(ids), 'records': sum(counts.values()), 'master_sha256': manifest['master_sha256'], 'config_sha256': manifest['config']['sha256']}
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
