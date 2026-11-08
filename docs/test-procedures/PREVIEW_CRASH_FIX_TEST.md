# v0.0.7g2 Qt/Wayland preview crash regression

## Reproducing the reported failure

v0.0.7g1 exited with SIGABRT (134) during `QPlainTextEdit` construction in `_export_preview_show_result` after the background export audit. The C stack showed a Qt QObject connection mutex wait, while a QThread still existed. This is a suspected Qt/Wayland lifecycle deadlock; the log alone cannot prove the exact native root cause.

## Changes

The read-only preview no longer creates a modal progress dialog. It displays a status-bar message while the worker runs. After `QThread.finished`, the cleanup callback calls `wait(2000)` and retries if needed, then schedules the result report 300ms later. The report uses `show()` instead of a nested `exec()` loop.

## Kubuntu GUI test (required)

1. Extract v0.0.7g2 into a new folder, run `test-launch.sh`.
2. Confirm the title bar shows v0.0.7g2.
3. Run File -> Preview Scanner Export (Read-only) with `unchanged` and the SDS100 BCDx36HP folder.
4. Confirm the new `NATIVE FAVORITES SPEC FIELD MAPPING AUDIT — READ ONLY` section appears.
5. Close the report, then confirm menus are responsive. Upload report and logs if any crash.

This is a read-only test. Scanner export remains DISABLED.
