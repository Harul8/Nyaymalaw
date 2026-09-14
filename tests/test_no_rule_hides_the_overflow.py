"""A STYLE RULE MAY NOT MAKE THE SIDEWAYS-SCROLL CHECK UNABLE TO FAIL.

BK-43, and it is CLAUDE.md §4 rather than a CSS defect.

`body, main { overflow-x: hidden }` looks like belt-and-braces and is the
opposite. The journey's width phase asks the page:

    document.documentElement.scrollWidth > document.documentElement.clientWidth

Clipping the overflow makes those two equal whatever the content does, so the
assertion can no longer fail. The page still has content off the right edge on
a phone and nothing will ever say so again -- a fix that disables its own test,
which is defect shape S11.

WHY A TEST AND NOT A COMMENT
----------------------------
There was already a comment. `frontend/app.css` carried, in full, an explanation of
why this rule had been written and removed -- and 518 lines above it the rule
was still live, in a second copy nobody had swept. The comment sat over a
disabled check for a week and the journey suite reported green throughout.

The question CLAUDE.md §4 asks is not "where is the other copy" but "what makes
a second copy impossible". Nothing did. This is that.

THE POPULATION IS EVERY STYLESHEET THE PRODUCT SERVES, not the one file the
rule was found in, and the subject is every DOCUMENT-LEVEL scroller: `html`,
`body`, and `main` -- the panes are `<main>` elements, so clipping there hides
the same overflow from the same measurement.

WHAT IS DELIBERATELY ALLOWED
----------------------------
`overflow` on an inner container is ordinary layout and is not touched: a
scrolling rail, a clipped avatar, a table in its own `overflow-x: auto` box are
all correct and none of them can flatten the document scroll width.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "frontend"

#: The selectors that ARE the document scroller. A rule whose subject is one of
#: these can flatten `documentElement.scrollWidth`; a rule on anything nested
#: cannot.
SCROLLERS = frozenset({"html", "body", "main", ":root", "*"})

#: Clipping values. `clip` is `hidden` without the scroll container, and it
#: flattens the measurement identically -- naming only `hidden` would leave the
#: obvious replacement open.
CLIPS = frozenset({"hidden", "clip"})

_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.S)
_DECL = re.compile(r"(?:^|;)\s*(overflow|overflow-x)\s*:\s*([a-z-]+)", re.I)


def _strip_comments(css: str) -> str:
    """Comments EXPLAIN the rule and must not COUNT as it.

    This file's whole reason for existing is a comment describing the rule,
    and a scan that read comments would report the explanation as the defect
    and be right for the wrong reason for ever after.
    """
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def hidden_overflow_on_a_scroller(css: str) -> list[str]:
    """Every declaration that clips sideways overflow on the document itself."""
    found: list[str] = []
    for selectors, body in _RULE.findall(_strip_comments(css)):
        subjects = {s.strip().lower() for s in selectors.split(",")}
        if not (subjects & SCROLLERS):
            continue
        for prop, value in _DECL.findall(body):
            if value.strip().lower() in CLIPS:
                found.append(
                    f"{', '.join(sorted(s for s in subjects if s))} "
                    f"{{ {prop.lower()}: {value.lower()} }}")
    return found


def _stylesheets() -> list[Path]:
    return sorted(WEB.rglob("*.css"))


def test_no_stylesheet_clips_the_document_scroll_width():
    """THE SWEEP. Every stylesheet the product serves, every document-level
    scroller, every clipping value."""
    sheets = _stylesheets()
    assert sheets, (
        "no stylesheet was found under frontend/, so this sweep read an empty "
        "population and would pass on any product at all")

    offenders: list[str] = []
    for sheet in sheets:
        for rule in hidden_overflow_on_a_scroller(
                sheet.read_text(encoding="utf-8")):
            offenders.append(f"{sheet.relative_to(ROOT)}: {rule}")

    assert not offenders, (
        "these rules clip sideways overflow on the document scroller, which "
        "makes `documentElement.scrollWidth > clientWidth` permanently false "
        "and the journey's width phase unable to fail:\n  "
        + "\n  ".join(offenders)
        + "\n\nThe page can still have content off the right edge; nothing "
          "will report it. Fix the overflowing element instead -- "
          "`overflow-wrap: anywhere` on the long locator, `max-width: 100%; "
          "min-width: 0` on its container.")


def test_the_overflow_scan_can_see_a_planted_rule():
    """THE POSITIVE CONTROL. A checker that always returns `[]` satisfies the
    sweep above identically -- B-049, on every commit for weeks.

    Both halves matter. The plants are the rule as it was actually written
    (`body, main`), the single-subject form, and the `clip` replacement that
    would otherwise be the obvious way around this test.
    """
    for planted in (
        "body, main { overflow-x: hidden; }",
        "body { overflow-x: hidden }",
        "main{overflow:clip}",
        "html { color: red; overflow-x: HIDDEN; }",
    ):
        assert hidden_overflow_on_a_scroller(planted), (
            f"the scan did not see {planted!r}, so it would not have caught "
            f"BK-43 and reports a clean product either way")


def test_the_overflow_scan_leaves_ordinary_containers_alone():
    """THE NEGATIVE CONTROL, and it is not optional here.

    A scan that flagged every `overflow: hidden` would be unusable, get
    suppressed, and this rule would come back for the third time. Clipping an
    inner box cannot flatten the document scroll width and is correct layout.
    """
    for allowed in (
        "#rail { overflow-y: auto; overflow-x: hidden; }",
        ".avatar { overflow: hidden; border-radius: 50%; }",
        ".wide-table { overflow-x: auto; }",
        "body { overflow-x: auto; }",
        "main { overflow-x: visible; }",
    ):
        assert not hidden_overflow_on_a_scroller(allowed), (
            f"the scan flagged {allowed!r}, which is ordinary layout -- a "
            f"sweep that cries wolf is one that gets turned off")


def test_the_scan_reads_rules_and_not_the_comments_explaining_them():
    """`frontend/app.css` documents this rule in prose, twice, deliberately.

    A scan that matched comment text would report those paragraphs as
    offenders, and the only way to a green build would be to DELETE THE
    EXPLANATION -- turning a test that protects the reasoning into one that
    destroys it.
    """
    commented = """
    /* `body, main { overflow-x: hidden }` WAS HERE AND WAS REMOVED, because
       it makes overflow-x: hidden on body impossible to detect. */
    .el .body { overflow-wrap: anywhere; }
    """
    assert not hidden_overflow_on_a_scroller(commented), (
        "the scan read a comment as a rule, so keeping the explanation of "
        "BK-43 in the stylesheet would fail the build")
