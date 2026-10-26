"""The design's fonts come from the app's own server, never from a font service (owner decision O24,
plan AN.18): Source Serif 4 and Source Sans 3, as declared .woff2 assets with their open licence
beside them. Offline reading of the shipped files; not a browser check of how the page looks."""
from __future__ import annotations

import re
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


def _faces():
    css = re.sub(r"/\*.*?\*/", " ", browser_assets()["fonts.css"].read_text(encoding="utf-8"), flags=re.S)
    return css, re.findall(r"@font-face\s*\{([^}]*)\}", css)


def test_one_sheet_declares_each_font_once_and_only_from_this_server():
    css, faces = _faces()
    fonts = _fonts()
    named = [url for face in faces for url in re.findall(r"url\(([^)]*)\)", face)]
    # Every file the sheet asks for is a declared font on this server, each asked for once; and the
    # sheet asks for nothing else (no other host, no import).
    assert sorted(named) == sorted(f"/static/{name}" for name in fonts)
    assert re.findall(r"url\(", css) and len(re.findall(r"url\(", css)) == len(named)
    assert "@import" not in css and "//" not in css.replace("/static/", "")
    for face in faces:
        family = re.search(r'font-family:\s*"([^"]+)"', face).group(1)
        style = re.search(r"font-style:\s*(\w+)", face).group(1)
        url = re.search(r"url\(/static/([^)]+)\)", face).group(1)
        assert family == FACES[url.split("-latin")[0]], f"{url} is declared as {family}"
        assert style == ("italic" if url.endswith("-italic.woff2") else "normal"), url
        assert "font-weight: 200 900" in face and "font-display: swap" in face, url
        assert "unicode-range:" in face, url


def test_the_open_font_licence_sits_beside_the_fonts_and_names_both():
    folders = {path.parent for path in _fonts().values()}
    assert len(folders) == 1, "the fonts are kept in one folder, with their licence"
    licence = (folders.pop() / "OFL.txt").read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE Version 1.1" in licence
    for family in FACES.values():
        assert family in licence, f"the licence file does not name {family}"
    assert licence.count("Reserved Font Name 'Source'") == 2
