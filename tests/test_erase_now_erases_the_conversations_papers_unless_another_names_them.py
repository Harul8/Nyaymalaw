"""Erase now erases a conversation's papers too, unless another conversation of the advocate's still names them (plan AN.53,
D244's fifth piece: Erase now).

D241: an advocate may erase a conversation they deleted at once, with everything that belongs to it - its papers as sent and the
text read from them among them. Until now Erase now erased the conversation and left its papers - their originals and the text
read from them - in the advocate's document space. Now, after the conversation is erased, each paper it named that no other
conversation of the advocate's names - one in use, or one deleted and not yet erased, which can still be put back - is erased
too. A paper sent and never named by the erased conversation is not touched, and nor is another advocate's. The conversation is
erased whatever becomes of its papers: where they could not be erased now they are kept, and said in the server's log.

Offline: the served application with stand-in models and a recorded malware check; no browser; the words are invented.
"""
from __future__ import annotations

import logging

import pytest

from nm.app.documents import space
from tests.test_core_documents import Checker
from tests.test_core_served import OTHER, OWNER, served  # noqa: F401 - served is a fixture
from tests.test_core_turn_documents import without_documents

pytestmark = pytest.mark.class_a


@pytest.fixture
def papers(served, monkeypatch):
    """The served application, reading the papers it is sent as the documents tests do."""
    served.app.documents.checker = Checker()
    scripted = served.model.structured
    monkeypatch.setattr(served.model, "structured",
                        lambda prompt, *args, **kwargs: scripted(without_documents(prompt), *args, **kwargs))
    return served


def _upload(client, words="The cheque was returned unpaid on 3 October 2026."):
    reply = client.post("/api/documents", content=words.encode(), headers={"x-nm-document-name": "notice.txt"})
    assert reply.status_code == 201, reply.text
    return reply.json()["document_ref"]


def _sent(served, ref, turn_id):
    """A new conversation whose first message carries the paper: its chat id."""
    reply = served.client.post("/api/turn", json={"message": "Read this notice.", "turn_id": turn_id, "document_refs": [ref]})
    assert reply.status_code == 200, reply.text
    return reply.json()["chat_id"]


def _erased(served, chat_id):
    deleted = served.client.request("DELETE", f"/api/chats/{chat_id}")
    assert deleted.status_code == 200, deleted.text
    erased = served.client.post(f"/api/deleted-chats/{deleted.json()['ref']}/erase")
    assert erased.status_code == 200, erased.text
    return erased.json()


def _files(served, ref):
    """The paper's files in its advocate's space: its original's parts and the records of its text."""
    paper = ref.split("-")[0]
    root = served.store._root
    return sorted(str(path.relative_to(root)) for folder in ("uploads", "document-text")
                  for path in (root / folder / space(OWNER)).glob(f"{paper}-*.nm"))


def test_a_paper_only_the_erased_conversation_named_is_erased_with_it(papers):
    ref = _upload(papers.client)
    chat = _sent(papers, ref, "turn-1")
    assert papers.client.get(f"/api/documents/{ref}").status_code == 200 and len(_files(papers, ref)) == 2
    said = _erased(papers, chat)
    assert said["state"] == "erased" and said["papers"] == {"erased": 1, "kept": 0, "left": 0}
    assert _files(papers, ref) == [], "its original and every record of its text are gone"
    assert papers.client.get(f"/api/documents/{ref}").status_code == 404
    assert papers.client.get(f"/api/documents/{ref}/original").status_code == 404


def test_a_paper_another_conversation_in_use_names_is_kept_until_the_last_is_erased(papers):
    ref = _upload(papers.client)
    first, second = _sent(papers, ref, "turn-1"), _sent(papers, ref, "turn-2")
    assert first != second
    assert _erased(papers, first)["papers"] == {"erased": 0, "kept": 1, "left": 0}
    assert papers.client.get(f"/api/documents/{ref}/original").status_code == 200, "the other conversation's paper is whole"
    listed = papers.client.get(f"/api/chats/{second}/documents").json()["sent"][0]["documents"][0]
    assert listed["file"] is not None and listed["file"]["cleared"] is True
    assert _erased(papers, second)["papers"] == {"erased": 1, "kept": 0, "left": 0}
    assert _files(papers, ref) == []


def test_a_paper_a_deleted_conversation_names_is_kept_for_it_to_be_put_back_whole(papers):
    ref = _upload(papers.client)
    first, second = _sent(papers, ref, "turn-1"), _sent(papers, ref, "turn-2")
    put_aside = papers.client.request("DELETE", f"/api/chats/{second}").json()["ref"]
    assert _erased(papers, first)["papers"] == {"erased": 0, "kept": 1, "left": 0}
    assert papers.client.post(f"/api/deleted-chats/{put_aside}/put-back").status_code == 200
    listed = papers.client.get(f"/api/chats/{second}/documents").json()["sent"][0]["documents"][0]
    assert listed["file"] is not None, "put back with its paper whole"
    assert papers.client.get(f"/api/documents/{ref}/original").status_code == 200


def test_a_paper_never_sent_with_the_erased_conversation_is_not_touched(papers):
    sent, unsent = _upload(papers.client), _upload(papers.client, "A paper uploaded and not yet sent.")
    chat = _sent(papers, sent, "turn-1")
    _erased(papers, chat)
    assert papers.client.get(f"/api/documents/{unsent}").status_code == 200 and len(_files(papers, unsent)) == 2


def test_another_advocates_papers_are_not_touched(papers):
    other = papers.login(OTHER)
    theirs = _upload(other, "Their own notice.")
    ref = _upload(papers.client)
    chat = _sent(papers, ref, "turn-1")
    _erased(papers, chat)
    assert other.get(f"/api/documents/{theirs}").status_code == 200


def test_the_conversation_is_erased_whatever_becomes_of_its_papers(papers, monkeypatch, caplog):
    ref = _upload(papers.client)
    chat = _sent(papers, ref, "turn-1")

    def unreadable(advocate_id, named):
        raise PermissionError("the store's folder refuses")
    monkeypatch.setattr(papers.app.store, "naming", unreadable)
    with caplog.at_level(logging.WARNING, logger="nm.papers"):
        said = _erased(papers, chat)
    assert said["state"] == "erased" and said["papers"] == {"erased": 0, "kept": 1, "left": 0}
    assert papers.client.get(f"/api/chats/{chat}").status_code == 404, "the conversation is gone all the same"
    assert len(_files(papers, ref)) == 2, "its paper is kept, to be found again"
    assert any("could not be erased now (PermissionError)" in record.getMessage() for record in caplog.records)
    assert ref not in caplog.text and "notice" not in caplog.text, "the log names no paper and no words"


def test_a_conversation_that_named_no_paper_erases_none(papers):
    ref = _upload(papers.client)
    reply = papers.client.post("/api/turn", json={"message": "Inspect this reported account.", "turn_id": "turn-1"})
    assert _erased(papers, reply.json()["chat_id"])["papers"] == {"erased": 0, "kept": 0, "left": 0}
    assert papers.client.get(f"/api/documents/{ref}").status_code == 200
