#!/usr/bin/env bash
# Runs SDS-Manager's tests on macOS. Extra arguments go to unittest (for example -v).
#  - Uses the real path of the temporary folder (/var is a link to /private/var on a Mac).
#  - Makes a small RAM disk for the tests that need a second file system, and removes it afterwards.
set -euo pipefail
cd "$(dirname "$0")"
export TMPDIR="$(cd "${TMPDIR:-/tmp}" && pwd -P)/"
DEV=$(hdiutil attach -nomount ram://262144 | awk '{print $1}')        # 128 MB
cleanup() { hdiutil detach "$DEV" >/dev/null 2>&1 || true; }
trap cleanup EXIT
diskutil erasevolume "Case-sensitive HFS+" SDSTestRAM "$DEV" >/dev/null
export SDS_TEST_ALT_FS="$(diskutil info "$DEV" | awk -F': *' '/Mount Point/{print $2; exit}')"
echo "Second file system for tests: $SDS_TEST_ALT_FS"
# Two test files swap PyQt6 for a stand-in and must run in their own process when the real PyQt6 is
# installed; otherwise windows loaded earlier with the real Qt leak into them.
SEPARATE="test_ui_extras_stub test_favorites_clipboard"
MAIN=$(ls test_*.py | sed 's/\.py$//' | grep -vxF -e test_ui_extras_stub -e test_favorites_clipboard)
status=0
echo "== main tests"; .venv-mac/bin/python -m unittest $MAIN "$@" || status=1
for m in $SEPARATE; do
  echo "== $m"; .venv-mac/bin/python -m unittest "$m" "$@" || status=1
done
[ $status -eq 0 ] && echo "ALL TESTS PASSED" || echo "SOME TESTS FAILED (see above)"
exit $status
