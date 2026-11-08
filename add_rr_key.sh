#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
# Adds SDS-Manager's RadioReference application key to a package, on your own computer, so the key
# never goes into the source code. The key file holds just the key (one line).
#
#   bash add_rr_key.sh sds-manager_0.1.4_all.deb ~/rr_app_key.txt
#
# The package is rebuilt in place, with the key as /opt/sds-manager/rr_app_key (readable by all users of
# the computer, like the program). Install it as usual afterwards: sudo apt install ./<package>.deb
set -euo pipefail
if [ $# -ne 2 ]; then
    echo "Usage: bash add_rr_key.sh <package.deb> <key file>" >&2
    exit 2
fi
deb=$(realpath "$1")
keyfile=$2
[ -f "$deb" ] || { echo "No package at $1" >&2; exit 1; }
[ -f "$keyfile" ] || { echo "No key file at $keyfile" >&2; exit 1; }
key=$(tr -d ' \t\r\n' < "$keyfile")
if ! [[ "$key" =~ ^[A-Za-z0-9_.:-]{4,128}$ ]]; then
    echo "The key file should hold just the application key (letters, digits, - _ . :)." >&2
    exit 1
fi
package=$(dpkg-deb -f "$deb" Package)
case "$package" in
    sds-manager|sds-manager-personal) ;;
    *) echo "$1 is not an SDS-Manager package ($package)." >&2; exit 1 ;;
esac
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
dpkg-deb -R "$deb" "$work/root"
[ -d "$work/root/opt/sds-manager" ] || { echo "Unexpected package layout." >&2; exit 1; }
printf '%s\n' "$key" > "$work/key"
install -m 644 "$work/key" "$work/root/opt/sds-manager/rr_app_key"
if [ -f "$work/root/DEBIAN/md5sums" ]; then
    (cd "$work/root" && sed -i '\# opt/sds-manager/rr_app_key$#d' DEBIAN/md5sums &&
     md5sum opt/sds-manager/rr_app_key >> DEBIAN/md5sums)
fi
dpkg-deb --root-owner-group -Zxz --build "$work/root" "$work/new.deb" > /dev/null
mv "$work/new.deb" "$deb"
echo "Added the RadioReference application key to $(basename "$deb")."
echo "Install it with: sudo apt install ./$(basename "$deb")"
