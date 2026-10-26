"""The person button shows the advocate's initials in a circle (plan AN.20; the signed-off design),
not a generic person mark. Reads the shipped page, stylesheet and script; the owner's browser shows how
it looks."""
from __future__ import annotations

import re

import pytest

from nm.shared.source_layout import browser_assets

pytestmark = pytest.mark.class_a

PAGE = browser_assets()["index.html"].read_text(encoding="utf-8")


def toggle() -> str:
    start = PAGE.index('<button type="button" id="account-toggle"')
    return PAGE[start:PAGE.index("</button>", start)]


def test_the_button_holds_an_initials_circle_that_is_not_read_out_and_keeps_its_name():
    button = toggle()
    assert '<span class="avatar" id="account-initials" aria-hidden="true"></span>' in button
    assert "person-icon" not in PAGE, "the generic person mark is gone"
    # What a screen reader hears is what the button opens, not two letters.
    assert '<span class="sr-only">Profile and sign out</span>' in button


STYLE = re.sub(r"/\*.*?\*/", "", browser_assets()["app.css"].read_text(encoding="utf-8"), flags=re.S)


def test_the_circle_is_drawn_only_when_it_has_letters_and_stays_on_a_phone():
    circle = re.search(r"(?<![\w-])\.avatar\s*\{([^}]*)\}", STYLE).group(1)
    assert "border-radius: 50%" in circle and "width: 30px" in circle and "height: 30px" in circle
    assert re.search(r"\.avatar:empty\s*\{\s*display:\s*none;", STYLE), "an empty circle is drawn"
    # The name gives way on a phone (F-A-17); the initials are what stay.
    phone = STYLE[STYLE.index("@media (max-width: 820px) {"):]
    phone = phone[:phone.index("\n}\n")]
    assert ".ribbon-account > .who-name { display: none; }" in phone and ".avatar" not in phone
