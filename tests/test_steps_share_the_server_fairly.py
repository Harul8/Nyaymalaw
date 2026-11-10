"""Limits and a queue (plan AN.48, piece 48f2; owner decision D167): at most AT_ONCE steps work at once on the server and PER_ADVOCATE
for one advocate; the others wait, first come first served - an advocate at their own limit passed over - each told its place; a
step stopped while it waits is taken out, nothing of it run or charged; what is added to it goes as the next message. Offline:
scripted models and stand-in steps; the words are invented."""
import threading

import pytest

from nm.app.step_jobs import AT_ONCE, PER_ADVOCATE, StepCancelled, StepJobs, count_from
from nm.core_engine.conversation import chat_matter_id, stored_chat
from tests.test_a_message_while_a_matter_waits import SENT
from tests.test_core_answer_sections import Scripted, scripted_answers
from tests.test_core_served import OWNER, served  # noqa: F401 - pytest fixture
from tests.test_steps_run_as_jobs import Held, outcome


def until(test, seconds=10):
    done = threading.Event()
    for _ in range(int(seconds / 0.02)):
        if test():
            return True
        done.wait(0.02)
    return test()


def held_step(gates, name):
    gate = gates.setdefault(name, threading.Event())
    return lambda: gate.wait(10) and name


def test_so_many_steps_work_at_once_and_so_many_for_one_advocate_the_rest_first_come_first_served():
    placed, gates = [], {}
    jobs = StepJobs(wait_seconds=0.05, at_once=2, per_advocate=1)
    jobs.placed = lambda advocate, turn, ahead: placed.append((advocate, turn, ahead))
    a1 = jobs.start("a", "t1", held_step(gates, "a1"))
    a2 = jobs.start("a", "t2", held_step(gates, "a2"))  # a is at its own limit
    b1 = jobs.start("b", "t3", held_step(gates, "b1"))
    c1 = jobs.start("c", "t4", held_step(gates, "c1"))  # two at work
    assert until(lambda: a1.running() and b1.running())
    assert jobs.waiting("a", "t2") and jobs.waiting("c", "t4") and placed[-2:] == [("a", "t2", 0), ("c", "t4", 1)]
    gates["b1"].set()
    assert b1.result(5) == "b1"
    # b's place is free; a is still at its own limit, so c begins before a's second.
    assert until(lambda: c1.running() and placed[-1] == ("a", "t2", 0)) and jobs.waiting("a", "t2")
    gates["a1"].set()
    assert a1.result(5) == "a1" and until(lambda: a2.running())
    for name in ("a2", "c1"):
        gates[name].set()
    assert a2.result(5) == "a2" and c1.result(5) == "c1"
    assert (AT_ONCE, PER_ADVOCATE) == (3, 2)
    assert [count_from(value, 3) for value in ("1", " 64 ", "0", "65", "two", None)] == [1, 64, 3, 3, 3, 3]


def test_a_step_stopped_while_it_waits_is_taken_out_unrun_and_the_others_move_up(tmp_path):
    from nm.app import main

    async def app(scope, receive, send):
        return None
    counter = main._InFlight(app, tmp_path / "count")
    placed, gates, ran = [], {}, []
    jobs = StepJobs(wait_seconds=0.05, at_once=1, per_advocate=1)
    jobs.placed = lambda advocate, turn, ahead: placed.append((advocate, turn, ahead))
    jobs.hold = counter.hold
    first = jobs.start("a", "t1", held_step(gates, "first"))
    second = jobs.start("b", "t2", lambda: ran.append("second"))
    third = jobs.start("c", "t3", lambda: "third")
    assert (tmp_path / "count").read_text() == "3", "a step waiting is in flight too"
    assert jobs.cancel("b", "t2") and not jobs.cancel("a", "t1") and not jobs.cancel("b", "t2"), "only a step not begun"
    with pytest.raises(StepCancelled):
        second.result(1)
    assert placed[-1] == ("c", "t3", 0) and (tmp_path / "count").read_text() == "2"
    gates["first"].set()
    assert third.result(5) == "third" and first.result(5) == "first" and ran == [], "the stopped step never ran"
    assert until(lambda: (tmp_path / "count").read_text() == "0")
    # Stop as a step begins, before its run could hear it, is kept for the run to take as it registers.
    begun = threading.Event()
    late = jobs.start("d", "t4", lambda: begun.wait(5))
    assert jobs.ask_stop("d", "t4") and jobs.stop_asked("d", "t4") and not jobs.stop_asked("d", "t9")
    begun.set()
    late.result(5)
    assert not jobs.ask_stop("d", "t4"), "nothing to stop once it is done"


def test_a_step_waiting_for_a_place_says_so_and_stopped_there_is_refused_unsaved_and_uncharged(served):
    scripted_answers(served, Scripted())
    held = Held(served)
    served.app.step_jobs.wait_seconds, served.app.step_jobs.at_once = 0.2, 1
    assert served.client.post("/api/turn", json=SENT).status_code == 202
    assert held.entered.wait(10)
    calls = len(served.model.calls)
    for turn in ("turn-2", "turn-3"):
        reply = served.client.post("/api/turn", json={**SENT, "turn_id": turn})
        assert reply.status_code == 202 and reply.json()["working"] is True
    seen = lambda turn: served.client.get("/api/turn-progress", params={"turn_id": turn}).json()  # noqa: E731
    assert seen("turn-2")["state"] == "working" and seen("turn-2")["label"] == "Waiting for NM to be free - yours is next"
    assert seen("turn-3")["label"] == "Waiting for NM to be free - 1 ahead of yours"
    # What is added to a step not yet begun goes as the next message.
    steer = served.client.post("/api/turn/steer", json={"turn_id": "turn-2", "message": "Also consider the notice."})
    assert steer.status_code == 409 and steer.json()["detail"]["code"] == "not_begun"
    assert served.client.post("/api/turn/stop", json={"turn_id": "turn-2"}).json() == {"state": "stopping"}
    stopped = outcome(served, "turn-2")
    assert stopped.status_code == 409
    detail = stopped.json()["detail"]
    assert detail["code"] == "stopped_before_start" and detail["committed"] == "not_committed" and "kept" not in detail
    assert seen("turn-2")["state"] == "stopped" and seen("turn-3")["label"] == "Waiting for NM to be free - yours is next"
    held.go.set()
    for turn in ("turn-1", "turn-3"):
        served.app.step_jobs.of(OWNER, turn).exception(timeout=30)
        assert outcome(served, turn).json()["detail"]["code"] == "waiting", "each works as it would have alone"
    assert served.store.load(chat_matter_id(OWNER, stored_chat(OWNER, None, "turn-2"))) is None, "nothing of it was saved"
    assert len(served.model.calls) > calls


def test_a_go_ahead_that_waited_for_a_place_is_not_refused_by_its_own_waiting(served):
    """A step that waits for a place has progress saying it is working from then on; the go-ahead's own check against a second
    run of its turn must not count that step itself (found building 48f3, 10 Nov 2026: only messages sent had been tried waiting)."""
    from nm.core_engine import steps as stepwise
    from nm.core_engine.conversation import shown_of
    scripted_answers(served, Scripted())
    waiting = served.client.post("/api/turn", json={**SENT, "turn_id": "turn-b"})
    assert waiting.json()["detail"]["code"] == "waiting"
    chat_b = waiting.json()["detail"]["chat_id"] or stored_chat(OWNER, None, "turn-b")
    held = Held(served)
    served.app.step_jobs.wait_seconds, served.app.step_jobs.at_once = 0.2, 1
    assert served.client.post("/api/turn", json=SENT).status_code == 202
    assert held.entered.wait(10)
    go = served.client.post("/api/turn/go", json={"chat_id": chat_b, "turn_id": "turn-b", "choice": "research"})
    assert go.status_code == 202
    progress = served.client.get("/api/turn-progress", params={"turn_id": "turn-b"}).json()
    assert progress["label"] == "Waiting for NM to be free - yours is next"
    held.go.set()
    for turn in ("turn-1", "turn-b"):
        served.app.step_jobs.of(OWNER, turn).exception(timeout=30)
    later = outcome(served, "turn-b")
    assert later.status_code == 409 and later.json()["detail"]["code"] == "waiting", later.json()
    assert stepwise.waiting_of(shown_of(served.store.load(chat_matter_id(OWNER, chat_b)))) == "researched"


def test_a_step_that_waited_then_was_refused_as_it_began_says_working_no_longer(served):
    """A go-ahead the matter no longer offers by the time its place is free is refused as it begins, before its run says anything:
    its progress, which said it was waiting, ends with it - the turn is not left looking busy (found building 48f3, 10 Nov 2026)."""
    from nm.core_engine.conversation import shown_of
    scripted_answers(served, Scripted())
    waiting = served.client.post("/api/turn", json={**SENT, "turn_id": "turn-b"})
    chat_b = waiting.json()["detail"]["chat_id"] or stored_chat(OWNER, None, "turn-b")
    held = Held(served)
    served.app.step_jobs.wait_seconds, served.app.step_jobs.at_once = 0.2, 1
    assert served.client.post("/api/turn", json=SENT).status_code == 202
    assert held.entered.wait(10)
    unready = served.client.post("/api/turn/go", json={"chat_id": chat_b, "turn_id": "turn-b", "choice": "write",
                                                       "disputes": ["D1"]})  # D1 is not researched yet
    assert unready.status_code == 202
    held.go.set()
    for turn in ("turn-1", "turn-b"):
        served.app.step_jobs.of(OWNER, turn).exception(timeout=30)
    refused = outcome(served, "turn-b")
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "not_offered"
    assert served.client.get("/api/turn-progress", params={"turn_id": "turn-b"}).json()["state"] != "working"
    assert not served.app.turn_running(OWNER, "turn-b")
    served.app.step_jobs.wait_seconds = 20
    research = served.client.post("/api/turn/go", json={"chat_id": chat_b, "turn_id": "turn-b", "choice": "research"})
    assert research.status_code == 409 and research.json()["detail"]["code"] == "waiting", "and it goes on when asked"
    assert shown_of(served.store.load(chat_matter_id(OWNER, chat_b)))["steps"]["parts"]
