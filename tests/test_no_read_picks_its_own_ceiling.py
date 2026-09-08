"""BK-29 — no call site chooses a token ceiling, and echoing reads derive one.

THE DEFECT
------------
The dispute read ran at `max_tokens=200`. Once it began returning three
verbatim spans the JSON truncated mid-string at character 827, the read was
LOST, and the turn fell back to one thread. Nothing was wrong with the model
or the prompt.

A read that must QUOTE to be believed has an output whose size follows its
input. A constant ceiling on such a read is a length limit on the advocate
disguised as a cost control — and it fails by TRUNCATION, which is a parse
error rather than a short answer, so the whole read is lost rather than
degraded. That is the worst available failure mode: a short answer is visible
and can be disclosed; a lost read falls back to whatever the call site's
`except` returns, and here that was a finding about the advocate's file
produced by a broken string.

WHY A SWEEP AND NOT SIXTEEN BETTER NUMBERS
--------------------------------------------
Raising every ceiling moves the cliff without removing it and leaves sixteen
call sites each choosing a number. CLAUDE.md §4's question is not *where is
the other copy* but *what makes a second copy impossible*, and the answer is
that a call site cannot name a ceiling at all: `TurnEngine._read` takes the
read's KEY, and `nm/core/ceiling.py` decides.

WHAT THIS FILE REFUSES
------------------------
The seventeenth. A `max_tokens=` literal added to a structured read in
`nm/core/` fails the build, and a read the product makes that has not
declared whether it echoes fails with it.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from nm.core import ceiling
from nm.domain import reads

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
CORE = ROOT / "nm" / "core"

#: Calls that may still name a ceiling, and why. `complete()` returns PROSE --
#: one imperative sentence, one rewritten step, one courtesy line -- and its
#: size does not follow the brief's. A derived ceiling there would buy nothing
#: and let a long file produce a long recommendation, which is the opposite of
#: what D3 wants.
PROSE_CALLS = frozenset({"complete"})


def structured_ceilings() -> list[str]:
    """Every `max_tokens=` on a STRUCTURED read in `nm/core/`, from the AST."""
    found: list[str] = []
    for path in sorted(CORE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            attr = getattr(node.func, "attr", "")
            if attr in PROSE_CALLS:
                continue
            for kw in node.keywords:
                if kw.arg != "max_tokens":
                    continue
                # A LITERAL is the defect. A call to the owner is the fix.
                if isinstance(kw.value, ast.Constant):
                    found.append(
                        f"{path.relative_to(ROOT).as_posix()}:{node.lineno} "
                        f"names max_tokens={kw.value.value}")
    return found


# ==================================================================== the rule ==

def test_no_structured_read_names_its_own_ceiling():
    """THE SWEEP. Sixteen literals became one owner; this refuses the next."""
    offenders = structured_ceilings()
    assert not offenders, (
        "these structured reads choose their own token ceiling. A read that "
        "quotes has an output the size of its input, and a constant there "
        "fails by TRUNCATION -- a parse error, so the read is lost rather "
        "than short. Call `TurnEngine._read(prompt, schema, key)` and let "
        "`nm/core/ceiling.py` decide:\n  " + "\n  ".join(offenders))


def test_every_read_declares_whether_it_echoes():
    """The property the ceiling is derived FROM, declared beside the schema.

    `reads.echoes()` returns False for a read it does not know, which is the
    quiet direction -- so the population has to be closed somewhere, and
    `tests/test_reads_registry.py` closes it by failing on a schema the
    product sends that is not in `READS`. This asserts the field exists on
    every row, so a new entry cannot be added without answering the question.
    """
    for read in reads.READS:
        assert isinstance(read.echoes, bool), (
            f"{read.key} does not say whether its answer follows the size of "
            f"the input, so nothing can size its ceiling")

    # AND BOTH ANSWERS ARE REPRESENTED. A registry where every read echoed --
    # or none did -- would pass the loop above while meaning nobody had
    # actually decided.
    kinds = {r.echoes for r in reads.READS}
    assert kinds == {True, False}, (
        f"every read gives the same answer ({kinds}), so the distinction is "
        f"not being made")


# ============================================================ the derivation ==

def test_an_echoing_read_gets_more_room_for_a_longer_brief():
    """THE POINT OF THE ROW. The dispute read's 200 was fine until the brief
    grew, and nothing about the ceiling knew the brief had grown."""
    from nm.ports.model import Prompt

    short = Prompt(system="s" * 200, user="u" * 400)
    long_ = Prompt(system="s" * 200, user="u" * 12000)

    assert ceiling.for_read("dispute", long_, echoes=True) > \
        ceiling.for_read("dispute", short, echoes=True), (
        "a longer brief gets no more room, so the ceiling is a constant "
        "wearing a function's clothes")


def test_a_fixed_read_is_unmoved_by_a_longer_brief():
    """THE BOUND. A route decision is a verdict; scaling it with the brief
    would spend tokens on every long file for nothing."""
    from nm.ports.model import Prompt

    short = Prompt(system="s" * 200, user="u" * 400)
    long_ = Prompt(system="s" * 200, user="u" * 12000)

    assert ceiling.for_read("route", short, echoes=False) == \
        ceiling.for_read("route", long_, echoes=False)


def test_the_floor_and_the_cap_both_hold():
    """A one-line brief still gets room for the JSON around an empty answer,
    and a pasted judgment cannot ask for an unbounded completion."""
    from nm.ports.model import Prompt

    tiny = Prompt(system="", user="hi")
    huge = Prompt(system="s" * 1000, user="u" * 400000)

    assert ceiling.for_read("issues", tiny, echoes=True) == ceiling.FLOOR
    assert ceiling.for_read("issues", huge, echoes=True) == ceiling.CAP


def test_an_undeclared_read_gets_the_floor_and_not_a_guess():
    """The safe direction for a read nobody listed. It is never reached --
    `test_reads_registry` fails the build first -- and if it were, a floor is
    a bounded failure and an invented number is an unbounded one."""
    from nm.ports.model import Prompt

    assert ceiling.for_read("no_such_read", Prompt(system="", user="x"),
                            echoes=False) == ceiling.FLOOR


# ======================================================== positive controls ==

def test_the_scan_can_see_a_planted_ceiling():
    """A CONTROL ON THE SWEEP. One that found nothing would pass the rule
    above while reading nothing -- which is how sixteen literals survived
    every check in this repository."""
    planted = CORE / "_ceiling_probe.py"
    planted.write_text(
        "def f(model, prompt, schema, tier):\n"
        "    return model.structured(prompt, schema, tier, max_tokens=200)\n",
        encoding="utf8")
    try:
        found = structured_ceilings()
        assert any("_ceiling_probe.py" in f for f in found), (
            f"the scan did not see a planted literal: {found}")
    finally:
        planted.unlink()


def test_the_scan_ignores_a_prose_completion():
    """AND THE BOUND ON THE CONTROL. `complete()` returns one sentence and
    may state a ceiling; a sweep that failed on it would be refusing correct
    code, which is how a check gets switched off."""
    planted = CORE / "_ceiling_probe.py"
    planted.write_text(
        "def f(model, prompt, tier):\n"
        "    return model.complete(prompt, tier, max_tokens=120)\n",
        encoding="utf8")
    try:
        assert not any("_ceiling_probe.py" in f for f in structured_ceilings())
    finally:
        planted.unlink()
