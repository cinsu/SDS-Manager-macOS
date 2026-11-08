# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Read-only check of Uniden's documented SDS100 download page.
No speculative HPDB endpoints, no executable downloads, no firmware operations.
"""
import html
import re
import urllib.request
from datetime import datetime, timezone

OFFICIAL_URL = "https://my.uniden.com/downloads.cfm?product=SDS100"

def check_official_source(timeout=12):
    request = urllib.request.Request(
        OFFICIAL_URL, headers={"User-Agent": "SDS100Monitor/24 (Kubuntu; database status only)",
                               "Accept": "text/html"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        final = response.geturl()
        if not final.startswith("https://") or not final.split("/")[2].endswith("uniden.com"):
            raise ValueError("Official source redirected outside Uniden's HTTPS domain")
        raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError("Official page exceeds safe status-check size")
        page = raw.decode("utf-8", errors="replace")
    plain = re.sub(r"<[^>]+>", " ", page)
    plain = html.unescape(re.sub(r"\s+", " ", plain))
    versions = re.findall(r"(?:Sentinel(?:_Version)?|BCDx36HP_Sentinel_Version)[_\s.-]*(\d+[_\.]\d+[_\.]\d+)", plain, re.I)
    return {
        "url": final,
        "checked_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "page_mentions_sentinel": "Sentinel" in plain,
        "sentinel_versions": list(dict.fromkeys(v.replace("_", ".") for v in versions))[:8],
        "master_hpdb_download_verified": False,
        "note": "The official SDS100 download page advertises Sentinel software. "
                "It does not establish a standalone Master HPDB download API. "
                "A newer Sentinel version is NOT an HPDB database version."
    }
