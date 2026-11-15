"""An advocate keeps at most two thousand papers (plan AN.53, 53h5a; D241: the count of stored papers D235 left unset for want of
deletion - 2,000 for one advocate, set once deletion is built).

Each paper an advocate sends is kept in their own document space - its original and each record of its text - and nothing bounded
how many. Deletion is built now (53h1-53h3c: a conversation's papers go with it; 53h4a: papers never sent go after thirty days), so
the count is set: the 2,001st paper is refused before anything of it is stored, in words that say what frees room. A paper read
again has a record more, and is still one paper.

Offline: the document desk on a temporary store, with a stand-in malware checker; no model call.
"""
from __future__ import annotations

import pytest

from nm.app import documents as desk_rules
from nm.core_engine.documents import DocumentRefused
from tests.test_core_documents import ADVOCATE, OTHER, desk, originals  # noqa: F401 - desk is a fixture

pytestmark = pytest.mark.class_a
WORDS = b"The cheque was returned on 3 October 2026 for insufficient funds."


def _holding(desk, monkeypatch, count, *, records_each=1):
    """The advocate's space as if it held `count` papers (each with `records_each` records of its text), and their own."""
    real = desk.texts.names

    def names(where):
        held = [f"doc_{number:024x}-{'a' * 63}{again}" for number in range(count) for again in range(records_each)]
        return tuple(held) + real(where)
    monkeypatch.setattr(desk.texts, "names", names)


def test_the_count_is_two_thousand():
    assert desk_rules.PAPERS_KEPT_MOST == 2000


def test_the_papers_an_advocate_keeps_are_counted_once_each_however_often_read(desk, monkeypatch):
    assert desk.papers_kept(ADVOCATE) == 0
    desk.receive(ADVOCATE, "note.txt", WORDS)
    assert desk.papers_kept(ADVOCATE) == 1 and desk.papers_kept(OTHER) == 0, "one's own, not another's"
    _holding(desk, monkeypatch, 10, records_each=3)
    assert desk.papers_kept(ADVOCATE) == 11, "a paper read three times is one paper"


def test_the_two_thousand_and_first_is_refused_and_nothing_of_it_is_kept(desk, monkeypatch, tmp_path):
    _holding(desk, monkeypatch, desk_rules.PAPERS_KEPT_MOST)
    with pytest.raises(DocumentRefused) as refused:
        desk.receive(ADVOCATE, "note.txt", WORDS)
    said = str(refused.value)
    assert "2,000" in said and "Recently deleted" in said and "their papers go with them" in said
    assert not list(tmp_path.rglob("doc_*.nm")), "nothing of it stored"


def test_the_two_thousandth_is_taken(desk, monkeypatch):
    _holding(desk, monkeypatch, desk_rules.PAPERS_KEPT_MOST - 1)
    record = desk.receive(ADVOCATE, "note.txt", WORDS)
    assert record["document_id"].startswith("doc_")


def test_another_advocate_is_not_counted_against_one(desk, monkeypatch):
    real = desk.texts.names
    full = desk_rules.space(OTHER)

    def names(where):
        if where == full:
            return tuple(f"doc_{number:024x}-{'b' * 64}" for number in range(desk_rules.PAPERS_KEPT_MOST))
        return real(where)
    monkeypatch.setattr(desk.texts, "names", names)
    assert desk.receive(ADVOCATE, "note.txt", WORDS)["document_id"].startswith("doc_")
    with pytest.raises(DocumentRefused):
        desk.receive(OTHER, "note.txt", WORDS)
