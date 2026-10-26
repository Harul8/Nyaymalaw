"""Load more under the conversation history is styled (plan AN.23; owner decision O29): a touch-sized button, a quiet
line saying how many are shown, and a rule for every class the page script builds for them. Reads the shipped sheet
and script; the owner's browser shows how it looks."""
from __future__ import annotations

import re

import pytest

from nm.shared.source_layout import browser_assets

pytestmark = pytest.mark.class_a

CSS = re.sub(r"/\*.*?\*/", " ", browser_assets()["app.css"].read_text(encoding="utf-8"), flags=re.S)
SCRIPT = browser_assets()["app.js"].read_text(encoding="utf-8")


def rule(selector: str) -> str:
    found = re.findall(r"(?:^|[{}])\s*" + re.escape(selector) + r"\s*\{([^{}]*)\}", CSS)
    assert len(found) == 1, f"{selector}: {len(found)} rules"
    return " ".join(found[0].split())


def test_the_button_is_a_touch_target_in_the_brand_colour_and_can_be_switched_off():
    button = rule(".rail-more-button")
    assert "min-height: 44px" in button and "border: 1px solid var(--accent)" in button
    assert "cursor: pointer" in button
    assert "opacity" in rule(".rail-more-button:disabled"), "a button that is waiting must look it"
    assert ":hover:not(:disabled)" in CSS and ".rail-more-button:hover:not(:disabled)" in CSS


def test_the_line_and_the_button_share_a_row_and_wrap_on_a_phone_instead_of_running_off_it():
    row = rule(".rail-more")
    assert "display: flex" in row and "flex-wrap: wrap" in row and "justify-content: space-between" in row
    assert "margin: 0" in rule(".rail-more > p")


def test_every_class_the_script_builds_for_load_more_has_a_rule():
    more = SCRIPT[SCRIPT.index("function offerMoreHistory("):SCRIPT.index("async function loadMatterList(")]
    built = set(re.findall(r"className = '([^']+)'", more))
    assert {"rail-more", "rail-more-button", "hint"} <= built, built
    declared = set(re.findall(r"\.([A-Za-z][\w-]*)", CSS))
    assert not sorted(built - declared), sorted(built - declared)
