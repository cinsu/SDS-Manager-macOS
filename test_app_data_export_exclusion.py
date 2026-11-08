# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Regression: scanner operating-state changes must not block profile export."""
import unittest
from pathlib import Path
from unittest.mock import patch
import tempfile
from collections import namedtuple
import scanner_first_write as writer

class VolatileStateTests(unittest.TestCase):
    def test_profile_change_with_volatile_app_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); config = base/'config'; local = config/'BCDx36HP'; scanner = base/'mount'/'BCDx36HP'
            local.mkdir(parents=True); scanner.mkdir(parents=True)
            for folder in (local, scanner):
                (folder/'app_data.cfg').write_bytes(b'state='+str(folder).encode())
            (local/'profile.cfg').write_bytes(b'changed')
            (scanner/'profile.cfg').write_bytes(b'original')
            with patch.object(writer, 'list_configurations', return_value=[(config, {})]), \
                 patch.object(writer, 'verify_configuration'), \
                 patch.object(writer, 'inspect_scanner', return_value=('ok', True)), \
                 patch.object(writer, '_identity', return_value={}), \
                 patch.object(writer, 'assess_profile_replacement', return_value=(True, 'ok', {'field_edits':1,'added':0,'deleted':0})), \
                 patch.object(writer.shutil, 'disk_usage', return_value=namedtuple('Usage','total used free')(10**10,0,10**10)):
                plan=writer.prepare_first_write(config, scanner)
            self.assertEqual([x['relative'] for x in plan['files']], ['profile.cfg'])

if __name__ == '__main__': unittest.main()
