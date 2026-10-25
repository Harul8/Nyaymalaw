"""The design's fonts come from the app's own server, never from a font service (owner decision O24,
plan AN.18): Source Serif 4 and Source Sans 3, as declared .woff2 assets with their open licence
beside them. Offline reading of the shipped files; not a browser check of how the page looks."""
from __future__ import annotations

from pathlib import Path

import pytest

from nm.shared.source_layout import browser_assets

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]
FACES = {"source-serif-4": "Source Serif 4", "source-sans-3": "Source Sans 3"}


def _fonts():
    fonts = {name: path for name, path in browser_assets().items() if path.suffix == ".woff2"}
    assert fonts, "no font is declared, so this checks nothing"
    return fonts


def test_each_declared_font_is_a_woff2_of_one_of_the_two_families():
    fonts = _fonts()
    for name, path in fonts.items():
        assert path.read_bytes()[:4] == b"wOF2", f"{name} is not a WOFF2 font"
        assert any(name.startswith(face + "-") for face in FACES), f"{name} is not one of the design's fonts"
    # Both families, each upright and italic, each in the Latin and the Latin Extended subset
    # (the rupee sign is in the second).
    assert len(fonts) == 8


def test_the_open_font_licence_sits_beside_the_fonts_and_names_both():
    folders = {path.parent for path in _fonts().values()}
    assert len(folders) == 1, "the fonts are kept in one folder, with their licence"
    licence = (folders.pop() / "OFL.txt").read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE Version 1.1" in licence
    for family in FACES.values():
        assert family in licence, f"the licence file does not name {family}"
    assert licence.count("Reserved Font Name 'Source'") == 2
