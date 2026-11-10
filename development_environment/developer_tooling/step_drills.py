"""Drills for steps as jobs (plan AN.48, piece 48f6; owner decision D167): offline, on a throwaway store under a short temporary
path, with the stand-in models the tests use - no paid call, and never the installation's own conversations or accounts.

    python development_environment/developer_tooling/step_drills.py restart  # a step whose process is killed is taken up again
    python development_environment/developer_tooling/step_drills.py load     # matters at once: the limits hold, pages answer
    python development_environment/developer_tooling/step_drills.py split    # web server and worker apart; the web server restarted
    python development_environment/developer_tooling/step_drills.py stream   # progress told as it changes, through a real server

Each prints what it measured and ends 0 when what it checks held. Run from the checkout root; the stand-in models come from tests/.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
KEY = "Synthetic-drill-store-key-41"
ADVOCATE, PASSWORD = "drill-owner@example.test", "Synthetic-drill-password-58!"
SENT = {"message": "Inspect this reported account.", "turn_id": "turn-1", "steps": "interactive"}


def _environment(store, **more):
    return {"NM_MATTER_KEY": KEY, "NM_MATTER_STORE": str(store), "NM_MODEL_PROVIDER": "scripted",
            "NM_MODEL_ROUTINE": "scripted-1", "NM_EMBED_MODEL": "text-embedding-3-large",
            "NM_BARE_ACTS_DIR": str(Path(store) / "no-held-acts"), **more}


def _application(store, *, slow=0.0, steps=None, **settings):
    """The application the tests serve, on this store, its stand-in model taking slow seconds a call."""
    from nm.app.composition import Application
    from nm.arrive.mail_outbox import FileOutbox
    from nm.arrive.store_directory import FileDirectory
    from nm.shared.store_file_store import FileMatterStore
    from tests.test_core_answer_sections import Scripted, scripted_answers
    from tests.test_core_turn import ScriptedModel, searcher

    class Served:
        model = ScriptedModel(legal=True)
    Served.model.provider = "scripted"
    scripted_answers(Served, Scripted())
    if slow:
        first = Served.model.structured

        def structured(prompt, schema, tier, **kwargs):
            time.sleep(slow)
            return first(prompt, schema, tier, **kwargs)
        Served.model.structured = structured
    return Application(root=ROOT, model=Served.model, store=FileMatterStore(store, key=KEY),
                       directory=FileDirectory(store, key=KEY), mail=FileOutbox(store, key=KEY), legal_search=searcher(),
                       audit_root=Path(store) / "audit", steps=steps, environment=_environment(store, **settings))


def _enrolled(store, who=ADVOCATE):
    from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, enrol
    from nm.arrive.store_directory import FileDirectory
    FileDirectory(store, key=KEY).enrol(Enrolment(AdvocateIdentity(who, who), enrol(PASSWORD)))


def _client(app, who=ADVOCATE):
    from fastapi.testclient import TestClient
    from nm.app.main import create_app
    client = TestClient(create_app(app))
    reply = client.post("/api/login", headers={"origin": "http://testserver"}, json={"advocate_id": who, "password": PASSWORD})
    assert reply.status_code == 200, reply.text
    client.headers.update({"origin": "http://testserver", "x-nm-csrf": client.cookies.get("nm_csrf")})
    return client


def _held(store, who=ADVOCATE, turn="turn-1"):
    """What the conversation holds of the turn, as code reads it: where it waits and what it understood (no words of a matter)."""
    from nm.core_engine import steps as stepwise
    from nm.core_engine.conversation import chat_matter_id, shown_of, stored_chat
    from nm.shared.store_file_store import FileMatterStore
    held = shown_of(FileMatterStore(store, key=KEY).load(chat_matter_id(who, stored_chat(who, None, turn))))
    plan = ((held["steps"]["understood"] or {}).get("plan") or {}).get("proposal") or {}
    disputes = (plan.get("understanding") or {}).get("disputes") or []
    return {"waiting": stepwise.waiting_of(held),
            "disputes": [[d.get("id"), [q.get("id") for q in d.get("legal_questions", [])]] for d in disputes]}


def _short_store(name):
    return Path(tempfile.mkdtemp(prefix=f"nm{name}", dir=os.environ.get("TEMP") or None))


# --- the restart drill -------------------------------------------------------------------------------------------------------------
def _start_and_wait(store):
    """Child: a message sent with its step slowed, then this process waits to be killed in the middle of that step."""
    app = _application(store, slow=1.5, NM_STEP_WAIT_SECONDS="0")
    client = _client(app)
    reply = client.post("/api/turn", json=SENT)
    print("STARTED", reply.status_code, flush=True)
    while True:
        time.sleep(1)


def _take_up(store):
    """Child: the next start - what the killed run left taken up by this process itself, then what the step finished as."""
    from nm.app import api
    from nm.app.main import _take_up_what_an_earlier_run_left
    app = _application(store)
    api.set_application(app)
    left = len(app.step_records.left())
    _take_up_what_an_earlier_run_left(app)
    future = app.step_jobs.of(ADVOCATE, "turn-1")
    if future is None:
        print(json.dumps({"left": left, "taken_up": False}), flush=True)
        return 1
    error = future.exception(timeout=300)
    print(json.dumps({"left": left, "taken_up": True, "outcome": getattr(error, "status_code", 200),
                      "code": (getattr(error, "detail", None) or {}).get("code"), "held": _held(store)}), flush=True)
    return 0


def _uninterrupted(store):
    """Child: the same message on its own store, never interrupted - what the step should finish as."""
    app = _application(store, NM_STEP_WAIT_SECONDS="60")
    reply = _client(app).post("/api/turn", json=SENT)
    print(json.dumps({"outcome": reply.status_code, "code": reply.json()["detail"].get("code"), "held": _held(store)}), flush=True)
    return 0


def _child(*args):
    return subprocess.Popen([sys.executable, "-B", __file__, *args], cwd=ROOT, stdout=subprocess.PIPE, text=True)


def drill_restart():
    killed, control = _short_store("r"), _short_store("c")
    try:
        _enrolled(killed)
        _enrolled(control)
        from nm.shared.step_record_store import FileStepRecords
        began = time.monotonic()
        first = _child("_start", str(killed))
        line = first.stdout.readline()
        assert line.startswith("STARTED 202"), f"the step did not go on as a job: {line!r}"
        records = FileStepRecords(killed / "step-records.sqlite")
        for _ in range(100):  # killed only once its record says the step is at work, a moment into its calls
            if any(left["begun"] for left in records.left()):
                break
            time.sleep(0.1)
        time.sleep(2)
        at_kill = records.left()
        first.kill()
        first.wait(30)
        assert at_kill and at_kill[0]["begun"], f"the step had finished before its process was killed: {at_kill}"
        again = _child("_take_up", str(killed))
        resumed = json.loads(again.stdout.readline())
        again.wait(60)
        alone = _child("_alone", str(control))
        expected = json.loads(alone.stdout.readline())
        alone.wait(60)
        print(json.dumps({"drill": "restart", "seconds": round(time.monotonic() - began, 1),
                          "killed": "2 s after the step's record said it was at work",
                          "taken_up": resumed, "uninterrupted": expected}, indent=1))
        same = resumed.get("taken_up") and {k: resumed[k] for k in ("outcome", "code", "held")} == expected
        print("RESTART DRILL:", "PASSED - taken up by itself, to the same result" if same else "FAILED")
        return 0 if same else 1
    finally:
        shutil.rmtree(killed, ignore_errors=True)
        shutil.rmtree(control, ignore_errors=True)


# --- the load drill ----------------------------------------------------------------------------------------------------------------
def drill_load(advocates=4, each=2):
    store = _short_store("l")
    try:
        names = [f"drill-{n}@example.test" for n in range(advocates)]
        for who in names:
            _enrolled(store, who)
        app = _application(store, slow=0.3, NM_STEP_WAIT_SECONDS="0.2", NM_STEPS_AT_ONCE="3", NM_STEPS_PER_ADVOCATE="2")
        clients = {who: _client(app, who) for who in names}
        most, most_each, stop = [0], [0], threading.Event()

        def watch():
            while not stop.is_set():
                with app.step_jobs._lock:
                    working = dict(app.step_jobs._working)
                most[0] = max(most[0], sum(working.values()))
                most_each[0] = max([most_each[0], *working.values()])
                time.sleep(0.02)
        threading.Thread(target=watch, daemon=True).start()
        began = time.monotonic()
        sent = [(who, f"turn-{n}") for who in names for n in range(each)]
        replies = {}

        def send(who, turn):
            replies[(who, turn)] = clients[who].post("/api/turn", json={**SENT, "turn_id": turn}).status_code
        threads = [threading.Thread(target=send, args=pair) for pair in sent]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        probe = clients[names[0]]
        times = []
        while any(app.step_jobs.of(who, turn) is None or not app.step_jobs.of(who, turn).done() for who, turn in sent):
            at = time.perf_counter()
            probe.get("/api/turn-progress", params={"turn_id": "turn-0"})
            times.append((time.perf_counter() - at) * 1000)
            time.sleep(0.1)
            if time.monotonic() - began > 600:
                break
        stop.set()
        outcomes = {}
        for who, turn in sent:
            error = app.step_jobs.of(who, turn).exception(timeout=1)
            outcomes[f"{who}/{turn}"] = (getattr(error, "detail", None) or {}).get("code") if error else "answered"
        held = most[0] <= 3 and most_each[0] <= 2 and all(code == "waiting" for code in outcomes.values())
        print(json.dumps({"drill": "load", "advocates": advocates, "steps": len(sent), "seconds": round(time.monotonic() - began, 1),
                          "first_answers": sorted(set(replies.values())), "most_at_work": most[0], "most_for_one_advocate": most_each[0],
                          "page_ms_median": round(statistics.median(times), 1) if times else None,
                          "page_ms_95th": round(sorted(times)[int(len(times) * 0.95) - 1], 1) if len(times) > 1 else None,
                          "page_reads": len(times), "outcomes": sorted(set(outcomes.values()))}, indent=1))
        print("LOAD DRILL:", "PASSED - within the limits, every step finished, pages answered meanwhile" if held else "FAILED")
        return 0 if held else 1
    finally:
        shutil.rmtree(store, ignore_errors=True)


# --- the split drill ----------------------------------------------------------------------------------------------------------------
def _free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _web(store, port):
    """Child: the web server, NM_STEP_WORKER=separate - it works no step itself."""
    import uvicorn
    from nm.app.main import create_app
    app = _application(store, steps="web", NM_STEP_WORKER="separate", NM_STEP_WAIT_SECONDS="1")
    print("SERVING", flush=True)
    uvicorn.run(create_app(app), host="127.0.0.1", port=int(port), log_level="warning")


def _worker(store):
    """Child: the step worker, its stand-in model slowed so that a step lasts while the web server is restarted."""
    from nm.app import api
    from nm.app.step_worker import StepWorker
    app = _application(store, slow=0.6, steps="worker", NM_STEP_WORKER="separate")
    api.set_application(app)
    worker = StepWorker(app, name="drill-worker")
    worker.start()
    print("WORKING", flush=True)
    worker.run()


class _Http:
    def __init__(self, port):
        self.base, self.jar = f"http://127.0.0.1:{port}", CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def call(self, method, path, body=None):
        csrf = next((cookie.value for cookie in self.jar if cookie.name == "nm_csrf"), "")
        request = urllib.request.Request(self.base + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                         headers={"content-type": "application/json", "origin": self.base, "x-nm-csrf": csrf})
        try:
            with self.opener.open(request, timeout=30) as reply:
                return reply.status, json.loads(reply.read() or b"null")
        except urllib.error.HTTPError as refused:
            return refused.code, json.loads(refused.read() or b"null")


def _until_up(http, seconds=60):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            if http.call("GET", "/api/health")[0] == 200:
                return True
        except OSError:
            pass
        time.sleep(0.5)
    return False


def drill_split():
    store, port = _short_store("s"), _free_port()
    web = worker = None
    try:
        _enrolled(store)
        worker = _child("_worker", str(store))
        assert worker.stdout.readline().startswith("WORKING")
        web = _child("_web", str(store), str(port))
        http = _Http(port)
        assert _until_up(http), "the web server did not start"
        assert http.call("POST", "/api/login", {"advocate_id": ADVOCATE, "password": PASSWORD})[0] == 200
        began = time.monotonic()
        status, _ = http.call("POST", "/api/turn", SENT)
        assert status == 202, f"the step was not handed to the worker: {status}"
        web.kill()  # the web server stops in the middle of the step
        web.wait(30)
        web = _child("_web", str(store), str(port))
        assert _until_up(http), "the web server did not start again"
        health = http.call("GET", "/api/health")[1]
        while True:
            status, body = http.call("GET", "/api/turn/outcome?turn_id=turn-1")
            if status != 202 or time.monotonic() - began > 300:
                break
            time.sleep(0.5)
        code = (body or {}).get("detail", {}).get("code") if isinstance((body or {}).get("detail"), dict) else None
        held = status == 409 and code == "waiting"
        print(json.dumps({"drill": "split", "seconds": round(time.monotonic() - began, 1), "web_server_restarted_mid_step": True,
                          "outcome": status, "code": code, "health_steps": health.get("steps")}, indent=1))
        print("SPLIT DRILL:", "PASSED - the step finished in the worker while the web server restarted" if held else "FAILED")
        return 0 if held else 1
    finally:
        for child in (web, worker):
            if child is not None and child.poll() is None:
                child.kill()
                child.wait(30)
        shutil.rmtree(store, ignore_errors=True)


# --- the stream drill ---------------------------------------------------------------------------------------------------------------
def _served(store, port):
    """Child: one process serving the pages and working the steps, as on the laptop, its stand-in model slowed."""
    import uvicorn
    from nm.app.main import create_app
    app = _application(store, slow=1.0, NM_STEP_WAIT_SECONDS="0.5")
    print("SERVING", flush=True)
    uvicorn.run(create_app(app), host="127.0.0.1", port=int(port), log_level="warning")


def drill_stream():
    """The progress stream through a real server: what a step is doing arrives as it changes, long before the step ends, and the
    stream ends with the step's last word."""
    store, port = _short_store("e"), _free_port()
    server = None
    try:
        _enrolled(store)
        server = _child("_served", str(store), str(port))
        http = _Http(port)
        assert _until_up(http), "the server did not start"
        assert http.call("POST", "/api/login", {"advocate_id": ADVOCATE, "password": PASSWORD})[0] == 200
        began = time.monotonic()
        status, _ = http.call("POST", "/api/turn", SENT)
        assert status == 202, f"the step did not go on as a job: {status}"
        heard = []
        request = urllib.request.Request(http.base + "/api/turn-events?turn_id=turn-1", headers={"accept": "text/event-stream"})
        with http.opener.open(request, timeout=300) as stream:
            for raw in stream:
                line = raw.decode("utf-8").rstrip("\r\n")
                if line.startswith("data: "):
                    heard.append((round(time.monotonic() - began, 2), json.loads(line[len("data: "):])))
        stages = []
        for _, seen in heard:
            if seen.get("stage") and (not stages or stages[-1] != seen["stage"]):
                stages.append(seen["stage"])
        first, last = heard[0], heard[-1]
        held = (first[1]["state"] == "working" and last[1]["state"] == "stopped" and last[0] - first[0] >= 2
                and len(stages) >= 2)
        print(json.dumps({"drill": "stream", "events": len(heard), "first_event_at_seconds": first[0],
                          "last_event_at_seconds": last[0], "stages_told_in_order": stages, "last_word": last[1]["state"]},
                         indent=1))
        print("STREAM DRILL:", "PASSED - told as it changed, through a real server, until its last word" if held else "FAILED")
        return 0 if held else 1
    finally:
        if server is not None and server.poll() is None:
            server.kill()
            server.wait(30)
        shutil.rmtree(store, ignore_errors=True)


def main(argv):
    command = argv[0] if argv else ""
    if command == "_start":
        return _start_and_wait(argv[1])
    if command == "_take_up":
        return _take_up(argv[1])
    if command == "_alone":
        return _uninterrupted(argv[1])
    if command == "_web":
        return _web(argv[1], argv[2])
    if command == "_worker":
        return _worker(argv[1])
    if command == "_served":
        return _served(argv[1], argv[2])
    drills = {"restart": drill_restart, "load": drill_load, "split": drill_split, "stream": drill_stream}
    if command not in drills:
        print(__doc__)
        return 2
    return drills[command]()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
