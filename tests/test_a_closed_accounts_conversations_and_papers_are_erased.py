"""A closed account's conversations and papers are erased before its record goes (plan AN.53, 53h7b; D241's closed account, with
D246's safeguards).

The application closes an account in D246's order, each step safe to repeat: every conversation of the advocate's - kept or
deleted - is erased as Erase now erases it, its own key first; then every paper in their space, its original and every record of
its text; and only then the directory closes the account, its record last (53h7a). Every paper in the advocate's own space goes:
a conversation that could still name one would be theirs too. Nothing is erased while NM works on one of their conversations,
and nothing of another advocate's is touched. A closure cut off part-way says what it did, and the account is kept, suspended,
to be closed again.

Offline: the served application with stand-in models; no model call.
"""
from __future__ import annotations

import pytest

from nm.arrive.admin_port import AdminChangeRefused
from nm.arrive.advocate_contracts import utcnow
from tests.served_application import OTHER, OWNER, successful
from tests.test_core_document_routes import upload
from tests.test_core_documents import Checker

pytestmark = pytest.mark.class_a


def _theirs(served, who):
    """`who`'s conversations, kept or deleted, and the names in their document space."""
    from nm.app.documents import space
    mine = ({entry[0] for entry in served.store.saved_files_for(who)}
            | {said["matter_id"] for said in served.store.deleted_for(who)})
    papers = served.app.documents.texts.names(space(who))
    return mine, papers


@pytest.fixture
def two(served):
    """Two advocates, each with a conversation and a paper; the owner's account suspended, as D246 asks first."""
    served.app.documents.checker = Checker()
    successful(served)
    assert upload(served.client).status_code == 201
    other = served.login(OTHER)
    assert other.post("/api/turn", json={"message": "A second account's question.", "turn_id": "turn-other"}).status_code == 200
    assert upload(other).status_code == 201
    served.app.admin_accounts.set_suspended(OWNER, True, utcnow())
    return served


def test_the_conversations_then_the_papers_then_the_record_go(two):
    served = two
    mine, papers = _theirs(served, OWNER)
    assert mine and papers
    said = served.app.close_account(OWNER, utcnow())
    assert said["conversations"] == len(mine) and said["papers"] == 1
    assert said["sign_ins"] >= 1 and set(said) >= {"draft_keys", "reset_links"}
    after, papers_after = _theirs(served, OWNER)
    assert after == set() and papers_after == (), "nothing of theirs is left in the store or their space"
    assert not served.directory._advocate_path(OWNER).exists(), "and the record went last"


def test_another_advocates_conversation_and_paper_are_untouched(two):
    served = two
    theirs, their_papers = _theirs(served, OTHER)
    served.app.close_account(OWNER, utcnow())
    assert _theirs(served, OTHER) == (theirs, their_papers)
    assert served.directory._advocate_path(OTHER).exists()


def test_a_deleted_conversation_goes_too(two):
    served = two
    (chat,) = served.store.list_for(OWNER).matters
    served.store.mark_deleted(chat.id, OWNER, utcnow())
    assert served.app.close_account(OWNER, utcnow())["conversations"] == 1
    assert _theirs(served, OWNER)[0] == set()


def test_nothing_goes_while_nm_works_on_one_of_their_conversations(two, monkeypatch):
    served = two
    monkeypatch.setattr(served.app, "turn_running", lambda advocate_id, turn_id: True)
    from nm.core_engine import conversation
    monkeypatch.setattr(conversation, "shown_of", lambda matter: {"turn_id": "turn-1"})
    before = _theirs(served, OWNER)
    with pytest.raises(AdminChangeRefused) as refused:
        served.app.close_account(OWNER, utcnow())
    assert refused.value.status == 409 and "working" in refused.value.detail
    assert _theirs(served, OWNER) == before and served.directory._advocate_path(OWNER).exists()


def test_an_account_not_suspended_is_refused_before_anything_is_erased(served):
    served.app.documents.checker = Checker()
    successful(served)
    before = _theirs(served, OWNER)
    with pytest.raises(AdminChangeRefused) as refused:
        served.app.close_account(OWNER, utcnow())
    assert refused.value.status == 409 and "Suspend" in refused.value.detail
    assert _theirs(served, OWNER) == before


def test_a_closure_cut_off_part_way_says_what_it_did_and_keeps_the_account(two, monkeypatch):
    served = two
    real = served.store.erase

    def failing(matter_id, advocate_id, **kwargs):
        raise OSError("the disk refused")
    monkeypatch.setattr(served.store, "erase", failing)
    with pytest.raises(AdminChangeRefused) as refused:
        served.app.close_account(OWNER, utcnow())
    assert refused.value.status == 503 and "part-way" in refused.value.detail and "close it again" in refused.value.detail
    assert served.directory._advocate_path(OWNER).exists(), "the account kept, suspended, to be closed again"
    monkeypatch.setattr(served.store, "erase", real)
    assert served.app.close_account(OWNER, utcnow())["conversations"] >= 1, "made again, it finishes"


def test_a_conversation_that_cannot_be_read_just_now_stops_the_closure_before_anything_goes(two, monkeypatch):
    """Whether NM works on it cannot be known, so nothing is erased (an OSError is the disk's, not a damaged record's)."""
    served = two

    def unreadable(matter_id, advocate_id):
        raise OSError("the disk refused")
    monkeypatch.setattr(served.store, "load_for", unreadable)
    before = _theirs(served, OWNER)
    with pytest.raises(AdminChangeRefused) as refused:
        served.app.close_account(OWNER, utcnow())
    assert refused.value.status == 503 and "Nothing was erased" in refused.value.detail
    assert _theirs(served, OWNER) == before and served.directory._advocate_path(OWNER).exists()


def test_papers_that_cannot_be_listed_stop_the_closure_part_way_and_say_so(two, monkeypatch):
    served = two
    texts = served.app.documents.texts

    def unlisted(where):
        raise OSError("the disk refused")
    monkeypatch.setattr(texts, "names", unlisted)
    with pytest.raises(AdminChangeRefused) as refused:
        served.app.close_account(OWNER, utcnow())
    said = refused.value.detail
    assert refused.value.status == 503 and "part-way" in said and "1 conversation(s)" in said and "close it again" in said
    assert served.directory._advocate_path(OWNER).exists()


def test_a_directory_that_fails_after_the_erasures_is_said_part_way_never_as_nothing_changed(two, monkeypatch):
    from nm.arrive.admin_port import AdminUnavailable
    served = two

    def failing(account_id, now):
        raise AdminUnavailable("a sign-in could not be read")
    monkeypatch.setattr(served.app.admin_accounts, "close", failing)
    with pytest.raises(AdminChangeRefused) as refused:
        served.app.close_account(OWNER, utcnow())
    said = refused.value.detail
    assert refused.value.status == 503 and "part-way" in said and "1 paper(s)" in said and "close it again" in said
    assert _theirs(served, OWNER) == (set(), ()), "what was erased is erased"


def test_a_directory_that_refuses_after_the_erasures_says_what_was_erased(two, monkeypatch):
    served = two

    def refusing(account_id, now):
        raise AdminChangeRefused(409, "Suspend this account first; then close it.")
    monkeypatch.setattr(served.app.admin_accounts, "close", refusing)
    with pytest.raises(AdminChangeRefused) as refused:
        served.app.close_account(OWNER, utcnow())
    said = refused.value.detail
    assert refused.value.status == 409 and "were erased" in said and "Suspend this account first" in said


def test_a_file_in_the_store_whose_name_is_no_conversations_does_not_stop_a_closure(two, monkeypatch):
    """The store lists such a file as possibly the advocate's (its reading says why); it is no conversation to erase, as Erase
    now holds, and every closure would otherwise stop on it."""
    served = two
    real = served.store.saved_files_for
    monkeypatch.setattr(served.store, "saved_files_for", lambda who: real(who) + (("not a conversation's name", (0, 0), "", None),))
    said = served.app.close_account(OWNER, utcnow())
    assert said["conversations"] == 1 and not served.directory._advocate_path(OWNER).exists()
