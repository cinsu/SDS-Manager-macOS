# v0.0.7p — One GUI test: restore a deleted channel to its existing department

This test targets the bug reported after v0.0.7o. Use a **fresh local configuration** imported from your SDS100 after the successful channel-deletion test. Do not reuse an older pre-deletion configuration.

1. Extract v0.0.7p into a new folder and launch `test-launch.sh`.
2. Connect the SDS100 in Mass Storage mode. Use **File → Import from Scanner…**, create a new local configuration, and open it in the Favorites workspace.
3. Select the Favorites List containing the existing conventional system and department from which you deleted the channel. Find the deleted channel in **Database Contents**, choose **Add to Favorites**, check **only that channel**, and confirm the preview. It should explicitly indicate that it will merge into the **existing** system and department, preserving their headers.
4. Expand the Favorites tree. Confirm **one system and one department** exist and that the restored channel appears alongside the existing channels. Save the local configuration.
5. Open **File → Export to Scanner…**. Expect one changed Favorites HPD file and **one added leaf record**, not an added department or system. If the preview says unsupported, shows unexpected changes, or displays duplicate departments, **Cancel** and report the exact message. Otherwise, confirm the write, safely eject, restart the scanner, and verify the channel appears under the original department.

Note: A newly restored channel inherits the other settings from a native channel already in the destination department; only its name and frequency come from the database. Review/edit the other channel settings afterward as needed. This initial test should not combine such setting edits with the structural addition in the same export.

**Report:** Whether the Favorites tree has only one department, whether export shows exactly one added channel, and whether the SDS100 loads it under that department after restart.

**Limits:** New departments, empty departments with no native channel template, duplicate system/department names, and frequency collisions are blocked for scanner-native additions in this fix. Other v0.0.7o export limitations remain unchanged.
