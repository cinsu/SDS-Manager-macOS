# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""The theme engine shared with SDS100 Monitor: modes, accents, text sizes, KDE detection, preferences."""
import tempfile
import unittest
from pathlib import Path

import app_theme
import preferences


def lum(hex_colour):
    return app_theme._lum(app_theme._rgb(hex_colour))


def contrast(a, b):
    return app_theme.contrast(app_theme._rgb(a), app_theme._rgb(b))


class ThemeTests(unittest.TestCase):
    def test_dark_keeps_the_original_colours(self):
        theme = app_theme.Theme('dark', 'blue', 'normal', True)
        self.assertEqual(app_theme.palette_colours(theme)['Window'].lower(), '#171b22')
        self.assertEqual(theme.scale, 1.0)

    def test_light_is_light_and_readable(self):
        theme = app_theme.Theme('light', 'blue', 'normal', True)
        colours = app_theme.palette_colours(theme)
        self.assertGreater(lum(colours['Window']), lum(colours['Text']))
        self.assertGreaterEqual(contrast(colours['Text'], colours['Base']), 4.5)
        self.assertGreaterEqual(contrast(theme.colour(app_theme.WARN), colours['Base']), 3.0)

    def test_night_is_red_only(self):
        theme = app_theme.Theme('night', 'teal', 'normal', True)
        for colour in app_theme.palette_colours(theme).values():
            r, g, b = (int(colour.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))
            self.assertLessEqual(max(g, b), r, colour)

    def test_accents_change_the_highlight(self):
        seen = {app_theme.palette_colours(app_theme.Theme('dark', a, 'normal', True))['Highlight']
                for a in app_theme.THEME_ACCENTS}
        self.assertEqual(len(seen), len(app_theme.THEME_ACCENTS))

    def test_text_sizes_scale(self):
        scales = [app_theme.Theme('dark', 'blue', s, True).scale for s in app_theme.TEXT_SIZES]
        self.assertEqual(scales, sorted(scales))

    def test_stylesheet_follows_the_theme(self):
        dark = app_theme.stylesheet(app_theme.Theme('dark', 'blue', 'normal', True))
        light = app_theme.stylesheet(app_theme.Theme('light', 'blue', 'normal', True))
        self.assertIn('#171b22', dark.lower())
        self.assertNotIn('#171b22', light.lower())

    def test_widget_css_is_recoloured_and_reapplied(self):
        class Widget:
            def __init__(self):
                self.props, self.css = {}, None
            def setProperty(self, k, v): self.props[k] = v
            def property(self, k): return self.props.get(k)
            def setStyleSheet(self, css): self.css = css
        w = Widget()
        app_theme.THEME = app_theme.Theme('dark', 'blue', 'normal', True)
        app_theme.set_css(w, f'color: {app_theme.WARN};')
        dark_css = w.css
        app_theme.THEME = app_theme.Theme('light', 'blue', 'normal', True)
        app_theme.reapply([w, object()])
        self.assertNotEqual(w.css, dark_css)
        app_theme.THEME = app_theme.Theme('dark', 'blue', 'normal', True)


class SystemModeTests(unittest.TestCase):
    def kde(self, rgb):
        folder = tempfile.mkdtemp()
        path = Path(folder) / 'kdeglobals'
        path.write_text(f'[General]\nx=1\n[Colors:Window]\nBackgroundNormal={rgb}\n')
        return path

    def test_kde_light_and_dark(self):
        self.assertFalse(app_theme.system_is_dark(path=self.kde('239,240,241')))
        self.assertTrue(app_theme.system_is_dark(path=self.kde('32,35,38')))
        self.assertEqual(app_theme.resolve('system', 'blue', 'normal', None, self.kde('239,240,241')).mode, 'light')

    def test_falls_back_to_the_desktop_palette_then_dark(self):
        missing = Path(tempfile.mkdtemp()) / 'none'
        self.assertFalse(app_theme.system_is_dark(240, missing))
        self.assertTrue(app_theme.system_is_dark(None, missing))
        self.assertTrue(app_theme.system_is_dark(object(), missing))

    def test_unknown_values_fall_back(self):
        theme = app_theme.resolve('purple', 'pink', 'huge', 20, Path(tempfile.mkdtemp()) / 'none')
        self.assertEqual((theme.mode, theme.accent, theme.size), ('dark', 'blue', 'normal'))


class PreferenceTests(unittest.TestCase):
    def test_appearance_choices_have_labels_and_match_the_engine(self):
        prefs = {p.key: p for p in preferences.PREFS}
        self.assertEqual(set(prefs['theme'].values), set(app_theme.THEME_MODES))
        self.assertEqual(set(prefs['accent'].values), set(app_theme.THEME_ACCENTS))
        self.assertEqual(set(prefs['text_size'].values), set(app_theme.TEXT_SIZES))
        self.assertEqual(prefs['theme'].display('night'), 'Night (red)')
        self.assertEqual(prefs['font_size'].display(3), 3)


if __name__ == '__main__':
    unittest.main()
