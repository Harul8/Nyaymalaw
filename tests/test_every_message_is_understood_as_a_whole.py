"""F-C-04, F-C-06, LB-81, LB-83, LB-90. Every message is understood as a whole.

Owner, 28 September 2026: understand the contribution on every turn -- what
the advocate added or changed, what they want now and what that authorises --
and "for every message, we need to also extract updates / changes to be done to
the matter board". And: "not everything in the advocate message is a true fact
or assertion, NM should understand the context and accordingly classify ... and
validate the advocate inputs in a polite way rather than blindly believing
everything."

THE RULES THIS FILE HOLDS, each stated without the example that exercises it:

* a part of the read that quotes the advocate is refused unless the words are
  in the message, and the refusal is counted, never repaired;
* a request the conversation cannot carry out is named in the reply;
* words not put forward as true are kept but never charted or dated;
* a message that may belong to a different matter adds nothing until the
  advocate keeps it here;
* the board note reports what the saved file gained, and a removal waits for
  the advocate;
* a polite check joins the one gap queue and is asked once;
* the whole record is sealed with the turn and never served back.
"""
from __future__ import annotations

from datetime import date

import pytest

from nm.advise.answer_contracts import Answer, BoardChange, Element, ElementKind, Mode, Route
from nm.advise.turn_receipt_contracts import answer_from_payload, answer_payload

pytestmark = pytest.mark.class_a

TODAY = date(2026, 9, 5)
BRIEF = ("We act for the plaintiff at Hyderabad. Goods were supplied on 14 March 2019 "
         "and were never paid for.")


# ================================================================ the read ==


# ======================================================= on a served turn ==


# ================================================== the note, on its own ==


def test_an_answer_saved_before_the_note_existed_reads_back_with_an_empty_note():
    answer = Answer(route=Route.MATTER, mode=Mode.SHORT_QUESTION, mode_statement="m",
                    elements=(Element(kind=ElementKind.QUESTION, text="Which side?"),))
    old = answer_payload(answer)
    old.pop("board_changes")
    assert answer_from_payload(old).board_changes == ()
    with pytest.raises(ValueError):
        BoardChange("invented_kind", "text")


# ============================================================== on the wire ==


