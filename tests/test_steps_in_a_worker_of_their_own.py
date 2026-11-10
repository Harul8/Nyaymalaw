"""Steps in a worker process of their own (plan AN.48, piece 48f4; owner decision D167): with NM_STEP_WORKER=separate the web server
works no step itself - it hands each to the step worker through the shared step store and waits for it as 48f1 waits - and what it
asks of a step at work (Stop, Steer, answers, what is typed meanwhile) reaches the worker the same way; the progress the page reads
is the worker's; a step taken while no worker is there waits for one; the shared store seals every word. The page is unchanged.
Offline: the web server and the worker as two applications on one store, in one test process; scripted models; invented words."""
import json
import sqlite3
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nm.app import api
from nm.app.composition import Application
from nm.app.main import create_app
from nm.app.step_worker import StepWorker, mode_from
from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, enrol
from nm.arrive.mail_outbox import FileOutbox
from nm.arrive.store_directory import FileDirectory
from nm.core_engine import steps as stepwise
from nm.core_engine.conversation import chat_matter_id, shown_of, stored_chat
from nm.shared.store_file_store import FileMatterStore
from tests.test_a_message_while_a_matter_waits import SENT
from tests.test_core_answer_sections import Scripted, scripted_answers
from tests.test_core_served import KEY, OWNER, PASSWORD
from tests.test_core_turn import ScriptedModel, searcher
from tests.test_steps_run_as_jobs import Held


def applications(tmp_path, model, directory, store):
    def made(steps):
        return Application(root=Path(__file__).resolve().parents[1], model=model, store=store, directory=directory,
                           mail=FileOutbox(tmp_path, key=KEY), legal_search=searcher(), audit_root=tmp_path / "audit",
                           steps=steps, environment={
                               "NM_MATTER_KEY": KEY, "NM_MATTER_STORE": str(tmp_path), "NM_MODEL_PROVIDER": "scripted",
                               "NM_MODEL_ROUTINE": "scripted-1", "NM_EMBED_MODEL": "text-embedding-3-large",
                               "NM_BARE_ACTS_DIR": str(tmp_path / "no-held-acts"), "NM_STEP_WORKER": "separate"})
    return made("web"), made("worker")


@pytest.fixture
def split(tmp_path, monkeypatch):
    directory, store = FileDirectory(tmp_path, key=KEY), FileMatterStore(tmp_path, key=KEY)
    model = ScriptedModel(legal=True)
    model.provider = "scripted"
    directory.enrol(Enrolment(AdvocateIdentity(OWNER, OWNER), enrol(PASSWORD)))
    web, worker_app = applications(tmp_path, model, directory, store)
    monkeypatch.setattr(api, "_application", web)
    client = TestClient(create_app(web))
    reply = client.post("/api/login", headers={"origin": "http://testserver"}, json={"advocate_id": OWNER, "password": PASSWORD})
    assert reply.status_code == 200, reply.text
    client.headers.update({"origin": "http://testserver", "x-nm-csrf": client.cookies.get("nm_csrf")})
    worker = StepWorker(worker_app, name="test-worker")

    class Split:
        def __init__(self):
            self.web, self.worker_app, self.worker, self.client, self.model, self.store = web, worker_app, worker, client, model, store
            self.thread = None

        def start_worker(self):
            self.worker.start()
            self.thread = threading.Thread(target=self.worker.run, daemon=True)
            self.thread.start()

    out = Split()
    out.served = type("Served", (), {"model": model})()  # what the scripted helpers patch
    yield out
    worker.stop()
    client.close()


def test_the_mode_is_the_setting_s_and_one_process_stays_the_default():
    assert [mode_from(value) for value in (None, "", "inside", "separate", " Separate ")] == [
        "inside", "inside", "inside", "web", "web"]


def test_the_web_server_hands_a_step_to_the_worker_and_answers_as_it_always_has(split):
    scripted_answers(split.served, Scripted())
    split.start_worker()
    reply = split.client.post("/api/turn", json=SENT)
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting", reply.text
    chat = stored_chat(OWNER, None, "turn-1")
    assert stepwise.waiting_of(shown_of(split.store.load(chat_matter_id(OWNER, chat)))) == "understood"
    assert split.web.step_jobs.latest(OWNER, "turn-1").answered()["status"] == 409
    go = split.client.post("/api/turn/go", json={"chat_id": chat, "turn_id": "turn-1", "choice": "research", "disputes": ["D1"]})
    assert go.status_code == 409 and go.json()["detail"]["code"] == "waiting"
    assert set(shown_of(split.store.load(chat_matter_id(OWNER, chat)))["steps"]["parts"]) == {"D1"}


def test_stop_reaches_a_step_at_work_in_the_worker_and_the_page_reads_the_worker_s_progress(split):
    scripted_answers(split.served, Scripted())
    held = Held(split.served)
    split.web.step_jobs.wait_seconds = 0.3
    split.start_worker()
    assert split.client.post("/api/turn", json=SENT).status_code == 202
    assert held.entered.wait(10)
    progress = split.client.get("/api/turn-progress", params={"turn_id": "turn-1"}).json()
    assert progress["state"] == "working" and progress["stage"] not in (None, "queued")
    assert split.client.post("/api/turn/stop", json={"turn_id": "turn-1"}).json() == {"state": "stopping"}
    held.go.set()
    for _ in range(300):
        outcome = split.client.get("/api/turn/outcome", params={"turn_id": "turn-1"})
        if outcome.status_code != 202:
            break
        threading.Event().wait(0.05)
    assert outcome.status_code == 409 and outcome.json()["detail"]["code"] == "stopped"


def test_a_step_taken_while_no_worker_is_there_waits_for_one(split):
    scripted_answers(split.served, Scripted())
    split.web.step_jobs.wait_seconds = 0.3
    reply = split.client.post("/api/turn", json=SENT)
    assert reply.status_code == 202, "taken and kept for the worker"
    assert split.client.get("/api/turn-progress", params={"turn_id": "turn-1"}).json()["state"] == "unknown", \
        "no worker is known to be there"
    split.start_worker()
    for _ in range(300):
        outcome = split.client.get("/api/turn/outcome", params={"turn_id": "turn-1"})
        if outcome.status_code != 202:
            break
        threading.Event().wait(0.05)
    assert outcome.status_code == 409 and outcome.json()["detail"]["code"] == "waiting"


def test_the_shared_store_seals_every_word(split, tmp_path):
    scripted_answers(split.served, Scripted())
    split.start_worker()
    assert split.client.post("/api/turn", json=SENT).status_code == 409
    raw = (tmp_path / "step-share.sqlite").read_bytes()
    assert SENT["message"].encode() not in raw, "the message is sealed"
    with sqlite3.connect(tmp_path / "step-share.sqlite") as db:
        asked, answered = db.execute("SELECT asked, answered FROM steps").fetchone()
    for blob in (asked, answered):
        with pytest.raises(ValueError):  # sealed: no JSON, no words, until opened under the installation's key
            json.loads(blob)


def until(test, seconds=15):
    for _ in range(int(seconds / 0.05)):
        if test():
            return True
        threading.Event().wait(0.05)
    return test()


def test_steer_and_what_is_typed_meanwhile_reach_a_step_at_work_in_the_worker(split):
    scripted_answers(split.served, Scripted())
    held = Held(split.served)
    split.web.step_jobs.wait_seconds = 0.3
    split.start_worker()
    assert split.client.post("/api/turn", json=SENT).status_code == 202
    assert held.entered.wait(10)
    chat = stored_chat(OWNER, None, "turn-1")
    steer = split.client.post("/api/turn/steer", json={"turn_id": "turn-1", "message": "Also weigh the second notice."})
    assert steer.status_code == 200 and steer.json() == {"state": "taken"}, steer.text
    queued = split.client.put(f"/api/chats/{chat}/queued", json={"queued": [{"text": "Then the map.", "documents": []}]})
    assert queued.status_code == 200 and queued.json() == {"state": "saved"}, queued.text
    held.go.set()
    assert until(lambda: split.client.get("/api/turn/outcome", params={"turn_id": "turn-1"}).status_code != 202)
    saved = shown_of(split.store.load(chat_matter_id(OWNER, chat)))
    assert [steer["text"] for steer in saved["steers"]] == ["Also weigh the second notice."], "the step went on with it"
    from nm.core_engine.conversation import queued_of
    assert [line["text"] for line in queued_of(split.store.load(chat_matter_id(OWNER, chat)))] == ["Then the map."]


class Asking:
    """A stand-in window of NM's questions, as nm.core_engine.questions keeps one."""

    def __init__(self):
        self.taken, self.is_open = [], True

    def open(self):
        return self.is_open

    def view(self):
        return {"questions": [{"id": "q1", "question": "Which notice?", "choices": ["First", "Second"]}], "taken": self.taken}

    def receive(self, given, *, hold=True):
        from nm.core_engine.questions import Refused
        if "q1" not in given:
            raise Refused("Answer the question NM asked.")
        self.taken.append(given["q1"])
        return "taken"


def test_nm_s_questions_are_read_from_the_worker_and_answered_there(split):
    split.start_worker()
    assert until(lambda: split.web.questions.window(OWNER, "turn-1") is None)
    asking = Asking()
    split.worker_app.questions.bound(OWNER).open("turn-1", asking)
    window = split.web.questions.window(OWNER, "turn-1")
    assert window is not None and window.view()["questions"][0]["question"] == "Which notice?"
    from nm.core_engine.questions import Refused
    with pytest.raises(Refused, match="Answer the question NM asked."):
        split.web.questions.answer(OWNER, "turn-1", {"other": {"chosen": ["First"]}})
    assert split.web.questions.answer(OWNER, "turn-1", {"q1": {"chosen": ["Second"]}}) == "taken"
    assert until(lambda: split.web.questions.window(OWNER, "turn-1").view()["taken"] == [{"chosen": ["Second"]}])
    split.worker_app.questions.close(OWNER, "turn-1")
    assert split.web.questions.window(OWNER, "turn-1") is None
    assert split.web.questions.answer(OWNER, "turn-1", {"q1": {"chosen": ["First"]}}) == "closed"


def test_a_worker_gone_quiet_leaves_nothing_said_to_be_at_work(split, monkeypatch):
    from nm.app import step_worker
    scripted_answers(split.served, Scripted())
    split.start_worker()
    assert split.client.post("/api/turn", json=SENT).status_code == 409
    split.worker.stop()
    split.thread.join(5)
    split.worker_app.step_share.put_progress(OWNER, "turn-x", {"started": 0, "ended": None, "state": "working",
                                                               "steps": [{"stage": "searching", "at": 0}], "detail": {}})
    monkeypatch.setattr(step_worker, "BEAT_LASTS", 0.0)
    assert split.client.get("/api/turn-progress", params={"turn_id": "turn-x"}).json()["state"] == "unknown"
    assert not split.web.turn_running(OWNER, "turn-x"), "a turn is not left looking busy by a worker that has gone"
    # The worker's next start says what it left was stopped.
    monkeypatch.setattr(step_worker, "BEAT_LASTS", 30.0)
    split.worker.start()
    split.worker_app.step_share.beat("test-worker", waiting=0, working=0)
    assert split.client.get("/api/turn-progress", params={"turn_id": "turn-x"}).json()["state"] == "stopped"
