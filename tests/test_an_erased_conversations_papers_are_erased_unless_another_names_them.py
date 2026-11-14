"""What an erased conversation named is erased in its turn, unless another conversation still names it (plan AN.53, D244's third
piece: the document desk's erasure).

D244: a paper - its original's parts and every record of its text - is kept in the advocate's own document space, and goes with
the last conversation that names it. The desk now finds every paper a conversation's saved record names, wherever in the record,
and erases those of them no kept conversation of the advocate's still names: the original first, then the text, so that an
erasure cut off part-way is still found by the paper's text and erased again. Where any of the advocate's conversations could not
be read, nothing is erased: whether it names a paper cannot be known. Only the advocate's own space is touched. Nothing asks for
it yet (the store's last look at a conversation it erases, and the callers, are the next pieces); `naming` stands in for the
store here.

Offline: the real desk on a store in a temporary folder, with a recorded malware check; no model call; the words are invented.
"""
from __future__ import annotations

import json

import pytest

from nm.app.documents import papers_named
from nm.core_engine import documents
from nm.core_engine.documents import DocumentRefused
from tests.test_core_documents import ADVOCATE, OTHER, desk, originals  # noqa: F401 - desk is a fixture

pytestmark = pytest.mark.class_a

A, B = "doc_" + "a1" * 12, "doc_" + "b2" * 12


def _sent(desk, advocate=ADVOCATE, words="The cheque was returned unpaid on 3 October 2026."):
    record = desk.receive(advocate, "notice.txt", words.encode())
    return record, documents.reference(record)


def _nobody_else(advocate_id, papers):
    return frozenset(), 0


def _gone(desk, tmp_path, advocate, record, ref):
    with pytest.raises(DocumentRefused):
        desk.load(advocate, ref)
    return originals(tmp_path, record) == []


# ------------------------------------------------------------------------- what a conversation names ---

def test_every_paper_the_record_names_is_found_wherever_it_is_named():
    record = json.dumps({"rows": [{"documents": [{"document_ref": f"{A}-{'0' * 64}", "name": "notice.txt"}]}],
                         "held": {"steers": [{"document_refs": [B]}], "message": "see the notice"}}).encode()
    assert papers_named(record) == {A, B}
    assert papers_named(record.decode()) == {A, B}


@pytest.mark.parametrize("text", ["doc_" + "a" * 23, "doc_" + "a" * 25, "xdoc_" + "a" * 24, "doc_" + "A" * 24, "doc-" + "a" * 24])
def test_what_is_not_a_papers_own_name_is_not_taken_for_one(text):
    assert papers_named(f'{{"said": "{text}"}}') == frozenset()


# --------------------------------------------------------------------------------------- the erasure ---

def test_a_paper_no_other_conversation_names_is_erased_its_original_and_its_text(desk, tmp_path):
    named, named_ref = _sent(desk)
    other, other_ref = _sent(desk, words="A second paper, named by another conversation.")
    theirs, theirs_ref = _sent(desk, advocate=OTHER)
    said = desk.erase(ADVOCATE, {named["document_id"]}, _nobody_else)
    assert said == {"erased": [named["document_id"]], "kept": [], "left": [], "unread": 0}
    assert _gone(desk, tmp_path, ADVOCATE, named, named_ref), "its original's parts are removed too"
    assert desk.load(ADVOCATE, other_ref) == other and originals(tmp_path, other), "another paper of theirs is kept"
    assert desk.load(OTHER, theirs_ref) == theirs and originals(tmp_path, theirs), "and another advocate's"


def test_a_paper_another_conversation_still_names_is_kept(desk, tmp_path):
    named, ref = _sent(desk)
    asked = []

    def naming(advocate_id, papers):
        asked.append((advocate_id, papers))
        return frozenset({named["document_id"]}), 0
    said = desk.erase(ADVOCATE, {named["document_id"]}, naming)
    assert said == {"erased": [], "kept": [named["document_id"]], "left": [], "unread": 0}
    assert asked == [(ADVOCATE, frozenset({named["document_id"]}))], "asked once, about these papers, of this advocate"
    assert desk.load(ADVOCATE, ref) == named and originals(tmp_path, named)


def test_nothing_is_erased_where_a_conversation_of_theirs_could_not_be_read(desk, tmp_path):
    named, ref = _sent(desk)
    said = desk.erase(ADVOCATE, {named["document_id"]}, lambda advocate_id, papers: (frozenset(), 1))
    assert said == {"erased": [], "kept": [named["document_id"]], "left": [], "unread": 1}
    assert desk.load(ADVOCATE, ref) == named and originals(tmp_path, named)


def test_a_conversation_that_named_no_paper_asks_nothing():
    from nm.app.documents import DocumentDesk
    bare = DocumentDesk(prepare_space=None, originals=None, texts=None, checker=None, reader=None)
    assert bare.erase(ADVOCATE, frozenset(), lambda *args: pytest.fail("nothing to ask")) == {
        "erased": [], "kept": [], "left": [], "unread": 0}


def test_only_the_advocates_own_space_is_touched(desk, tmp_path):
    named, ref = _sent(desk)
    desk.erase(OTHER, {named["document_id"]}, _nobody_else)
    assert desk.load(ADVOCATE, ref) == named and originals(tmp_path, named), "another advocate's erasure never reaches it"


# ------------------------------------------------------------------------------- order and failure ---

class Recorded:
    """One of the desk's two stores, its erasures recorded; stuck: what it says it could not remove; refuses: it fails."""

    def __init__(self, inner, kind, order, stuck=(), refuses=False):
        self.inner, self.kind, self.order, self.stuck, self.refuses = inner, kind, order, tuple(stuck), refuses

    def erase(self, where, paper):
        self.order.append((self.kind, paper))
        if self.refuses:
            raise PermissionError("the folder refuses")
        return self.stuck or self.inner.erase(where, paper)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def test_the_original_goes_first_and_its_text_last(desk, monkeypatch):
    named, _ = _sent(desk)
    order = []
    monkeypatch.setattr(desk, "originals", Recorded(desk.originals, "original", order))
    monkeypatch.setattr(desk, "texts", Recorded(desk.texts, "text", order))
    desk.erase(ADVOCATE, {named["document_id"]}, _nobody_else)
    assert order == [("original", named["document_id"]), ("text", named["document_id"])]


def test_a_paper_whose_original_was_not_all_removed_keeps_its_text_to_be_found_again(desk, tmp_path, monkeypatch):
    named, ref = _sent(desk)
    order = []
    monkeypatch.setattr(desk, "originals", Recorded(desk.originals, "original", order, stuck=(f"{named['document_id']}-0",)))
    monkeypatch.setattr(desk, "texts", Recorded(desk.texts, "text", order))
    said = desk.erase(ADVOCATE, {named["document_id"]}, _nobody_else)
    assert said["left"] == [named["document_id"]] and said["erased"] == []
    assert order == [("original", named["document_id"])], "its text is not touched"
    assert desk.load(ADVOCATE, ref) == named


def test_a_store_that_fails_leaves_that_paper_and_the_next_is_erased(desk, tmp_path, monkeypatch, caplog):
    first, first_ref = _sent(desk)
    second, second_ref = _sent(desk, words="A second paper, for the same conversation.")
    failing = min(first["document_id"], second["document_id"])  # the one the desk takes first
    order = []
    real = desk.originals

    class FailsOnce(Recorded):
        def erase(self, where, paper):
            self.refuses = paper == failing
            return super().erase(where, paper)
    monkeypatch.setattr(desk, "originals", FailsOnce(real, "original", order))
    said = desk.erase(ADVOCATE, {first["document_id"], second["document_id"]}, _nobody_else)
    erased = ({first["document_id"], second["document_id"]} - {failing}).pop()
    assert said == {"erased": [erased], "kept": [], "left": [failing], "unread": 0}
    assert "could not be erased" in caplog.text and failing not in caplog.text, "said, and naming no paper"
    kept_ref = first_ref if first["document_id"] == failing else second_ref
    assert desk.load(ADVOCATE, kept_ref)["document_id"] == failing


def test_a_paper_the_malware_check_held_has_only_its_text_and_that_is_erased(desk, tmp_path):
    desk.checker.state, desk.checker.reason = "held", "a recorded threat"
    held, ref = _sent(desk)
    assert originals(tmp_path, held) == [], "a held paper's original was never kept"
    assert desk.erase(ADVOCATE, {held["document_id"]}, _nobody_else)["erased"] == [held["document_id"]]
    with pytest.raises(DocumentRefused):
        desk.load(ADVOCATE, ref)


# ------------------------------------------------------- papers never sent, after thirty days (53h4a2) ---

def test_a_paper_received_thirty_days_ago_that_nothing_names_is_erased_and_a_younger_one_is_kept(desk, tmp_path):
    """Plan AN.53, D241 and D244 (53h4a2): a paper uploaded and never sent with a message is kept 30 days from its receipt."""
    from datetime import datetime, timedelta, timezone

    from nm.app.documents import UNSENT_DAYS
    now = datetime(2026, 11, 14, 9, 0, tzinfo=timezone.utc)
    desk.clock = lambda: now - timedelta(days=UNSENT_DAYS, minutes=1)
    old, old_ref = _sent(desk)
    theirs, theirs_ref = _sent(desk, advocate=OTHER)
    desk.clock = lambda: now - timedelta(days=UNSENT_DAYS - 1)
    young, young_ref = _sent(desk, words="A paper received yesterday but one, a month on.")
    asked = []

    def naming(advocate_id, papers):
        asked.append(set(papers))
        return frozenset(), 0
    said = desk.sweep_unsent(ADVOCATE, now, naming)
    assert said == {"erased": [old["document_id"]], "kept": [], "left": [], "unread": 0}
    assert asked == [{old["document_id"]}], "only the old paper is asked about"
    assert _gone(desk, tmp_path, ADVOCATE, old, old_ref)
    assert desk.load(ADVOCATE, young_ref) == young and desk.load(OTHER, theirs_ref) == theirs


def test_an_old_paper_a_conversation_names_is_kept_and_nothing_goes_where_one_could_not_be_read(desk):
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 11, 14, 9, 0, tzinfo=timezone.utc)
    desk.clock = lambda: now - timedelta(days=90)
    sent, ref = _sent(desk)
    assert desk.sweep_unsent(ADVOCATE, now, lambda advocate_id, papers: (frozenset(papers), 0))["kept"] == [sent["document_id"]]
    assert desk.sweep_unsent(ADVOCATE, now, lambda advocate_id, papers: (frozenset(), 1))["unread"] == 1
    assert desk.load(ADVOCATE, ref) == sent


def test_a_paper_whose_record_cannot_be_read_is_of_an_age_not_known_and_is_kept(desk, tmp_path):
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 11, 14, 9, 0, tzinfo=timezone.utc)
    desk.clock = lambda: now - timedelta(days=90)
    sent, ref = _sent(desk)
    for path in tmp_path.rglob(f"{ref}.nm"):
        path.write_bytes(b"damaged beyond reading")
    assert desk.sweep_unsent(ADVOCATE, now, _nobody_else) == {"erased": [], "kept": [], "left": [], "unread": 0}
    assert originals(tmp_path, sent), "its original is kept with it"


def test_a_paper_with_a_reading_since_is_aged_from_when_it_was_first_received(desk, tmp_path):
    from datetime import datetime, timedelta, timezone

    from nm.app.documents import space
    now = datetime(2026, 11, 14, 9, 0, tzinfo=timezone.utc)
    desk.clock = lambda: now - timedelta(days=40)
    sent, ref = _sent(desk)
    again = {**sent, "pages": [{**sent["pages"][0], "text": sent["pages"][0]["text"] + " (read again)"}]}
    body = json.dumps(again, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    desk.texts.put(space(ADVOCATE), documents.reference(again), body)
    assert desk.sweep_unsent(ADVOCATE, now, _nobody_else)["erased"] == [sent["document_id"]]
    assert list((tmp_path / "document-text").rglob(f"{sent['document_id']}-*.nm")) == [], "every reading of it goes"
