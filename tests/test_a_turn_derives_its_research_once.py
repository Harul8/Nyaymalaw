"""A turn derives what comes from its research once (plan AN.41, step 1; owner, 4 Nov 2026: "does it take so much time?").

On 4 Nov 2026 a turn of five disputes spent 37 of its 73 minutes with no AI call running: each writer, review and authority
check validated the research afresh, and each part shown drew the whole answer again. Within one turn what is derived from the
research alone is now derived once, shared by the turn's threads; a check of a draft, which a turn rewrites, is made each time.
Offline: invented derivations and the scripted turns of the other tests, no AI calls.
"""
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from nm.core_engine import replay_scope


def maker(log, name, value=None):
    def make():
        log.append(name)
        return {"made": name} if value is None else value
    return make


def test_within_a_turn_what_comes_from_the_research_is_derived_once_and_a_drafts_check_each_time():
    record, context, draft, log = {"r": 1}, {"c": 1}, {"d": 1}, []
    with replay_scope.turn():
        first = replay_scope.once(("research", id(record)), (record,), maker(log, "research"))
        again = replay_scope.once(("research", id(record)), (record,), maker(log, "research"))
        for kind in ("part", "sources", "raw"):
            for _ in range(3):
                replay_scope.once((kind, id(record), id(context)), (record, context), maker(log, kind))
        for _ in range(2):
            replay_scope.once(("authorities", id(draft)), (draft,), maker(log, "authorities"))
    assert first is again
    assert log == ["research", "part", "sources", "raw", "authorities", "authorities"]


def test_a_check_derives_everything_once_and_outside_both_nothing_is_remembered():
    draft, log = {"d": 1}, []
    with replay_scope.replaying():
        for _ in range(2):
            replay_scope.once(("authorities", id(draft)), (draft,), maker(log, "in a check"))
    for _ in range(2):
        replay_scope.once(("research", id(draft)), (draft,), maker(log, "outside"))
    assert log == ["in a check", "outside", "outside"]


def test_another_object_is_never_taken_for_the_one_derived_from():
    log = []
    with replay_scope.turn():
        record, same_content = {"r": 1}, {"r": 1}
        replay_scope.once(("research", 7), (record,), maker(log, "first"))
        replay_scope.once(("research", 7), (same_content,), maker(log, "second"))
    assert log == ["first", "second"]


def test_what_is_known_counts_as_derived_and_a_failed_derivation_is_not_remembered():
    record, log = {"r": 1}, []
    with replay_scope.turn():
        replay_scope.known(("research", id(record)), (record,), record)
        assert replay_scope.once(("research", id(record)), (record,), maker(log, "never")) is record

        def failing():
            log.append("failed")
            raise ValueError("cannot be read")
        with pytest.raises(ValueError):
            replay_scope.once(("part", id(record)), (record,), failing)
        replay_scope.once(("part", id(record)), (record,), maker(log, "part"))
    assert log == ["failed", "part"]


def test_a_pool_carries_the_turns_scope_into_its_threads_and_threads_derive_a_thing_once():
    record, log, started, release = {"r": 1}, [], threading.Event(), threading.Event()

    def slow():
        log.append("made")
        started.set()
        release.wait(5)
        return {"made": True}

    def derive():
        return replay_scope.once(("research", id(record)), (record,), slow)
    with replay_scope.turn():
        with replay_scope.Pool(max_workers=4) as pool:
            first = pool.submit(derive)
            started.wait(5)
            others = [pool.submit(derive) for _ in range(3)]
            release.set()
            results = [first.result(), *(future.result() for future in others)]
        # A thread the pool did not start, as before: outside the turn's scope.
        with ThreadPoolExecutor(max_workers=1) as plain:
            plain.submit(derive).result()
    assert log == ["made", "made"]
    assert all(result is results[0] for result in results)

