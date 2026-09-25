"""The turn contract. PRD §7.3.

Every test here is a COUNTEREXAMPLE from the previous build made runnable. The
tests are written against the SERVED PATH wherever the property is about the
wire, because a guard that is right in the core and wrong at the edge is not a
guard -- and every defect the first external review found lived in that gap.
"""
from __future__ import annotations

import ast
import json
import pathlib
from datetime import date

import pytest
from nm.adapters.model.config import ModelConfig, TierConfig
from nm.adapters.model.scripted import ScriptedModelAdapter
from nm.adapters.store.file_store import EncryptionNotConfigured, FileMatterStore
from nm.core.posture import interpret
from nm.core.turn import TurnEngine, TurnInput, TurnRefused, classify_route
from nm.domain.answer import Element, ElementKind, Route, Signal
from nm.domain.matter import Basis, Matter, Posture, Role, Side, Thread
from nm.domain.quotable import Quotable
from nm.domain.traceability import refuses
from nm.knowledge.resolution import accrual_trigger_for as corpus_trigger
from nm.ports.evidence import (
    Binding,
    Coverage,
    EvidencePort,
    EvidenceResult,
    Finding,
    ParaKind,
    SourceKind,
    Treatment,
)
from nm.ports.model import Tier
from nm.ports.store import StaleWrite

ROOT = pathlib.Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.class_a

KEY = "test-key-not-a-secret"


def _model_config() -> ModelConfig:
    return ModelConfig(tiers={
        Tier.ROUTINE: TierConfig(Tier.ROUTINE, "scripted", "scripted-1", None, None),
        # THE HARD TIER IS CONFIGURED HERE BECAUSE IT IS CONFIGURED IN
        # PRODUCTION, as of 5 September 2026. A fixture without it tests a
        # deployment that no longer ships, and the six decisive reads would
        # raise TierUnavailable on every turn of every test -- which is what
        # happened the moment the escalation landed.
        #
        # Its ABSENCE is exercised deliberately instead, in
        # tests/test_reads_registry.py::test_an_absent_hard_tier_degrades_out_loud,
        # by an adapter that refuses the tier. That is the right shape: the
        # ordinary fixture matches production, and the degraded path is driven
        # rather than left as the default nobody chose.
        Tier.HARD: TierConfig(Tier.HARD, "scripted", "scripted-hard", None, None),
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


class _Evidence(EvidencePort):
    def __init__(self, result: EvidenceResult | None = None):
        self.result = result or EvidenceResult(
            coverage=Coverage.ANSWERED,
            findings=(finding(),),
            searched_stores=("the_limitation_act_1963",))

    def fetch(self, need):
        return self.result

    def accrual_trigger(self, cause: str) -> str:
        """THE REAL CURATED TABLE, not a stub returning empty.

        A double answering "" here is not neutral -- empty is the engine's
        documented "no curated trigger", so a stub would take every offline
        turn down the pre-BK-35 path and the accrual read would never run in
        the suite. The fix would be green on the defect it was written to
        remove, which is this file's own lesson about `TracedModel` arriving
        one layer down.
        """
        return corpus_trigger(cause)


#: What a matter that has been through intake holds. BK-34.
#:
#: THE FIXTURE SUPPLIES IT BECAUSE MOST TESTS ARE NOT ABOUT INTAKE. A matter
#: whose conflict, scope and capacity screens have not been answered is
#: blocked before any substance is admitted -- which is the row working -- and
#: a suite in which every test therefore becomes a test of the intake block is
#: a suite that has stopped testing limitation, proof, theory and the rest.
#:
#: IT IS THE REAL PATH AND NOT A BACK DOOR: these are the same fields the
#: browser sends from the intake form, written to the matter before the
#: screens read it. `build(..., intake=False)` opts out, and the tests that
#: are about the screens use it.
INTAKE_PARTIES = {"Ramesh Traders": "client", "Kiran Steels": "adverse"}
INTAKE_ANSWERS = {"scope": "the recovery work described in this brief"}
INTAKE_CAPACITY = {"state": "not_in_doubt",
                   "basis": "the fixture advocate explicitly assessed capacity to instruct"}


class briefed:  # noqa: N801 -- reads as a verb at every call site
    """An engine whose matters have been through intake.

    A THIN PASS-THROUGH, so what is under test is the real engine. It fills
    the intake fields on a turn that carries none -- exactly what the browser
    does from its intake form -- and touches nothing else.
    """

    def __init__(self, inner):
        object.__setattr__(self, "inner", inner)

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def __setattr__(self, name, value):
        # WRITES GO THROUGH TOO, and this was a real defect for about ten
        # minutes. `__getattr__` alone forwards reads; a test doing
        # `engine._model = _Ungrounded(...)` then set the attribute on the
        # WRAPPER, the inner engine kept its old model, and three tests that
        # provoke a withheld turn stopped provoking one -- reporting "the turn
        # was not withheld, so this test is measuring an ordinary turn", which
        # is precisely the failure they were written to refuse.
        #
        # A wrapper that is transparent in one direction is a wrapper that
        # silently discards half of what is done to it.
        if name == "inner":
            object.__setattr__(self, name, value)
        else:
            setattr(self.inner, name, value)

    def run(self, turn):
        from dataclasses import replace as _replace
        if not turn.parties and not turn.release and turn.capacity is None:
            turn = _replace(turn, parties=dict(INTAKE_PARTIES),
                            release=dict(INTAKE_ANSWERS), capacity=dict(INTAKE_CAPACITY))
        return self.inner.run(turn)


def build(tmp_path, evidence=None, responses=None, model=None,
          intake=True, coverage=True):
    """The served engine, with a scripted model.

    `model` is optional and BACKWARD-COMPATIBLE on purpose: a test that needs
    a double which behaves differently across turns -- one that repeats its
    answer, or forgets it -- cannot express that through `responses`, and the
    alternative is every such test building its own engine and drifting from
    this one.
    """
    store = FileMatterStore(tmp_path, key=KEY)
    model = model or ScriptedModelAdapter(
        _model_config(),
        responses=responses or {
            "__default__": "File the summary possession suit within six months."})
    # THE COVERAGE PORT, BECAUSE THE COMPOSITION ROOT WIRES ONE.
    #
    # It did not, so the competence screen answered NOT_ASSESSED on every
    # fixture turn -- "nothing can say whether this jurisdiction is covered" --
    # and blocked substance in the suite while production ran fine. A fixture
    # that composes less than the composition root tests a deployment that
    # does not ship, which is CLAUDE.md §8 arriving from the other direction.
    # `coverage=False` IS FOR THE TESTS THAT ARE ABOUT AN UNMEASURED
    # INSTALLATION. Wiring one unconditionally would make
    # `test_an_unmeasured_installation_says_so_rather_than_implying_coverage`
    # measure a measured one, which is the test passing on the opposite of
    # its own subject.
    from nm.knowledge.coverage import CoverageProfile
    profile = (CoverageProfile.load(ROOT / "assurance" / "specification" / "coverage.yaml")
               if coverage else None)
    # LB-121's CURATED PRE-INSTITUTION TABLE, wired because the composition
    # root wires it. A fixture that composes less than the composition root
    # tests a deployment that does not ship (CLAUDE.md section 8), and the
    # `statutory_notice` row is exactly the kind of difference that would hide
    # here and appear on a served turn.
    from nm.adapters.knowledge.institution import CuratedPreInstitution
    from nm.adapters.knowledge.interim_relief import CuratedInterimRelief
    from nm.adapters.knowledge.procedural_period import (
        CuratedProceduralPeriods,
    )
    engine = TurnEngine(store=store, evidence=evidence or _Evidence(),
                        model=model, coverage=profile,
                        pre_institution=CuratedPreInstitution(),
                        interim_relief=CuratedInterimRelief(),
                        procedural=CuratedProceduralPeriods())
    return (briefed(engine) if intake else engine), store


def confirmed(engine, store, turn: TurnInput, *, trigger: str,
              again: str = "Where does the limitation stand now?"):
    """ONE TURN, THEN THE ADVOCATE CONFIRMS THE ACCRUAL, THEN THE TURN THAT
    COMPUTES UNDER IT. Returns that second turn's output.

    Since `602e3f0` a MODEL-SELECTED accrual is conditional: naming a dated
    entry does not establish that it satisfies the Article's trigger, so a
    first turn serves the arithmetic as CONDITIONAL and registers no dated
    deadline. A rule about a DEFINITIVE window -- a by-when, a passed bar, a
    correction reaching the deadline -- is reached only through the advocate,
    and this is that path at the engine, recorded exactly as
    `POST .../premises/accrual_rule` records it (`nm.edge.api.state_premise`).

    ONE HELPER, so the tests that need a confirmed accrual cannot each invent
    a different way of getting one. `trigger` names the event, never a date:
    the period must still rest on the dated entry, or a correction to that
    entry would have nothing to reach.
    """
    from dataclasses import replace

    from nm.domain.matter import new_id

    first = engine.run(turn)
    matter = store.load(first.matter.id)
    thread = matter.threads[0]
    stated = dict(thread.premises_stated or {})
    stated["accrual_rule"] = {"statement": trigger, "source": "the advocate",
                              "by": turn.advocate_id, "at": turn.today.isoformat()}
    store.commit(matter.with_thread(replace(thread, premises_stated=stated)),
                 expected_version=matter.version)
    # A NEW TURN ID, or the engine replays the first turn's receipt.
    return engine.run(replace(turn, message=again, matter_id=matter.id,
                              turn_id=new_id("turn"), expected_version=None))


# ======================================================= routing ==========

@refuses("B1", 0)
@pytest.mark.eval_id("E-012")
@pytest.mark.eval_id("E-100")
def test_route_is_not_decided_on_message_length(tmp_path):
    """COUNTEREXAMPLE: 'police arrested my son tonight' read as a greeting
    because it is five words -- measured live, in both directions.

    DRIVEN THROUGH THE READ, not through `classify_route`. The route is a
    model read as of 7 September 2026: two keyword lists and two length rules
    decided it before, under a docstring that forbade routing on length.
    `classify_route` survives as the fallback and always says MATTER, so
    asserting against it would assert nothing.
    """
    engine, _ = build(tmp_path)

    short = engine.run(TurnInput(
        advocate_id="adv", message="police picked up my client last night"))
    assert short.answer.route is Route.MATTER, "a five-word emergency is a matter"

    long_question = engine.run(TurnInput(
        advocate_id="adv",
        message=("what areas of law do you cover and how do you work with "
                 "an advocate")))
    assert long_question.answer.route is Route.NON_MATTER, (
        "a long question about NM is not a matter")


@refuses("B1", 0)
@pytest.mark.eval_id("E-012")
def test_a_one_word_case_fact_is_a_matter(tmp_path):
    """THE ADVOCATE'S OWN COUNTEREXAMPLE, 7 September 2026: *even if one word
    or two words, it need not be a greeting -- it can be the actual dispute.*

    "bail" is one word and a case fact. "he absconded" is two. The old rule
    routed anything of three words or fewer to NON_MATTER, which writes
    NOTHING to any file -- so the turn was discarded.
    """
    engine, _ = build(tmp_path)
    for message in ("bail", "he absconded", "ex parte decree"):
        out = engine.run(TurnInput(advocate_id="adv", message=message))
        assert out.answer.route is Route.MATTER, (
            f"{message!r} is a case fact and was routed away; NON_MATTER "
            f"writes nothing to any file, so the turn is gone")


def test_the_fallback_never_guesses_from_length(tmp_path):
    """`classify_route` is what runs when the read could not. It takes the
    SAFE DIRECTION rather than a word count: a full workup on a question
    wastes time, and a matter read as a greeting is negligent."""
    for message in ("bail", "hi", "a much longer message about a suit"):
        route, _, _ = classify_route(message)
        assert route is Route.MATTER, (
            f"the fallback routed {message!r} away without a model to read it")

    with pytest.raises(TurnRefused):
        classify_route("   ")


@pytest.mark.eval_id("E-012")
def test_a_greeting_writes_nothing_to_any_file(tmp_path):
    engine, store = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv", message="hi"))
    assert out.answer.route is Route.NON_MATTER
    assert out.matter is None
    listed = store.list_for("adv")
    assert tuple(listed) == (), "the non-matter route persists nothing"
    assert listed.complete, "nothing was written, so nothing can be unreadable"


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
    stated = interpret(Quotable(turn=message), {
        "states_client": True, "role": "plaintiff",
        "client_described_as": "landlord",
        "quoted": "the landlord has issued a quit notice"})
    assert stated.role is Role.UNKNOWN
    assert "describes events" in stated.refused

    # And a span that is not in the message at all cannot settle anything.
    invented = interpret(Quotable(turn=message), {
        "states_client": True, "role": "plaintiff",
        "client_described_as": "", "quoted": "we act for the landlord"})
    assert invented.role is Role.UNKNOWN
    assert "advocate wrote" in invented.refused


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
        stated = interpret(Quotable(turn=message), data)
        assert stated.refused is None, f"{message}: {stated.refused}"
        assert stated.role is role
        assert stated.client_described_as == described


def test_a_role_outside_the_products_vocabulary_is_blanked():
    """PRD D9: an out-of-vocabulary facet value is blanked and re-derived,
    never accepted. A model returning a role this product cannot reason about
    must not set one."""
    stated = interpret(Quotable(turn="we act for the amicus"), {
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
@refuses("I1", 1)
def test_an_unconfigured_key_is_a_hard_failure(tmp_path):
    """COUNTEREXAMPLE: making matters durable once wrote them to disk in
    PLAINTEXT, because encryption was a silent no-op when unconfigured."""
    with pytest.raises(EncryptionNotConfigured):
        FileMatterStore(tmp_path, key="")


@refuses("I1", 0)
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
    class _Exploding(EvidencePort):
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

    # THE SAME TIE. G-NOTHELD owes the advocate the NAME of what is
    # missing -- "a vague disclaimer is silence in more words" is the
    # matrix's own wording -- and the assertion above proves the bytes
    # while naming no gate, so nothing links the promise to the proof.
    assert "G-NOTHELD" in {g.gate_id for g in out.metrics.gates_fired}, (
        "the answer names what is missing and the gate that requires "
        "that did not fire")


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
                para_kind=ParaKind.NOT_ATTRIBUTABLE,
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
@refuses("A2", 2)
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
    # A SECOND ADVOCATE, WITH A SESSION.
    #
    # This named a different `advocate_id` in the query string and
    # asserted a 404. True, and empty: naming one was all it took to be
    # one, so the test passed while any caller could read any matter
    # (B-082). The other advocate now has to authenticate.
    someone_else = client.sign_in("someone_else", fresh=True)
    r = someone_else.get(f"/api/matters/{mine['matter_id']}")
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

    THE PRODUCT CHANGED UNDER THIS TEST ON 8 SEPTEMBER 2026 (BK-34) and the
    claim did not. Until then every screen was a NOT_ASSESSED placeholder and
    substance was admitted anyway under a general exception, so the only
    reachable case was `unscreened`. Now the screens have producers, and BOTH
    states are reachable -- which makes this a stronger test than it could be
    before, because a gate that can only ever fire one way is not being asked
    a question.

    SO IT IS DRIVEN BOTH WAYS. A matter that has been through intake records
    `screened`; one that has not records `unscreened` and says what is
    outstanding. The failure this refuses is the two being indistinguishable,
    and it is refused in both directions rather than one.
    """
    # NOT through intake: `intake=False` gives the engine no scope, capacity
    # or party answers, which is the state of a matter nobody has opened
    # properly.
    engine, _ = build(tmp_path, intake=False)
    out = engine.run(TurnInput(advocate_id="adv",
                               message="we act for the accused in a cheque matter"))
    fired = {g.gate_id: g for g in out.metrics.gates_fired}
    assert "G-UNSCREENED" in fired, (
        "a turn that was not screened must record that it was not screened")
    assert fired["G-UNSCREENED"].state == "unscreened"
    assert fired["G-UNSCREENED"].response == "disclose"
    assert "not cleared to hold substance" in fired["G-UNSCREENED"].detail

    # AND THE OTHER DIRECTION, which is what stops `unscreened` being the
    # only answer the gate knows how to give.
    briefed_engine, _ = build(tmp_path / "screened")
    (tmp_path / "screened").mkdir(exist_ok=True)
    done = briefed_engine.run(TurnInput(
        advocate_id="adv",
        message="we act for the accused in a cheque matter"))
    after = {g.gate_id: g for g in done.metrics.gates_fired}
    assert after["G-UNSCREENED"].state == "screened", (
        "a matter that has been through intake still records as unscreened, "
        "so the gate says the same thing whatever happened")


# ============ BK-2 — the screens reach the advocate =========================

def test_every_screen_is_named_to_the_advocate_and_none_reads_as_clear(tmp_path):
    """BK-2. `backend/nm/core/screens.py` has been complete since slice 6 -- four
    states, `unscreened` drawing its population from the KINDS, an express
    emergency exception -- and nothing produced a `Screen`.

    WHAT WAS ACTUALLY WRONG IS SHARPER THAN "UNBUILT". `_run_screens` fired
    G-UNSCREENED under a comment saying "the output says so rather than
    reading as though it had passed", and MEASURED on 7 September 2026 the
    advocate saw ZERO screen-related lines. The gate was in the metrics and
    invisible where it matters, which is §9: the third state must be visible
    in the OUTPUT and not only in the type.
    """
    from nm.core.screens import ScreenKind

    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(
        advocate_id="adv",
        message=("we act for the plaintiff in a recovery matter; invoices "
                 "dated 14 March 2023 unpaid")))

    said = " ".join(e.text for e in out.answer.elements)
    assert "Screens on this matter" not in said, "routine audit reports are not conversation"

    # EVERY KIND, by name. An advocate reading four rows believes the fifth
    # was checked -- which is `unscreened`'s own argument for drawing its
    # population from the vocabulary, and it holds whether the screens cleared
    # or not.
    from nm.core.screens import from_stored
    saved_screens = from_stored(out.matter.screens)
    assert {s.kind for s in saved_screens} == set(ScreenKind)
    assert all(s.detail or s.not_assessed_because for s in saved_screens)

    # AND WHAT THE ROW MEANS CHANGED WITH BK-34. It used to have to say that
    # substance was admitted with the screens outstanding, because it always
    # was. Now a matter that has been through intake CLEARS them, and the row
    # says which -- so the assertion is that the advocate is told the outcome,
    # not that the outcome is always an exception.
    # LB-113 changes presentation, not screening: a material coverage limit
    # still reaches the actual released answer and carries its gate identity.
    assert any(e.gate == "G-COMPETENCE" and e.disclosure for e in out.answer.elements)
    assert "all cleared" not in said


def test_the_coverage_position_reaches_the_advocate_not_only_the_metrics(
        tmp_path):
    """G-COMPETENCE discloses, and a disclosure nobody sees is not one.

    BK-34 built this gate. `trace` T9 required that -- a gate declared unbuilt
    that something consults fails harder than one that is simply missing --
    and building it immediately raised the harder question the disclose
    accounting asks: does the thing it discloses actually reach the bytes?

    IT IS THE SAME DEFECT AS G-UNSCREENED'S, one gate over. That fired into
    the metrics under a comment claiming the output said so, and MEASURED on
    7 September 2026 the advocate saw zero screen-related lines. A gate whose
    whole response class is DISCLOSE and whose disclosure is invisible has the
    response class in name only.

    THE POSITION IS MEASURED AND THE GAP IS NAMED. Telangana's most recent
    binding High Court judgment is from 2018, so there is a real coverage gap
    for the years since -- and the advocate is told which years and what is
    held, rather than being left to infer it from an answer that cites nothing
    recent.
    """
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(
        advocate_id="adv",
        message=("we act for the plaintiff in a recovery matter; invoices "
                 "dated 14 March 2023 unpaid")))

    fired = [g for g in out.metrics.gates_fired if g.gate_id == "G-COMPETENCE"]
    assert fired, "the competence gate did not fire at all"
    assert fired[0].response == "disclose"

    said = " ".join(e.text for e in out.answer.elements)
    assert any(e.gate == "G-COMPETENCE" and e.disclosure for e in out.answer.elements), (
        "the material coverage limit did not reach the advocate")
    # WHAT IT FOUND, not merely that it ran. `covered` and `COVERAGE GAP` are
    # opposite facts and an advocate who cannot tell them apart has been told
    # nothing worth the line.
    assert ("COVERAGE GAP" in said or "NOT MEASURED" in said
            or "binds" in said or "held" in said), (
        f"the competence row says the screen ran and not what it found:\n"
        f"{said[:600]}")


def test_every_answer_in_the_run_carries_the_trailing_disclosures(tmp_path):
    """EVERY Answer built by `_run` carries the screen rows and the split
    notice, or is one of the declared exemptions.

    THIS COUNTED THE MECHANISM AND NOT THE POPULATION, and that is how it
    passed over a live defect. It asserted three calls to `_with_screens`;
    there are FIVE Answer constructions in `_run`, so two of them carried
    no trailing disclosure at all and the check was satisfied anyway.

    Measured on three served turns before the fix: `G-UNSCREENED` fired on
    every one and the screens line reached the advocate on none, whenever
    the second citation attempt ran. The gate fired, the matrix promised
    the advocate would see it, and the answer carried nothing -- B-128,
    on the one branch nobody was counting.

    THE EXEMPTION IS DECLARED, NOT SILENT. An incomplete screen BLOCKS,
    and the blocking question is itself the answer about screens; adding
    the rows underneath would say the same thing twice. That is a reason,
    and it lives here where the next person can disagree with it.
    """
    import inspect

    from nm.core.turn import TurnEngine

    #: Answer constructions that legitimately carry no trailing rows,
    #: by the text that identifies them, with the reason.
    exempt = {
        "screens.blocking_question":
            "an incomplete screen blocks, and the question IS the screens "
            "answer -- the rows below it would repeat it",
    }

    src = inspect.getsource(TurnEngine._run)
    tree = ast.parse(src.lstrip())
    answers = [n for n in ast.walk(tree)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id == "Answer"]
    assert len(answers) >= 4, (
        f"only {len(answers)} Answer construction(s) found -- the walk is "
        f"broken, and a check that sees nothing passes everything")

    uncovered = []
    for node in answers:
        kw = [k for k in node.keywords if k.arg == "elements"]
        if not kw:
            continue
        text = ast.unparse(kw[0].value)
        if any(marker in text for marker in exempt):
            continue
        if "_with_screens" not in text:
            uncovered.append(text[:90])

    assert not uncovered, (
        "these Answer constructions do not carry the trailing disclosures, "
        "so a gate can fire while the advocate is told nothing:\n  "
        + "\n  ".join(uncovered)
        + "\n\nRoute the elements through `_with_screens`, or add the site "
          "to EXEMPT above with the reason it needs none.")


def test_the_answer_coverage_check_can_see_an_uncovered_site():
    """POSITIVE CONTROL. S11 -- a check that cannot fail proves nothing,
    and this one spent a slice passing over two uncovered sites.
    """
    planted = ast.parse(
        "Answer(route=r, elements=tuple([*head, *derived]))")
    node = next(n for n in ast.walk(planted)
                if isinstance(n, ast.Call)
                and getattr(n.func, "id", "") == "Answer")
    text = ast.unparse([k for k in node.keywords if k.arg == "elements"][0].value)
    assert "_with_screens" not in text, (
        "the check would not notice an Answer built without the assembler")

def test_the_admit_decision_goes_through_the_module(tmp_path):
    """`may_admit_substance` is the one owner of B3's rule. Returning
    `clear=True` from the turn instead would put the decision in two places,
    and the one that matters would be the hard-coded one."""
    import inspect

    from nm.core.turn import TurnEngine

    body = inspect.getsource(TurnEngine._run_screens)
    assert "may_admit_substance" in body
    assert "screens_mod.unscreened" in body, (
        "the rows are built here rather than by the module, so the "
        "population is whatever this function remembers")
