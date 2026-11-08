# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Link with SDS100 Monitor (personal build): "Edit in Manager" and names for unnamed talkgroups.

* Edit in Manager: the Monitor sends {system, department, channel, frequency, tgid} for a channel
  or talkgroup it heard. The running Manager receives it over a local socket on this computer only
  (QLocalServer, named per user); if none is running, the Monitor starts the Manager with
  --open-entry <JSON>, and a second copy hands the request to the first and exits. The Manager then
  finds the entry in the open configuration's Favorites Lists and opens the list editor on it.
* Unnamed talkgroups: talkgroups in the open lists with no real name get suggestions from the master
  database (same TGID, same system name first) and from what the Monitor recorded (the name the
  scanner showed while scanning, and your Analyze notes). Nothing changes until you tick and confirm;
  the change is one Undo step and, like every edit, reaches the scanner only through Export.

The Monitor's files (~/SDS100Monitor) are only ever read.
"""
import csv
import json
import os
import re
from collections import Counter
from pathlib import Path

SERVER_NAME = f"sds100-database-favorites-manager-{os.getuid()}"
REQUEST_KEYS = ("system", "department", "channel", "frequency", "tgid")
MONITOR_HISTORY_HEADERS = ["Start", "End", "Duration (s)", "System", "Department",
                           "Channel", "Frequency", "Talkgroup", "RSSI (dBm)"]
MONITOR_FOUND_HEADERS = ["Kind", "ID", "First seen", "Last seen", "Calls", "Seen with", "Notes"]
MAX_NAME = 64


def monitor_data_dir():
    return Path.home() / "SDS100Monitor"


# ---- requests from the Monitor ------------------------------------------------------------------
def clean_request(data):
    """A request dict with only known keys and short strings, or None if there is nothing to find."""
    if isinstance(data, (str, bytes)):
        try:
            data = json.loads(data)
        except (ValueError, UnicodeDecodeError):
            return None
    if not isinstance(data, dict):
        return None
    out = {k: str(data.get(k) or "").strip()[:200] for k in REQUEST_KEYS}
    out["tgid"] = re.sub(r"^(TGID|TG)\s*[:=]?\s*", "", out["tgid"], flags=re.I)
    if not out["tgid"].isdigit():
        out["tgid"] = ""
    mhz = re.sub(r"\s*MHz$", "", out["frequency"], flags=re.I)
    try:
        out["frequency"] = f"{float(mhz):.6f}" if 25 <= float(mhz) <= 1300 else ""
    except ValueError:
        out["frequency"] = ""
    # v0.1.18: "add" puts something heard into a Favorites List; "edit" (the default) opens it.
    out["action"] = "add" if str(data.get("action") or "") == "add" else "edit"
    modulation = str(data.get("modulation") or "").strip().upper()
    out["modulation"] = modulation if modulation in ("AUTO", "FM", "NFM", "AM") else "AUTO"
    return out if (out["tgid"] or out["frequency"]) else None


def describe_request(req):
    what = f"talkgroup {req['tgid']}" if req["tgid"] else f"{req['frequency'].rstrip('0').rstrip('.')} MHz"
    where = " › ".join(p for p in (req["system"], req["department"], req["channel"]) if p and p != "—")
    return what + (f" ({where})" if where else "")


def _same(a, b):
    return bool(a) and bool(b) and a.strip().casefold() == b.strip().casefold()


def list_label(draft_name):
    return re.sub(r" \(editable copy\)( \d+)?$", "", draft_name)


def find_entries(drafts, req):
    """Where the requested talkgroup or frequency is in the open drafts, best match first:
    [{draft, entry_index, group_index, row_index, label, score}]."""
    matches = []
    want_hz = round(float(req["frequency"]) * 1_000_000) if req.get("frequency") else None
    for draft, entries in drafts.items():
        for entry_index, entry in enumerate(entries or []):
            if entry.get("scope") == "metadata":
                continue
            system = entry.get("name", "")
            group_index, group_name = None, ""
            for row_index, row in enumerate(entry.get("records", [])):
                if not row:
                    continue
                kind = row[0].strip()
                if kind in ("C-Group", "T-Group", "Site"):
                    group_index, group_name = row_index, (row[3] if len(row) > 3 else "")
                    continue
                value = row[5].strip() if len(row) > 5 else ""
                hit = False
                if req.get("tgid") and kind == "TGID":
                    hit = value.lstrip("0") == req["tgid"].lstrip("0")
                elif want_hz is not None and kind == "C-Freq" and value.isdigit():
                    hit = abs(int(value) - want_hz) <= 50
                if not hit:
                    continue
                name = row[3] if len(row) > 3 else ""
                score = (4 if _same(system, req.get("system")) else 0) \
                    + (2 if _same(group_name, req.get("department")) else 0) \
                    + (1 if _same(name, req.get("channel")) else 0)
                label = " › ".join(p for p in (list_label(draft), system, group_name, name or "(no name)") if p)
                matches.append({"draft": draft, "entry_index": entry_index, "group_index": group_index,
                                "row_index": row_index, "label": label, "score": score})
    matches.sort(key=lambda m: (-m["score"], m["label"].casefold()))
    return matches


def pick_match(matches):
    """The match to open without asking, or None if the user should choose."""
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1 and matches[0]["score"] >= 4 and matches[0]["score"] > matches[1]["score"]:
        return matches[0]
    return None


# ---- unnamed talkgroups -------------------------------------------------------------------------
# "44353", "TGID 44353", "TG:44353", "Talkgroup 44353", "ID=44353", or a hex ID like "AD41h".
_PLACEHOLDER = re.compile(r"^(?:(?:tgid|tg|talk ?group|id)\s*[:#=]?\s*)?\d+$|^(?=[0-9a-f]*\d)[0-9a-f]+h$", re.I)
PLACEHOLDER_WORDS = {"", "unknown", "new talkgroup", "new tgid", "unnamed", "(unnamed)", "no name", "tbd", "?"}


def is_placeholder_name(name, tgid=""):
    """True for a talkgroup name that is really no name: blank, the ID itself, 'TGID 44353', 'Unknown'."""
    text = (name or "").strip()
    if text.casefold() in PLACEHOLDER_WORDS or text.startswith("Id="):
        return True
    if tgid and text.replace(" ", "").lstrip("0") == tgid.lstrip("0"):
        return True
    return bool(_PLACEHOLDER.match(text))


def unnamed_talkgroups(drafts):
    """[{draft, entry_index, row_index, system, department, tgid, name}] in the open drafts."""
    out = []
    for draft, entries in drafts.items():
        for entry_index, entry in enumerate(entries or []):
            if entry.get("scope") == "metadata":
                continue
            department = ""
            for row_index, row in enumerate(entry.get("records", [])):
                if not row:
                    continue
                if row[0].strip() == "T-Group":
                    department = row[3] if len(row) > 3 else ""
                    continue
                if row[0].strip() != "TGID" or len(row) <= 5:
                    continue
                tgid = row[5].strip()
                if tgid.isdigit() and is_placeholder_name(row[3], tgid):
                    out.append({"draft": draft, "entry_index": entry_index, "row_index": row_index,
                                "system": entry.get("name", ""), "department": department, "tgid": tgid.lstrip("0") or "0",
                                "name": row[3]})
    return out


def monitor_heard_names(data_dir=None):
    """{tgid: {system (folded): (name, last time)}} from the Monitor's reception history: the name the
    scanner showed for the talkgroup (real names only, newest wins)."""
    folder = Path(data_dir or monitor_data_dir()) / "history"
    names = {}
    for path in sorted(folder.glob("reception_history_????-??-??.csv")):
        try:
            with path.open(newline="", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                if next(reader, None) != MONITOR_HISTORY_HEADERS:
                    continue
                for row in reader:
                    if len(row) != len(MONITOR_HISTORY_HEADERS):
                        continue
                    tgid = re.sub(r"^TGID\s*:?\s*", "", row[7].strip(), flags=re.I).lstrip("0")
                    name = row[5].strip()
                    if not tgid.isdigit() or name in ("", "—") or is_placeholder_name(name, tgid):
                        continue
                    per = names.setdefault(tgid, {})
                    key = row[3].strip().casefold()
                    if key not in per or row[0] >= per[key][1]:
                        per[key] = (name[:MAX_NAME], row[0])
        except (OSError, csv.Error, UnicodeDecodeError):
            continue
    return names


def monitor_notes(data_dir=None):
    """{tgid: note} from the Monitor's Analyze → Found IDs notes for talkgroups."""
    path = Path(data_dir or monitor_data_dir()) / "analyze_found_ids.csv"
    notes = {}
    try:
        with path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            if next(reader, None) != MONITOR_FOUND_HEADERS:
                return notes
            for row in reader:
                if len(row) == len(MONITOR_FOUND_HEADERS) and row[0] == "Talkgroup" and row[6].strip():
                    tgid = re.sub(r"\D", "", row[1]).lstrip("0")
                    if tgid:
                        notes[tgid] = row[6].strip().splitlines()[0][:MAX_NAME]
    except (OSError, csv.Error, UnicodeDecodeError):
        pass
    return notes


def database_names(database_root, wanted, cancel=None, progress=None):
    """{tgid: [(system, department, name)]} for the wanted talkgroup IDs, from the master database."""
    found = {t: [] for t in wanted}
    if not database_root or not wanted:
        return found
    files = sorted(Path(database_root).glob("s_*.hpd"))
    for index, path in enumerate(files):
        if cancel is not None and cancel():
            break
        if progress is not None:
            progress(index, len(files))
        system = department = ""
        try:
            text = path.read_bytes().decode("cp1252", "replace")
        except OSError:
            continue
        for line in text.splitlines():
            if not line.startswith(("Trunk", "T-Group", "TGID")):
                continue
            f = line.split("\t")
            if f[0] == "Trunk":
                system, department = (f[3] if len(f) > 3 else ""), ""
            elif f[0] == "T-Group":
                department = f[3] if len(f) > 3 else ""
            elif f[0] == "TGID" and len(f) > 5:
                tgid = f[5].strip().lstrip("0")
                name = f[3].strip()
                if tgid in found and name and not is_placeholder_name(name, tgid):
                    found[tgid].append((system, department, name))
    return found


def suggest(item, db, heard, notes):
    """[(name, where it came from)] for one unnamed talkgroup, best first, no repeats."""
    out = []
    system = item["system"].strip().casefold()
    tgid = item["tgid"]
    same_db = [d for d in db.get(tgid, []) if d[0].strip().casefold() == system]
    for sys_name, dept, name in same_db:
        out.append((name, f"Database: {sys_name} › {dept}"))
    per = heard.get(tgid, {})
    if system in per:
        out.append((per[system][0], f"Monitor heard it as this ({per[system][1][:10]})"))
    if tgid in notes:
        out.append((notes[tgid], "Your note in the Monitor's Analyze → Found IDs"))
    other_db = [d for d in db.get(tgid, []) if d not in same_db]
    if len({n.casefold() for _s, _d, n in other_db}) == 1:   # only when every other system agrees
        out.append((other_db[0][2], f"Database, another system: {other_db[0][0]}"))
    for sys_key, (name, when) in per.items():
        if sys_key != system:
            out.append((name, f"Monitor heard it on another system ({when[:10]})"))
    seen, unique = set(), []
    for name, source in out:
        if name.casefold() not in seen:
            seen.add(name.casefold())
            unique.append((name[:MAX_NAME], source))
    return unique


def valid_name(name, encoding="cp1252"):
    name = name.strip()
    if not name or len(name) > MAX_NAME or any(c in name for c in "\t\r\n\x00"):
        return False
    try:
        name.encode(encoding)
    except (UnicodeError, LookupError):
        return False
    return True


def apply_names(drafts, changes):
    """Set names: changes = [(item, new name)]. Returns the number changed (unchanged rows skipped)."""
    count = 0
    for item, name in changes:
        row = drafts[item["draft"]][item["entry_index"]]["records"][item["row_index"]]
        if row[0].strip() != "TGID" or row[5].strip().lstrip("0") != item["tgid"]:
            raise ValueError(f"The list changed since it was read (talkgroup {item['tgid']}).")
        if row[3] != name:
            row[3] = name
            count += 1
    return count


def newest_version_key(name):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)([a-z]?)", name)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)) if m else (0, 0, 0, "")


# ---- adding something heard to a Favorites List (v0.1.18) -----------------------------------------------
def add_targets(drafts, req):
    """Departments it can go into: [{'label', 'draft', 'entry_index', 'group_index', 'preferred'}].
    A talkgroup goes into a talkgroup department of a trunked system (the same-named system first); a
    channel into a conventional department."""
    kind = 'T-Group' if req['tgid'] else 'C-Group'
    found = []
    for draft, entries in drafts.items():
        for ei, entry in enumerate(entries):
            records = entry.get('records') or []
            if entry.get('scope') == 'metadata' or not records:
                continue
            system = records[0][3] if len(records[0]) > 3 else ''
            if kind == 'T-Group' and not any(r[0] == 'TGID' for r in records):
                continue                                    # a talkgroup copies another one's layout
            for ri, row in enumerate(records):
                if row[0] == kind:
                    found.append({'label': f'{list_label(draft)} › {system} › {row[3]}', 'draft': draft,
                                  'entry_index': ei, 'group_index': ri,
                                  'score': 2 * _same(row[3], req['department']) + _same(system, req['system'])})
    for target in found:
        target['preferred'] = target['score'] > 0
    found.sort(key=lambda t: (-t['score'], t['label'].casefold()))       # same department, then same system
    return found


def suggested_name(req):
    """The name the scanner showed, unless it was only a number or a frequency."""
    name = req.get('channel', '').strip()
    if not name or re.fullmatch(r'[\d.\s]+(MHz)?', name, flags=re.I) or name == req.get('tgid'):
        return ''
    return name[:64]


def add_heard(drafts, target, req, name, modulation='AUTO', tone=''):
    """Put the channel or talkgroup into the target department. Returns the new row's index; raises
    ValueError (with a plain reason) when it is already there or can't be added."""
    import hand_entry
    records = drafts[target['draft']][target['entry_index']]['records']
    start = target['group_index']
    end = next((i for i in range(start + 1, len(records))
                if records[i][0] in ('C-Group', 'T-Group', 'Site', 'Trunk', 'Conventional')), len(records))
    if req['tgid']:
        if any(r[0] == 'TGID' and r[5].strip() == req['tgid'] for r in records):
            raise ValueError(f'Talkgroup {req["tgid"]} is already in this system.')
        template = next(r for r in records if r[0] == 'TGID')
        row = hand_entry.talkgroup_row(template, name, req['tgid'])
    else:
        item = hand_entry.channel(name, req['frequency'], modulation, tone)
        row = hand_entry.channel_row(item)
        if any(r[0] == 'C-Freq' and r[5] == row[5] and r[7] == row[7] for r in records[start:end]):
            raise ValueError('That frequency (with the same tone) is already in this department.')
    records.insert(end, row)
    return end

