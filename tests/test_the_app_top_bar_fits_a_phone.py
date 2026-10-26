"""The app's top bar wraps by whole groups instead of squeezing one, and on a phone its actions take a row of
their own (owner decision O28; plan AN.22). Reads the shipped style sheet; the width check in the journeys
(`scrollWidth <= clientWidth` at 390, 768 and 1280) and the owner's browser show the result.

Measured in a real browser before this rule: a 390px phone needed 557px of bar, which put the person menu off the
edge, and between 821px and about 1000px the name was squeezed into a column 195px tall. The logo, Home, + New
matter, Conversation history, the usage chip, the name and the person menu need about 1000px on one row.
"""
from __future__ import annotations

import re

import pytest

from nm.shared.source_layout import browser_assets

pytestmark = pytest.mark.class_a

CSS = re.sub(r"/\*.*?\*/", " ", browser_assets()["app.css"].read_text(encoding="utf-8"), flags=re.S)
PHONE = "@media (max-width: 600px) {"


def without_media(sheet: str) -> str:
    """The sheet without its media blocks, which only refine a rule at another width."""
    kept, depth, inside = [], 0, False
    for position, character in enumerate(sheet):
        if not inside and sheet.startswith("@media", position):
            inside, depth = True, 0
        if inside:
            depth += {"{": 1, "}": -1}.get(character, 0)
            if character == "}" and depth == 0:
                inside = False
            continue
        kept.append(character)
    return "".join(kept)


TOP_LEVEL = without_media(CSS)


def rule(selector: str, sheet: str = TOP_LEVEL) -> str:
    """What the one rule for exactly this selector declares in this sheet, in one line."""
    found = re.findall(r"(?:^|[{}])\s*" + re.escape(selector) + r"\s*\{([^{}]*)\}", sheet)
    assert len(found) == 1, f"{selector}: {len(found)} rules"
    return " ".join(found[0].split())


def block(opening: str) -> str:
    """The text inside the one media block that opens exactly like this."""
    assert CSS.count(opening) == 1, opening
    start = CSS.index(opening) + len(opening)
    depth = 1
    for position in range(start, len(CSS)):
        depth += {"{": 1, "}": -1}.get(CSS[position], 0)
        if depth == 0:
            return CSS[start:position]
    raise AssertionError("an unclosed block")


def test_the_row_wraps_by_whole_groups_and_the_person_group_stays_at_the_right():
    row = rule(".ribbon-row")
    assert "display: flex" in row and "flex-wrap: wrap" in row
    # A wrapped group is on a row of its own, so it has to find the right-hand edge itself.
    assert "margin-left: auto" in rule(".ribbon-account")


def test_on_a_phone_the_actions_take_a_row_under_the_logo_the_chip_and_the_person_menu():
    phone = block(PHONE)
    account = rule(".ribbon-account", phone)
    actions = rule(".top-actions", phone)
    assert "column-gap: 0.6rem" in rule(".ribbon-row", phone)
    order = lambda declarations: int(re.search(r"order: (\d+)", declarations).group(1))   # noqa: E731
    assert order(account) < order(actions), "the actions must come after the person menu to take the second row"
    assert "flex: 1 0 100%" in actions, "a row of their own"
    assert "margin: 0" in actions, "under the logo, not indented by its desktop margins"


def test_only_a_phone_gives_the_actions_a_row_of_their_own():
    """Between 601px and 820px the bar fits one row (590px at its widest, measured), so only the phone block orders it."""
    assert len(re.findall(r"\.top-actions \{[^}]*order:", CSS)) == 1
    assert "order:" in rule(".top-actions", block(PHONE))
    assert "order:" not in rule(".top-actions"), "the desktop rule would order the actions too"


def test_the_squeeze_that_stood_a_name_on_end_cannot_come_back():
    """The name may shrink to nothing in a flex row; wrapping, not shrinking, is what protects it."""
    name = rule(".who-name")
    assert "overflow-wrap: anywhere" in name and "max-width: 16rem" in name
    assert "flex-wrap: wrap" in rule(".ribbon-row")
