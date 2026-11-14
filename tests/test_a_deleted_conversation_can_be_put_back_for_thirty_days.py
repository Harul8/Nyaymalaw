"""A deleted conversation leaves the history at once, can be put back for thirty days, and is then erased (plan AN.53, D241's
second piece).

D241: Delete leaves the history at once; for 30 days the conversation can be put back, because for an advocate an accidental
deletion of a client's matter is the likelier harm than a late erasure; after 30 days it is erased - its own key first (the
store's one delete, 53h1). NM never deletes a conversation by itself: only one an advocate deleted is ever swept. While it is
deleted nothing reads it and nothing writes to it - a stale page's message must not bring it back, nor be erased with it.

Offline: a store in a temporary folder and a stand-in clock; no model call.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from nm.shared.store_file_store import PUT_BACK_DAYS, FileMatterStore
from nm.shared.store_port import StaleWrite
from nm.work_the_file.matter_contracts import Matter

pytestmark = pytest.mark.class_a

KEY = "put-back-control-" + "k" * 32
OWNER, OTHER = "owner@example.test", "other@example.test"
NOW = datetime(2026, 11, 14, 9, 0, tzinfo=timezone.utc)


def _store(root):
    return FileMatterStore(root, key=KEY)


def _saved(store, matter_id="m_one", advocate=OWNER):
    return store.commit(Matter(id=matter_id, advocate_id=advocate, title="Kept or not", version=1), expected_version=0)


def test_a_deleted_conversation_leaves_the_history_at_once_and_is_read_by_nothing(tmp_path):
    store = _store(tmp_path)
    _saved(store)
    _saved(store, "m_two")
    marked = store.mark_deleted("m_one", OWNER, NOW)
    assert marked == {"matter_id": "m_one", "deleted_at": NOW.isoformat(),
                      "erased_after": (NOW + timedelta(days=PUT_BACK_DAYS)).isoformat()}
    assert [entry[0] for entry in store.saved_files_for(OWNER)] == ["m_two"], "it leaves the history at once"
    assert [m.id for m in store.list_for(OWNER).matters] == ["m_two"]
    assert store.load_for("m_one", OWNER) is None and store.load("m_one") is None, "nothing reads it"
    assert (tmp_path / "matters" / "m_one.nm").exists(), "nothing of it is erased yet"


def test_nothing_writes_to_a_deleted_conversation_so_a_stale_page_cannot_bring_it_back(tmp_path):
    store = _store(tmp_path)
    saved = _saved(store)
    store.mark_deleted("m_one", OWNER, NOW)
    with pytest.raises(StaleWrite):
        store.commit(Matter(id="m_one", advocate_id=OWNER, title="A stale page's save", version=2),
                     expected_version=saved.version)
    with pytest.raises(StaleWrite):
        store.commit(Matter(id="m_one", advocate_id=OWNER, title="A new one under its name", version=1), expected_version=0)
    store.put_back("m_one", OWNER)
    assert store.load("m_one").title == "Kept or not", "and what was put back is what was deleted"


def test_its_advocate_sees_what_can_be_put_back_and_until_when_and_puts_it_back(tmp_path):
    store = _store(tmp_path)
    _saved(store)
    store.mark_deleted("m_one", OWNER, NOW)
    assert store.deleted_for(OWNER) == ({"matter_id": "m_one", "deleted_at": NOW.isoformat(),
                                         "erased_after": (NOW + timedelta(days=PUT_BACK_DAYS)).isoformat()},)
    assert store.deleted_for(OTHER) == ()
    assert store.put_back("m_one", OWNER) is True
    assert store.deleted_for(OWNER) == () and [e[0] for e in store.saved_files_for(OWNER)] == ["m_one"]
    assert store.load_for("m_one", OWNER).title == "Kept or not"


def test_only_its_own_advocate_deletes_or_puts_back_a_conversation(tmp_path):
    store = _store(tmp_path)
    _saved(store)
    assert store.mark_deleted("m_one", OTHER, NOW) is None
    assert store.load("m_one") is not None, "another's conversation is not there for them"
    store.mark_deleted("m_one", OWNER, NOW)
    assert store.put_back("m_one", OTHER) is False and store.load("m_one") is None


def test_the_sweep_erases_only_what_was_deleted_more_than_thirty_days_ago(tmp_path):
    store = _store(tmp_path)
    for name in ("m_old", "m_recent", "m_kept"):
        _saved(store, name)
    store.mark_deleted("m_old", OWNER, NOW)
    store.mark_deleted("m_recent", OWNER, NOW + timedelta(days=20))
    later = NOW + timedelta(days=PUT_BACK_DAYS, minutes=1)
    assert store.sweep_deleted(later) == ("m_old",)
    assert not (tmp_path / "matters" / "m_old.nm").exists() and not (tmp_path / "keys" / "m_old.key").exists()
    assert store.deleted_for(OWNER) == ({"matter_id": "m_recent", "deleted_at": (NOW + timedelta(days=20)).isoformat(),
                                         "erased_after": (NOW + timedelta(days=20 + PUT_BACK_DAYS)).isoformat()},)
    assert [entry[0] for entry in store.saved_files_for(OWNER)] == ["m_kept"], "nothing it was not asked to delete is touched"
    assert store.sweep_deleted(later) == (), "a second sweep finds nothing more"


def test_the_sweep_never_erases_a_conversation_nobody_deleted_however_old(tmp_path):
    store = _store(tmp_path)
    _saved(store)
    assert store.sweep_deleted(NOW + timedelta(days=3650)) == ()
    assert store.load("m_one") is not None


def test_deleting_twice_keeps_the_first_date_and_a_mark_that_cannot_be_read_is_not_swept(tmp_path):
    store = _store(tmp_path)
    _saved(store)
    store.mark_deleted("m_one", OWNER, NOW)
    again = store.mark_deleted("m_one", OWNER, NOW + timedelta(days=10))
    assert again["deleted_at"] == NOW.isoformat(), "the thirty days run from the first deletion"
    (tmp_path / "deleted" / "m_one.json").write_text("{not a mark", encoding="utf8")
    assert store.sweep_deleted(NOW + timedelta(days=400)) == (), "never erased on a mark that cannot be read"
    assert (tmp_path / "matters" / "m_one.nm").exists()


def test_the_port_declares_the_mark_put_back_and_sweep():
    from nm.shared.policed_port_adapter import port_methods
    from nm.shared.store_port import StorePort
    assert {"mark_deleted", "put_back", "deleted_for", "sweep_deleted"} <= port_methods(StorePort)


# --------------------------------------------------------------------------------- who sweeps, and when ---

def test_the_serving_process_sweeps_at_once_and_again_and_a_store_that_fails_is_said_and_tried_again(capsys):
    import threading
    from types import SimpleNamespace

    from nm.app import main
    swept, again = [], threading.Event()

    def sweep_deleted(now, look=None):
        swept.append(now)
        if len(swept) == 1:
            raise OSError("the store's folder refuses")
        again.set()
        if len(swept) > 2:
            threading.Event().wait()  # holds this test's sweeping thread: it must not sweep on for the rest of the session
        return ("m_old",)
    main._keep_deleted(SimpleNamespace(store=SimpleNamespace(sweep_deleted=sweep_deleted), documents=None,
                                       directory=SimpleNamespace(sweep_expired=lambda now: {"registrations": 0, "resets": 0}),
            turn_record_sweep=SimpleNamespace(sweep=lambda before: 0)),
                       every=0.05)
    assert again.wait(5), "a failed sweep is tried again"
    assert swept[0].utcoffset() is not None, "the sweep is asked with an aware moment"
    said = capsys.readouterr().err
    assert "could not be swept (OSError)" in said and "1 conversation(s)" in said


def test_only_the_serving_process_sweeps_never_the_step_worker():
    import inspect

    from nm.app import main, step_worker
    assert "_keep_deleted(application)" in inspect.getsource(main.main)
    assert "sweep_deleted" not in inspect.getsource(step_worker) and "_keep_deleted" not in inspect.getsource(step_worker)
