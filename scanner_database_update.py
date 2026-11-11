# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Replace the scanner's whole master database (BCDx36HP/HPDB) from a rebuilt local database version.

Guards, all read-only before any write:
  * the package is a complete rebuilt database (state files + hpdb.cfg) from managed storage;
  * the card holds the same set of states as the package;
  * every record in every new file has a tag and field count that the card's own files already use;
  * state files agree with their own file names;
  * the new database is not older than the card's and is not suspiciously smaller or different.
Favorites lists are self-contained copies and are never touched by this update.

The write itself is the same controlled batch as the favorites export: a fresh SHA-256-verified backup,
SHA-256 staging for every file, rollback of the whole batch on any failure, then os.sync().
"""
import mac_platform  # macOS: full flush to the SD card, no-overwrite rename
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import shutil

import scanner_first_write as fw
from scanner_backup import digest

STATE_NAME = re.compile(r's_(\d{6})\.hpd')
HEADER = (b'TargetModel\tBCDx36HP', b'FormatVersion\t1.00')
CONFIG = 'hpdb.cfg'
MIN_SIMILARITY = 0.70          # share of the card's existing records that must survive in the new file set
MIN_FILE_SIMILARITY = 0.40     # per state file (only judged when the file has at least 100 records)
MAX_SHRINK = 0.50              # a large state file may not lose more than half its bytes
MAX_PROBLEMS = 12


def _split_lines(data):
    if b'\x00' in data:
        raise ValueError('contains a NUL byte')
    if not data.endswith(b'\r\n'):
        raise ValueError('does not end with a CRLF line ending')
    lines = data.split(b'\r\n')[:-1]
    if any(b'\n' in x or b'\r' in x for x in lines):
        raise ValueError('mixes line endings')
    return lines


def _files(folder):
    """{name: Path} of the database files in a folder; rejects symlinks."""
    folder = Path(folder)
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError('Database folder is missing or a symbolic link: ' + str(folder))
    found = {}
    for item in sorted(folder.iterdir()):
        if item.is_symlink():
            raise ValueError('Symbolic link in database folder: ' + item.name)
        if item.is_file() and (STATE_NAME.fullmatch(item.name) or item.name == CONFIG):
            found[item.name] = item
    return found


def _widths(files):
    table = {}
    for path in files:
        for line in _split_lines(path.read_bytes()):
            fields = line.split(b'\t')
            table.setdefault(fields[0], set()).add(len(fields))
    return table


def _date(lines):
    for line in lines[:4]:
        if line.startswith(b'DateModified\t'):
            try:
                return datetime.strptime(line.split(b'\t', 1)[1].decode('ascii'), '%m/%d/%Y %H:%M:%S')
            except (ValueError, UnicodeError):
                return None
    return None


def analyze(package, card_hpdb):
    """Compare a rebuilt package with the card's HPDB folder.  Returns a report dict; never writes."""
    problems, warnings = [], []

    def problem(text):
        if len(problems) < MAX_PROBLEMS:
            problems.append(text)
        elif len(problems) == MAX_PROBLEMS:
            problems.append('Further problems omitted.')

    new, old = _files(package), _files(card_hpdb)
    if CONFIG not in new:
        raise ValueError('The database package has no hpdb.cfg.')
    if CONFIG not in old:
        raise ValueError('The scanner has no HPDB/hpdb.cfg to compare with.')
    new_states = {n: p for n, p in new.items() if n != CONFIG}
    old_states = {n: p for n, p in old.items() if n != CONFIG}
    if not old_states:
        raise ValueError('The scanner has no HPDB state files to compare with.')
    if set(new_states) != set(old_states):
        missing = sorted(set(old_states) - set(new_states))
        extra = sorted(set(new_states) - set(old_states))
        raise ValueError('The new database covers different states from the scanner '
                         '(missing %s; extra %s). Not supported in this release.' % (missing[:5], extra[:5]))
    widths = _widths(old_states.values())
    cfg_widths = _widths([old[CONFIG]])
    kept = total_old = 0
    changed, identical = [], 0
    for name in sorted(new_states):
        try:
            new_lines = _split_lines(new_states[name].read_bytes())
            old_lines = _split_lines(old_states[name].read_bytes())
        except ValueError as exc:
            problem('%s: %s' % (name, exc))
            continue
        if tuple(new_lines[:2]) != HEADER:
            problem('%s: header is not TargetModel BCDx36HP / FormatVersion 1.00' % name)
            continue
        state_id = int(STATE_NAME.fullmatch(name).group(1))
        bad_tag = bad_width = wrong_state = 0
        for line in new_lines[2:]:
            fields = line.split(b'\t')
            if fields[0] not in widths:
                bad_tag += 1
            elif len(fields) not in widths[fields[0]]:
                bad_width += 1
            if fields[0] in (b'Conventional', b'Trunk') and len(fields) > 2 \
                    and fields[2] != b'StateId=%d' % state_id:
                wrong_state += 1
        if bad_tag:
            problem('%s: %d record(s) of a type the scanner does not use' % (name, bad_tag))
        if bad_width:
            problem('%s: %d record(s) with a field count the scanner does not use' % (name, bad_width))
        if wrong_state:
            problem('%s: %d system(s) belong to another state' % (name, wrong_state))
        new_set = set(new_lines)
        survive = sum(1 for x in old_lines if x in new_set)
        kept += survive
        total_old += len(old_lines)
        if new_states[name].read_bytes() == old_states[name].read_bytes():
            identical += 1
        else:
            changed.append(name)
        if len(old_lines) >= 100 and survive / len(old_lines) < MIN_FILE_SIMILARITY:
            problem('%s: only %d%% of the scanner\'s records are present in the new file'
                    % (name, 100 * survive // len(old_lines)))
        new_size, old_size = new_states[name].stat().st_size, old_states[name].stat().st_size
        if old_size > 10_000 and new_size < old_size * (1 - MAX_SHRINK):
            problem('%s shrinks from %d to %d bytes' % (name, old_size, new_size))
    similarity = kept / total_old if total_old else 1.0
    if similarity < MIN_SIMILARITY:
        problem('Only %d%% of the scanner\'s current records appear in the new database (minimum %d%%). '
                'The rebuilt format may differ from what the scanner holds.'
                % (round(100 * similarity), round(100 * MIN_SIMILARITY)))
    # hpdb.cfg
    try:
        new_cfg = _split_lines(new[CONFIG].read_bytes())
        old_cfg = _split_lines(old[CONFIG].read_bytes())
        if tuple(new_cfg[:2]) != HEADER:
            problem('hpdb.cfg: header is not TargetModel BCDx36HP / FormatVersion 1.00')
        for line in new_cfg[2:]:
            fields = line.split(b'\t')
            if fields[0] not in cfg_widths or len(fields) not in cfg_widths[fields[0]]:
                problem('hpdb.cfg: a %s record does not match the scanner\'s hpdb.cfg layout' % fields[0].decode('cp1252'))
                break
        states_old = [x for x in old_cfg if x.startswith(b'StateInfo\t')]
        states_new = [x for x in new_cfg if x.startswith(b'StateInfo\t')]
        if sorted(x.split(b'\t')[1] for x in states_old) != sorted(x.split(b'\t')[1] for x in states_new):
            problem('hpdb.cfg lists different states from the scanner\'s hpdb.cfg')
        old_date, new_date = _date(old_cfg), _date(new_cfg)
        if new_date is None:
            problem('hpdb.cfg has no valid DateModified')
        elif old_date and new_date < old_date:
            problem('The new database (%s) is OLDER than the scanner\'s (%s).' % (new_date, old_date))
    except ValueError as exc:
        problem('hpdb.cfg: %s' % exc)
        old_date = new_date = None
    cfg_changed = new[CONFIG].read_bytes() != old[CONFIG].read_bytes()
    return {'valid': not problems, 'problems': problems, 'warnings': warnings,
            'states': len(new_states), 'changed_states': changed, 'unchanged_states': identical,
            'config_changed': cfg_changed, 'similarity': similarity,
            'old_date': str(old_date) if old_date else None, 'new_date': str(new_date) if new_date else None}


def prepare_database_update(package, location):
    """READ ONLY.  Returns the plan; raises ValueError if anything is unsafe or there is nothing to do."""
    package = Path(package).expanduser().resolve(strict=True)
    scanner = fw._safe_root(location)
    from scanner_preflight import inspect_scanner
    report, valid = inspect_scanner(scanner)
    if not valid:
        raise ValueError('Scanner configuration preflight failed: ' + report[:700])
    identity = fw._identity(scanner)
    hpdb = scanner / 'HPDB'
    if hpdb.is_symlink() or not hpdb.is_dir():
        raise ValueError('The scanner has no HPDB folder (or it is a symbolic link).')
    analysis = analyze(package, hpdb)
    if not analysis['valid']:
        raise ValueError('The new database failed the safety checks:\n- ' + '\n- '.join(analysis['problems']))
    new, old = _files(package), _files(hpdb)
    names = [n for n in sorted(new) if n != CONFIG and new[n].read_bytes() != old[n].read_bytes()]
    if analysis['config_changed']:
        names.append(CONFIG)               # hpdb.cfg last, so it never describes files not yet written
    if not names:
        raise ValueError('The scanner already holds exactly this database. Nothing to update.')
    plans, total, biggest = [], 0, 0
    for name in names:
        proposed, original = new[name].read_bytes(), old[name].read_bytes()
        total += len(proposed)
        biggest = max(biggest, len(proposed))
        plans.append({'action': 'replace', 'relative': 'HPDB/' + name,
                      'source_sha256': hashlib.sha256(proposed).hexdigest(),
                      'target_sha256': hashlib.sha256(original).hexdigest(), 'bytes': len(proposed),
                      'changes': {'field_edits': 0, 'added': 0, 'deleted': 0}})
    if shutil.disk_usage(scanner).free < 2 * biggest + fw.MIN_FREE_MARGIN:
        raise ValueError('Insufficient FAT32 free space for staged writes and safety margin.')
    if os.statvfs(scanner).f_flag & getattr(os, 'ST_RDONLY', 1):
        raise ValueError('Scanner filesystem is mounted read-only.')
    return {'package': str(package), 'scanner': str(scanner), 'files': plans, 'identity': identity,
            'analysis': analysis, 'total_bytes': total}


def describe_plan(plan):
    a = plan['analysis']
    lines = ['Scanner database: %s' % (a['old_date'] or 'unknown date'),
             'New database:     %s' % (a['new_date'] or 'unknown date'), '',
             '%d state file(s) will be replaced (%d already identical)%s.' % (
                 len(a['changed_states']), a['unchanged_states'],
                 ' and hpdb.cfg' if a['config_changed'] else ''),
             '%d%% of the scanner\'s current records are unchanged in the new database.' % round(100 * a['similarity']),
             'Favorites lists, profile.cfg and every other file are not touched.']
    return '\n'.join(lines)


def database_update_eligibility(package, location):
    try:
        plan = prepare_database_update(package, location)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return False, str(exc)
    return True, describe_plan(plan) + '\nA fresh verified backup will be created BEFORE writing.'


def execute_database_update(package, location):
    first = prepare_database_update(package, location)
    scanner, backup_folder, written = Path(first['scanner']), None, []
    try:
        backup_folder, manifest = fw.backup_scanner(scanner)
        entries = {e['path']: e for e in manifest['files']}
        for item in first['files']:
            entry = entries.get(item['relative'])
            backup_file = backup_folder / 'BCDx36HP' / item['relative']
            if entry is None or entry['sha256'] != item['target_sha256'] or digest(backup_file) != item['target_sha256']:
                raise fw.FirstWriteError('Fresh scanner backup verification failed: ' + item['relative'])
        if prepare_database_update(package, location) != first:
            raise fw.FirstWriteError('Scanner, database or USB device changed during backup; write cancelled.')
        payloads = []
        for item in first['files']:
            destination = scanner / item['relative']
            proposed = (Path(first['package']) / Path(item['relative']).name).read_bytes()
            if hashlib.sha256(proposed).hexdigest() != item['source_sha256']:
                raise fw.FirstWriteError('Database file changed before write: ' + item['relative'])
            if digest(destination) != item['target_sha256']:
                raise fw.FirstWriteError('Scanner file changed before write: ' + item['relative'])
            payloads.append((item, destination, proposed))
        if fw._identity(scanner) != first['identity']:
            raise fw.FirstWriteError('USB device changed before write.')
        receipt = backup_folder / 'EXPORT_RECOVERY.txt'
        receipt.write_text(
            'Verified original scanner configuration backup: ' + str(backup_folder) + '\n'
            'MASTER DATABASE UPDATE. Files replaced in this update:\n' +
            ''.join('REPLACED (restore from backup): BCDx36HP/' + i['relative'] + '\n' for i in first['files']) +
            'To recover, copy every listed file from the BCDx36HP folder in this backup back onto the scanner.\n',
            encoding='utf-8')
        with receipt.open('rb') as stream:
            os.fsync(stream.fileno())
        fw._sync_dir(backup_folder)
        try:
            for item, destination, proposed in payloads:
                written.append((item, destination))
                if fw._identity(scanner) != first['identity']:
                    raise OSError('Scanner changed during database update.')
                if digest(destination) != item['target_sha256']:
                    raise OSError('Scanner changed during database update.')
                fw._stage_and_replace(destination, proposed, item['source_sha256'])
        except Exception as exc:
            errors = []
            for item, destination in reversed(written):
                try:
                    fw._undo(item, destination, backup_folder)
                except Exception as restore_error:
                    errors.append(item['relative'] + ': ' + str(restore_error))
            if errors:
                raise fw.FirstWriteError('Database update/rollback failed. DO NOT DISCONNECT; manually restore ALL '
                                         'listed files from ' + str(backup_folder) + ': ' + '; '.join(errors)) from exc
            raise fw.FirstWriteError('Database update failed; every changed file was restored from the verified '
                                     'backup. ' + str(exc)) from exc
        try:
            os.sync()
        except (AttributeError, OSError):
            pass
        result = {'kind': 'master-database-update', 'files': [i['relative'] for i in first['files']],
                  'backup': str(backup_folder), 'written_bytes': first['total_bytes'],
                  'old_date': first['analysis']['old_date'], 'new_date': first['analysis']['new_date'],
                  'written_utc': datetime.now(timezone.utc).isoformat(), 'device': first['identity']['source']}
        try:
            (backup_folder / 'EXPORT_RESULT.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        except OSError:
            pass
        return result
    except Exception as exc:
        if isinstance(exc, fw.FirstWriteError):
            raise
        raise fw.FirstWriteError(str(exc) + (f'\nVerified backup: {backup_folder}' if backup_folder else
                                             '\nNo scanner write was attempted before backup verification.')) from exc
