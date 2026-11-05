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


# --- the turn (piece 41b) and its answering (piece 41c) -------------------------------------------------------------------------

def test_a_turns_preparation_is_one_turns_scope_closed_before_the_check_made_at_saving(tmp_path, monkeypatch):
    import contextlib

    from nm.core_engine import turn
    from nm.shared.store_file_store import FileMatterStore
    from tests.test_core_answer_sections import Scripted, through_turns
    from tests.test_core_turn import run
    seen, opened = [], replay_scope.turn

    @contextlib.contextmanager
    def watched():
        seen.append("opened")
        with opened():
            yield
        seen.append("closed")
    original_check = turn.validate_activity

    def check(*args):
        seen.append("checked")
        return original_check(*args)
    monkeypatch.setattr(replay_scope, "turn", watched)
    monkeypatch.setattr(turn, "validate_activity", check)
    response = run(FileMatterStore(tmp_path, key="synthetic-turn-fixture"), through_turns(Scripted()))
    assert response["committed"] == "committed"
    assert seen == ["opened", "closed", "checked"]

def faulty_first(round_, payload):
    """A section the review sends back once, so that it is written, checked and shown more than once."""
    from tests.test_core_answer_sections import paragraph
    return [paragraph("summary", "UNSUPPORTED claim." if round_ == 1 else "In short for D2."),
            paragraph("next_step", f"Take the next step for D2 (round {round_}).")]


def validated_while_answering(tmp_path, monkeypatch):
    """Each research validation one turn of two disputes makes before the check made at saving, by the identities it was made
    from; and how many times the turn showed more of its answer."""
    from nm.core_engine import research, turn
    from nm.shared.store_file_store import FileMatterStore
    from tests.test_core_answer_sections import Scripted, through_turns
    from tests.test_core_turn import run
    checking, made = {"now": False}, []
    original_check, original_validate = turn.validate_activity, research._validate

    def check(*args):
        checking["now"] = True
        try:
            return original_check(*args)
        finally:
            checking["now"] = False

    def validate(record, plan, context):
        if not checking["now"]:
            made.append((id(record), id(plan), id(context)))
        return original_validate(record, plan, context)
    monkeypatch.setattr(turn, "validate_activity", check)
    monkeypatch.setattr(research, "_validate", validate)
    shown = []
    response = run(FileMatterStore(tmp_path, key="synthetic-turn-fixture"), through_turns(Scripted({"D2": faulty_first})),
                   progress=lambda stage, **detail: shown.append(stage))
    monkeypatch.setattr(turn, "validate_activity", original_check)
    monkeypatch.setattr(research, "_validate", original_validate)
    assert response["committed"] == "committed"
    return made, shown.count("shown")


def test_a_turn_validates_each_research_record_once_however_often_it_writes_checks_and_shows(tmp_path, monkeypatch):
    made, shown = validated_while_answering(tmp_path, monkeypatch)
    assert shown >= 2, "the answer was shown more than once"
    assert len(made) == len(set(made)), "a research record validated twice in one turn"


def test_without_the_turns_scope_the_same_research_would_be_validated_again_and_again(tmp_path, monkeypatch):
    import contextlib
    with_scope = len(validated_while_answering(tmp_path / "with", monkeypatch)[0])
    monkeypatch.setattr(replay_scope, "turn", contextlib.nullcontext)
    without = len(validated_while_answering(tmp_path / "without", monkeypatch)[0])
    assert without > 3 * with_scope


def test_within_a_turn_the_research_plan_is_admitted_once_for_every_dispute_checked_against_it(monkeypatch):
    """Step 1 (5 Nov 2026): each dispute's research, and research continuing where it stopped, was checked against the same plan,
    admitting the plan again each time - about 5.5 s a dispute on the 4 Nov matter (28 s for its five; 7 s now). Within
    a turn it is admitted once; outside any scope, each time, as before."""
    from nm.core_engine import research
    log = []
    monkeypatch.setattr(research, "_accept", lambda proposal, context, contract=research.CONTRACT: log.append(contract) or
                        {"admitted": proposal["n"]})
    proposal, context = {"n": 1}, {"latest": {}}
    with replay_scope.turn():
        first = research.accept(proposal, context)
        assert all(research.accept(proposal, context) is first for _ in range(4))
        research.accept({"n": 1}, context)  # another proposal, though alike, is admitted for itself
    research.accept(proposal, context)
    assert log == [research.CONTRACT] * 3
