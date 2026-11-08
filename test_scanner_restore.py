# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import scanner_restore as sr

class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.folder=self.base/'backups'/'20261025T120000Z'
        self.folder.mkdir(parents=True)
        self.source=self.folder/'BCDx36HP'/'favorites_lists'/'f_000001.hpd'
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b'original')
        self.manifest={'verified':True,'file_count':1,'files':[{'path':'favorites_lists/f_000001.hpd',
            'size':8,'sha256':hashlib.sha256(b'original').hexdigest()}]}
        (self.folder/'manifest.json').write_text(json.dumps(self.manifest))
        self.patch=patch.object(sr,'BACKUPS',self.base/'backups')
        self.patch.start();self.addCleanup(self.patch.stop)
    def test_valid_backup(self):
        self.assertEqual(sr.verify_backup(self.folder)['file_count'],1)
    def test_tamper_rejected(self):
        self.source.write_bytes(b'tampered')
        with self.assertRaises(ValueError):sr.verify_backup(self.folder)
    def test_traversal_rejected(self):
        self.manifest['files'][0]['path']='../evil'
        (self.folder/'manifest.json').write_text(json.dumps(self.manifest))
        with self.assertRaises(ValueError):sr.verify_backup(self.folder)
    def test_emergency_backup_requires_explicit_root(self):
        emergency=self.base/'emergency'
        emergency.mkdir()
        target=emergency/'EMERGENCY-PRE-RESTORE-20261025T120000Z'
        import shutil
        shutil.copytree(self.folder,target)
        with self.assertRaises(ValueError):
            sr.verify_backup(target)
        self.assertEqual(sr.verify_backup(target,emergency)['file_count'],1)

    def test_emergency_backup_tampering_rejected(self):
        emergency=self.base/'emergency'
        emergency.mkdir()
        target=emergency/'EMERGENCY-PRE-RESTORE-20261025T120000Z'
        import shutil
        shutil.copytree(self.folder,target)
        (target/'BCDx36HP'/'favorites_lists'/'f_000001.hpd').write_bytes(b'corrupted')
        with self.assertRaises(ValueError):
            sr.verify_backup(target,emergency)

    def test_list_only_verified(self):
        self.assertEqual(len(sr.list_backups()),1)
        self.source.write_bytes(b'bad')
        self.assertEqual(len(sr.list_backups()),0)

    def test_quick_listing_never_hashes_but_full_verification_still_catches_tampering(self):
        with patch.object(sr,'digest',side_effect=AssertionError('hashed')):
            self.assertEqual(len(sr.list_backups(verify=False)),1)
        self.source.write_bytes(b'tampered')                       # same size, different content
        self.assertEqual(len(sr.list_backups(verify=False)),1)     # listing is only structural...
        with self.assertRaises(ValueError):                         # ...restore preparation is not
            sr.prepare_restore(self.folder,self.base/'nowhere',self.base/'backups')

    def test_quick_listing_still_rejects_missing_or_resized_files(self):
        self.source.write_bytes(b'short')
        self.assertEqual(len(sr.list_backups(verify=False)),0)
        self.source.unlink()
        self.assertEqual(len(sr.list_backups(verify=False)),0)

if __name__=='__main__': unittest.main()
