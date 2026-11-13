"""A Stop or Steer the page was told had not landed does not land later (plan AN.52, piece 52g; D213; the review's F-19).

Where the steps run in a worker, the web server asks the worker and waits. If no word came in time the page was told the answer
had already finished, and the request stayed in the shared table: the worker applied it later - a steer then went into the
running turn and was also sent as the next message; a Stop landed late; and one left from before a restart could stop the step
taken up after it. A request not answered in time is now withdrawn, the worker's taking of a request and the asker's withdrawing
of it cannot both happen, and the worker lets go at its start of everything asked of the run before it. Offline: the shared
store in a temporary folder; the worker is this test.
"""
import threading
from types import SimpleNamespace

import pytest

from nm.app import step_worker
from nm.app.step_worker import StepWorker, ask_worker
from nm.shared.step_share_store import FileStepShare
from nm.shared.store_file_store import _Cipher

pytestmark = pytest.mark.class_a
WHO = "worker-requests@example.test"
STEER = {"text": "Also weigh the second notice.", "documents": [], "at": "2026-11-13T10:00:00+00:00"}


@pytest.fixture
def share(tmp_path):
    return FileStepShare(tmp_path / "step-share.sqlite", _Cipher("withdrawn-requests-control-" + "k" * 24))


def test_a_request_nobody_answered_in_time_is_withdrawn_and_the_worker_never_sees_it(share):
    assert ask_worker(share, WHO, "turn-1", "steer", STEER, wait=0.3) is None, "the page is told it had not landed"
    assert share.controls() == [], "and it is not there for the worker to apply later"


def test_a_request_the_worker_took_in_that_same_moment_did_land_and_its_word_is_returned(share):
    """The worker takes the request just as the asker's wait ends: it is not withdrawn, and the worker's word is waited for."""
    taken = threading.Event()

    def worker():
        while not taken.is_set():
            for number, *_ in share.controls():
                taken.set()
                threading.Timer(0.05, lambda: share.verdict(number, {"taken": True})).start()
    real = step_worker.time.sleep
    working = threading.Thread(target=worker, daemon=True)
    # The worker looks only once the asker has stopped waiting.
    original = share.withdraw

    def withdraw(number):
        working.start()
        assert taken.wait(10)
        return original(number)
    share.withdraw = withdraw
    assert ask_worker(share, WHO, "turn-1", "steer", STEER, wait=0.5) == {"taken": True}
    assert real is step_worker.time.sleep


def test_a_request_is_taken_by_the_worker_or_withdrawn_by_the_asker_never_both(share):
    for _ in range(40):
        number = share.control(WHO, "turn-1", "stop", {})
        outcome, together = {}, threading.Barrier(2)

        def take():
            together.wait(10)
            outcome["took"] = [n for n, *_ in share.controls()]

        def withdraw():
            together.wait(10)
            outcome["withdrew"] = share.withdraw(number)
        pair = [threading.Thread(target=take), threading.Thread(target=withdraw)]
        for each in pair:
            each.start()
        for each in pair:
            each.join(30)
        assert (outcome["took"] == [number]) != outcome["withdrew"], outcome
        share.verdict(number, {"stopped": True})


def test_a_request_taken_once_is_not_given_to_the_worker_again(share):
    number = share.control(WHO, "turn-1", "stop", {})
    assert [n for n, *_ in share.controls()] == [number] and share.controls() == []
    assert share.verdict_of(number) is None, "taken is not answered"
    share.verdict(number, {"stopped": True})
    assert share.verdict_of(number) == {"stopped": True}


def test_at_its_start_the_worker_lets_go_of_what_was_asked_of_the_run_before_it(share, monkeypatch):
    left = share.control(WHO, "turn-1", "stop", {})  # a Stop pressed just before the restart, which nobody took
    answered = share.control(WHO, "turn-0", "stop", {})
    share.controls()  # (the run before took both...)
    share.verdict(answered, {"stopped": True})  # (...and answered one before it ended)
    from nm.app import main
    monkeypatch.setattr(main, "_take_up_what_an_earlier_run_left", lambda app: None)
    StepWorker(SimpleNamespace(step_share=share), name="restarted").start()
    assert share.controls() == [], "the Stop from before the restart stops nothing taken up after it"
    assert share.withdraw(left) is True and share.verdict_of(answered) == {"stopped": True}, "an answered one keeps its word"
