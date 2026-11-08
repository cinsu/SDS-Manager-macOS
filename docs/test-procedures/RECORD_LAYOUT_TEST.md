# v0.0.7c — Read-only record layout audit

Launch `test-launch.sh`, connect SDS100 in Mass Storage, File → Preview Scanner Export (Read-only)…, choose `unchanged`. Paste the **NATIVE FAVORITES RECORD LAYOUT AUDIT — READ ONLY** section. Verify dialog closes and menus remain responsive. Do not export to scanner.

The audit counts tab-separated fields for C-Freq, T-Freq and TGID records and flags missing/non-decimal column 6. It does not establish native field semantics or permit writes.
