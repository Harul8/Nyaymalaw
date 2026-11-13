"""A message sent while a matter waits for the advocate (plan AN.48, piece 48c; owner decisions D146, D158, D161): the message reader
judges what it is - a go-ahead, information, a correction, a rethink, a new question, or unclear - and code admits a go-ahead only as
one the stop offers, for the matter's disputes. A go-ahead runs its step; information, a correction or a rethink joins the matter as
the advocate's words and the matter is understood again with them; a new question waits as the next message; an unclear one is asked
about; a reader that cannot be reached loses no message. NM says how it took each. Offline: scripted models; the words are invented."""
import json

import pytest

from nm.core_engine import message_reader, steps
from nm.core_engine.conversation import queued_of, shown_of, stored_chat, chat_matter_id
from nm.shared.model_port import ModelResult, ProviderUnavailable, Usage
from nm.shared.budget_contracts import Completion
from tests.test_core_answer_sections import Scripted, scripted_answers
from tests.test_core_served import OWNER, served  # noqa: F401 - pytest fixture

SENT = {"message": "Inspect this reported account.", "turn_id": "turn-1", "steps": "interactive"}
CHAT = stored_chat(OWNER, None, "turn-1")


def judged(**out):
    base = {"kind": "unclear", "choice": None, "disputes": [], "critical": False, "corrects": "", "said": "", "ask": ""}
    return {**base, **out}


class Reader:
    """A stand-in reader: each call returns the next judgement given, and keeps what it was asked."""

    def __init__(self, *judgements):
        self.judgements, self.asked = list(judgements), []

    def answer(self, prompt, schema, tier):
        self.asked.append(json.loads(prompt.user))
        out = self.judgements.pop(0)
        if isinstance(out, Exception):
            raise out
        return ModelResult(None, out, tier, "synthetic", "fixture", Usage(1, 1, 0), 0, completion=Completion.COMPLETE)


def reading(served, reader):
    """The served model answers the message reader's calls from reader; every other call as before."""
    first = served.model.structured

    def structured(prompt, schema, tier, **kwargs):
        if prompt.operation == message_reader.OPERATION:
            return reader.answer(prompt, schema, tier)
        return first(prompt, schema, tier, **kwargs)
    served.model.structured = structured


def waiting_matter(served):
    scripted_answers(served, Scripted())
    reply = served.client.post("/api/turn", json=SENT)
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting"


def say(served, words):
    return served.client.post("/api/turn/message", json={"chat_id": CHAT, "turn_id": "turn-1", "message": words})


def held(served):
    return shown_of(served.store.load(chat_matter_id(OWNER, CHAT)))


def test_a_go_ahead_in_words_runs_its_step_for_the_dispute_named(served):
    waiting_matter(served)
    reader = Reader(judged(kind="go", choice="research", disputes=["D1"], said="Taken as your go-ahead to research D1."))
    reading(served, reader)
    reply = say(served, "Go ahead with the first dispute.")
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting"
    record = held(served)
    assert set(record["steps"]["parts"]) == {"D1"} and steps.waiting_of(record) == "researched"
    assert record["go"]["heard"][-1]["text"] == "Go ahead with the first dispute."
    card = served.client.get(f"/api/chats/{CHAT}").json()["pending"]["stopped"]["waiting"]
    # Plan AN.51 (51b, D196): code's own sentence first; the reader's wording after it, marked.
    assert card["heard"][-1]["said"] == "Taken as your go-ahead. NM's reading: Taken as your go-ahead to research D1."
    seen = reader.asked[0]
    assert seen["new_message"] == "Go ahead with the first dispute."
    assert [d["id"] for d in seen["where_the_matter_stands"]["disputes"]] == ["D1", "D2"]


def test_a_go_ahead_the_stop_does_not_offer_is_asked_again_then_taken_as_unclear(served):
    waiting_matter(served)
    wrong = judged(kind="go", choice="write", disputes=["D1"], said="Writing D1.")  # not researched yet
    reader = Reader(wrong, wrong)
    reading(served, reader)
    reply = say(served, "Write it up.")
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "heard"
    assert reply.json()["detail"]["heard"]["taken"] == "unclear"
    assert "why_it_cannot_be_taken" in reader.asked[1], "told why, once"
    assert steps.waiting_of(held(served)) == "understood" and held(served)["steps"]["parts"] == {}


def test_information_joins_the_matter_as_the_advocates_own_message_and_nothing_is_redone(served):
    """48h (D159) refines 48c: information is kept as the advocate's message after the latest one; the matter is not understood
    again for it."""
    waiting_matter(served)
    reader = Reader(judged(kind="information", disputes=["D2"], critical=True,
                           said="Taken as new information: the notice was served on 3 March."))
    reading(served, reader)
    calls_before = len(served.model.calls)
    reply = say(served, "The notice was served on 3 March.")
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "heard"
    record = held(served)
    assert [entry["text"] for entry in record["added"]] == ["The notice was served on 3 March."] and record["steers"] == []
    assert steps.waiting_of(record) == "understood" and record["go"]["heard"][-1]["taken"] == "information"
    assert len(served.model.calls) == calls_before, "nothing written yet to check: nothing is redone"


def test_a_rethink_joins_the_matter_as_the_advocates_words_and_it_is_understood_again(served):
    waiting_matter(served)
    reading(served, Reader(judged(kind="rethink", said="Taken as a request to rethink the matter.")))
    calls_before = len(served.model.calls)
    reply = say(served, "Look at this as a tenancy matter, not a sale.")
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting"
    record = held(served)
    assert [steer["text"] for steer in record["steers"]] == ["Look at this as a tenancy matter, not a sale."]
    assert steps.waiting_of(record) == "understood" and record["go"]["heard"][-1]["taken"] == "rethink"
    understood_again = [name for name, _ in served.model.calls[calls_before:] if name == "core_research_understand"]
    assert understood_again, "the matter is understood again with the advocate's words"


def test_a_new_question_waits_as_the_next_message_and_nothing_runs(served):
    waiting_matter(served)
    reading(served, Reader(judged(kind="question", said="Taken as a new question; it waits until you finish this matter.")))
    reply = say(served, "What is the stamp duty in Pune?")
    assert reply.status_code == 409 and reply.json()["detail"] == {
        **reply.json()["detail"], "code": "heard", "kept": True,
        "heard": {"taken": "question", "said": "Taken as a new question; it waits until you finish this matter."}}
    assert queued_of(served.store.load(chat_matter_id(OWNER, CHAT))) == [
        {"text": "What is the stamp duty in Pune?", "documents": []}]
    assert steps.waiting_of(held(served)) == "understood"


def test_an_unclear_message_is_asked_about(served):
    waiting_matter(served)
    reading(served, Reader(judged(kind="unclear", said="I could not tell how you meant this.",
                                  ask="Is this a new fact for the lease dispute?")))
    reply = say(served, "Also the lease.")
    assert reply.json()["detail"]["heard"]["said"] == (
        "NM could not tell how you meant this message. NM's reading: I could not tell how you meant this. "
        "Is this a new fact for the lease dispute?")


def test_a_reader_that_cannot_be_reached_loses_no_message(served):
    waiting_matter(served)
    reading(served, Reader(ProviderUnavailable("Synthetic outage")))
    reply = say(served, "Go ahead.")
    assert reply.status_code == 409 and reply.json()["detail"]["heard"]["taken"] == "unread"
    assert held(served)["go"]["heard"][-1]["text"] == "Go ahead."
    assert steps.waiting_of(held(served)) == "understood"


def test_a_message_is_taken_only_while_the_matter_waits(served):
    reply = say(served, "Go ahead.")
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "not_waiting"


def test_code_admits_only_the_matters_disputes_and_says_something_where_the_reader_did_not():
    plan = {"proposal": {"understanding": {"disputes": [{"id": "D1", "name": "Lease"}, {"id": "D2", "name": "Notice"}]}},
            "work": [{"id": "w1", "dispute": {"id": "D1"}}, {"id": "w2", "dispute": {"id": "D2"}}]}
    record = {"steps": {"understood": {"interpretation": {}, "plan": plan}, "limits": None, "parts": {}, "cases": {},
                        "answered": None},
              "go": steps.waited(steps.first(), "understood"), "stopped": {"code": "waiting", "at": "now"}}
    judgement, why = message_reader.admitted(judged(kind="information", disputes=["D9"]), record)
    assert judgement is None and "D9" in why
    judgement, _ = message_reader.admitted(judged(kind="information", disputes=["D2"], said=""), record)
    assert judgement["disputes"] == ["D2"] and judgement["said"] == message_reader.SAID["information"]
    judgement, _ = message_reader.admitted(judged(kind="go", choice="research", disputes=["D2"]), record)
    assert judgement["go"]["allowed"] == ["research"] and judgement["go"]["disputes"] == ["D2"]
    assert message_reader.admitted({"kind": "dance"}, record)[0] is None
