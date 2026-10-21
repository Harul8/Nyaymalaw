"""Reopening a saved conversation is near-instant (owner request P35, 21 Oct 2026).

One turn of live run 8 took half a minute to replay, and every read of its conversation -
the history, reopening it, its board, its files, a source in the reading pane - replayed it
again; inside the replay each check re-derived the same evidence for itself. Now what a
replay's checks share is derived once; a saved turn, by its chained digest, is replayed once by
a process; a conversation read and checked is read again only when its saved file changes; and
the history checks the receipts of what it lists, leaving the replay to the opening. Scripted
models prove the counting, not the speed; on live run 8's own saved turn the first replay went
from about 29 s to about 8 s, and a repeat read needs only the file's stamp.
"""
import contextlib

import pytest

from nm.core_engine import replay_scope, research, response_authorities, turn
from nm.core_engine.conversation import ConversationRefused, chat_matter_id
from tests.test_core_answer_sections import Scripted, through_turns
from tests.test_core_turn import run, store  # noqa: F401 - pytest fixture

pytestmark = pytest.mark.class_a


def counted(monkeypatch, module, name):
    calls, original = [], getattr(module, name)

    def counting(*args, **kwargs):
        calls.append(name)
        return original(*args, **kwargs)
    monkeypatch.setattr(module, name, counting)
    return calls


def saved(store):
    response = run(store, through_turns(Scripted()))
    return response, (lambda: store.load(chat_matter_id("owner", response["chat_id"])))


def test_what_the_checks_of_a_turn_answered_dispute_by_dispute_share_is_derived_once_in_its_replay(
        store, monkeypatch):
    response, matter = saved(store)
    validated = counted(monkeypatch, research, "_validate")
    authorities = counted(monkeypatch, response_authorities, "_validate")
    rows = turn.saved_rows(matter(), "owner")
    assert rows[0]["response"]["elements"] == response["elements"]
    # The whole answer's research and each dispute's part, each validated once; each piece's
    # authority evidence bound once, though its section and its review both bind it.
    assert (len(validated), len(authorities)) == (3, 3)
    validated.clear()
    authorities.clear()
    turn._REPLAYED.clear()
    monkeypatch.setattr(replay_scope, "replaying", contextlib.nullcontext)
    turn.saved_rows(matter(), "owner")
    # Every check deriving its own, as live run 8's replay did.
    assert (len(validated), len(authorities)) == (18, 6)


def test_a_turn_replayed_once_is_not_replayed_again_while_its_receipts_are_checked_on_every_read(store, monkeypatch):
    _, matter = saved(store)
    turn.saved_rows(matter(), "owner")
    replayed = counted(monkeypatch, turn, "validate_activity")
    assert turn.saved_rows(matter(), "owner") and replayed == []
    changed = matter()
    changed.brain_chat[0]["response"]["elements"][0]["text"] += " Changed on disk."
    with pytest.raises(ConversationRefused, match="could not be read reliably"):
        turn.saved_rows(changed, "owner")


def test_a_turn_whose_replay_failed_is_replayed_again_on_the_next_read(store, monkeypatch):
    _, matter = saved(store)
    original = turn.validate_activity

    def failing(*args):
        raise ValueError("Saved response differs from its admitted rendering")
    monkeypatch.setattr(turn, "validate_activity", failing)
    with pytest.raises(ConversationRefused):
        turn.saved_rows(matter(), "owner")
    assert turn._REPLAYED == set()
    monkeypatch.setattr(turn, "validate_activity", original)
    assert turn.saved_rows(matter(), "owner")


# --- the history, reopening and the reading pane, served (P35) ---------------------------

from tests.test_core_served import served, successful  # noqa: E402,F401 - pytest fixture


def test_the_history_lists_conversations_from_their_receipts_and_reopens_nothing_unchanged(served, monkeypatch):
    reply = successful(served)
    replayed = counted(monkeypatch, turn, "validate_activity")
    loaded = counted(monkeypatch, served.store, "load")
    work = served.client.get("/api/work").json()
    assert [chat["chat_id"] for chat in work["chats"]] == [reply["chat_id"]] and replayed == []
    assert loaded == ["load"]
    loaded.clear()
    assert served.client.get("/api/work").json() == work and loaded == []  # no file changed


def test_a_conversation_is_read_again_only_when_its_saved_file_changed(served, monkeypatch):
    first = successful(served)
    loaded = counted(monkeypatch, served.store, "load")
    url = f"/api/chats/{first['chat_id']}"
    opened = served.client.get(url).json()
    assert len(loaded) == 1
    # Its board, a source in the reading pane and reopening it read nothing again.
    for again in (f"{url}/board", f"/api/chats/{first['chat_id']}/turns/{first['turn_id']}/brain-sources/0/0", url):
        assert served.client.get(again).status_code == 200
    assert len(loaded) == 1 and served.client.get(url).json() == opened
    successful(served, turn_id="turn-2", chat_id=first["chat_id"], message="Hello again.")
    loaded.clear()
    assert [saved["turn_id"] for saved in served.client.get(url).json()["turns"]] == ["turn-1", "turn-2"]
    assert loaded  # the saved file changed, so it was read again
