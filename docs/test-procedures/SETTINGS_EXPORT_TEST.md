# Physical test: core settings export

1. Open a local scanner configuration. Scanner Settings -> Global, Search and Weather Settings.
2. Change a few harmless values: Volume, Squelch, Key Beep, Close Call Alert Color, Weather delay, a SAME group name. Save (review list should name each change).
3. File -> Export to Scanner. Preview should show profile.cfg as the only replaced file.
4. After "File Verified", unmount the scanner in the file manager, wait for "safe to remove", then power it off and on.
5. Check on the scanner: volume/squelch, beep, Close Call colour, weather settings and SAME names show the new values and nothing else changed.
6. Change them back the same way and export again to confirm the round trip.
If anything is wrong send EXPORT_RECOVERY.txt from ~/.local/share/sds100-database-favorites-manager/scanner-backups/<newest>/ and the card's profile.cfg.
