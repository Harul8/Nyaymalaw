"""An adapter built on its first use is built once, however many callers arrive together (plan AN.24; owner decision O30).

The usage store, the turn-attempt store, the case index and a turn's model are all built the first time they are used. Built
by two callers at once they were two things racing to make one: two stores creating one file, or a turn's two parallel steps
each checking the allowance. The one that is built is the one every caller uses; a build that fails is not kept.
"""
from __future__ import annotations

import threading
import time

import pytest

from nm.app.composition import _DeferredAdapter

pytestmark = pytest.mark.class_a


class Thing:
    def __init__(self, number):
        self.number = number

    def hello(self):
        return f"hello from {self.number}"


def test_callers_arriving_together_build_it_once_and_all_use_the_same_one():
    built, barrier = [], threading.Barrier(8)

    def factory():
        built.append(threading.get_ident())
        time.sleep(0.05)               # a slow build, so the callers really do overlap
        return Thing(len(built))

    deferred = _DeferredAdapter(factory)
    answers = []

    def caller():
        barrier.wait()
        answers.append(deferred.hello())

    pool = [threading.Thread(target=caller) for _ in range(8)]
    for thread in pool:
        thread.start()
    for thread in pool:
        thread.join()
    assert len(built) == 1, f"built {len(built)} times"
    assert answers == ["hello from 1"] * 8


def test_it_is_not_built_until_it_is_used_and_not_built_again_after():
    built = []
    deferred = _DeferredAdapter(lambda: built.append(True) or Thing(len(built)))
    assert built == []
    assert deferred.hello() == "hello from 1" and deferred.hello() == "hello from 1"
    assert built == [True]
    assert deferred._resolve() is deferred._resolve()


def test_a_build_that_fails_is_not_kept_and_the_next_caller_builds_it_afresh():
    attempts = []

    def factory():
        attempts.append(True)
        if len(attempts) == 1:
            raise OSError("the first build fails")
        return Thing(len(attempts))

    deferred = _DeferredAdapter(factory)
    with pytest.raises(OSError):
        deferred.hello()
    assert deferred.inner is None
    assert deferred.hello() == "hello from 2"
    assert len(attempts) == 2


def test_callers_waiting_on_a_build_that_fails_each_try_again_in_turn():
    attempts, barrier = [], threading.Barrier(3)

    def factory():
        attempts.append(True)
        time.sleep(0.02)
        if len(attempts) == 1:
            raise OSError("the first build fails")
        return Thing(len(attempts))

    deferred = _DeferredAdapter(factory)
    outcomes = []

    def caller():
        barrier.wait()
        try:
            outcomes.append(deferred.hello())
        except OSError:
            outcomes.append("refused")

    pool = [threading.Thread(target=caller) for _ in range(3)]
    for thread in pool:
        thread.start()
    for thread in pool:
        thread.join()
    assert outcomes.count("refused") == 1 and outcomes.count("hello from 2") == 2
    assert len(attempts) == 2, "the second build served the two that were waiting"


def test_the_stores_built_this_way_are_the_ones_that_first_used_together_must_be_safe():
    """The population: every adapter the composition root builds lazily goes through this one mechanism."""
    import inspect

    from nm.app import composition

    source = inspect.getsource(composition)
    assert source.count("_DeferredAdapter(") >= 4
    assert "self.inner = self.factory()" in source and source.count("self.factory()") == 1
