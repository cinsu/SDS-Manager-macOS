## GUI test — import cancellation
1. Launch test-launch.sh; connect SDS100 in Mass Storage mode.
2. File → Import from Scanner; choose the scanner and a new unique name.
3. While file copy/verification is running, press Cancel import.
4. Expect Cancelling import… followed by Import cancelled. No configuration was saved.
5. Verify the named configuration was not added.
6. Do not disconnect scanner during import or cleanup.
