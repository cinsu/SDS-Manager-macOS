# v0.0.7l — One Kubuntu GUI test (read-only)

1. Extract v0.0.7l in a **new** folder and launch `test-launch.sh`.
2. Connect SDS100 in Mass Storage mode.
3. Choose **File → Export to Scanner…** (not the diagnostic preview in Tools).
4. Select the saved **test of file system** local configuration and the SDS100 drive.
5. After automatic progress and comparison, verify **Export to Scanner — Preview & Confirmation** opens and shows ADD/REPLACE/UNCHANGED counts. Confirm **Cancel** is available and **Proceed with Export** is **disabled**. If `app_data.cfg` is still the only changed file, the preview should explain that it is not a certified first-write candidate.
6. Click **Cancel**. Confirm the scanner was not written.

Send whether the dialog appeared with Proceed disabled, or an error message. Do not attempt scanner writes.

## Remaining milestones after this test

- v0.0.7l: validate the integrated export-preview GUI and candidate-specific blocker reporting.
- v0.0.7m (target, not unconditional authorization): implement and test trustworthy identity authorization, native compatibility for the selected limited HPD change, fresh verified backup, FAT32-safe staged write and rollback, and post-write validation. **If any safety gate remains unresolved, do not write; release a corrective build instead.**
