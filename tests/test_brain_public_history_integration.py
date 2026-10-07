"""Historical and fresh context share public storage without rewriting old proof.

All meanings and reviewer decisions are scripted. These checks exercise the
authenticated public boundary, exact source reconstruction and durable replay;
they make no claim about real-model semantic quality.
"""

from copy import deepcopy
from dataclasses import replace

import pytest

from nm.advise.answer_contracts import (
    Answer,
    Element,
    ElementKind,
    Mode,
    ReplyParagraph,
    Route,
)
from nm.advise.turn_receipt_contracts import TurnReceipt, answer_payload
from nm.brain import turn as boundary
from nm.brain.conversation import Message
from nm.work_the_file.matter_contracts import Matter
from tests.test_brain_continuation_service import send
from tests.test_brain_evidence_rendering_public import RawExpressionModel, raw_unit
from tests.test_brain_turn import plan

MATTER = "mat_public_history_versions"
OLDER = "historical-z-first"
OLDER_SECOND = "historical-a-second"
ORIGINAL = "I need to distinguish the collection event from the inspection."
FINDING = "The historical working finding concerns collection."
PUBLIC = "Which date did you mean for the inspection?"
OLD_REQUEST = "Compare my present request with your earlier explanation."
NEW_REQUEST = "Compare this answer with the question you actually showed me."
PUBLIC_CONTRACT = "public_reply_v2"


def _receipt(identity, words, working, visible, at):
    answer = Answer(
        route=Route.NON_MATTER,
        mode=Mode.EXPLANATION,
        mode_statement="A released historical explanation.",
        elements=(Element(ElementKind.GROUND, working),),
        composed=(ReplyParagraph(visible),),
    )
    return TurnReceipt(identity, "0" * 64, at, answer_payload(answer), words, True)


def _seed_older(wired, mixed_offsets):
    receipts = [_receipt(OLDER, ORIGINAL, FINDING, PUBLIC,
                         "2026-09-07T10:00:00+05:30")]
    if mixed_offsets:
        # This is later in real time, but sorts before 10:00 as an ISO string.
        receipts.append(_receipt(
            OLDER_SECOND, "Keep the two events separate.",
            "The second historical finding preserves separate events.",
            "I will keep your two reported events separate.",
            "2026-09-07T05:00:00+00:00"))
    matter = Matter(
        id=MATTER, advocate_id="adv_demo", title="Historical conversation continuity",
        turns_applied=tuple(receipt.turn_id for receipt in receipts),
        turn_receipts=tuple(receipts), version=1,
    )
    return wired.store.commit(matter, expected_version=0)


def _compare_earlier_nm(payload):
    unit = raw_unit(payload, operator="comparison", all_sources=False)
    earlier = next(message for message in payload["earlier_conversation"]
                   if message["turn_id"] == OLDER and message["role"] == "nm")
    sources = [earlier["source_spans"][0]["id"], payload["latest_message_spans"][0]["id"]]
    unit["blocks"][0]["evidence_expression"]["source_ids"] = sources
    return {"units": [unit]}


def _wire(wired, monkeypatch, request):
    model = RawExpressionModel(
        [plan(request, scope="current", relation="continues")], [_compare_earlier_nm])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    return model


def _pre_change_generation(monkeypatch):
    """Generate and seal v1 honestly; never remove a marker from a saved row.

    The historical service used lexical older-row ordering and element wording.
    Emulate those inputs only while the original turn is being generated. The
    normal writer, review, mutation, persistence and seal owners still run.
    """
    read = boundary.from_turns
    older = boundary.released_older_turns
    execute = boundary._material_execution

    def legacy_read(turns, **kwargs):
        validated = read(turns, **kwargs)
        messages = []
        for row in turns:
            reply = "\n".join(element["text"] for element in row["elements"]
                              if element["text"].strip())
            if not reply:
                reply = row["blocked_reason"]
            messages.extend((Message(row["turn_id"], "advocate", row["message"]),
                             Message(row["turn_id"], "nm", reply)))
        return replace(validated, messages=tuple(messages))

    def legacy_older(store, matter):
        return sorted(older(store, matter),
                      key=lambda row: (str(row.get("at") or ""), str(row["turn_id"])))

    def legacy_execution(*args, **kwargs):
        execution = execute(*args, **kwargs)
        execution.pop("context_contract", None)
        return execution

    monkeypatch.setattr(boundary, "from_turns", legacy_read)
    monkeypatch.setattr(boundary, "released_older_turns", legacy_older)
    monkeypatch.setattr(boundary, "_material_execution", legacy_execution)


def _input(model, operation):
    calls = [payload for observed, payload in model.calls if observed == operation]
    assert len(calls) == 1, "A context handoff must not need an extra correction call."
    return calls[0]


def _reference(answer):
    blocks = answer["continuation"]["units"][0]["blocks"]
    return next(reference for block in blocks for reference in block["references"]
                if reference.get("turn_id") == OLDER and reference.get("role") == "nm")


def _visible_transcript(body):
    result = []
    for row in body["turns"]:
        shown = row.get("composed") or row["elements"]
        result.extend((
            {"turn_id": row["turn_id"], "role": "advocate", "text": row["message"]},
            {"turn_id": row["turn_id"], "role": "nm",
             "text": "\n".join(element["text"] for element in shown if element["text"].strip())},
        ))
    return result


@pytest.mark.parametrize("mixed_offsets", [False, True], ids=["composed", "order-and-composed"])
def test_public_context_preserves_genuine_v1_proof_while_new_turn_uses_public_words(
        client, wired, monkeypatch, mixed_offsets):
    seeded = _seed_older(wired, mixed_offsets)
    opened = {"matter_id": seeded.id, "chat_id": None}
    with monkeypatch.context() as previous:
        _pre_change_generation(previous)
        old_model = _wire(wired, previous, OLD_REQUEST)
        old_answer = send(client, OLD_REQUEST, "native-v1", opened=opened)
    old_saved = deepcopy(wired.store.load(MATTER))
    old_row = deepcopy(old_saved.brain_chat[0])
    old_receipt = old_row["response"]["material_coverage"]["execution"]
    assert "context_contract" not in old_receipt
    assert old_answer["blocked"] is False
    assert old_answer["metrics"]["llm_calls"] == 3
    assert _reference(old_answer)["text"] == FINDING
    old_input = _input(old_model, "interpret_conversation")["earlier_conversation"]
    assert next(row["text"] for row in old_input
                if row["turn_id"] == OLDER and row["role"] == "nm") == FINDING

    # The readback used by the browser is the complete actual public transcript.
    readback = client.get(f"/api/matters/{MATTER}/transcript")
    assert readback.status_code == 200, readback.text
    assert readback.json()["state"] == "ok", readback.text
    expected = _visible_transcript(readback.json())
    expected_older = [OLDER, OLDER_SECOND] if mixed_offsets else [OLDER]
    assert [row["turn_id"] for row in expected if row["role"] == "advocate"] == [
        *expected_older, "native-v1"]
    assert next(row["text"] for row in expected
                if row["turn_id"] == OLDER and row["role"] == "nm") == PUBLIC

    current_model = _wire(wired, monkeypatch, NEW_REQUEST)
    fresh = send(client, NEW_REQUEST, "native-v2", opened=opened)
    assert fresh["blocked"] is False
    assert fresh["metrics"]["llm_calls"] == 3
    interpreted = _input(current_model, "interpret_conversation")["earlier_conversation"]
    assert interpreted == expected
    assert _reference(fresh)["text"] == PUBLIC
    if mixed_offsets:
        assert _reference(fresh)["id"] != _reference(old_answer)["id"]
    current = deepcopy(wired.store.load(MATTER))
    assert current.brain_chat[0] == old_row
    assert current.turn_receipts == old_saved.turn_receipts
    assert current.brain_chat[-1]["response"]["material_coverage"]["execution"][
        "context_contract"] == PUBLIC_CONTRACT

    # Reopen and replay both versions through the shipped boundaries. Neither
    # replay may regenerate the response, mutate the old seal or dispatch a model.
    before_calls = len(current_model.calls)
    detail = client.get(f"/api/matters/{MATTER}")
    transcript = client.get(f"/api/matters/{MATTER}/transcript")
    assert detail.status_code == transcript.status_code == 200
    assert transcript.json()["state"] == "ok"
    for message, identity, original in (
            (OLD_REQUEST, "native-v1", old_answer), (NEW_REQUEST, "native-v2", fresh)):
        replay = send(client, message, identity, opened=opened)
        assert replay["replayed"] is True
        assert replay["metrics"]["llm_calls"] == 0
        assert replay["elements"] == original["elements"]
        assert replay["continuation"] == original["continuation"]
    assert len(current_model.calls) == before_calls
    assert wired.store.load(MATTER) == current
    assert len(current.brain_chat) == 2

