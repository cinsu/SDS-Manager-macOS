#!/usr/bin/env bash
set -euo pipefail
SOURCE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VERSION="$(cd "$SOURCE" && python3 -c 'import edition; print(edition.APP_VERSION)')"
[[ -n "$VERSION" ]] || { echo "Cannot read the version from edition.py" >&2; exit 1; }
DEST="$HOME/SDS100DatabaseFavoritesManager-$VERSION"
DESKTOP="$HOME/.local/share/applications/sds100-database-favorites-$VERSION.desktop"
mkdir -p "$DEST" "$HOME/.local/share/applications"
cp -a "$SOURCE"/. "$DEST"/
chmod +x "$DEST/launch.sh" "$DEST/uninstall.sh" "$DEST/test-launch.sh"
cat > "$DESKTOP" <<DESKTOP_ENTRY
[Desktop Entry]
Type=Application
Name=SDS-Manager v$VERSION
Exec=$DEST/launch.sh
Terminal=false
Icon=$DEST/assets/sds100-manager.svg
Categories=Utility;
DESKTOP_ENTRY
printf '\033[34mInstalled v%s at %s\033[0m\n' "$VERSION" "$DEST"
echo "Older versions can be listed and removed with: python3 cleanup_old_installs.py"
