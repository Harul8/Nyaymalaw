"""Plan AN.61 (61b, D309): a request at a stop for one specific thing about the matter - a question answered, a point looked up, a
dispute's analysis - authorises its deliverable and the work it needs. For the disputes it concerns NM researches each not yet
researched and writes its analysis, while the other disputes wait; a point no question of their research asks is researched as what
is new for that dispute (48i); the message joins the matter as the advocate's own (48h); code says what NM does. Code admits it only
for the matter's disputes still to be researched or written, and never at a guided stop. Offline: scripted models and search; the
words are invented - no claim about how the real model reads real messages; not browser QA."""
import json

from nm.core_engine import message_reader, steps
from tests.guided import intake
from tests.test_a_message_while_a_matter_waits import CHAT, SENT, Reader, held, judged, reading, say
from tests.test_core_answer_sections import Scripted, scripted_answers
from tests.test_core_served import served  # noqa: F401 - pytest fixture
from tests.test_research_only_what_is_new import NEW, phrased

ASKED = "What notice did the first dispute need, and was it given in time?"


def waiting(served, *, disputes=2, guided=False):
    """A matter at its first research stop (or, guided, at its first guided stop), its answering scripted."""
    scripted = Scripted()
    scripted_answers(served, scripted)
    served.model.disputes = disputes
    assert served.client.post("/api/turn", json=SENT).json()["detail"]["code"] == "waiting"
    if not guided:
        intake(served.client, CHAT)
    return scripted


def card(served):
    return served.client.get(f"/api/chats/{CHAT}").json()["pending"]["stopped"]["waiting"]


def wrote(scripted, dispute):
    return json.dumps(scripted.payloads("core_response_writer", dispute), ensure_ascii=False)


def test_a_specific_request_for_one_dispute_is_researched_and_written_while_the_other_waits(served):
    scripted = waiting(served)
    reading(served, Reader(judged(kind="go", choice="work", disputes=["D1"], said="You want the first dispute's notice answered.")))
    reply = say(served, ASKED)
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting", reply.text
    record = held(served)
    assert set(record["steps"]["parts"]) == {"D1"} and steps.waiting_of(record) == "written"
    assert [saved["dispute_id"] for saved in record["steps"]["answered"]["sections"]] == ["D1"]
    # The message joined the matter as the advocate's own, and the analysis was written with it before it.
    assert [entry["text"] for entry in record["added"]] == [ASKED]
    assert ASKED in wrote(scripted, "D1") and not scripted.payloads("core_response_writer", "D2")
    heard = record["go"]["heard"][-1]
    assert heard["text"] == ASKED and heard["taken"] == "go"
    assert heard["said"].startswith("Taken as a request for Dispute 1: NM researches Dispute 1 and writes its analysis; the other "
                                    "disputes wait for you.")
    assert [(item["id"], item["researched"], item["written"]) for item in card(served)["disputes"]] == [
        ("D1", True, True), ("D2", False, False)]


def test_a_point_no_question_asks_is_researched_as_what_is_new_for_that_dispute(served):
    scripted = waiting(served)
    phrased(served)
    before = [work["id"] for work in held(served)["steps"]["understood"]["plan"]["work"]]
    reading(served, Reader(judged(kind="go", choice="work", disputes=["D1"], new_questions=[NEW], said="")))
    reply = say(served, "Was the notice valid when it went only by email?")
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting", reply.text
    record = held(served)
    new, = [item for item in record["steps"]["understood"]["plan"]["work"] if item["id"] not in before]
    assert new["dispute"]["id"] == "D1" and new["question"] == NEW["question"]
    assert new["sources"][-1]["source_id"] == "turn-1:added1", "named by the message it came from, which joined the matter"
    assert "proposed" not in record["go"] and set(record["steps"]["parts"]) == {"D1"}
    assert NEW["question"] in wrote(scripted, "D1")
    assert record["go"]["heard"][-1]["said"].endswith(f"It researches what is new for Dispute 1: {NEW['question']}")


def test_work_is_admitted_only_for_disputes_still_to_be_researched_or_written(served):
    waiting(served)
    matter = held(served)
    for wrong in ({"disputes": []}, {"disputes": ["D9"]}, {"disputes": ["D1"], "choice": "work_all"}):
        judgement, why = message_reader.admitted({**judged(kind="go", choice="work"), **wrong}, matter)
        assert judgement is None and why, wrong
    judgement, why = message_reader.admitted(judged(kind="go", choice="work", disputes=["D2", "D1"]), matter)
    assert why is None and judgement["go"]["allowed"] == ["research", "write"] and judgement["go"]["disputes"] == ["D1", "D2"]
    assert judgement["joins"] is True and judgement["said"].startswith("Taken as a request for Dispute 1 and Dispute 2: NM "
                                                                       "researches Dispute 1 and Dispute 2 and writes their analyses.")
    # A dispute already written is not open to it, unless a point the request asks is new for that dispute (48i).
    reading(served, Reader(judged(kind="go", choice="work", disputes=["D1"])))
    assert say(served, ASKED).json()["detail"]["code"] == "waiting"
    matter = held(served)
    judgement, why = message_reader.admitted(judged(kind="go", choice="work", disputes=["D1"]), matter)
    assert judgement is None and "still to be researched or written" in why
    judgement, why = message_reader.admitted(judged(kind="go", choice="work", disputes=["D1"], new_questions=[NEW]), matter)
    assert why is None and judgement["go"]["allowed"] == ["research", "write"] and judgement["go"]["disputes"] == ["D1"]
    assert [entry["source"] for entry in judgement["go"]["proposed"]] == ["turn-1:added2"]
    # A new question for a dispute outside the request's scope is not taken with it.
    judgement, why = message_reader.admitted(judged(kind="go", choice="work", disputes=["D2"], new_questions=[NEW]), matter)
    assert why is None and judgement["go"]["disputes"] == ["D2"] and "proposed" not in judgement["go"]
    assert judgement["new_questions"] == []
    # Analysis only, for a dispute researched and not written.
    reading(served, Reader(judged(kind="go", choice="research", disputes=["D2"])))
    assert say(served, "Research the second one.").json()["detail"]["code"] == "waiting"
    judgement, why = message_reader.admitted(judged(kind="go", choice="work", disputes=["D2"]), held(served))
    assert why is None and judgement["go"]["allowed"] == ["write"]
    assert judgement["said"].startswith("Taken as a request for Dispute 2: NM writes its analysis.")


def test_work_is_not_taken_at_a_guided_stop(served):
    waiting(served, guided=True)
    matter = held(served)
    assert steps.waiting_of(matter) in steps.GUIDED
    judgement, why = message_reader.admitted(judged(kind="go", choice="work", disputes=["D1"]), matter)
    assert judgement is None and "not one this stop offers" in why


def test_a_specific_request_on_an_answer_written_as_a_whole_is_worked_to_the_end(served):
    scripted = waiting(served, disputes=1)
    assert card(served)["disputes"] == []
    reading(served, Reader(judged(kind="go", choice="work", disputes=[], said="")))
    reply = say(served, ASKED)
    assert reply.status_code == 200 and reply.json()["committed"] == "committed", reply.text
    assert ASKED in json.dumps(scripted.payloads("core_response_writer"), ensure_ascii=False)
