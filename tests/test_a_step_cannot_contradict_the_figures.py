"""G-CONSISTENT — a step is not served beside figures that say it is wrong.

WHAT THIS REFUSES, AND WHY IT IS NOT A PROMPT
-----------------------------------------------
B-074, measured on a served turn: the ACTION read *"file the recovery suit,
ensuring it is within the limitation period"* while the GROUND directly below
it read *"that period has run"* — 174 days ago. It was fixed by telling the
model what had been worked out, at length and correctly, and it recurred on
`6e29cf0`: *"Confirm the date of service and file within the window"*, beside
an annotation on the same element saying every deadline had passed.

A prompt is an instruction that is usually followed. The turns where it is not
followed are exactly the turns nobody is watching, and this file is what
watches them.

WHY THE READ IS DRIVEN AND NOT THE SENTENCE
---------------------------------------------
Every test here replaces the consistency responder rather than trying to coax
a real contradiction out of a scripted step. That is deliberate: what is under
test is the MECHANISM — what the engine does with a verdict — and a test that
depended on a double producing a genuine contradiction would be testing the
double. `scripted_consistency` says so in its own docstring and explains why
it cannot be the thing that judges.

EVERY BRANCH, INCLUDING THE ONES THAT MUST NOT BLOCK
------------------------------------------------------
Four of the six cases below assert that the step is STILL SERVED — a read that
could not run, one that named a fact it was not shown, one that could not
quote the words it objected to, and one that found nothing. That asymmetry is
the whole design and it is the opposite of every other guard in this product:
refusing here deletes advice that is probably sound, and an advocate cannot
tell a step that was suppressed from a step that was never written.
"""
from __future__ import annotations

import json
import re
from datetime import date

import pytest

from nm.adapters.model.scripted import SCRIPTED_READS, ScriptedModelAdapter
from nm.adapters.store.file_store import FileMatterStore
from nm.core.turn import TurnEngine, TurnInput
from nm.domain.answer import ElementKind
from nm.ports.model import ModelError
from tests.test_turn_contract import KEY, _Evidence, _model_config, briefed

pytestmark = pytest.mark.class_a

TODAY = date(2026, 9, 4)

BRIEF = ("We act for the plaintiff, a supplier at Hyderabad. Goods were "
         "supplied against invoices on 14 March 2010 and were never paid for.")

#: The step the double writes, and the rewrite it produces when asked to
#: repair one. Keyed on a phrase unique to `consistency.repair_prompt`, so
#: the two are told apart by which prompt arrived rather than by call order.
STEP = "File the recovery suit within the limitation period."
REPAIRED = "Obtain certified copies of the invoices and the ledger extract."
RESPONSES = {"The corrected step": REPAIRED, "__default__": STEP}


def _claims(prompt: str) -> list[str]:
    """The claim ids the read was OFFERED, off the prompt it was sent."""
    return re.findall(r"^\s+(\w+)\t", prompt, flags=re.M)


def _step(prompt: str) -> str:
    """The step the read was shown, off the same prompt."""
    m = re.search(r"THE STEP:\n(.*?)\n\nWhich", prompt, flags=re.S)
    return m.group(1).strip() if m else ""


def _verdicts(*answers):
    """A consistency responder that gives `answers` in order, then repeats.

    Each answer is a callable taking (claims, step) and returning the dict.
    Sequencing matters for the repair case: the first read must contradict
    and the second must not, which is one responder answering differently on
    two different steps.
    """
    calls = {"n": 0}

    def responder(user: str) -> str:
        i = min(calls["n"], len(answers) - 1)
        calls["n"] += 1
        return json.dumps(answers[i](_claims(user), _step(user)))
    return responder


def _contradicts(claims, step):
    """Name the first offered claim, quoting the step's own opening words."""
    return {"claim_id": claims[0],
            "quoted": " ".join(step.split()[:4]),
            "why": "the step directs action the computed position rules out"}


def _clean(claims, step):
    return {"claim_id": "", "quoted": "", "why": "nothing is contradicted"}


def _run(tmp_path, monkeypatch, responder=None, model=None):
    if responder is not None:
        monkeypatch.setitem(SCRIPTED_READS, "consistency", responder)
    engine = briefed(TurnEngine(
        store=FileMatterStore(tmp_path, key=KEY),
        evidence=_Evidence(),
        model=model or ScriptedModelAdapter(_model_config(),
                                            responses=RESPONSES)))
    return engine.run(TurnInput(advocate_id="adv_1", message=BRIEF,
                                today=TODAY))


def _action(out):
    """The served step, or None if none was served."""
    return next((e for e in out.answer.elements
                 if e.kind is ElementKind.ACTION), None)


def _blocked(out):
    """The block that replaced the step, or None."""
    return next((e for e in out.answer.elements
                 if e.gate == "G-CONSISTENT"), None)


def _states(out) -> list[str]:
    return [g.state for g in out.metrics.gates_fired
            if g.gate_id == "G-CONSISTENT"]


# ================================================ the step does not go out ==

def test_a_step_that_contradicts_the_figures_is_not_served(
        tmp_path, monkeypatch):
    """THE RULE. Where the step cannot be reconciled with what this same
    answer computed, the advocate gets the computed position and a question —
    never the sentence that disagrees with the figures beside it.
    """
    out = _run(tmp_path, monkeypatch, _verdicts(_contradicts))

    assert _action(out) is None, (
        f"a contradicting step was served: {_action(out).text!r}")
    block = _blocked(out)
    assert block is not None, "the step vanished without the advocate being told"
    assert block.kind is ElementKind.QUESTION
    assert _states(out) == ["contradicted"]
    # THE COMPUTED FACT IS IN THE BLOCK, not just the complaint. A block that
    # says "that was wrong" and not "here is what was worked out" costs the
    # advocate the turn and gives nothing back.
    assert "limitation" in block.text.lower() or "deadline" in block.text.lower()


def test_a_contradiction_is_rewritten_once_and_then_served(
        tmp_path, monkeypatch):
    """ONE REPAIR. The step is not abandoned for a fixable wording, and it is
    not rewritten until it passes — a second failure is evidence about the
    step rather than about the words.
    """
    out = _run(tmp_path, monkeypatch, _verdicts(_contradicts, _clean))

    action = _action(out)
    assert action is not None, "a repairable step was thrown away"
    assert action.text == REPAIRED, (
        f"the step served was not the rewrite: {action.text!r}")
    assert _states(out) == ["repaired"]
    assert _blocked(out) is None


def test_a_rewrite_that_still_contradicts_is_not_served(tmp_path, monkeypatch):
    """THE BOUND ON THE REPAIR, and the reason there is no third attempt."""
    out = _run(tmp_path, monkeypatch, _verdicts(_contradicts, _contradicts))

    assert _action(out) is None
    assert _blocked(out) is not None
    assert _states(out) == ["contradicted"]


# ============================================ and the four that must serve ==

def test_a_read_that_finds_nothing_serves_the_step(tmp_path, monkeypatch):
    """The ordinary turn, and the one this gate must not disturb."""
    out = _run(tmp_path, monkeypatch, _verdicts(_clean))

    assert _action(out) is not None
    assert _states(out) == ["consistent"]


def test_a_read_that_names_a_fact_it_was_not_shown_serves_the_step(
        tmp_path, monkeypatch):
    """EXACT MEMBERSHIP, failing toward serving.

    An id that is not among the claims names nothing — the answer space is
    the turn's own computed facts, a closed set built moments earlier. The
    refusal is RECORDED rather than acted on, so a read that keeps failing
    its own guard is visible without being able to delete advice.
    """
    out = _run(tmp_path, monkeypatch, _verdicts(
        lambda claims, step: {"claim_id": "not_a_computed_fact",
                              "quoted": " ".join(step.split()[:4]),
                              "why": "invented"}))

    assert _action(out) is not None, "an unoffered id suppressed a sound step"
    assert _states(out) == ["consistent"]
    assert any("not one of the computed facts" in v.detail
               for v in out.metrics.violations), (
        "the guard refused silently — nothing recorded that the read misfired")


def test_a_read_that_cannot_quote_the_step_serves_it(tmp_path, monkeypatch):
    """A contradiction nobody can point at is not one the advocate can check.

    It is also the shape a model produces when asked a yes/no question it
    would rather answer yes to, which is why the quotation is required and
    why failing it does not block.
    """
    out = _run(tmp_path, monkeypatch, _verdicts(
        lambda claims, step: {"claim_id": claims[0],
                              "quoted": "words that appear nowhere in it",
                              "why": "unpointable"}))

    assert _action(out) is not None
    assert _states(out) == ["consistent"]
    assert any("not in the step" in v.detail for v in out.metrics.violations)


def test_a_read_that_could_not_run_serves_the_step_and_says_so(
        tmp_path, monkeypatch):
    """THE THIRD STATE, and it is served differently from both others.

    A check that could not run must not become a check that passed (S1), and
    must not become a refusal either — an unavailable model would then delete
    the advice on a turn where nothing is wrong.
    """
    class _Down(ScriptedModelAdapter):
        def structured(self, prompt, schema, tier, **kw):
            if schema.get("x-nm-read") == "consistency":
                raise ModelError("the consistency read is unavailable")
            return super().structured(prompt, schema, tier, **kw)

    out = _run(tmp_path, monkeypatch,
               model=_Down(_model_config(), responses=RESPONSES))

    assert _action(out) is not None, (
        "an unavailable consistency read deleted a sound step")
    assert _states(out) == ["not_verified"], (
        "a read that could not run is indistinguishable from one that passed")


# =========================================== the claims, drawn from the code ==

@pytest.mark.parametrize("state", ["computed", "not_computed", "not_applicable"])
def test_every_limitation_state_becomes_a_claim(state):
    """A COMPUTED FACT NEVER FAILS TO BECOME A CLAIM.

    The population is the typed facts, and a branch that produced no claim
    would make the step uncheckable against that fact — silently, and only
    for that state. That is S1 in the gate's own machinery: the check would
    report `consistent` because it had nothing to compare against, and
    nothing would say so.
    """
    from nm.core import limitation
    from nm.core.consistency import claims_for
    from nm.domain.matter import Side

    made = {
        "computed": limitation.compute(
            for_side=Side.MOVING, article="Limitation Act, 1963 Article 14",
            accrual="fact_1", accrual_on=date(2024, 1, 1),
            accrual_reason="the delivery", chronology=("fact_1",),
            period=limitation.period_in("...three years.")),
        "not_computed": limitation.not_computed(
            Side.MOVING, "no Article was retrieved", ("fact_1",)),
        "not_applicable": limitation.not_applicable(
            Side.DEFENDING, "they have brought no claim"),
    }[state]

    claims = claims_for(made, None, "plaintiff", TODAY)
    ids = [c.id for c in claims]
    assert "limitation" in ids, (
        f"a {state} position produces no claim, so no step can be checked "
        f"against it")
    assert all(c.sentence.strip() for c in claims)


def test_an_absent_register_is_a_claim_and_not_a_silence():
    """`None` REGISTER IS A FACT ABOUT THIS TURN, not the absence of one.

    A step that says "file within the window" on a turn where no register was
    computed is contradicting something real — that nothing established a
    window either way — and dropping the claim would let exactly that
    sentence through.
    """
    from nm.core.consistency import claims_for

    ids = [c.id for c in claims_for(None, None, "plaintiff", TODAY)]
    assert "register" in ids
    assert "side" in ids
