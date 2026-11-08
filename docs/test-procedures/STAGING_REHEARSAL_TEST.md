# v0.0.7k — One Kubuntu read-only test

1. Extract v0.0.7k into a new folder, launch `test-launch.sh`, and confirm the title shows **v0.0.7k**.
2. Connect your SDS100 in Mass Storage mode.
3. Select **File → Preview Scanner Export (Read-only)…**. Choose the local **test of file system** configuration, then your SDS100 Mass Storage root.
4. Wait for the existing progress window to finish. In the resulting report, locate **LOCAL STAGING AND ROLLBACK REHEARSAL — READ ONLY**.
5. Report the lines for **Candidate files to stage**, **Local staged copies**, **Injected interruption and simulated rollback**, and **Scanner writes** (or any **Rehearsal: BLOCKED** reason).

Expected when local and scanner files differ: SHA-256 verified; simulated interruption rollback PASSED; Scanner writes: 0; Export authorization: BLOCKED. If the files are identical, the report will explicitly say actual-file rehearsal skipped; that is not a failed test. Do not perform any scanner write.

## Remaining milestones after this test
- v0.0.7k: confirm local rehearsal results; on-device staging and identity checks remain unresolved.
- v0.0.7l: final native compatibility checks and integrate preview into a single Export to Scanner confirmation workflow (still fail-closed).
- v0.0.7m: first tightly limited SDS100 write ONLY if native, identity, staging, fresh-backup and recovery safety gates are actually validated. Otherwise defer the write and explain the blocker.
