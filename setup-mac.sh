#!/usr/bin/env bash
# One-time macOS setup: Homebrew Python 3.12 + a private environment in .venv-mac
set -euo pipefail
cd "$(dirname "$0")"
command -v brew >/dev/null || { echo "Install Homebrew first: https://brew.sh"; exit 1; }
brew install python@3.12 ffmpeg
"$(brew --prefix python@3.12)/bin/python3.12" -m venv .venv-mac
.venv-mac/bin/python -m pip install --upgrade pip
.venv-mac/bin/python -m pip install PyQt6 keyring
echo "Done. Start it with: ./launch-mac.sh"
