# v0.0.7g3 — visible export-preview progress (Kubuntu GUI test)

The v0.0.7g2 audit completed successfully but provided no clearly visible feedback while working. v0.0.7g3 restores a **visible, non-modal** progress window. The animated progress bar indicates unknown-duration work; the elapsed time label changes every second. This is NOT a percent-complete measurement.

## One GUI test
1. Extract this release to a new folder, run `test-launch.sh`.
2. Verify the title bar says v0.0.7g3.
3. Select File > Preview Scanner Export (Read-only), choose `unchanged` and your SDS100 BCDx36HP root.
4. Confirm the **Scanner Export Preview — Working (READ ONLY)** dialog appears immediately, with an animated busy bar and an increasing elapsed-seconds counter.
5. Wait for it to disappear and the report to open. Close the report and check the main-window menus still work.
6. If a crash occurs, provide crash logs; do not repeatedly run a failing release.

The progress dialog is non-modal to avoid the previously reported Qt/Wayland modal dialog teardown issue. The scanner remains read-only, and Export to Scanner is DISABLED.
