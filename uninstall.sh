#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VERSION="$(grep -o -m1 'Manager v[0-9.]*[a-z]*' "$HERE/database_favorites_manager.py" | head -1 | sed 's/Manager v//')"
TARGET="$HOME/SDS100DatabaseFavoritesManager-$VERSION"
DESKTOP="$HOME/.local/share/applications/sds100-database-favorites-$VERSION.desktop"
echo "Uninstall v$VERSION application files only. Data, configurations, and backups are retained."
if [[ -n "$VERSION" && "$HERE" == "$TARGET" && -f "$TARGET/database_favorites_manager.py" ]]; then
  read -r -p 'Type REMOVE to uninstall this version: ' ANSWER
  [[ "$ANSWER" == REMOVE ]] || exit 0
  [[ ! -f "$DESKTOP" ]] || rm -- "$DESKTOP"
  cd "$HOME"
  rm -rf -- "$TARGET"
  echo "Uninstalled v$VERSION"
else
  echo "Run this script from the installed v$VERSION directory, or use cleanup_old_installs.py for older versions."
fi
