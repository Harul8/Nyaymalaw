"""The sweep erases each conversation deleted thirty days ago or more and then its papers, unless another conversation of its
advocate's still names them (plan AN.53, D244's sixth piece: the sweep).

D241: after thirty days a deleted conversation is erased, its own key first; D244: its papers go after it - each one that no
other conversation of its advocate's names, in use or deleted and not yet erased - from that advocate's own space. The sweep
erased conversations and left their papers. Now each sweep takes the store's last look at every conversation it erases - given
only once it is erased - and the desk erases what each named that nothing else names. Where the sweep fails part-way, the papers
of those it erased are erased all the same. What it says is counts, never a name.

Offline: the served application with stand-in models and a recorded malware check, swept at a moment after the thirty days; no
browser; the words are invented.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from nm.app import main
from nm.core_engine.conversation import chat_matter_id
from nm.shared.store_file_store import PUT_BACK_DAYS
from tests.test_core_served import OTHER, OWNER, served  # noqa: F401 - served is a fixture
from tests.test_erase_now_erases_the_conversations_papers_unless_another_names_them import _sent, _upload, papers  # noqa: F401

pytestmark = pytest.mark.class_a


def _later(days=PUT_BACK_DAYS + 1):
    return datetime.now(timezone.utc) + timedelta(days=days)


def _deleted(client, chat_id):
    reply = client.request("DELETE", f"/api/chats/{chat_id}")
    assert reply.status_code == 200, reply.text
    return reply.json()["ref"]


def test_the_sweep_erases_the_conversation_and_then_its_papers(papers, capsys):
    ref = _upload(papers.client)
    chat = _sent(papers, ref, "turn-1")
    _deleted(papers.client, chat)
    main._sweep_deleted(papers.app, _later())
    assert papers.store.load(chat_matter_id(OWNER, chat)) is None and papers.client.get("/api/deleted-chats").json()["deleted"] == []
    assert papers.client.get(f"/api/documents/{ref}").status_code == 404
    assert papers.client.get(f"/api/documents/{ref}/original").status_code == 404
    said = capsys.readouterr().err
    assert "1 conversation(s)" in said and "Their papers: 1 erased, 0 kept" in said
    assert ref.split("-")[0] not in said and "notice" not in said, "counts, never a name"


def test_a_paper_another_conversation_names_is_kept_by_the_sweep(papers):
    ref = _upload(papers.client)
    swept, kept = _sent(papers, ref, "turn-1"), _sent(papers, ref, "turn-2")
    _deleted(papers.client, swept)
    main._sweep_deleted(papers.app, _later())
    assert papers.client.get(f"/api/documents/{ref}/original").status_code == 200
    assert papers.client.get(f"/api/chats/{kept}/documents").json()["sent"][0]["documents"][0]["file"] is not None


def test_nothing_is_swept_before_the_thirty_days_and_its_papers_stay(papers, capsys):
    ref = _upload(papers.client)
    chat = _sent(papers, ref, "turn-1")
    put_aside = _deleted(papers.client, chat)
    main._sweep_deleted(papers.app, _later(PUT_BACK_DAYS - 1))
    assert capsys.readouterr().err == "", "nothing to say"
    assert papers.client.post(f"/api/deleted-chats/{put_aside}/put-back").status_code == 200
    assert papers.client.get(f"/api/documents/{ref}/original").status_code == 200


def test_each_advocates_papers_go_from_their_own_space(papers):
    other = papers.login(OTHER)
    mine, theirs = _upload(papers.client), _upload(other, "Their own notice.")
    kept = _upload(other, "A paper of theirs no conversation has named.")
    _deleted(papers.client, _sent(papers, mine, "turn-1"))
    their_chat = other.post("/api/turn", json={"message": "Read this notice.", "turn_id": "turn-9", "document_refs": [theirs]})
    assert their_chat.status_code == 200, their_chat.text
    _deleted(other, their_chat.json()["chat_id"])
    main._sweep_deleted(papers.app, _later())
    assert papers.client.get(f"/api/documents/{mine}").status_code == 404
    assert other.get(f"/api/documents/{theirs}").status_code == 404
    assert other.get(f"/api/documents/{kept}").status_code == 200


def test_where_the_sweep_fails_part_way_the_papers_of_those_it_erased_go_all_the_same(papers, monkeypatch, capsys):
    ref = _upload(papers.client)
    chat = _sent(papers, ref, "turn-1")
    _deleted(papers.client, chat)
    sweeping = papers.app.store.sweep_deleted

    def fails_after(now, look=None):
        sweeping(now, look=look)
        raise PermissionError("the folder of the next refuses")
    monkeypatch.setattr(papers.app.store, "sweep_deleted", fails_after)
    main._sweep_deleted(papers.app, _later())
    said = capsys.readouterr().err
    assert "could not be swept (PermissionError)" in said and "Their papers: 1 erased" in said
    assert papers.client.get(f"/api/documents/{ref}").status_code == 404


def test_a_conversation_whose_record_could_not_be_read_keeps_its_papers_and_says_so(papers, capsys):
    ref = _upload(papers.client)
    chat = _sent(papers, ref, "turn-1")
    _deleted(papers.client, chat)
    (papers.store._root / "matters" / f"{chat_matter_id(OWNER, chat)}.nm").write_bytes(b"damaged beyond reading")
    main._sweep_deleted(papers.app, _later())
    said = capsys.readouterr().err
    assert "1 conversation(s)" in said and "could not be read, and their papers are kept" in said
    assert papers.client.get(f"/api/documents/{ref}").status_code == 200, "kept for the sweep of papers nothing names"
