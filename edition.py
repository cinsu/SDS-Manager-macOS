# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Which build this is (v0.1.0).

The personal build also downloads database archives and firmware from Uniden's servers. The public
build, made from it by build_manager.py, leaves those downloads out: it updates the database from an
archive file you choose, and takes firmware files you add yourself.
"""
EDITION = "public"
PERSONAL = EDITION == "personal"
APP_NAME = "SDS-Manager"
BASE_VERSION = "0.1.23"
APP_VERSION = BASE_VERSION + ("-personal" if PERSONAL else "")
PACKAGE_NAME = "sds-manager-personal" if PERSONAL else "sds-manager"
PROGRAM_COMMAND = "/usr/bin/sds-manager"
DB_UPDATE_LABEL = ("Update Database (Download and Rebuild)…" if PERSONAL
                   else "Update Database (Rebuild from Archive)…")
