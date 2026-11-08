# v0.0.7i — Independent offline configuration Save As

**One NEW GUI test (no repetition of previously passed Save/reopen tests):**

1. Extract this release into a NEW folder and launch `test-launch.sh`. Confirm title **v0.0.7i**.
2. File → Open Scanner Configuration… → choose a LOCAL test configuration (for example **test of file system**).
3. File → **Save Configuration As…** → enter **Independent Test Copy** and confirm. The app should create and open a new local configuration. Do **not** connect/export to scanner for this test.
4. File → Open Scanner Configuration… → verify **both** the original configuration and **Independent Test Copy** appear as independent choices. Do not delete either one.

**Report only:** Did Save As succeed, and are both configurations present? If not, send the displayed error.

The underlying regression suite additionally verifies Save As with an **unsaved frequency edit**, independent manifest checksums, byte-identical opaque CFG copies, real uploaded native HPD edit preservation, duplicate-name blocking, symlink blocking, and cleanup after a failed save.

**Scanner export is disabled.** The standalone read-only preview is a development diagnostic; production Export to Scanner will automatically preview and ask **Cancel / Proceed with Export** in one operation.

**Remaining planned milestones after v0.0.7i passes:**
- **v0.0.7j:** Scanner identity verification.
- **v0.0.7k:** Safe staging, rollback and storage validation.
- **v0.0.7l:** Final export safety and native compatibility validation.
- **v0.0.7m:** First limited verified SDS100 write, only if safety gates pass.
