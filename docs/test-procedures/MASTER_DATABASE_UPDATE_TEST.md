# Update Scanner's Master Database — test

1. Use Database -> Update Database... and wait for the offline rebuild to finish (skip if you already have a version).
2. Connect the SDS100 in mass-storage mode. Choose Database -> Update Scanner's Master Database..., pick the version, pick the SD card root.
3. Read the check result. If it says BLOCKED, copy the message to me; nothing has been written.
4. If it is eligible, note both dates and the number of state files, then confirm. Wait for the completion message.
5. Eject the card from the computer, wait, then power on the scanner. Check: the scanner boots, Menu -> Manage Favorites still lists your lists, a system you know changed shows the new data, and a favorites list scans as before.
6. If anything is wrong: restore from the backup folder named in the completion message (EXPORT_RECOVERY.txt lists every file replaced), or tell me the symptoms.
