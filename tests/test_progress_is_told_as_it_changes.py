"""The server tells the page (plan AN.48, piece 48f5; owner decision D167): /api/turn-events streams the words /api/turn-progress
gives, as server-sent events, while the advocate's own step works - each change at once, the time so far every few seconds - and
ends once the turn has finished or stopped, or stays unknown; a page not signed in is refused. Offline: scripted models; the words
are invented."""
import json
import threading

from fastapi.testclient import TestClient

from nm.app import api
from nm.app.main import create_app
from tests.test_a_message_while_a_matter_waits import SENT
from tests.test_core_answer_sections import Scripted, scripted_answers
from tests.test_core_served import OWNER, served  # noqa: F401 - pytest fixture
from tests.test_steps_run_as_jobs import Held


def told(response):
    """The events the stream sent, in order, until it ended. (The test client hands a stream over once it has ended; that it
    arrives as it is sent is the stream drill's to show, against a real server: development_environment/developer_tooling.)"""
    return [json.loads(line[len("data: "):]) for line in response.iter_lines() if line.startswith("data: ")]


def test_a_step_at_work_is_told_as_it_changes_and_the_stream_ends_with_its_last_word(served):
    scripted_answers(served, Scripted())
    held = Held(served)
    served.app.step_jobs.wait_seconds = 0.2
    assert served.client.post("/api/turn", json=SENT).status_code == 202
    assert held.entered.wait(10)
    letting_go = threading.Timer(1.5, held.go.set)  # the step goes on while the stream is told
    letting_go.start()
    with served.client.stream("GET", "/api/turn-events", params={"turn_id": "turn-1"}) as response:
        assert response.status_code == 200 and response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["x-accel-buffering"] == "no" and response.headers["cache-control"] == "no-store"
        events = told(response)
    letting_go.join()
    assert served.app.step_jobs.of(OWNER, "turn-1").exception(timeout=5).detail["code"] == "waiting", \
        "the step finished as it would have, not held up by the stream"
    assert events[0]["state"] == "working" and events[0]["label"], "told at once what the step is doing"
    assert len(events) >= 2 and events[-1]["state"] == "stopped", "the last word: the step stopped for the go-ahead"
    assert all(event["state"] == "working" for event in events[:-1])
    assert events[-1] == {**served.client.get("/api/turn-progress", params={"turn_id": "turn-1"}).json(),
                          "elapsed_seconds": events[-1]["elapsed_seconds"], "steps": events[-1]["steps"]}, \
        "the same words the page would have asked for"


def test_a_turn_not_known_ends_its_stream_and_a_page_not_signed_in_is_refused(served, monkeypatch):
    monkeypatch.setattr(api, "_EVENTS_UNKNOWN", 0.3)
    with served.client.stream("GET", "/api/turn-events", params={"turn_id": "turn-never-sent"}) as response:
        events = told(response)
    assert events and {event["state"] for event in events} == {"unknown"}
    stranger = TestClient(create_app(served.app))
    assert stranger.get("/api/turn-events", params={"turn_id": "turn-1"}).status_code == 401
    stranger.close()
