# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
import re
import unittest
from pathlib import Path

import help_system as h

ROOT = Path(__file__).resolve().parent


class AboutAndLicenseTests(unittest.TestCase):
    def test_about_credits_author_ai_and_license(self):
        text = h.about_text()
        self.assertIn('Created by J. Lynch', text)
        self.assertIn('AI was used in the build', text)
        self.assertIn('GNU General Public License', text)
        self.assertIn('NO WARRANTY', text)
        self.assertIn('Not affiliated', text)
        self.assertIn(h.APP_VERSION, text)

    def test_version_is_the_same_everywhere(self):
        import edition
        main = (ROOT / 'database_favorites_manager.py').read_text(encoding='utf-8')
        self.assertIn('setWindowTitle(f"{APP_NAME} v{APP_VERSION}")', main)
        self.assertEqual(h.changelog_version(), edition.BASE_VERSION)
        self.assertTrue(h.APP_VERSION.startswith(edition.BASE_VERSION))
        self.assertEqual(h.APP_VERSION.endswith('-personal'), edition.PERSONAL)
        self.assertIn('edition.APP_VERSION', (ROOT / 'install.sh').read_text(encoding='utf-8'))

    def test_license_file_is_the_gpl_v3(self):
        text = h.read_doc('LICENSE')
        self.assertIn('GNU GENERAL PUBLIC LICENSE', text)
        self.assertIn('Version 3, 29 June 2007', text)
        self.assertGreater(len(text), 30000)

    def test_every_source_file_carries_the_license_header(self):
        for path in sorted(ROOT.glob('*.py')):
            head = path.read_text(encoding='utf-8')[:300]
            self.assertIn('SPDX-License-Identifier: GPL-3.0-or-later', head, path.name)
            self.assertIn('J. Lynch', head, path.name)

    def test_notice_names_license_ai_and_trademarks(self):
        text = (ROOT / 'NOTICE.md').read_text(encoding='utf-8')
        for needle in ('J. Lynch', 'GNU General Public License', 'AI assistance', 'Trademarks', 'PyQt6'):
            self.assertIn(needle, text)


class HelpContentTests(unittest.TestCase):
    def test_guide_and_changelog_are_bundled_and_readable(self):
        for name in ('USER_GUIDE.md', 'CHANGELOG.md', 'LICENSE'):
            self.assertTrue(h.read_doc(name), name)
        self.assertIsNone(h.read_doc('NO_SUCH_FILE.md'))
        self.assertIsNone(h.read_doc('../etc/passwd'))

    def test_help_menu_jump_target_exists_in_the_guide(self):
        titles = [t for _, t in h.headings(h.read_doc('USER_GUIDE.md'))]
        self.assertIn('If something goes wrong', titles)
        self.assertIn('Update the scanner\'s system database', titles)

    def test_headings_ignore_code_fences(self):
        md = '# Title\n## One\n```\n## not a heading\n```\n### Two\ntext'
        self.assertEqual(h.headings(md), [(2, 'One'), (3, 'Two')])

    def test_diagnostics_contain_no_paths_or_scanner_data(self):
        report = h.diagnostic_report('My configuration')
        self.assertIn(h.APP_NAME, report)
        self.assertIn('Active configuration: My configuration', report)
        self.assertNotIn('/home', report)

    def test_every_help_menu_target_is_wired(self):
        main = (ROOT / 'database_favorites_manager.py').read_text(encoding='utf-8')
        for method in ('show_document', 'show_about', 'open_backups_folder', 'copy_diagnostics'):
            self.assertIn('def %s(' % method, main)
        for label in ('User Guide', 'Recovery and Troubleshooting', "What's New", 'License', 'About…'):
            self.assertIn(label, main)


if __name__ == '__main__':
    unittest.main()
