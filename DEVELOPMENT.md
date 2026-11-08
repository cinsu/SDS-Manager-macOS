# Development notes

## Principles
- Real SDS100 files win over the Uniden specification ("SDS Series File Specification V2.00") wherever they differ. Layouts are verified against files written by Sentinel or the scanner and kept in `test_fixtures/`.
- Never write what is not understood. Every export path re-derives the proposed file from the original plus validated edits and requires byte equality; anything else is refused.
- All scanner writes go through one controlled batch: verified backup, SHA-256 staging, rollback of every changed file on failure, `os.sync()` at the end.

## Modules by role
| Role | Modules |
|---|---|
| Application and UI | `database_favorites_manager.py` (main window, menus, dialogs), `database_workspace.py` (database browser, selection dialogs, draft), `favorites_*.py` |
| Database rebuild | `master_hpdb_validator.py`, `hpdb_state_reconstruction.py`, `hpdb_bulk_reconstruction.py`, `hpdb_cfg_generator.py`, `managed_storage.py` |
| Scanner master database update | `scanner_database_update.py` (checks, plan, write) |
| Favorites lists | `new_favorites_list.py` (build new lists from database rows), `scanner_list_sync.py` (new/deleted list guards, f_list.cfg), `flist_settings.py` (per-list settings), `scanner_favorites_expanded.py` (edits to existing lists), `native_favorites_*.py` |
| Scanner settings | `profile_schema.py` (spec-driven fields and validation), `scanner_profile_export.py` (profile.cfg guard), `scanner_global_settings.py`, `location_settings.py`, `quick_keys_settings.py` |
| Scanner I/O | `scanner_preflight.py`, `scanner_identity.py`, `scanner_backup.py`, `scanner_first_write.py` (batch export), `scanner_restore.py`, `scanner_export_preview.py`, `scanner_configurations.py` (local configuration library) |
| Audits and rehearsals (diagnostic, read-only) | `scanner_native_*_audit.py`, `scanner_native_*probe.py`, `scanner_*_rehearsal.py` |

## Key file facts
- Files are tab-separated, CRLF, cp1252. Favorites list: `favorites_lists/f_NNNNNN.hpd` plus a row in `f_list.cfg` (keyword + 116 fields + one trailing empty field). Settings: `profile.cfg`. Database: `HPDB/s_NNNNNN.hpd` (one per state) and `HPDB/hpdb.cfg`.
- Trunked list order: Trunk, DQKs_Status, Site, BandPlan, Rectangle(s), T-Freq(s), T-Group, Rectangle(s), TGID(s).
- `profile_schema.py`: `SCHEMA[kind]` holds fixed-record fields (choice, int, text, freq, color, mhz, fips, fixed); display layouts and colours use variable-length records through `fields_for`. Reserved fields are never editable.

## Testing
- `python3 -m unittest discover -s .`. Mock-scanner tests subclass `SyncBase` in `test_list_sync_export.py`.
- GUI code cannot be run in the headless test environment; new GUI work is tested by hand on Kubuntu.

## Not yet verified on hardware
Motorola, EDACS, LTR and MotoTrbo new lists; rectangle departments; IFX (locked); avoid-frequency lists (locked). Real Sentinel-written samples are needed for each.
