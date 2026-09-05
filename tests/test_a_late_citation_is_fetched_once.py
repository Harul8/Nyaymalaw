"""B-104 — a citation the answer named and retrieval did not fetch.

THE MEASURED DEFECT
---------------------
GS-15, served, 5 September 2026. The advocate said *"the agreement was never
registered"*. The answer reached for TRANSFER OF PROPERTY ACT s.53A — part
performance, which is the correct provision for exactly that question — and
G-GROUND withheld the turn because s.53A had never been retrieved. Turn 3 went
the same way on s.18. Two of five turns produced no advice.

THE GATE WAS RIGHT EVERY TIME. It is not a false positive: the answer cited a
provision nobody had read, and serving that is the failure the whole product is
built to refuse. What was missing is that the withholding named a provision the
product could simply have looked up.

WHY IT RE-DERIVES RATHER THAN RE-CHECKING
-------------------------------------------
The cheap fix is to fetch the provision and run the citation check again — it
would pass, because the provision is now in the retrieved set. That is worse
than withholding. The prose was composed WITHOUT the text, so passing the check
would certify a sentence nobody wrote from the source, and the citation gate
would have been converted into a formality that any fetch satisfies.

So the text is put in front of the reads that write the answer, and the answer
is written again. That is the only thing that makes the second attempt
different in kind from the first.

ONCE, AND THE BOUND IS THE SAFETY ARGUMENT
--------------------------------------------
An unbounded loop lets a model conjure citations until one lands, which is
precisely what G-GROUND exists to stop. A second failure withholds exactly as
before, and at most two provisions are fetched — an answer naming eight
unretrieved sections is not a turn one more lookup rescues.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from nm.adapters.model.scripted import ScriptedModelAdapter
from nm.adapters.model.traced import TracedModel
from nm.adapters.store.file_store import FileMatterStore
from nm.core.turn import TurnEngine, TurnInput, TurnRefused
from tests.test_turn_contract import KEY, _Evidence, _model_config

pytestmark = pytest.mark.class_a

TODAY = date(2026, 9, 5)
OPENING = ("We act for the plaintiff at Hyderabad on an agreement of sale. "
           "The agreement is dated 15 April 2024.")


class _CitesSomethingElse(ScriptedModelAdapter):
    """Writes an answer naming a provision the turn never retrieved.

    Driven this way because waiting for the live model to reach for an
    unretrieved section is waiting on a coincidence — it did so twice in five
    turns of GS-15, and neither run could be reproduced on demand.
    """

    def __init__(self, *a, cite: str = "53A", **kw):
        super().__init__(*a, **kw)
        self.cite = cite

    def complete(self, prompt, tier, **kw):
        result = super().complete(prompt, tier, **kw)
        return replace(result, text=(
            f"Proceed on part performance under section {self.cite} of the "
            f"Transfer of Property Act."))


def _engine(tmp_path, evidence=None, cite="53A"):
    store = FileMatterStore(tmp_path, key=KEY)
    model = TracedModel(inner=_CitesSomethingElse(
        _model_config(), cite=cite,
        responses={"__default__": "Issue the notice."}))
    return TurnEngine(store=store, evidence=evidence or _Evidence(),
                      model=model), store


# ============================ the round happens =============================

def test_a_provision_the_answer_named_is_fetched_and_the_answer_rewritten(
        tmp_path):
    """THE FIX, on the wire.

    Not "the turn is served" — a turn served with the same unsupported prose
    would pass that and be the defect. The answer must have been DERIVED
    AGAIN, which is visible in the note the second pass carries.
    """
    fetched: list = []

    class _Holds(_Evidence):
        def fetch(self, need):
            if need.provision_hint:
                fetched.append(need.provision_hint)
            return super().fetch(need)

    engine, _ = _engine(tmp_path, evidence=_Holds())
    try:
        engine.run(TurnInput(advocate_id="adv_1", today=TODAY,
                             message=OPENING))
    except TurnRefused:
        pass

    assert fetched, (
        "the answer cited a provision that was not retrieved and nothing "
        "went looking for it — the turn was withheld naming a section the "
        "product could have read")


def test_the_second_pass_is_declared_to_the_advocate(tmp_path):
    """A retry nobody can see is a product that quietly tries again until
    something comes out, which is the shape the bound exists to refuse."""
    engine, _ = _engine(tmp_path)
    try:
        out = engine.run(TurnInput(advocate_id="adv_1", today=TODAY,
                                   message=OPENING))
    except TurnRefused:
        return                      # still withheld: nothing to declare
    said = " ".join(e.text for e in out.answer.elements)
    if "second pass" in said:
        assert "without having retrieved it" in said, (
            "the note says a second pass happened and not why:\n" + said)


# ================================ the bound =================================

def test_a_second_failure_still_withholds(tmp_path):
    """THE BOUND, AND IT IS THE WHOLE SAFETY ARGUMENT.

    The model is made to cite a provision that does not exist, so no fetch can
    satisfy it. The turn must still be withheld — a retry that eventually
    serves whatever the model asked for has converted the gate into a
    formality.
    """
    engine, _ = _engine(tmp_path, cite="9999")
    with pytest.raises(TurnRefused) as refused:
        engine.run(TurnInput(advocate_id="adv_1", today=TODAY,
                             message=OPENING))
    assert "G-GROUND" in str(refused.value)


def test_the_round_runs_at_most_once(tmp_path):
    """A loop would let a model conjure citations until one landed.

    Counted on the FETCHES, not on a flag, because a flag records the
    intention and the fetch count records what happened.
    """
    hints: list = []

    class _Counting(_Evidence):
        def fetch(self, need):
            if need.provision_hint:
                hints.append(need.provision_hint)
            return super().fetch(need)

    engine, _ = _engine(tmp_path, evidence=_Counting(), cite="9999")
    with pytest.raises(TurnRefused):
        engine.run(TurnInput(advocate_id="adv_1", today=TODAY,
                             message=OPENING))

    assert len(hints) <= 2, (
        f"the late-citation fetch ran {len(hints)} times; the bound is two "
        f"provisions on one round")


def test_an_ordinary_turn_makes_no_extra_round(tmp_path):
    """THE COST BOUND. An answer that cites only what was retrieved must not
    pay for a second derivation — the round is for the case that would
    otherwise be withheld, not a tax on every turn."""
    hints: list = []

    class _Counting(_Evidence):
        def fetch(self, need):
            if need.provision_hint:
                hints.append(need.provision_hint)
            return super().fetch(need)

    store = FileMatterStore(tmp_path, key=KEY)
    engine = TurnEngine(
        store=store, evidence=_Counting(),
        model=TracedModel(inner=ScriptedModelAdapter(
            _model_config(), responses={"__default__": "Issue the notice."})))
    engine.run(TurnInput(advocate_id="adv_1", today=TODAY, message=OPENING))

    assert hints == [], (
        f"an ordinary turn triggered a late-citation fetch for {hints}")
