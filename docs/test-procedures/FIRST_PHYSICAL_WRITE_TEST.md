# v0.0.7n — First controlled SDS100 scanner write

This release contains a **real scanner write path**. No simulated-write step is required.

**Prepare a clean candidate:** Connect the SDS100 in Mass Storage mode. Use **File → Import from Scanner…** to import the *current* scanner configuration under a NEW name such as `First Physical Write Test`. Do **not** use `unchanged2` because it contains a deleted HPD record. Open the new local configuration. In its Favorites Lists, edit **one conventional channel's frequency only** to another valid scanner-supported frequency using the existing Favorites editor. Choose **File → Save Configuration…** to persist the local edit. Leave all other files/fields unchanged.

**Perform the single hardware test:** Choose **File → Export to Scanner…**, select `First Physical Write Test` and the mounted SDS100 drive. The automatic preview must report **REPLACE: 1** and **READY FOR CONTROLLED FIRST WRITE**; otherwise **Cancel** and report the reason. When eligible, **Proceed with Export** becomes enabled. Click it and read the explicit **FIRST Physical SDS100 Write** warning. If you accept, choose **Yes**. Do not disconnect the scanner until the application reports the write result.

The program automatically creates and SHA-256 verifies a fresh backup of the scanner's supported BCDx36HP configuration files, revalidates the mount, USB identity, native file and expected checksums, stages the single HPD file on the scanner's FAT32 filesystem, renames it into place, and verifies the written file SHA-256. Backup files are stored under `~/.local/share/sds100-database-favorites-manager/scanner-backups/`. The backup includes a `FIRST_WRITE_RECOVERY.txt` instruction file.

After success, safely eject the SDS100 and restart it. Verify the Favorites List loads and the changed frequency appears. Report the application's completion message and the scanner's actual behavior. If the scanner rejects the edit, restore the original HPD from the fresh backup; do not attempt additional exports.

**Limits:** This release writes exactly one existing HPD containing exactly one C-Freq/T-Freq frequency-field edit. It does not write CFG/INF, add/delete records, or change multiple files. The recovery method for a power interruption is the verified local backup and manual restoration (including SD card reformat/reinitialization if needed), not a guarantee of FAT32 crash atomicity. Actual SDS100 acceptance is not yet proven until this test succeeds. No firmware or live GPS operations.
