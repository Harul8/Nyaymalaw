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
