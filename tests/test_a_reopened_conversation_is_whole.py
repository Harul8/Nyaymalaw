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
from nm.legal_brain.orchestrate.turn import TurnInput
from nm.open_matter.transcripts_api import project
from nm.work_the_file.matter_contracts import Matter, MatterId
from tests.test_turn_contract import build

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


def test_blocked_messages_read_back_in_order_without_becoming_case_facts(tmp_path):
    engine, store = build(tmp_path, intake=False)
    first = engine.run(TurnInput(advocate_id="adv", message=WORDS))
    later_words = "The opposing party may be Ravi Kumar; please check that name."
    second = engine.run(TurnInput(advocate_id="adv", matter_id=first.matter.id,
                                  message=later_words))

    saved = store.load(first.matter.id)
    rows, problems = project(saved, store.transcripts_for(saved.id))
    assert not problems
    assert [row["message"] for row in rows] == [WORDS, later_words]
    assert all(row["committed"] and row["release_state"] == "released" for row in rows)
    assert all(row["input_admitted"] is False for row in rows)
    assert all(receipt.message == "" for receipt in saved.turn_receipts)
    assert saved.facts == ()
    assert all("derived" not in archive for archive in store.transcripts_for(saved.id))
    assert first.answer.blocked and second.answer.blocked
    question = first.answer.elements[0].text.lower()
    assert "client" in question and "opposing party" in question
    assert "capacity" not in question, "a step-only limit was made an admission blocker"


def test_the_served_transcript_restores_the_words_of_a_blocked_turn(client, wired):
    # This test exercises the missing-intake path; the shared client normally
    # supplies completed intake so unrelated wire tests can reach legal work.
    wired.engine = wired.engine.inner
    sent = client.post("/api/turn", json={"message": WORDS})
    assert sent.status_code == 200, sent.text
    assert sent.json()["blocked"] is True
    matter_id = sent.json()["matter_id"]

    read = client.get(f"/api/matters/{matter_id}/transcript")
    assert read.status_code == 200, read.text
    rows = read.json()["turns"]
    assert len(rows) == 1
    assert rows[0]["message"] == WORDS
    assert rows[0]["message_source"] == "conversation_record"
    assert rows[0]["input_admitted"] is False
