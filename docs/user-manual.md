# SDS-Manager User Manual

Version 0.1.31 · by J. Lynch, developed with the help of AI (Anthropic's Claude) · [PDF with each release](https://github.com/jmlynchjr/SDS-Manager/releases)

Use the outline button (☰) at the top right of this file to jump to a chapter.

## About this manual

> [!NOTE]
> **On a Mac?** This fork adds macOS support. See [Appendix: Running on macOS](#appendix-running-on-macos) for install steps, SD card safety and what's different.

This manual describes **SDS-Manager version 0.1.31**, a Linux program for managing a Uniden SDS100 scanner's Favorites Lists, settings and system database from a PC, without Sentinel.

Chapters 1 to 4 cover installing, the main window and scanner configurations, and are worth reading first. Chapter 10, *Exporting to the scanner*, explains how changes reach the scanner and how they are protected. The rest can be read as you need them.

### Conventions

- **Bold** names a button, menu item, window or setting as it appears on screen, for example **Save Configuration** or **Favorites → Keys & Tags…**.
- An arrow (→) shows a path through menus: **File → Export to Scanner…** means open the File menu and choose Export to Scanner….
- `Monospace` shows something you type, a file or folder, such as `~/.local/share` or `f_list.cfg`.
- `~` means your home folder, for example `/home/yourname`.
- An ellipsis (…) on a button or menu item means it opens a window or dialog.

> [!NOTE]
> Notes give background that helps explain why something works the way it does.

> [!TIP]
> Tips suggest a quicker or better way to do something.

> [!CAUTION]
> Cautions mark something that changes the scanner or can't easily be undone.

### About SDS-Manager

SDS-Manager was created by **J. Lynch**, developed with the help of AI (Anthropic's Claude) and tested on a real SDS100. AI was also used to help write this manual.

It is **free software** under the GNU General Public License version 3 or later: you may use, share and change it under the licence's terms. The source, the releases and the version history are at **github.com/jmlynchjr/SDS-Manager**.

SDS-Manager is an independent program. It is not made, endorsed or supported by Uniden or RadioReference. Uniden, SDS100, SDS200 and Sentinel are names and trademarks of their owners; RadioReference is a trademark of RadioReference.com LLC. The program follows Uniden's *SDS Series File Specification V2.00* and is provided as is, without warranty. Use it at your own risk.

Laws on listening to radio communications differ between places. You are responsible for using the scanner and this program lawfully.

## 1. Introduction

### What SDS-Manager does

SDS-Manager works with the files on the SDS100's memory card, the same files Sentinel uses. With it you can:

- build **Favorites Lists** from the **RadioReference** database, or type systems, departments, channels and talkgroups in by hand;
- **edit** lists: names, frequencies, tones, avoids, attenuators, delays, alerts and the rest of each channel's settings; cut, copy and paste between lists; change many channels at once;
- manage **quick keys, number tags and scanning** in one window (**Keys & Tags**), with scan profiles, a LibreOffice spreadsheet and a printable key card;
- change the scanner's **settings**: global, search, weather, display, display layouts and colours, hardware, GPS and location, and service types;
- update the scanner's **system database** from a Uniden database archive, and put new **firmware** on the card for the scanner to install;
- **export** everything to the scanner with checks, a backup first, and automatic recovery if a write fails;
- work with **SDS100 Monitor**: open what you hear in SDS-Manager, see how often each channel was heard, put the Monitor's unit names on the scanner, and share quick key names and scan profiles.

### What you need

- A PC running Linux with **Python 3.10 or newer** and **PyQt6**. The program is developed on **Kubuntu**; the install steps here are for Kubuntu and other Debian- and Ubuntu-based systems.
- A Uniden **SDS100** and its USB cable. The program is written for the SDS100; other models are refused.
- For database contents: a **RadioReference Premium** account (chapter 5).
- Recommended: `python3-keyring` (keeps your RadioReference password in KDE Wallet or GNOME Keyring) and `python3-openpyxl` (the Keys & Tags spreadsheet). The package installs both when it can.

### How it works

SDS-Manager never edits the scanner directly. It keeps **scanner configurations**: copies of the scanner's files on your computer.

1. **Import from Scanner…** copies the scanner's configuration into SDS-Manager's library.
2. Every change you make goes into that copy. The scanner isn't touched.
3. **Save Configuration** keeps your changes in the copy.
4. **Export to Scanner…** compares the copy with the card, shows what will change, backs the card up, writes only what changed, and checks every file it wrote.

> [!NOTE]
> Before anything is written, every changed file is checked against Uniden's file specification and against real files from a working SDS100. A change SDS-Manager doesn't fully understand is refused, not guessed at.

## 2. Installing

> [!NOTE]
> **On a Mac?** This fork adds macOS support. See [Appendix: Running on macOS](#appendix-running-on-macos) for install steps, SD card safety and what's different.

### Install the package (recommended)

1. Download `sds-manager_<version>_all.deb` from the project's **Releases** page on GitHub.
2. In a terminal, in the folder you downloaded it to:

```
sudo apt install ./sds-manager_<version>_all.deb
```

apt installs PyQt6 and the other packages it needs. SDS-Manager appears in the application menu, and `sds-manager` starts it from a terminal. The program is installed in `/opt/sds-manager`.

Your configurations, databases, backups and settings live in your home folder, not in the program folder, so installing a new version or removing the program never touches them.

### Updates

**Help → Check for Updates…** looks for a newer `sds-manager` package in `~/Downloads`, or on the project's GitHub releases once you enter the repository, and installs it with **Install**.

### Removing it

```
sudo apt remove sds-manager
```

Your data stays in your home folder.

### Building from source

The source on GitHub runs with `./launch.sh` from its folder, or installs for the current user with `./install.sh`. The RadioReference application key is **not** in the source; the release packages include it. If you run SDS-Manager from source, enter your own RadioReference application key under **Advanced** in **Tools → RadioReference Account…**.

The automated tests run with `python3 -m unittest discover -s .` in the source folder.

## 3. The main window

### Panels

- **Database Contents** (left): the RadioReference database, browsed by country, state and county (chapter 5). Select a system to see its departments, channels and talkgroups, and use **Add to Favorites** to put them in a list.
- **Favorites Lists** (right): the lists of the open scanner configuration, in the scanner's order, with each list's systems, departments and channels. The **Favorites List** dropdown picks the list; the **Keys / Tag** column shows quick keys and number tags (for example *Key 03 · Tag 12* beside a system, *Key 04* beside a department, *Tag 120* beside a channel).
- **Scanner panel** (right side; show or hide it from the **Tools** menu): when the SDS100's card is mounted, it shows the model, firmware, database date, free space and number of lists, your backups and the open configuration, with buttons for the common jobs. Detection only reads the card's identity files.

### The status bar

The bottom of the window shows the open configuration's name, with:

- **\*** when there are unsaved changes;
- **— not on scanner yet** when saved changes haven't been exported to the scanner (chapter 10). Hover over the name to see when the scanner last matched the configuration.

The bottom right shows whether the scanner's card is connected.

### Menus

| Menu | Contents |
|---|---|
| **File** | New, import, open, save and export scanner configurations; Manage Configurations; Backup and Restore; Storage |
| **Edit** | Undo, Redo, Undo All Changes |
| **Favorites** | Everything about Favorites Lists, including Keys & Tags |
| **Database** | Rebuild the system database from an archive, and update the scanner's database |
| **Scanner Settings** | The scanner's settings, and Update Scanner Firmware |
| **Tools** | Settings, Find Everywhere, Name Unnamed Talkgroups, Search Frequency in RadioReference, RadioReference Account, Theme |
| **Help** | User Guide, Recovery and Troubleshooting, What's New, Check for Updates, backups and log folders, licence and About |

Rarely used and read-only inspection tools are in **Advanced** submenus. A full list is in the appendix.

### Undo and redo

**Undo** and **Redo** (Ctrl+Z, Ctrl+Y, also on the **Edit** menu) work in the main window and the Favorites List editor. **Edit → Undo All Changes…** steps back through up to 40 remembered changes at once. Undo only affects the open configuration before you save; it never changes the scanner.

### Drag and drop

Drop the scanner's card folder on the main window to import it, or drop a `.hpd` list file to inspect it read-only.

## 4. Scanner configurations

Everything you edit belongs to the **open scanner configuration**. You can keep several, for example one per scanner, or a spare to try ideas in.

### Import from the scanner

1. Connect the SDS100 to the PC with its USB cable and choose **Mass Storage** on the scanner. Its card appears as a removable drive.
2. **File → Import from Scanner…**. Choose the card's top folder, the one containing `BCDx36HP` (the detected card is offered first).
3. Give the configuration a name. SDS-Manager copies and checks the files, then opens it.

> [!TIP]
> Import again whenever the scanner was changed elsewhere (on the scanner itself, or in Sentinel), so you work from what the scanner really has.

### Open, save and save as

- **File → Open Scanner Configuration…** opens a saved configuration. If the open one has unsaved changes you are asked first (Save, Discard or Cancel).
- **File → Save Configuration** (Ctrl+S) keeps your changes.
- **File → Save Configuration As…** saves the open configuration under a new name.

### New scanner configuration

**File → New Scanner Configuration…** makes a configuration with the settings of one you choose (GPS, display, service types, search, alerts and so on) and **no Favorites Lists**. Add lists to it from the Favorites menu.

> [!CAUTION]
> Exporting a new configuration to the scanner it came from removes that scanner's current Favorites Lists. The export backs the scanner up first, and the old lists are kept in the backup.

### Manage configurations

**File → Manage Configurations** has **Rename**, **Delete** and **Validate Scanner Configuration…**. Validate checks every file of a configuration against its saved checksums and Uniden's file rules, and changes nothing.

## 5. RadioReference

The **Database Contents** panel comes from **RadioReference**, live, through your own RadioReference account.

### Your account

**Tools → RadioReference Account…** signs SDS-Manager in with **your own RadioReference account**, which needs an active **Premium** subscription.

1. Enter your username and password.
2. Press **Save and Test Sign-in**. It shows your username and when your Premium subscription ends.

- Your password is kept in **KDE Wallet** or **GNOME Keyring** (through `python3-keyring`), never in a settings file. Without a keyring it is kept only until SDS-Manager closes. **Forget Saved Password** removes it.
- The application key, which identifies SDS-Manager to RadioReference, is built into the release package. Only a build without one (for example, run from source) shows an **Advanced** section for a key of your own.
- SDS-Manager talks to RadioReference directly from your computer, always over HTTPS.

> [!NOTE]
> RadioReference data is used only to build and update the Favorites Lists of your own scanner. It is kept in memory while SDS-Manager runs; only what you add to a list is saved, in your configuration.

### Browsing

1. Choose the country and state.
2. Choose the **County**:
   - **Statewide systems and agencies** lists the state's trunked systems and statewide agencies;
   - a county lists its own conventional frequencies (as one system, with RadioReference's categories as departments), its trunked systems and its agencies.
3. Choose a system. It is loaded when you choose it.

**All Systems / Conventional / Trunked** narrows the list, and the search box finds names in what is shown.

### Searching for a frequency

**Tools → Search Frequency in RadioReference…** shows what uses a frequency: conventional frequencies in a county (**Search County**) or the whole state (**Search Whole State**); choose the **State** and **County** in the window (they start as Database Contents' choice), and, with **Include trunked site frequencies** ticked, the site frequencies of the area's trunked systems (system, site, LCN, NAC or colour code). Searching a whole state with trunked sites reads every system's sites once, which takes a while the first time; they stay in memory until SDS-Manager closes. **Add to Favorites List…** puts a conventional result into a list. SDS100 Monitor can open this window for the frequency it is hearing.

### Which systems can be used

Conventional systems can always be used. Trunked systems can be used when their type has a list confirmed working on a real SDS100:

- **P25**;
- **DMR**, with one frequency per site (each talkgroup keeps its timeslot) or several (Capacity Plus, Connect Plus, Tier III, written as MotoTrbo, as Sentinel does). Every frequency needs its logical channel number on RadioReference;
- **NXDN in NEXEDGE format**, with each frequency's channel number and RAN.

Other types (Motorola, EDACS, LTR, NXDN IDAS) show why they can't be used yet. Talkgroups that RadioReference marks as fully encrypted are left out.

Talkgroup and channel names, frequencies, tones, NACs, colour codes, modes, service types and locations come from RadioReference. Everything else starts at the scanner's defaults.

## 6. Favorites Lists

### Making a list from the database

1. Open your configuration (**File → Open Scanner Configuration…**).
2. In **Database Contents**, select a system and use **Add to Favorites**.
3. Choose **Create a new Favorites List** to start a list from your selection, or add to an existing list.
4. For conventional systems, pick departments and channels. For trunked systems, pick site frequencies and talkgroups. Rectangle locations are supported in new lists.
5. **File → Save Configuration**, then **File → Export to Scanner…**.

New items take their information from the database, otherwise the scanner's default. Nothing is copied from another item, and two items never share a quick key or number tag.

### The Favorites menu

- **New Favorites List…** (Ctrl+N) asks for a name and what the list starts with: the system selected in the database, what you cut or copied in the list editor, or a conventional system you type in (system, department and first channel). A list always starts with at least one system.
- **Edit Favorites List…** (Ctrl+E) opens the list editor for the selected list.
- **Duplicate Favorites List…** copies a list under a new name. **Copy Favorites List to Another Configuration…** copies it into another saved configuration. Copies start with their quick key, number tag and startup keys Off, so they never clash with the lists already there.
- **Reorder Favorites Lists…**: drag the lists, or use Up and Down. The scanner shows them in that order after export.
- **Delete Favorites List…** removes a list. The file is kept in the configuration's backups.
- **Import Favorites List File (.hpd)…** adds a list file from anywhere (another scanner's card, a backup, a friend) after the same checks as any new list. **Save Favorites List as File (.hpd)…** writes the selected list to a file.
- **Favorites List Settings…**: each list's name, monitor state, quick key, number tag, startup keys and system quick-key flags.
- **Keys & Tags…** (Ctrl+K): chapter 7.

### The list editor

**Edit Favorites List…** opens the list in its own window. The **left pane** shows the list's systems, sites and departments; the **right pane** shows the channels or talkgroups of the department selected on the left, with all their settings.

- Change a value by double-clicking it, or select it and use **Edit Selected Field…**. Dropdowns offer only the values the scanner accepts. Reserved and unsupported fields are read-only and kept exactly.
- Right-click in the left pane to **Rename System…** or **Rename Department…**, or **Edit Site…** (a trunked site's settings, including its quick key, location and range). Right-click a channel or talkgroup to edit its name, frequency or ID, or delete it.
- Quick keys and number tags of systems, departments and channels are set in **Keys & Tags** (chapter 7).
- **Heard (90 days)** and **Last Heard** show how often SDS100 Monitor logged each channel or talkgroup (chapter 11).
- Each change is one Undo step. **Save Configuration** keeps them.

#### Adding by hand

Right-click in the left pane:

- **New Conventional System…** (also on the empty area): system name, first department and first channel.
- **New Department…** on a system or department: a conventional department starts with one channel (name, frequency, modulation, tone); a talkgroup department starts with one talkgroup (name and ID).
- **Add Conventional Frequency…** on a conventional department: name, frequency, modulation and an optional tone, NAC or colour code. **Add Talkgroup…** on a talkgroup department.
- **Delete System…**, **Delete Department…** and **Delete Site…** remove them with everything in them, or select one and press **Delete**. A list can't be left empty, and a trunked system keeps at least one site.
- Select several channels or talkgroups on the right, or several systems, sites and departments on the left (Ctrl+click adds one, Shift+click a range), and press **Delete** to remove them together, as one Undo step.

Trunked systems come from RadioReference, with their sites.

#### Cut, copy and paste

Right-click, or press Ctrl+X, Ctrl+C and Ctrl+V, in either pane:

- **Left pane:** a whole **system**, or a **department** with its channels or talkgroups. A talkgroup department brings its system's sites along, so it can start that system in a list that doesn't have it yet.
- **Right pane:** the selected **channels** or **talkgroups** (Ctrl+click or Shift+click to select several). Select the department to paste into in the left pane first.

To move something to another list, cut or copy it, close the window, open the other list with **Edit Favorites List…**, select where it goes and **Paste**:

- it goes into the selected conventional system, or into the same system (same name and type) if the list has it, or in as a new system;
- a department with the same name takes the new channels or talkgroups;
- anything already there is skipped, and nothing is replaced. You see what will be added before anything changes.

Talkgroups only go into a trunked system of the same type (P25 into P25, DMR into DMR). **Cut** removes the item at once, as one Undo step; paste it once. A copy can be pasted many times.

**Paste as New Favorites List…** (left pane) makes a new list holding what you cut or copied. For example, cut *City Police* from a county list and paste it as a new list called *City Police*.

When something you paste has a quick key or number tag already used in the list you paste into, Paste lists the clashes and asks:

- **Next Free Numbers** (the default) moves only the clashing ones to free numbers;
- **Set Them Off** clears them;
- **Keep Them** leaves them used twice; Keys & Tags will show them.

#### Changing several channels at once

Select rows (Ctrl+click or Shift+click the row numbers) and choose **Change Selected…**. Pick Avoid, Attenuator, Delay or Volume Offset and a value, and confirm once. The whole change is one Undo step.

## 7. Keys & Tags

**Favorites → Keys & Tags…** (Ctrl+K) is the one place for quick keys, number tags and what the scanner scans.

### Quick keys and number tags

- A **quick key** switches scanning On and Off. Favorites Lists, systems, departments and trunked sites can have one.
- A **number tag** jumps straight to a Favorites List, system or channel (on the scanner, or with SDS100 Monitor's Go to Number Tag).

They are separate settings: Favorites List quick key 1 is not number tag 1.

**Number sets:**

| Numbers | One set for | Range |
|---|---|---|
| Favorites List quick keys and number tags | the whole scanner | 0–99 |
| System quick keys and number tags | each Favorites List | 0–99 |
| Department and site quick keys | each system | 0–99 |
| Channel and talkgroup number tags | each system | 0–999 |

A trunked site's quick key is in the same set as its system's departments: switching that key Off stops both.

### The window

- **The tree** lists every Favorites List, with its systems, their sites and departments, and their channels and talkgroups.
- **Quick key** and **Number tag** show each item's numbers.
- **Scanning** says in words whether the scanner scans it, and why not. For example: *not scanned: department key 04 is Off*, or *not scanned: Favorites List Lakeside County has Monitor Off*.
- **Sorting:** click a column heading, or pick from **Sort:** (Scanner order, Name, Quick key, Number tag, Not scanned first, Detail). Items are sorted among their own level; **Scanner order** puts everything back.

### Changing numbers and switches

- **Double-click** a number. The list shows every number with *free* or *used by …*, plus **Next free**.
- **Tick or untick Scanning** to switch that key On or Off. Everything on the same key follows. Tick **Detail** on a list to switch its Monitor.
- **Number Keys in Order…** and **Number Tags in Order…** number everything under the selected item from a start number, counting up by a step. On a trunked system, Number Keys in Order… asks whether to number its departments, its sites, or both.
- **Next Free Key**, **Next Free Tag** and **Clear** work on the selected item.
- **Tags by Department…** (select a system) gives each department's channels a block of number tags, for example the 100s for the first department and the 200s for the next.
- **Match Tags to Keys** sets each number tag to the item's quick key, so you only remember one number.

Underneath, **problems** are updated as you work: numbers used twice in one set, items that won't be scanned because a key is Off, and Favorites List keys that are On with nothing on them.

### Scan profiles

A profile is a saved set of which keys are On and which lists are monitored, for example *Home*, *Fire only* or *Storm*.

- **Save Current as Profile…** saves the switches as they stand.
- **Use** sets them from a profile; **Apply** keeps them, and Export to Scanner sends them.
- Profiles go by list and system names. Lists added after a profile was saved are left as they are, and the window names them.
- Profiles are kept on your computer, not on the scanner. **SDS100 Monitor** can apply one to the scanner while it runs.

### Spreadsheet and key card

- **Save Spreadsheet…** writes a LibreOffice Calc spreadsheet with sheets for Favorites Lists, Systems, Departments (and sites) and Channels, plus a 00–99 map of Favorites List numbers. Numbers go in yellow cells; check columns turn red when two items in one set share a number. It needs `python3-openpyxl`; without LibreOffice it is saved as .xlsx, which Calc also opens.
- **Read Spreadsheet…** brings the numbers you edited back as changes to check and Apply. Rows that no longer match, and values that aren't whole numbers, are skipped and listed. Keep the hidden Ref column, and don't add or move rows.
- **Key Card (PDF)…** makes a printable page to keep with the scanner: list keys and tags, each monitored list's system and department keys, and a directory of channel number tags.

### Apply

**Apply** shows the changes in words first, then saves list keys, tags and switches to the configuration and puts system, department and channel changes into the lists, offering to **Save Configuration**. Two Favorites Lists can't share a key or tag, so Apply refuses that.

**Export to Scanner** shows the same warnings in its preview. They don't block the export.

## 8. Scanner settings

All under **Scanner Settings**. Each window shows only the settings it covers; **Save** shows the checked changes for review, then saves them to the configuration. **Export to Scanner…** sends them.

| Menu entry | Contents |
|---|---|
| **GPS and Location Settings…** | Location source, current location and saved locations |
| **Service Types…** | Which service types are scanned |
| **Global Settings…** | Global scanner options |
| **Search Settings…** | Common search, Close Call, Limit Search, Tone-Out, band defaults, Waterfall bands and colours, broadcast screens |
| **Weather Settings…** | Weather options and SAME groups |
| **Display Settings…** | Display options and backlight |
| **Display Layouts and Colours…** | The items on each screen row, and screen colours |
| **Hardware Settings…** | Battery, owner information, clock, recording, standby |

**Inspect Scanner Settings (Read-only)…** shows every setting without changing anything.

### Firmware

**Scanner Settings → Update Scanner Firmware…** puts new firmware on the scanner the way Sentinel does: it writes the files to the card's `BCDx36HP/firmware` folder, and the scanner installs them itself the next time it starts from its own card. SDS-Manager never flashes firmware itself.

1. Connect the SDS100 in mass-storage mode. The window shows the model and main firmware version from the card, and any files already waiting.
2. Download the firmware from Uniden's support page and use **Add File…** with the `.zip`, `.bin` or `.firm` file. Zips are read without unpacking.
3. **Write to Scanner…** checks the files and shows exactly what will be written. Confirm, and the files are written and read back.
4. Eject the scanner in your file manager, then unplug the USB cable. The scanner checks each file, installs it and deletes it.

Checks before writing: the file is for exactly your model (an SDS100 never gets SDS100E or SDS200 firmware); at most one main and one sub file; a plausible size and not a saved web page; the identified SDS100 with enough free space; a second confirmation for an older main version. Firmware files already waiting in the folder are listed and removed first (you can keep them); other files there, such as the scanner's location tables, are left alone.

> [!CAUTION]
> Don't turn the scanner off while it installs firmware. Follow its on-screen prompts.

## 9. The system database

The scanner keeps its own copy of Uniden's system database (the **master database**), which it uses for Full Database scanning and location-based scanning. SDS-Manager can replace it with a newer one.

1. **Database → Update Database (Rebuild from Archive)…**: choose a Uniden master database archive (`MasterHpdb_MM_DD_YYYY.gz`). SDS-Manager rebuilds the scanner's database files from it on your computer. This takes several minutes and doesn't touch the scanner.
2. Connect the SDS100 in mass-storage mode.
3. **Database → Update Scanner's Master Database…**: pick the rebuilt version, then the card's top folder.
4. A read-only check runs first. It shows the scanner's database date and the new one, and how many state files change. It refuses an older database, a different set of states, or a rebuild that doesn't match what the card holds.
5. Confirm. SDS-Manager backs up, writes only the files that changed (`hpdb.cfg` last), checks them, and tells you where the backup is.

Your Favorites Lists, settings and every other file are not touched by a database update.

## 10. Exporting to the scanner

**File → Export to Scanner…** sends the saved configuration to the scanner.

1. Save your changes (**File → Save Configuration**).
2. Connect the SDS100 in mass-storage mode and choose **Export to Scanner…**. Choose the card's top folder.
3. If avoids on the scanner differ from the configuration, you are asked about them first (below).
4. The **preview** lists in plain words what will change (new, removed and edited lists, changed settings, keys and tags that clash or switch things off), then the file-by-file details.
5. If it says **READY**, confirm. If it says **BLOCKED**, the reason is shown and nothing has changed.
6. When it finishes, **eject the card** in your file manager and wait for it to finish before unplugging or switching the scanner on.

What the export does:

- checks that the card belongs to the identified SDS100 on USB, isn't read-only, and has room;
- makes a fresh **backup** of the card's configuration and checks it (SHA-256) before writing anything;
- writes only the files that changed, staging and checking each one, and **restores every changed file automatically** if anything fails part way.

> [!CAUTION]
> Unplugging or switching off before the card has finished ejecting can leave a file empty on the card. If that happens, run the export again.

### Avoids made on the scanner

A permanent avoid set on the SDS100 itself, or from SDS100 Monitor, is stored on the scanner. A configuration saved earlier still has the old setting, so exporting it would undo the avoid.

Before an export, SDS-Manager compares the avoids of systems, sites, departments, channels and talkgroups on the scanner with the configuration's. Any that differ are listed with tick boxes:

- **Keep Ticked and Continue** saves the ticked avoids into the configuration, then goes on with the export;
- **Continue Without** exports the configuration as it is; **Cancel** stops.

Ticked to begin with: those changed on the scanner since it last matched the configuration. Avoids you changed in SDS-Manager aren't listed; your change is exported. Until a configuration has been read from or exported to the scanner once, SDS-Manager can't tell which side changed, and ticks the ones the scanner has avoided.

### Is the scanner up to date?

SDS-Manager remembers when the scanner last matched each configuration: after **Import from Scanner…** and after each successful export. If you save changes and don't export them, the status bar says **— not on scanner yet**, and SDS100 Monitor shows a warning.

## 11. Working with SDS100 Monitor

**SDS100 Monitor** (github.com/jmlynchjr/SDS-MONITOR) controls the scanner live over USB. With both installed:

### From the Monitor

- **Edit in Manager…**: right-click a reception in the Monitor (or use **Tools → Edit Current Channel in Manager…**). SDS-Manager opens the list editor on that talkgroup or channel. If it is in several places you choose one; with no configuration open you are offered one.
- **Add to Favorites List in Manager…**: right-click a reception. SDS-Manager asks which department to put it in (the same department and system come first, marked ★), and for a name, and for channels the modulation and an optional tone. It is one Undo step; **Save Configuration** keeps it. This works for Close Call, search and Discovery hits, and for talkgroups heard through ID Search.

### In SDS-Manager

- **Heard (90 days)** and **Last Heard**, the last two columns of the list editor, show how many times the Monitor logged each channel or talkgroup in the last 90 days, and when. Talkgroups are matched by system name and talkgroup ID, channels by frequency. Sort by them to find what's never on the air.
- **Add Unit Names from SDS100 Monitor…** (right-click a system in the list editor) puts the unit names you confirmed in the Monitor (not those marked Guess) into every trunked system in the list where the Monitor heard that unit. A unit already there with another name is renamed. It is one Undo step; Save Configuration and Export send it.
- **Tools → Name Unnamed Talkgroups…** suggests names for talkgroups that have none, from the database and from what the Monitor recorded. Tick, check and apply, as one Undo step.

> [!NOTE]
> Uniden's file specification doesn't fully say how the scanner stores unit IDs, so SDS-Manager copies a unit ID row the scanner wrote itself. If a system has none yet, add one unit ID on the SDS100 (in that system's Edit Unit IDs menu), import the configuration from the scanner again, and run **Add Unit Names** again.

### Shared with the Monitor

Whenever the configuration is saved or a profile changes, SDS-Manager writes `~/.local/share/sds100-database-favorites-manager/monitor-keys.json`. From it the Monitor:

- names its quick key buttons (systems, departments, and sites marked "(site)");
- lists tagged channels in Go to Number Tag;
- applies scan profiles to the scanner;
- warns when the scanner is out of date.

SDS-Manager only reads the Monitor's files in `~/SDS100Monitor`, and the two programs talk only on this computer.

## 12. Finding things

**Tools → Find Everywhere…** (Ctrl+F) searches the active master database and the Favorites Lists of the open configuration at once. Enter:

- a name (system, department, site, channel, talkgroup or list);
- a frequency in MHz: `154.9` finds everything from 154.900 to 154.999; `460.025` finds exactly that frequency;
- or a talkgroup ID.

Results show the type, value and the system › department they belong to. **Copy Results** copies the table. Searching never changes anything. Only the first 500 matches are shown, so narrow a very broad search.

## 13. Settings and themes

### Settings

**Tools → Settings…** (Ctrl+,):

- **Scanner connection:** where removable media appear, automatic detection, and offering the detected card in folder prompts.
- **Backups:** how many to keep when you clean up, and a size warning.
- **Confirmations:** low-risk prompts only. **Writes to the scanner are always confirmed.**
- **Database:** an optional startup check for a newer database (it only reports), and how many database versions to keep.
- **Appearance:** theme, accent colour, text size and an exact font size.
- **Log detail.**

**Tools → Preferences** chooses the columns shown in Database Contents and the Favorites Lists.

### Themes

**Tools → Theme** offers the same themes as SDS100 Monitor, applied at once:

- **Mode:** *System (follow KDE)*, *Dark*, *Light*, or *Night (red)*, dim red only to keep your night vision.
- **Accent:** Blue, Red, Green, Amber, Purple or Teal.
- **Text size:** Small, Normal, Large or Extra large.

## 14. Backups, storage and recovery

### Where things are kept

| What | Where |
|---|---|
| Scanner configurations | SDS-Manager's library (**File → Storage → Open Managed Data Folder…** shows it) |
| Rebuilt databases | `~/.local/share/SDS100DatabaseFavoritesManager/database/` |
| Firmware files and write receipts | `~/.local/share/SDS100DatabaseFavoritesManager/firmware/` |
| Scanner backups | `~/.local/share/sds100-database-favorites-manager/scanner-backups/<date and time>/` |
| Scan profiles and export state | beside the configuration library |

Each backup holds `BCDx36HP/` (the scanner's files as they were), `manifest.json` (every file with its SHA-256), `EXPORT_RECOVERY.txt` (which files the export changed) and `EXPORT_RESULT.json` (what was written). Backups are on your computer, not on the card.

**File → Backup and Restore → Back Up Scanner Configuration (Read-only)…** (or **Back Up Scanner Now…** on the Scanner panel) makes a backup without exporting. **Clean Up Old Backups…** on the Scanner panel, and cleaning up old database versions, are always manual and show exactly what will be deleted first; the newest backups, the current database and the one on your scanner are never offered.

### If something goes wrong

**SDS-Manager reports a failed write.** It restores every changed file from the backup by itself. If it says *DO NOT DISCONNECT*, leave the scanner connected and follow the message, which names the backup folder and the files to restore.

**The scanner misbehaves, or a list is empty after an export.**

1. Switch the scanner off. Connect it in mass-storage mode (or put the card in a card reader).
2. **File → Backup and Restore → Restore from Backup…** and choose the backup taken before that export. Follow the preview.
3. By hand instead: open the backup folder, read `EXPORT_RECOVERY.txt`, and copy each listed file from the backup's `BCDx36HP` folder back to the same place on the card. Delete any file marked as ADDED.
4. Eject the card, then switch the scanner on.

**A list or the database looks empty right after writing.** The card was almost always unplugged or switched off before it finished ejecting. Export again, wait for the eject to finish, then switch on.

**Export says BLOCKED.** Read the reason. Typical causes: the card isn't the recognised SDS100 on USB, it is read-only or too full, or a file on the card changed since the configuration was imported (import a fresh copy with **Import from Scanner…**).

**After a firmware update the scanner doesn't start or shows an error.** The scanner checks firmware before installing it and refuses a damaged or wrong file. Switch it off and on. If it keeps trying, connect it in mass-storage mode, delete everything in `BCDx36HP/firmware`, eject and start again.

**Last resort.** Copy the `BCDx36HP` folder from any backup over the card's `BCDx36HP` folder, or restore with Sentinel's own backup.

**Help → Copy Diagnostic Information** copies the version and system details (no scanner data) for a problem report.

## 15. Limits and reporting problems

### What SDS-Manager will and won't do

- It **will** replace the master database, add and remove Favorites Lists, edit existing lists, and change the checked scanner settings.
- It **will** place checked firmware files for the scanner to install. It never flashes firmware itself.
- It **won't** write anything it can't check.
- **Not yet supported** (waiting for real samples): new lists for Motorola, EDACS and LTR systems; IFX frequencies; editing avoid-frequency lists; adding a rectangle department to an existing list.

### Reporting problems

Report problems on the project's GitHub **Issues** page, with the message shown and **Help → Copy Diagnostic Information**.

If you use a system type that isn't supported yet, build the same list in Sentinel and send the `f_NNNNNN.hpd` and `f_list.cfg` it writes. Real Sentinel-written files are how each new type is checked.

## Appendix: menus

| Menu | Item |
|---|---|
| **File** | New Scanner Configuration…, Import from Scanner…, Open Scanner Configuration…, Save Configuration (Ctrl+S), Save Configuration As…, Export to Scanner…, Exit |
| File → Manage Configurations | Rename, Delete and Validate Scanner Configuration… |
| File → Backup and Restore | Scanner Export Preflight (Read-only)…, Back Up Scanner Configuration (Read-only)…, Restore from Backup… |
| File → Storage | Import Existing Database into Managed Storage…, Open Managed Data Folder… |
| **Edit** | Undo (Ctrl+Z), Redo (Ctrl+Y), Undo All Changes… |
| **Favorites** | New Favorites List… (Ctrl+N), Edit Favorites List… (Ctrl+E), Duplicate…, Copy to Another Configuration…, Reorder…, Delete…, Import Favorites List File (.hpd)…, Save Favorites List as File (.hpd)…, Favorites List Settings…, Keys & Tags… (Ctrl+K) |
| Favorites → Advanced | Favorites List Relationships (Read-only)…, Inspect Native .hpd (Read-only)… |
| **Database** | Update Database (Rebuild from Archive)…, Update Scanner's Master Database… |
| Database → Advanced | Validate Master HPDB…, Validate Master HPDB .gz…, Export One State File…, Rebuild Full Database to a Folder… |
| **Scanner Settings** | Inspect Scanner Settings (Read-only)…, GPS and Location…, Service Types…, Global…, Search…, Weather…, Display…, Display Layouts and Colours…, Hardware…, Update Scanner Firmware… |
| **Tools** | Settings… (Ctrl+,), Find Everywhere… (Ctrl+F), Name Unnamed Talkgroups…, Search Frequency in RadioReference…, RadioReference Account…, Theme, Preferences, Advanced → Diagnostic Export Preview (Read-only)… |
| **Help** | User Guide (F1), Recovery and Troubleshooting, What's New (Change Log), Check for Updates…, Open Scanner Backups Folder, Copy Diagnostic Information, Open Log Folder, License, About… |

## Appendix: Running on macOS

This fork ([cinsu/SDS-Manager-macOS](https://github.com/cinsu/SDS-Manager-macOS), `macos` branch) runs SDS-Manager on a Mac. The program is the same; installing, a few paths and how it talks to the scanner's card differ. Everything else in this manual applies as written.

> [!NOTE]
> The Mac version has been tested on an Apple Silicon Mac with an **SDS150**. Report Mac problems on the fork's GitHub page, not to the original author.

### What you need

- A Mac with **Homebrew** (brew.sh) and **git** (macOS offers to install git the first time you type `git`).
- A **RadioReference Premium** account. If you run from source instead of the release download, also your own RadioReference **application key** (see below).

On a Mac, `~` means your home folder, for example `/Users/yourname`.

### Installing

**From a release (recommended).** Download the latest `SDS-Manager-macOS-….zip` from the fork's **Releases** page. It includes the fork's RadioReference application key. Unzip it, move the **SDS-Manager** folder to your home folder, then in Terminal run `cd ~/SDS-Manager && bash setup-mac.sh`. To update, download the newer release and replace the folder; your configurations and backups are kept elsewhere and stay.

**From source with git,** in Terminal:

1. `cd ~`
2. `git clone -b macos https://github.com/cinsu/SDS-Manager-macOS.git SDS-Manager`
3. `cd ~/SDS-Manager`
4. `./setup-mac.sh`

`setup-mac.sh` installs Python 3.12 with Homebrew and puts the program's own Python packages (PyQt6 and keyring) in a private folder, `~/SDS-Manager/.venv-mac`.

- **Start:** `~/SDS-Manager/launch-mac.sh`. Terminal stays open while the program runs; errors appear there.
- **Update:** `cd ~/SDS-Manager && git pull`, in place of **Help → Check for Updates…**, which installs Linux packages.
- **Tests:** `./run-tests-mac.sh` (it makes a small temporary RAM disk for the tests that need a second drive).
- **Remove:** delete the `~/SDS-Manager` folder. Your data stays.

### RadioReference application key

The fork's release download includes a RadioReference application key, so with it you only sign in with your own RadioReference username and password (Premium required).

> [!NOTE]
> The key is never in the source code on GitHub, only in release downloads, the same way the original author's Linux packages work.

**If you run from source,** you need your own key. Apply at radioreference.com/account/api/apply (Premium required). Then enter it, with your RadioReference username and password, under **Advanced** in **Tools → RadioReference Account…**. On a Mac the password and key are kept in the **Keychain**. Never put a key in a file you commit to git.

### Connecting the scanner

Choose **Mass Storage** on the scanner when you connect it. Its card appears under `/Volumes`, as `/Volumes/NO NAME` if the card has no label. The default **Folder where removable media appear** is `/Volumes`.

The Mac version checks the scanner's identity with `mount` and `ioreg` instead of Linux's `/proc` and `/sys`. It accepts the SDS100 (USB `1965:001c`) and the SDS150 (USB `1965:001a`). To see what it finds, read-only:

`.venv-mac/bin/python -c "import scanner_identity as i; print(i.inspect_scanner_identity('/Volumes/NO NAME'))"`

### Before the first write: protect the card

Do these once, with the scanner connected in Mass Storage mode. Replace `NO NAME` with your card's name.

1. **Back up the whole card** to a dated folder:
   `ditto "/Volumes/NO NAME" ~/scanner-card-backup-$(date +%Y-%m-%d)`
2. **Check the copy:**
   `diff -rq -x '._*' -x '.Spotlight-V100' -x '.fseventsd' -x '.Trashes' -x '.DS_Store' "/Volumes/NO NAME" ~/scanner-card-backup-$(date +%Y-%m-%d) && echo "BACKUP MATCHES"`
3. **Turn off Spotlight on the card**, so macOS stops indexing it:
   `sudo mdutil -i off "/Volumes/NO NAME"`

`ditto` reports *Operation not permitted* for `.Spotlight-V100`; that is Spotlight's own folder and isn't scanner data.

### How writes are protected on a Mac

All of chapter 10's protections apply. In addition:

- **Full flush.** On a Mac a normal "save to disk" can finish while data is still in the card's cache. Every save the program makes uses macOS's full flush (`F_FULLFSYNC`), which writes it to the card itself.
- **macOS clutter is cleared.** macOS stores its own file information on FAT cards as hidden `._` files next to each file, and Finder leaves `.DS_Store` files. The scanner doesn't expect them. Before and after every export, database update, firmware update and restore, the program removes them from the card (only files that really are macOS's, checked by their contents). To tidy the card by hand:
  `.venv-mac/bin/python -c "import mac_platform as m; print(m.clean_card('/Volumes/NO NAME'))"`
- **Always eject before unplugging**, with Finder's eject button or `diskutil eject "/Volumes/NO NAME"`. Ejecting makes sure everything is on the card.

### Status on the SDS150

The original program was written for and tested on the SDS100. This fork has been tested on an SDS150 and works. As with any scanner, back up the card before big changes such as a database or firmware update.

### Settings and files

Configurations, databases and the program's own scanner backups are in `~/.local/share/sds100-database-favorites-manager`, and settings in `~/.config`, the same places as on Linux (chapter 14).

### Working with SDS100 Monitor

The macOS fork of the Monitor is at github.com/cinsu/SDS-MONITOR-macOS. Installed as `~/SDS-MONITOR` and `~/SDS-Manager` side by side, the Monitor's **Edit in Manager…** finds SDS-Manager's `launch-mac.sh`.
