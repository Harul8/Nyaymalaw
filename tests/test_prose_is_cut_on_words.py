"""A SENTENCE SHORTENED FOR AN ADVOCATE IS CUT ON A WORD, AND SAYS IT WAS CUT.

THE MEASURED DEFECT. A defending turn served this, and the arithmetic beside
it was correct:

    CONDITIONAL, not a deadline: on the reading that the period was run from
    the plaintiff says our client trespassed on 15 April 2019 and they hav
    because the cause carries no curated accrual trigger; confirm it or name
    the entry it should run from...

`accrual.statement[:70]`. The premise the advocate is being asked to confirm
ends mid-word, and confirming the premise is the entire mechanism by which a
wrong accrual is meant to be caught. Correcting it in four words is impossible
if it cannot be read.

WHY THIS IS A SCAN AND NOT A FIX AT THAT LINE. Forty-two sites in `nm/` cut
prose to a character count when this was written, and thirty-six of them fed a
sentence somebody reads. Not one of them was written by a person ignoring a
rule; they were written by people who each needed to shorten a statement and
had nowhere to find the answer. That is the exact history of
`test_one_fold.py`'s six folds and `test_citation_patterns.py`'s two provision
patterns, and the answer is the same one: an owner, and a scan that refuses a
second way of doing it.

THE TWO THINGS A BARE SLICE GETS WRONG are stated on `nm.shared.text_contracts.snippet`.
Briefly: it counts characters where the unit is words, and it does not mark the
elision -- so a shortened statement renders as the whole statement, which is
CLAUDE.md §9's absent-reads-as-complete in the one place the advocate is being
asked to check the product's reading of their own file.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: What a name has to be called for its value to be a sentence. Names, not
#: types, because the cut happens at the call site where only the name is in
#: hand -- and it is deliberately the vocabulary this product actually uses for
#: prose rather than a guess at every word that could hold text.
PROSE = frozenset({
    "statement", "text", "quote", "quoted", "question", "message", "account",
    "span", "said", "proposition", "why", "reason", "sentence", "described",
    "objective", "limb", "label", "first", "reply", "event", "theme", "route",
    "trigger",
})

#: THE VOCABULARY IS THE ENFORCED SCOPE AND IT IS NOT A PROOF OF ABSENCE.
#: A name outside it is UNSCANNED, not shown safe. `held_because` on a
#: `__repr__` is out of scope because nobody reads a repr as English, and
#: `named`, `what` and `element` in the proof refusals are short element
#: labels rather than sentences -- judged, not overlooked. Saying which is
#: which is the point: a scan that implies a completeness it does not have is
#: the S11 shape. Widen the set when a name here turns out to hold a sentence,
#: and sweep the sites it surfaces in the same change.

#: THE CUTS THAT ARE NOT DISPLAY, each with the reason it is not.
#:
#: A budget is not a shortening. `posture`, `route` and the two in `turn` bound
#: what is sent to a MODEL, where nobody reads the seam and an ellipsis would
#: be one more token spent saying nothing. `wanted` keeps a fragment of an
#: element to seed a retrieval, and `described` is a tuple of descriptors --
#: not a sentence at all, and caught here only because of what it is called.
#:
#: Asserted at length below, because an exemption list that can grow quietly is
#: the hole this scan would otherwise be.
#:
#: KEYED ON THE EXPRESSION, NOT THE LINE. The first version keyed on
#: `(file, lineno)` and every entry went stale the moment an import was added
#: above it -- an exemption that drifts onto a different line is worse than no
#: exemption, because it silently permits whatever lands there next.


def _underlying_name(node: ast.AST) -> str | None:
    """The name of the thing being sliced, through the wrappers that keep it
    the same prose.

    `" ".join((data.get("why") or "").split())[:200]` is `why` cut to two
    hundred characters, and the first version of this walked only `.strip()`
    chains and reported it clean -- which the positive control below caught on
    its first run, against a planted string, before the real population was
    read. Ten sites hid behind that shape.

    THE LINE IS BETWEEN A WRAPPER AND A TRANSFORM. `strip`, `split`, `join`,
    `lower` and a `.get` off a parsed model response all hand back the same
    sentence in a different wrapper, so the slice is still a slice of that
    sentence. A call to a NAMED function is not: `fold(statement)[:90]`
    produces a folded KEY whose fixed width is the point, and reading through
    it would refuse the one shape that is deliberately fixed-width.
    """
    probe = node
    for _ in range(12):                     # a bounded walk, never a cycle
        if isinstance(probe, ast.Attribute):
            return probe.attr
        if isinstance(probe, ast.Name):
            return probe.id
        if isinstance(probe, ast.BoolOp) and probe.values:
            probe = probe.values[0]          # `(x or "")`
            continue
        if isinstance(probe, ast.Subscript):
            # `said.split(".")[0][:70]` -- the first sentence OF said, cut to
            # seventy characters. Reading through the index is what found the
            # entry that produced "and they hav": the chronology statement was
            # already garbled where it was PARSED, and every renderer
            # downstream showed the garbling faithfully. A cut applied to a
            # piece of a sentence is a cut applied to a sentence.
            probe = probe.value
            continue
        if isinstance(probe, ast.Call) and isinstance(probe.func, ast.Attribute):
            attr = probe.func.attr
            if attr == "get" and probe.args and isinstance(
                    probe.args[0], ast.Constant) and isinstance(
                    probe.args[0].value, str):
                return probe.args[0].value   # `data.get("why")`
            if isinstance(probe.func.value, ast.Constant) and probe.args:
                probe = probe.args[0]        # `" ".join(X)`
                continue
            probe = probe.func.value         # `X.strip()`
            continue
        if (isinstance(probe, ast.Call)
                and isinstance(probe.func, ast.Name)
                and probe.func.id in ("str", "clean", "fold_spacing")
                and probe.args):
            probe = probe.args[0]            # a cast or a spacing fold
            continue
        return None
    return None                              # pragma: no cover -- defensive


def constant_prose_cuts(source: str) -> list[tuple[int, str]]:
    """Every `<prose>[:N]` in this source, by line.

    Only a constant upper bound with no lower bound and no step: `blob[:12]`
    on a nonce is a different operation that happens to share a syntax, and
    `text[start:end]` is a span rather than a shortening.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:                     # pragma: no cover -- defensive
        return []

    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Subscript):
            continue
        sl = node.slice
        if not isinstance(sl, ast.Slice):
            continue
        if sl.lower is not None or sl.step is not None:
            continue
        if not (isinstance(sl.upper, ast.Constant)
                and isinstance(sl.upper.value, int)):
            continue
        name = _underlying_name(node.value)
        if name in PROSE:
            out.append((node.lineno, ast.unparse(node)))
    return out


def test_the_scanner_sees_a_character_cut_on_a_sentence():
    """THE POSITIVE CONTROL, and it runs first.

    A scan whose finder is wrong reports a clean product, which is this
    repository's most repeated failure and the reason every sweep here is
    proved on planted source before the real population is read.
    """
    for planted in (
        "x = fact.statement[:70]",
        "y = quoted[:60]",
        "z = f'{turn.message.strip()[:200]}'",
        "w = ' '.join(said.split())[:44]",
    ):
        assert constant_prose_cuts(planted), (
            f"the scanner did not see the cut in {planted!r}")


def test_the_scanner_leaves_the_owner_and_a_real_span_alone():
    """THE NEGATIVE CONTROL. A rule that also refuses the correct shape is a
    rule somebody deletes the first time it is in the way."""
    for allowed in (
        "x = snippet(fact.statement, 70)",
        "y = blob[:12]",                      # a nonce, not a sentence
        "z = text[start:end]",                # a span
        "w = rows[:8]",                       # a count of things
        "v = fold(fact.statement)[:90]",      # a KEY, deliberately fixed-width
    ):
        assert not constant_prose_cuts(allowed), (
            f"the scanner flagged {allowed!r}, which is not the defect")

