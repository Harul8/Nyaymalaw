"""NM's questions wait for the advocate in a matter worked step by step (plan AN.48, piece 48d; owner decisions D142, D154, D135).

No default after a wait: a question shown at a stop is answered there; where the writing of a dispute, or a dispute's research, needs
an answer not yet given, the step ends - waiting for the answers - and resumes by itself from its saved work once every question is
answered; end to end goes on at once on NM's own understanding, its defaults standing as assumptions. A message sent without steps
waits as before (AN.37). Offline: scripted models; the words are invented."""
import json
import time

import pytest

from nm.core_engine import questions, research, steps
from nm.core_engine.conversation import asking_of, chat_matter_id, save_asking, shown_of, stored_chat
from tests.test_core_answer_sections import Scripted, scripted_answers
from tests.test_core_served import OWNER, served  # noqa: F401 - pytest fixture
from tests.test_nm_asks_in_the_middle_of_a_turn import Desk, proposal, proposer

SENT = {"message": "Inspect this reported account.", "turn_id": "turn-1", "steps": "interactive"}
CHAT = stored_chat(OWNER, None, "turn-1")


def go(served, choice, disputes=None):
    return served.client.post("/api/turn/go", json={"chat_id": CHAT, "turn_id": "turn-1", "choice": choice,
                                                    **({"disputes": disputes} if disputes else {})})


def answer(served, given):
    return served.client.post("/api/turn/answers", json={"chat_id": CHAT, "turn_id": "turn-1", "answers": given})


def stop(served):
    return served.client.get(f"/api/chats/{CHAT}").json()["pending"]["stopped"]


def researched_with_a_question(served, scripted):
    """A matter of two disputes, researched step by step; NM asks one question, about the second dispute."""
    scripted_answers(served, scripted)
    served.app.propose_questions = proposer(proposal(depends=["D2"]))
    assert served.client.post("/api/turn", json=SENT).json()["detail"]["code"] == "waiting"
    assert go(served, "next").json()["detail"]["code"] == "waiting"
    card = stop(served)["waiting"]
    assert card["after"] == "researched" and [q["question"] for q in card["questions"]] == ["Whom do you act for?"]
    assert card["questions"][0]["answer"] is None


def written_for(scripted, dispute):
    return scripted.payloads("core_response_writer", dispute)


def test_a_question_shown_at_a_stop_is_answered_there_and_the_writing_reads_the_answer(served):
    scripted = Scripted()
    researched_with_a_question(served, scripted)
    taken = answer(served, {"q1": {"chosen": ["The seller"]}})
    assert taken.status_code == 409 and taken.json()["detail"]["heard"]["taken"] == "answer"
    assert stop(served)["waiting"]["questions"][0]["answer"] == {"chosen": ["The seller"], "other": ""}
    written = go(served, "next")
    assert written.json()["detail"]["code"] == "waiting" and stop(served)["waiting"]["after"] == "written"
    assert written_for(scripted, "D1") and written_for(scripted, "D2")
    assert "The seller" in json.dumps(written_for(scripted, "D2"), ensure_ascii=False)


def test_the_writing_a_question_touches_stops_for_the_answer_and_goes_on_by_itself_once_it_is_given(served):
    scripted = Scripted()
    researched_with_a_question(served, scripted)
    asked = go(served, "next")
    assert asked.json()["detail"]["code"] == "waiting" and stop(served)["waiting"]["after"] == steps.ASKED
    assert written_for(scripted, "D1") and not written_for(scripted, "D2"), "no default: the touched dispute waits"
    card = stop(served)["waiting"]
    assert [g["choice"] for g in card["gos"]] == ["end_to_end", "done"]
    assert go(served, "next").json()["detail"]["code"] == "not_offered", "only an answer, end to end or done"
    resumed = answer(served, {"q1": {"other": "For the seller, through his attorney."}})
    assert resumed.json()["detail"]["code"] == "waiting" and stop(served)["waiting"]["after"] == "written"
    assert "through his attorney" in json.dumps(written_for(scripted, "D2"), ensure_ascii=False)
    assert len(written_for(scripted, "D1")) == 1, "the first analysis is not written again"


def test_end_to_end_goes_on_at_once_on_nms_own_understanding(served, monkeypatch):
    monkeypatch.setattr(questions, "WAIT", 30.0)  # were it to wait, this test would take half a minute
    scripted_answers(served, Scripted())
    served.app.propose_questions = proposer(proposal(depends=["D2"]))
    assert served.client.post("/api/turn", json=SENT).json()["detail"]["code"] == "waiting"
    began = time.monotonic()
    whole = go(served, "end_to_end")
    assert whole.status_code == 200 and time.monotonic() - began < 20
    row = served.client.get(f"/api/chats/{CHAT}").json()["turns"][0]
    assert row["committed"] is True


def test_an_answer_code_cannot_take_is_refused_and_nothing_is_kept(served):
    researched_with_a_question(served, Scripted())
    refused = answer(served, {"q9": {"chosen": ["The seller"]}})
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "answer_refused"
    assert stop(served)["waiting"]["questions"][0]["answer"] is None


def test_codes_question_during_research_ends_the_step_and_it_resumes_once_answered(tmp_path, monkeypatch):
    """D154: code's question (which Act a name means, D87) ends the research step; answered, the step goes on from its saved work."""
    from nm.shared.store_file_store import FileMatterStore
    from tests.test_core_answer_sections import through_turns
    from tests.test_core_turn import run
    store = FileMatterStore(tmp_path, key="k" * 64)
    question = research.named_question({"act": "The Rent Act", "work_ids": ["w1"], "acts": ["UNION OF INDIA_1_ONE",
                                                                                            "TELANGANA_2_TWO"],
                                        "titles": ["One", "Two"]}, {"id": "D1", "name": "Possession"})
    real, got = research.retrieve_parts, []

    def retrieve_parts(*args, settle=None, **kwargs):
        got.extend(settle([question]))
        return real(*args, settle=settle, **kwargs)
    monkeypatch.setattr(research, "retrieve_parts", retrieve_parts)
    model = through_turns(Scripted())
    from nm.core_engine.conversation import ConversationRefused
    with pytest.raises(ConversationRefused):
        run(store, model, go=steps.first(), propose=lambda *args: [], desk=Desk())
    understood = shown_of(store.load(chat_matter_id("owner", stored_chat("owner", None, "t1"))))
    with pytest.raises(ConversationRefused) as stopped:
        run(store, model, go=steps.given(understood["go"], "next", held=understood), propose=lambda *args: [], desk=Desk())
    assert stopped.value.code == "waiting"
    matter = store.load(chat_matter_id("owner", stored_chat("owner", None, "t1")))
    record = shown_of(matter)
    assert steps.waiting_of(record) == steps.ASKED and record["steps"]["parts"] == {}, "the research waits for the answer"
    asked = asking_of(matter, "t1")["state"]
    window = questions.Asking(asked["questions"])
    window.start()
    window.receive({"q1": {"chosen": ["Two (Telangana)"]}})
    save_asking(store, matter, "t1", window.state())
    with pytest.raises(ConversationRefused) as again:
        run(store, model, go={**record["go"], "waiting": None}, propose=lambda *args: [], desk=Desk())
    assert again.value.code == "waiting"
    resumed = shown_of(store.load(chat_matter_id("owner", stored_chat("owner", None, "t1"))))
    assert steps.waiting_of(resumed) == "researched" and set(resumed["steps"]["parts"]) == {"D1", "D2"}
    assert got and got[-1][1]["chosen"] == ["Two (Telangana)"], "the research went on with the advocate's answer"
