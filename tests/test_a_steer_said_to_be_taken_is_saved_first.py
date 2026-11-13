"""A steer said to be 'taken' is saved first (plan AN.52, piece 52h; D214; the review's F-20).

A steer was added to a list in the server's memory and answered "taken"; it reached the store only when the turn's next step
took it. A restart in between lost the advocate's correction silently, and Continue went on without it. The steer is now saved
beside the conversation before "taken" is said, and a turn that is continued takes up a steer saved for it that it never took.
Offline: scripted models and a synthetic store; the words are invented.
"""
import pytest

from nm.core_engine import turn
from nm.core_engine.conversation import STEERING, chat_matter_id, hold_steer, steering_of, stored_chat
from nm.shared.external_ai_contracts import ModelPermissionRefused
from tests.test_core_answer_sections import Scripted, through_turns
from tests.test_core_turn import FileMatterStore, run

pytestmark = pytest.mark.class_a
STEER = {"text": "Take the second notice into account too.", "documents": [], "at": "2026-11-13T10:00:00+00:00"}


@pytest.fixture
def store(tmp_path):
    return FileMatterStore(tmp_path, key="synthetic-turn-fixture")


def conversation(store):
    return store.load(chat_matter_id("owner", stored_chat("owner", None, "t1")))


def stopped_with_a_steer_saved_and_never_taken(store):
    """A turn that is told a steer as it works - saved beside its conversation, as the server now does before it says 'taken' -
    and then stops before any step takes it: the server's memory of the steer is gone, as after a restart."""
    scripted = Scripted(refuse={"core_response_overview"})
    model = through_turns(scripted)
    first, writer, told = model.structured, {}, []

    def structured(prompt, schema, tier, **kwargs):
        if prompt.operation == "core_response_cross_check" and not told:
            told.append(True)
            writer["write"](lambda context: hold_steer(store, context, STEER))
        return first(prompt, schema, tier, **kwargs)
    model.structured = structured
    with pytest.raises(ModelPermissionRefused):
        run(store, model, attach=lambda advocate, chat, write: writer.update(write=write), steers=lambda: [])
    assert told and steering_of(conversation(store), "t1") == [STEER], "the steer is in the store although no step took it"
    return scripted


def test_a_steer_saved_and_never_taken_is_in_the_conversation_after_continue(store):
    scripted = stopped_with_a_steer_saved_and_never_taken(store)
    scripted.refuse.clear()
    response = run(store, through_turns(scripted))
    assert response["committed"] == "committed"
    saved = conversation(store)
    rows = turn.saved_rows(saved, "owner")
    assert rows[0]["steers"] == [STEER] and rows[0]["message"] == "Hello.", "the steer is in the conversation"
    assert STEERING not in saved.intake_answers, "and no longer waits beside it"
    reviews = [payload for name, payload in scripted.calls if name == "core_response_review"]
    assert any(STEER["text"] in str(payload) for payload in reviews), "the answer was reviewed against the steer"
    assert run(store, through_turns(Scripted()))["replayed"], "reopened, the turn is read exactly as saved"


def test_a_steer_the_turn_did_take_is_not_taken_twice(store):
    """Saved beside the conversation and then taken by the turn's next step, as on any ordinary day."""
    import threading
    pressed, waiting = threading.Event(), []
    scripted = Scripted()
    model = through_turns(scripted)
    first, writer = model.structured, {}

    def structured(prompt, schema, tier, **kwargs):
        out = first(prompt, schema, tier, **kwargs)
        if prompt.operation == "core_response_cross_check" and not pressed.is_set() and not writer.get("told"):
            writer["told"] = True
            writer["write"](lambda context: hold_steer(store, context, STEER))
            waiting.append(STEER)
            pressed.set()
        return out
    model.structured = structured

    def steers():
        taken = list(waiting)
        waiting.clear()
        pressed.clear()
        return taken
    response = run(store, model, stopping=pressed.is_set, steers=steers,
                   attach=lambda advocate, chat, write: writer.update(write=write))
    assert response["committed"] == "committed"
    assert turn.saved_rows(conversation(store), "owner")[0]["steers"] == [STEER], "once"
    assert STEERING not in conversation(store).intake_answers


def test_a_steer_that_cannot_be_read_reliably_is_not_saved_and_one_of_an_earlier_turn_is_not_taken(store):
    scripted = stopped_with_a_steer_saved_and_never_taken(store)
    saved = conversation(store)
    assert steering_of(saved, "another-turn") == [], "a steer is for the turn it was sent to"
    from dataclasses import replace
    damaged = replace(saved, intake_answers={**saved.intake_answers, STEERING: [{"turn_id": "t1", "steer": {"text": ""}}]},
                      version=saved.version + 1)
    assert steering_of(damaged, "t1") == [], "what cannot be read is not put into an answer"
    assert steering_of(replace(saved, intake_answers={**saved.intake_answers, STEERING: "words"}), "t1") == []
    assert scripted is not None


# ---- through the server (52h2): saved before "taken" is said; a restart; Continue ----

from tests.test_core_answer_sections import scripted_answers  # noqa: E402
from tests.test_core_served import OWNER, served  # noqa: E402, F401 - pytest fixture

SENT = {"message": "Inspect this reported account.", "turn_id": "turn-1"}
WORDS = "Weigh the later notice too."


def test_taken_is_said_only_after_the_steer_is_in_the_store_and_a_restart_then_continue_keeps_it(served):
    scripted = Scripted(refuse={"core_response_overview"})  # the turn stops later, as a restart stops it: no step takes the steer
    scripted_answers(served, scripted)
    answering, seen = served.model.structured, {}

    def structured(prompt, schema, tier, **kwargs):
        if prompt.operation == "core_response_cross_check" and not seen:
            seen["reply"] = served.client.post("/api/turn/steer", json={"turn_id": "turn-1", "message": WORDS}).json()
            matter = served.store.load(chat_matter_id(OWNER, stored_chat(OWNER, None, "turn-1")))
            seen["in_store"] = [steer["text"] for steer in steering_of(matter, "turn-1")]
            # The restart: the server's memory of the steer is gone before any step took it.
            for running in served.app._running.values():
                running.take()
        return answering(prompt, schema, tier, **kwargs)
    served.model.structured = structured
    assert served.client.post("/api/turn", json=SENT).status_code == 403
    assert seen["reply"] == {"state": "taken"} and seen["in_store"] == [WORDS], "in the store when 'taken' was said"
    served.app.turn_progress.end(OWNER, "turn-1", "stopped")

    after = Scripted()
    scripted_answers(served, after)
    chat_id = stored_chat(OWNER, None, "turn-1")
    reply = served.client.post("/api/turn/continue", json={"chat_id": chat_id, "turn_id": "turn-1"})
    assert reply.status_code == 200, reply.text
    rows = turn.saved_rows(served.store.load(chat_matter_id(OWNER, chat_id)), OWNER)
    assert [steer["text"] for steer in rows[0]["steers"]] == [WORDS], "the steer is in the conversation"
    assert any(WORDS in str(payload) for payload in after.payloads("core_response_review"))


def test_a_steer_that_cannot_be_saved_is_not_said_to_be_taken(served):
    from nm.core_engine import conversation
    scripted_answers(served, Scripted())
    answering, seen = served.model.structured, {}

    def refusing(store, context, steer):
        raise OSError("the store refused the write")

    def structured(prompt, schema, tier, **kwargs):
        if prompt.operation == "core_response_cross_check" and not seen:
            real, conversation.hold_steer = conversation.hold_steer, refusing
            try:
                seen["reply"] = served.client.post("/api/turn/steer", json={"turn_id": "turn-1", "message": WORDS})
            finally:
                conversation.hold_steer = real
        return answering(prompt, schema, tier, **kwargs)
    served.model.structured = structured
    reply = served.client.post("/api/turn", json=SENT)
    assert reply.status_code == 200, reply.text
    assert seen["reply"].json() != {"state": "taken"}, "the page then sends the message as the next one"
    rows = turn.saved_rows(served.store.load(chat_matter_id(OWNER, reply.json()["chat_id"])), OWNER)
    assert "steers" not in rows[0]
