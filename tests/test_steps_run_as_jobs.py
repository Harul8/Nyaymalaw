"""Steps as jobs (plan AN.48, piece 48f1; owner decision D167): every route that runs a step hands it to the server's own step
threads and waits for it a short while. A step done by then answers exactly as before; one still working answers that it is
working (202) and goes on, the server serving pages meanwhile, and what it answers - the same answer or refusal its request would
have had - is read from /api/turn/outcome, by its own advocate only. Offline: scripted models; the words are invented."""
import contextvars
import threading

import pytest

from nm.app.step_jobs import WAIT_SECONDS, StepJobs, wait_from
from nm.shared.model_port import ProviderUnavailable
from tests.test_a_message_while_a_matter_waits import SENT
from tests.test_core_answer_sections import Scripted, scripted_answers
from tests.test_core_served import OTHER, OWNER, served  # noqa: F401 - pytest fixture


class Held:
    """The scripted model held at its first call until the test lets it go: the step still working when its request's wait ends.
    fail: what every call raises once let go."""

    def __init__(self, served, fail=None):
        self.entered, self.go, self.fail = threading.Event(), threading.Event(), fail
        first = served.model.structured

        def structured(prompt, schema, tier, **kwargs):
            self.entered.set()
            assert self.go.wait(30), "the test lets the step go"
            if self.fail is not None:
                raise self.fail
            return first(prompt, schema, tier, **kwargs)
        served.model.structured = structured


def outcome(served, turn_id="turn-1", client=None):
    return (client or served.client).get("/api/turn/outcome", params={"turn_id": turn_id})


def without_ids(reply):
    detail = reply.json()["detail"]
    return {key: value for key, value in detail.items() if key not in ("turn_id", "chat_id")} if isinstance(detail, dict) else detail


def test_a_step_still_working_answers_working_goes_on_and_its_answer_is_read_once_done(served):
    scripted_answers(served, Scripted())
    held = Held(served)
    served.app.step_jobs.wait_seconds = 0.2
    reply = served.client.post("/api/turn", json=SENT)
    assert reply.status_code == 202 and reply.json()["working"] is True and reply.json()["turn_id"] == "turn-1"
    assert held.entered.wait(10)
    # The step's thread is not one that serves pages: the server answers meanwhile.
    assert served.client.get("/api/turn-progress", params={"turn_id": "turn-1"}).json()["state"] == "working"
    assert outcome(served).status_code == 202 and outcome(served).json()["working"] is True
    held.go.set()
    served.app.step_jobs.of(OWNER, "turn-1").exception(timeout=30)
    later = outcome(served)
    assert later.status_code == 409 and later.json()["detail"]["code"] == "waiting", "the step stopped for the go-ahead"
    # Exactly what the request answers where its step is done within the wait.
    served.app.step_jobs.wait_seconds = WAIT_SECONDS
    within = served.client.post("/api/turn", json={**SENT, "turn_id": "turn-2"})
    assert within.status_code == later.status_code and without_ids(within) == without_ids(later)
    assert outcome(served, "turn-2").json() == within.json(), "and its outcome is held the same"


def test_a_refusal_after_the_step_went_on_is_the_refusal_its_request_would_have_had(served):
    scripted_answers(served, Scripted())
    held = Held(served, fail=ProviderUnavailable("The synthetic service is not answering."))
    served.app.step_jobs.wait_seconds = 0.2
    assert served.client.post("/api/turn", json=SENT).status_code == 202
    held.go.set()
    served.app.step_jobs.of(OWNER, "turn-1").exception(timeout=30)
    later = outcome(served)
    served.app.step_jobs.wait_seconds = WAIT_SECONDS
    within = served.client.post("/api/turn", json={**SENT, "turn_id": "turn-2"})
    assert later.status_code == within.status_code >= 400
    assert without_ids(later) == without_ids(within)


def test_what_a_step_answered_is_read_by_its_own_advocate_only(served):
    scripted_answers(served, Scripted())
    assert served.client.post("/api/turn", json=SENT).status_code == 409
    other = served.login(OTHER)
    refused = outcome(served, client=other)
    assert refused.status_code == 404 and refused.json()["detail"]["code"] == "no_step"
    assert outcome(served, "turn-never-sent").status_code == 404


def test_the_step_threads_carry_a_step_s_context_and_what_it_raised_and_keep_what_it_answered_a_while():
    clock = [0.0]
    jobs = StepJobs(wait_seconds=5, keep_seconds=10, clock=lambda: clock[0])
    marked = contextvars.ContextVar("marked", default=None)
    marked.set("the request's own")
    assert jobs.answered(jobs.start("a", "t1", marked.get)) == (True, "the request's own")

    def timed_out():
        raise TimeoutError("the step's own timeout")
    with pytest.raises(TimeoutError, match="the step's own timeout"):
        jobs.answered(jobs.start("a", "t2", timed_out))  # done, not still working
    let_go = threading.Event()
    slow = jobs.start("a", "t3", lambda: let_go.wait(5) and "late")
    jobs.wait_seconds = 0.05
    assert jobs.answered(slow) == (False, None)
    let_go.set()
    assert slow.result(5) == "late" and jobs.of("a", "t3") is slow and jobs.of("b", "t3") is None
    again = jobs.start("a", "t3", lambda: "again")
    assert again.result(5) == "again" and jobs.of("a", "t3") is again, "a later step of the turn takes its place"
    still = threading.Event()
    working = jobs.start("a", "t4", lambda: still.wait(5) and "the working step's")
    second = jobs.start("a", "t4", lambda: "a second request's")
    assert second.result(5) == "a second request's" and jobs.of("a", "t4") is working, "while one works, the turn answers its"
    still.set()
    assert working.result(5) == "the working step's"
    clock[0] = 11.0
    assert jobs.of("a", "t1") is None and jobs.of("a", "t3") is None, "kept a while after it is done, then let go"
    assert [wait_from(value) for value in ("5", "0", "60", "61", "-1", "soon", None)] == [5, 0, 60, 20, 20, 20, 20]


def test_a_step_that_goes_on_after_its_request_is_in_flight_for_the_supervisor_until_it_ends(tmp_path):
    """The server following the code on disk restarts onto new code only once nothing is in flight (main.py): a step that goes on
    after its request has answered is counted, so a code change never restarts the server in the middle of a step."""
    from nm.app import main

    async def app(scope, receive, send):
        return None
    counter = main._InFlight(app, tmp_path / "count")
    jobs = StepJobs(wait_seconds=0.05)
    jobs.hold = counter.hold
    let_go = threading.Event()
    step = jobs.start("a", "t1", lambda: let_go.wait(5))
    assert jobs.answered(step) == (False, None)
    assert (tmp_path / "count").read_text() == "1", "in flight while it works"
    let_go.set()
    step.result(5)
    for _ in range(100):
        if (tmp_path / "count").read_text() == "0":
            break
        threading.Event().wait(0.02)
    assert (tmp_path / "count").read_text() == "0", "and no longer once it has ended"

    def failing(step):
        raise OSError("the count could not be written")
    jobs.hold = failing
    assert jobs.answered(jobs.start("a", "t2", lambda: "answered")) == (True, "answered"), "a step never fails for the count"
