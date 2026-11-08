# SDS-Manager

*Formerly SDS100 Database & Favorites Manager.*

A native Kubuntu (PyQt6) manager for the Uniden SDS100 scanner: update the system database, build and edit Favorites Lists, and change scanner settings, with every scanner write validated, backed up first and reversible. A Sentinel alternative for Linux.

**New here? Read the [user manual](docs/user-manual.md)** (also as a PDF with each [release](https://github.com/jmlynchjr/SDS-Manager/releases)). The shorter [USER_GUIDE.md](USER_GUIDE.md) is the guide shown in the program (Help → User Guide).

Created by J. Lynch, with AI assistance in the build. Free software under the GNU GPL v3 or later (see `LICENSE`, `NOTICE.md`).

## Run

- Requires `python3` and `python3-pyqt6` (Kubuntu: `sudo apt install python3-pyqt6`).
- Try without installing: `./launch.sh` (or `./test-launch.sh` to also capture logs).
- Install for the current user: `./install.sh` (adds an application-menu entry; version taken from the application). Remove with `./uninstall.sh` from the installed folder, or list and remove older versions with `python3 cleanup_old_installs.py`.
- Application data lives outside the program folder, so installing or removing a version never touches your configurations, databases or backups.

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
