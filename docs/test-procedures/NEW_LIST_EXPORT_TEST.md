# v0.0.8h physical test — new and removed lists (REAL SCANNER WRITE)

Do this with a configuration you can restore, and keep the SDS100 in Mass Storage mode.

A. New list
1. Open a saved configuration, Add to Favorites → create a new list with a few conventional channels, Save Configuration.
2. File → Export to Scanner… The preview should show ADD: 1 and REPLACE including favorites_lists/f_list.cfg, and say
   READY FOR CONTROLLED CONFIGURATION EXPORT. Proceed.
3. Safely eject, power the scanner on. Check: the list appears under Favorites Lists, can be enabled and scanned, channels
   have the right frequency/tone/modulation. Copy the new list file and f_list.cfg back off the scanner and send them to me.

B. Remove a list
1. In the program use Favorites → Delete Favorites List… on a list you created in step A, Save Configuration.
2. Export to Scanner… The preview should show REMOVE FROM SCANNER: 1. Proceed.
3. Check that the list is gone from the scanner and the other lists are intact.

If anything looks wrong, the verified pre-export backup is named in the result window and EXPORT_RECOVERY.txt inside it
lists exactly what to restore.
