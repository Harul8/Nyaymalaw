"""Tentative times (plan AN.48, piece 48e; owner decision D140): after Send and at each stop NM says how long its next step should
take, labelled tentative, and keeps each estimate beside the time the step took - with the matter while it is worked on, and with the
answer once it is saved. Offline: scripted models; the words are invented."""
import pytest

from nm.app.turn_progress import TurnProgress
from nm.core_engine import steps, tentative
from nm.core_engine.conversation import ConversationRefused, chat_matter_id, shown_of, stored_chat
from tests.test_core_answer_sections import Scripted, through_turns
from tests.test_core_turn import FileMatterStore, run


@pytest.fixture
def store(tmp_path):
    return FileMatterStore(tmp_path, key="synthetic-turn-fixture")


def held(store):
    return shown_of(store.load(chat_matter_id("owner", stored_chat("owner", None, "t1"))))


def waits(store, model, go):
    reported = []
    with pytest.raises(ConversationRefused):
        run(store, model, go=go, progress=lambda stage, **detail: reported.append((stage, detail)))
    return held(store), reported


def test_the_figures_are_said_in_whole_minutes_and_never_less_than_one():
    assert tentative.seconds("understand", 1) == 278 and tentative.seconds("write", 3) == 480
    assert tentative.said(20) == "about 1 minute" and tentative.said(300) == "about 5 minutes"
    assert tentative.pages_of([{"pages": [{}, {}]}, {"pages": [{}]}]) == 3


def test_each_step_says_its_tentative_time_and_keeps_it_beside_the_time_it_took(store):
    model = through_turns(Scripted())
    understood, reported = waits(store, model, steps.first())
    assert ("tentative", {"seconds": tentative.seconds("understand", 0)}) in reported, "said while the step runs"
    first, = understood["go"]["times"]
    assert first["n"] == 1 and first["steps"] == ["understand"] and first["estimate_s"] == tentative.seconds("understand", 0)
    assert first["actual_s"] >= 0

    card = steps.card(understood)
    timed = {(go["choice"], tuple(go["disputes"] or ())): go["tentative"] for go in card["gos"]}
    assert timed[("research", ("D1",))] == tentative.said(tentative.seconds("research", 1))
    assert timed[("done", ())] is None, "Done before an analysis runs no step"

    researched, _ = waits(store, model, steps.given(understood["go"], "next", held=understood))
    assert [entry["n"] for entry in researched["go"]["times"]] == [1, 2]
    written, _ = waits(store, model, steps.given(researched["go"], "next", held=researched))
    response = run(store, model, go=steps.given(written["go"], "done", held=written))
    assert [entry["steps"] for entry in response["metrics"]["steps_timed"]] == [
        ["understand"], ["research"], ["write"], ["finish"]], "kept with the answer once it is saved"


def test_a_run_end_to_end_is_timed_for_every_step_it_takes():
    plan = {"proposal": {"understanding": {"disputes": [{"id": "D1", "name": "A"}, {"id": "D2", "name": "B"}]}},
            "work": [{"id": "w1", "dispute": {"id": "D1"}}, {"id": "w2", "dispute": {"id": "D2"}}]}
    understood = {"understood": {"interpretation": {}, "plan": plan}, "limits": None, "parts": {}, "cases": {}, "answered": None}
    go = {"mode": "steps", "allowed": ["research", "write", "finish"], "n": 2, "waiting": None, "disputes": None}
    assert steps.estimate(go, understood) == (tentative.seconds("research", 2) + tentative.seconds("write", 2)
                                              + tentative.seconds("finish", 2))
    one = {**go, "allowed": ["research"], "disputes": ["D2"]}
    assert steps.estimate(one, understood) == tentative.seconds("research", 1)


def test_the_progress_carries_the_tentative_time_of_the_step_being_worked_on():
    progress = TurnProgress(clock=lambda: 100.0)
    progress.tentative("a", "t", 300)
    progress.report("a", "t", "understanding")
    assert progress.read("a", "t")["tentative_seconds"] == 300
    progress.tentative("a", "t", -1)  # not a time: ignored
    assert progress.read("a", "t")["tentative_seconds"] == 300
