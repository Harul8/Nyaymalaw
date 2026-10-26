"""The app's backgrounds are white, not beige (owner decision O27, 26 Oct 2026; plan AN.21).

The owner, looking at the redesigned app: "I don't want the beige color as background color, keep it
white / transparent." So the page, the conversation, the matter board, the history list and the sign-in
page are white; the few small tinted spots that shared the beige (table header rows, hover highlights,
quiet labels) take a barely-there COOL grey so hovering and headers still show; and the amber and brass
washes that MEAN a warning, a limit or a near deadline stay, because they are meanings and not backgrounds.
This reads the shipped stylesheets; the owner's browser shows how it looks. The public site is not the app
and keeps its own ivory until the owner says otherwise.
"""
from __future__ import annotations

import re

import pytest

from nm.shared.source_layout import browser_assets

pytestmark = pytest.mark.class_a

#: The ivory paper, the sunken beige, the hover ivory and the ivory on the sign-in story panel.
BEIGE = ("#fbf8f1", "#f4f0e6", "#fdfcf8", "#f3efe4")
#: Everything the app's own style comes from.
SHEETS = ("app.css", "intake-materials.css")
#: What the owner sees as the app's background, by the rule that paints it.
PAINTED = ("body", ".conversation", ".matter-board", ".rail", "#gate", ".workspace-heading", ".masthead")


def _css(name: str) -> str:
    return re.sub(r"/\*.*?\*/", " ", browser_assets()[name].read_text(encoding="utf-8"), flags=re.S)


APP = _css("app.css")


def tokens() -> dict[str, str]:
    root = re.search(r":root\s*\{(.*?)\n\}", APP, re.S).group(1)
    return {name: " ".join(value.split()).lower() for name, value in re.findall(r"--([\w-]+)\s*:\s*([^;]+);", root)}


def resolved(value: str) -> str:
    """A background's colour, with a var() followed to the token it names."""
    value = value.strip().lower()
    named = re.fullmatch(r"var\(--([\w-]+)\)", value)
    return tokens()[named.group(1)] if named else value


def backgrounds_of(selector: str) -> list[str]:
    """Every background the stylesheet gives this exact selector, resolved to a colour."""
    found = []
    for body in re.findall(r"(?:^|\})\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", APP):
        for declaration in re.findall(r"(?:^|;)\s*background(?:-color)?\s*:\s*([^;]+)", body):
            found.append(resolved(declaration))
    return found


def test_the_page_and_the_boards_are_white():
    colours = tokens()
    assert colours["paper"] == "#ffffff", "the page's paper is not white"
    assert colours["board"] == "#ffffff", "the matter board's and the history list's ground is not white"


@pytest.mark.parametrize("selector", PAINTED)
def test_what_the_owner_sees_as_the_background_resolves_to_white(selector):
    found = backgrounds_of(selector)
    assert found, f"{selector} paints no background, so this checks nothing"
    assert set(found) == {"#ffffff"}, f"{selector} is painted {sorted(set(found))}, not white"


def test_the_small_tints_are_a_light_cool_grey_so_hover_and_headers_still_show():
    tint = tokens()["surface-2"]
    assert re.fullmatch(r"#[0-9a-f]{6}", tint), tint
    red, green, blue = (int(tint[i:i + 2], 16) for i in (1, 3, 5))
    assert tint != "#ffffff", "a hover highlight needs something to show"
    assert min(red, green, blue) >= 0xF0, f"{tint} is no longer barely there"
    assert blue >= red, f"{tint} is warm, so it reads as beige"


@pytest.mark.parametrize("name", SHEETS)
def test_no_beige_value_is_left_in_the_apps_stylesheets(name):
    css = _css(name).lower()
    assert not [value for value in BEIGE if value in css], f"{name} still holds a beige value"


def test_the_colours_that_mean_something_are_left_alone():
    """A warning, the usage limit and a near deadline are colours with a meaning (O27, effect 3)."""
    colours = tokens()
    assert colours["amber-w"] == "#f6ecd2" and colours["brass-w"] == "#f4ecd6"
    assert colours["signal-w"] == "#f7e6e2" and colours["good-w"] == "#dcebe2"
