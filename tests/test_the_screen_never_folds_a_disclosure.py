"""A DISCLOSURE MUST NOT BE FOLDED AWAY, whatever the screen looks like.

The advise pane was redesigned on 7 September 2026 to read as a conversation:
the advocate's own words as a bubble, the answer as prose, and the supporting
material collapsed behind a row that opens in one click. That last part is what
this file exists to bound.

**B-128 WAS EXACTLY THIS DEFECT, THREE DAYS OLD WHEN THE SCREEN CHANGED.**
`nm/core/screens.py` fired `G-UNSCREENED` into the metrics and the advocate saw
nothing; the fix put five screen rows into the answer's bytes. A redesign that
folds `disclosure` elements by default undoes it at the last inch -- the bytes
are served, and the advocate still cannot see them. §9 says the third state
must be visible in the OUTPUT, and behind a triangle is *available*, which is a
different word.

WHY THIS IS A PYTHON TEST OVER JAVASCRIPT SOURCE
--------------------------------------------------
There is no JS test runner in this repo and adding one to hold a single rule
would be apparatus that runs when someone has time -- R-6 in the project plan.
What this asserts is structural and reads perfectly well from the source: the
partition that decides what folds. If a JS runner ever lands, this moves; until
then the rule is checked rather than remembered.

The screen was ALSO driven and read back through the DOM when it was built --
`details.support .el.disclosure` returned 0 and `.turn > .el.disclosure`
returned 2 on a two-disclosure turn. That measurement is what this encodes.
"""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.class_a

WEB = pathlib.Path(__file__).resolve().parents[1] / "web"


def _app_js() -> str:
    return (WEB / "app.js").read_text(encoding="utf-8")


def test_only_plain_ground_is_ever_folded():
    """THE PARTITION, read off the source.

    `support` is what folds. Its filter must require BOTH that the element is
    ground AND that it carries no disclosure -- dropping the second clause is
    the whole defect, and it is a two-character edit.
    """
    src = _app_js()

    m = re.search(r"const support = entry\.answer\.elements\.filter\(\s*"
                  r"\(el\) => ([^;]+)\);", src)
    assert m, ("the `support` partition is gone or renamed; whatever decides "
               "what folds is now unchecked")

    predicate = " ".join(m.group(1).split())
    assert "el.kind === 'ground'" in predicate, (
        f"the fold no longer restricts itself to ground elements, so an "
        f"ACTION could be collapsed: {predicate}")
    assert "!el.disclosure" in predicate, (
        f"THE FOLD NO LONGER EXCLUDES DISCLOSURES: {predicate}\n\n"
        f"A disclosure behind a collapsed row is B-128 at the last inch -- "
        f"the bytes are served and the advocate still cannot see them.")


def test_the_spoken_half_is_the_complement_and_not_a_second_list():
    """§4: what refuses the second copy?

    `spoken` and `support` must partition the same array by the SAME
    predicate, negated. Two independently written filters are two places for
    an element kind to fall through, and an element in neither list is
    rendered nowhere -- silently, because nothing counts them.
    """
    src = _app_js()
    m = re.search(r"const spoken = entry\.answer\.elements\.filter\(\s*"
                  r"\(el\) => ([^;]+)\);", src)
    assert m, "the `spoken` partition is gone or renamed"

    spoken = " ".join(m.group(1).split())
    assert spoken.startswith("!("), (
        f"`spoken` is not the negation of `support`'s predicate but a second "
        f"list of its own: {spoken}. An element kind added tomorrow can fall "
        f"between them and render nowhere at all.")
    assert "el.kind === 'ground'" in spoken and "!el.disclosure" in spoken


def test_the_fold_says_how_much_is_inside_it():
    """`left_out` is the precedent in this product: a reader told something is
    hidden learns less than a reader told how much. A bare "details" gives no
    reason to open it, so it is never opened."""
    src = _app_js()
    assert "supporting passage" in src, (
        "the fold no longer labels itself with a count")
    assert "support.length === 1" in src, (
        "one passage is labelled 'passages'; a plural on a count of one reads "
        "as a template that nobody finished")


def test_the_advocates_own_words_are_still_marked_as_theirs():
    """Everything else on the screen is something this product wrote. An
    advocate scanning back through a long matter must be able to find what THEY
    said without reading it -- which is what the bubble is for, and it is the
    one thing a chat layout must not lose."""
    src = _app_js()
    assert "said-row" in src, "the advocate's own words are no longer set apart"

    css = (WEB / "app.css").read_text(encoding="utf-8")
    assert ".said-row" in css and "justify-content: flex-end" in css, (
        "the bubble has no styling, so the advocate's words render as another "
        "paragraph of the product's prose")


def test_a_disclosure_still_looks_different_from_an_assertion():
    """The rule that predates the redesign and survives it. "Here is the law"
    and "here is what I could not establish" rendered identically is how a gap
    becomes a finding in the reader's memory."""
    css = (WEB / "app.css").read_text(encoding="utf-8")
    assert ".el.disclosure" in css
    assert "border-left-style: dashed" in css, (
        "a disclosure is no longer visually distinct from an assertion")
