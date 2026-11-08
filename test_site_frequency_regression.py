# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Native site frequency guard regression (does not require Qt runtime)."""
import ast
import unittest
from pathlib import Path
from decimal import Decimal, InvalidOperation

class TestSiteFrequency(unittest.TestCase):
    def test_parser_rejects_invalid_or_imprecise_frequency(self):
        module = ast.parse(Path(__file__).with_name('favorites_settings_window.py').read_text())
        cls = next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == 'FavoritesSettingsDialog')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_parse_site_mhz')
        ns = {'Decimal': Decimal, 'InvalidOperation': InvalidOperation}
        exec(compile(ast.Module(body=[method], type_ignores=[]), '<method>', 'exec'), ns)
        parse = ns['_parse_site_mhz']
        self.assertEqual(parse('853.612500'), '853612500')
        self.assertEqual(parse('853.6125'), '853612500')
        for bad in ('', 'nan', 'inf', '0', '1301', '853.6125001', 'hello', '-1'):
            self.assertIsNone(parse(bad), bad)
    def test_native_tfreq_field(self):
        row = 'T-Freq\tTFreqId=0\tSiteId=48419\t\t\t452450000\t1\t7\tAny'.split('\t')
        self.assertEqual(row[5], '452450000')
        self.assertEqual(row[2], 'SiteId=48419')
