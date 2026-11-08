## v0.1.22 — Site quick keys

- **New: trunked sites' quick keys.** On the SDS100 a site can have a quick key; it uses the same 00–99 keys as the departments of its system, so switching that department key Off stops scanning the departments and sites on it. SDS-Manager didn't show or set them before.
  - **Keys & Tags** lists each site under its system (Details: Site) with its quick key: set it, Next Free, Number in Order (departments, sites, or departments then sites), warnings when a key is used twice, and "not scanned" when its key is Off.
  - **Edit Site…** has a Quick Key field (Off or 0–99).
  - **Quick Keys…**, the spreadsheet (Departments sheet, marked "(site)"), the key card and SDS100 Monitor's department key names (marked "(site)") include them.
  - **The export checks** site quick keys (Off or 0–99), and Paste treats them like department keys.
- Site quick key is column 16 of the Site line (Uniden SDS file specification v2.00); every site in the lists seen so far has it Off.
- New tests (4).

## v0.1.21 — Avoids made on the scanner aren't undone by Export

- **Fixed: Export to Scanner quietly undid avoids made on the scanner.** A permanent avoid set on the SDS100 itself, or from SDS100 Monitor, is written into the scanner's Favorites List file; the configuration saved earlier still had the old value, and exporting it put that back.
- **Now, before an export**, SDS-Manager compares the avoids on the scanner with the configuration's (systems, sites, departments, channels and talkgroups, matched by where they are). Any that differ are listed; tick the ones to keep and they are saved into the configuration first, then the export goes on. **Continue Without** exports as it is; Cancel stops.
  - Ticked to begin with: those changed on the scanner since it last matched the configuration. An avoid you changed in SDS-Manager isn't listed; your change is exported.
  - When that isn't known yet (a configuration last read or exported before 0.1.21), the ones the scanner has avoided are ticked.
  - If the configuration is open with unsaved changes, you're asked to save or discard them first; it's reopened afterwards.
- SDS100 Monitor 1.1.75 says so after a permanent avoid.
- New tests (3).

## v0.1.20 — Is the scanner up to date?

- **New: SDS-Manager remembers when the scanner matches a configuration**: when it's read from the scanner and after each successful Export to Scanner. When the saved Favorites Lists differ from that, the configuration name at the bottom says **— not on scanner yet**, and its tooltip says when the scanner last matched. Kept in `export-state.json` beside the configuration library, never on the scanner.
- **SDS100 Monitor 1.1.74 shows a warning** from this: "Scanner out of date: … has changes saved in SDS-Manager that aren't on the scanner yet". The Monitor also warns if the scanner is playing a Favorites List the open configuration doesn't have.
- Configurations made before 0.1.20 show nothing until they're next read from or exported to the scanner.
- New tests (4).

## v0.1.19 — What SDS100 Monitor heard, and its unit names, in SDS-Manager

- **New: Heard (90 days) and Last Heard columns** in the Favorites List editor, from SDS100 Monitor's reception history (`~/SDS100Monitor/history`). Talkgroups are matched by system name and TGID, channels by frequency. "not heard" means the Monitor didn't log it in that time. Sort by them to find what's never on the air. Saved column layouts are kept; the two columns are added at the end.
- **New: Add Unit Names from SDS100 Monitor…** (right-click a system in the editor). Unit names you confirmed in the Monitor go into the trunked systems of the list where the Monitor heard each unit, so the scanner shows them on its own. Names marked Guess are left out; a unit already in the system with another name is renamed. One Undo step; Save Configuration and Export send it.
  - New unit ID rows are copied from one the scanner wrote in the same system (same layout, same alert settings), because the file specification doesn't fully say how they're stored. A system with none yet is listed, with how to add one on the SDS100.
  - The export checks unit ID rows: name up to 64 characters, ID 1–16777215, alert tone and volume, inside a trunked system, and only in a layout the scanner has written in that list.
- The Manager still only reads the Monitor's files.
- New tests (6).

## v0.1.18 — Add what SDS100 Monitor heard to a Favorites List

- **New: Add to Favorites List from SDS100 Monitor** (Monitor 1.1.73, personal edition). Right-click a reception in the Monitor (or Tools → Add Current Channel to Favorites List in Manager…) and SDS-Manager opens a small window:
  - It shows what was heard and offers the departments it can go into: the same department and system first (marked ★), then the rest.
  - A channel goes into a conventional department, with name, modulation and an optional tone, NAC or colour code. A talkgroup goes into a talkgroup department of a trunked system.
  - The name starts as the one the scanner showed, unless that was only a number.
  - If it's already in a list, you're asked before adding it again. A duplicate in the same department or system is refused.
  - It's one Undo step; Save Configuration keeps it and Export to Scanner sends it. **Open the list editor on it afterwards** is optional.
- If no list has a suitable department, the window says how to make one (New Department… or New Conventional System… in Edit Favorites List).
- New tests (3).

## v0.1.17 — Trunked systems' quick keys and number tags in the right place

- **Fixed (important): trunked systems' quick keys and number tags were in the wrong columns.** Uniden's file specification puts a trunked system's quick key in column 12 and number tag in column 13. Columns 7 and 8 are ID Search and Alert Tone. Since 0.1.8, Keys & Tags, Quick Keys…, the Keys / Tag column and Paste read and wrote columns 7 and 8 (correct only for conventional systems). So Keys & Tags showed trunked systems such as Palmetto 800 without their real quick key, and any key or tag set for them never reached the scanner. That's why Go to Number Tag got NG for a channel in Palmetto 800.
- **Repair.** When a configuration is opened, or Keys & Tags is opened, trunked systems with a number in ID Search or Alert Tone are listed. You're offered to move those numbers to the quick key and number tag and set ID Search and Alert Tone back to Off; then save and export. An emergency Alert Tone you set yourself would need setting again (every trunked system in the lists seen so far has it Off).
- **The export now refuses** a trunked system with a number in ID Search or with an Alert Tone outside Off/0–9, and says to repair it in Keys & Tags. Trunked systems' quick keys and number tags (Off or 0–99) are checked in their real columns.
- Built on 0.1.16. New tests (4), on a real SDS100 list where Palmetto 800's quick key 0 is in column 12.

## v0.1.16 — Export accepts the scanner's own band plans

- **Fixed: Export to Scanner refused a changed list** with "BandPlan_P25 has 34 columns, expected 50". When a list has bigger edits, it's checked as a complete Favorites List, and that check only knew the 50-column P25 band plan line. Your SDS100 writes a 34-column one too. Both layouts are now accepted. A scanner-written line that is exactly as it is on the scanner is accepted as the scanner wrote it, even in a layout this program hasn't seen before.
- Built on 0.1.14; the 0.1.15 changes were set aside.
- New test (1).

## v0.1.14 — Export accepts Keys & Tags and editor changes

- **Fixed: Export to Scanner refused lists changed in Keys & Tags** with "Line 3: only a system/site/department name may change". The export check for existing lists was older than Keys & Tags and only allowed names to change in system and department lines. It now accepts system quick keys and number tags (Off or 0–99), department quick keys, department quick-key On/Off and channel number tags (0–999).
- **Bigger changes are checked as a complete list.** Changes the old check didn't cover (new or deleted departments and systems, pasted entries, several kinds of change in one list) are now checked as a complete Favorites List, with the same checks as a brand-new list, which match lists confirmed working on a real SDS100. The preview says "changed list, checked as a complete Favorites List". A list that fails those checks is still refused.
- Several departments may share a quick key; they switch together. Keys & Tags warns about it, and the export no longer refuses it.
- New tests (3), including the change that was refused.

## v0.1.13 — Sorting in Keys & Tags

- **Keys & Tags can be sorted.** Click a column heading (Name, Detail, Quick key, Scanning, Number tag) to sort, and again to reverse, or choose from the new **Sort:** list. The choices are Scanner order, Name A–Z or Z–A, Quick key or Number tag low or high first, Not scanned first, and Detail.
- Sorting keeps lists, systems and departments together. Numbers sort as numbers (2 before 10), and items without a number go last either way.
- New test (1).

## v0.1.12 — Keys, tags and profiles for SDS100 Monitor

- **SDS100 Monitor can now use your keys, number tags and scan profiles.** SDS-Manager writes a small file (`monitor-keys.json`, beside the configuration library) whenever the open configuration is saved or a scan profile changes. SDS100 Monitor 1.1.68 reads it to:
  - name its quick keys;
  - list the tagged channels in Go to Number Tag;
  - apply scan profiles to the scanner while it runs.
- The file holds names and numbers only, and nothing is sent anywhere.
- New test (1).

## v0.1.11 — Spreadsheet and key card

- **New: Save Spreadsheet… in Keys & Tags.** A LibreOffice Calc (.ods) spreadsheet of every quick key and number tag in the open configuration: Favorites Lists, Systems, Departments and Channels sheets with yellow input cells and check columns that flag a number used twice in the same set, plus a 00–99 map of Favorites List numbers. Without LibreOffice it is saved as .xlsx.
- **New: Read Spreadsheet…** brings back numbers edited in that spreadsheet as changes to check and Apply. Rows that no longer match the configuration, or values that aren't whole numbers, are skipped and listed.
- **New: Key Card (PDF)…** prints a page to keep with the scanner. It lists Favorites List keys and tags, the system and department keys of the monitored lists, and the channel number tag directory.
- The package now recommends `python3-openpyxl`, which the spreadsheet needs.
- New tests (4), including the formulas worked out by LibreOffice.

## v0.1.10 — Keys on paste, and keys beside names

- **Paste asks about clashing numbers.** When something you paste has a system key, system tag, department key or channel number tag already used in the same set of the list you paste into, the confirmation lists them. Choose Next Free Numbers (the default), Set Them Off or Keep Them. Numbers that don't clash are kept, and departments in a newly pasted system are their own set. (Duplicated, copied and imported lists already start with their list key and tag Off; the numbers inside a list are per list, so they never clash.)
- **New Keys / Tag column** in the main window's Favorites tree and in the list editor's left pane, for example *Key 03 · Tag 12* for a system, *Key 04* for a department and *Tag 120* for a channel.
- New tests (4).

## v0.1.9 — Scan profiles and more numbering helpers

- **New: scan profiles in Keys & Tags.** Save the current set of which keys are On and which lists are monitored under a name (Home, Fire only, Storm …). Use a profile to set them all at once, then Apply. Profiles go by list and system names, are kept with the configuration library on your computer, and name any lists they don't cover.
- **New: Tags by Department…** gives each department of a system its own block of channel number tags (for example 100s, 200s), with the block size and start you choose. It refuses blocks that would run past 999.
- **New: Match Tags to Keys** sets number tags to the quick key for the selected item and everything under it.
- New tests (3).

## v0.1.8 — Keys & Tags

- **New: Favorites → Keys & Tags… (Ctrl+K)**, one window for every quick key, number tag and On/Off switch, replacing Quick Keys…. It shows every Favorites List with its systems, departments and channels. The Quick key and Number tag columns show each item's numbers. The Scanning column says in words whether the scanner scans each item and, if not, which key or Monitor setting stops it.
- **Every level can now be edited**, including system quick keys and number tags, department quick keys and their On/Off status, which couldn't be changed before. Double-click a number to change it: the list shows which numbers are free and who uses the others. Tick Scanning to switch a key; tick Detail to switch a list's Monitor.
- **Numbering helpers:** Number Keys in Order…, Number Tags in Order… (start and step, for example channel tags 100, 101, 102…), Next Free Key, Next Free Tag and Clear.
- **Problems listed as you work:** a number used twice in the same set, things that won't be scanned because a key is Off, and Favorites List keys On with nothing on them.
- **Export to Scanner** shows the same warnings in its preview, without blocking the export.
- Apply describes the changes in words first. List-level settings are saved straight away; system, department and channel changes go into the lists, kept by Save Configuration (offered right away). Each step can be undone.
- New tests (6) on real SDS100 files.

## v0.1.7 — No more Drafts & Planning; new configurations and list management

- **Removed: the Drafts & Planning menu** and the separate offline planning drafts (.sds100draft.json), with their Create, Open, Save, Rename and Delete Draft commands and the "SAFETY: Save draft creates a JSON planning file" notice. You now work directly on the open scanner configuration: its Favorites Lists are the lists you edit, **Save Configuration** (Ctrl+S) keeps the changes and **Export to Scanner** sends them. Old draft files stay on disk untouched; the program no longer uses them.
- **New Edit menu** with Undo, Redo and Undo All Changes.
- **Opening a configuration** shows only its lists, in the scanner's order, under the configuration's name, and asks first if there are unsaved changes. Lists are shown under their own names (no more "(editable copy)"). Import from Scanner opens the new configuration straight away.
- **New: File → New Scanner Configuration…** with the settings of an existing configuration and no Favorites Lists.
- **New on the Favorites menu:** New Favorites List… (from the database selection, from what you cut or copied, or a conventional system you type in), Edit Favorites List…, Duplicate Favorites List…, Copy Favorites List to Another Configuration…, Reorder Favorites Lists…, Import Favorites List File (.hpd)… and Save Favorites List as File (.hpd)….
- **New in the list editor:** New Department…, New Conventional System…, Delete System… and Delete Department…. Add Conventional Frequency… now asks for modulation and tone, and works in a department that has no channels to copy from.
- **Export:** the lists may now be in a new order on the scanner (the check still refuses lists that disappear without being deleted here).
- **Fixed:** Database Information, the database import messages and the trunked-system preview showed "\n" instead of starting new lines.
- New tests (11), including a new configuration and a reordered configuration exported to a mock scanner.

## v0.1.6 — Quick keys show what they switch

- **New: Favorites → Quick Keys…** (replaces Quick Keys Status). One tree shows each Favorites List with its quick key, its systems with theirs and their departments with theirs. Beside each is whether the key is On (scanned) or Off (not scanned), in words. Items without a key say so. Keys shared by several items at the same level are marked. Favorites List and system keys can be switched there; department keys are shown read-only for now.
- The 00–99 grid of Favorites List keys is still there as a tab, with each key labelled with the lists that use it and an option to show only keys in use.
- **Favorites List Settings → Edit keys…** labels each system key with the systems assigned to it, and explains the startup keys.
- **Fixed:** the export check treated department quick keys as one set for the whole list. They are numbered per system, so two systems can each have a department on key 0, as in lists written by the scanner.
- Favorites List Relationships no longer says that list quick keys can't be shown.
- New tests (4) from real SDS100 files.

## v0.1.5 — Cut, Copy and Paste between Favorites Lists

- **New: Cut, Copy and Paste in the Edit Favorites List window**, in both panes (right-click, or Ctrl+X, Ctrl+C, Ctrl+V). The left pane cuts or copies a whole system or a department with its channels or talkgroups; the right pane, the selected channels or talkgroups. Open another list and paste them there.
- **Paste adds and never replaces.** It goes into the selected conventional system or the same system the list already has, or becomes a new system. A talkgroup department brings its system's missing sites along. A department with the same name takes the new entries. Channels and talkgroups already there are skipped. A summary shows what will be added before anything changes.
- **Paste as New Favorites List…** creates a new list in the scanner configuration from what you cut or copied (for example, a city's police department as its own list).
- Rows are copied exactly as the scanner wrote them, with every setting. Talkgroups only go into a trunked system of the same type. A list can't be cut down to nothing. Each cut and each paste is one Undo step.
- New tests (12) on two Favorites Lists confirmed working on a real SDS100: every result passes the export checks.

## v0.1.4 — Application key built into the package

- **The RadioReference application key now comes with the package.** Tools → RadioReference Account… asks only for your RadioReference **username and password**, and shows "Application key: built into this package". The key identifies SDS-Manager to RadioReference; each user still signs in with their own Premium account.
- **The key is not in the source code.** It is added to a package on the packager's own computer with the new `add_rr_key.sh` (`bash add_rr_key.sh sds-manager_0.1.4_all.deb rr_app_key.txt`), which puts it in `/opt/sds-manager/rr_app_key`. `.gitignore` keeps a key file out of the repository, and the build checks that no key file is in either build.
- **Builds without a key** (for example, built from source) show an **Advanced** section where a RadioReference application key of your own can be entered; it is kept in KDE Wallet, as before.
- A key saved in KDE Wallet by an earlier version is no longer used while the package has one, and is removed the next time you save the account.
- New tests (4).

## v0.1.3 — Multi-frequency DMR (MotoTrbo)

- **New: DMR systems with several frequencies per site** (Capacity Plus, Connect Plus, Tier III) can be added from RadioReference. They are written as **MotoTrbo**, exactly as in a Sentinel-written list confirmed working on a real SDS100 (Charleston Wireless Group/James White): the Manager rebuilds that system row for row, and RadioReference data comes out the same. Each frequency keeps its logical channel number and colour code; RadioReference must have an LCN for every frequency, or the system says why it can't be used.
- **MotoTrbo systems from the Uniden database** are written in the same confirmed form (system and site defaults as Sentinel writes them, 8-column site frequencies).
- The export check accepts the department quick-key line as Sentinel writes it (without the trailing empty column), and still checks all 100 values.
- New tests (3) from the confirmed Sentinel list.

## v0.1.2 — DMR and NXDN from RadioReference

- **New: RadioReference trunked systems of two more types** can be added to Favorites Lists: **DMR with one frequency per site** (colour code per frequency, each talkgroup's timeslot) and **NXDN in NEXEDGE format** (each frequency's channel number and RAN). Both were checked against Favorites Lists confirmed working on a real SDS100 (Oconee County Emergency Services and FleetTalk Carolinas): RadioReference data comes out row for row the same.
- **DMR site frequencies are written in the confirmed form** (without the optional last column), from either source. The export check accepts site frequencies with or without that column, as both forms work on the scanner.
- Motorola, EDACS, LTR, multi-frequency DMR (Capacity Plus, Connect Plus, Tier III) and NXDN IDAS still show why they can't be used yet: they need a list confirmed on a real scanner first.
- New tests (5) built from the two confirmed lists: every system in them is rebuilt exactly, and they pass the export checks.

## v0.1.1 — RadioReference in Database Contents

- **New: RadioReference as the source of Database Contents.** Database Contents comes from RadioReference, through your account. Choose the state and a **County** (or *Statewide systems and agencies*): a county lists its conventional frequencies (RadioReference's categories as departments), its trunked systems and its agencies.
- Everything after that works as before: the channel and site/talkgroup selectors, **Add to Favorites**, new lists and adding to existing lists, with the same checks. RadioReference's names, frequencies, tones (PL, DPL), NACs, colour codes, modes, service types and locations are translated into the scanner's format.
- Trunked systems from RadioReference: **P25** for now. Fully encrypted talkgroups are left out.
- RadioReference replies are kept in memory while SDS-Manager runs, so going back to a system doesn't ask again; nothing is saved from RadioReference except what you add to your configuration.
- New tests (11), including RadioReference systems built into real Favorites Lists by the same code that writes them to the scanner.

## v0.1.0 — SDS-Manager; RadioReference account

- **Renamed SDS-Manager** (formerly SDS100 Database & Favorites Manager). The package is now `sds-manager`, installed in `/opt/sds-manager` and started with `sds-manager`; it replaces the old `sds100-manager` package when installed. Your databases, configurations, backups and settings stay where they were.
- **New: Tools → RadioReference Account…** — sign in with your own RadioReference Premium account and the application key; **Save and Test Sign-in** shows when your subscription ends. The password and key are kept in KDE Wallet, never in a settings file. RadioReference features build on this in the next versions.
- **Database → Update Database (Rebuild from Archive)…** rebuilds the database from a Uniden master database archive you choose (`MasterHpdb_MM_DD_YYYY.gz`). **Update Scanner Firmware** takes firmware files you download from Uniden's support page (Add File…).
- New tests for the RadioReference connection (9).

## v0.0.9i — Firmware found on Uniden's server

- **Fixed: Check Uniden for Firmware found nothing for the SDS100.** Uniden's update server spells the model with a hyphen (`SDS-100_V1_26_01.bin`, `SDS-100-SUB_V1_03_15.firm`), which the Manager didn't recognise as SDS100 firmware. Both spellings are now accepted; SDS100E, SDS200 and other models are still refused.
- **Other files in the firmware folder are left alone.** The scanner keeps its location tables there (`CityTable_…dat`, `ZipTable_…dat`); they were listed as waiting firmware and offered for removal before a write. Now only firmware files (`.bin`, `.firm`) count as waiting; other files are shown as "not firmware, left alone" and never removed.
- New tests (3), using the file names on Uniden's server.

## v0.0.9h — Menu icon and quieter installs

- **Fixed: no icon in the application menu after installing the 0.0.9g package.** The menu entry now gives the icon's full path, and the package refreshes the icon and menu caches when it is installed or removed.
- **Check for Updates no longer causes apt's "Download is performed unsandboxed as root" notice:** the update is copied to a temporary folder apt can read before installing.
- Try the updater with this version: put this .deb in Downloads and use Help → Check for Updates….

## v0.0.9g — .deb package and updates

- **New: installs as a Debian package** (`sds100-manager`): `sudo apt install ./sds100-manager_0.0.9g_all.deb`. apt installs PyQt6 if needed; the program goes to `/opt/sds100-manager`, the menu entry is **SDS100 Database & Favorites Manager**, and `sds100-manager` starts it from a terminal. Your databases, configurations, backups and settings stay where they were (`~/.local/share/SDS100DatabaseFavoritesManager` and `~/.config`). Folder installs still work, and `cleanup_old_installs.py` removes them when you no longer need them.
- **New: Help → Check for Updates…** looks for a newer `sds100-manager_<version>_all.deb` in `~/Downloads` and, once you enter the project's GitHub repository, in its latest release. It shows what's new; **Install** installs it (KDE asks for your password) and offers to restart. It also checks quietly 20 seconds after start and says so in the status bar (untick *Check when the Manager starts* to stop that; **Skip This Version** stops it for one version).
- SDS100 Monitor's Edit in Manager starts this package when it is installed.
- New tests (5) for the update check.

## v0.0.9f — SDS100 Monitor link: Edit in Manager, and names for unnamed talkgroups

- **New: Edit in Manager (with SDS100 Monitor 1.1.52-personal or later).** In the Monitor, right-click a reception → **Edit in Manager…** (or Tools → Edit Current Channel in Manager…). The Manager comes to the front and opens the Favorites List editor on that talkgroup or channel in the open configuration, with its row selected.
  - If the Manager isn't running, the Monitor starts the newest installed one; a second copy hands the request to the one already open and closes.
  - Several matches (the same talkgroup in two departments or lists): you choose; one clearly best match (same system and department) opens directly.
  - No configuration open: it offers to open one. Not in your lists: it says so and points to Find Everywhere and Add to Favorites.
  - The connection is local to this computer and only your user can use it. Requests contain only names and IDs; they open the editor, they never change anything.
- **New: Tools → Name Unnamed Talkgroups…** Lists talkgroups in the open Favorites Lists whose name is blank or just the ID (`44353`, `TGID 44353`, `Unknown`…), with suggested names from:
  - the master database: the same talkgroup ID in a system with the same name first, then another system only if every system agrees on the name;
  - SDS100 Monitor's reception history: the name the scanner showed for it (for example while scanning the full database);
  - your notes in the Monitor's Analyze → Found IDs.
  Tick the ones to use (or **Tick All With Suggestions**), edit or choose a name, then **Apply Ticked Names**. You confirm the list of changes; it is one Undo step; names are checked like a manual rename (1–64 characters the list can store). Nothing reaches the scanner until Save Configuration and Export. The Monitor's files are only read.
- New tests (18): requests and their limits, finding entries and choosing between matches, placeholder names, suggestions from a made-up database and Monitor history, applying names, the local connection, and the windows on the Qt stub.
- **Not yet tried on the real scanner or with the Monitor on your PC.**

## v0.0.9e — New icon

- **New program icon:** a handheld scanner with an orange database badge. It matches SDS100 Monitor's icon, which has a green waveform badge, so the two are easy to tell apart in the taskbar. It shows in the window title bar, the taskbar and KDE's application menu (after running `install.sh`).

## v0.0.9d — Fix: crash at startup in v0.0.9c

- **Fixed: v0.0.9c would not start** ("'ManagerWindow' object has no attribute 'prefs'"). The new Tools → Theme menu is built before the preferences are loaded, and it tried to read them too early. It now waits for them; nothing else changed.
- New test: the Theme menu built in the same order as the real window (menus first, then preferences). The Qt stub tests had set the preferences first, which is why they missed it.

## v0.0.9c — Themes (the same as SDS100 Monitor)

- **New: Tools → Theme.** The same choices as SDS100 Monitor, applied live with no restart:
  - **Mode:** System (follows KDE's light or dark colour scheme, and switches when KDE does), Dark, Light, and Night (dim red, to keep night vision).
  - **Accent:** Blue, Red, Green, Amber, Purple or Teal, for tabs, menu highlights, selections and accent buttons (not used in Night).
  - **Text size:** Small, Normal, Large or Extra large.
- The same settings are in **Tools → Preferences → Settings → Appearance**, with readable names instead of internal values. An exact font size there still overrides Text size; picking a Text size from the menu clears it.
- Every hard-coded colour in the program (warning and note text, headings, the Add button, scanner panel severity colours) now follows the theme, including in Light and Night.
- The colours come from the same theme engine as the Monitor, so the two programs look the same side by side.
- An existing preferences file loads unchanged: theme `system`, `light` or `dark` keep their meaning; accent defaults to Blue and Text size to Normal.
- New tests for the theme engine, KDE detection, the preferences and the Settings choices.

## v0.0.9b — Update Scanner Firmware window closes again

- **Fixed: the Update Scanner Firmware window wouldn't close** (Close button or the ×). Its "write finished" step was named `done()`, which is the name of Qt's own method that closing a dialog goes through, so every close attempt failed silently. Renamed. It also no longer uses the name `window` for its link to the main window, which hid another Qt method.
- **New test:** every window class in the program is checked for methods or attributes that reuse a Qt method's name by accident. The Qt stub used by the other tests can't see this kind of mistake. The one intended override (the busy dialog's `reject()`, which stops Escape hiding progress mid-task) is listed.

## v0.0.9a — Update Scanner Firmware

- **New: Scanner Settings → Update Scanner Firmware…** Puts new SDS100 firmware on the scanner the way Sentinel does: verified files go in the card's `BCDx36HP/firmware` folder, and the scanner installs them itself when it next starts from its own card (eject, unplug USB). The program never flashes firmware itself.
- **Check Uniden for Firmware** reads Uniden's update server (the one Sentinel uses, with the same built-in login as the database download) and lists the main (`.bin`) and sub (`.firm`) firmware for your model, compared with the scanner's main version from `scanner.inf`. **Add File…** takes a `.bin`, `.firm` or Uniden's support-page `.zip` (read in memory, never unpacked).
- Checks before writing: exact model match in the file name (SDS100 never matches SDS100E or SDS200), one main and one sub at most, plausible size, not a saved web page, enough free space, a second confirmation for an older main version, and leftovers already in the firmware folder listed and removed first (optional). The write uses the same USB identity check, SHA-256 staging and read-back as every scanner write, and leaves a receipt in `firmware/receipts/`.
- The User Guide's safety section and "If something goes wrong" cover firmware.
- New tests (15): file names and models, Uniden zips (including a path-traversal entry), error pages and sizes, server listings, downloads, planning and downgrades, the write with leftovers, a scanner that changes mid-write, a symlinked firmware folder, and the window on the Qt stub.
- **Not yet tried on the real scanner or server.** In particular: whether Uniden's server lists SDS100 firmware in the same place as the database (if not, the window says so and Add File… still works), and the exact names Uniden uses for the current SDS100 files.

## v0.0.8z — Busy dialogs for Restore, Backup and Preflight

- **Fixed: "Not Responding" during Restore from Backup.** The window froze with no feedback because three steps ran on the main thread: verifying every saved backup before the list appeared (it re-hashed all of them, over 1 GB with 19 backups), the restore itself (emergency backup, file writes and full verification), and emergency recovery. All now run in the background behind a busy dialog with a moving bar and an elapsed-time counter, and the window stays responsive.
- The backup list now loads instantly (it checks each backup's structure and file sizes). Nothing about safety changed: every file is still SHA-256 verified when you pick a backup for the preview and again immediately before and after the restore.
- **Back Up Scanner Configuration** and **Scanner Export Preflight** had the same problem and now use the same busy dialog.
- While any scanner operation runs, starting another one is refused, and the application will not close (it warns "DO NOT DISCONNECT"). Closing during a master-database update was previously not blocked.
- New tests: the busy-dialog wiring for backup, restore, stale-preview refusal, close blocking, and the quick listing (including that tampered backups are still caught by the full verification).

## v0.0.8y — Undo, bulk edit and drag and drop (stage 3 of 3)

- **Undo / Redo in the Favorites List editor.** Undo and Redo buttons (Ctrl+Z, Ctrl+Y) in the editor use the same history as the Drafts & Planning menu, which now also has the shortcuts. The editor redraws and keeps your place. **Drafts & Planning → Undo All Changes…** steps back through every remembered change (up to 40) in one go after a confirmation; Redo then replays them one step at a time.
- **Bulk edit.** Select two or more channels or talkgroups (Ctrl+click or Shift+click the row numbers) and use **Change Selected…** (button, or right-click). Choose Avoid, Attenuator, Delay or Volume Offset and a value. You get one confirmation listing what will change, rows the setting does not apply to are skipped and reported, and the whole change is a single Undo step. It uses the same allowed values as the single-row editor.
- **Drag and drop.** Drop an SD card folder (the one containing BCDx36HP) on the main window to start the normal verified Import from Scanner, or drop a Favorites List `.hpd` file to open the read-only inspector. Nothing is written by a drop; anything else is refused with a reason.
- **Changed in the editor code (please test):** right-clicking inside a multi-row selection now keeps the selection (before it collapsed to one row); right-clicking outside it behaves as before. Single-row editing is otherwise unchanged.
- **Coordinate format preference removed.** It was never used: the only place coordinates are shown is GPS and Location Settings, which already follows the scanner's own DMS/DEG setting. An old preferences file containing it still loads.
- Not done: reordering by drag and drop inside a list, and a one-click "revert to the scanner's value" (to discard everything, reopen the configuration from the scanner or use Undo All Changes).

## v0.0.8x — Change summary, Find Everywhere and tidier menus (stage 2 of 3)

- **Plain-language export summary.** The Export to Scanner preview now opens with "What will change on the scanner": new lists (name, systems, departments, channels, talkgroups), removed lists, edited lists (fields edited, items added and removed) and every changed list setting or scanner setting in words (for example `Monitor: 'On' → 'Off'`). The technical file-by-file details stay below it. The summary only describes the plan the export will actually run; it adds no new write path.
- **Tools → Find Everywhere… (Ctrl+F).** One search across the active master database and the Favorites Lists of the open configuration, with no index to build. Type a name, a frequency in MHz (`154.9` matches 154.900 to 154.999, `460.025` is exact; 7 digits or more is hertz) or a talkgroup ID. Results show where each match is, its type, value and the system › department it sits in. Runs in the background, can be stopped, shows the first 500 matches, and Copy Results puts them on the clipboard. Read-only.
- **Menu tidy.** File: Manage Configurations, Backup and Restore and Storage submenus. Database: Update Database and Update Scanner's Master Database stay on top, the rarely used items move to Advanced. Favorites and Tools get Advanced submenus for the read-only inspection tools. Nothing was removed.
- New tests: export summary, search engine (query forms, frequency ranges, caps, cancel), Find Everywhere and the menu structure on the Qt-stub harness. As before, the stub cannot show appearance; please click through the new dialog and menus.
- Stage 3 (v0.0.8y) will cover undo/revert, bulk edit, drag and drop and coordinate display.

## v0.0.8w — Scanner panel, Settings, detection and cleanup (stage 1 of 3)

- **Scanner panel** (dock on the right; Tools menu toggles it): model and firmware, database date with a note when a newer database is available locally (or the card is newer), free space, number of lists, backups summary with a size warning, open configuration, and buttons for Refresh, Update Database, Update Scanner's Master Database, Export, Back Up and Clean Up Backups. A status-bar indicator shows connection state and database date.
- **Automatic detection**: reads /proc/mounts every few seconds for a FAT volume with a BCDx36HP folder and reads only scanner.inf and hpdb.cfg. Folder prompts offer the detected card ("Use detected scanner?") instead of making you browse; every write still checks the USB identity itself.
- **Tools → Settings… (Ctrl+,)**: validated preferences stored in `~/.config/sds100-database-favorites-manager/preferences.json` (invalid values fall back one at a time; the file can never stop the program starting). Safety is deliberately not a preference: the checks, the backup and the confirmation before every scanner write cannot be switched off.
- **Backups**: usage summary, size warning, and manual **Clean Up Old Backups** (keeps the newest N, never fewer than 3, lists everything before deleting, only real timestamped backup folders). **Database versions**: manual cleanup that always keeps the newest N, the current version and the version on your scanner.
- **Startup check for a newer Uniden database** (off by default; reports in the status bar, never downloads). **Theme** (system/light/dark), **font size**, **coordinate format** preference (display of coordinates comes in stage 3). **Log file** with selectable detail in `~/.local/state/sds100-database-favorites-manager/application.log`; Help → Open Log Folder.
- Low-risk confirmations (creating a local list) can be switched off; scanner writes cannot.
- New tests: preferences, detection, panel wording, housekeeping, and a Qt-stub harness (`qt_stub.py`) that runs the new window code against stand-in widgets to catch broken logic. It cannot show appearance; please click through the new dialogs.
- Coming in stages 2 and 3: change summary before export, global search, menu tidy, undo/revert, bulk edit, drag and drop, coordinate display.

## v0.0.8v — Help menu, About credits and licence

- **Licence: GPL-3.0-or-later.** `LICENSE` (full GPL v3 text), `NOTICE.md` (copyright, AI assistance, trademarks, third-party software) and an SPDX header on every source file. GPL because PyQt6 is GPL v3: a program built on it must be distributed under GPL-compatible terms.
- **About** now credits "Created by J. Lynch", states that AI was used in the build, names the licence and warranty position, and says the program is not affiliated with Uniden. A button opens the licence.
- **Help menu now works:** User Guide (F1) and Recovery and Troubleshooting open the guide inside the application with a heading list and find box; What's New shows the change log; License; Open Scanner Backups Folder; Copy Diagnostic Information (version, Python, OS, Qt, configuration name; no scanner data).
- The version now lives in one module (`help_system.py`) and a test checks it matches the application and the change log.

## v0.0.8u — Archive cleanup

- Per-version test procedures (`*_TEST.md`) moved to `docs/test-procedures/`, per-version notes to `docs/release-notes/`, and the old README, development notes, and diagnostics notes to `docs/history/`. The top level now holds `README.md`, `USER_GUIDE.md`, `CHANGELOG.md` and `DEVELOPMENT.md` (both rewritten for the current program).
- `install.sh` and `uninstall.sh` read the version from the application instead of a hard-coded 0.0.6b, so each install gets its own folder and menu entry. Tested with a throwaway home directory.
- Removed `tests_fixtures/` (byte-identical duplicates of files in `test_fixtures/`). No application code changed.

## v0.0.8t — User guide and wording cleanup

- New **USER_GUIDE.md**: the safety model, step-by-step workflows (database update, new lists, settings, export), what is and is not supported, where files and backups live, and recovery steps.
- Removed the "Experimental" wording now that the database update is verified on a real SDS100. Database menu: **Update Database (Download and Rebuild)…**, **Update Scanner's Master Database…**, **Export One State File (Advanced)…**, **Rebuild Full Database to a Folder (Advanced)…**. The duplicate "Update Database…" entry is gone. About box and status bar updated.
- A rebuilt database folder now contains README.txt (install only through Update Scanner's Master Database) instead of the old "NOT_FOR_INSTALLATION.txt". Folder names keep the historical `HPDB-Experimental-<date>` prefix so older versions still sort and load.

## v0.0.8s — Rectangle locations in new Favorites Lists

- New lists can now include sites and departments that use a rectangle location (previously refused). Your Sentinel list f_000029 (Palmetto 800, Laurens rectangle site) is the reference: the builder reproduces it byte for byte, and the new-list guard accepts it. Layout: Site, band plan(s), Rectangle row(s), then the site's frequencies.
- Rectangle departments (trunked talkgroup departments and conventional departments) follow the database layout: department row, Rectangle row(s), then members. No Sentinel sample of those exists yet, so they are untested on a scanner.
- Checks: a Rectangles location must have at least one Rectangle row directly after it, a circle location may not have one, coordinates must be latitude within 90 and longitude within 180 with up to six decimals, and there is a limit of 50 rectangles per location.
- Adding a rectangle department to an existing list or draft is refused with a message (new lists only), until a sample shows how Sentinel merges them.
- Still waiting for real samples: Motorola, EDACS, LTR and MotoTrbo systems, and IFX. See V0.0.8S_NOTES.md.

## v0.0.8r — Update Scanner's Master Database

- New **Database → Update Scanner's Master Database…**. It takes a rebuilt database from **Database → Update Database…** (download and offline rebuild, unchanged) and writes the whole database to the SD card in one step.
- Read-only check first, nothing written: the new database must cover the same states as the card; every record must be of a type and field count the card's own files already use; state files must agree with their own file names; the database may not be older than the card's; and at least 70% of the card's existing records must appear unchanged in the new files (this catches a rebuilt format that differs from what the scanner holds). The check shows both database dates and how many state files change.
- Then the same controlled write as the favorites export: fresh SHA-256-verified backup of the whole card configuration, SHA-256 staging of every file, automatic restore of every changed file if anything fails, `sync` at the end. State files are written first and `hpdb.cfg` last. Only changed files are rewritten. Favorites lists, profile.cfg and every other file are never touched.
- Favorites export and preview now ignore the HPDB folder. A saved configuration keeps the older database it was taken with, which would otherwise have been reported as a difference after an update.
- Limits: the rebuild is still labelled experimental (it was matched to a 2025 reference, not verified against a Sentinel-written database); the update refuses a package covering different states than the card. Pending physical test. See MASTER_DATABASE_UPDATE_TEST.md.

## v0.0.8q — Display layouts and colours

- New **Scanner Settings → Display Layouts and Colours…** with two tabs. **Screen items** shows the 25 layout rows (7 layouts); each slot is a dropdown limited to the item names your real SDS100 profile uses for that screen row (for example FL_Name, Frequency, TGID, Rssi, Volume, REC, GPS). **Screen colours** shows the 46 colour records; every colour is a six-digit hex value (for example ff4600), text-edited and checked.
- Safe by construction: the number of slots in a record never changes, identifiers cannot change, an item may not appear twice in one row, and an item name not seen for that row in a real profile is refused. A record that doesn't match the known layout is shown as not editable and preserved exactly.
- I don't know which item each colour pair belongs to (the file doesn't say), so colours are labelled by position (Colour 1 first/second, ...). Change one, check the scanner screen, and tell me what it affected so I can label them. IFX frequencies stay locked.
- Same review, backup, export guard and rollback as the other settings. Pending physical test.

## v0.0.8p — Settings split into separate menu entries

- The single crowded settings dialog is replaced by five entries under Scanner Settings: **Global Settings…**, **Search Settings…** (common search, Close Call, Limit Search, Tone-Out, band defaults, Waterfall, waterfall bands and colours, broadcast screens), **Weather Settings…** (weather and SAME groups), **Display Settings…** (display, backlight) and **Hardware Settings…** (battery, owner info, clock, recording, standby).
- Each uses the same validation, review, backup, export guard and rollback as before; only the grouping changed. Every previous tab appears in exactly one entry.
- IFX: the RadioReference thread only explains what IFX is for (moving the receiver's intermediate frequency to avoid birdies). It gives no stored format, and your profile.cfg has no populated IFX values, so IFX frequencies stay locked until a profile with some set is available.

## v0.0.8o — Searches and tools settings

- The settings dialog (now **Global, Search, Display and Hardware Settings…**) gains tabs for Limit Search (10 slots), Tone-Out (32 slots), Waterfall, Waterfall custom bands, Waterfall colours, Band defaults (31 bands), the preset broadcast screen and the 10 custom broadcast screen bands. Slot-based records (Limit Search, Tone-Out, band defaults, SAME groups, waterfall bands) are shown as a grid with one row per slot.
- Validation follows the specification and your real profile.cfg: frequencies 25-1300 MHz in Hz, tone frequencies 0 or 250.0-3500.0 Hz, steps and spans from fixed lists, colours as six lowercase hex digits, broadcast band edges 000-1300 MHz, names up to 16 characters (my limit, see notes). A Limit Search lower frequency may not exceed its upper frequency. Slot IDs and reserved fields cannot change.
- Same validated export path as the other settings (guard, verified backup, rollback). IFX frequencies, display layouts and colours remain locked. See V0.0.8O_NOTES.md and SEARCH_TOOLS_TEST.md. Pending physical test. Roadmap next: display layouts and colours, then Update Scanner's Master Database.

## v0.0.8n — Display and hardware settings; favorites items moved

- Scanner Settings → **Global, Display and Hardware Settings…** (renamed) gains tabs for Display (Motorola/EDACS TGID format, simple mode, colour mode), Backlight (brightness, key backlight, flash LED, external power light, squelch light, key light time), Battery (battery save, alert interval, tone, volume), Owner info (four 24-character lines), Clock (time zone, daylight saving), Recording (replay duration, user recording) and a read-only Standby tab. Same validation, review, backup and export guard as the other settings.
- **Quick Keys Status…** and **Favorites List Relationships (Read-only)…** moved to the Favorites menu.
- Layouts follow a real SDS100 profile.cfg where it differs from the specification: DisplayOption has 13 fields, Backlight 11 (the SDS200-only fields are absent). A record with a different layout is simply not shown or edited; other changes still export. The hour format (12H/24H) and the standby mode stay read-only because the specification does not document them.
- See V0.0.8N_NOTES.md and HARDWARE_SETTINGS_TEST.md. Pending physical test. Roadmap next: searches and tools (Limit Search, Tone-Out, Waterfall, band defaults, broadcast screens, IFX).

## v0.0.8m — Favorites List Settings moved to the Favorites menu

- **Favorites List Settings…** is now under the Favorites menu (between Open and Delete Favorites List), not Scanner Settings. No other change. v0.0.8l's list settings editing and export were tested on the real scanner.

## v0.0.8l — Favorites List settings (f_list.cfg): edit and export

- New Scanner Settings → Favorites List Settings…: for every list, edit Name, Location Control, Monitor, Quick Key (Off/0-99), Number Tag (Off/0-99), the ten Startup Keys and the 100 system quick key flags. Two lists cannot share a quick key, number tag or name; every value is validated; the save is reviewed, backed up and transactional.
- Export to Scanner now accepts these changes to existing f_list.cfg rows (also together with added or removed lists). List order, filenames, row layout and every other byte must stay identical; the guard re-validates everything and uses the same verified backup, staging and rollback.
- New `flist_settings.py` (rules and lossless patching), `save_local_flist_settings` in `scanner_configurations.py`. See V0.0.8L_NOTES.md and LIST_SETTINGS_TEST.md. Pending physical test. Roadmap next: display and hardware settings.

## v0.0.8k — Core scanner settings: edit and export (first step toward full configuration export)

- New `profile_schema.py`: one spec-driven set of validators (Uniden SDS Series File Specification V2.00, checked against a real SDS100 profile.cfg) for GlobalSetting, SearchCommon, CloseCall, Weather and WxSameList (SAME groups). Reserved fields can never change; every editable field is range/choice checked; layout, row count and all other bytes must stay identical.
- Scanner Settings dialog (Scanner Settings menu) now has tabs for all five records, including previously read-only fields: priority interval/channels, search keys, key beep, volume, squelch, global auto filter, audio-off time, Close Call alert and band options, search defaults, weather options, SAME group names/FIPS codes.
- Export to Scanner accepts any combination of these edits with the existing profile edits (quick keys, location/GPS, service types), using the same verified backup, staging and rollback.
- Not yet covered (later steps): display/backlight/battery/owner/clock/recording/standby, Limit Search, Tone-Out, Waterfall, band defaults, broadcast screens, IFX/avoid frequencies, display layouts and colours. Updating the scanner's master database will be its own menu item under Database, as a separate step. Pending physical test.

## v0.0.8j — Non-P25 trunked lists verified against real Sentinel files

- New trunked lists now match real Sentinel-written NXDN (FleetTalk Carolinas) and DMR (Oconee County Emergency Services) lists: site NAC is `0` for non-P25 systems, DMR One Frequency uses channel number `0`, NXDN keeps the database channel numbers and `RAN=` options, DMR keeps the bare colour code (e.g. `8`), no band plan is written except the P25 Standard default.
- Still unverified against real files: Motorola, EDACS, LTR and MotoTrbo. See V0.0.8J_NOTES.md. Pending physical test.

## v0.0.8i — New Favorites Lists from trunked systems; safer export finish

- Add to Favorites → "new list" now works for trunked systems (sites, band plans, site frequencies, talkgroup departments, talkgroups). Values come from the database; everything else is the scanner default or blank, never copied from another item. Quick keys, number tags, Avoid and Priority start Off.
- Export accepts new trunked list files (same checks, backup, rollback as conventional lists).
- Export now forces a flush to the card (`sync`) and the result dialog tells you to unmount and wait for "safe to remove" before powering the scanner off. (A v0.0.8h export looked empty when the scanner was powered off before the card finished unmounting.)
- Rectangle-type locations are refused. See V0.0.8I_NOTES.md and TRUNK_NEW_LIST_TEST.md. Pending physical test.

## v0.0.8h — Export of new and removed Favorites Lists

Export to Scanner adds new list files (with their f_list.cfg row) and removes lists deleted in this program (only when the scanner copy still matches the archived deletion). Rollback restores every change. See V0.0.8H_NOTES.md. Pending physical test.

## v0.0.7q — Multi-Favorites HPD export (pending physical test)

Export now supports multiple existing, individually eligible Favorites HPD files in one confirmed batch. All changed files are validated before writing; a fresh verified scanner backup is created, each file is staged and SHA-256 checked, and failures trigger reverse-order rollback from backup. New HPD files, CFG/INF changes and unsupported structural changes remain blocked. The current scanner configuration filename indicator was user-tested in the preview build. Multi-file scanner export is not yet physically verified.

## v0.0.7p — Restore a database channel to an existing Favorites department

- Fix **Add to Favorites** incorrectly creating a second system/department when the selected list already contains a scanner-imported system. Scanner-native and database-source keys differ; a unique existing system is now found by kind and normalized name, and a unique department by type and normalized name. Preserve the scanner-native system/department headers, source metadata, and other channels.
- When adding a conventional channel to a scanner-imported Favorites List, construct the new native leaf from a channel already in that department, changing only the new-record marker, channel name, and frequency. This preserves native layout and reserved settings; the channel initially inherits the template channel's other settings, which may be edited afterward.
- Skip duplicate channels by name/frequency, reject ambiguous system or department names, frequency collisions, missing native templates, and unsupported new departments instead of silently creating duplicates. Existing native export checks still apply.
- Preserve the tested v0.0.7o physical channel-deletion export and prior v0.0.7n first-write workflow. No additional scanner write modes, firmware functions, or live GPS functions.
- 150 available pure-Python regression tests pass. GUI integration requires the Kubuntu test in `EXISTING_DEPARTMENT_MERGE_TEST.md`.

## v0.0.7o — Expanded Favorites export (REAL SCANNER WRITE)

Building on the **user-tested v0.0.7n physical write**, File → Export to Scanner… now accepts more changes **within one existing Favorites HPD**: multiple supported native field edits, system/site/department name changes, or insertion/deletion of individual C-Freq, T-Freq and TGID records. The existing editor and local Save/Save As workflow are unchanged. The native export guard validates the existing record hierarchy, new-record IDs, source-template preservation, documented frequency/TGID values, and last trunked-site frequency protection. Eight-column and nine-column T-Freq templates are supported by Add Site Frequency, preserving the source reserved ID field instead of manufacturing an ID.

The normal single export flow still creates a fresh SHA-256-verified BCDx36HP configuration backup, checks the mounted SDS100 identity and source/destination again, stages and verifies the replacement, and records restoration instructions. A verified backup can be restored manually, including after FAT32 reformat/reinitialization if needed. It is not a guarantee of power-loss atomicity.

**Deliberate scope for this release:** one existing HPD file per export; field-only changes or leaf insertions/deletions (not mixed in one export); no entire system/site/department deletion, no added HPD files, no opaque CFG/INF changes, and no multi-file batch writes. This is the next measured extension, not a claim of complete export support. See `EXPANDED_FAVORITES_EXPORT_TEST.md` for the single physical scanner test.

---

## v0.0.7n — First controlled physical SDS100 export

- Real, explicitly confirmed write path for **one existing Favorites HPD, exactly one C-Freq/T-Freq frequency field**. Other modifications remain blocked.
- Practical mounted-USB identity (`1965:001c`, manufacturer, SDS100 product, vfat, mount provenance), without requiring cryptographic authentication.
- Automatically create/verify fresh full BCDx36HP configuration backup before writing, compare source/destination/identity again after backup, stage on scanner filesystem, SHA-256 verify staged and final bytes.
- Best-effort immediate rollback on caught post-replacement errors; documented manual restore from backup for interruption/power loss. No claim of power-loss atomicity.
- Integrated compact automatic preview, explicit second confirmation, visible nonmodal worker progress and result. Retain old diagnostic audits in Tools.
- New isolated filesystem tests exercise real write implementation and rejection/rollback branches. Actual SDS100 acceptance and GUI behavior require user test.

## v0.0.7m — Durable recovery rehearsal on isolated local mock (scanner writes BLOCKED)

- Extend **File → Export to Scanner…** automatic preview with **DURABLE WRITE/RESTART RECOVERY REHEARSAL — LOCAL MOCK ONLY**. This is integrated into the existing workflow, not a second editor or a required separate preview.
- Copy one eligible native Favorites HPD into a new temporary LOCAL mock device on a different filesystem from the scanner. Prefer a real narrowly edited frequency candidate; when the selected configuration has structural/CFG edits, use an explicitly labeled synthetic one-field change from a scanner HPD *only for the mock rehearsal*. Structural edits remain blocked for export.
- Build and SHA-256 verify a fresh local mock backup, create an fsynced recovery journal, stage and verify the candidate, simulate successful replacement, and independently recover from interruptions after journal creation, staging, and replacement (3/3). Verify the original scanner file did not change and delete the temporary mock workspace.
- Reject unsafe path names, symlinks, changed candidate bytes, invalid native changes, corrupted recovery backups, and unexpected destination bytes. On recovery mismatch, retain the journal and fail closed.
- **No scanner writes. Proceed with Export remains disabled.** A local mock cannot verify actual FAT32 atomicity, hardware interruption recovery, trusted device identity, or scanner acceptance. A physical first-write test is NOT yet authorized.
- Preserve the tested v0.0.7l single Export-to-Scanner preview/confirmation workflow, all prior GUI functionality, local configurations, and verified backup history.

See `DURABLE_RECOVERY_TEST.md` for the single Kubuntu GUI test.

## v0.0.7l — Integrated automatic export preview, fail-closed

- **File → Export to Scanner…** is the one-step production-style entry point. It automatically compares the chosen saved local configuration to the selected SDS100 Mass Storage drive, displays progress, then opens **Export to Scanner — Preview & Confirmation** with file counts and **Cancel / Proceed with Export**.
- **Proceed with Export is intentionally disabled in this release**. The app contains no scanner write path. A specific unsupported candidate such as `app_data.cfg` is shown in the confirmation dialog. Detailed diagnostics can be expanded.
- Previous standalone preview is retained as a troubleshooting-only command under **Tools → Diagnostic Export Preview (Read-only)…**, not as a required separate step.
- Add a native candidate audit that accepts for *format inspection only* narrow HPD replacements where only the documented C-Freq or T-Freq frequency field changes. Reject added files, CFG/INF edits, structural HPD changes, other field changes, line-ending changes, and undocumented-column modifications. Passing this inspection is **not** proof of scanner acceptance and never enables writing.
- Preserve the tested v0.0.7k local rehearsal, USB identity evidence, offline configurations, existing editor, worker teardown, and read-only scanner safety.
- Run 105 available pure-Python regression tests. One PyQt6-dependent regression module is not runnable in this environment; the Kubuntu GUI test is still required.

See `EXPORT_WORKFLOW_TEST.md` for the next single GUI test.

## v0.0.7k — Read-only local export safety rehearsal

- Extend the existing background **Preview Scanner Export (Read-only)** with a local-only staging and rollback rehearsal. This does NOT add a second editor, and does NOT write to the scanner.
- For the proposed ADD/REPLACE set, copy source bytes into a verified local temporary staging area; copy replacement originals into local rollback storage; verify SHA-256 before and after; simulate a successful apply and an injected interruption; then restore simulated originals and remove simulated additions. The temporary directory is deleted on exit.
- Refuse a temporary workspace on the scanner filesystem, symlinked candidate files, unsafe or case-colliding paths, inconsistent change plans, FAT32 oversize files, and a conservative free-space estimate failure.
- Report local rehearsal separately from on-device validation. This **does not** verify real FAT32 atomicity, power-loss handling, or actual scanner rollback. Identity/model verification and native compatibility remain unresolved; scanner export stays disabled.
- Preserve the tested v0.0.7j USB identity evidence, previous Favorites GUI, multiple editable local configurations, Save/Save As, verified backups, and safe non-modal preview worker lifetime.

## v0.0.7j

- Add Linux read-only scanner USB identity evidence to the **existing** export preflight, rather than a separate mandatory workflow. Correlates mounted filesystem with USB vendor/product descriptors using mountinfo and sysfs; rejects bind mounts, non-block-device mounts, malformed descriptors, and missing USB associations.
- Report explicitly distinguishes a USB mount correlation from verified SDS100 identity. USB serial descriptor value is not displayed. No model allowlist has yet been established; scanner export remains disabled.
- Include the preflight/identity evidence in the existing read-only export preview.
- Six new pure-Python identity tests; 87 available regression tests pass. One additional PyQt6-dependent test cannot run in this build environment and must be exercised on Kubuntu.

## v0.0.7i
- Add **Save Configuration As…** to the existing File menu; copy the current named offline configuration into an independent, editable local configuration and switch the GUI to it.
- Include all unsaved native Favorites working-draft edits from the current configuration in the new copy **without changing the original local configuration or scanner**.
- Verify source manifest, copied bytes, new checksums, native HPD round-trips, and opaque CFG/INF bytes. Reject duplicate names, unsafe paths and symlinks; use atomic no-overwrite publication on Kubuntu/Linux.
- Add automated tests including an actual supplied native HPD sample, edited frequencies, duplicate-name and rollback protections.
- Keep previous GUI editor and verified native field patch; scanner export remains disabled. Standalone read-only preview is a development diagnostic, not the eventual production export workflow.

## v0.0.7h
- Integrate a byte-preserving, field-aware HPD serialization path into the EXISTING Favorites GUI and existing Save Configuration action; no second editor.
- For field-only edits, verify the loaded native source SHA-256, change only the intended native field bytes, and preserve all unrelated bytes, tabs, BOM, record order, unknown fields, and individual CR/LF terminators.
- Validate edited frequency Hz, TGID, channel names, documented modulation/audio choices, and Avoid values; reject changes to reserved/undocumented T-Freq extension columns.
- Retain previous local-only structural edit serialization (add/remove records) as a compatibility path, not yet certified byte-preserving; export to scanner remains disabled.
- Add pure offline regression tests using actual uploaded native HPD samples and synthetic mixed-newline/BOM/unknown-extension cases.
- Preserve the v0.0.7g3 tested nonmodal visible progress window and all prior functionality. No scanner writes.

## v0.0.7g3
- Restore a VISIBLE progress dialog during read-only scanner export preview, fixing the v0.0.7g2 usability regression (status bar alone was too easy to miss).
- Use a non-modal custom QDialog with an indeterminate animated progress bar and an updating elapsed-seconds label, without a nested event loop or cancellation that hides active work.
- Keep the dialog visible until the preview QThread has fully terminated, then hide and defer deletion before opening the report in a later event-loop turn.
- Add static regression tests requiring visible progress and safe teardown order.
- Preserve v0.0.7g2's successful native specification field mapping audit, prior tested features, and disabled scanner export. No scanner writes.

## v0.0.7g2
- Address a reported Qt/Wayland SIGABRT (exit 134) during export preview report window creation following the v0.0.7g1 specification audit.
- Remove the modal QProgressDialog from the read-only preview; show background activity in the status bar instead.
- Wait for the native QThread to terminate, then defer opening a non-modal report window; avoid nested dialog.exec() during Qt object deletion.
- Connect worker.deleteLater to worker.finished in its own thread, and release the QThread only after wait() confirms termination.
- Fix spec audit interpretation: T-Freq column 5 is reserved, not a conventional Avoid enum. Do not report spurious T-Freq Avoid warnings.
- Preserve all existing functionality and three scanner export blockers. No scanner writes.

## v0.0.7g1
- Fix v0.0.7g preview integration: invoke the already-imported read-only specification field mapping audit and include its report after the variable-length audit.
- Add a full preview integration regression test to ensure the section is emitted and export remains disabled.
- Preserve all previous features, background Qt lifecycle safeguards and read-only scanner safety gates. No scanner writes.

## v0.0.7g
- Added read-only field-position audit against Uniden SDS Series File Specification v2.00 (PDF pages 16–17): C-Freq, T-Freq and TGID columns 4–8, and documented record widths.
- Verify observed ASCII decimal Hz frequency fields, TGID string representation, modulation/audio-type enumerations, Avoid values, and T-Freq LCN representation without editing files.
- Report observed nine-column T-Freq layouts as undocumented extensions to preserve opaquely, not as confirmed field meanings or scanner errors.
- Preserve all v0.0.7f1 functionality, backup checks, Qt worker safeguards, and disabled scanner export. No scanner writes.

## v0.0.7f1
- Fix variable-length audit's one-digit TGID case: search for an eligible multi-digit value within the same file and layout before testing shortening.
- Explicitly report any layout/file combinations without an eligible shorter value as skipped, not as a failed edit; keep true errors as warnings.
- Preserve all previous read-only audits and scanner export safety blockers. No scanner writes.

## v0.0.7f
- Added read-only variable-length native field mutation and byte-exact restoration audit for C-Freq, T-Freq (8/9 columns), TGID.
- Scanner export remains disabled.

## v0.0.7e
- Added read-only in-memory byte-level field edit/reversal probes for each observed C-Freq, T-Freq, and TGID layout per Favorites file.
- Verify exact restoration and unchanged adjacent fields, tabs, line terminators and trailing empty columns.
- Preserve v0.0.7d audit and export-disabled safety gates.

## v0.0.7d
- Corrected stale application title to show v0.0.7d.
- Added read-only per-column value-class census, separated by native record type and observed layout width.
- Preserved export-disabled safety gates and previous audits.

## v0.0.7c — Native Favorites record layout census (read-only)
- Adds column-count distributions for C-Freq, T-Freq and TGID native Favorites records, preserving trailing empty fields.
- Flags missing/non-decimal column 6 values, with bounded location-only examples.
- Preserves v0.0.7b1 Qt/Wayland preview cleanup fix; scanner export stays disabled.
- Layout observations do not certify field semantics or edited-file serialization.

## v0.0.7b1 — Export preview Qt/Wayland cleanup regression fix
- Replace synchronous progress-dialog close during QThread.finished cleanup with hide and deferred deletion, avoiding the reported Wayland close/destructor crash path.
- Prevent closing the main window while a preview worker is active.
- Preserve read-only frequency audit and disabled scanner export.
- Needs user GUI regression test; fix not yet verified on Kubuntu/Wayland.

## v0.0.7b — Official specification frequency unit cross-check
- Reference Uniden SDS100/150/200 File Specification v2.00 (Basic Rule, p.6): frequency integers use 1 Hz units.
- New read-only audit checks exact integer Hz-to-MHz-to-Hz conversion for every observed Favorites C-Freq and T-Freq numeric value.
- Reject fractional sub-Hz input in the pure conversion helper rather than silently rounding. No TGID frequency conversion.
- Distinguish official unit rule from still-unverified record-column mapping, scanner acceptance, and edited-file serialization.
- Scanner export remains disabled; no scanner writes.

## v0.0.7a — Read-only native numeric representation analysis
- Report raw numeric ranges and digit-width distributions for conventional frequency, trunked frequency, and TGID records.
- Show /1,000,000 MHz conversion as a hypothesis based on existing display logic, not verified native units.
- Never convert TGIDs to MHz; no scanner writes.

## v0.0.6z — Read-only native field-value format audit
- Survey column 6 of C-Freq, T-Freq, and TGID records, reporting ASCII decimal representation, blanks, and anomalies without modifying files.
- Explicitly distinguish observed format from scanner-valid ranges or serialization. Export remains disabled.

## v0.0.6x — Read-only reversible native edit probe
- Adds one-field in-memory edit/restore checks per eligible Favorites HPD; compares all other records and exact original bytes after restoration. No file writes. Export disabled.

## v0.0.6w1 — Import progress cancellation fix
- Set a thread-safe cancellation event directly from the GUI thread, rather than queueing a slot on the busy import worker.
- Keep progress visible until the worker exits and incomplete staging is cleaned.
- Check cancellation after the final staging rename.
- Scanner remains read-only.

## v0.0.6w — Read-only Favorites record round-trip inspection
- Inspect native Favorites HPD text, retaining line endings, empty fields and byte-exact original content.
- Run existing native Favorites parser and basic header/structural checks; report warnings without changing files.
- Explicitly do not certify edited serialization, CFG/INF formats or scanner export.
- Scanner writing remains disabled.

## v0.0.6u — Export Safety Audit (read-only)

- Adds scanner identity, free-space, and native format safety audit to existing background export preview.
- Explicitly reports unresolved blockers; does not enable export.
- Preserves v0.0.6t1 comparison, backup matching, and responsive progress dialog.

## v0.0.6t1 — Responsive Export Preview

- Run scanner file comparison and backup checksum verification in a background QThread worker.
- Display a modal busy dialog while the operation runs, without blocking Qt event processing.
- Delay result dialogs until the worker thread has finished, preserving the tested import-thread cleanup pattern.
- Read-only: no scanner writes; export remains disabled.


## v0.0.6v — Read-only native file inspection
- Report lossless decoding of HPD files and inspect Favorites TargetModel/FormatVersion headers.
- Preserve CFG/INF as opaque bytes; do not claim native serialization support.
- All scanner writes remain disabled.

## v0.0.6y
- Added read-only multi-record, multi-column native Favorites reversible edit probe with untouched-record, field-count, line-ending and byte restoration checks.
- No native scanner write capability enabled.
