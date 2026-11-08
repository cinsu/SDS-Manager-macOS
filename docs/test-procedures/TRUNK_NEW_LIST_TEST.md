# Physical test: new list from a trunked system

1. Open the database, pick a P25 system (e.g. Palmetto 800).
2. Add to Favorites -> new list, name it, tick two sites (some frequencies) and a few talkgroups. Confirm the list appears with those items only.
3. File -> Export to Scanner. Preview should show ADD 1 and REPLACE f_list.cfg only.
4. After "File Verified", unmount/eject the scanner in the file manager, wait for "safe to remove", THEN power the scanner off.
5. Restart the scanner: the new list appears, can be enabled, and scans the selected talkgroups.
6. If anything is wrong, send EXPORT_RECOVERY.txt from ~/.local/share/sds100-database-favorites-manager/scanner-backups/<newest>/ and the new f_NNNNNN.hpd.
