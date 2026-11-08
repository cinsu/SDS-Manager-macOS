# v0.0.7j — One new read-only Kubuntu test

1. Extract v0.0.7j into a NEW folder and launch `test-launch.sh`. Confirm title **v0.0.7j**.
2. Connect the SDS100 in **Mass Storage** mode (as in prior scanner tests).
3. Choose **File → Scanner Export Preflight (Read-only)…** and select the same SDS100 mass-storage folder you used previously.
4. In the preflight report, find **SCANNER USB IDENTITY EVIDENCE — READ ONLY**. Report the values for **Mounted USB device association**, **USB vendor ID**, **USB product ID**, **USB manufacturer string**, and **USB product string**, or the **Evidence limitation** line if those fields are absent. No need to share a USB serial number.

**Expected:** USB mount association should be FOUND when Linux exposes sysfs USB descriptors. **SDS100 model identity: NOT YET VERIFIED** and **Export authorization: BLOCKED** are correct at this phase. Do not export or modify scanner files.

**Remaining milestones after this test:**
- v0.0.7j: confirm USB evidence and finish model verification using trusted model-specific identifiers (if evidence permits).
- v0.0.7k: safe staging, rollback and storage validation.
- v0.0.7l: final native export safety and compatibility validation; automatic preview and explicit confirmation integrated into Export to Scanner.
- v0.0.7m: first limited SDS100 write, ONLY after every gate passes.
