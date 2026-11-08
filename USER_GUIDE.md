# SDS-Manager — User Guide

A native Kubuntu application for managing a Uniden SDS100: update its system database, build and edit Favorites Lists, and change scanner settings, without Sentinel.

## The safety model (read this once)

1. **You always work on a local copy first.** *Open Scanner Configuration…* (or *Import from Scanner…*) copies the scanner's configuration into the application's library. Every edit changes that copy only. The scanner is never touched until you export.
2. **Nothing is written without a check.** Before any write the application validates every changed file against Uniden's file specification and against real files from a working SDS100. A change it does not fully understand is refused, not guessed at.
3. **Every write is backed up first.** A fresh, SHA-256-verified backup of the scanner's configuration (favorites lists, settings and the master database) is created before the first byte is written. Files are staged, verified, then swapped in. If anything fails part-way, every changed file is restored automatically.
4. **You confirm each write.** The preview shows exactly what will change. Cancel at any point to leave the scanner untouched.
5. **Eject before you power off.** After a write, eject or safely remove the SD card from your computer and wait for it to finish before switching the scanner on. Unplugging early can leave a file empty on the card.

## Typical workflows

### Update the scanner's system database
1. **Database → Update Database (Rebuild from Archive)…** — choose a Uniden master database archive (`MasterHpdb_MM_DD_YYYY.gz`). The application rebuilds the 70 database files locally from it. This takes several minutes and does not touch the scanner.
2. Connect the SDS100 in mass-storage mode.
3. **Database → Update Scanner's Master Database…** — pick the rebuilt version, then the SD card root (the folder containing `BCDx36HP`).
4. A read-only check runs first. It shows the scanner's database date, the new date, how many state files change, and refuses an older database, a different set of states, or a rebuild that does not match what the card holds. Nothing is written yet.
5. Confirm. The application backs up, writes only the files that changed (`hpdb.cfg` last), verifies them, and tells you where the backup is. Eject the card before powering on.

Your Favorites Lists, settings and every other file are not touched by a database update.

### Update the scanner's firmware
**Scanner Settings → Update Scanner Firmware…** puts new firmware on the scanner the same way Sentinel does: it writes the files to the card's `BCDx36HP/firmware` folder, and the scanner installs them itself the next time it starts from its own card.

1. Connect the SDS100 in mass-storage mode. The window shows the model and the main firmware version from the card (for example *SDS100 • main firmware 1.26.01*) and any files already waiting in the firmware folder.
2. Download the firmware from Uniden's support page (info.uniden.com → SDS100 Firmware Update) and use **Add File…** with the `.zip`, `.bin` or `.firm` file; zips are read without unpacking.
3. **Write to Scanner…** checks the files and shows exactly what will be written. Confirm, and the files are written and read back.
4. Eject the scanner in your file manager, then unplug the USB cable. The scanner checks each file is for this model and that its checksum is good, installs it, and deletes it. Follow its on-screen prompts and **do not turn it off while it updates**. Connect again and the Scanner panel shows the new version.

What it checks before writing:
- the file name is for exactly your model (an SDS100 never gets SDS100E or SDS200 firmware), at most one main and one sub file;
- the size is plausible and the file is not a saved web page (a failed download);
- the card is the identified SDS100 over USB (the same check as every other write), with enough free space;
- a main version older than the scanner's needs a second confirmation;
- firmware files (`.bin`, `.firm`) already waiting in the firmware folder are listed and removed first (you can keep them), because the scanner would try to install them too. Other files there, such as the scanner's `CityTable` and `ZipTable` location data, are left alone;

Downloads are kept in `~/.local/share/SDS100DatabaseFavoritesManager/firmware/`, with a receipt for each write in `firmware/receipts/`. The card does not record the sub firmware version, so the window can't say whether a sub file is newer; the scanner shows both versions on its own screen.

### Create a Favorites List from the database
1. **File → Open Scanner Configuration…** and choose your saved configuration.
2. Browse the database. Select a conventional or trunked system and use **Add to Favorites**. Choose *Create a new Favorites List* to start a list from your selection, or add to an existing list.
   Database Contents comes from **RadioReference**, live, through your RadioReference account (Tools → RadioReference Account…).
   With RadioReference, choose the state, then **County**: *Statewide systems and agencies* lists the state's trunked systems and statewide agencies; a county lists its own conventional frequencies (as one system, with RadioReference's categories as departments), its trunked systems and its agencies. Each system is loaded when you choose it; RadioReference data is kept only while SDS-Manager runs, and only what you add goes into your configuration.
   From RadioReference, trunked systems can be used when they are of a type with a list confirmed working on a real SDS100: **P25**, **DMR** — with one frequency per site (each talkgroup keeps its timeslot) or several (Capacity Plus, Connect Plus, Tier III, written as MotoTrbo like Sentinel does; every frequency needs its logical channel number on RadioReference) — and **NXDN in NEXEDGE format** (with each frequency's channel number and RAN). Other types (Motorola, EDACS, LTR, NXDN IDAS) show why they can't be used yet. Talkgroups RadioReference marks as fully encrypted are left out. Talkgroup and channel names, frequencies, tones, NACs, colour codes, modes, service types and locations come from RadioReference; everything else starts at the scanner defaults, exactly as for the Uniden database.
3. Conventional systems: pick departments and channels. Trunked systems: pick site frequencies and individual talkgroups. Rectangle locations are supported in new lists.
4. New items take their information from the database, otherwise the scanner default. Nothing is copied from another item, and two items never share a quick key or number tag.
5. **File → Save Configuration** (Ctrl+S), then **File → Export to Scanner…**.

### Configurations and Favorites Lists
Everything you edit belongs to the **open scanner configuration**: the Favorites Lists dropdown shows its lists, in the scanner's order, under the configuration's name. Opening another configuration asks first if there are unsaved changes (Save, Discard or Cancel).

- **File → New Scanner Configuration…** makes a configuration with the settings of one you choose (GPS, display, service types, search, alerts and so on) and **no Favorites Lists**. Add lists to it with the Favorites menu. Exporting it to the scanner it came from removes that scanner's current Favorites Lists; the export backs the scanner up first, and the lists are kept in the configuration's backups.
- **Favorites → New Favorites List…** (Ctrl+N) asks for a name and what the list starts with: the system selected in the database, what you cut or copied in the list editor, or a conventional system you type in (system, department and first channel). A list always starts with at least one system.
- **Edit Favorites List…** (Ctrl+E) opens the list editor for the selected list.
- **Duplicate Favorites List…** copies a list under a new name. **Copy Favorites List to Another Configuration…** copies it into another saved configuration. Copies start with their quick key, number tag and startup keys Off, so they never clash with the lists already there. A list with unsaved changes offers to save first, so the copy includes them.
- **Reorder Favorites Lists…**: drag the lists, or use Up and Down. The scanner shows them in that order after export.
- **Import Favorites List File (.hpd)…** adds a list file from anywhere (another scanner's card, a backup, a friend) to the open configuration, after the same checks as any new list. **Save Favorites List as File (.hpd)…** writes the selected list to a file.
- **Delete Favorites List…** removes a list; the file is kept in the configuration's backups.

In the list editor (right-click in the left pane):
- **New Department…** on a system or department: a conventional department starts with one channel (name, frequency, modulation, tone); a talkgroup department starts with one talkgroup (name and ID).
- **New Conventional System…** (also on the empty area): system name, first department and first channel. Trunked systems come from the database or RadioReference, with their sites.
- **Add Conventional Frequency…** on a conventional department: name, frequency, modulation and an optional tone, NAC or colour code. **Add Talkgroup…** on a talkgroup department.
- **Delete System…** and **Delete Department…** remove them with everything in them. A list can't be left with nothing in it.
- New items get the scanner's default settings, the same as items from the database. Each change is one Undo step; **Save Configuration** keeps them.

### Change settings
All under **Scanner Settings**; each dialog shows only the settings it covers.

| Menu entry | Contents |
|---|---|
| Global Settings | Global scanner options |
| Search Settings | Common search, Close Call, Limit Search, Tone-Out, band defaults, Waterfall (bands and colours), broadcast screens |
| Weather Settings | Weather options and SAME groups |
| Display Settings | Display options, backlight |
| Display Layouts and Colours | The items shown on each screen row, and screen colours |
| Hardware Settings | Battery, owner information, clock, recording, standby |
| GPS and Location Settings, Service Types | Location source and service-type settings |

Favorites list settings (name, monitor state, quick key, number tag, startup keys, system quick-key flags) are under **Favorites → Favorites List Settings…**.

The main window's Favorites tree and the list editor's left pane have a **Keys / Tag** column: for example *Key 03 · Tag 12* beside a system, *Key 04* beside a department, *Tag 120* beside a channel. Empty means none.

SDS-Manager shares the saved configuration's keys, number tags and scan profiles with SDS100 Monitor, so the Monitor can name its quick keys, offer tagged channels in Go to Number Tag and apply scan profiles. It writes `~/.local/share/sds100-database-favorites-manager/monitor-keys.json` whenever the configuration is saved or a profile changes; the Monitor only reads it.

**Adding what you heard (with SDS100 Monitor, personal edition):** right-click a reception in the Monitor and choose **Add to Favorites List in Manager…**. This works for Close Call, search and Discovery hits, and talkgroups heard through ID Search.
- SDS-Manager asks which department to put it in. The same department and system come first, marked ★.
- It also asks for a name, and for channels the modulation and an optional tone.
- It's added as one Undo step. Save Configuration keeps it.

**Favorites → Keys & Tags…** (Ctrl+K) is the one place for quick keys, number tags and what the scanner scans.

- **The tree** lists every Favorites List, with its systems, their sites and departments, and their channels and talkgroups.
- **Two questions, kept apart:**
  - The **Quick key** and **Number tag** columns show which number each item has.
  - The **Scanning** column says in words whether the scanner scans it, and why not. For example: *not scanned: department key 04 is Off*, or *not scanned: Favorites List Spartanburg County has Monitor Off*.
- **Sorting:** click a column heading to sort by it, and click again to reverse. Or pick from **Sort:**: Scanner order, Name, Quick key, Number tag, Not scanned first, or Detail. Each list keeps its systems, each system its departments, and each department its channels; they are sorted among themselves. Numbers sort as numbers, and items without a number go last. **Scanner order** puts everything back as the scanner has it.
- **Changing a number:** double-click it. The list shows every number with *free* or *used by …*, plus a **Next free** button.
- **Switching scanning:** tick or untick **Scanning** to switch that key On or Off. Everything on the same key follows. Tick **Detail** on a list to switch its Monitor.
- **Number sets:** Favorites List numbers are one set for the whole scanner. System keys and tags are one set per list. Department keys and channel number tags (0–999) are one set per system. A trunked site's quick key (0.1.22) is in the same set as its system's departments: switching that key Off stops both. Number Keys in Order… on a trunked system asks whether to number its departments, its sites, or both.
- **Numbering helpers:**
  - **Number Keys in Order…** and **Number Tags in Order…** number everything under the selected item, from a start number counting up by a step. For example, channel tags 100, 101, 102… for one department.
  - **Next Free Key**, **Next Free Tag** and **Clear** work on the selected item.
  - **Tags by Department…** (select a system) gives each department's channels a block of number tags: for example 100s for the first department, 200s for the next. You choose the block size and the start. A system with many departments needs smaller blocks, because tags stop at 999.
  - **Match Tags to Keys** sets each number tag to the item's quick key, for the selected item and everything under it, so you only remember one number.
- **Scan profiles:** a profile is a saved set of which keys are On and which lists are monitored, for example *Home*, *Fire only*, *Storm*.
  - **Save Current as Profile…** saves the switches as they stand in the window.
  - **Use** sets them from a profile; **Apply** keeps them, then Export to Scanner sends them.
  - Profiles go by list and system names. Lists added after a profile was saved are left as they are, and the window names them.
  - Profiles are kept on your computer with the configuration library, not on the scanner.
  - **SDS100 Monitor** (1.1.68 or later) can apply a profile to the scanner while it runs: Scanner Tools → Quick Keys → APPLY PROFILE TO SCANNER.
- **Save Spreadsheet…** writes a LibreOffice Calc spreadsheet of every key and tag:
  - It has sheets for Favorites Lists, Systems, Departments and Channels, plus a 00–99 map of Favorites List numbers.
  - Numbers go in yellow cells. Check columns turn red when two items in the same set share a number.
  - It needs `python3-openpyxl`. Without LibreOffice installed, it is saved as .xlsx, which Calc also opens.
- **Read Spreadsheet…** brings numbers you edited in Calc back into the window as changes to check and Apply. Nothing is written until you Apply.
  - Rows that no longer match the configuration, and values that aren't whole numbers, are skipped and listed.
  - Keep the hidden Ref column, and don't add or move rows.
- **Key Card (PDF)…** makes a printable page to keep with the scanner:
  - Favorites List keys and tags, and whether each list is scanned.
  - For each monitored list, its system keys and tags and its department keys.
  - A directory of channel number tags.
- **Problems underneath, updated as you work:** numbers used twice in one set; items that won't be scanned because a key is Off; and Favorites List keys that are On with nothing on them.
- **Apply:**
  - Shows the changes in words first.
  - Saves list keys, tags and On/Off to the configuration straight away.
  - Puts system, department and channel changes into the lists, then offers to Save Configuration.
  - Two Favorites Lists can't share a key or tag, so Apply refuses that.
- **Export to Scanner** shows the same warnings (numbers used twice, things that won't be scanned) in its preview. They don't block the export.

Dropdowns and text boxes can be changed; reserved or unsupported fields are read-only and preserved exactly. **Save** shows the validated changes for review, then saves them to the local configuration. Export them with **File → Export to Scanner…**.

### Undo, bulk edit and drag and drop
- **Undo / Redo** (Ctrl+Z / Ctrl+Y, also on the **Edit** menu) work in the main window and the Favorites List editor. **Edit → Undo All Changes…** steps back through up to 40 remembered changes at once; Redo replays them one at a time. Undo only affects the open configuration's lists before you save, never the scanner.
- **Cut, Copy and Paste between Favorites Lists:** in the Edit Favorites List window, right-click (or press Ctrl+X, Ctrl+C, Ctrl+V) in either pane.
  - **Left pane:** a whole **system**, or a **department** with its channels or talkgroups. A talkgroup department brings its system's sites along, so it can start that system in a list that doesn't have it yet.
  - **Right pane:** the selected **channels** or **talkgroups** (Ctrl+click or Shift+click to select several). Select the department to paste them into in the left pane first.
  - Close the window, open the other list with **Edit Favorites List…**, select where it goes and **Paste**. It is added to the selected conventional system, or to the same system (same name and type) if the list has it, or as a new system. A department with the same name takes the new channels or talkgroups. Anything already there is skipped, and nothing is replaced. You see what will be added before anything changes.
  - Talkgroups only go into a trunked system of the same type (P25 into P25, DMR into DMR), as their IDs are written differently for each type.
  - **Cut** removes the item right away, with one Undo step; paste it once. A copy can be pasted many times. A list can't be cut down to nothing: the scanner needs at least one system in it.
  - **Paste as New Favorites List…** (left pane) creates a new list in your scanner configuration holding the system or department you cut or copied. For example, cut *Greenville (City) - Police* and paste it as a new list called *Greenville City Police*.
  - Every row is copied exactly as the scanner wrote it, with all its settings. **Save Scanner Configuration** keeps the changes, as for any edit.
  - **Quick keys and number tags that clash:** if something you paste has a system key, system tag, department key or channel number tag that's already used in the same set of the list you paste into, Paste lists them and asks what to do:
    - **Next Free Numbers** (the default) moves only the clashing ones to free numbers.
    - **Set Them Off** clears them.
    - **Keep Them** leaves them used twice; Keys & Tags will show them.
  - Numbers that don't clash are always kept.
- **Change several channels at once:** in the editor, select rows (Ctrl+click or Shift+click the row numbers) and choose **Change Selected…**. Pick Avoid, Attenuator, Delay or Volume Offset and a value; confirm once. The whole change is one Undo step.
- **Drag and drop:** drop an SD card folder on the main window to import it from the scanner, or drop a `.hpd` file to inspect it read-only.

### Export to the scanner
**File → Export to Scanner…** compares the saved local configuration with the card. The preview starts with a plain-language list of what will change (new, removed and edited lists, and changed settings), followed by the technical file-by-file details. If it says *READY*, confirm to run the controlled write. If it says *BLOCKED*, the reason is shown and nothing has changed.

**Avoids made on the scanner** (0.1.21): a permanent avoid set on the SDS100 or from SDS100 Monitor is stored on the scanner. Before exporting, SDS-Manager lists the avoids that differ from the configuration; ticked ones are saved into the configuration first, so the export doesn't undo them.

### Find Everywhere
**Tools → Find Everywhere…** (Ctrl+F) searches the active master database and the Favorites Lists of the open configuration at once. Enter a name (system, department, site, channel, talkgroup or list name), a frequency in MHz (`154.9` finds everything from 154.900 to 154.999; `460.025` finds exactly that frequency) or a talkgroup ID. Results show the type, value and the system › department they belong to; **Copy Results** copies the table. Searching never changes anything. Only the first 500 matches are shown, so narrow a very broad search.

### Menus
**File**: new, import, open, save and export configurations (with Manage Configurations, Backup and Restore and Storage submenus). **Edit**: Undo, Redo, Undo All Changes. **Favorites**: everything about Favorites Lists. **Database**, **Scanner Settings**, **Tools** and **Help** as before. Rarely used or read-only inspection tools are in **Advanced** submenus.

### The Scanner panel and Settings
- **Scanner panel** (right side; show or hide it from the Tools menu): when the SDS100 card is mounted it shows the model, firmware, database date (and whether a newer database is available locally), free space and number of lists, your backups, and the open configuration. Buttons start the common jobs: update the database, export, back up, clean up backups. The bottom-right of the window shows the same connection state. Detection only reads the card's identity files.
- **Tools → Settings…** (Ctrl+,): scanner connection (where removable media appear, automatic detection, offering the detected card in folder prompts), backups (how many to keep when you clean up, size warning), confirmations (low-risk prompts only; **writes to the scanner are always confirmed**), database (optional startup check for a newer Uniden database, versions to keep), appearance (theme, accent colour, text size, exact font size) and log detail.
- **Tools → Theme:** the same themes as SDS100 Monitor, applied immediately.
  - **Mode:** *System (follow KDE)* uses KDE's light or dark colour scheme and changes within a few seconds when KDE does; *Dark*; *Light*; *Night (red)*, dim red only, to keep your night vision.
  - **Accent:** Blue, Red, Green, Amber, Purple or Teal, used for tabs, menu highlights, selections and accent buttons. Greyed out in Night.
  - **Text size:** Small, Normal, Large or Extra large, relative to your desktop's font. An exact font size set in Settings overrides it; choosing a Text size here clears that.
- **Clean up old backups** and **Clean up old database versions** are always manual and show exactly what will be deleted first. The newest backups, the current database and the version on your scanner are never offered for deletion.

### Installing and updates
- **Install:** `sudo apt install ./sds-manager_<version>_all.deb` (the personal build: `sds-manager-personal`). Remove with `sudo apt remove sds-manager`; your data stays.
- **Help → Check for Updates…** finds a newer .deb in `~/Downloads` (or a GitHub release, once you enter the repository) and installs it with **Install**.

### RadioReference
**Tools → RadioReference Account…** signs SDS-Manager in to the RadioReference database with **your own RadioReference account**, which needs an active **Premium** subscription. Enter your username and password, then **Save and Test Sign-in**: it shows your username and when your Premium subscription ends. The application key, which identifies SDS-Manager to RadioReference, is built into the package; only a build without one (for example, built from source) shows an **Advanced** section where you enter a key of your own.

- The password (and a key you entered yourself) is kept in **KDE Wallet** (through `python3-keyring`), never in a settings file; your username is kept in the settings. Without a secret store it is kept only until SDS-Manager closes. **Forget Saved Password** removes it.
- **Packaging with the key:** the key is never in the source code. `add_rr_key.sh` adds it to a package on your own computer: `bash add_rr_key.sh sds-manager_<version>_all.deb rr_app_key.txt` (the file holds just the key), then install the package as usual.
- SDS-Manager talks to RadioReference directly from your computer, always over HTTPS.
- RadioReference data is used only to build and update the Favorites Lists of your own scanner; only what you add is kept, in your configuration.
- Updating existing Favorites Lists from RadioReference, naming talkgroups from it and looking up unknown talkgroups come in the next versions.

### SDS100 Monitor link
With **SDS100 Monitor** (personal build 1.1.52 or later) installed:
- **Edit in Manager:** in the Monitor, right-click a reception → **Edit in Manager…**, or use **Tools → Edit Current Channel in Manager…**. The Manager opens the Favorites List editor on that talkgroup or channel in the open configuration. If it is in several places you choose one; with no configuration open you are offered one.
- **Tools → Name Unnamed Talkgroups…** suggests names for talkgroups that have none (blank or just the ID), from the master database and from what the Monitor recorded. Tick, check, and apply; it is one Undo step and goes to the scanner only with Save Configuration and Export.
- **Heard (90 days) and Last Heard** (0.1.19): the last two columns of the Favorites List editor show how many times the Monitor logged each channel or talkgroup in the last 90 days, and when it was last heard. Talkgroups are matched by system name and TGID, channels by frequency. Read-only; they come from the Monitor's daily reception history and are read once when the editor opens.
- **Add Unit Names from SDS100 Monitor…** (0.1.19): right-click a system in the editor. The confirmed unit names from the Monitor (not those marked Guess) go into every trunked system in the list where the Monitor heard that unit; a unit already there with another name is renamed. It is one Undo step; Save Configuration and Export send it.
  - The file specification doesn't fully say how the scanner stores unit IDs, so SDS-Manager copies a unit ID row the scanner wrote itself. If a system has none yet, add one on the SDS100 (Manage Favorites → the list → the system → Edit Unit IDs → New Unit ID), read the configuration from the scanner again, and run it again. The export refuses unit ID rows in any other layout.
- **Scanner out of date** (0.1.20): SDS-Manager remembers when the scanner last matched the configuration (read from the scanner, or exported). If you save changes and haven't exported them, the configuration name at the bottom says **— not on scanner yet**, and SDS100 Monitor (1.1.74 or later) shows a yellow warning. The Monitor also warns when the scanner plays a Favorites List the open configuration doesn't have. A configuration made before 0.1.20 shows nothing until it's next read or exported.
- The Manager only reads the Monitor's files (`~/SDS100Monitor`), and the two programs talk only on this computer.

## What the application will and will not do

- It **will** replace the master database, add and remove Favorites Lists, edit existing lists, and edit the validated scanner settings.
- It **will** place verified firmware files for the scanner to install (Scanner Settings → Update Scanner Firmware…). It never flashes firmware itself; the scanner's own protected boot loader does that.
- It **will not** write anything it cannot validate, or use live GPS.
- Not yet supported (waiting for real samples): new lists for Motorola, EDACS and LTR systems (P25, DMR including MotoTrbo, and NXDN NEXEDGE are confirmed); IFX frequencies; editing avoid-frequency lists; adding a rectangle department to an *existing* list.

## Where things are stored

| What | Where |
|---|---|
| Local configurations (copies of your card) | the application's library (*File → Open Managed Data Folder…* shows the data folder) |
| Downloaded and rebuilt databases | `~/.local/share/SDS100DatabaseFavoritesManager/database/` |
| Downloaded firmware and write receipts | `~/.local/share/SDS100DatabaseFavoritesManager/firmware/` |
| Scanner backups | `~/.local/share/sds100-database-favorites-manager/scanner-backups/<timestamp>/` |

Rebuilt database folders are named `HPDB-Experimental-<date>` for historical reasons; they are ordinary, verified-complete database versions.

Each backup folder holds `BCDx36HP/` (the original files), `manifest.json` (every file with its SHA-256), `EXPORT_RECOVERY.txt` (which files the export changed) and `EXPORT_RESULT.json` (what was written). These are on your computer, not on the SD card.

## If something goes wrong

**The application reports a failed write.** It restores every changed file from the verified backup by itself. If it says *DO NOT DISCONNECT*, leave the scanner connected and follow the message, which names the backup folder and the files to restore.

**The scanner misbehaves or a list is empty after an export.**
1. Power the scanner off. Connect it in mass-storage mode (or put the SD card in a reader).
2. Easiest: **File → Restore from Backup…** and choose the backup taken before that export. Follow the preview.
3. By hand: open the newest backup folder, read `EXPORT_RECOVERY.txt`, and copy each listed file from the backup's `BCDx36HP` folder back to the same place on the card. Delete any file marked as ADDED.
4. Eject the card, then power on.

**A list or the database looks empty on the card right after writing.** Almost always the card was powered off before it finished unmounting. Run the export again, wait for the card to be ejected, then power on.

**Export says BLOCKED.** Read the reason. Typical causes: the scanner is not the recognised SDS100 USB device, the card is read-only or too full, or a file on the card changed since you opened the configuration (open a fresh copy with *Import from Scanner…*).

**After a firmware update the scanner doesn't start or shows an error.** The scanner checks firmware before installing it and refuses a damaged or wrong file, and Uniden users report its boot loader is protected. Turn it off and on; if it keeps trying, connect it in mass-storage mode, delete everything in `BCDx36HP/firmware`, eject and start again. Write the firmware again from **Update Scanner Firmware…** if needed.

**Last resort.** The scanner can be restored with Uniden Sentinel's own backup, or by copying the `BCDx36HP` folder from any backup here over the card's `BCDx36HP` folder.

## Help, credits and licence

**Help → User Guide** (F1) opens this guide inside the application, with a heading list and search. **Recovery and Troubleshooting** jumps straight to the recovery steps; **Copy Diagnostic Information** copies the version and system details (no scanner data) for a problem report; **Open Scanner Backups Folder** opens the backups.

Created by J. Lynch, with AI assistance in the build (Claude, by Anthropic). Free software under the GNU General Public License v3 or later, with no warranty (**Help → License**, `LICENSE`, `NOTICE.md`). Not affiliated with Uniden.

## Reporting problems or testing new system types

If you use a system type that is not yet supported, build the same list in Sentinel and send the resulting `f_NNNNNN.hpd` and `f_list.cfg`. Real Sentinel-written files are how each new type is verified. For anything refused unexpectedly, send the message shown plus the backup's `manifest.json`.
