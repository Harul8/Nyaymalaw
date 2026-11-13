"""The set-up to host (plan AN.48, piece 48f6; owner decision D167): the server says where the steps are worked and how many wait
and are at work (at /api/health/detail, behind sign-in, since plan AN.52's 52a3 - a visitor is told up or down only) - counts only, never whose or what - and, where the steps run in a worker of their own, whether the worker has been
heard from; the hosting guide says how to run, update and front the two processes; the drills that prove them are there to run.
Offline: scripted models; the words are invented."""
from pathlib import Path

from tests.test_a_message_while_a_matter_waits import SENT
from tests.test_core_answer_sections import Scripted, scripted_answers
from tests.test_core_served import served  # noqa: F401 - pytest fixture
from tests.test_steps_in_a_worker_of_their_own import split, until  # noqa: F401 - pytest fixture
from tests.test_steps_run_as_jobs import Held

ROOT = Path(__file__).resolve().parents[1]


def test_one_process_says_how_many_steps_wait_and_work(served):
    assert served.client.get("/api/health/detail").json()["steps"] == {"mode": "inside", "waiting": 0, "working": 0}
    scripted_answers(served, Scripted())
    held = Held(served)
    served.app.step_jobs.wait_seconds, served.app.step_jobs.at_once = 0.2, 1
    assert served.client.post("/api/turn", json=SENT).status_code == 202
    assert held.entered.wait(10)
    assert served.client.post("/api/turn", json={**SENT, "turn_id": "turn-2"}).status_code == 202
    assert served.client.get("/api/health/detail").json()["steps"] == {"mode": "inside", "waiting": 1, "working": 1}
    held.go.set()
    for turn in ("turn-1", "turn-2"):
        served.app.step_jobs.of("core-owner@example.test", turn).exception(timeout=30)
    assert until(lambda: served.client.get("/api/health/detail").json()["steps"]["working"] == 0)


def test_a_web_server_says_whether_its_worker_is_there(split):
    assert split.client.get("/api/health/detail").json()["steps"] == {"mode": "separate", "worker": "not heard from",
                                                               "waiting": 0, "working": 0}
    split.start_worker()
    assert until(lambda: split.client.get("/api/health/detail").json()["steps"]["worker"] == "alive")


def test_the_hosting_guide_and_the_drills_are_there_and_say_what_hosting_needs():
    guide = (ROOT / "docs" / "HOSTING.md").read_text(encoding="utf-8")
    for needed in ("python -m nm.app.step_worker", "NM_STEP_WORKER", "NM_STEP_WAIT_SECONDS", "NM_STEPS_AT_ONCE",
                   "NM_STEPS_PER_ADVOCATE", "--no-follow-code", "/api/turn-events", "proxy_buffering off", "Backups"):
        assert needed in guide, needed
    drills = (ROOT / "development_environment" / "developer_tooling" / "step_drills.py").read_text(encoding="utf-8")
    for drill in ("def drill_restart", "def drill_split", "def drill_load", "def drill_stream"):
        assert drill in drills, drill
