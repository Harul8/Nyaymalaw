"""Checklist state follows scoped, current conversation evidence, not ticks."""

import json
from dataclasses import asdict, replace
from datetime import date

import pytest

from nm.legal_brain.orchestrate.turn import TurnInput
from nm.legal_brain.reason import requirements
from nm.legal_brain.reason.requirements_contracts import (
    Force,
    Requirement,
    State,
    checklist,
    key,
    settled,
)
from nm.shared.metrics_contracts import TurnMetrics
from nm.shared.model_scripted import SCRIPTED_READS
from nm.shared.store_file_store import FileMatterStore
from nm.work_the_file import deadlines, dispute_agenda
from nm.work_the_file import summary_contracts as summary
from nm.work_the_file.matter_contracts import Basis, Fact, Matter, Posture, Provenance, Role, Thread
from tests.test_matter_memory import _engine, _Recorder
from tests.test_turn_contract import KEY, finding

pytestmark = pytest.mark.class_a
TODAY = date(2026, 9, 22)


def record():
    reqs = tuple(
        Requirement(
            f"Item {n}",
            f"Purpose {n}",
            f"A retrieved passage requires supporting material numbered {n}.",
            "Retrieved source",
            f"locator:{n}",
            Force.REQUIRED,
        )
        for n in range(4)
    )
    thread = replace(Thread.create("Rent"), requirements=reqs)
    return Matter.create(advocate_id="adv", title="Three distinct claims").with_thread(thread)


def answer(matter, index, state, quote, *, due="", turn="t1", **overrides):
    thread = matter.threads[0]
    fact = Fact.create(statement=quote, provenance=Provenance(kind="advocate_statement", turn=turn))
    matter = matter.with_fact(fact).with_thread(
        replace(thread, chronology=(*thread.chronology, fact.id))
    )
    row = {
        "thread_id": thread.id,
        "key": key(requirements.restored(thread)[index]),
        "answer": state,
        "quoted": quote,
        "due_expression": due,
        **overrides,
    }
    return requirements.apply_answers(matter, [row], message=quote, turn_id=turn, today=TODAY)


def states(matter):
    return [r.state for r in checklist(matter.threads[0], matter.facts)]


def test_four_answers_are_derived_and_unknown_words_are_not_lost():
    m = answer(record(), 0, "held", "The notice was served on 4 March 2025.")
    m = answer(m, 1, "unavailable", "The original was destroyed; I cannot obtain it.")
    m = answer(m, 2, "promised", "I will send the receipt tomorrow.", due="tomorrow")
    m = answer(m, 3, "outstanding", "I do not know.")
    assert states(m) == [State.HELD, State.UNAVAILABLE, State.PROMISED, State.OUTSTANDING]
    assert checklist(m.threads[0], m.facts)[3].outcome.basis == "I do not know."
    assert not requirements.nothing_to_ask(m.threads[0], m.facts)
    assert not settled(m.threads[0], m.facts)
    m = answer(m, 3, "unavailable", "There is no way for me to get that material.", turn="t2")
    assert requirements.nothing_to_ask(m.threads[0], m.facts)
    assert not settled(m.threads[0], m.facts), "a promise is not an arrival"
    m = answer(m, 2, "held", "The receipt confirms delivery on 4 March 2025.", turn="t3")
    assert settled(m.threads[0], m.facts)
    item_key = key(requirements.restored(m.threads[0])[2])
    history = m.threads[0].requirement_outcomes[item_key]["history"]
    assert history[-1]["state"] == "promised"


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_key",
        "unknown_thread",
        "false_quote",
        "foreign_fact",
        "duplicate",
        "wrong_turn",
        "invented_date",
    ],
)
def test_proposals_cannot_update_an_unattributed_or_wrong_dispute(mutation):
    m = answer(record(), 0, "held", "The acknowledged delivery occurred.")
    t = m.threads[0]
    r = {
        "thread_id": t.id,
        "key": key(requirements.restored(t)[0]),
        "answer": "unavailable",
        "quoted": "The acknowledged delivery occurred.",
        "due_expression": "",
    }
    if mutation == "unknown_key":
        r["key"] = "invented"
    elif mutation == "unknown_thread":
        r["thread_id"] = "foreign"
    elif mutation == "false_quote":
        r["quoted"] = "Words never supplied"
    elif mutation == "foreign_fact":
        m = m.with_thread(replace(t, chronology=()))
    elif mutation == "invented_date":
        r["due_expression"] = "tomorrow"
    old = m.threads[0].requirement_outcomes
    out = requirements.apply_answers(
        m,
        [r, r] if mutation == "duplicate" else [r],
        message="The acknowledged delivery occurred.",
        turn_id="another" if mutation == "wrong_turn" else "t1",
        today=TODAY,
    )
    assert out.threads[0].requirement_outcomes == old


def test_saved_json_board_and_handover_agree_after_reopening(tmp_path):
    m = answer(record(), 0, "held", "The current facts supply this item.")
    t = m.threads[0]
    # Orphan outcomes cannot inflate completion counts.
    m = m.with_thread(
        replace(
            t,
            requirement_outcomes={
                **t.requirement_outcomes,
                "orphan": {"state": "held", "fact": "missing", "basis": "false", "at": "today"},
            },
        )
    )
    store = FileMatterStore(tmp_path, key=KEY)
    store.commit(replace(m, version=1), expected_version=0)
    restored = FileMatterStore(tmp_path, key=KEY).load(m.id)
    assert isinstance(restored.threads[0].requirements[0], dict)
    assert states(restored) == states(m)
    assert summary._requirement_state(restored.threads[0], restored.facts) == {
        "state": "established",
        "held": 1,
        "outstanding": 3,
        "promised": 0,
        "unavailable": 0,
        "applicability_review_required": 0,
        "total": 4,
    }
    assert len(dispute_agenda.project(restored)["disputes"][0]["requirements"]) == 4


def test_superseding_the_supporting_fact_removes_green_without_erasing_the_answer():
    m = answer(record(), 0, "held", "Delivery is confirmed.")
    old = m.facts[0]
    replacement = Fact.create(
        statement="I withdraw my confirmation.",
        provenance=Provenance(kind="advocate_statement", turn="t2"),
    )
    m = m.with_fact(replacement).superseding(old.id, replacement.id)
    assert states(m)[0] is State.OUTSTANDING
    assert m.threads[0].requirement_outcomes, "the old answer is retained for audit"


def test_due_and_undated_promises_return_without_becoming_legal_deadlines():
    m = answer(record(), 0, "promised", "I will provide it tomorrow.", due="tomorrow")
    m = answer(m, 1, "promised", "I will provide it later.")
    t = m.threads[0]
    assert not requirements.due_items(t, m.facts, TODAY)
    assert len(requirements.due_items(t, m.facts, date(2026, 9, 23))) == 1
    assert len(requirements.due_items(t, m.facts, date(2026, 9, 23), resumed=True)) == 2
    followups = deadlines.read_matter(m).rows
    assert len(followups) == 2
    assert all(r.kind is deadlines.DeadlineKind.INFORMATION_FOLLOWUP for r in followups)
    assert "not a legal deadline" in followups[0].source
    assert all(s is State.PROMISED for s in states(m)[:2])


def test_unsupported_or_wrong_source_spans_are_not_requirements():
    passage = requirements.Passage(
        "Act X", "A person must supply a dated record of the notice.", "provision", "act-x:1"
    )
    good = {
        "force": "required",
        "need": "Dated notice",
        "why": "Establish notice",
        "span": passage.text,
        "source": passage.source,
    }
    reading = requirements.read(
        {
            "requirements": [
                good,
                {**good, "source": "Act Y"},
                {**good, "span": "A made-up requirement no source ever mentioned."},
            ]
        },
        (passage,),
    )
    assert len(reading.requirements) == 1 and reading.dropped == 2
    assert len(requirements.merge((asdict(reading.requirements[0]),), reading)) == 1


@pytest.mark.parametrize('kind,force', [('authority', 'required'),
                                       ('provision', 'strengthening')])
def test_force_is_not_invented_from_document_type(kind, force):
    passage = requirements.Passage('Source', 'The supplied clause supports this requirement.',
                                    kind, 'source:1')
    row = {'need': 'An item', 'why': 'Read the clause in its context',
           'span': passage.text, 'source': passage.source, 'force': force}
    read = requirements.read({'requirements': [row]}, (passage,))
    assert read.requirements[0].force.value == force
    assert requirements.read({'requirements': [{**row, 'force': 'invented'}]},
                             (passage,)).dropped == 1


def test_session_return_does_not_change_the_idempotent_request_identity():
    from nm.legal_brain.orchestrate.turn import TurnEngine
    turn = TurnInput(advocate_id='adv', message='These are my instructions',
                     session_reference='old-session')
    assert TurnEngine._offer(turn, 'matter') == TurnEngine._offer(
        replace(turn, session_reference='new-session'), 'matter')


def test_successful_empty_read_is_cached_but_changed_text_is_not(tmp_path):
    model = _Recorder()
    engine, _ = _engine(tmp_path, model=model)
    t = Thread.create("Test")
    source = finding()
    concluded = {}
    engine._requirements(t, (source,), TurnMetrics(turn_id="test"), concluded=concluded)
    assert concluded["requirement_reads"]
    t = replace(t, requirement_reads=concluded["requirement_reads"],
                requirement_read_contexts=concluded["requirement_read_contexts"])
    calls = len(model.prompts)
    assert engine._requirements(t, (source,), TurnMetrics(turn_id="test")) is None
    assert len(model.prompts) == calls
    engine._requirements(
        t, (replace(source, span=source.span + " Changed."),), TurnMetrics(turn_id="test")
    )
    assert len(model.prompts) == calls + 1


@pytest.mark.parametrize("change", ["represented_side", "objective", "corrected_fact"])
def test_same_source_is_reconsidered_when_this_disputes_material_context_changes(tmp_path, change):
    model = _Recorder()
    engine, _ = _engine(tmp_path, model=model)
    source = finding()
    old_fact = Fact.create("The notice was served on 4 March.",
                           Provenance(kind="advocate_statement", turn="old"))
    original = replace(Thread.create("Notice"),
                       posture=Posture(Role.PLAINTIFF, Basis.STATED),
                       objective={"desired_result": "Recover possession"},
                       chronology=(old_fact.id,))
    concluded = {}
    engine._requirements(original, (source,), TurnMetrics(turn_id="first"),
                         facts=(old_fact,), concluded=concluded)
    assert concluded["requirement_reads"], "even an empty successful read is cached"
    original = replace(original, requirement_reads=concluded["requirement_reads"],
                       requirement_read_contexts=concluded["requirement_read_contexts"])
    unrelated = replace(Thread.create("Rent"),
                        posture=original.posture, objective=original.objective,
                        chronology=(old_fact.id,))
    other_read = {}
    engine._requirements(unrelated, (source,), TurnMetrics(turn_id="other"),
                         facts=(old_fact,), concluded=other_read)
    unrelated = replace(unrelated, requirement_reads=other_read["requirement_reads"],
                        requirement_read_contexts=other_read["requirement_read_contexts"])
    calls = len(model.prompts)
    assert engine._requirements(original, (source,), TurnMetrics(turn_id="repeat"),
                                facts=(old_fact,)) is None
    assert len(model.prompts) == calls, "unchanged successful reads stay cached"

    facts = (old_fact,)
    if change == "represented_side":
        changed = replace(original, posture=Posture(Role.DEFENDANT, Basis.STATED))
    elif change == "objective":
        changed = replace(original, objective={"desired_result": "Resist possession"})
    else:
        new_fact = Fact.create("The notice was not served on 4 March.",
                               Provenance(kind="advocate_statement", turn="correction"))
        changed = replace(original, chronology=(*original.chronology, new_fact.id))
        facts = (replace(old_fact, superseded_by=new_fact.id), new_fact)
    engine._requirements(changed, (source,), TurnMetrics(turn_id="changed"),
                         facts=facts, concluded={})
    assert len(model.prompts) == calls + 1, "the same law may apply differently after a correction"
    assert engine._requirements(unrelated, (source,), TurnMetrics(turn_id="other-repeat"),
                                facts=(old_fact,)) is None
    assert len(model.prompts) == calls + 1, "a separate dispute retains its own current read"


def test_old_need_and_answer_stay_on_file_but_do_not_certify_changed_applicability():
    m = answer(record(), 0, "held", "The dated notice is held.")
    old = m.threads[0]
    old = replace(old, posture=Posture(Role.PLAINTIFF, Basis.STATED))
    original_context = requirements.applicability_identity(old, m.facts)
    item = replace(old.requirements[0], source_identity="actual-passage-v1",
                   context_identity=original_context)
    ident = key(item)
    original_answer = {
        **old.requirement_outcomes[ident],
        "source_identity": "actual-passage-v1",
        "context_identity": original_context,
    }
    old = replace(old, requirements=(item, *old.requirements[1:]),
                  requirement_reads={item.locator: item.source_identity},
                  requirement_read_contexts={item.locator: original_context},
                  requirement_outcomes={ident: original_answer})
    assert checklist(old, m.facts)[0].state is State.HELD

    changed = replace(old, posture=Posture(Role.DEFENDANT, Basis.STATED))
    stale = checklist(changed, m.facts)[0]
    assert stale.state is State.OUTSTANDING
    assert stale.rendered()["applicability_state"] == "review_required"
    assert changed.requirement_outcomes[ident] == original_answer
    assert not requirements.settled(changed, m.facts)
    questions = requirements.conversation_context(changed, m.facts, TODAY)
    assert "legal-applicability re-review" in questions
    assert item.need not in questions, "stale needs cannot become current questions"
    reviewed_file = m.with_thread(replace(
        changed, assessed=(*summary.DERIVED_SECTIONS, "review_current")))
    board = dispute_agenda.project(reviewed_file)["disputes"][0]
    assert board["status"] == "needs_review"
    assert board["outstanding_requirements"] == 3  # only the other current rows
    assert board["applicability_review_required"] == 1

    # A read finding no currently applicable need retains the old row only as
    # history. A new read finding the same clause still cannot borrow the old
    # answer without assessing that answer in the changed dispute context.
    assert (requirements.merge(changed.requirements, requirements.Reading(()))
            == changed.requirements)
    current_context = requirements.applicability_identity(changed, m.facts)
    reread = requirements.merge(changed.requirements, requirements.Reading((
        replace(item, context_identity=current_context),)))
    reassessed = replace(changed, requirements=reread,
                         requirement_read_contexts={item.locator: current_context})
    assert checklist(reassessed, m.facts)[0].state is State.OUTSTANDING
    assert reassessed.requirement_outcomes[ident] == original_answer
    assert checklist(old, m.facts)[0].state is State.HELD

    legacy = replace(old, requirements=(replace(item, context_identity=""),
                                        *old.requirements[1:]),
                     requirement_read_contexts={})
    assert checklist(legacy, m.facts)[0].rendered()["applicability_state"] == "review_required"
    assert not requirements.settled(legacy, m.facts), (
        "a source-backed old row with no recorded applicability context cannot be current")


@pytest.mark.parametrize("failure", ["unavailable", "truncated", "not_established"])
def test_failed_requirement_read_preserves_existing_rows_answers_and_cache(
        tmp_path, monkeypatch, failure):
    from nm.shared.budget_contracts import Completion
    from nm.shared.model_port import ModelError, ModelResult, Tier, Usage

    engine, _ = _engine(tmp_path)
    m = answer(record(), 0, "held", "The current record is available.")
    t = replace(m.threads[0], requirement_reads={"previous:1": "prior-hash"})
    before = asdict(t)
    calls = []

    def failed_read(*args, **kwargs):
        calls.append(True)
        if failure == "unavailable":
            raise ModelError("Provider unavailable")
        completion = (Completion.LENGTH_LIMITED if failure == "truncated"
                      else Completion.NOT_ESTABLISHED)
        return ModelResult(text=None, data={"requirements": []}, tier=Tier.ROUTINE,
                           provider="scripted", model="scripted-1", usage=Usage(0, 0, 0),
                           latency_ms=0, completion=completion)

    monkeypatch.setattr(engine, "_read", failed_read)
    concluded = {}
    for _ in range(2):
        assert engine._requirements(t, (finding(),), TurnMetrics(turn_id="test"),
                                    concluded=concluded) is None
    assert len(calls) == 2, "a failed read must be retried, not cached as empty"
    assert concluded == {}
    assert asdict(t) == before
    assert checklist(t, m.facts)[0].state is State.HELD


def test_information_promises_cannot_become_the_nearest_legal_deadline():
    from nm.work_the_file.projections_api import cover_projection

    m = answer(record(), 0, "promised", "I will supply it tomorrow.", due="tomorrow")
    register = deadlines.read_matter(m)
    window = cover_projection(m, register, today=TODAY)["case_deadlines"]
    assert window["next_deadline"] is None
    assert window["deadline_assessment"] == "not_assessed"
    assert window["deadline_entries"] == []
    assert len(window["information_followups"]) == 1
    assert window["information_followups"][0]["on"] == "2026-09-23"
    assert deadlines.nearest_thread(register.rows, TODAY) is None


def test_unsupported_requirement_read_preserves_the_held_checklist_without_crashing(
        tmp_path, monkeypatch):
    engine, _ = _engine(tmp_path)
    m = answer(record(), 0, "held", "The current record is available.")
    t = replace(m.threads[0], requirement_reads={"previous:1": "prior-hash"})
    before, concluded = asdict(t), {}
    monkeypatch.setitem(SCRIPTED_READS, "requirements", lambda _: json.dumps({
        "requirements": [{"need": "Invented requirement", "why": "Unsupported",
                          "span": "Words not in the source", "source": "unknown",
                          "force": "required", "answer": "", "answer_quote": "",
                          "due_expression": ""}]}))
    metrics = TurnMetrics(turn_id="test")
    assert engine._requirements(t, (finding(),), metrics, concluded=concluded) is None
    assert not concluded and asdict(t) == before
    assert any(g.gate_id == "G-MODEL" and g.state == "unavailable" for g in metrics.gates_fired)


def test_live_turn_updates_an_existing_item_without_an_extra_reply_read(tmp_path, monkeypatch):
    engine, store = _engine(tmp_path)
    first = engine.run(
        TurnInput(
            advocate_id="adv",
            message="We act for the plaintiff in O.S. 44/2025 seeking possession.",
        )
    )
    m = store.load(first.matter.id)
    t = m.threads[0]
    req = requirements.restored(record().threads[0])[0]
    version = m.version
    m = m.with_thread(replace(t, requirements=(req,)))
    store.commit(m, expected_version=version)
    quote = "The bank cannot supply the original record; it was destroyed."

    def reader(_):
        return json.dumps(
            {
                "client": "",
                "why": "Existing dispute",
                "disputes": [
                    {"other_side": "", "contested": t.label, "kind": "other",
                     "on_file": t.id, "sentences": ["S1"]}
                ],
                "background": [],
                "instructions": [],
                "focus_thread_id": "",
                "focus_quote": "",
                "advance_quote": "",
                "requirement_answers": [
                    {
                        "thread_id": t.id,
                        "key": key(req),
                        "answer": "unavailable",
                        "quoted": quote,
                        "due_expression": "",
                    }
                ],
            }
        )

    monkeypatch.setitem(SCRIPTED_READS, "dispute", reader)
    out = engine.run(TurnInput(advocate_id="adv", matter_id=m.id, message=quote))
    saved = store.load(m.id)
    assert checklist(saved.threads[0], saved.facts)[0].state is State.UNAVAILABLE
    assert out.metrics.binding_reads == 1
    assert any(quote in p.user and "CHECKLIST CONTEXT" in p.user for p in engine._model.prompts)
