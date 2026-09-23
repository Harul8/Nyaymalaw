"""AN ACT IS NOT MADE ONLY OF SECTIONS.

THE MEASURED DEFECT, 23 September 2026, on a live multi-dispute matter. The
answer served this as the authority it rested on:

    Limitation Act, 1963 s.Article_64 — "For possession of immovable property
    based on previous possession"

`s.Article_64`. Four sites in `nm.adapters.evidence.corpus` built the reference
as `f"{act} s.{section}"`, hard-coding the prefix for every provision — and the
corpus's `section_number` column holds `Article_64` for a schedule article
exactly as it holds `53A` for a section. It also holds the storage underscore,
which is not how anyone writes a citation.

WHY THAT IS SERIOUS AND NOT COSMETIC. The citation line exists so the advocate
can go and read the source themselves; that is the whole mechanism by which a
wrong authority is caught. A citation in a form that does not exist cannot be
looked up, and an advocate who cannot check stops checking.

THE RULE: THE PREFIX BELONGS TO THE UNIT'S KIND, NOT TO THE RENDERER. The
Limitation Act's periods are Schedule Articles, the CPC's procedure is Orders
and Rules, a constitution is Articles throughout. A unit that NAMES its own
kind is rendered as it names itself; only a bare designation — `53A`, `138` —
is a section and takes `s.`.

OWNED BY `nm.domain.citation`, because CLAUDE.md section 4 puts every
provision-reference pattern in that module and `test_citation_patterns.py`
fails the build on a second one. `SECTION` and `ARTICLE` there already know the
two are different; a renderer elsewhere that did not would be that second
definition wearing a different hat.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from nm.domain.citation import provision_label

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_a_unit_that_names_its_own_kind_is_not_called_a_section():
    """THE REGRESSION, on the value that produced it."""
    assert provision_label("Limitation Act, 1963", "Article_64") == \
        "Limitation Act, 1963 Article 64"
    assert "s.Article" not in provision_label("Limitation Act, 1963", "Article_64")


def test_a_bare_designation_is_a_section():
    """THE OTHER HALF. A rule that also refuses the correct shape is a rule
    somebody deletes the first time it is in the way — every ordinary section
    must still read as one."""
    assert provision_label("Transfer of Property Act, 1882", "53A") == \
        "Transfer of Property Act, 1882 s.53A"
    assert provision_label("Negotiable Instruments Act, 1881", "138") == \
        "Negotiable Instruments Act, 1881 s.138"


def test_every_kind_the_corpus_can_hold_is_rendered_as_it_is_written():
    """THE POPULATION OF KINDS, not the one that was hit.

    `Article` is what a live matter happened to surface. An Act's units are
    also Orders, Rules, Schedules, Clauses and Parts, and each would have come
    out as `s.<kind>` on the day a brief reached it.
    """
    for unit, expected in (
        ("Article 65", "Article 65"),
        ("Order VII Rule 11", "Order VII Rule 11"),
        ("schedule I", "Schedule I"),
        ("Rule 3", "Rule 3"),
        ("clause (b)", "Clause (b)"),
        ("Part V", "Part V"),
    ):
        got = provision_label("Some Act, 1963", unit)
        assert got == f"Some Act, 1963 {expected}", (
            f"{unit!r} rendered as {got!r}; a unit that names its kind is "
            f"cited as it names itself")


def test_the_storage_underscore_never_reaches_a_citation():
    """An atom id is storage. No one writes `Article_64` in a citation, and a
    reference an advocate cannot paste into a search is a reference they
    cannot check."""
    assert "_" not in provision_label("Limitation Act, 1963", "Article_64")
    assert "_" not in provision_label("Code of Civil Procedure, 1908",
                                      "Order_VII_Rule_11")


def test_nothing_else_in_the_package_builds_a_provision_reference():
    """THE SWEEP, drawn from the source.

    The four sites were not written by anyone ignoring a rule — `s.` is what
    you reach for when you have an Act and a number, and there was nowhere to
    find the answer. This fails the build on the fifth.
    """
    #: THE OWNER IS WHERE THE PREFIX IS ALLOWED TO EXIST. `provision_label`
    #: builds `s.<unit>` for the bare designations that really are sections --
    #: that is the whole job. Exempting it is the same line `test_one_fold.py`
    #: draws around `nm.domain.text.fold`: the rule is ONE definition, not
    #: none.
    OWNER = "backend/nm/domain/citation.py"

    found: list[str] = []
    for path in sorted((ROOT / "backend" / "nm").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel == OWNER:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf8"))
        except SyntaxError:                      # pragma: no cover -- defensive
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.JoinedStr):
                continue
            rendered = ast.unparse(node)
            # `... s.{<anything>}` -- an interpolated designation given the
            # section prefix by the caller rather than by the unit's kind.
            if " s.{" in rendered:
                found.append(f"{rel}:{node.lineno}  {rendered[:90]}")

    assert not found, (
        "A provision reference is built with a hard-coded `s.` prefix. The "
        "prefix belongs to the unit's KIND -- an Act is not made only of "
        "sections, and `s.Article_64` was served to an advocate as the "
        "authority an answer rested on.\n\n"
        "Use `nm.domain.citation.provision_label`:\n  " + "\n  ".join(found))
