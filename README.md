# SDS-Manager

> **This is a macOS fork** of [jmlynchjr/SDS-Manager](https://github.com/jmlynchjr/SDS-Manager), maintained by [cinsu](https://github.com/cinsu). The macOS changes are on the `macos` branch. Tested on an Apple Silicon Mac with an **SDS150**. Please report Mac problems here, not to the original author. See [Running on macOS](#running-on-macos).

*Formerly SDS100 Database & Favorites Manager.*

A native Kubuntu (PyQt6) manager for the Uniden SDS100 scanner: update the system database, build and edit Favorites Lists, and change scanner settings, with every scanner write validated, backed up first and reversible. A Sentinel alternative for Linux.

**New here? Read the [user manual](docs/user-manual.md)** (also as a PDF with each [release](https://github.com/jmlynchjr/SDS-Manager/releases)). The shorter [USER_GUIDE.md](USER_GUIDE.md) is the guide shown in the program (Help → User Guide).

Created by J. Lynch, with AI assistance in the build. Free software under the GNU GPL v3 or later (see `LICENSE`, `NOTICE.md`).

## Run

- Requires `python3` and `python3-pyqt6` (Kubuntu: `sudo apt install python3-pyqt6`).
- Try without installing: `./launch.sh` (or `./test-launch.sh` to also capture logs).
- Install for the current user: `./install.sh` (adds an application-menu entry; version taken from the application). Remove with `./uninstall.sh` from the installed folder, or list and remove older versions with `python3 cleanup_old_installs.py`.
- Application data lives outside the program folder, so installing or removing a version never touches your configurations, databases or backups.

## Running on macOS

This fork adds macOS support. Nothing changes for Linux users. The full Mac guide, including safety steps for the scanner's SD card, is the appendix *Running on macOS* in the [user manual](docs/user-manual.md).

**Requirements:** a Mac with [Homebrew](https://brew.sh) and git, and a RadioReference Premium account.

**RadioReference application key:** a key for the Mac version has been applied for. Once RadioReference approves it, a ready-to-run Mac release that includes the key will be published on the [Releases](https://github.com/cinsu/SDS-Manager-macOS/releases) page. Until then, running from source needs your own key (see the manual's appendix), entered under Advanced in Tools → RadioReference Account….

**Set up (one time):**

```bash
cd ~
git clone -b macos https://github.com/cinsu/SDS-Manager-macOS.git SDS-Manager
cd ~/SDS-Manager
./setup-mac.sh
```

**Start:** `~/SDS-Manager/launch-mac.sh`. **Update:** `cd ~/SDS-Manager && git pull`. **Tests:** `./run-tests-mac.sh`

**Before the first write to your scanner:** back up the whole SD card, and always eject it properly before unplugging. See the manual's appendix.

**What's different on macOS:**

- **Scanner detection and write safety** use macOS's own tools (`mount`, `ioreg`) in place of Linux's `/proc` and `/sys`. The SDS150 (USB `1965:001a`) is accepted alongside the SDS100.
- **Every save to the card is fully flushed** (macOS `F_FULLFSYNC`), and macOS's hidden `._` and `.DS_Store` files are cleared from the card before and after each write.
- **Your RadioReference password and key** are kept in the macOS Keychain.
- **Help → Check for Updates** installs Linux packages and doesn't work on a Mac. Use `git pull`.

**Status on the SDS150:** detection, preview and **Export to Scanner** of an edited Favorites List are tested and work. Database updates, firmware updates and restores have not been tested on an SDS150 yet.

## RadioReference

Database contents and list building come from RadioReference.com; each user signs in with their own RadioReference Premium account (Tools → RadioReference Account…). The password is kept in the desktop keyring (KDE Wallet / GNOME Keyring), never in a file.

The program's RadioReference app key is not in this source. The .deb packages on the [Releases](https://github.com/jmlynchjr/SDS-Manager/releases) page include it. If you build from source, enter your own key under Advanced in Tools → RadioReference Account….

## Works with SDS100 Monitor

[SDS100 Monitor](https://github.com/jmlynchjr/SDS-MONITOR) controls the scanner live. With both installed, the Monitor can open what you hear in SDS-Manager (Edit in Manager, Add to Favorites List in Manager), shows SDS-Manager's quick key names, number tags and scan profiles, and warns when the scanner is out of date; SDS-Manager shows how often the Monitor heard each channel and can put the Monitor's unit names on the scanner.

## What is in the folder

| Path | Contents |
|---|---|
| `docs/user-manual.md` | The user manual |
| `USER_GUIDE.md` | The in-program guide: how to use it, safety model, recovery |
| `CHANGELOG.md` | What changed in each version |
| `DEVELOPMENT.md` | Architecture and how to test, for contributors |
| `docs/test-procedures/` | Hardware test steps written for earlier versions |
| `docs/release-notes/` | Per-version notes |
| `test_*.py`, `test_fixtures/` | Automated tests and real SDS100 sample files |
| `*.py` | The application (see DEVELOPMENT.md) |

## Tests

`python3 -m unittest discover -s .` — about 585 tests. One module (`test_site_settings_regression`) needs PyQt6 and errors where it is not installed; everything else is pure Python.
