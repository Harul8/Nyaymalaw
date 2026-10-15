"""A turn in progress shows the advocate what it is doing (owner decision, 14 Oct 2026).

Stage names, counts and times only; each advocate reads only their own turns; a
reporting failure never fails the turn; a refused same-turn retry never closes the
progress of the run still working.
"""
import pytest

from nm.app.turn_progress import STAGES, TurnProgress
from nm.core_engine.conversation import ConversationRefused
from tests.test_core_served import OTHER, OWNER, served, successful  # noqa: F401 - pytest fixture
from tests.test_core_turn import ScriptedModel, run, store  # noqa: F401 - pytest fixture

pytestmark = pytest.mark.class_a


class Clock:
    def __init__(self): self.now = 100.0
    def __call__(self): return self.now


def test_the_record_keeps_stage_names_counts_and_times_only():
    clock = Clock()
    progress = TurnProgress(clock=clock, keep_seconds=60)
    progress.report("a", "t1", "understanding")
    clock.now += 4
    progress.report("a", "t1", "searching", {"done": 2, "total": 9, "text": "client words", "round": -1})
    clock.now += 3
    seen = progress.read("a", "t1")
    assert seen == {"state": "working", "stage": "searching", "label": STAGES["searching"],
                    "detail": {"done": 2, "total": 9}, "elapsed_seconds": 7,
                    "steps": [{"label": STAGES["understanding"], "seconds": 4},
                              {"label": STAGES["searching"], "seconds": 3}]}
    progress.report("a", "t1", "searching", {"done": 3, "total": 9})  # the same stage moves on, not repeats
    assert len(progress.read("a", "t1")["steps"]) == 2 and progress.read("a", "t1")["detail"]["done"] == 3
    progress.report("a", "t1", "not a stage")
    assert progress.read("a", "t1")["stage"] == "searching"


def test_each_advocate_reads_only_their_own_turn_and_entries_lapse_after_the_turn():
    clock = Clock()
    progress = TurnProgress(clock=clock, keep_seconds=60)
    progress.report("a", "t1", "writing")
    assert progress.read("b", "t1") == {"state": "unknown"}
    progress.end("a", "t1", "finished")
    clock.now += 30
    assert progress.read("a", "t1")["state"] == "finished"
    clock.now += 31
    assert progress.read("a", "t1") == {"state": "unknown"}


def test_a_turn_reports_its_stages_in_order(store):
    seen = []
    run(store, ScriptedModel(legal=True), progress=lambda stage, **detail: seen.append((stage, detail)))
    assert seen == [("understanding", {}), ("understanding_matter", {}), ("checking_understanding", {"round": 1}),
                    ("writing_search_terms", {"total": 1}), ("searching", {"done": 0, "total": 1}),
                    ("choosing_provisions", {}), ("writing", {}), ("checking_authorities", {}),
                    ("reviewing", {}), ("saving", {})]
    assert set(stage for stage, _ in seen) <= set(STAGES)


def test_a_failing_progress_report_never_fails_the_turn(store):
    def broken(stage, **detail):
        raise RuntimeError("display store unavailable")
    assert run(store, ScriptedModel(legal=True), progress=broken)["committed"] == "committed"


def test_the_advocate_reads_their_turn_progress_and_no_one_else_does(served):
    successful(served)
    mine = served.client.get("/api/turn-progress", params={"turn_id": "turn-1"}).json()
    assert mine["state"] == "finished" and mine["steps"][0]["label"] == STAGES["understanding"]
    assert mine["steps"][-1]["label"] == STAGES["saving"]
    assert "Inspect this reported account" not in str(mine)
    other = served.login(OTHER)
    assert other.get("/api/turn-progress", params={"turn_id": "turn-1"}).json() == {"state": "unknown"}
    assert served.client.get("/api/turn-progress", params={"turn_id": ""}).status_code == 422


def test_progress_needs_a_signed_in_advocate(served):
    from fastapi.testclient import TestClient
    from nm.app.main import create_app
    with TestClient(create_app(served.app)) as anonymous:
        assert anonymous.get("/api/turn-progress", params={"turn_id": "turn-1"}).status_code == 401


def test_a_refused_retry_does_not_close_the_progress_of_the_run_still_working(served, monkeypatch):
    from nm.core_engine import turn
    served.app.turn_progress.report(OWNER, "turn-1", "searching", {"done": 1, "total": 4})

    def refused(*args, **kwargs):
        raise ConversationRefused("This message is already being answered.", status=409)
    monkeypatch.setattr(turn, "process", refused)
    with pytest.raises(ConversationRefused):
        served.app.run_turn(advocate_id=OWNER, session_current=lambda: True, message="m", turn_id="turn-1")
    assert served.app.turn_progress.read(OWNER, "turn-1")["state"] == "working"
