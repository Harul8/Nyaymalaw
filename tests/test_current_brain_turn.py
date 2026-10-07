"""Focused turn-owner failure injection; no real model calls."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from nm.brain.turn import BrainRefused, BrainService, BrainTurn, _digest, saved_rows
from nm.shared.store_port import StaleWrite
from tests.test_current_brain_app import WiredModel, greeting_outputs, mixed_outputs


class MemoryStore:
    def __init__(self, *, lost_ack=False, fail_write=False):
        self.value = None
        self.lost_ack, self.fail_write = lost_ack, fail_write
        self.commits = 0

    def load(self, identity):
        return deepcopy(self.value)

    def commit(self, matter, *, expected_version):
        self.commits += 1
        if (self.value.version if self.value else 0) != expected_version:
            raise StaleWrite("changed")
        if self.fail_write:
            raise OSError("synthetic write failure")
        self.value = deepcopy(matter)
        if self.lost_ack:
            self.lost_ack = False
            raise OSError("synthetic lost acknowledgement")
        return deepcopy(self.value)


def turn(**changes):
    return BrainTurn(**{"advocate_id": "adv_owner", "turn_id": "turn_one", "message": "Hello.", **changes})


def service(model=None, store=None, session=None):
    model = model or WiredModel(*greeting_outputs())
    store = store or MemoryStore()
    return BrainService(store=store, model=model, session_current=session or (lambda: True)), model, store


def test_confirmed_save_after_lost_ack_returns_receipt_without_repeating_model_calls():
    brain, model, store = service(store=MemoryStore(lost_ack=True))
    output = brain.run(turn()).as_dict()
    assert output["committed"] == "committed" and output["replayed"] is True
    assert len(model.calls) == 3 and store.commits == 1
    again = brain.run(turn()).as_dict()
    assert again == output and len(model.calls) == 3 and store.commits == 1
    assert len(store.value.brain_chat) == 1


def test_unconfirmed_write_never_claims_save_or_releases_a_reply():
    brain, model, store = service(store=MemoryStore(fail_write=True))
    with pytest.raises(BrainRefused) as caught:
        brain.run(turn())
    assert caught.value.committed == "unconfirmed"
    assert store.value is None and len(model.calls) == 3


def test_session_expiration_before_commit_prevents_save_and_public_release():
    brain, model, store = service()
    brain.session_current = lambda: len(model.calls) < 3
    with pytest.raises(BrainRefused) as caught:
        brain.run(turn())
    assert caught.value.status == 401 and store.value is None and store.commits == 0


@pytest.mark.parametrize("field,value", [
    ("composed", [{"text": "I completed and filed everything."}]),
    ("material", [{"understanding": "Unsupported saved fact"}]),
    ("board_changes", [{"kind": "completed", "text": "The date was corrected."}]),
    ("continuation", {"reply": "Unsupported extra prose"}),
])
def test_replay_rejects_public_prose_outside_the_owned_release(field, value):
    brain, _, store = service()
    brain.run(turn())
    rows = deepcopy(store.value.brain_chat)
    rows[0]["response"][field] = value
    rows[0]["response_digest"] = _digest(rows[0]["response"])
    changed = replace(store.value, brain_chat=rows)
    with pytest.raises(BrainRefused, match="saved conversation"):
        saved_rows(changed, "adv_owner")


def test_replay_rejects_incomplete_history_even_when_the_remaining_row_is_valid():
    brain, model, store = service(WiredModel(*greeting_outputs(), *greeting_outputs()))
    first = brain.run(turn()).as_dict()
    brain.run(turn(turn_id="turn_two", message="Thanks.", chat_id=first["chat_id"], expected_version=1))
    changed = replace(store.value, brain_chat=store.value.brain_chat[:-1])
    with pytest.raises(BrainRefused, match="saved conversation"):
        saved_rows(changed, "adv_owner")
    assert len(model.calls) == 6


def test_replay_rejects_private_preparation_detached_from_original_context():
    brain, _, store = service()
    brain.run(turn())
    rows = deepcopy(store.value.brain_chat)
    rows[0]["preparation"]["sources"][-1]["message"]["text"] = "An unrelated original request."
    changed = replace(store.value, brain_chat=rows)
    with pytest.raises(BrainRefused, match="saved conversation"):
        saved_rows(changed, "adv_owner")


def test_partial_release_service_status_survives_save_and_replay():
    message = "I received a draft. Please explain it."
    outputs = mixed_outputs(message)
    outputs[-1]["unit_reviews"][1].update(verdict="unsupported", reason="restriction")
    brain, model, store = service(WiredModel(*outputs))
    first = brain.run(turn(message=message)).as_dict()
    assert first["service_status"] == "Some of this message could not be prepared for a response."
    assert store.value.brain_chat[0]["response"]["service_status"] == first["service_status"]
    again = brain.run(turn(message=message)).as_dict()
    assert again["service_status"] == first["service_status"] and again["replayed"] is True
    assert len(model.calls) == 3
    model.outputs.extend(greeting_outputs())
    brain.run(turn(turn_id="turn_next", message="Thank you.", chat_id=first["chat_id"], expected_version=1))
    context = json.loads(model.calls[3][0].user)["earlier_conversation"]
    assert context[-1]["role"] == "nm" and context[-1]["service_status"] == first["service_status"]


def test_wrong_owner_history_is_rejected_before_dispatch():
    brain, model, store = service()
    brain.run(turn())
    store.value = replace(store.value, advocate_id="another_owner", brain_chat=())
    with pytest.raises(BrainRefused) as caught:
        brain.run(turn(turn_id="turn_two"))
    assert caught.value.status == 404 and len(model.calls) == 3


def test_explicit_missing_chat_is_not_silently_reclassified_as_a_first_message():
    brain, model, store = service()
    with pytest.raises(BrainRefused) as caught:
        brain.run(turn(chat_id="chat_that_is_not_available"))
    assert caught.value.status in (404, 409)
    assert model.calls == [] and store.commits == 0
