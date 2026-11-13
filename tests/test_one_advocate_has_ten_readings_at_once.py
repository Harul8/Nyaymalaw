"""One advocate has ten readings at once; the rest wait their turn (plan AN.53, 53d2; D219 with the number of D235; F-29).

Each reading of scanned pages or a recording began a thread of its own the moment it was asked for, with no count: one account
could have as many running as it had documents, each holding memory and calls to the AI service. At most ten of one advocate's
readings now run at once - the most papers one message carries - and one asked for beyond that is not refused: it waits, in the
order asked, shown as a reading that has not yet read a page, and begins when one of the ten ends. Another advocate's readings
are not held up by them.
"""
from __future__ import annotations

import threading
import time

import pytest

from nm.app import api
from nm.app.documents import ReadingJobs

pytestmark = pytest.mark.class_a


class _Work:
    """Readings that begin when the jobs let them and end when the test says."""

    def __init__(self):
        self.begun, self.gates, self.lock = [], {}, threading.Lock()

    def of(self, name, fails=False):
        gate = self.gates[name] = threading.Event()

        def work(progress):
            with self.lock:
                self.begun.append(name)
            assert gate.wait(20), "the test never let this reading end"
            if fails:
                raise RuntimeError("the reading failed")
            return {"document_ref": name}
        return work

    def end(self, name):
        self.gates[name].set()


def _until(condition, what):
    deadline = time.monotonic() + 10
    while not condition():
        assert time.monotonic() < deadline, what
        time.sleep(0.01)


def _explain(exc):
    return {"status": 503, "why": "The pages could not be read just now.", "code": "document_reading_unavailable"}


def test_the_number_is_the_most_papers_one_message_carries():
    assert ReadingJobs.AT_ONCE == api.TURN_DOCUMENT_LIMIT == 10


def test_ten_of_one_advocates_readings_run_and_the_rest_wait_in_the_order_asked():
    jobs, work = ReadingJobs(), _Work()
    names = [f"doc-{number:02d}" for number in range(13)]
    for name in names:
        assert jobs.start("first@example.test", name, 4, work.of(name), _explain)["state"] == "reading"
    _until(lambda: len(work.begun) == 10, "ten readings begin")
    time.sleep(0.2)
    assert sorted(work.begun) == names[:10], "and no more than ten"
    assert jobs.status("first@example.test", "doc-11") == {"state": "reading", "done": 0, "total": 4}, "one that waits is not refused"
    work.end("doc-03")
    _until(lambda: len(work.begun) == 11, "a place freed is taken")
    assert work.begun[-1] == "doc-10", "by the one that has waited longest"
    assert jobs.status("first@example.test", "doc-03")["state"] == "done"
    # One place freed at a time, so that the order the waiting ones begin in can be seen.
    for freed, taken_by in (("doc-00", "doc-11"), ("doc-01", "doc-12")):
        work.end(freed)
        _until(lambda: work.begun[-1] == taken_by, f"{taken_by} takes the place {freed} gave up")
    assert work.begun[10:] == names[10:]
    for name in names:
        work.end(name)
    _until(lambda: all(jobs.status("first@example.test", name)["state"] == "done" for name in names), "every reading ends")
    assert not jobs._running and not jobs._waiting, "and nothing is left counted or waiting"


def test_another_advocates_reading_is_not_held_up_by_them():
    jobs, work = ReadingJobs(), _Work()
    for number in range(12):
        jobs.start("first@example.test", f"doc-{number}", 1, work.of(f"doc-{number}"), _explain)
    _until(lambda: len(work.begun) == 10, "ten readings begin")
    jobs.start("second@example.test", "theirs", 1, work.of("theirs"), _explain)
    _until(lambda: "theirs" in work.begun, "the other advocate's reading begins at once")
    for name in list(work.gates):
        work.end(name)


def test_asking_again_for_one_that_waits_says_where_it_stands_and_does_not_ask_twice():
    jobs, work = ReadingJobs(), _Work()
    for number in range(10):
        jobs.start("first@example.test", f"doc-{number}", 1, work.of(f"doc-{number}"), _explain)
    _until(lambda: len(work.begun) == 10, "ten readings begin")
    first = jobs.start("first@example.test", "waits", 3, work.of("waits"), _explain)
    again = jobs.start("first@example.test", "waits", 3, work.of("waits-asked-again"), _explain)
    assert first == again == {"state": "reading", "done": 0, "total": 3}
    for name in list(work.gates):
        work.end(name)
    _until(lambda: jobs.status("first@example.test", "waits")["state"] == "done", "it is read once a place is free")
    assert work.begun.count("waits") == 1 and "waits-asked-again" not in work.begun


def test_a_reading_that_fails_gives_up_its_place():
    jobs, work = ReadingJobs(), _Work()
    for number in range(10):
        jobs.start("first@example.test", f"doc-{number}", 1, work.of(f"doc-{number}", fails=number == 0), _explain)
    jobs.start("first@example.test", "waits", 1, work.of("waits"), _explain)
    _until(lambda: len(work.begun) == 10, "ten readings begin")
    work.end("doc-0")
    _until(lambda: "waits" in work.begun, "the place of the one that failed is taken")
    assert jobs.status("first@example.test", "doc-0")["state"] == "failed"
    for name in list(work.gates):
        work.end(name)
