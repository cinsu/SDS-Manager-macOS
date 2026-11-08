# v0.0.7g1 — Spec Field Mapping Audit (read-only)

1. Extract into a new folder and launch `test-launch.sh`.
2. Confirm title bar reads **v0.0.7g1**.
3. In **File → Preview Scanner Export (Read-only)…**, choose saved configuration **unchanged** and the SDS100 BCDx36HP folder.
4. Copy the **NATIVE FAVORITES SPEC FIELD MAPPING AUDIT — READ ONLY** section of the report, including any warnings.
5. Close the report and confirm the menus still respond.

**Expected:** approximately 1,930 C-Freq, 15,077 T-Freq, and 1,026 TGID records in 28 Favorites files (counts may vary if configuration changes). T-Freq 9-column records should be reported as *undocumented trailing fields*, not discarded or reinterpreted. We will review any format warnings rather than automatically rewrite records.

This is a **read-only** observational check against the published column positions. It does not establish native edited-file serialization or SDS100 scanner acceptance. Export to Scanner remains **DISABLED**. No firmware or live GPS operations.
