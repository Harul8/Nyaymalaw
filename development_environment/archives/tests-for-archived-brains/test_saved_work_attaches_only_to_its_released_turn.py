"""P52 controlled receipts: honest per-turn linkage and historic working scope."""

import copy
from dataclasses import replace

import pytest

from nm.advise.answer_contracts import Answer, Element, ElementKind, Mode, Route
from nm.advise.turn_receipt_contracts import TurnReceipt, answer_payload
from nm.Archives.legal_brain.understand.brain_context import ContextSession, assemble_brief
from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopRecord, StepKind, StopReason
from nm.Archives.legal_brain.communicate.loop_progress import links_released_turn, progress, recorded_scope
from tests.test_brain_context_is_a_checked_file_projection import file_fixture, snapshot
from tests.test_saved_loop_progress_is_not_an_advice_transport import AT, SECRET, add, base, work

pytestmark = pytest.mark.class_a


def scoped_work(*, actor="adv_demo", matter_id="scoped_progress_matter", turn_id="scoped_turn"):
    matter = replace(file_fixture(), id=matter_id, advocate_id=actor, version=1)
    original = work(actor=actor, matter_id=matter_id, turn_id=turn_id)
    brief = assemble_brief(matter, advocate_id=actor)
    session = ContextSession(snapshot(), (), brief, provider="scripted", model="scripted:author")
    record = add(LoopRecord(original.identity), StepKind.START, {"context": session.to_record()})
    record = add(record, StepKind.MODEL_STARTED, {"private_context": SECRET})
    record = add(record, StepKind.MODEL_RETURNED, {"assessment": SECRET})
    record = add(record, StepKind.STOP, {"reason": StopReason.QUESTION.value, "question": SECRET})
    answer = Answer(
        Route.MATTER,
        Mode.FULL_BRIEF,
        "Recorded response",
        (Element(ElementKind.QUESTION, "Please provide the original document."),),
    )
    receipt = TurnReceipt(
        turn_id,
        original.identity.offer_hash,
        AT,
        answer_payload(answer),
        "Please assess the records.",
        True,
    )
    return replace(
        matter, loop_records=(record,), turn_receipts=(receipt,), turns_applied=(turn_id,)
    ), record


def test_scope_is_the_original_checked_file_not_the_current_board_or_private_judgment():
    matter, record = scoped_work()
    renamed = replace(
        matter, threads=tuple(replace(row, label="Renamed today") for row in matter.threads)
    )
    scoped = recorded_scope(record)
    assert scoped["state"] == "recorded"
    assert [row["label"] for row in scoped["disputes"]] == ["One", "Two"]
    assert scoped["separate_dispute_progress"] == "not_established"
    assert scoped["shared_stages"] is True
    assert links_released_turn(renamed, record)
    assert SECRET not in str(progress(record))
    assert "Renamed today" not in str(progress(record))


@pytest.mark.parametrize(
    "field,value",
    [
        ("matter_id", "another_matter"),
        ("advocate_id", "another_advocate"),
        ("snapshot_id", "a" * 64),
        ("selected_issue_ids", ["missing"]),
        ("selected_issue_ids", ["dispute_one", "dispute_one"]),
        ("selected_issue_ids", [" "]),
        ("source_record_json", "[]"),
        ("source_record_json", "not json"),
    ],
)
def test_changed_or_unowned_scope_is_not_displayed(field, value):
    _, record = scoped_work()
    payload = copy.deepcopy(record.events[0].payload)
    assert field in payload["context"]["brief"]
    payload["context"]["brief"][field] = value
    changed = add(LoopRecord(record.identity), StepKind.START, payload)
    scoped = recorded_scope(changed)
    assert scoped["state"] == "not_established"
    assert scoped["disputes"] == []


@pytest.mark.parametrize(
    "mutation", ["no_receipt", "no_applied", "duplicate_applied", "wrong_offer", "wrong_actor"]
)
def test_coincident_turn_identity_does_not_claim_a_released_response_link(mutation):
    matter, record = scoped_work()
    assert links_released_turn(matter, record)
    if mutation == "no_receipt":
        matter = replace(matter, turn_receipts=())
    elif mutation == "no_applied":
        matter = replace(matter, turns_applied=())
    elif mutation == "duplicate_applied":
        matter = replace(matter, turns_applied=matter.turns_applied * 2)
    elif mutation == "wrong_offer":
        receipt = replace(matter.turn_receipts[0], offer_fingerprint="d" * 64)
        matter = replace(matter, turn_receipts=(receipt,))
    else:
        matter = replace(matter, advocate_id="another_advocate")
    assert not links_released_turn(matter, record)


def test_actual_owned_routes_link_only_the_strict_release_and_keep_the_loop_candidate_unreleased(
    client,
):
    from nm.app.api import application

    matter, record = scoped_work()
    application().store.commit(matter, expected_version=0)
    response = client.get(base(record))
    assert response.status_code == 200
    assert response.json()["linked_released_turn"] is True
    assert response.json()["result_state"] == "not_released"
    assert response.json()["scope"]["disputes"] == [
        {"issue_id": "dispute_one", "label": "One"},
        {"issue_id": "dispute_two", "label": "Two"},
    ]
    assert SECRET not in response.text
    listed = client.get(f"/api/matters/{matter.id}/loops").json()["loops"]
    assert listed[0]["linked_released_turn"] is True
