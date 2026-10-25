"""The answer runs the full width of its column (owner decision P50, 25 Oct 2026; plan AN.10).

P45 set the answer's paragraphs to 33em and three of its boxes had widths of their own, so the
text ended well short of the window's edge while the headings and tables ran to it. The owner
chose the whole window. This reads the served stylesheet and refuses any rule that gives an
element of the answer a width of its own; it does not draw the page, which the owner's browser
shows.

P50 AMENDED (owner, O22 item 5, 25 Oct 2026; plan AN.13): "keep it at full 80% width, with 10%
left on left and right sides". The answer still has no width of its own; the one side margin the
answer and the message box share is 10% of the conversation's column, and 1rem on a phone.
"""
from __future__ import annotations

import re

import pytest

from nm.shared.source_layout import browser_assets

pytestmark = pytest.mark.class_a

#: What the answer is made of: its units, the boxes that hold them, its folds, tables and checks.
#: The advocate's own messages (.brief) and the message box are not part of it.
ANSWER = re.compile(
    r"(?<![\w-])\.(turn|el|in-short[\w-]*|answer-[\w-]+|more-fold|need[\w-]*|checked-[\w-]+|fallback-list"
    r"|shown-so-far[\w-]*|time-limit[\w-]*|working[\w-]*)(?![\w-])")
#: Values that follow the column rather than cap it.
FOLLOWS_THE_COLUMN = {"100%", "none", "auto", "inherit", "initial", "unset"}
WIDTHS = ("max-width", "max-inline-size", "width", "inline-size")


def capped_rules(css: str) -> list[str]:
    """Each rule that gives an element of the answer a width of its own, as it is written."""
    css = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    found = []
    # Innermost blocks only: a media query's own condition is never read as a rule.
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        selector = " ".join(selector.split())
        if not ANSWER.search(selector):
            continue
        for declaration in body.split(";"):
            name, _, value = declaration.partition(":")
            name, value = name.strip().lower(), " ".join(value.split()).lower()
            if name in WIDTHS and value not in FOLLOWS_THE_COLUMN:
                found.append(f"{selector} {{ {name}: {value} }}")
    return found


def test_no_rule_of_the_served_stylesheet_caps_the_width_of_the_answer():
    sheets = sorted({path for path in browser_assets().values() if path.suffix == ".css"})
    assert sheets, "the served stylesheet must not disappear"
    found = [rule for sheet in sheets for rule in capped_rules(sheet.read_text(encoding="utf-8"))]
    assert not found, "the answer runs the column's full width (P50), but these cap it: " + "; ".join(found)


def _rule(css: str, selector: str) -> str:
    found = re.search(r"(?:^|\})\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    return found.group(1) if found else ""


def test_the_answer_and_the_message_box_keep_a_tenth_of_the_column_on_each_side():
    """P50 amended (O22 item 5): one shared side margin, a tenth of the column, on every part that
    lines up with the answer - the thread, the message box, the draft's status and the matter's title."""
    css = re.sub(r"/\*.*?\*/", " ", browser_assets()["app.css"].read_text(encoding="utf-8"), flags=re.S)
    assert "--talk-gutter: 10%" in _rule(css, ".conversation"), "the conversation's side margin is not 10%"
    for selector in (".thread", ".composer", ".draft-status", ".workspace-heading"):
        assert "var(--talk-gutter" in _rule(css, selector), f"{selector} no longer keeps the shared margin"
    assert ".conversation { --talk-gutter: 1rem; }" in css, "a phone no longer keeps its narrow margin"


@pytest.mark.parametrize("rule", [
    ".thread .turn .el .body { max-width: 33em; }",
    ".thread .turn .in-short { max-width: 60rem; }",
    ".more-fold { padding: 0.4rem; max-width: 36rem; }",
    ".checked-list { max-width: 33em }",
    "@media (min-width: 900px) { .thread .shown-so-far p { max-width: 70ch; } }",
    ".turn .el .body { width: 640px; }"])
def test_a_width_cap_on_an_element_of_the_answer_is_found(rule):
    assert capped_rules(rule)


@pytest.mark.parametrize("rule", [
    "#thread, .el { max-width: 100%; min-width: 0; }",
    ".in-short-table { width: 100%; }",
    ".in-short-dispute { min-width: 8rem; }",
    ".brief { max-width: 84%; }",
    "@media (max-width: 820px) { .turn { margin: 0; } }"])
def test_what_follows_the_column_or_is_not_the_answer_is_not_a_cap(rule):
    assert not capped_rules(rule)
