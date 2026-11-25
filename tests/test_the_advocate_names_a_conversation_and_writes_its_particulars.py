"""The advocate's own name for a conversation and its particulars, kept with it (plan AN.55, piece 55c1; D255, D256, D332,
D355).

The advocate names a conversation and writes its particulars - the client, the court, the case number, the next date - by their
own hand. Both are kept in the conversation's own keyed record, as NM's title is: the saved matter's stored shape does not
change, its turns and receipts stay exactly as saved (P46), NM's title stays under its own key and the name is shown in its
place, and an empty name gives NM's title back. Each is checked as it is written and as it is read. Offline: a temporary sealed
store and invented words.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from nm.core_engine import conversation
from nm.core_engine.conversation import (
    NAME,
    PARTICULARS,
    TITLE,
    admitted_particulars,
    checked_rows,
    commit_turn,
    name_of,
    named,
    open_turn,
    particulars_of,
    save_name,
    save_particulars,
    save_title,
    shown_title,
)
from nm.shared.store_file_store import FileMatterStore
from nm.shared.store_port import StaleWrite

pytestmark = pytest.mark.class_a


@pytest.fixture
def saved(tmp_path):
    store = FileMatterStore(tmp_path, key="synthetic-not-a-secret")
    context = open_turn(store, advocate_id="owner", message="A synthetic question about a lease.", turn_id="t1")
    commit_turn(store, context, elements=[{"text": "A synthetic answer."}], activities={"fixture": "synthetic"},
                session_current=lambda: True)
    return store, store.load(context.matter.id)


def test_a_name_is_shown_in_place_of_nm_s_title_which_stays_and_comes_back_when_the_name_is_taken_away(saved):
    store, matter = saved
    matter = save_title(store, matter, {"text": "Lease of a shop in Andheri", "from_matter": True})
    assert shown_title(matter) == {"text": "Lease of a shop in Andheri", "by": "nm"}
    turns = matter.brain_chat
    renamed = save_name(store, matter, "  Mehta   lease \n renewal  ")
    assert renamed.version == matter.version + 1
    again = store.load(matter.id)
    assert name_of(again) == "Mehta lease renewal", "kept as one line, the spaces evened"
    assert shown_title(again) == {"text": "Mehta lease renewal", "by": "advocate"}
    assert again.intake_answers[TITLE]["text"] == "Lease of a shop in Andheri", "NM's own title is kept, never written over"
    assert again.brain_chat == turns and checked_rows(again, "owner"), "the turns and their receipts stay exactly as saved"
    back = save_name(store, again, "")
    assert NAME not in back.intake_answers and shown_title(store.load(matter.id))["by"] == "nm"


def test_a_name_that_cannot_be_kept_is_refused_and_nothing_is_written(saved):
    store, matter = saved
    for text, why in [("x" * 121, "121 characters"), ("see https://example.test/a", "link"),
                      ("Send me your password", "password")]:
        assert named(text)[0] is None and why in named(text)[1]
        with pytest.raises(ValueError, match=why):
            save_name(store, matter, text)
    assert store.load(matter.id).version == matter.version


def test_particulars_are_kept_only_as_given_and_each_is_checked(saved):
    store, matter = saved
    written = save_particulars(store, matter, {"client": " Asha  Rao ", "court": "City Civil Court, Mumbai",
                                               "case_number": "", "next_date": "2026-12-04"})
    assert particulars_of(store.load(matter.id)) == {"client": "Asha Rao", "court": "City Civil Court, Mumbai",
                                                    "next_date": "2026-12-04"}
    for given, why in [({"client": "a" * 201}, "201 characters"), ({"next_date": "4 Dec 2026"}, "calendar date"),
                       ({"next_date": "2026-02-30"}, "calendar date"), ({"court": "https://example.test"}, "link"),
                       ({"judge": "someone"}, "not the ones kept")]:
        assert admitted_particulars(given)[1] and why in admitted_particulars(given)[1]
        with pytest.raises(ValueError, match=why):
            save_particulars(store, written, given)
    emptied = save_particulars(store, written, {"client": None, "court": " ", "case_number": None, "next_date": None})
    assert PARTICULARS not in emptied.intake_answers and particulars_of(store.load(matter.id)) == {}


def test_what_cannot_be_read_reliably_says_so(saved):
    _, matter = saved
    for key, held in [(NAME, {"text": "Mehta", "extra": 1}), (NAME, {"text": "  "}), (NAME, "Mehta"),
                      (PARTICULARS, {}), (PARTICULARS, {"client": ""}), (PARTICULARS, {"next_date": "soon"})]:
        broken = replace(matter, intake_answers={**matter.intake_answers, key: held})
        reader = name_of if key == NAME else particulars_of
        with pytest.raises(ValueError, match="could not be read reliably"):
            reader(broken)
    assert name_of(matter) is None and particulars_of(matter) == {} and shown_title(matter) is None


def test_a_write_on_a_conversation_that_moved_meanwhile_is_refused(saved):
    store, matter = saved
    save_name(store, matter, "First name")
    with pytest.raises(StaleWrite):
        save_particulars(store, matter, {"client": "Asha Rao"})
    assert particulars_of(store.load(matter.id)) == {}


def test_the_name_and_particulars_ride_in_the_keyed_record_so_the_format_stays_as_it_was(saved):
    # The stored shape of each format is pinned by tests/test_a_saved_matter_says_its_format.py, which this piece leaves as it is.
    from dataclasses import fields

    from nm.shared.store_file_store import MATTER_FORMAT
    from nm.work_the_file.matter_contracts import Matter
    store, matter = saved
    assert MATTER_FORMAT == 1 and {NAME, PARTICULARS}.isdisjoint(field.name for field in fields(Matter))
    assert {NAME, PARTICULARS}.isdisjoint({conversation.HEADER, conversation.TITLE, conversation.SHOWN, conversation.QUEUED})
    written = save_particulars(store, save_name(store, matter, "Mehta"), {"client": "Asha Rao"})
    assert store.load(matter.id).intake_answers == written.intake_answers
