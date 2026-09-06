"""PHASE 1 — the matter remembers what it CONCLUDED, not only what was said.

THE MEASURED DEFECT
---------------------
GS-15, served, 6 September 2026. Five turns produced FIVE DIFFERENT THEORIES
while the advocate supplied a date, corrected it, and mentioned non-registration
— nothing that asked for a new theory of the case:

    turn 1  the plaintiff is entitled to specific performance…
    turn 2  the claim is valid BECAUSE THE LIMITATION PERIOD…
    turn 3  the case for the agreement DATED APRIL 15 2024…
    turn 4  entitled DESPITE ITS NON-REGISTRATION…
    turn 5  the unregistered agreement DOES NOT BAR…

The issue count went 1, 1, 1, 0, 2. On turn 4 the thread had NO ISSUES AT ALL,
having had one for three turns.

An advocate who reconsidered their whole theory each time you gave them a date
would not be trusted with the matter.

WHY IT HAPPENED, AND WHY IT IS ARCHITECTURAL
----------------------------------------------
`Matter` persisted `threads, facts, turns_applied, asked`. The product's own
type says the rest: a handover needs SIXTEEN sections and `CARRIES` names FOUR,
so `handover_blockers` returns ten. Issues, theory, proof, authorities,
decisions and reservations were re-derived from the account every turn — not
because anything changed, but because that was the design.

NM remembered what the advocate SAID and forgot what it had CONCLUDED.

THE FIX IS REVISION, NOT PERSISTENCE ALONE
--------------------------------------------
Storing the theory and regenerating it anyway would change nothing. So the read
is SHOWN the standing theory and told to revise it: keep what still fits, and
name in `revises_because` what stopped fitting before replacing it. A theory
that changes with no reason given is disclosed as exactly that.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from nm.adapters.model.scripted import ScriptedModelAdapter
from nm.adapters.model.traced import TracedModel
from nm.adapters.store.file_store import FileMatterStore
from nm.core import theory as theory_reader
from nm.core.turn import TurnEngine, TurnInput
from tests.test_turn_contract import KEY, _Evidence, _model_config

pytestmark = pytest.mark.class_a

TODAY = date(2026, 9, 6)
OPENING = ("We act for the plaintiff at Hyderabad on an agreement of sale. "
           "The agreement is dated 15 April 2024.")
FOLLOW_UPS = ("the agreement was never registered",
              "so where do we stand now",
              "what about the notice")


def _engine(tmp_path, inner=None):
    store = FileMatterStore(tmp_path, key=KEY)
    model = TracedModel(inner=inner or ScriptedModelAdapter(
        _model_config(), responses={"__default__": "Issue the notice."}))
    return TurnEngine(store=store, evidence=_Evidence(), model=model), store


def _standing(store, matter_id):
    return theory_reader.from_stored(store.load(matter_id).threads[0].theory)


# ============================ it survives ==================================

def test_the_theory_is_the_same_across_four_turns(tmp_path):
    """THE DEFECT, AS A RULE.

    Not "a theory is stored" — storing it and regenerating it anyway would
    pass that and change nothing. The theme must be the SAME STRING turn after
    turn while nothing in the file contradicts it.
    """
    engine, store = _engine(tmp_path)
    first = engine.run(TurnInput(advocate_id="adv_1", today=TODAY,
                                 message=OPENING))
    themes = [_standing(store, first.matter.id).theme]
    for message in FOLLOW_UPS:
        engine.run(TurnInput(advocate_id="adv_1", matter_id=first.matter.id,
                             today=TODAY, message=message))
        themes.append(_standing(store, first.matter.id).theme)

    assert len(set(themes)) == 1, (
        "the theory of the case changed across turns with nothing asking it "
        "to. GS-15 produced five in five turns:\n  "
        + "\n  ".join(dict.fromkeys(themes)))


def test_it_comes_back_from_the_store_typed(tmp_path):
    """A DEFECT WITH A DELAY ON IT, caught within the minute.

    `Thread.theory` is typed `object` because `nm.domain` may not import
    `nm.core.theory` — domain holds the state, core holds the reading of it —
    so the generic decoder hands back a plain dict. The value round-trips
    fine, and the NEXT turn touches `.theme` on a dict and the whole revision
    path fails.
    """
    engine, store = _engine(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", today=TODAY,
                               message=OPENING))

    raw = store.load(out.matter.id).threads[0].theory
    assert raw is not None, "nothing was persisted at all"
    assert theory_reader.from_stored(raw) is not None, (
        "the stored theory could not be read back into a Theory, so the next "
        "turn would form a fresh one and the persistence would be decorative")
    assert theory_reader.from_stored(raw).theme


def test_a_record_that_cannot_be_read_forms_a_fresh_theory():
    """The third state. A record written before a rule existed can fail
    today's constructor, and crashing a turn on history is worse than
    starting again — but it must be a DECISION, not an exception nobody
    catches."""
    assert theory_reader.from_stored(None) is None
    assert theory_reader.from_stored({"theme": ""}) is None
    assert theory_reader.from_stored("not a theory at all") is None
    assert theory_reader.from_stored({"theme": "x", "stance": "nonsense"}) is None


def test_a_theory_object_passes_through_unchanged():
    """`from_stored` is called on a value that may already be typed — on the
    turn that created it, it is. Re-parsing would be a second construction of
    something already validated."""
    t = theory_reader.Theory(thread="thr_1", theme="a theme",
                             relief="the relief",
                             stance=theory_reader.Stance.AFFIRMATIVE)
    assert theory_reader.from_stored(t) is t


# ============================ it is revised ================================

def test_the_read_is_shown_the_theory_it_must_revise():
    """Without this the read forms a theory FROM THE FILE every turn, and the
    answer is a fresh one every turn. The prompt is what turns the job from
    forming into revising."""
    standing = theory_reader.Theory(
        thread="thr_1", theme="The plaintiff is entitled to possession.",
        relief="possession", stance=theory_reader.Stance.AFFIRMATIVE)
    prompt = theory_reader.build_theory_prompt(
        "the file", ("f1: a bad fact",), "moving", standing=standing)

    assert "THE THEORY ALREADY ON THIS THREAD" in prompt.user
    assert "The plaintiff is entitled to possession." in prompt.user
    assert "REVISE it, not to replace it" in prompt.user

    fresh = theory_reader.build_theory_prompt("the file", (), "moving")
    assert "No theory has been formed" in fresh.user, (
        "the first turn on a thread must be told there is nothing to revise, "
        "or it will look for a theory that does not exist")


def test_a_theory_that_changes_says_what_stopped_fitting(tmp_path):
    """REVISION MEANS A REASON. A theory replaced with no reason given is a
    regeneration wearing a revision's clothes, and it is what produced five
    theories in five turns.

    Driven with a model that changes the theme every turn and never explains
    it, because that is precisely the behaviour being guarded against.
    """
    import json

    class _AlwaysDifferent(ScriptedModelAdapter):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.n = 0

        def structured(self, prompt, schema, tier, **kw):
            result = super().structured(prompt, schema, tier, **kw)
            if schema.get("x-nm-read") == "theory" and result.data:
                self.n += 1
                data = {**result.data,
                        "theme": f"a completely different theory {self.n}",
                        "revises_because": ""}
                return replace(result, data=data,
                               text=json.dumps(data))
            return result

    engine, store = _engine(tmp_path, inner=_AlwaysDifferent(
        _model_config(), responses={"__default__": "Issue the notice."}))
    first = engine.run(TurnInput(advocate_id="adv_1", today=TODAY,
                                 message=OPENING))
    out = engine.run(TurnInput(advocate_id="adv_1", matter_id=first.matter.id,
                               today=TODAY, message=FOLLOW_UPS[0]))

    said = " ".join(e.text for e in out.answer.elements)
    assert "no reason was given for the change" in said, (
        "the theory changed from the one on the file and the advocate was not "
        "told:\n" + said)


def test_a_blocked_turn_does_not_erase_the_standing_theory(tmp_path):
    """THE BOUND, and it is the direction that loses work.

    A turn that asked a question and derived nothing must not write an empty
    conclusion over a theory the file already holds — that is the same
    forgetting, arriving through the fix for it.
    """
    engine, store = _engine(tmp_path)
    first = engine.run(TurnInput(advocate_id="adv_1", today=TODAY,
                                 message=OPENING))
    before = _standing(store, first.matter.id)
    assert before is not None

    engine.run(TurnInput(advocate_id="adv_1", matter_id=first.matter.id,
                         today=TODAY, message="what is the limitation"))
    after = _standing(store, first.matter.id)

    assert after is not None, "a later turn erased the theory on the file"
    assert after.theme == before.theme
