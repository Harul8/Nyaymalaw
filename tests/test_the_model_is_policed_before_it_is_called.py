"""NOTHING REACHES A PROVIDER THAT THE POLICY DID NOT PERMIT. BK-85-AC1. P06.

`nm/domain/egress.py` decides. This is about whether the decision is actually
IN FRONT of the thing it governs — which is a different question, and the one
CLAUDE.md §8 says every external review found the product failing: *a guard
that is right in the core and wrong in the composition root is not a guard.*

A policy module with a green unit suite and no caller refuses nothing at all.

WHAT IS ASSERTED HERE
-----------------------
    the composition root wraps the model in the policy
    the policy is OUTSIDE the tracer, so a refusal never reaches the provider
    a refused dispatch RAISES rather than returning an empty result
    the refusal and the audit line carry no prompt text
    an unlisted provider is refused even though the model would have answered

THE LAST ONE IS THE POINT. `ScriptedModelAdapter` answers whatever it is asked.
If the wrapper were absent or wired inside the tracer, every test below would
still see a perfectly good answer come back.
"""
from __future__ import annotations

import pathlib

import pytest

from nm.adapters.model.policed import EgressRefused, PolicedModel
from nm.bootstrap.egress_policy import egress_policy
from nm.domain.egress import DataClass, Policy, Processor, Sink

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]


class _Recording:
    """A provider that records what it was asked, so an escape is visible."""

    def __init__(self, name: str = "scripted") -> None:
        self._name = name
        self.calls: list[str] = []

    @property
    def provider(self) -> str:
        return self._name

    def resolved_model(self, tier):
        return "recording"

    def context_budget(self, tier):
        return 1000

    def complete(self, prompt, tier, *, max_tokens=None):
        self.calls.append("complete")
        return "answered"

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.calls.append("structured")
        return {"answered": True}

    def embed(self, texts):
        self.calls.append("embed")
        return ("vector",)


class _Prompt:
    def __init__(self, user: str) -> None:
        self.user = user


SECRET = "the client admitted the possession began in March 2011"
APPROVED = Policy(processors=(Processor(
    processor_id="scripted", region="in", purposes=(Sink.MODEL,),
    data_classes=(DataClass.CLIENT_MATTER,), approval_id="IN-PROCESS-NO-EGRESS"),))


# ============================ the negative control ==========================

def test_an_approved_provider_is_called_normally():
    """Without this, a wrapper that refused everything satisfies the file and
    the product answers nothing."""
    inner = _Recording()
    model = PolicedModel(inner=inner, policy=APPROVED)
    assert model.complete(_Prompt("hello"), tier=None) == "answered"
    assert inner.calls == ["complete"]


# ========================== what never reaches out ==========================

@pytest.mark.parametrize("call", ["complete", "structured", "embed"])
def test_an_unlisted_provider_is_refused_before_the_call(call):
    """THE POINT OF THE FILE. The adapter would have answered."""
    inner = _Recording(name="some-foreign-provider")
    model = PolicedModel(inner=inner, policy=APPROVED)
    with pytest.raises(EgressRefused):
        if call == "complete":
            model.complete(_Prompt(SECRET), tier=None)
        elif call == "structured":
            model.structured(_Prompt(SECRET), {}, tier=None)
        else:
            # EMBEDDING IS EGRESS TOO. The vectors come back; the sentences
            # went. `TracedModel` deliberately does not trace this call, which
            # is a different question with a different answer -- and the first
            # draft of the wrapper skipped it for the same reason and left an
            # unpoliced route that worked.
            model.embed((SECRET,))
    assert inner.calls == [], "the provider was called despite the refusal"


def test_a_refusal_raises_and_never_returns_an_empty_answer():
    """A refused dispatch returning the shape of a clean result is the single
    most repeated defect in this codebase, holding client material."""
    model = PolicedModel(inner=_Recording(name="elsewhere"), policy=APPROVED)
    with pytest.raises(EgressRefused) as refused:
        model.complete(_Prompt(SECRET), tier=None)
    assert "does not permit" in str(refused.value)


def test_neither_the_refusal_nor_the_audit_quotes_the_prompt():
    """The whole argument for deciding on the route is that the refusal can
    then say everything useful without quoting anything privileged."""
    written: list[str] = []
    model = PolicedModel(inner=_Recording(name="elsewhere"), policy=APPROVED,
                         audit=written.append)
    with pytest.raises(EgressRefused) as refused:
        model.complete(_Prompt(SECRET), tier=None)

    assert written, "nothing was audited"
    for text in (str(refused.value), *written):
        assert SECRET not in text
        assert "possession" not in text
        assert "2011" not in text
    assert "bytes=" in written[0] and "REFUSED" in written[0]


def test_a_permitted_dispatch_is_audited_too():
    """An audit that only records refusals cannot answer *where has this
    matter's material been sent*, which is the question after an incident."""
    written: list[str] = []
    PolicedModel(inner=_Recording(), policy=APPROVED,
                 audit=written.append).complete(_Prompt(SECRET), tier=None)
    assert written and "permitted" in written[0]
    assert SECRET not in written[0]


def test_refusals_are_counted_so_a_closed_policy_is_visible():
    """A policy refusing everything must read as a number here rather than as
    an outage somebody diagnoses from the other end."""
    model = PolicedModel(inner=_Recording(name="elsewhere"), policy=APPROVED)
    for _ in range(3):
        with pytest.raises(EgressRefused):
            model.complete(_Prompt("x"), tier=None)
    assert len(model.refused) == 3


# ===================== it is wired, not merely written ======================

def test_the_composition_root_puts_the_policy_in_front_of_the_provider():
    """CLAUDE.md §8. A policy module with a green suite and no caller refuses
    nothing, and that is how every defect the first external review found
    reached a served turn."""
    import inspect

    from nm.bootstrap import composition

    source = inspect.getsource(composition.Application.__init__)
    assert "PolicedModel(" in source, (
        "the composition root does not wrap the model in the egress policy")
    wiring = source[source.index("PolicedModel("):]
    wiring = wiring[:wiring.index("self.coverage")]
    assert "TracedModel(" in wiring, "the tracer is not inside the policy"
    assert wiring.index("PolicedModel(") < wiring.index("TracedModel("), (
        "the tracer wraps the policy rather than the other way round, so a "
        "refused dispatch would reach the provider before being refused")


def test_the_live_inventory_permits_only_what_it_records():
    """The file this installation actually runs under, not a fixture."""
    policy = egress_policy(ROOT)
    assert policy.processors, "the inventory is empty, so this asserts nothing"
    # THE RULE, NOT A SNAPSHOT OF THE LIST. `== {"scripted"}` asserted current
    # behaviour, so adding the storage and index destinations broke it while
    # breaking nothing it was written to protect -- CLAUDE.md section 2: a
    # test that asserts current behaviour is not an invariant. What must hold
    # is that NOTHING OUTSIDE THIS MACHINE has been approved, which is a
    # property of each row rather than of the set.
    assert policy.approved_foreign_regions == {}, (
        "a foreign region is admitted; it needs a named legal review")
    for row in policy.processors:
        assert row.approval_id, f"{row.processor_id} is listed with no approval"
        assert row.region == "in", f"{row.processor_id} operates elsewhere"
        assert row.approval_id == "IN-PROCESS-NO-EGRESS", (
            f"{row.processor_id} is approved under {row.approval_id!r}, which "
            f"is not the in-process approval. A third-party processor needs "
            f"CHOICE-03 adopted, and `tools/blueprint.py readiness` still "
            f"reports it not_recorded.")


def test_the_in_process_adapter_is_recorded_rather_than_branched_around():
    """`scripted` is permitted because the inventory says so, not because
    `PolicedModel` skips some providers. A code path that bypasses the policy
    for one adapter is one somebody extends to an adapter that does egress."""
    import inspect

    source = inspect.getsource(PolicedModel)
    for escape in ("scripted", "in_process", "skip", "bypass"):
        assert escape not in source, (
            f"PolicedModel branches on {escape!r} instead of consulting the "
            f"inventory")


def test_a_real_provider_is_refused_by_the_live_inventory():
    """Nothing is approved for external egress yet, and that is the state the
    product should be in until CHOICE-03 has an adoption record."""
    policy = egress_policy(ROOT)
    model = PolicedModel(inner=_Recording(name="openai"), policy=policy)
    with pytest.raises(EgressRefused) as refused:
        model.complete(_Prompt(SECRET), tier=None)
    assert "not in the reviewed inventory" in str(refused.value)


def test_the_policy_answers_the_whole_port_it_wraps():
    """The policy must not change what the core sees, or wrapping would be a
    behaviour change disguised as a control.

    Checked against the PORT rather than by composing a real `TracedModel`:
    this file's recording double returns a bare string where the tracer wants a
    `ModelResult`, and building one here would test the fixture. The wiring
    order is asserted above; the served path is exercised by every turn test.
    """
    from nm.ports.model import ModelPort

    required = [name for name in dir(ModelPort)
                if not name.startswith("_")]
    assert required, "the port exposes nothing, so this checks nothing"
    for name in required:
        assert hasattr(PolicedModel, name), (
            f"PolicedModel does not answer {name!r}, so wrapping the model "
            f"would break the core rather than police it")

    inner = _Recording()
    model = PolicedModel(inner=inner, policy=APPROVED)
    assert model.provider == "scripted"
    assert model.context_budget(None) == 1000
    assert model.resolved_model(None) == "recording"
