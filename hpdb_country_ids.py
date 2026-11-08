# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Country IDs from user-provided MasterHpdb dated 2026-10-18; local master overrides."""
COUNTRY_BY_STATE_ID = {0: 0, 1: 1, 2: 1, 4: 1, 5: 1, 6: 1, 8: 1, 9: 1, 10: 1, 11: 1, 12: 1, 13: 1, 66: 1, 15: 1, 16: 1, 17: 1, 18: 1, 19: 1, 20: 1, 21: 1, 22: 1, 23: 1, 24: 1, 25: 1, 26: 1, 27: 1, 28: 1, 29: 1, 30: 1, 31: 1, 32: 1, 33: 1, 34: 1, 35: 1, 36: 1, 37: 1, 38: 1, 39: 1, 40: 1, 41: 1, 42: 1, 72: 1, 44: 1, 45: 1, 46: 1, 47: 1, 48: 1, 49: 1, 50: 1, 78: 1, 51: 1, 53: 1, 54: 1, 55: 1, 56: 1, 101: 2, 102: 2, 103: 2, 104: 2, 105: 2, 106: 2, 107: 2, 108: 2, 109: 2, 110: 2, 111: 2, 112: 2, 113: 2}

def load_country_ids(folder):
    from pathlib import Path
    import re
    mapping = dict(COUNTRY_BY_STATE_ID)
    master = Path(folder) / "MasterHpdb.hp1"
    if master.is_file():
        with master.open("r", encoding="cp1252", errors="replace") as handle:
            for line in handle:
                if not line.startswith("StateInfo\t"):
                    continue
                state = re.search(r"(?:^|\t)StateId=(\d+)(?:\t|$)", line)
                country = re.search(r"(?:^|\t)CountryId=(\d+)(?:\t|$)", line)
                if state and country:
                    mapping[int(state.group(1))] = int(country.group(1))
    return mapping
