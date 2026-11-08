# v0.0.6r — GUI Test 1

1. Launch with `test-launch.sh`.
2. Choose **File → Scanner Export Preflight (Read-only)…**.
3. Select the SDS100 Mass Storage drive root containing `BCDx36HP`.
4. Confirm a report displays file counts and checks, and explicitly says no files were modified.
5. Close the report. Do not use Export to Scanner; it is not enabled.

This release only checks directory structure; it does not write to the scanner or certify export safety.
