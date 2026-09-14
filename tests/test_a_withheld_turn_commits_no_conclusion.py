"""A WITHHELD TURN KEEPS WHAT THE ADVOCATE SAID AND DISCARDS WHAT IT DERIVED.

THE RULE, NOT THE SCENARIO. The defect was found by forcing an ungrounded
citation, but nothing here is about citations: it is about which half of a
turn survives a refusal. Any gate that withholds the ANSWER must leave the
INPUT and take the conclusions with it.

WHAT WAS HAPPENING, MEASURED
------------------------------
An external review reported it and the reproduction matched to the number. A
turn withheld by `G-GROUND` still committed:

    facts              2
    thread.theory      SET      <- a model-derived theory
    thread.decisions   1
    thread.authorities 1
    thread.issues      2
    thread.assessed    8
    turns_applied      (none)

So the answer was refused and the conclusions were kept. The next turn reads
them as the file's standing position: a theory that was never grounded and
never served becomes what the matter believes about itself, and every later
turn reasons from it.

WHY IT SURVIVED SO LONG
-------------------------
The gated branch already said the right thing in a comment -- *the input is
committed and the answer is not* -- and the rule was correct. What was wrong
is that `matter` at that line was no longer the input: `with_thread(settled)`
had written the turn's conclusions onto it several hundred lines earlier, and
nothing separated the two.

That is this project's recurring shape from the other direction. Usually a
control is missing; here it was stated, believed, and quietly untrue -- which
is worse, because the comment reassured every reader who looked.

WHAT THIS TEST IS NOT
-----------------------
It does not assert that G-GROUND fires on a particular sentence. It asserts
that when ANY withholding gate fires, the committed matter carries the
advocate's facts and none of the turn's derived state. A future gate added to
the withholding set is covered without editing this file.
"""
from __future__ import annotations

import pathlib
import tempfile
from dataclasses import replace

import pytest
from nm.adapters.model.scripted import ScriptedModelAdapter
from nm.core.turn import TurnInput, TurnRefused

from tests.test_turn_contract import _model_config, build

pytestmark = pytest.mark.class_a

BRIEF = ("We act for the plaintiff, a supplier at Hyderabad. Goods were "
         "supplied against invoices on 14 March 2023 and were never paid for.")

#: Every field on a thread that holds something this turn WORKED OUT, as
#: opposed to something the advocate said. Drawn from the write-back in
#: `turn.py` -- if a tenth conclusion is added there and not here, the
#: population check below fails rather than this test quietly narrowing.
DERIVED = ("theory", "issues", "decisions", "proof", "deadlines", "gaps",
           "authorities", "evidence", "thresholds_told",
           # P22/P23, added when the population check below caught them
           # missing -- which is that check doing exactly its job. The legal
           # premises a limitation ran under, the objective relief is measured
           # against, and the relief position itself are all WORKED OUT rather
           # than said, so a withheld turn must discard them as it discards the
           # theory.
           "premises", "objective", "reliefs",
           # P26, caught the same way. The typed E2 recommendation is the most
           # conclusion-shaped thing on the thread -- a position, a step, an
           # owner and a date -- so a withheld turn discarding everything else
           # while keeping THAT would leave the advocate the one sentence they
           # would act on, drawn from an answer the gate refused to serve.
           "recommendation")


class _Ungrounded(ScriptedModelAdapter):
    """Answers the recommendation with a provision nobody retrieved.

    The cheapest way to make a WITHHOLDING gate fire on a turn that has
    otherwise derived a full position -- which is exactly the state that must
    not be committed.
    """

    def complete(self, prompt, tier, **kw):
        res = super().complete(prompt, tier, **kw)
        if "single next step" in (prompt.user or "").lower():
            return type(res)(
                text="File under section 999 of the Imaginary Act, 1999.",
                data=None, tier=res.tier, provider=res.provider,
                model=res.model, usage=res.usage, latency_ms=res.latency_ms)
        return res


def _withheld(root: pathlib.Path):
    engine, store = build(root)
    engine._model = _Ungrounded(_model_config())
    refused = None
    try:
        engine.run(TurnInput(advocate_id="adv", message=BRIEF))
    except TurnRefused as exc:
        refused = exc
    assert refused is not None, (
        "the turn was not withheld, so this test is measuring an ordinary "
        "turn and would pass however the commit behaved")
    files = list(root.glob("matters/*.nm"))
    assert len(files) == 1, (
        f"expected exactly one matter on disk, found {len(files)} -- a "
        f"withheld turn must still keep the advocate's words")
    return store.load(files[0].stem)


def _derived_leaks(matter) -> list[str]:
    """Report conclusions present on a matter that should be input-only."""
    leaked: list[str] = []
    for thread in matter.threads:
        for field in DERIVED:
            value = getattr(thread, field, None)
            if value:
                leaked.append(f"{field} = {value!r}"[:100])
        if thread.assessed:
            leaked.append(f"assessed = {list(thread.assessed)}")
    return leaked


def test_a_withheld_turn_keeps_the_facts_the_advocate_stated():
    """THE OTHER HALF, and it is why this is a snapshot and not a rollback.

    Committing nothing was the previous defect: GS-15 turn 1 was withheld,
    the matter was never created, and everything the advocate had written was
    gone. Both halves have to hold at once.
    """
    with tempfile.TemporaryDirectory() as d:
        matter = _withheld(pathlib.Path(d))
    assert matter.facts, "the advocate's words were lost with the refusal"


def test_a_withheld_turn_commits_none_of_what_it_derived():
    """THE INVARIANT."""
    with tempfile.TemporaryDirectory() as d:
        matter = _withheld(pathlib.Path(d))

    leaked = _derived_leaks(matter)

    assert not leaked, (
        "a withheld turn committed what it derived, so the next turn will "
        "read as the file's standing position something that was never "
          "grounded and never served:\n  " + "\n  ".join(leaked))


def test_the_withheld_conclusion_sweep_can_see_a_planted_leak():
    """BK-52. Plant derived state in the exact matter population checked."""
    with tempfile.TemporaryDirectory() as d:
        matter = _withheld(pathlib.Path(d))
    assert matter.threads, "the control has no thread in which to plant a leak"
    planted_thread = replace(matter.threads[0], assessed=("theory",))
    planted = replace(matter, threads=(planted_thread, *matter.threads[1:]))
    assert _derived_leaks(planted) == ["assessed = ['theory']"]


def test_a_withheld_turn_is_not_marked_applied():
    """`turns_applied` is the replay key. A withheld turn is NOT done, and
    marking it would make a retry return the refusal instead of re-deriving."""
    with tempfile.TemporaryDirectory() as d:
        matter = _withheld(pathlib.Path(d))
    assert not matter.turns_applied, (
        f"the withheld turn was marked applied: {matter.turns_applied}")


def test_the_derived_population_is_drawn_from_the_write_back():
    """POSITIVE CONTROL ON THE POPULATION, not on the assertion.

    The test above can only find a leak in a field it knows about. If the
    write-back gains a tenth conclusion and `DERIVED` does not, the invariant
    silently narrows -- which is how a sweep comes to pass while the defect it
    was written for walks through the gap beside it.
    """
    import ast
    import inspect

    from nm.core.turn import TurnEngine

    tree = ast.parse(inspect.getsource(TurnEngine._run).lstrip())
    written = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg and "concluded.get" in ast.unparse(kw.value):
                written.add(kw.arg)

    assert written, (
        "no `concluded.get(...)` write-back found in `_run` -- the scan is "
        "broken, and a scan that sees nothing passes everything")
    missing = sorted(written - set(DERIVED) - {"assessed", "reservations"})
    assert not missing, (
        f"these conclusions are written back to the thread and are not in "
        f"DERIVED, so the invariant above does not check them: {missing}")
