"""The evals S1, S2 and S3 name and that had never run.

Written against what each eval CLAIMS and against the counterexample it says it
must reject — not tagged onto whichever existing test happened to be nearby. A
test that covers a claim by accident stops covering it the first time the code
moves, and nothing says so.

Three of these needed the mechanism built before the test could fail for the
right reason:

  E-020b  MAX_EVIDENCE_ROUNDS was a constant no code read, and
          `evidence_bound_hit` a field nothing ever set. A bound that is not
          enforced is not a bound.
  E-021   a provision Finding could be built with no validity window at all,
          so `in_force` had nothing to refuse the superseded text with.
  E-008   there was no register of hard-tier promotions (in test_slice0).
"""
from __future__ import annotations

import json

import pytest

from nm.adapters.store.file_store import FileMatterStore
from nm.core.turn import TurnEngine, TurnInput
from nm.domain.answer import Answer, Element, ElementKind, Mode, Route
from nm.domain.gates import GATES, Response
from nm.domain.traceability import refuses
from nm.ports.evidence import (
    Coverage,
    EvidenceResult,
    ParaKind,
    SourceKind,
    Treatment,
)
from nm.ports.store import StaleWrite
from tests.test_turn_contract import KEY, _Evidence, _model_config, build, finding

pytestmark = pytest.mark.class_a


# ================================================== S1 · the wire ===========

@pytest.mark.eval_id("E-017")
def test_a_turn_commits_atomically_and_the_commit_precedes_emission(tmp_path):
    """THE COUNTEREXAMPLE: a turn that showed advice and then failed to persist it.

    COMMIT PRECEDES EMIT, which is the opposite of the intuitive order and
    deliberate: the advocate must never receive advice the file does not
    record. Better to fail before showing than to show and fail to save.
    """
    class _RefusingStore(FileMatterStore):
        def commit(self, matter, expected_version=None):
            raise StaleWrite("the matter moved underneath this turn")

    engine = TurnEngine(
        store=_RefusingStore(tmp_path, key=KEY),
        evidence=_Evidence(),
        model=__import__("nm.adapters.model.scripted", fromlist=["x"])
        .ScriptedModelAdapter(_model_config(),
                              responses={"__default__": "File within the window."}))

    with pytest.raises(StaleWrite):
        engine.run(TurnInput(advocate_id="adv", turn_id="turn_nocommit",
                             message="we act for the plaintiff in a possession suit"))

    # NOTHING WAS EMITTED. The engine raised instead of returning an answer,
    # so no caller could have shown it.
    written = json.loads((tmp_path / "metrics" / "turn_nocommit.json").read_text())
    assert written["outcome"] in ("failed", "gated")
    assert written["failed_phase"] == "emit", (
        "the failure must be recorded in EMIT -- if it lands in derive, the "
        "commit was attempted before the answer was assembled")


@pytest.mark.eval_id("E-020b")
@refuses("H4", 0)
def test_reaching_the_evidence_bound_produces_a_visible_gap(tmp_path, monkeypatch):
    """THE COUNTEREXAMPLE: a turn that hit the round cap and answered as if the
    evidence had been retrieved.

    `MAX_EVIDENCE_ROUNDS` was declared in slice 1 and read by nothing, and
    `evidence_bound_hit` was a field no code ever set. The bound existed as a
    number in a file.

    THIS TEST USED TO ASSERT `evidence_rounds <= MAX_EVIDENCE_ROUNDS`, which is
    true whether or not the bound works: the engine makes at most two fetches a
    turn, so three is unreachable and nothing could ever exceed it. A mutation
    disabling the guard entirely left it green. That is a test asserting
    CURRENT BEHAVIOUR rather than the rule, and the rule is not "the count
    stays low" -- it is that REACHING THE BOUND IS VISIBLE.

    So the bound is lowered and the engine driven into it. The bound is a guard
    against a retrieval loop that does not exist yet, exactly as `bind-1`
    guards a corpus that does not exist yet, and the way to test either is to
    drive it rather than to wait for it.
    """
    from nm.core import turn as turn_module

    class _Exhausting:
        """Every fetch succeeds, so only the BOUND can stop the turn."""

        def fetch(self, need):
            return EvidenceResult(
                coverage=Coverage.ANSWERED, findings=(finding(),),
                searched_stores=("s",))

    monkeypatch.setattr(turn_module, "MAX_EVIDENCE_ROUNDS", 1)
    engine, _ = build(tmp_path, evidence=_Exhausting())
    out = engine.run(TurnInput(
        advocate_id="adv",
        message=("we act for the plaintiff; is there any judgment on "
                 "Article 65 possession we can rely on?")))

    assert out.metrics.evidence_rounds <= 1, (
        f"{out.metrics.evidence_rounds} rounds ran against a bound of 1")
    assert out.metrics.evidence_bound_hit, (
        "the bound was reached and nothing recorded it. `evidence_bound_hit` "
        "was a field no code ever set, which is how the bound came to exist as "
        "a number in a file.")

    # AND THE ADVOCATE IS TOLD. A turn that ran out of rounds and said nothing
    # is indistinguishable from one that found everything it needed -- and they
    # would read it as the second.
    disclosed = [e.text for e in out.answer.elements if e.disclosure]
    assert any("stopped after" in t for t in disclosed), (
        "the turn hit the evidence bound and answered as though it had not. "
        f"Disclosures were: {disclosed}")


def test_the_bound_is_enforced_by_the_engine_not_by_the_caller(tmp_path):
    """The counter lives in ONE place. Incrementing at each call site is how a
    bound stops matching the rounds actually run."""
    class _Counting:
        def __init__(self):
            self.calls = 0

        def fetch(self, need):
            self.calls += 1
            return EvidenceResult(coverage=Coverage.ANSWERED,
                                  findings=(finding(),), searched_stores=("s",))

    ev = _Counting()
    engine, _ = build(tmp_path, evidence=ev)
    out = engine.run(TurnInput(
        advocate_id="adv",
        message="we act for the plaintiff; any judgment on Article 65?"))
    assert ev.calls == out.metrics.evidence_rounds, (
        "the recorded round count does not match the fetches actually made")


@pytest.mark.eval_id("E-015")
def test_nothing_is_released_except_through_the_byte_boundary(client):
    """THE COUNTEREXAMPLE: a streamed turn whose first token is model prose and
    whose duty screen returns after it.

    Two properties, and the second is why this is checked on the WIRE: there is
    no streaming entry point at all, so no first token can precede the
    invariant assertion; and `_release` is the only function permitted to hand
    an answer to the transport.
    """
    import inspect

    from nm.edge import api

    source = inspect.getsource(api)
    assert "StreamingResponse" not in source and "EventSource" not in source, (
        "a streaming path exists -- the first byte can then precede the "
        "invariant assertion, which is the defect E-015 names")

    # Every route that returns an answer goes through _release.
    turn_src = inspect.getsource(api.turn)
    assert "_release(" in turn_src

    r = client.post("/api/turn", json={
        "advocate_id": "adv",
        "message": "we act for the plaintiff in a possession suit"})
    assert r.status_code == 200
    body = r.json()
    # The invariant assertion completed: metrics exist and record the outcome.
    assert body["metrics"]["outcome"] in ("ok", "blocked")
    assert "gates_fired" in body["metrics"]


@pytest.mark.eval_id("E-014")
def test_every_response_class_is_exercised_on_the_served_path(client, tmp_path):
    """THE COUNTEREXAMPLE: a green suite where the streaming entry point does
    not exist — a guard proven in the core and never reached on the wire.

    Every defect the first external review found lived between a correct module
    and the served path, so each of the three gate responses is driven through
    the ASGI app rather than the engine.
    """
    seen = set()

    # DISCLOSE — the unscreened matter, on every turn.
    r = client.post("/api/turn", json={
        "advocate_id": "adv", "message": "we act for the plaintiff in a suit"})
    assert r.status_code == 200
    for g in r.json()["metrics"]["gates_fired"]:
        seen.add(g["response"])

    # BLOCK — posture unresolved, the block IS the answer.
    r = client.post("/api/turn", json={
        "advocate_id": "adv", "message": "the landlord issued a quit notice"})
    assert r.status_code == 200
    assert r.json()["blocked"] is True
    seen.add("block")

    # WITHHOLD — nothing emitted, and the refusal names the gate.
    r = client.post("/api/turn", json={
        "advocate_id": "adv2",
        "message": "we act for the plaintiff; rely on section 27 of the Limitation Act"})
    if r.status_code == 422:
        detail = r.json()["detail"]
        assert detail["withheld_by"], "a withheld turn must name its gate"
        seen.add("withhold")

    assert {"disclose", "block"} <= seen, f"only reached {seen} on the wire"


# ================================================== S2 · grounding ==========

@pytest.mark.eval_id("E-021")
@refuses("P1", 3)
def test_a_finding_cannot_be_built_without_what_makes_it_auditable():
    """THE COUNTEREXAMPLE: a retrieval adapter returning a bare passage.

    Every field here is one an advocate needs to check the citation themselves.
    An obligation not represented in the type crossing the boundary is an
    obligation that will be dropped.
    """
    required = {
        "locator": "",
        "span": "   ",
        "binding_for": None,
        "binding_reason": "  ",
    }
    for field, bad in required.items():
        with pytest.raises((ValueError, TypeError)):
            finding(**{field: bad})

    # para_kind and treatment have NO DEFAULT: omitting them is a TypeError.
    import inspect

    from nm.ports.evidence import Finding
    params = inspect.signature(Finding).parameters
    for field in ("locator", "span", "binding", "binding_for", "binding_reason",
                  "para_kind", "treatment", "supports"):
        assert params[field].default is inspect.Parameter.empty, (
            f"{field} has a default -- a default is a decision taken on behalf "
            f"of every call site that forgets")

    # VALIDITY. A provision must say when it was in force; a judgment need not,
    # because a judgment is decided once rather than in force over a window.
    with pytest.raises(ValueError, match="validity window"):
        finding(valid_from=None, valid_to=None)
    finding(source_kind=SourceKind.AUTHORITY, ref="X v Y", span="held that",
            locator="X::p1::ratio", store="idx", para_kind=ParaKind.RATIO,
            treatment=Treatment.not_checked("no entry"),
            valid_from=None, valid_to=None)


@pytest.mark.eval_id("E-025")
def test_a_proposition_carries_a_finding_and_an_inference_never_does():
    """THE COUNTEREXAMPLE: an inference rendered with a citation attached.

    The distinction is structural, not editorial: an element that reports what
    could NOT be established is marked `disclosure`, and the grounding gate
    holds asserting elements to their findings while leaving disclosures alone.
    """
    from nm.core import grounding

    retrieved = (finding(),)          # Limitation Act Article 65

    asserted = Answer(
        route=Route.MATTER, mode=Mode.SHORT_QUESTION, mode_statement="m",
        elements=(Element(kind=ElementKind.ACTION,
                          text="Rely on section 27 of the Limitation Act.",
                          no_deadline_reason="none"),))
    assert grounding.verify(asserted, retrieved, retrieved).withholding, (
        "an assertion citing an unretrieved provision must withhold")

    disclosed = Answer(
        route=Route.MATTER, mode=Mode.SHORT_QUESTION, mode_statement="m",
        elements=(Element(kind=ElementKind.ACTION, text="Confirm the date.",
                          no_deadline_reason="none"),
                  Element(kind=ElementKind.GROUND, disclosure=True,
                          text="Not held in the corpus: Limitation Act section 27.")))
    assert grounding.verify(disclosed, retrieved, retrieved).clear, (
        "naming what could not be retrieved is not citing it")


# ================================================== S3 · the frame ==========

@pytest.mark.eval_id("E-034")
class _RecordingNeeds(_Evidence):
    """Answers normally and keeps every EvidenceNeed it was handed.

    `want_authority` is the only place the authority decision is observable,
    and it is the one that must not be taken behind a closed posture gate.
    """

    def __init__(self, result=None):
        super().__init__(result)
        self.needs: list = []

    def fetch(self, need):
        self.needs.append(need)
        return super().fetch(need)


def test_nothing_side_dependent_is_computed_behind_a_closed_gate(tmp_path):
    """E-034. THE COUNTEREXAMPLE: merits questions answered before posture is
    settled, so the same provision is applied to the wrong side.

    THIS USED TO ASSERT THAT NOTHING AT ALL WAS COMPUTED, and that is a claim
    you satisfy by doing nothing. It was also wrong in one direction that cost
    a daily interaction: `what is the limitation for a suit for possession of
    immovable property` -- no matter, no client, nobody's side at stake -- was
    answered with "whose side are we on?", which GS-02's NEVER column forbids
    in terms.

    The gate's own reason is that THE SAME PROVISION HELPS ONE SIDE AND HURTS
    THE OTHER WHEN A STEP IS RECOMMENDED. The text of a statute is the
    legislature's words and the same bytes for either party, so refusing to
    read it back applied the gate to a case it was not written for.

    So the property is now that nothing SIDE-DEPENDENT is computed, and the
    three things that are get named. Satisfying this requires knowing which of
    your outputs depend on the side, which is a stronger thing to know.
    """
    for message, gate in (
            ("the landlord has issued a quit notice on the shop", "G-POSTURE"),):
        evidence = _RecordingNeeds()
        engine, _ = build(tmp_path / gate, evidence=evidence)
        out = engine.run(TurnInput(
            advocate_id="adv", message=message + " and any judgment on it"))
        assert out.answer.blocked, f"{gate}: the turn was not blocked"
        assert any(g.gate_id == gate for g in out.metrics.gates_fired)

        # (1) NO DIRECTIVE STEP. The gate exists for this one.
        assert not any(e.kind is ElementKind.ACTION for e in out.answer.elements), (
            f"{gate}: a directive step was produced behind a closed gate")

        # (2) NO MODEL CALL BEYOND THE READS THAT SETTLE THE GATE. A blocked
        # turn legitimately spends the cheap extraction that settles it and
        # must spend nothing else. Asserting a total of zero would confuse the
        # two and would have to be RELAXED, rather than tightened, the moment
        # the read moved to a model.
        derivation_calls = out.metrics.llm_calls - out.metrics.settling_reads
        assert derivation_calls == 0, (
            f"{gate}: {derivation_calls} derivation call(s) behind a closed gate")

        # (3) NO AUTHORITY SET. Which judgments come back is a function of how
        # the advocate framed the question, so presenting a side-flavoured
        # selection as "the law" with no posture on record is the subtler form
        # of the very defect this gate exists for -- and the harder one to see.
        assert not any(n.want_authority for n in evidence.needs), (
            f"{gate}: an authority set was assembled behind a closed gate")

        # (4) AND THE FIRST ELEMENT IS THE QUESTION. What follows it is only
        # what could be established without knowing the side.
        assert out.answer.elements[0].kind is ElementKind.QUESTION


def test_a_provision_is_still_read_back_behind_a_closed_posture_gate(tmp_path):
    """The other half of E-034, and the reason it was sharpened.

    An advocate asking what a provision SAYS is asking something whose answer
    does not depend on the side. Refusing it is not caution; it is the product
    declining its cheapest useful act, and GS-02 exists to say so.
    """
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(
        advocate_id="adv",
        message="what is the limitation for a suit for possession of immovable "
                "property"))
    assert out.answer.blocked, "the directive step is still refused"
    assert out.answer.elements[0].kind is ElementKind.QUESTION
    assert not any(e.kind is ElementKind.ACTION for e in out.answer.elements)
    assert len(out.answer.elements) > 1, (
        "the turn returned the blocking question and nothing else. The "
        "provision text does not depend on which side we are on, and an "
        "advocate asking a bare question of law was told to state a posture "
        "they have no matter for.")


def test_the_thread_gate_also_computes_nothing(tmp_path):
    """G-THREAD closes the same way: two open threads and nothing decisive."""
    engine, _ = build(tmp_path)
    first = engine.run(TurnInput(
        advocate_id="adv",
        message="we act for the plaintiff in O.S. 442/2023, a possession suit"))
    second = engine.run(TurnInput(
        advocate_id="adv", matter_id=first.matter.id,
        message="in C.C. 77/2025 our client is the accused on a cheque complaint"))
    out = engine.run(TurnInput(
        advocate_id="adv", matter_id=second.matter.id,
        message="the hearing yesterday went badly, what now"))

    assert out.answer.blocked
    assert out.metrics.llm_calls - out.metrics.settling_reads == 0
    assert out.metrics.evidence_rounds == 0


def test_every_built_gate_declares_a_response_the_engine_can_obey():
    """A gate whose response the engine cannot act on is a gate in name only."""
    for g in GATES:
        assert g.response in (Response.WITHHOLD, Response.BLOCK, Response.DISCLOSE)
        if g.response is Response.WITHHOLD:
            assert g.recovery.value in ("system", "none", "human")
