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

TWO HALVES, AND THE SECOND ONE RUNS THE CODE
----------------------------------------------
The checks that read `web/app.js` as TEXT are structural: they hold if the
partition is right and the rendering then does something else with the result.
They are cheap, they name the exact predicate, and they are not sufficient.

So the last test in this file EXECUTES `renderTurn` --
`tests/js/render_turn_partition.mjs`, under plain `node`, against a forty-line
stub DOM -- and walks the tree it builds. That answers the question the
advocate cares about, which no reading of the source can: is a disclosure ever
inside a collapsed `<details>`?

**No npm install.** jsdom to hold one rule is R-6 apparatus -- a check that
needs a toolchain nobody maintains is a check that stops running. And when
`node` is absent the test says NOT ASSESSED in those words rather than
passing, because a test that quietly returns when its tooling is missing is
the shape of every silent gap in this register.

The screen was ALSO driven through a real browser when it was built --
`details.support .el.disclosure` returned 0 and `.turn > .el.disclosure`
returned 2 on a two-disclosure turn. That measurement is what the `.mjs`
encodes rather than replaces.
"""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


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


# ============ BK-12 — the same rule, asserted BEHAVIOURALLY ================

def test_the_rendered_turn_puts_no_disclosure_inside_a_fold():
    """THE STRUCTURAL CHECKS ABOVE READ THE SOURCE. This runs it.

    Every assertion before this one reads the partition's predicate out of
    `web/app.js`. That is real and it is structural: it holds if the filter is
    correct and the rendering then does something else with the result — puts
    the disclosures in the fold by a different route, or drops them.

    `tests/js/render_turn_partition.mjs` executes the ACTUAL `renderTurn`
    against a forty-line stub DOM and walks the tree it builds, asking the
    question the advocate cares about: is a disclosure ever inside a
    collapsed `<details>`?

    NO npm INSTALL. jsdom to hold one rule is R-6 apparatus — a check that
    needs a toolchain nobody maintains is a check that stops running.

    THREE STATES, because node may not be here. A missing runtime is NOT
    ASSESSED, said in those words and skipped; it is not a pass. §9 is about
    exactly this, and a test that quietly returns when its tooling is absent
    is the shape of every silent gap in this register.
    """
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip(
            "NOT ASSESSED: node is not on PATH, so the behavioural half of "
            "this rule did not run. The structural checks above still hold. "
            "This is a third state, not a pass.")

    script = ROOT / "tests" / "js" / "render_turn_partition.mjs"
    result = subprocess.run([node, str(script)], capture_output=True,
                            text=True, cwd=ROOT)
    assert result.returncode == 0, (
        "the rendered turn breaks the disclosure rule:\n"
        + result.stdout + result.stderr)
