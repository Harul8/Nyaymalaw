"""Actual saved and served deadline read integrity; no external models or algorithms."""
from __future__ import annotations

import copy
from datetime import date

import pytest

from nm.adapters.store.file_store import FileMatterStore
from nm.core.deadlines import read_matter
from nm.domain.matter import Matter, Thread
from nm.edge.api import application
from tests.test_turn_contract import KEY

pytestmark = pytest.mark.class_a
TODAY = date(2026, 9, 12)
KNOWN = {"thread": "thr_window", "kind": "listed_hearing", "source": "Supplied listing",
         "action": "Attend the listed hearing", "owner": "Named advocate",
         "consequence": "The supplied listing would be missed", "on": "2026-09-17"}


def _seed(client, monkeypatch, threads):
    actor = client.get("/api/session").json()["advocate"]["id"]
    monkeypatch.setattr("nm.edge.projections.forum_today", lambda: TODAY)

    def forbidden(*args, **kwargs):
        raise AssertionError("saved deadline readback reached model-backed routing")

    monkeypatch.setattr(application().engine, "_read_route", forbidden)
    matter = Matter(id="mat_read_deadlines", advocate_id=actor, title="Saved deadline review",
                    threads=tuple(threads), version=1)
    application().store.commit(matter, expected_version=0)
    return matter


def _views(client, matter):
    listed = client.get("/api/matters")
    boarded = client.get(f"/api/matters/{matter.id}")
    covered = client.get(f"/api/matters/{matter.id}/cover")
    assert listed.status_code == boarded.status_code == covered.status_code == 200
    selected = [row for row in listed.json()["matters"] if row["matter_id"] == matter.id]
    assert len(selected) == 1 and boarded.json()["row_count"] == len(matter.threads)
    return selected[0], boarded.json(), covered.json()["case_deadlines"]


@pytest.mark.parametrize("assessed", [False, True])
def test_default_empty_is_not_the_same_as_a_recorded_empty_assessment(
    client, monkeypatch, assessed,
):
    thread = Thread(id="thr_window", label="Deadline instruction",
                    assessed=("deadlines",) if assessed else ())
    matter = _seed(client, monkeypatch, (thread,))
    listed, board, cover = _views(client, matter)
    assert len(board["threads"]) == 1
    for view in (listed, board["threads"][0], cover):
        assert view["deadline_assessment"] == ("assessed" if assessed else "not_assessed")
        assert view["next_deadline"] is None and view["deadline_unreadable"] == []
        assert view["deadline_unassessed"] == ([] if assessed else [thread.id])
        if assessed:
            assert view["next_deadline_status"] in {"none_on_this_matter", "none_on_this_thread"}
            assert view["passed_deadlines"] == []
        else:
            assert view["next_deadline_status"] == "not_assessed"
            assert view["passed_deadlines"] is None


def test_no_threads_is_not_an_assessed_empty_population(client, monkeypatch):
    matter = _seed(client, monkeypatch, ())
    listed, board, cover = _views(client, matter)
    assert board["threads"] == [] and board["row_count"] == 0
    for view in (listed, cover):
        assert view["deadline_assessment"] == "not_assessed"
        assert view["next_deadline_status"] == "not_assessed"


def test_legacy_dated_rows_are_kept_without_inventing_full_assessment(client, monkeypatch):
    thread = Thread(id="thr_window", label="Legacy saved listing", deadlines=(dict(KNOWN),))
    matter = _seed(client, monkeypatch, (thread,))
    listed, board, cover = _views(client, matter)
    for view in (listed, board["threads"][0], cover):
        assert view["next_deadline"] == KNOWN["on"] and view["next_deadline_status"] == "near"
        assert view["deadline_assessment"] == "incomplete"
        assert view["deadline_unassessed"] == [thread.id] and view["deadline_unreadable"] == []


@pytest.mark.parametrize("mutation", [
    "null_row", "list_row", "string_row", "missing_date", "bool_date", "numeric_date",
    "datetime_date", "unknown_kind", "null_source", "numeric_owner", "blank_action",
    "wrong_thread", "stored_status",
])
def test_every_malformed_saved_row_is_counted_beside_the_valid_window(
    client, monkeypatch, mutation,
):
    damaged = copy.deepcopy(KNOWN)
    if mutation == "null_row":
        damaged = None
    elif mutation == "list_row":
        damaged = []
    elif mutation == "string_row":
        damaged = "not a saved obligation"
    elif mutation == "missing_date":
        damaged.pop("on")
    elif mutation == "bool_date":
        damaged["on"] = False
    elif mutation == "numeric_date":
        damaged["on"] = 0
    elif mutation == "datetime_date":
        damaged["on"] = "2026-09-17T12:00:00+00:00"
    elif mutation == "unknown_kind":
        damaged["kind"] = "invented_kind"
    elif mutation == "null_source":
        damaged["source"] = None
    elif mutation == "numeric_owner":
        damaged["owner"] = 99
    elif mutation == "blank_action":
        damaged["action"] = "  "
    elif mutation == "wrong_thread":
        damaged["thread"] = "another_thread"
    elif mutation == "stored_status":
        damaged["status"] = "future"
    assert damaged != KNOWN, "the probe must alter the populated obligation"
    thread = Thread(id="thr_window", label="Mixed deadline read", assessed=("deadlines",),
                    deadlines=(dict(KNOWN), damaged))
    matter = _seed(client, monkeypatch, (thread,))
    store = application().store
    original = store._path(matter.id).read_bytes()
    decoded = store.load(matter.id)
    assert len(decoded.threads[0].deadlines) == 2, "inspect the actual persisted population"
    register = read_matter(decoded)
    assert len(register.rows) == len(register.unreadable) == 1
    assert register.unreadable[0].thread == thread.id and register.unreadable[0].index == 1
    listed, board, cover = _views(client, matter)
    for view in (listed, board["threads"][0], cover):
        assert view["next_deadline"] == KNOWN["on"] and view["next_deadline_status"] == "near"
        assert view["deadline_assessment"] == "incomplete"
        assert len(view["deadline_unreadable"]) == 1
        assert view["deadline_unassessed"] == []
    assert store._path(matter.id).read_bytes() == original, "readback must not repair by rewriting"


@pytest.mark.parametrize("saved", [(None,), None], ids=["only_bad_row", "bad_collection"])
def test_no_usable_rows_cannot_hide_a_malformed_saved_population(client, monkeypatch, saved):
    thread = Thread(id="thr_window", label="Unreadable register", assessed=("deadlines",),
                    deadlines=saved)
    matter = _seed(client, monkeypatch, (thread,))
    decoded = application().store.load(matter.id)
    assert decoded.threads[0].deadlines == saved
    register = read_matter(decoded)
    assert register.rows == () and len(register.unreadable) == 1
    listed, board, cover = _views(client, matter)
    for view in (listed, board["threads"][0], cover):
        assert view["next_deadline"] is None
        assert view["next_deadline_status"] == "not_assessed"
        assert view["deadline_assessment"] == "incomplete"
        assert len(view["deadline_unreadable"]) == 1
        assert view["passed_deadlines"] is None


def test_assessed_empty_does_not_clear_another_unassessed_thread(client, monkeypatch):
    assessed = Thread(id="thr_window", label="Actually assessed", assessed=("deadlines",))
    unknown = Thread(id="thr_unknown", label="Not yet assessed")
    matter = _seed(client, monkeypatch, (assessed, unknown))
    listed, board, cover = _views(client, matter)
    for view in (listed, cover):
        assert view["next_deadline"] is None
        assert view["next_deadline_status"] == "not_assessed"
        assert view["deadline_assessment"] == "incomplete"
        assert view["deadline_unassessed"] == [unknown.id]
        assert view["deadline_unreadable"] == []
    by_id = {row["thread_id"]: row for row in board["threads"]}
    assert by_id[assessed.id]["next_deadline_status"] == "none_on_this_thread"
    assert by_id[assessed.id]["deadline_assessment"] == "assessed"
    assert by_id[unknown.id]["next_deadline_status"] == "not_assessed"
    assert by_id[unknown.id]["deadline_assessment"] == "not_assessed"


def test_assessed_and_unassessed_threads_remain_distinct_after_restart(client, monkeypatch):
    assessed = Thread(id="thr_window", label="Known listing", assessed=("deadlines",),
                      deadlines=(dict(KNOWN),))
    unknown = Thread(id="thr_unknown", label="Not yet assessed")
    matter = _seed(client, monkeypatch, (assessed, unknown))
    before = _views(client, matter)
    old_store = application().store
    reopened = FileMatterStore(old_store._root, key=KEY)
    monkeypatch.setattr(application(), "store", reopened)
    after = _views(client, matter)
    assert after == before
    listed, board, cover = after
    for view in (listed, cover):
        assert view["next_deadline"] == KNOWN["on"]
        assert view["deadline_assessment"] == "incomplete"
        assert view["deadline_unassessed"] == [unknown.id]
    by_id = {row["thread_id"]: row for row in board["threads"]}
    assert by_id[assessed.id]["deadline_assessment"] == "assessed"
    assert by_id[unknown.id]["deadline_assessment"] == "not_assessed"
    assert reopened.load(matter.id).threads[0].assessed == ("deadlines",)


@pytest.mark.parametrize("on,status", [("2026-09-11", "passed"), (None, "not_computed")])
def test_passed_and_uncomputed_obligations_do_not_become_no_deadlines(
    client, monkeypatch, on, status,
):
    row = {**KNOWN, "on": on}
    thread = Thread(id="thr_window", label="No upcoming window", assessed=("deadlines",),
                    deadlines=(row,))
    matter = _seed(client, monkeypatch, (thread,))
    listed, board, cover = _views(client, matter)
    for view in (listed, board["threads"][0], cover):
        assert view["deadline_assessment"] == "assessed"
        assert view["next_deadline"] is None and view["next_deadline_status"] == status
        kept = view["passed_deadlines"] if status == "passed" else view["uncomputed_deadlines"]
        assert len(kept) == 1 and kept[0]["on"] == on
