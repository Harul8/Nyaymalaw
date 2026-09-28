"""A reopened or reloaded matter shows the whole conversation, as it was.

Owner, 28 September 2026. A turn released without admitting its message to the
file keeps no narrative on its receipt -- rightly -- and the read-back showed
its answer with the advocate's own words missing. The rule, for every read-back
turn: the advocate's words come back when any record holds them, the turn says
so when none does, and reading them back admits nothing.
"""
from dataclasses import replace

import pytest

from nm.advise.answer_contracts import Answer, Element, ElementKind, Mode, Route
from nm.advise.turn_receipt_contracts import TurnReceipt, answer_payload
from nm.open_matter.transcripts_api import project
from nm.work_the_file.matter_contracts import Matter, MatterId

pytestmark = pytest.mark.class_a

WORDS = "My client lent Rs. 50,000 as a hand loan and is now being threatened."


def _matter(*, admitted: bool) -> Matter:
    receipt = TurnReceipt(
        turn_id="turn-one", offer_fingerprint="a" * 64,
        recorded_at="2026-09-28T10:00:00+00:00",
        answer=answer_payload(Answer(
            route=Route.MATTER, mode=Mode.SHORT_QUESTION, mode_statement="checks outstanding",
            elements=(Element(kind=ElementKind.QUESTION,
                              text="State the work you are instructed to do."),))),
        message=WORDS if admitted else "", input_admitted=admitted)
    base = Matter(id=MatterId("m_reopened"), advocate_id="adv_demo", title="Reopened", version=1)
    return replace(base, turn_receipts=(receipt,), turns_applied=(receipt.turn_id,))


def _archive(message: str = WORDS, **extra) -> dict:
    return {"turn_id": "turn-one", "matter_id": "m_reopened", "message": message,
            "at": "2026-09-28T10:00:00+00:00", "withheld_by": [], **extra}


def test_an_unadmitted_turn_reads_back_with_the_advocates_own_words():
    matter = _matter(admitted=False)
    rows, problems = project(matter, (_archive(),))
    assert not problems
    assert rows[0]["message"] == WORDS and rows[0]["release_state"] == "released"
    assert rows[0]["input_admitted"] is False, "reading the words back admits nothing"
    assert matter.turn_receipts[0].message == "", "the receipt still keeps no narrative"


@pytest.mark.parametrize("archives", [
    (), (_archive(unreadable=True),), (_archive(message=""),), (_archive(message="   "),),
])
def test_words_no_record_holds_are_said_to_be_missing_not_shown_as_nothing(archives):
    rows, _ = project(_matter(admitted=False), archives)
    assert not rows[0]["message"].strip()
    assert rows[0]["message_source"] == "not_held"


def test_an_admitted_turn_reads_back_from_its_receipt_unchanged():
    matter = _matter(admitted=True)
    rows, _ = project(matter, (_archive(message="an archive copy that differs"),))
    assert rows[0] == matter.turn_receipts[0].projected(matter.id)
