# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Themes shared with SDS100 Monitor: Dark, Light, System (follow KDE) and Night (red), six accents and
four text sizes. Pure Python (no Qt) so it can be tested; ui_extras applies the result to the application.

Every colour is written as one of the original dark-theme values. Those values are keys: each has a role
(background, text, status colour, button fill, accent), and the theme works out what that role looks like
in the chosen mode and accent. The engine is the same one SDS100 Monitor v1.1.40+ uses, so both programs
look alike with the same settings.
"""
from pathlib import Path
import re

import colorsys

THEME_MODES = {"dark": "Dark", "light": "Light", "system": "System (follow KDE)",
               "night": "Night (red)"}
THEME_ACCENTS = {"blue": ("Blue", 210), "red": ("Red", 0), "green": ("Green", 140),
                 "amber": ("Amber", 38), "purple": ("Purple", 275), "teal": ("Teal", 178)}
TEXT_SIZES = {"small": ("Small", 0.86), "normal": ("Normal", 1.0),
              "large": ("Large", 1.15), "xlarge": ("Extra large", 1.3)}
# The Scanner Screen mirror shows the scanner's own display colours.
FIXED_COLOURS = {"#000000", "#05080d", "#111111", "#0d1d3a", "#f0f0f0", "#f4f4f0",
                 "#f2f6ff", "#8fa3ba"}
# Coloured button backgrounds with white text: kept as they are in Light.
FILL_COLOURS = {"#344d71", "#536779", "#566476", "#7654a6", "#8a3b3b", "#263849",
                "#435c77", "#1b8a5a", "#a87d15", "#bd6b23", "#9c3b2e", "#a83232",
                "#5b4a1e", "#7d6420", "#a5841f", "#2f9e62", "#39424e", "#1c2028"}
ACCENT_FILLS = {"#2167b1", "#344d71", "#245b91", "#2975b8", "#426789"}
ACCENT_LINES = {"#69b8ef", "#76d5f4", "#83c3e9", "#85dcff", "#69a8d6", "#6d9fc6",
                "#567c9f", "#dceeff", "#3d8fd6"}
ON_FILL = {"#ffffff"}
LIGHT_BG = (0.85, 0.865, 0.88)          # darkest Light panel text sits on (buttons, headers)
HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b")
FONT_PX_RE = re.compile(r"(font-size:\s*)(\d+(?:\.\d+)?)px")
WHITE_RE = re.compile(r"(color:\s*)white\b")


def _rgb(hexkey):
    return tuple(int(hexkey[i:i + 2], 16) / 255 for i in (1, 3, 5))


def _hex(r, g, b):
    return "#" + "".join(f"{max(0, min(255, round(v * 255))):02x}" for v in (r, g, b))


def _lum(rgb):
    def ch(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def colour_role(key):
    if key in FIXED_COLOURS:
        return "fixed"
    if key in ON_FILL:
        return "onfill"
    if key in ACCENT_FILLS:
        return "afill"
    if key in ACCENT_LINES:
        return "aline"
    if key in FILL_COLOURS:
        return "fill"
    h, l, s = colorsys.rgb_to_hls(*_rgb(key))
    hue = h * 360
    if l < 0.45 and s < 0.45:
        return "surface"
    if l < 0.5:
        return "fill"
    if s < 0.3 or l > 0.9 or (s < 0.45 and 195 <= hue <= 235):
        return "text"
    return "status"


class Theme:
    def __init__(self, mode="dark", accent="blue", size="normal", system_dark=True):
        self.choice = mode if mode in THEME_MODES else "dark"
        self.mode = ({"system": "dark" if system_dark else "light"}.get(self.choice,
                                                                         self.choice))
        self.accent = accent if accent in THEME_ACCENTS else "blue"
        self.size = size if size in TEXT_SIZES else "normal"
        self.scale = TEXT_SIZES[self.size][1]
        self.cache, self.reverse = {}, {}

    @property
    def identity(self):
        return self.mode == "dark" and self.accent == "blue"

    def colour(self, key):
        """Theme value of one colour key ('#rrggbb'); anything else unchanged."""
        if not isinstance(key, str) or not HEX_RE.fullmatch(key.strip()):
            return key
        key = key.strip().lower()
        out = self.cache.get(key)
        if out is None:
            out = key if self.identity else self.transform(key)
            self.cache[key] = out
            self.reverse.setdefault(out, key)
        return out

    def transform(self, key):
        role = colour_role(key)
        rgb = _rgb(key)
        if self.mode == "night":
            return self.night(rgb, role)
        h, l, s = colorsys.rgb_to_hls(*rgb)
        hue = h * 360
        if self.accent != "blue" and (role in ("afill", "aline")
                                      or (role in ("surface", "text") and 195 <= hue <= 235)):
            hue = (hue + THEME_ACCENTS[self.accent][1] - 210) % 360
            if role in ("surface", "text"):
                s *= 0.55
            elif role == "afill":
                # Same brightness as the blue it replaces, so white text stays readable
                # (green, teal and amber are much brighter than blue at equal lightness).
                target = _lum(rgb)
                while l > 0.05 and _lum(colorsys.hls_to_rgb(hue / 360, l, s)) > target:
                    l -= 0.01
        if self.mode == "light":
            if role == "surface":
                l = max(0.6, min(0.985, 0.97 - (l - 0.09) * 0.9))
                s *= 0.7
            elif role == "text":
                l = min(0.34, (1 - l) * 1.3)
                s = min(s, 0.5)
            elif role in ("status", "aline"):
                s = max(s, 0.55) if s > 0.2 else s
                target = 4.5 if role == "status" else 3.0
                while l > 0.05 and contrast(colorsys.hls_to_rgb(hue / 360, l, s),
                                            LIGHT_BG) < target:
                    l -= 0.01
        return _hex(*colorsys.hls_to_rgb(hue / 360, l, s))

    @staticmethod
    def night(rgb, role):
        """Night: every colour becomes a shade of red by its brightness."""
        y = _lum(rgb)
        if role == "surface":
            l, s = 0.42 * y ** 0.5, 0.55
        elif role in ("fill", "afill"):
            l, s = 0.40 * y ** 0.5, 0.7
        else:
            l, s = 0.25 + 0.25 * y ** 0.5, 1.0
        return _hex(*colorsys.hls_to_rgb(0, l, s))

    def css(self, text):
        if not isinstance(text, str):
            return text
        if not self.identity:
            text = WHITE_RE.sub(lambda m: m.group(1) + "#ffffff", text)
        # Always through colour(), so the colours in use are known for a change.
        text = HEX_RE.sub(lambda m: self.colour(m.group()), text)
        if self.scale != 1.0:
            text = FONT_PX_RE.sub(
                lambda m: f"{m.group(1)}{max(7, round(float(m.group(2)) * self.scale))}px",
                text)
        return text




THEME = Theme()


def theme_hex(key):
    return THEME.colour(key)


def th(css):
    """A stylesheet in the current theme."""
    return THEME.css(css)


KDE_GLOBALS = Path.home() / ".config" / "kdeglobals"


def kde_window_lightness(path=None):
    """Lightness (0-255) of KDE's window background from ~/.config/kdeglobals, or None.
    Qt 6 programs don't always get KDE's palette on Plasma 5, so it's read directly."""
    try:
        section = None
        for line in Path(path or KDE_GLOBALS).read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("["):
                section = line
            elif section == "[Colors:Window]" and line.startswith("BackgroundNormal="):
                r, g, b = (int(x) for x in line.split("=", 1)[1].split(",")[:3])
                return (max(r, g, b) + min(r, g, b)) / 2
    except (OSError, ValueError):
        pass
    return None


def system_is_dark(palette_lightness=None, path=None):
    """KDE's scheme if it can be read, otherwise the desktop palette's window lightness."""
    lightness = kde_window_lightness(path)
    if lightness is not None:
        return lightness < 128
    if isinstance(palette_lightness, (int, float)):
        return palette_lightness < 128
    return True


# Palette roles (Qt's QPalette.ColorRole names) → colour keys.
PALETTE = {
    "Window": "#171b22", "WindowText": "#e9eef5", "Base": "#1c2530", "AlternateBase": "#253140",
    "Text": "#e9eef5", "Button": "#293544", "ButtonText": "#e9eef5", "BrightText": "#ff9e91",
    "Highlight": "#2975b8", "HighlightedText": "#ffffff", "ToolTipBase": "#202d3d",
    "ToolTipText": "#edf5ff", "PlaceholderText": "#8392a6", "Link": "#8bd6f2", "LinkVisited": "#b48cf0",
    "Light": "#53647a", "Midlight": "#465c75", "Mid": "#40536b", "Dark": "#11161d", "Shadow": "#0d1117",
}
DISABLED_TEXT = "#718094"

# Named colours for the few places that colour text themselves.
MUTED, WARN, OK, HEADING, ACCENT_BUTTON = "#8392a6", "#ff9e91", "#7ee3a5", "#a5bdd2", "#2167b1"

# The application stylesheet: SDS100 Monitor's main stylesheet, without its fixed font size (text size is
# applied to the application font here), plus the widgets this program uses that the Monitor doesn't.
STYLESHEET = """
QWidget { background:#171b22; color:#e9eef5; }
QMainWindow::separator { background:#263448; width:5px; height:5px; }
QMenuBar { background:#171b22; }
QMenuBar::item { background:transparent; padding:5px 10px; border-radius:4px; }
QMenuBar::item:selected { background:#2975b8; color:#ffffff; }
QPushButton { background:#293544; border:1px solid #53647a; border-radius:5px; padding:6px 12px; }
QPushButton:hover { background:#3d536b; }
QPushButton:pressed { background:#245b91; color:#ffffff; }
QPushButton:default { border:2px solid #69b8ef; }
QPushButton:disabled { background:#202832; color:#718094; border-color:#40536b; }
QLineEdit, QTextEdit, QPlainTextEdit, QTextBrowser, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {
    background:#1c2530; border:1px solid #53647a; border-radius:4px; padding:3px;
    selection-background-color:#2975b8; selection-color:#ffffff; }
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus,
QDoubleSpinBox:focus { border:1px solid #69b8ef; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled { color:#718094; }
QComboBox QAbstractItemView { background:#202d3d; border:1px solid #567c9f;
    selection-background-color:#2975b8; selection-color:#ffffff; }
QTableWidget, QTableView, QTreeWidget, QTreeView, QListWidget, QListView {
    background:#1c2530; alternate-background-color:#253140; gridline-color:#405066;
    border:1px solid #40536b; selection-background-color:#2975b8; selection-color:#ffffff; }
QHeaderView::section { background:#35445a; padding:5px; border:0; border-right:1px solid #465c75;
    border-bottom:1px solid #465c75; }
QTableCornerButton::section { background:#35445a; border:0; }
QProgressBar { background:#283341; border:1px solid #53647a; border-radius:4px; text-align:center; }
QProgressBar::chunk { background:#55b98b; }
QGroupBox { border:1px solid #465c75; border-radius:6px; margin-top:14px; padding-top:8px; }
QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 5px; color:#a5bdd2; font-weight:600; }
QTabWidget::pane { border:1px solid #465c75; border-radius:4px; top:-1px; }
QTabBar { background:#171b22; qproperty-drawBase:0; }
QTabBar::tab { background:#263448; color:#c8d7e8; border:1px solid #465c75;
    border-bottom:3px solid #465c75; border-top-left-radius:8px; border-top-right-radius:8px;
    padding:7px 16px; margin:3px 3px 0 0; font-weight:600; }
QTabBar::tab:hover:!selected { background:#364e69; color:#edf5ff; border-color:#6d9fc6;
    border-bottom-color:#6d9fc6; }
QTabBar::tab:selected { background:#245b91; color:#ffffff; border:1px solid #69b8ef;
    border-bottom:3px solid #76d5f4; font-weight:700; }
QTabBar::tab:disabled { color:#718094; background:#202832; }
QSplitter::handle { background:#426789; }
QSplitter::handle:hover { background:#69a8d6; }
QMenu { background-color:#202d3d; color:#edf5ff; border:2px solid #567c9f; border-radius:7px; padding:6px; }
QMenu::item { background:transparent; padding:7px 30px 7px 14px; margin:2px 3px; border-radius:5px; }
QMenu::item:selected:enabled { background:#2975b8; color:#ffffff; border-left:4px solid #85dcff;
    padding-left:10px; font-weight:700; }
QMenu::item:disabled { color:#8392a6; }
QMenu::separator { height:1px; background:#51637a; margin:6px 10px; }
QDockWidget { border:1px solid #40536b; }
QDockWidget::title { background:#25354a; color:#eaf4ff; padding:7px 10px; font-weight:700; }
QToolTip { background:#202d3d; color:#edf5ff; border:1px solid #567c9f; padding:4px; }
QStatusBar { background:#171b22; }
QStatusBar::item { border:0; }
QScrollBar:vertical, QScrollBar:horizontal { background:#1c2530; border:0; }
QScrollBar::handle { background:#465c75; border-radius:4px; min-height:24px; min-width:24px; }
QScrollBar::handle:hover { background:#6d9fc6; }
QScrollBar::add-line, QScrollBar::sub-line { width:0; height:0; }
"""


def stylesheet(theme=None):
    return (theme or THEME).css(STYLESHEET)


def palette_colours(theme=None):
    """{role name: '#rrggbb'} for QPalette, plus 'Disabled' for disabled text."""
    t = theme or THEME
    colours = {role: t.colour(key) for role, key in PALETTE.items()}
    colours["Disabled"] = t.colour(DISABLED_TEXT)
    return colours


def resolve(mode, accent, size, palette_lightness=None, kde_path=None):
    """A Theme from saved preferences (bad values fall back to the defaults)."""
    return Theme(mode, accent, size, system_is_dark(palette_lightness, kde_path))


def set_css(widget, css):
    """setStyleSheet() through the theme; the original is kept so a theme change can re-apply it."""
    try:
        widget.setProperty("themeCss", css)
    except (AttributeError, TypeError):
        pass
    widget.setStyleSheet(th(css))


def reapply(widgets):
    """Re-apply set_css() styles after a theme change."""
    for widget in widgets:
        try:
            css = widget.property("themeCss")
        except (AttributeError, TypeError, RuntimeError):
            continue
        if isinstance(css, str):
            widget.setStyleSheet(th(css))
