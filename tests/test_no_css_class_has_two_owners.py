"""ONE CLASS NAME, ONE MEANING. What refuses the second owner in a stylesheet.

THE DEFECT, FOUND BY THE BK-30 BROWSER HARNESS ON ITS FIRST REAL RUN
----------------------------------------------------------------------
`frontend/app.css` defined `.gate` twice, for two unrelated things:

    line 231   a GATE FIRING inside an answer -- `G-COVERAGE · disclose · …`,
               a small inline row in the conversation;
    line 537   THE SIGN-IN GATE -- `position: fixed; inset: 0;
               background: var(--paper); z-index: 100`.

The second is later in the cascade, so it won. Every gate firing rendered in
an answer became a full-screen opaque overlay above everything. An advocate
who submitted a brief was shown A BLANK WHITE PAGE carrying one centred line:
`G-EXPOSURE · none_found · 0 exposure(s)`. The advice, the citations, the
limitation position and the open questions were all painted over, and the tab
bar beneath could not be clicked -- Playwright reported the click intercepted
by `<div class="gate disclose">`.

EVERY TEST IN THIS REPOSITORY PASSED. The served JSON was correct. The engine
was correct. `test_the_page_and_the_script_agree.py` checks that the script
and the page agree about element NAMES and says in its own docstring that it
does not run the page. So the product produced a right answer nobody could
read, which is this repository's founding failure written in a stylesheet:
two correct components and the defect living in the gap.

WHY THIS TEST AND NOT "BE CAREFUL WITH CLASS NAMES"
-----------------------------------------------------
CLAUDE.md §4 asks the question this file is the answer to: not *where is the
other copy* but *what makes a second copy impossible?* The same question was
answered for provision-reference patterns by `tests/test_citation_patterns.py`
-- `backend/nm/domain/citation.py` is the only module permitted to define one, and a
scan fails the build on a second.

This is that rule for the stylesheet. A class may be declared in one place.
Adding a modifier (`.gate.disclose`), a descendant (`.gate .gid`) or a
responsive override inside a media query is not a second declaration -- those
refine an existing owner rather than competing with it. A second BARE
declaration at the top level is, and it is the shape that bit.

THE EXEMPTIONS ARE DECLARED, WITH THEIR REASON
------------------------------------------------
A stylesheet legitimately declares some things twice, and a check with no way
to say so is a check people delete. `EXEMPT` carries the name and why -- the
arrangement `UNWIRED`, `RESERVED` and `STRUCTURED_ONLY` all use here.
"""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.class_a

WEB = pathlib.Path(__file__).resolve().parents[1] / "frontend"

#: Class names allowed more than one bare declaration, and why. Empty today,
#: and that is the point of writing it down: the first entry has to carry a
#: reason somebody can disagree with.
EXEMPT: dict[str, str] = {}

#: A selector that is EXACTLY one bare class -- `.gate`, and not
#: `.gate.disclose`, `.gate .gid`, `a.gate`, `.turn .gate` or
#: `.conversation, .thread, .turn`. Anchored at both ends so a refinement is
#: never counted as a competing owner.
BARE_CLASS = re.compile(r"^\.([A-Za-z][\w-]*)$")


def _strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", " ", css, flags=re.S)


def declarations(css: str) -> dict[str, list[str]]:
    """Bare class declarations, by name, TOP LEVEL ONLY.

    Media-query bodies are skipped deliberately: `@media (max-width: 820px)
    { .rail { display: none } }` is the same owner saying what happens at a
    narrower width, and counting it would make every responsive rule look
    like a collision -- a check that fires on correct code is one that gets
    switched off.
    """
    css = _strip_comments(css)
    found: dict[str, list[str]] = {}
    depth = 0
    at_rule_depth: list[int] = []
    buf = ""
    for ch in css:
        if ch == "{":
            selector = " ".join(buf.split())
            buf = ""
            depth += 1
            if selector.startswith("@"):
                at_rule_depth.append(depth)
                continue
            if at_rule_depth:
                continue
            # THE WHOLE SELECTOR, NOT A MEMBER OF A GROUP.
            #
            # `.conversation, .thread, .turn { min-width: 0 }` gives three
            # classes one shared property; it does not claim ownership of any
            # of them, and it names every class it touches on the same line
            # where anyone can see it. Counting group membership reported six
            # collisions in this stylesheet on the first run, all of them
            # correct code -- and a check that fires on correct code is one
            # that gets switched off, which would have cost the real find.
            #
            # What bit was two SOLO declarations three hundred lines apart,
            # each looking like the only one.
            m = BARE_CLASS.match(selector)
            if m:
                found.setdefault(m.group(1), []).append(selector)
        elif ch == "}":
            if at_rule_depth and at_rule_depth[-1] == depth:
                at_rule_depth.pop()
            depth -= 1
            buf = ""
        else:
            buf += ch
    return found


def stylesheets() -> list[pathlib.Path]:
    return sorted(WEB.rglob("*.css"))


# ==================================================================== the rule ==

def test_no_class_is_declared_twice_at_the_top_level():
    """THE RULE. A class name has one owner, or the later one silently wins."""
    offenders: list[str] = []
    for path in stylesheets():
        for name, selectors in declarations(
                path.read_text(encoding="utf-8")).items():
            if len(selectors) > 1 and name not in EXEMPT:
                offenders.append(
                    f"{path.name}: .{name} is declared {len(selectors)} times "
                    f"({', '.join(selectors)})")

    assert not offenders, (
        "these class names have more than one owner, and the LAST one wins "
        "wherever they disagree. `.gate` meant a gate firing in an answer and "
        "also the full-screen sign-in overlay, and every answer element "
        "quietly became a `position:fixed; inset:0; z-index:100` box that "
        "painted over the whole application:\n  " + "\n  ".join(offenders)
        + "\n\nRename one, address it by its id, or add it to EXEMPT above "
          "with the reason it may be declared twice.")


def test_the_sign_in_gate_is_addressed_by_its_id():
    """THE SPECIFIC HALF, kept because the general rule above would also pass
    if somebody re-collided `.gate` and added it to EXEMPT without reading
    what it costs. The overlay is ONE element; it has an id; it uses it."""
    css = _strip_comments((WEB / "app.css").read_text(encoding="utf-8"))
    html = (WEB / "index.html").read_text(encoding="utf-8")

    assert re.search(r"(^|\})\s*#gate\s*\{", css), (
        "the sign-in overlay is no longer addressed by its id")
    assert 'class="gate"' not in html, (
        "the sign-in element claims the `.gate` class again, so the "
        "gate-firing rule applies to it and vice versa")

    overlay = re.search(r"#gate\s*\{([^}]*)\}", css)
    assert overlay and "position: fixed" in overlay.group(1), (
        "the sign-in gate no longer covers the application; if the board can "
        "paint over it, the gate is decoration")


# ============================================================ positive controls ==

def test_the_scan_finds_the_classes_that_are_there():
    """A control on the PARSER. A `declarations()` that returned nothing would
    pass the rule while reading nothing, which is exactly how the defect it
    was written for survived every check in this repository."""
    found = declarations((WEB / "app.css").read_text(encoding="utf-8"))
    assert len(found) > 20, f"the scan found almost no classes: {sorted(found)}"
    assert "gate" in found, "the class this test exists for is not seen at all"
    assert len(found["gate"]) == 1, (
        f"`.gate` has more than one owner again: {found['gate']}")


def test_the_scan_sees_a_planted_collision():
    """A control on the RULE, on the shape that actually bit -- a second bare
    declaration far from the first, with unrelated properties."""
    planted = """
    .thing, .other-thing { min-width: 0; }
    .thing { color: red; }
    .thing.modifier { color: blue; }
    .thing .child { color: green; }
    @media (max-width: 820px) { .thing { display: none; } }
    .other { color: black; }
    .thing { position: fixed; inset: 0; z-index: 100; }
    """
    found = declarations(planted)
    assert len(found["thing"]) == 2, (
        f"the scan did not see the collision it was shown: {found}")
    assert len(found["other"]) == 1
    assert "modifier" not in found, "a modifier was counted as an owner"
    assert "child" not in found, "a descendant was counted as an owner"
    assert "other-thing" not in found, (
        "a shared property in a grouped selector was counted as an ownership "
        "claim -- that reported six collisions in this stylesheet, all of "
        "them correct code")
