# Physical test: searches and tools

1. Open the settings dialog and check the new tabs match what the scanner shows (Limit Search names and ranges, Tone-Out slots, band defaults).
2. Change a few things: rename one Limit Search and set its range and step, set a Tone-Out frequency and tones, change a Waterfall span or colour, tick a broadcast screen. Try a Limit Search with the lower frequency above the upper one: Save must refuse.
3. Save, review, then File -> Export to Scanner (only profile.cfg should be replaced). After "File Verified", unmount, wait for "safe to remove", power the scanner off and on.
4. On the scanner open Limit Search, Tone-Out and Waterfall and confirm the new values. Change them back and export again.
If anything is wrong send EXPORT_RECOVERY.txt from ~/.local/share/sds100-database-favorites-manager/scanner-backups/<newest>/ and the card's profile.cfg.
