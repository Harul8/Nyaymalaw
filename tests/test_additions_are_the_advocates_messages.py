"""What the advocate adds while a matter waits is kept as their own message (plan AN.48, piece 48h; owner decisions D159, D161, D162).

Numbered after their latest message and citable as theirs; the research made before stays as it is; information that is not critical
causes nothing at once, and the analyses already written are checked against it once - in the next run that writes, or at Done -
each reviewed again from its own words; critical information causes that check at once. An answer to NM's question given at a stop
is the advocate's message too. Offline: scripted models; the words are invented."""
import json

from nm.core_engine import steps, turn, understanding
from nm.core_engine.conversation import TurnContext, chat_matter_id, shown_of, stored_chat
from tests.test_a_message_while_a_matter_waits import Reader, judged, reading
from tests.test_core_answer_sections import Scripted, scripted_answers
from tests.test_core_served import OWNER, served  # noqa: F401 - pytest fixture
from tests.test_nm_asks_in_the_middle_of_a_turn import proposal, proposer

SENT = {"message": "Inspect this reported account.", "turn_id": "turn-1", "steps": "interactive"}
CHAT = stored_chat(OWNER, None, "turn-1")
ADDED = "The notice was served on 3 March."


def go(served, choice, disputes=None):
    return served.client.post("/api/turn/go", json={"chat_id": CHAT, "turn_id": "turn-1", "choice": choice,
                                                    **({"disputes": disputes} if disputes else {})})


def say(served, words):
    return served.client.post("/api/turn/message", json={"chat_id": CHAT, "turn_id": "turn-1", "message": words})


def held(served):
    return shown_of(served.store.load(chat_matter_id(OWNER, CHAT)))


def reviews_reading(scripted, words):
    return [payload for payload in scripted.payloads("core_response_review") if words in json.dumps(payload, ensure_ascii=False)]


def written_one(served, scripted):
    """A matter of two disputes: the first researched and its analysis written."""
    scripted_answers(served, scripted)
    assert served.client.post("/api/turn", json=SENT).json()["detail"]["code"] == "waiting"
    assert go(served, "research", ["D1"]).json()["detail"]["code"] == "waiting"
    assert go(served, "write", ["D1"]).json()["detail"]["code"] == "waiting"


def test_information_is_kept_as_the_advocates_message_after_the_latest_and_the_research_stays(served):
    scripted = Scripted()
    written_one(served, scripted)
    parts_before = held(served)["steps"]["parts"]
    reading(served, Reader(judged(kind="information", disputes=["D2"], critical=False,
                                  said="Taken as new information about the notice; kept for what is still to come.")))
    calls_before = len(served.model.calls)
    reply = say(served, ADDED)
    assert reply.status_code == 409 and reply.json()["detail"]["heard"]["taken"] == "information"
    record = held(served)
    assert [entry["text"] for entry in record["added"]] == [ADDED] and record["steers"] == []
    assert record["steps"]["parts"] == parts_before, "the research made before stays as it is"
    assert record["go"]["recheck"] is True, "the analysis written before is to be checked against it"
    assert len(served.model.calls) == calls_before + 0, "nothing is redone at once"
    matter = served.store.load(chat_matter_id(OWNER, CHAT))
    context = TurnContext(matter, CHAT, "turn-1", record["message"], (), documents=tuple(record["documents"]),
                          added=tuple(record["added"])).payload()
    aliases = understanding.context_aliases(context)
    assert aliases["M2"] == "turn-1:added1" and context["added"][0]["text"] == ADDED, "numbered after the latest, citable"


def test_the_next_run_that_writes_checks_the_analysis_written_before_against_it(served):
    scripted = Scripted()
    written_one(served, scripted)
    reading(served, Reader(judged(kind="information", disputes=["D2"], critical=False, said="Kept.")))
    say(served, ADDED)
    assert go(served, "research", ["D2"]).json()["detail"]["code"] == "waiting"
    assert held(served)["go"]["recheck"] is True, "research does not check the analyses"
    assert go(served, "write", ["D2"]).json()["detail"]["code"] == "waiting"
    record = held(served)
    assert sorted(s["dispute_id"] for s in record["steps"]["answered"]["sections"]) == ["D1", "D2"], "nothing written is lost"
    assert reviews_reading(scripted, ADDED), "the analysis written before is reviewed again with the advocate's words"
    assert "recheck" not in record["go"], "checked once"


def test_critical_information_checks_the_analyses_written_at_once(served):
    scripted = Scripted()
    written_one(served, scripted)
    reading(served, Reader(judged(kind="information", disputes=["D1"], critical=True, said="Critical: rechecking.")))
    reply = say(served, ADDED)
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting"
    record = held(served)
    assert steps.waiting_of(record) == "written" and [entry["text"] for entry in record["added"]] == [ADDED]
    assert reviews_reading(scripted, ADDED) and "recheck" not in record["go"]


def test_done_after_an_addition_saves_it_with_the_answer_as_the_advocates_message(served):
    scripted = Scripted()
    written_one(served, scripted)
    reading(served, Reader(judged(kind="information", disputes=["D1"], critical=False, said="Kept.")))
    say(served, ADDED)
    saved = go(served, "done")
    assert saved.status_code == 200, saved.text
    matter = served.store.load(chat_matter_id(OWNER, CHAT))
    row = turn.saved_rows(matter, OWNER)[0]
    assert [entry["text"] for entry in row["added"]] == [ADDED]
    assert reviews_reading(scripted, ADDED), "checked once at Done"
    later = TurnContext(matter, CHAT, "turn-2", "And now?", tuple(turn.saved_rows(matter, OWNER))).payload()
    assert any(entry["text"] == ADDED and entry["source_id"] == "turn-1:added1" for entry in later["conversation"]), (
        "a later turn reads it as the advocate's message too")


def test_an_answer_given_at_a_stop_is_the_advocates_message_too(served):
    scripted_answers(served, Scripted())
    served.app.propose_questions = proposer(proposal(depends=["D2"]))
    served.client.post("/api/turn", json=SENT)
    go(served, "next")
    served.client.post("/api/turn/answers", json={"chat_id": CHAT, "turn_id": "turn-1", "answers": {"q1": {"chosen": ["The seller"]}}})
    assert [entry["text"] for entry in held(served)["added"]] == ['Answer to NM\'s question "Whom do you act for?": The seller']
