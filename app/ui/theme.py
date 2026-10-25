"""Brutalist theme: two palettes, orange accent on brown secondary surfaces."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase

ACCENT = "#FF6A00"
BROWN = "#3B2416"


def _root() -> Path:
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        return Path(frozen)
    return Path(__file__).resolve().parents[2]


def asset(*parts: str) -> Path:
    return _root().joinpath("assets", *parts)


def load_fonts() -> str:
    """Register bundled JetBrains Mono faces; return the family actually used."""
    families: list[str] = []
    for name in ("JetBrainsMono-Regular.ttf", "JetBrainsMono-Bold.ttf"):
        path = asset("fonts", name)
        if path.exists():
            font_id = QFontDatabase.addApplicationFont(str(path))
            if font_id >= 0:
                families.extend(QFontDatabase.applicationFontFamilies(font_id))
    if "JetBrains Mono" in QFontDatabase.families():
        return "JetBrains Mono"
    for fallback in ("Consolas", "Cascadia Mono", "Courier New"):
        if fallback in QFontDatabase.families():
            return fallback
    return "monospace"


def base_font(family: str) -> QFont:
    font = QFont(family)
    font.setPointSize(9)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return font


def spaced_font(family: str, size: int, weight: QFont.Weight, spacing: float) -> QFont:
    font = QFont(family)
    font.setPointSize(size)
    font.setWeight(weight)
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return font


@dataclass(frozen=True)
class Palette:
    inverted: bool
    bg: str
    panel: str
    surface: str
    on_surface: str
    fg: str
    dim: str
    line: str
    surface_line: str
    accent: str = ACCENT
    paper: str = "#FFFFFF"
    ink: str = "#000000"

    @property
    def graph_bg(self) -> str:
        return "#F4F4F4" if self.inverted else "#070707"

    @property
    def graph_ink(self) -> str:
        return "#000000" if self.inverted else "#F2F2F2"

    @property
    def graph_grid(self) -> str:
        return "#C9C9C9" if self.inverted else "#1E1E1E"

    @property
    def graph_axis(self) -> str:
        return "#3A3A3A" if self.inverted else "#6A6A6A"


DARK = Palette(
    inverted=False,
    bg="#050505",
    panel="#0C0C0C",
    surface=BROWN,
    on_surface="#FFF1E0",
    fg="#EDEDED",
    dim="#8C7E72",
    line="#3A2C23",
    surface_line="#7A4A2A",
)

LIGHT = Palette(
    inverted=True,
    bg="#F2F2F2",
    panel="#FFFFFF",
    surface=BROWN,
    on_surface="#FFF1E0",
    fg="#0A0A0A",
    dim="#6A625B",
    line="#C6BCB3",
    surface_line="#2A1A10",
)


def stylesheet(p: Palette, family: str) -> str:
    arrow = asset("ui", "arrow.png").as_posix()
    return f"""
    QWidget {{
        background: transparent;
        color: {p.fg};
        font-family: "{family}", "Consolas", "Courier New", monospace;
        font-size: 12px;
    }}
    QWidget#Root {{
        background: {p.bg};
        border: 2px solid {p.fg};
    }}
    QLabel {{ background: transparent; }}
    QLabel#Brand {{
        font-family: "{family}";
        font-size: 22px;
        font-weight: bold;
    }}
    QLabel#BrandMark {{
        background: {p.accent};
        color: #000000;
        font-weight: bold;
        font-size: 15px;
        padding: 2px 6px;
    }}
    QLabel#Section {{
        color: {p.accent};
        font-weight: bold;
        font-size: 12px;
    }}
    QLabel#SectionTitle {{ font-weight: bold; font-size: 13px; }}
    QLabel#Dim {{ color: {p.dim}; font-size: 11px; }}
    QLabel#Accent {{ color: {p.accent}; }}
    QLabel#Big {{ font-size: 26px; font-weight: bold; }}
    QLabel#Readout {{ color: {p.accent}; font-size: 11px; }}
    QLabel#StatusText {{ color: {p.on_surface}; font-size: 11px; }}
    QFrame#Panel {{
        background: {p.panel};
        border: 2px solid {p.line};
    }}
    QFrame#PanelAccent {{ background: {p.panel}; border: 2px solid {p.accent}; }}
    QFrame#Divider {{ background: {p.line}; border: none; }}
    QFrame#TitleBar {{ background: {p.bg}; border: none; border-bottom: 2px solid {p.line}; }}
    QFrame#StatusBar {{ background: {p.surface}; border: none; border-top: 2px solid {p.accent}; }}
    QFrame#GraphShell {{ background: {p.graph_bg}; border: 2px solid {p.line}; }}
    QPushButton {{
        background: {p.surface};
        color: {p.on_surface};
        border: 2px solid {p.fg};
        border-radius: 0px;
        padding: 5px 9px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background: {p.accent};
        color: #000000;
        border-color: {p.accent};
    }}
    QPushButton:pressed {{ background: {p.fg}; color: {p.bg}; }}
    QPushButton:checked {{
        background: {p.accent};
        color: #000000;
        border-color: {p.accent};
    }}
    QPushButton:disabled {{
        color: {p.dim};
        border-color: {p.surface_line};
        background: {p.surface};
    }}
    QPushButton#Primary {{
        background: {p.accent};
        color: #000000;
        border: 2px solid {p.accent};
        padding: 7px 12px;
    }}
    QPushButton#Primary:hover {{ background: {p.fg}; color: {p.bg}; border-color: {p.fg}; }}
    QPushButton#WindowBtn {{
        border: none;
        background: transparent;
        color: {p.fg};
        padding: 0px;
        font-size: 13px;
        font-weight: bold;
    }}
    QPushButton#WindowBtn:hover {{ background: {p.accent}; color: #000000; }}
    QLineEdit, QPlainTextEdit {{
        background: {p.surface};
        color: {p.on_surface};
        border: 2px solid {p.surface_line};
        border-radius: 0px;
        padding: 4px;
        selection-background-color: {p.accent};
        selection-color: #000000;
    }}
    QLineEdit:focus, QPlainTextEdit:focus {{ border: 2px solid {p.accent}; }}
    QComboBox {{
        background: {p.surface};
        color: {p.on_surface};
        border: 2px solid {p.surface_line};
        border-radius: 0px;
        padding: 4px 6px;
    }}
    QComboBox:hover {{ border-color: {p.accent}; }}
    QComboBox::drop-down {{
        width: 20px;
        border-left: 2px solid {p.surface_line};
        background: {p.surface};
    }}
    QComboBox::down-arrow {{
        image: url({arrow});
        width: 9px;
        height: 6px;
    }}
    QComboBox QAbstractItemView {{
        background: {p.surface};
        color: {p.on_surface};
        border: 2px solid {p.accent};
        outline: none;
        selection-background-color: {p.accent};
        selection-color: #000000;
    }}
    QSlider::groove:horizontal {{
        height: 4px;
        background: {p.line};
        border: none;
    }}
    QSlider::sub-page:horizontal {{ background: {p.accent}; }}
    QSlider::handle:horizontal {{
        background: {p.accent};
        border: 2px solid {p.bg};
        width: 12px;
        height: 12px;
        margin: -8px 0px;
    }}
    QSlider::handle:horizontal:hover {{ background: {p.fg}; }}
    QScrollBar:vertical {{
        background: transparent;
        width: 12px;
        border-left: 2px solid {p.line};
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{ background: {p.dim}; min-height: 24px; }}
    QScrollBar::handle:vertical:hover {{ background: {p.accent}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px; background: transparent; border: none;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 12px;
        border-top: 2px solid {p.line};
        margin: 0px;
    }}
    QScrollBar::handle:horizontal {{ background: {p.dim}; min-width: 24px; }}
    QScrollBar::handle:horizontal:hover {{ background: {p.accent}; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px; background: transparent; border: none;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}
    QToolTip {{
        background: {p.surface};
        color: {p.on_surface};
        border: 2px solid {p.accent};
        border-radius: 0px;
        padding: 3px;
    }}
    QMenu {{
        background: {p.panel};
        color: {p.fg};
        border: 2px solid {p.fg};
    }}
    QMenu::item {{ padding: 6px 18px; }}
    QMenu::item:selected {{ background: {p.accent}; color: #000000; }}
    QSplitter::handle {{ background: {p.line}; }}
    """
