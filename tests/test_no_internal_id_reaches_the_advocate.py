"""B-103 — this product's own keys must not appear in text meant for a person.

THE MEASURED DEFECT
---------------------
GS-15, served, 5 September 2026. Turn 2 put this to the advocate:

    "To take this further I need: whether anything already done on limitation
     on thr_380e2b97f5a6 needs undoing."

An advocate cannot answer a question addressed to a database key. The thread
has a LABEL — 'the sale' — that every other line of the same turn uses.

WHY IT IS A SWEEP AND NOT A FIX AT ONE SITE
---------------------------------------------
The id arrived because a derived value is keyed `<what> on <thread_id>` for
uniqueness, and that key was rendered straight into a question. Renaming that
one string would fix that one question. Every other place that composes
advocate-facing text from an internal name is still free to do it, and the
next one will be found the same way this one was — by reading a served run.

So the population is EVERY ELEMENT OF A SERVED ANSWER, and the check is that
none of them contains one of this product's own id prefixes. It draws from the
whole product rather than from the cascade, so a leak from the gap queue, the
threshold map or a module written next month fails here too.
"""
from __future__ import annotations

import re
from datetime import date

import pytest

from nm.adapters.model.scripted import ScriptedModelAdapter
from nm.adapters.model.traced import TracedModel
from nm.adapters.store.file_store import FileMatterStore
from nm.core.turn import TurnEngine, TurnInput, TurnRefused
from tests.test_turn_contract import KEY, _Evidence, _model_config

pytestmark = pytest.mark.class_a

TODAY = date(2026, 9, 5)

#: The id shapes this product mints. Read off `Matter.create`, `Thread.create`
#: and the fact/turn id helpers -- not a guess at what ids look like.
INTERNAL_ID = re.compile(r"\b(?:mat|thr|fact|turn|adv)_[0-9a-f]{8,}\b")

#: A conversation that exercises the paths which compose text from derived
#: names: a limitation that arrives, a correction that moves it, and a turn
#: that asks where things stand.
CONVERSATION = (
    "We act for the plaintiff at Hyderabad on an agreement of sale. "
    "The agreement is dated 15 April 1984.",
    "sorry, that is wrong. It is dated 15 April 2024.",
    "the agreement was never registered",
    "so where do we stand now",
)


def _served(tmp_path) -> list[str]:
    """Every line the advocate was actually shown, across the conversation."""
    store = FileMatterStore(tmp_path, key=KEY)
    engine = TurnEngine(
        store=store, evidence=_Evidence(),
        model=TracedModel(inner=ScriptedModelAdapter(
            _model_config(),
            responses={"__default__": "Issue the notice and diarise it."})))

    shown: list[str] = []
    matter_id = None
    for message in CONVERSATION:
        try:
            out = engine.run(TurnInput(advocate_id="adv_1", today=TODAY,
                                       matter_id=matter_id, message=message))
        except TurnRefused as refused:
            # A REFUSAL IS SHOWN TOO, and its text is advocate-facing.
            matter_id = getattr(refused, "matter_id", matter_id)
            shown.extend(refused.disclosures)
            shown.append(str(refused))
            continue
        matter_id = out.matter.id
        shown.extend(e.text for e in out.answer.elements)
        shown.extend(q.text for q in out.matter.asked)
    return shown


def test_the_sweep_can_see_the_text():
    """A positive control on the POPULATION. A conversation that produced no
    lines would pass the check below while looking at nothing."""
    assert INTERNAL_ID.search("limitation on thr_380e2b97f5a6"), (
        "the pattern does not match the id shape that caused B-103")
    assert not INTERNAL_ID.search("the limitation on 'the sale'")


def test_no_internal_id_reaches_the_advocate(tmp_path):
    """THE SWEEP.

    Asked the other way -- do the ids we mint look like ids -- it would
    confirm the pattern matches itself, which cannot fail. This asks which
    advocate-facing lines contain one, which is the only direction that finds
    anything.
    """
    shown = _served(tmp_path)
    assert len(shown) > 10, f"the conversation produced almost nothing: {shown}"

    leaked = [line for line in shown if INTERNAL_ID.search(line or "")]
    assert not leaked, (
        "these lines were shown to the advocate and carry one of this "
        "product's own keys. An advocate cannot answer a question addressed "
        "to a database key, and every thread has a label:\n  "
        + "\n  ".join(line[:160] for line in leaked))


def test_the_sweep_can_see_a_planted_leak(tmp_path):
    """A POSITIVE CONTROL ON THE MECHANISM, planted on the real collection.

    The check passes trivially on a run that leaks nothing, and would go on
    passing if `_served` returned an empty list or the pattern were broken --
    which is B-049's shape, a checker that always returns nothing.
    """
    shown = [*_served(tmp_path), "whether anything on thr_deadbeef12 moved"]
    assert [line for line in shown if INTERNAL_ID.search(line)], (
        "the sweep cannot see a leak sitting in the collection it reads")


def test_a_derived_value_keeps_its_key_and_gains_a_label():
    """THE FIX ITSELF: two strings, because one cannot be both.

    The key must stay unique across threads -- two limitations are two values
    -- and the label must stay readable. Renaming the key to the label would
    make two threads' limitations collide, which is a worse defect wearing a
    friendlier name.
    """
    from nm.core import cascade

    d = cascade.Derived(name="limitation on thr_380e2b97f5a6", value="2027-04-15",
                        from_facts=("f1",), shown="the limitation on 'the sale'")
    assert INTERNAL_ID.search(d.name), "the key lost its uniqueness"
    assert not INTERNAL_ID.search(d.shown)

    (change,) = cascade.changes((), (d,))
    assert change.shown == d.shown
    assert not INTERNAL_ID.search(cascade.report((change,))[0])


def test_a_derivation_with_no_label_falls_back_to_its_key():
    """An older transcript carries no label, and inventing one would show the
    advocate a string the earlier turn never used. The key is worse to read
    and it is TRUE, which is the right way round."""
    from nm.core import cascade

    d = cascade.Derived(name="limitation on thr_380e2b97f5a6", value="2027-04-15",
                        from_facts=("f1",))
    (change,) = cascade.changes((), (d,))
    assert change.shown == d.name
