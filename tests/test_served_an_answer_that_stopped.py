"""Plan AN.41 (D65-D73) and AN.42 (D77-D79) through the HTTP API: the history lists a conversation from its first message; a
stopped answer waits for Continue or Discard; after a restart the progress reads the saved conversation; Stop and Steer reach only
an answer being worked on; what waits to be sent is kept with the conversation; the advocate counts as active while NM works.
Offline: the scripted served application; not browser QA."""
import threading

from nm.app import api
from nm.core_engine.conversation import stored_chat
from tests.test_core_answer_sections import Scripted, scripted_answers
from tests.test_core_served import OWNER, served  # noqa: F401 - pytest fixture

SENT = {"message": "Inspect this reported account.", "turn_id": "turn-1"}


def stopped_at_the_overview(served):
    scripted_answers(served, Scripted(refuse={"core_response_overview"}))
    reply = served.client.post("/api/turn", json=SENT)
    assert reply.status_code == 403 and reply.json()["detail"]["kept"] is True
    served.app.turn_progress.end(OWNER, "turn-1", "stopped")
    return stored_chat(OWNER, None, "turn-1")


def test_the_history_lists_a_conversation_from_its_first_message(served):
    chat_id = stopped_at_the_overview(served)
    listed = served.client.get("/api/work").json()
    assert [(chat["chat_id"], chat["preview"], chat["turn_count"]) for chat in listed["chats"]] == [
        (chat_id, SENT["message"], 1)]


def test_continue_finishes_the_answer_where_it_stopped(served):
    chat_id = stopped_at_the_overview(served)
    scripted = Scripted()
    scripted_answers(served, scripted)
    reply = served.client.post("/api/turn/continue", json={"chat_id": chat_id, "turn_id": "turn-1"})
    assert reply.status_code == 200, reply.text
    assert reply.json()["committed"] == "committed"
    assert not scripted.payloads("core_response_writer"), "the sections finished are not written again"
    assert len(scripted.payloads("core_response_overview")) == 1
    reopened = served.client.get(f"/api/chats/{chat_id}").json()
    assert "pending" not in reopened and [turn["turn_id"] for turn in reopened["turns"]] == ["turn-1"]
    assert served.client.post("/api/turn/continue", json={"chat_id": chat_id, "turn_id": "turn-1"}).status_code == 404


def test_after_a_restart_the_progress_reads_the_saved_conversation(served):
    stopped_at_the_overview(served)
    served.app.turn_progress = type(served.app.turn_progress)()  # a new process knows no turn
    seen = served.client.get("/api/turn-progress?turn_id=turn-1").json()
    assert seen["state"] == "stopped" and seen["chat_id"] == stored_chat(OWNER, None, "turn-1")
    assert seen["stopped"]["code"] == "model_permission_required"
    assert served.client.get("/api/turn-progress?turn_id=turn-2").json()["state"] == "unknown"


def test_stop_and_steer_reach_only_an_answer_being_worked_on(served):
    stopped_at_the_overview(served)
    stop = served.client.post("/api/turn/stop", json={"turn_id": "turn-1"})
    assert stop.status_code == 409 and stop.json()["detail"]["code"] == "not_working"
    steer = served.client.post("/api/turn/steer", json={"turn_id": "turn-1", "message": "And the lease."})
    assert steer.status_code == 409 and steer.json()["detail"]["code"] == "finished"


def test_a_stop_pressed_while_nm_works_stops_it_after_the_step_in_progress(served):
    pressed = threading.Event()
    scripted = Scripted()
    scripted_answers(served, scripted)
    answering = served.model.structured

    def structured(prompt, schema, tier, **kwargs):
        if prompt.operation == "core_response_cross_check" and not pressed.is_set():
            assert served.client.post("/api/turn/stop", json={"turn_id": "turn-1"}).json() == {"state": "stopping"}
            pressed.set()
        return answering(prompt, schema, tier, **kwargs)
    served.model.structured = structured
    reply = served.client.post("/api/turn", json=SENT)
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "stopped" and reply.json()["detail"]["kept"]
    assert not scripted.payloads("core_response_overview")
    pending = served.client.get(f"/api/chats/{stored_chat(OWNER, None, 'turn-1')}").json()["pending"]
    assert pending["stopped"]["code"] == "stopped" and pending["stopped"]["by_itself"] is False


def test_what_waits_to_be_sent_is_kept_with_the_conversation(served):
    chat_id = stopped_at_the_overview(served)
    waiting = [{"text": "Also the second deed.", "documents": [{"document_ref": "doc_synthetic", "name": "deed.pdf"}]}]
    assert served.client.put(f"/api/chats/{chat_id}/queued", json={"queued": waiting}).json() == {"state": "saved"}
    assert served.client.get(f"/api/chats/{chat_id}").json()["queued"] == waiting
    # The answer saved: what waits stays, for the page to send.
    assert served.client.post("/api/turn/discard", json={"chat_id": chat_id, "turn_id": "turn-1"}).status_code == 200
    assert served.client.get(f"/api/chats/{chat_id}").json()["queued"] == waiting
    assert served.client.put(f"/api/chats/{chat_id}/queued", json={"queued": []}).status_code == 200
    assert "queued" not in served.client.get(f"/api/chats/{chat_id}").json()
    other = served.client.put("/api/chats/new_nothing/queued", json={"queued": waiting})
    assert other.status_code == 404


def test_the_advocate_counts_as_active_while_nm_works(served, monkeypatch):
    """D65: from Send until the answer is saved or stops, the server keeps the session active."""
    touched = []
    original = served.app.directory.touch_session
    monkeypatch.setattr(api, "_ACTIVE_EVERY", 0.01)
    monkeypatch.setattr(served.app.directory, "touch_session", lambda *args: touched.append(args) or original(*args))
    scripted_answers(served, Scripted())
    answering = served.model.structured

    def slow(prompt, schema, tier, **kwargs):
        threading.Event().wait(0.05)
        return answering(prompt, schema, tier, **kwargs)
    served.model.structured = slow
    assert served.client.post("/api/turn", json=SENT).status_code == 200
    assert touched, "the session was kept active while NM worked"
    count = len(touched)
    threading.Event().wait(0.1)
    assert len(touched) == count, "and no longer once it had finished"


def test_a_steer_sent_while_nm_works_goes_into_the_answer(served):
    """D79 through the HTTP API: Steer while the answer is worked on; the answer takes it in and is saved with it."""
    from nm.core_engine import turn
    from nm.core_engine.conversation import chat_matter_id
    scripted = Scripted()
    scripted_answers(served, scripted)
    answering, sent = served.model.structured, []

    def structured(prompt, schema, tier, **kwargs):
        if prompt.operation == "core_response_cross_check" and not sent:
            reply = served.client.post("/api/turn/steer", json={"turn_id": "turn-1", "message": "Weigh the later notice too."})
            sent.append(reply.json())
        return answering(prompt, schema, tier, **kwargs)
    served.model.structured = structured
    reply = served.client.post("/api/turn", json=SENT)
    assert reply.status_code == 200, reply.text
    assert sent == [{"state": "taken"}]
    rows = turn.saved_rows(served.store.load(chat_matter_id(OWNER, reply.json()["chat_id"])), OWNER)
    assert [steer["text"] for steer in rows[0]["steers"]] == ["Weigh the later notice too."]
    assert any("Weigh the later notice too." in str(payload) for payload in scripted.payloads("core_response_review"))


def test_the_progress_says_each_part_s_state_and_how_often_the_work_was_saved():
    from nm.app.turn_progress import TurnProgress
    progress = TurnProgress(clock=lambda: 100.0)
    progress.saved("a", "t", 0, "new_chat")
    progress.report("a", "t", "reviewing", {"part": "s1"})
    progress.report("a", "t", "revising", {"part": "s1", "corrections": 3})
    progress.report("a", "t", "writing", {"part": "o"})
    progress.report("a", "t", "writing", {"part": "<script>"})
    progress.saved("a", "t", 2, "new_chat")
    seen = progress.read("a", "t")
    assert seen["chat_id"] == "new_chat" and seen["saved"] == 2
    assert seen["parts"] == {"s1": {"state": "rewriting", "corrections": 3}, "o": {"state": "writing"}}
