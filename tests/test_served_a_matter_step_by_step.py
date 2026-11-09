"""Plan AN.48, piece 48a (D134-D135, D147, D153, D164) through the HTTP API: a message sent step by step stops after the
understanding with its stop card; Go ahead runs the next step and stops again; Done saves the answer; End to end runs the rest;
Done before any analysis saves the matter as it stands; a go-ahead the matter does not wait for is refused; a waiting matter is
never continued by the page by itself; the history says where it waits; a message sent without steps runs end to end as before.
Offline: the scripted served application; not browser QA."""
from nm.core_engine.conversation import stored_chat
from tests.test_core_answer_sections import Scripted, scripted_answers
from tests.test_core_served import OWNER, served  # noqa: F401 - pytest fixture

SENT = {"message": "Inspect this reported account.", "turn_id": "turn-1", "steps": "interactive"}
CHAT = stored_chat(OWNER, None, "turn-1")


def waiting(served):
    return served.client.get(f"/api/chats/{CHAT}").json()["pending"]["stopped"]


def go(served, choice):
    return served.client.post("/api/turn/go", json={"chat_id": CHAT, "turn_id": "turn-1", "choice": choice})


def test_a_message_sent_step_by_step_stops_at_each_step_and_done_saves_the_answer(served):
    scripted = Scripted()
    scripted_answers(served, scripted)
    sent = served.client.post("/api/turn", json=SENT)
    assert sent.status_code == 409 and sent.json()["detail"]["code"] == "waiting" and sent.json()["detail"]["kept"] is True
    stop = waiting(served)
    assert stop["code"] == "waiting" and stop["by_itself"] is False, "a waiting matter is never continued by itself (D153)"
    assert stop["waiting"]["after"] == "understood" and [g["choice"] for g in stop["waiting"]["gos"]] == [
        "next", "end_to_end", "done"]
    listed = served.client.get("/api/work").json()["chats"]
    assert [chat.get("waiting") for chat in listed] == ["Waiting for you: research"]
    assert not scripted.payloads("core_response_writer")

    researched = go(served, "next")
    assert researched.status_code == 409 and researched.json()["detail"]["code"] == "waiting"
    assert waiting(served)["waiting"]["after"] == "researched" and not scripted.payloads("core_response_writer")

    written = go(served, "next")
    assert written.status_code == 409 and waiting(served)["waiting"]["after"] == "written"
    assert scripted.payloads("core_response_writer") and not scripted.payloads("core_response_cross_check")
    assert [g["choice"] for g in waiting(served)["waiting"]["gos"]] == ["next"]

    saved = go(served, "next")
    assert saved.status_code == 200, saved.text
    assert saved.json()["committed"] == "committed"
    reopened = served.client.get(f"/api/chats/{CHAT}").json()
    assert "pending" not in reopened and [turn["turn_id"] for turn in reopened["turns"]] == ["turn-1"]
    assert go(served, "next").json()["detail"]["code"] == "not_waiting"


def test_end_to_end_at_a_stop_runs_the_rest_and_done_before_an_analysis_saves_it_as_it_stands(served):
    scripted_answers(served, Scripted())
    assert served.client.post("/api/turn", json=SENT).status_code == 409
    assert go(served, "sideways").status_code == 422, "only the go-aheads a stop offers"
    whole = go(served, "end_to_end")
    assert whole.status_code == 200 and whole.json()["committed"] == "committed"

    other = {**SENT, "turn_id": "turn-2"}
    assert served.client.post("/api/turn", json=other).status_code == 409
    chat = stored_chat(OWNER, None, "turn-2")
    done = served.client.post("/api/turn/go", json={"chat_id": chat, "turn_id": "turn-2", "choice": "done"})
    assert done.status_code == 200, done.text
    assert done.json()["service_status"].startswith("You finished this matter here.")


def test_a_message_sent_without_steps_runs_end_to_end_as_before(served):
    scripted_answers(served, Scripted())
    reply = served.client.post("/api/turn", json={"message": SENT["message"], "turn_id": "turn-1"})
    assert reply.status_code == 200 and reply.json()["committed"] == "committed"
