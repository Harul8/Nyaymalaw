"""The conversation history is served a page at a time, from lines kept beside the saved files (plan AN.23; owner
decisions P35, O29).

Whose a saved file is, and what the history shows of it, is known only by opening it; a long conversation is tens of
megabytes. The route now reads the small line kept for each file, derives one from the file only when none is kept for
the file as it is now, and serves the advocate's history ten at a time, conversations first and then the earlier matter
records, each newest first. Through the real HTTP edge with the served fixture.
"""
from __future__ import annotations

import logging
import os

import pytest

from nm.app import api
from nm.core_engine.conversation import HEADER, chat_matter_id
from nm.work_the_file.matter_contracts import Matter
from tests.test_core_served import OTHER, OWNER, served, source_url, successful  # noqa: F401 -- the fixture

pytestmark = pytest.mark.class_a


def old_matters(served, who, count, *, first=0):
    """Earlier matter records for this advocate, each saved a minute after the one before, oldest first."""
    ids = []
    for index in range(first, first + count):
        matter = Matter.create(who, f"Earlier matter {index:02d}")
        served.store.commit(matter, expected_version=0)
        stamp = 1_700_000_000 + index * 60
        os.utime(served.store._path(matter.id), (stamp, stamp))
        ids.append(matter.id)
    return ids


def a_chat(served, turn="turn-1", **changes):
    return successful(served, turn_id=turn, **changes)


def listed(page):
    """What a page shows, in the order shown: chat ids, then matter ids."""
    return [chat["chat_id"] for chat in page["chats"]] + [matter["matter_id"] for matter in page["matters"]]


def watched(served, monkeypatch):
    """Every file the store is asked to open from now on."""
    opened = []
    real = served.store.load

    def load(matter_id):
        opened.append(matter_id)
        return real(matter_id)

    monkeypatch.setattr(served.store, "load", load)
    return opened


def the_lines(served):
    folder = served.store._lines
    return sorted(p.stem for p in folder.glob("*.nm")) if folder.exists() else []


# ------------------------------------------------------------------ the pages ---

def test_without_a_limit_the_whole_history_is_served_as_before(served):
    chat = a_chat(served)
    old = old_matters(served, OWNER, 3)
    work = served.client.get("/api/work").json()
    assert work["state"] == "ok"
    assert [c["chat_id"] for c in work["chats"]] == [chat["chat_id"]]
    assert [m["matter_id"] for m in work["matters"]] == old[::-1], "earlier matter records, newest first"
    assert (work["chat_count"], work["row_count"], work["total"]) == (1, 3, 4)
    assert (work["offset"], work["has_more"], work["next_offset"]) == (0, False, None)


def test_a_page_is_ten_items_conversations_first_then_earlier_matters_each_newest_first(served):
    chat = a_chat(served)
    old = old_matters(served, OWNER, 12)
    first = served.client.get("/api/work?limit=10&offset=0").json()
    assert [c["chat_id"] for c in first["chats"]] == [chat["chat_id"]]
    assert [m["matter_id"] for m in first["matters"]] == old[::-1][:9]
    assert (first["has_more"], first["next_offset"], first["offset"]) == (True, 10, 0)
    second = served.client.get("/api/work?limit=10&offset=10").json()
    assert second["chats"] == [] and [m["matter_id"] for m in second["matters"]] == old[::-1][9:]
    assert (second["has_more"], second["next_offset"], second["offset"]) == (False, None, 10)
    stamps = [m["last_updated"] for m in first["matters"] + second["matters"]]
    assert stamps == sorted(stamps, reverse=True)


def test_the_counts_are_of_the_whole_history_on_every_page(served):
    a_chat(served)
    old_matters(served, OWNER, 12)
    for offset in (0, 10, 40):
        page = served.client.get(f"/api/work?limit=10&offset={offset}").json()
        assert (page["chat_count"], page["row_count"], page["total"]) == (1, 12, 13), offset


def test_walking_the_pages_shows_every_item_once_and_in_the_order_of_the_whole_list(served):
    a_chat(served)
    a_chat(served, turn="turn-2", chat_id=None, message="A second conversation.")
    old_matters(served, OWNER, 9)
    whole = listed(served.client.get("/api/work").json())
    walked, offset = [], 0
    while offset is not None:
        page = served.client.get(f"/api/work?limit=4&offset={offset}").json()
        walked += listed(page)
        offset = page["next_offset"]
    assert walked == whole and len(set(walked)) == len(walked) == 11


def test_a_page_past_the_end_is_empty_and_says_nothing_more_follows(served):
    old_matters(served, OWNER, 3)
    for offset in (3, 4, 500):
        page = served.client.get(f"/api/work?limit=10&offset={offset}").json()
        assert listed(page) == [] and (page["has_more"], page["next_offset"], page["total"]) == (False, None, 3)


def test_an_empty_history_is_an_empty_page_not_an_error(served):
    page = served.client.get("/api/work?limit=10").json()
    assert page["state"] == "ok" and listed(page) == [] and page["total"] == 0 and page["has_more"] is False


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "limit=-1", "limit=abc", "limit=10&offset=-1",
                                   "limit=10&offset=abc"])
def test_a_page_that_cannot_be_meant_is_refused_without_echoing_it(served, query):
    response = served.client.get(f"/api/work?{query}")
    assert response.status_code == 422
    assert "abc" not in response.text


def test_the_largest_page_is_a_hundred(served):
    old_matters(served, OWNER, 3)
    assert served.client.get("/api/work?limit=100").status_code == 200


def test_the_chats_route_pages_the_same_way(served):
    old = old_matters(served, OWNER, 5)
    page = served.client.get("/api/chats?limit=2&offset=1").json()
    assert [m["matter_id"] for m in page["matters"]] == old[::-1][1:3]
    assert (page["has_more"], page["next_offset"], page["total"]) == (True, 3, 5)


def test_another_advocates_items_are_never_counted_or_shown(served):
    mine = old_matters(served, OWNER, 4)
    theirs = old_matters(served, OTHER, 6, first=50)
    a_chat(served)
    page = served.client.get("/api/work?limit=10").json()
    assert set(listed(page)).isdisjoint(theirs) and page["row_count"] == 4 and page["total"] == 5
    other = served.login(OTHER).get("/api/work?limit=3").json()
    assert set(listed(other)) == set(theirs[::-1][:3]) and other["row_count"] == 6 and other["chat_count"] == 0
    assert set(mine).isdisjoint(listed(other))


def test_a_page_asked_for_by_no_one_is_refused(served):
    from fastapi.testclient import TestClient
    with TestClient(api.app) as anonymous:
        assert anonymous.get("/api/work?limit=10").status_code == 401
        assert anonymous.get("/api/chats?limit=10&offset=10").status_code == 401


def test_a_session_revoked_while_the_page_is_read_gets_nothing(served, monkeypatch):
    old_matters(served, OWNER, 3)
    token = served.client.cookies.get("nm_session")
    real = served.store.saved_files

    def revoke():
        result = real()
        served.directory.close_session(token, "Synthetic read revocation")
        return result

    monkeypatch.setattr(served.store, "saved_files", revoke)
    response = served.client.get("/api/work?limit=10")
    assert response.status_code == 401 and "Earlier matter" not in response.text


# ------------------------------------------------------------ the kept lines ---

def test_the_first_call_keeps_a_line_for_each_readable_file_and_a_later_start_opens_none_of_them(served, monkeypatch):
    chat = a_chat(served)
    old = old_matters(served, OWNER, 4)
    served.client.get("/api/work?limit=10")
    chat_file = chat_matter_id(OWNER, chat["chat_id"])
    assert the_lines(served) == sorted([chat_file, *old])
    # A new process: nothing kept in memory, and no file may be opened for the history.
    api._LISTED.clear()
    opened = watched(served, monkeypatch)
    page = served.client.get("/api/work?limit=10").json()
    assert opened == [], "a kept line is read instead of its file"
    assert listed(page) == [chat["chat_id"], *old[::-1]]
    assert page["chats"][0]["turn_count"] == 1 and page["chats"][0]["preview"] == "Inspect this reported account."


def test_a_file_that_changed_is_derived_again_and_never_served_from_its_old_line(served, monkeypatch):
    from dataclasses import replace
    (mid,) = old_matters(served, OWNER, 1)
    assert served.client.get("/api/work").json()["matters"][0]["matter"] == "Earlier matter 00"
    matter = served.store.load(mid)
    served.store.commit(replace(matter, title="Earlier matter, retitled"), expected_version=matter.version)
    api._LISTED.clear()
    opened = watched(served, monkeypatch)
    page = served.client.get("/api/work").json()
    assert page["matters"][0]["matter"] == "Earlier matter, retitled" and opened == [mid]
    assert served.store.kept_line(mid, served.store.signature(mid))["matter"]["matter"] == "Earlier matter, retitled"
    opened.clear()
    api._LISTED.clear()
    served.client.get("/api/work")
    assert opened == [], "the new line is kept in its turn"


def test_a_line_kept_under_another_contract_is_derived_again_and_replaced(served, monkeypatch):
    chat = a_chat(served)
    mid = chat_matter_id(OWNER, chat["chat_id"])
    served.client.get("/api/work")
    signature = served.store.signature(mid)
    stale = {**served.store.kept_line(mid, signature), "v": "history-line-0/an_older_contract"}
    served.store.keep_line(mid, signature, stale)
    api._LISTED.clear()
    opened = watched(served, monkeypatch)
    served.client.get("/api/work")
    assert opened == [mid]
    assert served.store.kept_line(mid, signature)["v"] == api._LINE_VERSION


@pytest.mark.parametrize("damage", [
    {"owner": None}, {"owner": 7}, {"owner": None, "chat": {"chat_id": "c", "preview": "p", "turn_count": 1}},
    {"owner": OWNER, "chat": "text"}, {"owner": OWNER, "chat": None}, {"owner": OWNER, "unavailable": True},
    {"owner": OWNER}])
def test_a_kept_line_that_is_not_what_a_line_should_be_is_derived_again_not_trusted(served, monkeypatch, damage):
    (mid,) = old_matters(served, OWNER, 1)
    signature = served.store.signature(mid)
    served.store.keep_line(mid, signature, {"v": api._LINE_VERSION, **damage})
    opened = watched(served, monkeypatch)
    page = served.client.get("/api/work").json()
    assert opened == [mid] and [m["matter"] for m in page["matters"]] == ["Earlier matter 00"]
    assert served.store.kept_line(mid, signature)["matter"]["matter"] == "Earlier matter 00"


def test_a_file_that_cannot_be_read_is_said_and_no_line_is_kept_for_it(served):
    old = old_matters(served, OWNER, 2)
    (served.store._path(old[0])).write_bytes(b"damaged")
    page = served.client.get("/api/work?limit=10").json()
    assert page["state"] == "partial" and old[0] in page["unavailable"] and old[0] in page["unreadable"]
    assert listed(page) == [old[1]]
    assert the_lines(served) == [old[1]]


def test_a_conversation_whose_receipts_fail_is_said_and_no_line_is_kept_for_it(served):
    from dataclasses import replace
    chat = a_chat(served)
    mid = chat_matter_id(OWNER, chat["chat_id"])
    matter = served.store.load(mid)
    rows = (dict(matter.brain_chat[0], message="A message that no longer matches its receipt"),)
    served.store.commit(replace(matter, brain_chat=rows, version=matter.version + 1), expected_version=matter.version)
    page = served.client.get("/api/work").json()
    assert page["state"] == "partial" and mid in page["unavailable"] and page["chats"] == []
    # The line kept for the answer, before the record was tampered with, is for another version of the file.
    assert served.store.kept_line(mid, served.store.signature(mid)) is None


def test_a_line_that_could_not_be_kept_does_not_fail_the_request_and_is_logged_without_words(served, monkeypatch, caplog):
    old = old_matters(served, OWNER, 2)

    def refuse(*_args):
        raise PermissionError("the folder is read-only; the first message was Privileged words")

    monkeypatch.setattr(served.store, "keep_line", refuse)
    with caplog.at_level(logging.WARNING, logger="nm.history"):
        page = served.client.get("/api/work?limit=10")
    assert page.status_code == 200 and listed(page.json()) == old[::-1]
    assert "PermissionError" in caplog.text and "Privileged" not in caplog.text and "read-only" not in caplog.text


def test_a_second_call_in_the_same_process_reads_neither_lines_nor_files(served, monkeypatch):
    old_matters(served, OWNER, 3)
    served.client.get("/api/work?limit=10")
    opened = watched(served, monkeypatch)
    real = served.store.kept_line
    asked = []
    monkeypatch.setattr(served.store, "kept_line", lambda *a: asked.append(a) or real(*a))
    served.client.get("/api/work?limit=10&offset=0")
    served.client.get("/api/work?limit=10&offset=10")
    assert opened == [] and asked == []


# ------------------------------------------------- prepared ahead of the asking ---

def test_an_answer_prepares_its_conversations_line_once_it_has_gone(served, monkeypatch):
    chat = a_chat(served)
    mid = chat_matter_id(OWNER, chat["chat_id"])
    assert the_lines(served) == [mid], "no history call has been made: the answer's own aftermath kept the line"
    second = a_chat(served, turn="turn-2", chat_id=chat["chat_id"], message="And a second message.")
    assert served.store.kept_line(mid, served.store.signature(mid))["chat"]["turn_count"] == 2
    api._LISTED.clear()
    opened = watched(served, monkeypatch)
    page = served.client.get("/api/work?limit=10").json()
    assert opened == [] and page["chats"][0]["turn_count"] == 2
    assert second["replayed"] is False


def test_a_replayed_answer_derives_no_line_again(served, monkeypatch):
    a_chat(served)
    derived = []
    real = api._derived_line
    monkeypatch.setattr(api, "_derived_line", lambda store, matter_id: derived.append(matter_id) or real(store, matter_id))
    again = successful(served, turn_id="turn-1", expected_version=0)
    assert again["replayed"] is True and derived == []


def test_an_answer_that_names_no_conversation_prepares_nothing(served, monkeypatch):
    real = served.app.run_turn
    monkeypatch.setattr(served.app, "run_turn", lambda **kwargs: {**real(**kwargs), "chat_id": None})
    derived = []
    real_derive = api._derived_line
    monkeypatch.setattr(api, "_derived_line", lambda store, matter_id: derived.append(matter_id) or real_derive(store, matter_id))
    assert successful(served)["chat_id"] is None
    assert derived == [] and the_lines(served) == []


def test_preparing_the_line_never_fails_the_answer(served, monkeypatch):
    def refuse(*_args):
        raise PermissionError("no")

    monkeypatch.setattr(served.store, "keep_line", refuse)
    reply = a_chat(served)
    assert reply["committed"] == "committed"


def test_preparing_the_history_keeps_every_readable_line_so_the_first_call_opens_nothing(served, monkeypatch):
    chat = a_chat(served)
    old = old_matters(served, OWNER, 3)
    (served.store._path(old[0])).write_bytes(b"damaged")
    for line in served.store._lines.glob("*.nm"):
        line.unlink()
    api._LISTED.clear()
    api.prepare_history()
    assert the_lines(served) == sorted([chat_matter_id(OWNER, chat["chat_id"]), old[1], old[2]])
    api._LISTED.clear()
    opened = watched(served, monkeypatch)
    assert api.prepare_history() is None
    assert opened == [old[0]], "only the file that cannot be read is opened again, and it is said again"


def test_preparing_the_history_is_newest_first_and_survives_what_goes_wrong(served, monkeypatch, caplog):
    old = old_matters(served, OWNER, 3)
    order = []
    real = api._listed

    def spy(store, matter_id, signature):
        order.append(matter_id)
        if matter_id == old[1]:
            raise RuntimeError("a fault inside a file's line, with Privileged words")
        return real(store, matter_id, signature)

    monkeypatch.setattr(api, "_listed", spy)
    with caplog.at_level(logging.WARNING, logger="nm.history"):
        api.prepare_history()
    assert order == old[::-1], "newest first"
    assert "RuntimeError" in caplog.text and "Privileged" not in caplog.text
    assert the_lines(served) == sorted([old[0], old[2]])


def test_a_history_that_cannot_even_be_listed_is_logged_and_prepares_nothing(served, monkeypatch, caplog):
    def refuse():
        raise OSError("the store is not there; Privileged words")

    monkeypatch.setattr(served.store, "saved_files", refuse)
    with caplog.at_level(logging.WARNING, logger="nm.history"):
        assert api.prepare_history() is None
    assert "OSError" in caplog.text and "Privileged" not in caplog.text


def test_a_file_that_changes_while_its_line_is_derived_gets_no_line_kept_for_the_version_that_was_read(served, monkeypatch):
    """The line is for the file as it was when it was opened; if the file moved on meanwhile, it is not kept - in this
    process or beside the file - and the next call derives the line afresh."""
    from dataclasses import replace
    (mid,) = old_matters(served, OWNER, 1)
    before = served.store.signature(mid)
    real = served.store.load

    changing = []

    def load_then_change(matter_id):
        matter = real(matter_id)
        if not changing:  # the commit reads the file too, which must not change it again
            changing.append(matter_id)
            served.store.commit(replace(matter, title="Changed while it was being listed"),
                                expected_version=matter.version)
        return matter

    monkeypatch.setattr(served.store, "load", load_then_change)
    page = served.client.get("/api/work").json()
    assert page["matters"][0]["matter"] == "Earlier matter 00", "what was read is what is shown for this call"
    assert served.store.kept_line(mid, before) is None and mid not in api._LISTED
    monkeypatch.setattr(served.store, "load", real)
    assert served.client.get("/api/work").json()["matters"][0]["matter"] == "Changed while it was being listed"
