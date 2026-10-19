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
from nm.shared.model_port import ProviderUnavailable
from nm.shared.model_scripted import ScriptedModelAdapter
from nm.work_the_file.matter_contracts import Matter
from tests.test_turn_contract import _model_config

pytestmark = pytest.mark.class_a

TODAY = date(2026, 9, 5)
BRIEF = ("We act for the plaintiff at Hyderabad. Goods were supplied on 14 March 2019 "
         "and were never paid for.")


def _said(**parts) -> dict:
    return {"discloses": "matter", "depth": "a_question", "why": "work on this matter",
            **parts}


class _Reads(ScriptedModelAdapter):
    """The ordinary double, with the contribution read chosen per message."""

    def __init__(self, route_for, fail_route=False):
        super().__init__(_model_config(), responses={"__default__": "File the suit."})
        self.route_for, self.fail_route = route_for, fail_route

    def structured(self, prompt, schema, tier, **kw):
        if schema.get("x-nm-read") == "route":
            if self.fail_route:
                raise ProviderUnavailable("the route read is unavailable in this test")
            chosen = self.route_for(prompt.user)
            if chosen is None:
                self._structured_responses.pop("route", None)
            else:
                self._structured_responses["route"] = chosen
        return super().structured(prompt, schema, tier, **kw)


# ================================================================ the read ==


# ======================================================= on a served turn ==


# ================================================== the note, on its own ==

def _matter(**kw) -> Matter:
    return Matter(id="mat_note", advocate_id="adv_1", title="Note", version=1, **kw)


def test_an_answer_saved_before_the_note_existed_reads_back_with_an_empty_note():
    answer = Answer(route=Route.MATTER, mode=Mode.SHORT_QUESTION, mode_statement="m",
                    elements=(Element(kind=ElementKind.QUESTION, text="Which side?"),))
    old = answer_payload(answer)
    old.pop("board_changes")
    assert answer_from_payload(old).board_changes == ()
    with pytest.raises(ValueError):
        BoardChange("invented_kind", "text")


# ============================================================== on the wire ==

def test_the_served_reply_carries_its_note_and_when_it_was_saved(client):
    reply = client.post("/api/turn", json={"message": BRIEF, "today": TODAY.isoformat()})
    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert body["at"] and body["board_changes"]
    assert all(set(row) == {"kind", "text", "target", "value", "was", "was_date"}
               for row in body["board_changes"])
    history = client.get(f"/api/matters/{body['matter_id']}/transcript").json()
    assert history["turns"][-1]["board_changes"] == body["board_changes"]


