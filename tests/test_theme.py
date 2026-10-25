"""Palette guard for the brutalist theme."""

from app.ui.theme import ACCENT, BROWN, DARK, LIGHT, stylesheet


def test_accent_and_secondary_surface():
    assert ACCENT == "#FF6A00"
    assert BROWN == "#3B2416"
    assert DARK.surface == BROWN
    assert LIGHT.surface == BROWN
    assert DARK.accent == ACCENT and LIGHT.accent == ACCENT


def test_stylesheet_uses_theme_colours():
    for palette in (DARK, LIGHT):
        qss = stylesheet(palette, "JetBrains Mono")
        assert ACCENT in qss
        assert BROWN in qss
        assert "border-radius: 0px" in qss
        assert "background: #3B2416" in qss
