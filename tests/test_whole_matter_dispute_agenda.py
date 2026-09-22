"""LB-109–112: a complete inventory is not a completed review."""

import json
from dataclasses import replace

import pytest
from nm.adapters.model.scripted import SCRIPTED_READS
from nm.core import briefing, dispute_agenda, posture
from nm.core.dispute import Described, interpret
from nm.core.screens import Screen, ScreenKind, ScreenState
from nm.core.threading import _with_identifiers, bind
from nm.core.turn import ScreenResult, TurnInput, _with_screens
from nm.domain.answer import Element, ElementKind
from nm.domain.matter import Basis, Fact, Matter, Posture, Provenance, Role, Thread
from nm.domain.quotable import Quotable
from nm.domain.summary import DERIVED_SECTIONS

from tests.test_matter_memory import _engine, _Recorder

pytestmark = pytest.mark.class_a


def matter(*threads):
    value = Matter.create(advocate_id="adv", title="Separate claims")
    for thread in threads:
        value = value.with_thread(thread)
    return value


def fact(text):
    return Fact.create(statement=text, provenance=Provenance(kind="advocate_statement", turn="t"))


def reviewed(label):
    return replace(
        Thread.create(label),
        posture=Posture(Role.PLAINTIFF, Basis.STATED),
        assessed=(*DERIVED_SECTIONS, "review_current"),
    )


def test_empty_and_unassessed_files_never_finish():
    for m in (
        matter(),
        matter(Thread.create("Rent")),
        matter(reviewed("Rent"), Thread.create("Access")),
    ):
        assert not dispute_agenda.project(m)["review_complete"]
        assert briefing.block(m)["state"] != "ready"


def test_every_dispute_must_earn_current_review_and_it_never_closes_the_file():
    a, b = reviewed("Rent"), reviewed("Access")
    result = dispute_agenda.project(matter(a, b))
    assert result["review_complete"]
    assert not result["matter_closed"]
    assert result["next_thread_id"] is None
    assert not dispute_agenda.project(matter(a, replace(b, assessed=DERIVED_SECTIONS)))[
        "review_complete"
    ]


def test_a_paused_dispute_and_repeated_question_stay_open_without_reasking():
    a = Thread.create("Access")
    m = matter(a).asking("G-POSTURE", "Who seeks relief?", "t1", a.id)
    m = m.asking("G-POSTURE", "Who seeks relief?", "t2", a.id)
    result = dispute_agenda.project(m)
    assert result["disputes"][0]["status"] == "waiting"
    assert result["next_thread_id"] is None
    assert not result["review_complete"]
    b = replace(reviewed("Rent"), deferred_reason="Awaiting the bank record")
    assert dispute_agenda.project(matter(b))["state"] == "waiting"


def test_unworked_dispute_precedes_repeated_material_request():
    a, b = Thread.create("Rent"), Thread.create("Access")
    m = matter(a, b).asking("G-POSTURE", "Who seeks relief?", "t1", a.id)
    assert dispute_agenda.project(m)["next_thread_id"] == b.id


def test_missing_internal_work_is_not_a_question_the_advocate_can_pause():
    a, b = Thread.create("Claim A"), Thread.create("Claim B")
    result = briefing.block(matter(a, b))
    assert result["state"] == "open"
    assert result["open_needs"] == []
    assert result["next_step"]["action"] == "assess"
    assert result["intake_complete_refused"]
    needed = replace(a, gaps=({"what": "The dated notice", "kind": "information"},))
    assert briefing.block(matter(needed, b))["open_needs"] == ["The dated notice"]


def test_explicit_advance_does_not_loop_on_the_same_urgent_gap():
    a, b = Thread.create("Claim A"), Thread.create("Claim B")
    a = replace(a, gaps=({"what": "Starting date", "kind": "deadline"},))
    m = matter(a, b)
    assert dispute_agenda.project(m)["next_thread_id"] == a.id
    assert dispute_agenda.project(m, after_thread_id=a.id)["next_thread_id"] == b.id
    assert not dispute_agenda.project(m, after_thread_id=a.id)["review_complete"]


@pytest.mark.parametrize("event_count", [1, 3])
def test_a_retrieved_trigger_cannot_certify_a_model_selected_event(tmp_path, event_count):
    from datetime import date
    from types import SimpleNamespace

    from nm.core import premise

    engine, _ = _engine(tmp_path, _Recorder())
    dated = [replace(fact(f"Recorded event {i}"), date=date(2020 + i, 2, 3))
             for i in range(event_count)]
    result = engine._premises(
        SimpleNamespace(ref="Retrieved provision", store="held", locator="p1"),
        dated[0], "retrieved trigger", "retrieved trigger", dated,
        TurnInput(message="Assess the period", advocate_id="adv", jurisdiction="Telangana"))
    assert premise.Kind.ACCRUAL_RULE in result.inferred()
    assert premise.Kind.ACCRUAL_RULE not in result.unestablished()


def test_last_focus_comes_from_the_saved_answer_not_thread_list_order():
    from types import SimpleNamespace

    a, b = Thread.create("Claim A"), Thread.create("Claim B")
    m = replace(matter(a, b), turn_receipts=(SimpleNamespace(answer={"elements": [
        {"kind": "question", "thread": a.id, "text": "A material question"}]}),))
    assert dispute_agenda.last_focus(m) == a.id
    assert dispute_agenda.project(m, after_thread_id=dispute_agenda.last_focus(m))[
        "next_thread_id"] == b.id
    only = replace(matter(a), turn_receipts=m.turn_receipts)
    assert dispute_agenda.project(only, after_thread_id=a.id)["next_thread_id"] is None
    assert not dispute_agenda.project(only, after_thread_id=a.id)["review_complete"]


def test_unknown_id_and_nonliteral_binding_cannot_change_a_file():
    a = Thread.create("Rent")
    for row in (
        Described("paid yesterday", "Rent", "someone-elses-thread"),
        Described("invented payment", "Rent", a.id),
    ):
        result = bind(matter(a), "paid yesterday", fact("paid yesterday"), described=(row,))
        assert result.blocks and result.thread is None


def test_continue_and_explicit_focus_keep_ids_without_merging_or_losing_work():
    a, b = reviewed("Rent"), reviewed("Access")
    msg = "Rent receipts arrived. The gate remains locked."
    result = bind(
        matter(a, b),
        msg,
        fact(msg),
        thread_hint=b.id,
        opens_new_dispute=False,
        described=(
            Described("Rent receipts arrived.", "Arrears", a.id),
            Described("The gate remains locked.", "Obstruction", b.id),
        ),
    )
    assert result.thread.id == b.id
    assert result.others[0].id == a.id
    assert result.others[0].assessed == a.assessed
    assert dict(result.allocations)[a.id] == ("Rent receipts arrived.",)


def test_identifier_enrichment_preserves_all_other_state():
    t = replace(
        reviewed("Rent"),
        gaps=({"what": "receipt", "blocks": "payment"},),
        parties={"Client": "client"},
        recommendation={"held": True},
    )
    enriched = _with_identifiers(t, {"case_number": "OS42/2026"})
    assert replace(enriched, identifiers=t.identifiers) == t


@pytest.mark.parametrize("role", [Role.PROSPECTIVE_CLAIMANT, Role.PROSPECTIVE_RESPONDENT])
def test_prospective_positions_need_stated_evidence_and_do_not_invent_filing(role):
    words = "I act for our client on the proposed claim, before anything is filed."
    row = {
        "states_client": True,
        "quoted": words,
        "client_described_as": "our client",
        "role": role.value,
        "role_basis": "stated",
        "opponent": "",
    }
    got = posture.interpret(Quotable(turn=words), row)
    assert got.role is role and got.basis is Basis.STATED
    assert Posture(got.role, got.basis).resolved
    assert posture.interpret(Quotable(turn=words), dict(row, role_basis="inferred")).refused
    assert posture.interpret_role({"role": role.value})[0] is None


def test_bad_focus_and_context_only_quotes_are_refused():
    row = {
        "verdict": "continues",
        "why": "update",
        "disputes": [],
        "focus_thread_id": "foreign",
        "focus_quote": "work this",
        "advance_quote": "",
    }
    assert interpret(Quotable(turn="work this"), row, thread_ids=frozenset({"local"})).refused
    row["focus_thread_id"] = "local"
    assert interpret(
        Quotable(turn="hello", context="work this"), row, thread_ids=frozenset({"local"})
    ).refused


def test_routine_screen_report_is_not_conversation_but_material_limits_remain():
    action = Element(kind=ElementKind.ACTION, text="Check the receipt before relying on payment.",
                     no_deadline_reason="An evidence check, not a dated procedural step.")
    checks = tuple(
        Screen(kind=k, state=ScreenState.CLEAR, detail="Recorded routine detail")
        for k in ScreenKind
    )
    report = ScreenResult(
        clear=True, assessed=True, reason="run", rows=("Long audit report",), screens=checks
    )
    assert _with_screens([action], report) == (action,)
    gap = Screen(
        kind=ScreenKind.COMPETENCE,
        state=ScreenState.CLEAR,
        detail="COVERAGE GAP -- Later local judgments are not held.",
    )
    out = _with_screens([action], replace(report, screens=(gap,)))
    assert out[0] == action and len(out) == 2
    assert out[1].disclosure and "not held" in out[1].text


def test_served_engine_keeps_scoped_accounts_and_persists_all_disputes(tmp_path, monkeypatch):
    spans = (
        "We act for the plaintiff seeking rent from X in 2025.",
        "We act for the defendant resisting Y's separate access claim in 2026.",
    )

    def inventory(_):
        return json.dumps(
            {
                "verdict": "cannot_tell",
                "quoted": "",
                "why": "opening",
                "disputes": [
                    {"quoted": text, "label": label, "thread_id": "", "additional_quotes": []}
                    for text, label in zip(spans, ("Rent", "Access"), strict=True)
                ],
                "focus_thread_id": "",
                "focus_quote": "",
                "advance_quote": "",
            }
        )

    monkeypatch.setitem(SCRIPTED_READS, "dispute", inventory)
    recorder = _Recorder()
    engine, store = _engine(tmp_path, model=recorder)
    out = engine.run(TurnInput(advocate_id="adv", message="\n".join(spans)))
    assert len(out.matter.threads) == 2
    by_id = {f.id: f for f in out.matter.facts}
    by_label = {t.label: t for t in out.matter.threads}
    a, b = by_label["Rent"], by_label["Access"]
    assert spans[0] in [by_id[i].statement for i in a.chronology]
    assert spans[1] not in [by_id[i].statement for i in a.chronology]
    assert spans[1] in [by_id[i].statement for i in b.chronology]
    assert spans[0] not in [by_id[i].statement for i in b.chronology]
    assert a.posture.role is Role.PLAINTIFF and b.posture.role is Role.DEFENDANT
    comparisons = [p for p in recorder.prompts if "THE DISPUTES ON THIS FILE:" in p.user]
    assert len(comparisons) == 1
    assert a.id in comparisons[0].user and b.id in comparisons[0].user
    assert all(s in comparisons[0].user for s in spans)
    assert not dispute_agenda.project(out.matter)["review_complete"]
    reopened = store.load(out.matter.id)
    assert [(t.id, t.chronology, t.posture) for t in reopened.threads] == [
        (t.id, t.chronology, t.posture) for t in out.matter.threads
    ]
