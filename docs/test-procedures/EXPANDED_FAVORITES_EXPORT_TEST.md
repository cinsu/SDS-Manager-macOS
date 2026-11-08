# v0.0.7o — One SDS100 physical export test: delete one channel

This release builds directly on the v0.0.7n write you already tested successfully. **Only one GUI/hardware test is requested.**

1. Extract v0.0.7o into a **new** folder and run `test-launch.sh`. Connect the SDS100 in Mass Storage mode.
2. Use **File → Import from Scanner…** to create a new local configuration named `Leaf Deletion Test` (or another unused name). This ensures it matches the scanner *after* the successful v0.0.7n write. Do not use an older stale configuration for this test.
3. Open that local configuration in the existing Favorites editor. Choose **one nonessential conventional channel** in an existing Favorites List, use **Delete Channel…**, and confirm. Do not delete a system, department, site, or multiple records.
4. Use **File → Save Configuration…** to save the edited local configuration. No scanner files change yet.
5. Use **File → Export to Scanner…**, select the saved `Leaf Deletion Test` configuration and SDS100 drive. The automatic preview should show **REPLACE: 1** and **READY FOR CONTROLLED FAVORITES EXPORT**. The eligibility reason should report **0 field edits, 0 additions, 1 deletion**. If anything differs, choose **Cancel** and share the reason instead of proceeding.
6. Click **Proceed with Export**, read the physical-write warning, and confirm. Wait for the success message and note the new verified backup location. Do not disconnect while writing.
7. Safely eject and restart the SDS100. Verify the chosen channel is gone and neighboring channels and the Favorites List still load normally.

**Report:** whether the preview allowed the deletion, whether the write completed successfully, and whether the SDS100 accepted the updated Favorites List after restart. If the scanner fails to load the list, stop and restore the original HPD from the fresh verified backup identified by the application.

This test checks one real structural deletion, not all new capabilities. The app deliberately blocks mixed structural + field edits, multiple changed HPD files, and opaque settings files for now.
