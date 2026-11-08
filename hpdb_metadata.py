# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Read-only HPDB metadata inspection. No network or firmware operations."""
from pathlib import Path
import re
from datetime import datetime

def inspect_hpdb(folder):
    folder = Path(folder).expanduser().resolve()
    cfgs = [folder / n for n in ("hpdb.cfg", "HPDB.config", "hpdb.config", "HPDB.cfg")]
    cfg = next((p for p in cfgs if p.is_file()), None)
    states = list(folder.glob("s_*.hpd"))
    result = {"path": str(folder), "state_files": len(states),
              "catalog": str(cfg) if cfg else "Not found",
              "version": "Not found", "date": "Not found",
              "total_bytes": sum(p.stat().st_size for p in states)}
    if not cfg:
        return result
    with cfg.open("r", encoding="cp1252", errors="replace") as stream:
        for line in stream:
            fields = line.strip().split("\t")
            if not fields:
                continue
            key = fields[0].strip().casefold()
            if key in ("datemodified", "dbversion", "databaseversion", "version"):
                val = " ".join(fields[1:]).strip()
                if val:
                    result["version"] = val
                    if key == "datemodified":
                        result["date"] = val
            elif "date" in key and len(fields) > 1 and result["date"] == "Not found":
                result["date"] = " ".join(fields[1:]).strip()
    return result
