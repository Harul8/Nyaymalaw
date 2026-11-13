"""A save that lost a race is 'not saved', and Continue saves it (plan AN.50, piece 50b; D188; the review's F-07).

The final save of an answer is refused as stale where the conversation moved under it - another write beside it landed first, as
the conversation's title once did. The refusal writes nothing, and a clean reload that does not hold the answer makes the
outcome known: not saved. It used to be said as 'could not be confirmed', and the message's attempt was then refused for ever.
Now the answer is kept and Continue saves it on the conversation as it then stands, with no model call. An outcome still
unknown - an OS error whose write may yet land, or a reload that fails - stays 'unconfirmed' (tests/test_core_served.py keeps
that case). Offline: the scripted model and a temporary store; the words are invented.
"""
import threading
import time
from dataclasses import replace

import pytest

from nm.core_engine import titles, turn
from nm.core_engine.conversation import (
    SHOWN, ConversationRefused, commit_turn, hold_shown, open_turn, sent, shown_of, title_of,
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


def late_title(served, monkeypatch, *, keeping_fails=False):
    """The review's trigger, reproduced: the conversation's title, still being written when the answer is ready, lands after
    the turn has stopped waiting for it and moves the conversation's version under the final save. keeping_fails: the store
    will not take the turn's record of why it stopped either. Returns the store's own save."""
    monkeypatch.setattr(turn, "TITLE_WAIT", 0.05)
    release, original_call, original_commit = threading.Event(), served.model.structured, served.store.commit

    def calling(prompt, schema, tier, **kwargs):
        if prompt.operation == titles.OPERATION:
            release.wait(30)  # the title is slow: it is written only once the final save has begun
        return original_call(prompt, schema, tier, **kwargs)

    def saving(matter, **kwargs):
        if matter.brain_chat and not release.is_set():
            release.set()
            deadline = time.monotonic() + 30
            while title_of(served.store.load(matter.id)) is None and time.monotonic() < deadline:
                time.sleep(0.01)
        if keeping_fails and ((matter.intake_answers or {}).get("core_shown") or {}).get("stopped"):
            raise OSError("Synthetic store that will not take the stop")
        return original_commit(matter, **kwargs)
    monkeypatch.setattr(served.model, "structured", calling)
    monkeypatch.setattr(served.store, "commit", saving)
    return original_commit


def test_a_save_refused_because_a_late_title_moved_the_conversation_is_not_saved_and_continue_saves_it_with_no_model_call(
        served, monkeypatch):
    original_commit = late_title(served, monkeypatch)
    reply = send(served)
    assert reply.status_code == 409, reply.text
    detail = reply.json()["detail"]
    assert (detail["code"], detail["committed"], detail["retryable"], detail.get("kept")) == (
        "not_saved", "not_committed", True, True)
    assert "elements" not in detail, "a refusal carries no answer"
    (matter,) = served.store.list_for(OWNER).matters
    held = shown_of(matter)
    assert matter.brain_chat == () and held["stopped"]["code"] == "not_saved" and held["steps"]["answered"]["sections"]
    assert title_of(matter) is not None, "the title that moved the conversation is kept"
    calls = len(served.model.calls)
    monkeypatch.setattr(served.store, "commit", original_commit)
    saved = successful(served)  # Continue: the same message sent again
    assert len(served.model.calls) == calls, "the kept answer is saved with no model call"
    assert not saved["replayed"] and saved["elements"] == held["elements"]
    (matter,) = served.store.list_for(OWNER).matters
    assert len(matter.brain_chat) == 1 and title_of(matter) is not None, "saved on the conversation as it now stands"
    assert successful(served)["replayed"], "and only once"


def test_an_answer_the_store_would_not_keep_is_not_said_to_be_kept(served, monkeypatch):
    """Plan AN.50 (50b3): 'kept' is said only where the turn's record of why it stopped was written."""
    original_commit = late_title(served, monkeypatch, keeping_fails=True)
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
