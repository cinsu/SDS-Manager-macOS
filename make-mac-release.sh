#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# macOS fork of SDS-Manager: builds a release zip that includes the RadioReference application key,
# without the key ever going into git. The key is read from rr_app_key in this folder (ignored by git).
#
#   ./make-mac-release.sh            build the zip in ~/SDS-Manager-releases and check it
#   ./make-mac-release.sh publish    build it, then create the GitHub release and upload the zip
set -euo pipefail
cd "$(dirname "$0")"

KEY_FILE="rr_app_key"
MAC_NUMBER="${MAC_NUMBER:-1}"            # the .1 in 0.1.27-macos.1; set MAC_NUMBER=2 for a Mac-only fix

# --- safety checks ---------------------------------------------------------------------------------
[ -f "$KEY_FILE" ] || { echo "No $KEY_FILE here. Put the key in it first."; exit 1; }
if git ls-files --error-unmatch "$KEY_FILE" >/dev/null 2>&1; then
    echo "STOP: $KEY_FILE is tracked by git. It must never be committed."; exit 1
fi
git check-ignore -q "$KEY_FILE" || { echo "STOP: $KEY_FILE is not ignored by git."; exit 1; }
[ "$(git rev-parse --abbrev-ref HEAD)" = "macos" ] || { echo "Switch to the macos branch first."; exit 1; }
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "Commit (and push) your changes first, so the release matches GitHub."; exit 1
fi
KEY=$(tr -d ' \t\r\n' < "$KEY_FILE")
[[ "$KEY" =~ ^[A-Za-z0-9_.:-]{4,128}$ ]] || { echo "$KEY_FILE doesn't look like a key."; exit 1; }

BASE=$(sed -n 's/^BASE_VERSION = "\(.*\)"/\1/p' edition.py)
[ -n "$BASE" ] || { echo "Couldn't read BASE_VERSION from edition.py"; exit 1; }
TAG="v${BASE}-macos.${MAC_NUMBER}"
NAME="SDS-Manager-macOS-${BASE}-macos.${MAC_NUMBER}"
OUT="$HOME/SDS-Manager-releases"         # outside the repo, so the zip can never be committed
ZIP="$OUT/${NAME}.zip"

# --- build -----------------------------------------------------------------------------------------
mkdir -p "$OUT"
rm -f "$ZIP"
git archive --format=zip --prefix=SDS-Manager/ -o "$ZIP" HEAD
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/SDS-Manager"
printf '%s\n' "$KEY" > "$STAGE/SDS-Manager/rr_app_key"
chmod 644 "$STAGE/SDS-Manager/rr_app_key"
(cd "$STAGE" && zip -q -X "$ZIP" SDS-Manager/rr_app_key)

# --- check -----------------------------------------------------------------------------------------
LIST=$(unzip -Z1 "$ZIP")
for must in SDS-Manager/rr_app_key SDS-Manager/setup-mac.sh SDS-Manager/launch-mac.sh SDS-Manager/mac_platform.py; do
    grep -qx "$must" <<< "$LIST" || { echo "Zip is missing $must"; exit 1; }
done
if grep -qE '(^|/)\.venv-mac/|(^|/)\.git/' <<< "$LIST"; then echo "Zip contains .venv-mac or .git"; exit 1; fi
echo "Built $ZIP ($(du -h "$ZIP" | cut -f1)), tag $TAG. Key included; not in git."

[ "${1:-}" = "publish" ] || { echo "Check it, then run: ./make-mac-release.sh publish"; exit 0; }

# --- publish ---------------------------------------------------------------------------------------
NOTES=$(mktemp)
cat > "$NOTES" <<EOF
## SDS-Manager ${BASE} for macOS

A macOS port of [jmlynchjr/SDS-Manager](https://github.com/jmlynchjr/SDS-Manager) ${BASE}. Tested on an Apple Silicon Mac with a Uniden **SDS150**.

### Download
Download **${NAME}.zip** below. It includes this fork's RadioReference application key, so you only sign in with your own RadioReference Premium account. (The "Source code" downloads GitHub adds automatically don't include the key.)

### Install
1. Install [Homebrew](https://brew.sh) if you don't have it.
2. Unzip the download and move the **SDS-Manager** folder to your home folder.
3. In Terminal: \`cd ~/SDS-Manager && bash setup-mac.sh\`
4. Start it with \`~/SDS-Manager/launch-mac.sh\`

**Before the first write to your scanner,** read the user manual's appendix *Running on macOS*: back up the whole SD card, turn off Spotlight on it, and always eject before unplugging.

### Status on the SDS150
Detection, the export preview and Export to Scanner of an edited Favorites List are tested and work. Database updates, firmware updates and restores have not yet been tested on an SDS150.
EOF
gh release create "$TAG" "$ZIP" --repo cinsu/SDS-Manager-macOS --target macos \
    --title "SDS-Manager ${BASE} for macOS" --notes-file "$NOTES"
rm -f "$NOTES"
echo "Published $TAG."
