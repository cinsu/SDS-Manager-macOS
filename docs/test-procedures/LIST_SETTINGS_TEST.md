# Physical test: Favorites List settings

1. Open a local scanner configuration. Scanner Settings -> Favorites List Settings.
2. Pick one list you do not mind changing: give it a free Quick Key, rename it, switch Monitor, tick one system quick key (Edit keys...). Try giving it another list's Quick Key: Save must refuse with a clear message.
3. Save, review the change list, confirm.
4. File -> Export to Scanner. Preview should show f_list.cfg as the only replaced file.
5. After "File Verified", unmount in the file manager, wait for "safe to remove", then power the scanner off and on.
6. On the scanner: the list shows the new name and quick key, monitor state is as set, and nothing else moved.
7. Revert the same way and export again.
If anything is wrong send EXPORT_RECOVERY.txt from ~/.local/share/sds100-database-favorites-manager/scanner-backups/<newest>/ and the card's f_list.cfg.
