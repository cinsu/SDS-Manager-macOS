# v0.0.7h — one offline GUI test

This release reuses the EXISTING Favorites editor and **Save Configuration…**. It does not edit scanner media.

1. Extract into a NEW folder, launch `test-launch.sh`, confirm title v0.0.7h.
2. File > Open Scanner Configuration… > choose a LOCAL configuration you are comfortable editing (ideally a test configuration).
3. In Favorites Lists choose an imported list containing a conventional channel; right-click the list and choose Edit Favorites List…, edit **one conventional channel frequency** (e.g. +0.012500 MHz, if valid), and confirm the editor's change.
4. File > Save Configuration…; confirm the LOCAL file update and backup. Close/reopen that local configuration and check the changed frequency is displayed.
5. Verify the main window still responds. **Do not use Export to Scanner**; it remains disabled.

Report whether the frequency persisted and any errors. The next release will target Save As and independent local configurations.

**After this testing phase, remaining target releases to first controlled scanner write:** v0.0.7i (Save As/independent configuration persistence), v0.0.7j (scanner identity), v0.0.7k (staging/rollback/storage), v0.0.7l (final export safety validation), v0.0.7m (limited verified SDS100 write, only if gates pass).
