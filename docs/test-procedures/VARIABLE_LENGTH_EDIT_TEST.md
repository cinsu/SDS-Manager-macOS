# v0.0.7f1 test — one-digit TGID selection fix

Launch `test-launch.sh`, select File → Preview Scanner Export (Read-only), choose `unchanged`, and copy the **NATIVE FAVORITES VARIABLE-LENGTH FIELD EDIT AUDIT — READ ONLY** section. Confirm title displays v0.0.7f1 and report closes with responsive menus.

The earlier `favorites_lists/f_000015.hpd: line 133: shorter: no length change` warning should be absent. Expect zero warnings; the total number of probes may vary if a layout/file has no eligible multi-digit value. Any skipped cases must be reported separately rather than falsely counted as passing.

Scanner export remains disabled; no scanner files are written.
