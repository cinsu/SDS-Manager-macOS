# v0.0.8g — Add to Favorites: new Favorites List (GUI test, Kubuntu)

Local configuration only. The scanner is never written by this test.

1. Open a saved scanner configuration.
2. In Database Contents select a CONVENTIONAL system, click **＋ Add to Favorites →**.
3. The dialog offers **Add to an existing Favorites List** (dropdown of loaded lists) and
   **Create a new Favorites List with this selection** (name box).
4. Choose the new-list option, enter a name, OK, pick departments/channels, confirm.
   Expect: the list appears in the Favorites Lists dropdown and tree, already containing the channels.
5. Repeat but Cancel at the channel-selection or confirmation step. Expect: no list created.
6. Try a duplicate name, then a TRUNKED system with "new list". Expect a clear refusal, nothing created.
7. File → Save Configuration, then reopen the configuration: the new list is still there.
8. Favorites → Delete Favorites List… on the new list. Expect it disappears from the dropdown and that
   Save Configuration still works (no error about a missing file).
9. Confirm Favorites menu no longer has **Create Favorites List…**.

Row layouts and defaults were checked against real SDS100 files and Uniden's File Specification V2.00.
Still unverified on hardware: that the scanner accepts the new list. After the test, copy the scanner's own
version of the new list back and compare it with what this program wrote.
Export to Scanner still cannot add or remove list files; do not use it with a new or deleted list.
