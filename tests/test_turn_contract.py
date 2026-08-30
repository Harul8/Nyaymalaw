"""The turn contract. PRD §7.3.

Every test here is a COUNTEREXAMPLE from the previous build made runnable. The
tests are written against the SERVED PATH wherever the property is about the
wire, because a guard that is right in the core and wrong at the edge is not a
guard -- and every defect the first external review found lived in that gap.
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from nm.adapters.model.config import ModelConfig, TierConfig
from nm.adapters.model.scripted import ScriptedModelAdapter
from nm.adapters.store.file_store import EncryptionNotConfigured, FileMatterStore
from nm.core.posture import interpret
from nm.core.turn import TurnEngine, TurnInput, classify_route
from nm.domain.answer import Element, ElementKind, Route, Signal
from nm.domain.matter import Basis, Matter, Posture, Role, Side, Thread
from nm.domain.traceability import refuses
from nm.ports.evidence import (
    Binding,
    Coverage,
    EvidenceResult,
    Finding,
    ParaKind,
    SourceKind,
    Treatment,
)
from nm.ports.model import Tier
from nm.ports.store import StaleWrite

pytestmark = pytest.mark.class_a

KEY = "test-key-not-a-secret"


def _model_config() -> ModelConfig:
    return ModelConfig(tiers={
        Tier.ROUTINE: TierConfig(Tier.ROUTINE, "scripted", "scripted-1", None, None),
        Tier.EMBED: TierConfig(Tier.EMBED, "scripted", "text-embedding-3-large", None, None),
    })


def finding(**kw) -> Finding:
    """A Finding with every required field filled.

    A helper, not a default. The slice-2 contract removed the defaults from
    `binding`, `para_kind` and `treatment` precisely because a default is a
    decision taken on behalf of every call site that forgets -- so this fills
    them EXPLICITLY and each test overrides what it is actually testing.
    """
    base = dict(
        proposition="Limitation Act, 1963 Article 65",
        source_kind=SourceKind.PROVISION,
        ref="Limitation Act, 1963 Article 65",
        span="For possession of immovable property... twelve years.",
        locator="the_limitation_act_1963::Article_65::schedule_article",
        store="the_limitation_act_1963",
        binding=Binding.BINDING,
        binding_for="Telangana",
        binding_reason="an Act of Parliament in force, applying of its own force",
        supports=True,
        para_kind=ParaKind.UNKNOWN,
        treatment=Treatment.statutory(),
        # A PROVISION must carry its validity window [E-021]. Without it
        # `in_force` cannot refuse superseded text, and the 2024 codes make
        # that the difference between right and confidently wrong.
        valid_from=date(1964, 1, 1),
    )
    base.update(kw)
    return Finding(**base)


class _Evidence:
    def __init__(self, result: EvidenceResult | None = None):
        self.result = result or EvidenceResult(
            coverage=Coverage.ANSWERED,
            findings=(finding(),),
            searched_stores=("the_limitation_act_1963",))

    def fetch(self, need):
        return self.result


def build(tmp_path, evidence=None, responses=None):
    store = FileMatterStore(tmp_path, key=KEY)
    model = ScriptedModelAdapter(
        _model_config(),
        responses=responses or {
            "__default__": "File the summary possession suit within six months."})
    return TurnEngine(store=store, evidence=evidence or _Evidence(), model=model), store


# ======================================================= routing ==========

@refuses("B1", 0)
@pytest.mark.eval_id("E-012")
def test_route_is_not_decided_on_message_length():
    """COUNTEREXAMPLE: 'police arrested my son tonight' read as a greeting
    because it is five words -- measured live, in both directions."""
    route, _, _ = classify_route("police picked up my client last night")
    assert route is Route.MATTER, "a five-word emergency is a matter"

    route2, _, _ = classify_route(
        "what areas of law do you cover and how do you work with an advocate")
    assert route2 is Route.NON_MATTER, "a long question about NM is not a matter"


@pytest.mark.eval_id("E-012")
def test_a_greeting_writes_nothing_to_any_file(tmp_path):
    engine, store = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv", message="hi"))
    assert out.answer.route is Route.NON_MATTER
    assert out.matter is None
    assert store.list_for("adv") == (), "the non-matter route persists nothing"


# ======================================================= posture ==========

@refuses("C3", 1)
@pytest.mark.eval_id("E-030")
def test_posture_is_never_inferred_from_familiar_vocabulary():
    """C3, and it survives the move to a model reading the posture.

    "The landlord has issued a quit notice" names a landlord and says NOTHING
    about which side the client is on. The measured defect there told an
    employer he could claim reinstatement from himself -- every citation
    correct, the whole analysis on the wrong side.

    The phrase list is gone: it could never cover the ways an advocate states
    a client, and an advocate whose words were missing from it was asked the
    same question forever. What replaces it is not trust. A model reads the
    posture and TWO GUARDS refuse what the message does not support -- the
    quoted span must be the advocate's actual words, and it must speak of the
    representation rather than the events.
    """
    message = "the landlord has issued a quit notice to the tenant"

    # Even if the model claims a posture, the span describes EVENTS and is
    # refused: the guard is on grammar, not on which nouns appear.
    stated = interpret(message, {
        "states_client": True, "role": "plaintiff",
        "client_described_as": "landlord",
        "quoted": "the landlord has issued a quit notice"})
    assert stated.role is Role.UNKNOWN
    assert "describes events" in stated.refused

    # And a span that is not in the message at all cannot settle anything.
    invented = interpret(message, {
        "states_client": True, "role": "plaintiff",
        "client_described_as": "", "quoted": "we act for the landlord"})
    assert invented.role is Role.UNKNOWN
    assert "not in the message" in invented.refused


def test_an_advocate_who_states_their_client_is_understood_however_they_say_it():
    """THE LOOP THIS REPLACED. Ten exact phrases meant "we act for the workman"
    left posture unresolved and the same question asked again."""
    for message, role, described in (
            ("we act for the plaintiff in O.S. 442/2023", Role.PLAINTIFF, None),
            ("we represent the second respondent", Role.RESPONDENT, None),
            ("appearing on behalf of the caveator", Role.UNKNOWN, "caveator"),
            ("we act for the workman", Role.UNKNOWN, "workman"),
    ):
        data = {"states_client": True,
                "role": role.value if role is not Role.UNKNOWN else "not_stated",
                "client_described_as": described or "",
                "quoted": message}
        stated = interpret(message, data)
        assert stated.refused is None, f"{message}: {stated.refused}"
        assert stated.role is role
        assert stated.client_described_as == described


def test_a_role_outside_the_products_vocabulary_is_blanked():
    """PRD D9: an out-of-vocabulary facet value is blanked and re-derived,
    never accepted. A model returning a role this product cannot reason about
    must not set one."""
    stated = interpret("we act for the amicus", {
        "states_client": True, "role": "amicus curiae",
        "client_described_as": "", "quoted": "we act for the amicus"})
    assert stated.role is Role.UNKNOWN
    assert "not a role this product knows" in stated.refused


@pytest.mark.eval_id("E-031")
def test_side_is_derived_from_role_and_never_stored():
    assert Posture(role=Role.PLAINTIFF).side is Side.MOVING
    assert Posture(role=Role.ACCUSED).side is Side.DEFENDING
    assert Posture().side is Side.UNKNOWN
    assert not hasattr(Posture(), "_side")


@refuses("C3", 2)
def test_a_stated_posture_is_never_silently_flipped():
    """COUNTEREXAMPLE: a turn-5 reversal is worse than a turn-1 error, because
    by then the advocate has acted on it."""
    p = Posture().enrich(Role.ACCUSED, Basis.STATED)
    flipped = p.enrich(Role.COMPLAINANT, Basis.STATED)
    assert flipped.role is Role.ACCUSED, "the posture on record must not change"
    assert flipped.conflicts, "the contradiction must surface as a conflict"


@pytest.mark.eval_id("E-030")
def test_unresolved_posture_blocks_the_directive_step(tmp_path):
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(
        advocate_id="adv",
        message="there is a cheque matter and a possession dispute on this file"))
    first = out.answer.elements[0]
    assert first.kind is ElementKind.QUESTION
    assert first.signal is Signal.UNRESOLVED_POSTURE
    assert out.answer.blocked
    assert not any(e.kind is ElementKind.ACTION for e in out.answer.elements), \
        "no directive step may be produced behind a closed gate"


# ================================================== the Answer type =======

@pytest.mark.eval_id("E-012")
def test_no_element_kind_can_hold_a_recital():
    assert {k.value for k in ElementKind} == {"action", "finding", "question", "ground"}


def test_an_action_without_a_by_when_cannot_be_constructed():
    with pytest.raises(ValueError):
        Element(kind=ElementKind.ACTION, text="File the suit")


@refuses("A2", 4)
@pytest.mark.eval_id("E-065")
def test_a_loud_signal_cannot_be_marked_collapsible():
    """COUNTEREXAMPLE: 'concise' becoming the mechanism that suppresses exactly
    the signals we fought to raise."""
    with pytest.raises(ValueError):
        Element(kind=ElementKind.FINDING, text="Time-barred.",
                signal=Signal.LIMITATION_BAR, collapsible=True)


# =================================================== store discipline =====

@pytest.mark.eval_id("E-011")
def test_an_unconfigured_key_is_a_hard_failure(tmp_path):
    """COUNTEREXAMPLE: making matters durable once wrote them to disk in
    PLAINTEXT, because encryption was a silent no-op when unconfigured."""
    with pytest.raises(EncryptionNotConfigured):
        FileMatterStore(tmp_path, key="")


def test_matter_state_is_not_plaintext_on_disk(tmp_path):
    engine, store = build(tmp_path)
    out = engine.run(TurnInput(
        advocate_id="adv",
        message="we act for the accused in a cheque matter; the notice went on 15 April"))
    blob = (tmp_path / "matters" / f"{out.matter.id}.nm").read_bytes()
    assert b"15 April" not in blob
    assert b"accused" not in blob


@pytest.mark.eval_id("E-011")
def test_state_survives_a_restart(tmp_path):
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv",
                               message="we act for the accused in a cheque matter"))
    # A genuinely fresh store object -- nothing carried in memory.
    reopened = FileMatterStore(tmp_path, key=KEY)
    again = reopened.load(out.matter.id)
    assert again is not None
    assert again.threads[0].posture.role is Role.ACCUSED


@pytest.mark.eval_id("E-021b")
def test_a_stale_commit_is_refused_rather_than_overwriting(tmp_path):
    store = FileMatterStore(tmp_path, key=KEY)
    m = Matter.create(advocate_id="adv", title="t")
    store.commit(m, expected_version=0)
    moved = store.commit(m.with_thread(Thread.create("later")), expected_version=0)
    with pytest.raises(StaleWrite):
        store.commit(m.with_thread(Thread.create("racing")), expected_version=0)
    assert moved.version > m.version


# ================================================ idempotency & metrics ===

@refuses("A1", 0)
@pytest.mark.eval_id("E-018")
def test_replaying_a_turn_does_not_apply_it_twice(tmp_path):
    """COUNTEREXAMPLE: a network retry that duplicates every fact, splits the
    thread, and re-raises resolved urgencies -- invisibly."""
    engine, store = build(tmp_path)
    first = engine.run(TurnInput(
        advocate_id="adv", turn_id="turn_fixed",
        message="we act for the accused in a cheque matter"))
    facts_before = len(first.matter.facts)

    replay = engine.run(TurnInput(
        advocate_id="adv", turn_id="turn_fixed", matter_id=first.matter.id,
        message="we act for the accused in a cheque matter"))
    assert replay.replayed
    assert len(replay.matter.facts) == facts_before


@pytest.mark.eval_id("E-019")
def test_metrics_are_written_even_when_the_turn_fails(tmp_path):
    """COUNTEREXAMPLE: the most diagnostically valuable turns -- the ones that
    crashed -- being the only ones with no record."""
    class _Exploding:
        def fetch(self, need):
            raise RuntimeError("retrieval exploded")

    engine, _ = build(tmp_path, evidence=_Exploding())
    with pytest.raises(RuntimeError):
        engine.run(TurnInput(advocate_id="adv", turn_id="turn_boom",
                             message="we act for the accused in a cheque matter"))
    written = json.loads((tmp_path / "metrics" / "turn_boom.json").read_text())
    assert written["outcome"] == "failed"
    assert written["failed_phase"] == "derive"
    assert "retrieval exploded" in written["failure"]


@pytest.mark.eval_id("E-023")
def test_a_held_but_not_found_result_is_a_defect_not_a_disclosure(tmp_path):
    """The third coverage state escalates. It is NEVER shown to the advocate as
    a corpus gap."""
    engine, _ = build(tmp_path, evidence=_Evidence(EvidenceResult(
        coverage=Coverage.HELD_NOT_FOUND,
        missing="Limitation Act Article 65 is intended but was not retrieved")))
    out = engine.run(TurnInput(
        advocate_id="adv",
        message="we act for the plaintiff; what is the limitation for possession"))
    fired = {g.gate_id: g for g in out.metrics.gates_fired}
    assert "G-HELDNOTFOUND" in fired, "the third coverage state must fire its gate"
    assert fired["G-HELDNOTFOUND"].response == "disclose"

    # It IS disclosed -- silence would let the advocate act on an answer whose
    # authority is missing without ever learning it. What it must never be
    # disclosed as is a gap in the law.
    text = " ".join(e.text for e in out.answer.elements)
    assert "defect in my retrieval" in text
    assert "not held in the corpus" not in text.lower()


@pytest.mark.eval_id("E-023")
def test_a_not_held_result_names_what_is_missing(tmp_path):
    engine, _ = build(tmp_path, evidence=_Evidence(EvidenceResult(
        coverage=Coverage.NOT_HELD,
        missing="the Kerala Buildings (Lease and Rent Control) Act is not held")))
    out = engine.run(TurnInput(
        advocate_id="adv", message="we act for the plaintiff in a tenancy dispute"))
    assert any("not held" in e.text.lower() and "Kerala" in e.text
               for e in out.answer.elements)


@pytest.mark.eval_id("E-020")
def test_a_finding_whose_span_does_not_support_is_never_a_ground(tmp_path):
    """An unsupported Finding is DROPPED, and the drop is DISCLOSED.

    It does not become a citation, and it does not vanish. Vanishing would
    leave the advocate believing nothing was found, which is a different and
    false statement about the corpus.

    Withholding the whole turn on it would be wrong in the other direction:
    once it is dropped, the answer does not rest on it and nobody has been
    misled. The withhold lives where the risk actually is -- the answer citing
    something that was never retrieved -- in tests/test_grounding_gate.py.
    """
    engine, _ = build(tmp_path, evidence=_Evidence(EvidenceResult(
        coverage=Coverage.ANSWERED,
        findings=(finding(proposition="Article 65 governs",
                          ref="Limitation Act Article 65",
                          span="unrelated text", locator="loc", store="s",
                          supports=False),))))
    out = engine.run(TurnInput(
        advocate_id="adv",
        message="we act for the plaintiff in a possession suit"))
    text = " ".join(e.text for e in out.answer.elements)
    assert "NOT being relied on" in text
    assert "G-GROUND" in text
    assert not any(e.refs and "unrelated text" in e.text for e in out.answer.elements)


@pytest.mark.eval_id("E-022")
def test_a_judgment_proposition_cannot_come_from_counsels_submission():
    """COUNTEREXAMPLE: 14.8% of retrievable paragraphs are counsel's
    submission, and quoting one as the holding is a live risk."""
    with pytest.raises(ValueError):
        finding(source_kind=SourceKind.AUTHORITY, ref="X v Y",
                span="counsel submitted that...", locator="l", store="s",
                para_kind=ParaKind.ARGUMENTS,
                treatment=Treatment.not_checked("no citator entry"))


# ================================================ THE SERVED PATH =========

@pytest.mark.eval_id("E-013", "E-064")
def test_the_served_path_answers_end_to_end(client):
    r = client.post("/api/turn", json={
        "advocate_id": "adv",
        "message": "we act for the accused; a cheque was dishonoured on 3 March"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["route"] == "matter"
    assert body["elements"][0]["kind"] in ("action", "question")
    assert body["metrics"]["outcome"] == "ok"
    assert body["metrics"]["llm_calls"] >= 1, "a served call must be counted"


@pytest.mark.eval_id("E-064", "E-065")
def test_the_served_path_blocks_on_unresolved_posture(client):
    body = client.post("/api/turn", json={
        "advocate_id": "adv", "message": "a cheque was dishonoured on 3 March"}).json()
    assert body["blocked"] is True
    assert body["elements"][0]["kind"] == "question"
    assert body["elements"][0]["signal"] == "unresolved_posture"
    assert body["elements"][0]["collapsible"] is False, \
        "a loud signal must never be collapsible on the wire"


@pytest.mark.eval_id("E-063")
def test_the_boards_are_bounded_by_row_count_not_turns(client):
    """THE REGRESSION TO WATCH. The previous build's board carried up to 28
    lines of analysis and grew with the conversation."""
    first = client.post("/api/turn", json={
        "advocate_id": "adv",
        "message": "we act for the accused in a cheque matter"}).json()
    matter_id = first["matter_id"]

    before = client.get(f"/api/matters/{matter_id}?advocate_id=adv").json()
    for i in range(4):
        client.post("/api/turn", json={
            "advocate_id": "adv", "matter_id": matter_id,
            "message": f"further instruction number {i} about the cheque matter"})
    after = client.get(f"/api/matters/{matter_id}?advocate_id=adv").json()

    assert after["row_count"] == before["row_count"], \
        "adding a turn must never add a board line"
    assert after["bounded_by"] == "thread_count"


@pytest.mark.eval_id("E-063e")
def test_the_matter_list_is_bounded_by_matter_count(client):
    client.post("/api/turn", json={
        "advocate_id": "adv", "message": "we act for the accused in a cheque matter"})
    listing = client.get("/api/matters?advocate_id=adv").json()
    assert listing["bounded_by"] == "matter_count"
    assert listing["row_count"] == len(listing["matters"])


@pytest.mark.eval_id("E-010")
def test_another_advocates_matter_is_not_disclosed(client):
    mine = client.post("/api/turn", json={
        "advocate_id": "adv", "message": "we act for the accused in a cheque matter"}).json()
    r = client.get(f"/api/matters/{mine['matter_id']}?advocate_id=someone_else")
    assert r.status_code == 404
    assert "no such matter" in r.json()["detail"], \
        "the response must not distinguish 'not yours' from 'does not exist'"


# ============================== THE SCREEN BOUNDARY =======================

@pytest.mark.eval_id("E-016")
def test_the_screens_run_before_any_substance_is_admitted(tmp_path):
    """STOP-SHIP #2, found by external review of the PRD.

    ADMIT used to extract, integrate and bind BEFORE the gating screens. That
    both retains substance on an uncleared file and -- because extraction goes
    through a model provider -- sends privileged client material to a third
    party before the matter is cleared to hold it.

    The screen must be reached with the matter still empty.
    """
    engine, _ = build(tmp_path)
    seen: list[int] = []
    original = engine._run_screens

    def spy(matter, turn, metrics):
        seen.append(len(matter.facts))
        return original(matter, turn, metrics)

    engine._run_screens = spy
    engine.run(TurnInput(advocate_id="adv",
                         message="we act for the accused in a cheque matter"))
    assert seen == [0], (
        "the screens must run before ANY fact is admitted; saw "
        f"{seen} fact(s) already on the matter")


@pytest.mark.eval_id("E-016")
def test_an_unscreened_matter_says_so_rather_than_reading_as_screened(tmp_path):
    """A screen that has not run must never be indistinguishable from a pass.

    The conflict, competence and engagement screens are slice 10. Until they
    exist, every turn must RECORD that it proceeded unscreened -- silence here
    is defect shape S1 at its most consequential.
    """
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv",
                               message="we act for the accused in a cheque matter"))
    fired = {g.gate_id: g for g in out.metrics.gates_fired}
    assert "G-UNSCREENED" in fired, (
        "a turn that was not screened must record that it was not screened")
    assert fired["G-UNSCREENED"].state == "unscreened"
    assert fired["G-UNSCREENED"].response == "disclose"
    assert "B3-B5" in fired["G-UNSCREENED"].detail
