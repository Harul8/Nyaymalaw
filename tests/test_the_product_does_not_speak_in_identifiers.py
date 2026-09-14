"""BK-13 — an enum reaches the advocate through a phrase it owns.

WHAT WAS ON THE PAGE, measured 7 September 2026 when the advocate asked why
the product sounded like a form rather than a colleague:

    {i.statement} [{i.kind.value}; runs against {i.runs_against.value}; ...]
    {pos.element} [burden {whose}; {elements.standard.value}; {detail}]
    {item.what} — held by {item.holder.value}, {item.form.value}

So an advocate read `balance_of_probabilities`, `certified_copy`,
`third_party`, `not_assessed`. Those are identifiers, and `held_not_found` is
worse than an identifier -- it is this product's private word for a retrieval
DEFECT, and the one place it must never appear is in front of the person it
was invented to protect.

WHAT THIS IS AND IS NOT
-------------------------
It is NOT "make the product conversational". The element kinds are
load-bearing: `Answer.__post_init__` refuses an answer that leads with
background, the gate matrix hangs off `disclosure`, and B-128 -- five days
before this -- was exactly a disclosure the advocate could not see. The
previous build produced advice that read beautifully and hid what it could not
establish. That is the failure mode of dissolving structure into prose.

It IS: better sentences inside that structure, and one mechanism that makes
the identifier version impossible rather than merely absent today.

`backend/nm/domain/spoken.py` holds it. The phrases live ON the enum, and `complete()`
asserts every member has one at import -- so a member added without a phrase
is an ImportError, not a surprise in a served turn. There is no fallback to
`.value`: a fallback is what makes a missing phrase invisible.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The one `.value` that may reach an advocate, and why.
#:
#: `cascade.Derived.value` is a `str` -- the VALUE of a derived quantity, such
#: as a limitation date -- not an enum member. "limitation was 2027-04-15 and
#: is not computed now" is already English. Rewriting it would be changing a
#: line because a scan matched it, which is the opposite of drawing the
#: population from the code.
ALLOWED = {("backend/nm/core/turn.py", "d.value")}


def _sources():
    return [p for p in (ROOT / "backend" / "nm").rglob("*.py")
            if "__pycache__" not in p.parts]


def test_no_enum_value_reaches_the_advocate():
    """THE SWEEP, and its population is every `Element` in the product rather
    than the four that were found by eye."""
    offenders = []
    for path in _sources():
        src = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError:                      # a probe module mid-write
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "Element"):
                continue
            kw = {k.arg: k.value for k in node.keywords}
            if "text" not in kw:
                continue
            text = ast.get_source_segment(src, kw["text"]) or ""
            rel = path.relative_to(ROOT).as_posix()
            for attr in _value_reads(text):
                if (rel, attr) in ALLOWED:
                    continue
                offenders.append(f"{rel}:{node.lineno} — {attr}")

    assert not offenders, (
        "these put a raw `.value` in front of the advocate:\n  "
        + "\n  ".join(offenders)
        + "\n\nUse `.said`. An enum value is an identifier -- "
          "`balance_of_probabilities`, `held_not_found` -- and the advocate "
          "is the one person who cannot be expected to read this product's "
          "internal vocabulary.")


def _value_reads(text: str) -> list[str]:
    """Every `x.value` in a fragment, as `x.value`."""
    out = []
    for i, _ in enumerate(text.split(".value")):
        if i == 0:
            continue
        stem = text.split(".value")[i - 1]
        name = stem.rsplit("{", 1)[-1].rsplit(" ", 1)[-1].rsplit("(", 1)[-1]
        out.append(f"{name}.value")
    return out


def _lazy_phrases(enums, reads_as_itself: set[str]) -> list[str]:
    """Return phrases that merely remove underscores from identifiers."""
    lazy: list[str] = []
    for enum in enums:
        for member in enum:
            name = f"{enum.__name__}.{member.name}"
            if name in reads_as_itself:
                continue
            if (member.said == member.value.replace("_", " ")
                    and "_" in member.value):
                lazy.append(name)
    return lazy


def test_every_spoken_enum_called_complete():
    """A CHECK SOMEBODY MUST REMEMBER TO INVOKE IS THE ARRANGEMENT THIS
    REPLACED.

    `complete()` is what turns a missing phrase into an ImportError, and it
    cannot live in `__init_subclass__` because that runs before the members
    exist. So it is called by hand -- and a hand-called check needs a check.
    """
    missing = []
    for path in _sources():
        src = path.read_text(encoding="utf-8")
        if "Spoken" not in src:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not any(isinstance(b, ast.Name) and b.id == "Spoken"
                       for b in node.bases):
                continue
            if f"{node.name}.complete()" not in src:
                missing.append(
                    f"{path.relative_to(ROOT).as_posix()}::{node.name}")

    assert not missing, (
        "these enums are Spoken and never call `complete()`, so a member "
        "added without a phrase raises KeyError on a served turn instead of "
        "failing at import:\n  " + "\n  ".join(missing))


def test_a_missing_phrase_is_an_import_error_and_not_a_transcript():
    """THE POSITIVE CONTROL. A check that has never failed is S11.

    `ValueError` AND NOT `AssertionError` since BK-17. `complete()` asserted,
    and `python -O` deletes an assert -- which would have made it a no-op and
    moved the failure to a `KeyError` from `said` mid-turn, the exact outcome
    its docstring promised to prevent. The type in this test is the evidence
    that the guard is a statement rather than a debug aid.
    """
    from enum import Enum, nonmember

    from nm.domain.spoken import Spoken

    class _Gappy(Spoken, str, Enum):
        FINE = "fine"
        FORGOTTEN = "forgotten"
        SAID = nonmember({"fine": "fine"})

    with pytest.raises(ValueError, match="forgotten"):
        _Gappy.complete()

    class _Stale(Spoken, str, Enum):
        ONLY = "only"
        SAID = nonmember({"only": "only", "deleted": "a member that went"})

    with pytest.raises(ValueError, match="deleted"):
        _Stale.complete()


def test_said_has_no_fallback_to_the_value():
    """A fallback is what makes a missing phrase invisible: the member renders
    as its own identifier and the build stays green, which is the failure
    being removed rather than a safety net."""
    import inspect

    from nm.domain.spoken import Spoken

    src = inspect.getsource(Spoken.said.fget)

    # `self.value` IS in there -- it is the key. The first version of this
    # test asserted its absence and failed on the lookup it exists to
    # require, which is the difference between checking a rule and checking
    # a string.
    assert "self.SAID[self.value]" in src, (
        "`said` no longer looks the phrase up by value")
    for escape in ("or self.value", ".get(", "except", "getattr"):
        assert escape not in src, (
            f"`said` carries {escape!r}, so a missing phrase renders as an "
            f"identifier or is swallowed. `complete()` is what makes the "
            f"KeyError unreachable; softening it here makes `complete()` "
            f"optional and the phrase table advisory.")


def test_the_phrases_are_not_the_identifiers_with_the_underscores_removed():
    """A phrase that is the value with its underscores swapped for spaces is
    the same identifier wearing a coat. `balance of probabilities` needs the
    `on the` an advocate would actually write."""
    from nm.core.evidence_item import Form, Holder
    from nm.domain.issue import Effect, IssueKind
    from nm.domain.matter import Side
    from nm.domain.proof import Standard
    from nm.ports.evidence import Binding

    # THE ONE MEMBER WHOSE IDENTIFIER IS ALREADY THE ENGLISH, declared
    # rather than special-cased in the rule. "beyond reasonable doubt" is
    # exactly the phrase an advocate writes, and a check that could not say
    # so would be one people learn to edit rather than obey.
    reads_as_itself = {"Standard.BEYOND_REASONABLE_DOUBT"}

    lazy = _lazy_phrases(
        (Holder, Form, Standard, IssueKind, Effect, Side, Binding),
        reads_as_itself,
    )
    assert not lazy, (
        "these phrases are the identifier with the underscores taken out, "
        "which reads as an identifier to everyone except the person who "
        f"wrote it: {lazy}. `balance of probabilities` is the value; `on the "
        f"balance of probabilities` is the sentence.")


# ==================== the positive controls ==============================
#
# `test_every_sweep_has_a_positive_control` caught both of the sweeps above
# the moment they landed. A checker that always returns [] passes a sweep
# identically -- and one of them did, on every commit for weeks (B-049).
#
# The offender is planted in a REAL file under `backend/nm/`, because both scanners
# walk the tree. A synthetic fixture would prove the scanner compiles, not
# that it can see.

def test_the_value_scan_can_see_an_identifier_reaching_the_advocate():
    """Plant an Element whose text renders a raw enum value."""
    planted = ROOT / "backend" / "nm" / "core" / "_speaks_in_identifiers.py"
    planted.write_text(block_of((
        "from nm.domain.answer import Element, ElementKind",
        "from nm.domain.matter import Side",
        "",
        "def _leak(side: Side):",
        "    return Element(kind=ElementKind.GROUND,",
        "                   text=f\"the side is {side.value}\")",
    )), encoding="utf8")
    try:
        with pytest.raises(AssertionError, match="side.value"):
            test_no_enum_value_reaches_the_advocate()
    finally:
        planted.unlink()


def test_the_phrase_sweep_can_see_underscores_merely_removed():
    """BK-52. Plant the exact lazy-phrase relation the sweep rejects."""
    from enum import Enum, nonmember

    from nm.domain.spoken import Spoken

    class PlantedPhrase(Spoken, str, Enum):
        INTERNAL_WORDS = "internal_words"
        SAID = nonmember({"internal_words": "internal words"})

    assert _lazy_phrases((PlantedPhrase,), set()) == [
        "PlantedPhrase.INTERNAL_WORDS"
    ]


def test_the_complete_scan_can_see_an_enum_that_never_checks_itself():
    """Plant a `Spoken` enum with no `complete()` call."""
    planted = ROOT / "backend" / "nm" / "domain" / "_never_completes.py"
    planted.write_text(block_of((
        "from enum import Enum, nonmember",
        "",
        "from nm.domain.spoken import Spoken",
        "",
        "class Quiet(Spoken, str, Enum):",
        "    A = \"a\"",
        "    SAID = nonmember({\"a\": \"a\"})",
    )), encoding="utf8")
    try:
        with pytest.raises(AssertionError, match="Quiet"):
            test_every_spoken_enum_called_complete()
    finally:
        planted.unlink()


def block_of(lines):
    """Lines to source. Written this way rather than as one escaped string
    because heredoc-mangled escapes have broken a file in this repo five
    times in one session."""
    return "".join(line + "\n" for line in lines)
