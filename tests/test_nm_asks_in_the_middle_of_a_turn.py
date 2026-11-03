"""NM asks the advocate in the middle of a turn (plan AN.37, D37-D40, D44): what code lets a window show, how an answer is taken,
how the turn waits and goes on, and what is saved. Offline; scripted models; the window on the page is checked in the browser."""
from __future__ import annotations

import json
import threading

import pytest

from nm.core_engine import questions, turn
from nm.core_engine.conversation import ASKING, asking_of, chat_matter_id

pytestmark = pytest.mark.class_a


def proposal(**changes):
    item = {"header": "Your client", "question": "Whom do you act for?",
            "why": "It decides which party is adverse to your client in every dispute.",
            "choices": [{"label": "The buyer", "description": "Named first in the agreement"},
                        {"label": "The seller", "description": ""}],
            "multiple": False, "default": ["The buyer"], "depends": []}
    item.update(changes)
    return item


# --- what code lets a window show ------------------------------------------------------------------------------------------

def test_code_admits_well_formed_questions_and_says_why_it_refuses_the_rest():
    admitted, refused = questions.admit([
        proposal(),
        proposal(question="Which disputes should I take up now?", choices=[{"label": "Both"}]),
        proposal(question="Please confirm your login details?"),
        proposal(question="See https://example.test for the form - is it right?"),
        proposal(question="Whom do you act for?"),  # the same as the first
        proposal(question="Do you have the notice?", default=["Yes"]),
        proposal(question="Which dispute matters most?", depends=["D9"]),
        "not a question",
    ], disputes=["D1", "D2"])
    assert [(q["id"], q["question"], q["asked_by"]) for q in admitted] == [("q1", "Whom do you act for?", "model")]
    assert [item["why"] for item in refused] == [
        "it needs 2 to 4 choices", "it asks for a password, a code or a card", "it carries a link",
        "it was asked before in this conversation", "its default is not one of its choices",
        "it names something it depends on that this answer does not have", "not a question"]


def test_a_question_asked_before_in_the_conversation_is_never_asked_again_and_a_window_asks_at_most_four():
    _, refused = questions.admit([proposal()], asked_before=["  WHOM do you act for? "])
    assert refused == [{"position": 1, "why": "it was asked before in this conversation"}]
    many = [proposal(question=f"Question {number}?") for number in range(6)]
    admitted, refused = questions.admit(many)
    assert len(admitted) == 4 and [item["position"] for item in refused] == [5, 6]


def test_an_answer_is_one_of_the_choices_or_the_advocates_own_words():
    question = questions.admit([proposal()])[0][0]
    assert questions.answer(question, {"chosen": ["The seller"]}) == {"chosen": ["The seller"], "other": ""}
    assert questions.answer(question, {"other": " Neither: the bank "}) == {"chosen": [], "other": "Neither: the bank"}
    for wrong in ({"chosen": ["Someone"]}, {"chosen": ["The buyer", "The seller"]}, {}, {"other": "x" * 2001}):
        with pytest.raises(questions.Refused):
            questions.answer(question, wrong)


# --- how the turn waits ------------------------------------------------------------------------------------------------------

class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_the_work_waits_for_an_answer_and_goes_on_at_once_when_it_comes():
    question = questions.admit([proposal()])[0]
    sealed = []
    asking = questions.Asking(question, hold=sealed.append, wait=5)
    threading.Timer(0.05, lambda: asking.receive({"q1": {"chosen": ["The seller"]}})).start()
    answers = asking.ask()
    assert answers["q1"]["chosen"] == ["The seller"] and answers["q1"]["how"] == "answered"
    assert sealed and sealed[-1]["answers"][0]["how"] == "answered"


def test_without_an_answer_the_default_is_applied_and_a_late_answer_is_still_taken_while_the_window_is_open():
    clock = Clock()
    asking = questions.Asking(questions.admit([proposal()])[0], wait=0.01, open_for=600, clock=clock)
    answers = asking.ask()
    assert answers["q1"] == {**answers["q1"], "chosen": ["The buyer"], "how": "assumed"}
    began = asking.version
    # The same as the default: taken as the advocate's, and nothing to redo.
    clock.now = 100
    assert asking.receive({"q1": {"chosen": ["The buyer"]}}) == "taken"
    assert asking.answers()["q1"]["how"] == "late" and asking.changed_since(began) == set()
    # A different late answer counts only where none came before it; here the first one already did.
    assert asking.receive({"q1": {"chosen": ["The seller"]}}) == "taken" and asking.answers()["q1"]["chosen"] == ["The buyer"]


def test_a_late_answer_that_differs_from_the_default_is_what_the_writing_redoes_and_the_window_closes_after_ten_minutes():
    clock = Clock()
    asking = questions.Asking(questions.admit([proposal()])[0], wait=0.01, clock=clock)
    asking.ask()
    began = asking.version
    clock.now = 300
    asking.receive({"q1": {"chosen": ["The seller"]}})
    assert asking.changed_since(began) == {"q1"} and asking.answers()["q1"]["how"] == "late"
    clock.now = questions.OPEN + 1
    assert asking.receive({"q1": {"other": "Too late"}}) == "closed"


# --- through the real turn ---------------------------------------------------------------------------------------------------

class Desk:
    """The page's side: answers the window as soon as it opens, or not at all."""

    def __init__(self, given=None):
        self.given, self.opened = given, []

    def open(self, turn_id, asking):
        self.opened.append(turn_id)
        if self.given is not None:
            threading.Timer(0.02, lambda: asking.receive(self.given)).start()


def proposer(*items):
    asked = []

    def propose(calls, context, interpreted, plan, asked_before):
        asked.append(list(asked_before))
        return [dict(item) for item in items]
    propose.asked = asked
    return propose


def writer_payloads(model):
    return [json.loads(payload) if isinstance(payload, str) else payload for name, payload in model.calls
            if name == "core_response_writer"]


def test_an_answer_given_in_the_window_is_read_by_the_writing_and_saved_with_the_turn(store):
    from tests.test_core_turn import ScriptedModel, run
    model, desk = ScriptedModel(legal=True), Desk({"q1": {"chosen": ["The seller"]}})
    response = run(store, model, propose=proposer(proposal()), desk=desk)
    assert desk.opened == ["t1"] and response["committed"] == "committed"
    matter = store.load(chat_matter_id("owner", response["chat_id"]))
    assert ASKING not in matter.intake_answers  # the commit replaces what was sealed beside the conversation
    row = turn.saved_rows(matter, "owner")[0]
    assert [q["question"] for q in row["asked"]["questions"]] == ["Whom do you act for?"]
    assert [(a["chosen"], a["how"]) for a in row["asked"]["answers"]] == [(["The seller"], "answered")]
    # The writer read it with the conversation, as the advocate's answer.
    assert "The seller" in json.dumps(model.calls, ensure_ascii=False, default=str)


def test_without_an_answer_the_turn_goes_on_with_the_default_and_says_so_to_the_next_turn(store, monkeypatch):
    from tests.test_core_turn import ScriptedModel, run
    monkeypatch.setattr(questions, "WAIT", 0.01)
    propose = proposer(proposal())
    response = run(store, ScriptedModel(legal=True), propose=propose, desk=Desk())
    row = turn.saved_rows(store.load(chat_matter_id("owner", response["chat_id"])), "owner")[0]
    assert [(a["chosen"], a["how"]) for a in row["asked"]["answers"]] == [(["The buyer"], "assumed")]
    # The next turn reads it as NM's assumption, not the advocate's words, and is never asked the same again.
    from nm.core_engine.conversation import open_turn
    later = open_turn(store, advocate_id="owner", message="And now?", turn_id="t2", chat_id=response["chat_id"])
    rows = [item for item in later.payload()["conversation"] if item["source_id"] == "t1:q1"]
    assert rows == [{"source_id": "t1:q1", "turn_id": "t1", "speaker": "nm", "record_role": "nm_interpretation",
                     "text": "NM asked: Whom do you act for?\nNo answer came; NM went on assuming: The buyer"}]
    again = run(store, ScriptedModel(legal=True), propose=propose, desk=Desk(), chat_id=response["chat_id"],
                turn_id="t2", message="And now?")
    assert propose.asked[-1] == ["Whom do you act for?"] and "asked" not in turn.saved_rows(
        store.load(chat_matter_id("owner", again["chat_id"])), "owner")[1]


def test_a_message_sent_again_after_its_turn_stopped_while_asking_reuses_the_questions_and_answers(store, monkeypatch):
    from nm.shared.external_ai_contracts import ModelPermissionRefused
    from tests.test_core_turn import ScriptedModel, run
    model = ScriptedModel(legal=True)
    writing = model.structured

    def stopped(prompt, schema, tier, **kwargs):
        if prompt.operation == "core_response_writer":
            raise ModelPermissionRefused("External model permission is required.")
        return writing(prompt, schema, tier, **kwargs)
    model.structured = stopped
    with pytest.raises(ModelPermissionRefused):
        run(store, model, propose=proposer(proposal()), desk=Desk({"q1": {"chosen": ["The seller"]}}))
    from nm.core_engine.conversation import stored_chat
    chat = chat_matter_id("owner", stored_chat("owner", None, "t1"))
    held = asking_of(store.load(chat), "t1")
    assert held["state"]["answers"][0]["chosen"] == ["The seller"]
    propose = proposer(proposal(question="Something else?"))
    response = run(store, ScriptedModel(legal=True), propose=propose, desk=Desk())
    assert propose.asked == []  # nothing new was proposed: the sealed questions and the answer given were reused
    row = turn.saved_rows(store.load(chat), "owner")[0]
    assert [(a["chosen"], a["how"]) for a in row["asked"]["answers"]] == [(["The seller"], "answered")]
    assert response["committed"] == "committed"


def test_a_turn_with_nothing_to_ask_is_saved_exactly_as_before(store):
    from tests.test_core_turn import ScriptedModel, run
    response = run(store, ScriptedModel(legal=True), propose=lambda *args: [], desk=Desk())
    row = turn.saved_rows(store.load(chat_matter_id("owner", response["chat_id"])), "owner")[0]
    assert "asked" not in row


def test_a_late_answer_that_differs_is_written_again_once_in_the_sections_it_touches():
    """D44, through the real answer stage of two disputes: the sections are written on the default; an answer that came after
    them, touching the second dispute only, has that section written again, once, with it."""
    from nm.core_engine import answer_sections, calculation, response_writer
    from nm.core_engine.calls import TurnCalls
    from tests.test_core_answer_sections import Scripted
    from tests.test_core_response_writer import two_disputes
    ctx, record, sources = two_disputes()
    model = Scripted()
    disputes = [part["dispute_id"] for part in response_writer.parts(record) if part["dispute_id"]]

    class Later:
        def __init__(self):
            self.asked = 0

        def version(self):
            return 1

        def since(self, version):
            self.asked += 1
            return {**ctx, "answers": [{"question": "Whom do you act for?", "answer": "The seller",
                                        "given_by": "the advocate"}]}, {disputes[1]}
    later = Later()
    sections, _, _ = answer_sections.answer(
        TurnCalls(model), ctx, record, sources, interpretation={"units": []}, execution=turn.execution_record(record),
        worked=calculation.skipped(), later=later)
    assert later.asked == 1
    assert len(model.payloads("core_response_writer", disputes[0])) == 1
    assert len(model.payloads("core_response_writer", disputes[1])) == 2
    assert "The seller" in json.dumps(model.payloads("core_response_writer", disputes[1])[-1], ensure_ascii=False)
    assert [saved["dispute_id"] for saved in sections] == disputes


@pytest.fixture
def store(tmp_path):
    from nm.shared.store_file_store import FileMatterStore
    return FileMatterStore(tmp_path, key="synthetic-asking-fixture")
