"""A save that lost a race is 'not saved', and Continue saves it (plan AN.50, piece 50b; D188; the review's F-07).

The final save of an answer is refused as stale where the conversation moved under it - another write beside it landed first, as
the conversation's title once did. The refusal writes nothing, and a clean reload that does not hold the answer makes the
outcome known: not saved. It used to be said as 'could not be confirmed', and the message's attempt was then refused for ever.
Now the answer is kept and Continue saves it on the conversation as it then stands, with no model call. An outcome still
unknown - an OS error whose write may yet land, or a reload that fails - stays 'unconfirmed' (tests/test_core_served.py keeps
that case). Plan AN.50 (50c, D189): nothing writes beside the conversation once its final save begins, so the late title that
once moved it, and a message queued meanwhile, now wait for the save and are written on the conversation as saved. Offline: the
scripted model and a temporary store; the words are invented.
"""
import threading
import time
from dataclasses import replace

import pytest

from nm.core_engine import titles, turn
from nm.core_engine.conversation import (
    HEADER, SHOWN, ConversationRefused, commit_turn, hold_shown, open_turn, queued_of, sent, shown_of, title_of,
)
from nm.shared.store_file_store import FileMatterStore
from nm.shared.store_port import StaleWrite
from tests.test_core_served import OWNER, send, served, successful  # noqa: F401 - pytest fixture

pytestmark = pytest.mark.class_a


def renamed_meanwhile(store, matter_id, title="Renamed meanwhile"):
    """Another write, made outside the turn's own writer, moves the conversation's version."""
    current = store.load(matter_id)
    return store.commit(replace(current, title=title, version=current.version + 1), expected_version=current.version)


def test_a_write_from_outside_the_turn_that_moved_the_conversation_leaves_the_answer_kept_for_continue(served, monkeypatch):
    """Plan AN.50 (50b4, D188): the final save is refused as stale and the turn's record of the finished answer is written again
    on the conversation as it now stands - the other write's change and the answer both kept - so Continue saves it."""
    original = served.store.commit
    moved = []

    def racing(matter, **kwargs):
        if matter.brain_chat and not moved:
            moved.append(renamed_meanwhile(served.store, matter.id))
        return original(matter, **kwargs)
    monkeypatch.setattr(served.store, "commit", racing)
    reply = send(served)
    assert reply.status_code == 409, reply.text
    detail = reply.json()["detail"]
    assert (detail["code"], detail["committed"], detail["retryable"], detail.get("kept")) == (
        "not_saved", "not_committed", True, True)
    (matter,) = served.store.list_for(OWNER).matters
    held = shown_of(matter)
    assert matter.brain_chat == () and held["stopped"]["code"] == "not_saved" and held["steps"]["answered"]["sections"]
    assert matter.title == "Renamed meanwhile", "the other write's change is kept"
    calls = len(served.model.calls)
    monkeypatch.setattr(served.store, "commit", original)
    saved = successful(served)  # Continue
    assert len(served.model.calls) == calls and saved["elements"] == held["elements"]
    (matter,) = served.store.list_for(OWNER).matters
    assert len(matter.brain_chat) == 1 and matter.title == "Renamed meanwhile"


def test_a_write_beside_is_made_again_only_where_nothing_it_rewrites_was_changed_by_another(tmp_path):
    store = FileMatterStore(tmp_path, key="synthetic-not-a-secret")
    context = open_turn(store, advocate_id="owner", message="Words", turn_id="t1")

    def record(words):
        return {**sent("t1", context.request, "Words", (), 0, at="2026-11-13T00:00:00+00:00"),
                "elements": [{"text": words}]}
    context = hold_shown(store, context, record("First part."))
    renamed_meanwhile(store, context.matter.id)
    context = hold_shown(store, context, record("Second part."))
    saved = store.load(context.matter.id)
    assert saved.title == "Renamed meanwhile" and shown_of(saved)["elements"] == [{"text": "Second part."}]
    # Another writer changes what this turn showed: nothing of it may be put back, so the write is refused.
    current = store.load(context.matter.id)
    store.commit(replace(current, intake_answers={**current.intake_answers, SHOWN: record("Another's part.")},
                         version=current.version + 1), expected_version=current.version)
    with pytest.raises(StaleWrite):
        hold_shown(store, context, record("Third part."))
    assert shown_of(store.load(context.matter.id))["elements"] == [{"text": "Another's part."}]


def landing_under_the_save(served, monkeypatch, write):
    """As the answer's final save begins, write(matter) starts another write beside the conversation and is given a second to
    land under the save. Returns what landed (one bool) and the store's own save."""
    landed, original_commit = [], served.store.commit

    def saving(matter, **kwargs):
        if matter.brain_chat and not landed:
            arrived = write(matter)
            deadline = time.monotonic() + 1
            while not arrived(served.store.load(matter.id)) and time.monotonic() < deadline:
                time.sleep(0.01)
            landed.append(arrived(served.store.load(matter.id)))
        return original_commit(matter, **kwargs)
    monkeypatch.setattr(served.store, "commit", saving)
    return landed, original_commit


def until(condition, seconds=30):
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.01)
    return condition()


def test_a_title_arriving_after_the_wait_and_before_the_save_waits_for_the_save_and_is_then_kept_with_it(served, monkeypatch):
    """Plan AN.50 (50c, D189; the review's trigger for F-07): the conversation's title, still being written when the answer is
    ready, arrives after the turn has stopped waiting for it and before the answer is saved. It once moved the conversation
    under the save, which was then refused. Nothing writes beside the conversation once the final save begins: the title waits
    for the save and is then written on the conversation as saved."""
    monkeypatch.setattr(turn, "TITLE_WAIT", 0.05)
    release, original_call = threading.Event(), served.model.structured

    def calling(prompt, schema, tier, **kwargs):
        if prompt.operation == titles.OPERATION:
            release.wait(30)  # the title is slow: it is ready only once the final save has begun
        return original_call(prompt, schema, tier, **kwargs)
    monkeypatch.setattr(served.model, "structured", calling)
    landed, _ = landing_under_the_save(served, monkeypatch,
                                       lambda matter: release.set() or (lambda saved: title_of(saved) is not None))
    saved = successful(served)
    assert landed == [False], "the title did not move the conversation under the save"
    assert until(lambda: title_of(served.store.list_for(OWNER).matters[0]) is not None), "the title is written after it"
    (matter,) = served.store.list_for(OWNER).matters
    assert len(matter.brain_chat) == 1 and matter.brain_chat[0]["response"]["elements"] == saved["elements"]


def test_a_message_queued_as_the_answer_is_saved_waits_for_the_save_and_is_then_kept_with_it(served, monkeypatch):
    """Plan AN.50 (50c, D189): what waits to be sent, written by the turn's own writer while the answer is being saved, waits for
    the save and is then written on the conversation as saved - neither write undoes the other."""
    waiting, queuing = [{"text": "Then the second notice.", "documents": []}], []

    def queue(matter):
        queuing.append(threading.Thread(target=served.app.save_queued, kwargs={
            "advocate_id": OWNER, "chat_id": matter.intake_answers[HEADER]["chat_id"], "queued": waiting}))
        queuing[0].start()
        return lambda saved: queued_of(saved) == waiting
    landed, _ = landing_under_the_save(served, monkeypatch, queue)
    saved = successful(served)
    queuing[0].join(30)
    assert landed == [False] and not queuing[0].is_alive()
    (matter,) = served.store.list_for(OWNER).matters
    assert len(matter.brain_chat) == 1 and matter.brain_chat[0]["response"]["elements"] == saved["elements"]
    assert queued_of(matter) == waiting, "what waits is kept with the saved answer"


def test_an_answer_the_store_would_not_keep_is_not_said_to_be_kept(served, monkeypatch):
    """Plan AN.50 (50b3): 'kept' is said only where the turn's record of why it stopped was written. A write from outside the
    turn moves the conversation under the save, and the store will not take the record of why the turn stopped either."""
    original_commit = served.store.commit

    def racing(matter, **kwargs):
        if matter.brain_chat and not racing.moved:
            racing.moved = renamed_meanwhile(served.store, matter.id)
        if ((matter.intake_answers or {}).get(SHOWN) or {}).get("stopped"):
            raise OSError("Synthetic store that will not take the stop")
        return original_commit(matter, **kwargs)
    racing.moved = None
    monkeypatch.setattr(served.store, "commit", racing)
    reply = send(served)
    assert reply.status_code == 409, reply.text
    detail = reply.json()["detail"]
    assert (detail["code"], detail["committed"], detail["retryable"]) == ("not_saved", "not_committed", True)
    assert "kept" not in detail, "the stop was not written, so it is not said to be kept"
    (matter,) = served.store.list_for(OWNER).matters
    assert matter.brain_chat == () and shown_of(matter)["stopped"] is None
    monkeypatch.setattr(served.store, "commit", original_commit)
    saved = successful(served)  # the same message sent again goes on from the steps that were kept
    assert not saved["replayed"] and saved["elements"]
    (matter,) = served.store.list_for(OWNER).matters
    assert len(matter.brain_chat) == 1


class Refusing:
    """A store that refuses every save as stale, and whose reload gives `loaded` or raises it."""

    def __init__(self, loaded):
        self.loaded = loaded

    def commit(self, matter, *, expected_version):
        raise StaleWrite("the conversation moved")

    def load(self, matter_id):
        if isinstance(self.loaded, Exception):
            raise self.loaded
        return self.loaded


def saving(store):
    context = open_turn(FileMatterStore(store, key="synthetic-not-a-secret"), advocate_id="owner", message="Words", turn_id="t1")
    return lambda refusing: commit_turn(refusing, context, elements=[{"text": "Reply."}], activities={"fixture": "admitted"},
                                        session_current=lambda: True)


def test_a_stale_refusal_with_a_clean_reload_is_not_saved_and_one_whose_reload_fails_stays_unconfirmed(tmp_path):
    save = saving(tmp_path)
    with pytest.raises(ConversationRefused) as known:
        save(Refusing(None))
    assert (known.value.code, known.value.committed, known.value.retryable, known.value.status) == (
        "not_saved", "not_committed", True, 409)
    with pytest.raises(ConversationRefused) as unknown:
        save(Refusing(OSError("unavailable")))
    assert (unknown.value.code, unknown.value.committed, unknown.value.retryable) == ("save_unconfirmed", "unconfirmed", True)
