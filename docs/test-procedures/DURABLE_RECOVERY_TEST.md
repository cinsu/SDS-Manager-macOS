# v0.0.7m — One Kubuntu GUI test (scanner stays read-only)

1. Extract v0.0.7m into a NEW folder and run `test-launch.sh`. Confirm title v0.0.7m.
2. Connect the SDS100 in Mass Storage mode. Choose **File → Export to Scanner…**.
3. Select the existing saved **unchanged2** configuration and the SDS100 drive.
4. Wait for the **Export to Scanner — Preview & Confirmation** dialog. Confirm **Cancel** works and **Proceed with Export** is DISABLED.
5. Click **Show technical details**. Find **DURABLE WRITE/RESTART RECOVERY REHEARSAL — LOCAL MOCK ONLY**. Send that section (including any BLOCKED message) and confirm the app stayed responsive.

Expected on a suitable separate local temporary filesystem: a SHA-256 verified mock backup, successful mock commit, and **Restart recovery after journal/stage/replacement interruption: PASSED (3/3)**. A synthetic one-field mock candidate is expected if `unchanged2` still contains a deleted HPD record. The actual structural change remains unsupported and no scanner file is written.

**Remaining before a physical first write:** trustworthy SDS100 model authorization; verified native candidate and scanner acceptance; an actual FAT32-safe transaction/recovery design and prewrite revalidation; fresh full verified scanner backup immediately before writing; a controlled physical test. These are conditional safety gates, not claims of completion.
