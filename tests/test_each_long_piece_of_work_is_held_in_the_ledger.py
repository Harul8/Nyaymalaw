"""Each long piece of work is held in the ledger while it goes on (plan AN.52, 52c2; D209; the review's F-12).

The ledger (52c1) answers 'may I stop?' and 'how long has it been quiet?'. It held only steps and, under the supervisor, requests.
Now each other long piece of work D209 names is held by its own owner: an upload being scanned, a paper or a recording being read
(waiting its turn included), dictation (the message box's, and live words for the life of their session), and a save. And a
signed-in advocate's action is the sign of life that quiet runs from - a request no one is signed in for is not. The plan's
test: 'may I stop?' asked during each answers no, and yes once it has ended.

Offline: stand-in scanners, readers and models; no browser.
"""
from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from nm.app import api
from nm.app.activity import Activity
from nm.app.composition import _document_desk
from nm.shared.egress_contracts import Gatekeeper
from nm.shared.egress_policy import egress_policy
from nm.shared.store_file_store import FileMatterStore
from nm.work_the_file.matter_contracts import Matter
from tests.test_core_documents import ADVOCATE, ROOT, Checker
from tests.test_core_served import OWNER, served  # noqa: F401 - served is a fixture
from tests.test_core_voice import Hearing, wav

pytestmark = pytest.mark.class_a


def until(condition, seconds=5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return condition()


class Gate:
    """Lets the work it stands in for go on only when told."""

    def __init__(self):
        self.entered, self.go = threading.Event(), threading.Event()

    def pass_through(self):
        self.entered.set()
        assert self.go.wait(5), "the test never let the work go on"


def background(work):
    done, failed = threading.Event(), []

    def run():
        try:
            work()
        except BaseException as exc:  # noqa: BLE001 - kept for the test to see
            failed.append(exc)
        finally:
            done.set()
    threading.Thread(target=run, daemon=True).start()
    return done, failed


def _desk(tmp_path, ledger, checker=None):
    made = _document_desk(FileMatterStore(tmp_path, key="ledger-desk-key-for-these-tests-only-1"), tmp_path,
                          Gatekeeper(policy=egress_policy(ROOT)), {}, activity=ledger)
    made.checker = checker or Checker()
    return made


def test_may_not_stop_while_an_upload_is_being_scanned(tmp_path):
    ledger, gate = Activity(), Gate()

    class Slow(Checker):
        def check(self, data):
            gate.pass_through()
            return super().check(data)
    desk = _desk(tmp_path, ledger, Slow())
    done, failed = background(lambda: desk.receive(ADVOCATE, "note.txt", b"The cheque was returned on 3 October 2026."))
    assert gate.entered.wait(5)
    assert not ledger.may_stop() and ledger.counts() == {"scan": 1}
    gate.go.set()
    assert done.wait(5) and not failed, failed
    assert ledger.may_stop()


def test_an_upload_refused_by_the_scanner_or_its_rules_is_let_go_too(tmp_path):
    ledger = Activity()
    desk = _desk(tmp_path, ledger, Checker(state="held", reason="Eicar-Test-Signature"))
    desk.receive(ADVOCATE, "note.txt", b"held by the scanner")
    with pytest.raises(Exception):
        desk.receive(ADVOCATE, "film.mp4", b"\x00\x00\x00\x18ftypmp42 not a document")
    assert ledger.may_stop()


def test_may_not_stop_while_a_paper_is_read_or_waits_its_turn_to_be_read(tmp_path):
    ledger = Activity()
    desk = _desk(tmp_path, ledger)
    gates = [Gate() for _ in range(desk.jobs.AT_ONCE + 1)]

    def reading(gate):
        def work(progress):
            gate.pass_through()
            return {"read": True}
        return work
    for number, gate in enumerate(gates):
        desk.jobs.start(ADVOCATE, f"doc-{number}", 1, reading(gate), lambda exc: None)
    assert all(gate.entered.wait(5) for gate in gates[:-1])
    assert ledger.counts() == {"reading": desk.jobs.AT_ONCE + 1}, "the one waiting its turn is held too"
    for gate in gates:
        gate.go.set()
    assert until(ledger.may_stop), ledger.counts()


def test_a_reading_that_fails_is_let_go(tmp_path):
    ledger = Activity()
    desk = _desk(tmp_path, ledger)

    def work(progress):
        raise OSError("the pages could not be kept")
    desk.jobs.start(ADVOCATE, "doc-1", 1, work, lambda exc: {"status": 503, "why": "x", "code": "y"})
    assert until(ledger.may_stop)


def test_a_reading_already_under_way_asked_again_is_not_held_twice(tmp_path):
    ledger, gate = Activity(), Gate()
    desk = _desk(tmp_path, ledger)

    def work(progress):
        gate.pass_through()
        return {"read": True}
    desk.jobs.start(ADVOCATE, "doc-1", 1, work, lambda exc: None)
    assert gate.entered.wait(5)
    desk.jobs.start(ADVOCATE, "doc-1", 1, work, lambda exc: None)
    assert ledger.counts() == {"reading": 1}
    gate.go.set()
    assert until(ledger.may_stop)


def test_may_not_stop_while_the_message_box_is_dictated(served, monkeypatch):
    gate = Gate()

    class Slow(Hearing):
        def transcribe(self, audio, **request):
            gate.pass_through()
            return super().transcribe(audio, **request)
    monkeypatch.setattr(served.app, "dictation_reader", lambda advocate_id, *, session_current: Slow(said="Draft a reply."))
    replies = []
    done, failed = background(lambda: replies.append(served.client.post(
        "/api/dictation", content=wav(), headers={"x-nm-document-name": "dictation.wav"})))
    assert gate.entered.wait(5)
    assert served.app.activity.counts().get("dictation") == 1
    gate.go.set()
    assert done.wait(5) and not failed and replies[0].status_code == 200, (failed, replies)
    assert "dictation" not in served.app.activity.counts()


def test_a_dictation_that_fails_is_let_go(served, monkeypatch):
    from nm.shared.model_port import ProviderUnavailable
    monkeypatch.setattr(served.app, "dictation_reader", lambda advocate_id, *, session_current: Hearing(
        fails=ProviderUnavailable("down")))
    assert served.client.post("/api/dictation", content=wav(),
                              headers={"x-nm-document-name": "dictation.wav"}).status_code == 503
    assert "dictation" not in served.app.activity.counts()


def test_may_not_stop_while_live_words_are_heard(served, monkeypatch):
    from tests.test_live_dictation import ORIGIN, LiveModel, completed, delta
    served.client.post("/api/account/dictation", json={"live": True, "expected_version": 0})
    model = LiveModel([delta("i1", "Draft a reply")],
                      [{"type": "input_audio_buffer.committed", "item_id": "i1"}, completed("i1", "Draft a reply.")])
    monkeypatch.setattr(served.app, "live_dictation_reader", lambda advocate_id, *, session_current: model)
    with served.client.websocket_connect("/ws/dictation", headers=ORIGIN) as socket:
        socket.send_bytes(b"\x00\x00" * 2400)
        assert socket.receive_json() == {"words": "Draft a reply"}
        assert served.app.activity.counts().get("dictation") == 1, "held for the life of the live session"
        socket.send_text("done")
        while "final" not in socket.receive_json():
            pass
    assert until(lambda: "dictation" not in served.app.activity.counts())


def test_may_not_stop_while_a_save_is_written(served, monkeypatch):
    gate = Gate()
    writing = served.store.commit

    def slow(matter, *, expected_version):
        gate.pass_through()
        return writing(matter, expected_version=expected_version)
    monkeypatch.setattr(served.store, "commit", slow)
    matter = Matter(id="m_ledger", advocate_id=OWNER, title="Held while saved", version=1)
    done, failed = background(lambda: served.app.store.commit(matter, expected_version=0))
    assert gate.entered.wait(5)
    assert served.app.activity.counts() == {"save": 1}
    gate.go.set()
    assert done.wait(5) and not failed, failed
    assert served.app.activity.may_stop()
    assert served.app.store.load("m_ledger").title == "Held while saved", "the save itself is the store's, unchanged"


def test_a_save_the_store_refuses_is_let_go(served):
    from nm.shared.store_port import StaleWrite
    matter = Matter(id="m_ledger_two", advocate_id=OWNER, title="Refused", version=1)
    with pytest.raises(StaleWrite):
        served.app.store.commit(matter, expected_version=3)
    assert served.app.activity.may_stop()


def test_a_signed_in_action_is_the_sign_of_life_quiet_runs_from_and_a_visitors_request_is_not(served):
    now = [5000.0]
    served.app.activity = Activity(clock=lambda: now[0])
    now[0] += 120
    with TestClient(api.app) as visitor:
        assert visitor.get("/api/health").status_code == 200
    assert served.app.activity.quiet_for() == 120, "a request no one is signed in for is no sign of life"
    assert served.client.get("/api/work").status_code == 200
    assert served.app.activity.quiet_for() == 0, "a signed-in advocate's request is"
    now[0] += 30
    assert served.app.activity.quiet_for() == 30
