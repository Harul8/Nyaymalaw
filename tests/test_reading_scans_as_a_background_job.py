"""Reading scanned pages is a background job with page-by-page progress (plan AN.25, P4).

A 20-page scan was read inside one request that the browser held for 80 seconds or more, with a chip that said only "reading scans"; a
proxy that cuts requests at 60 seconds would have refused a scan of about 25 pages. The reading is now started once and asked after: a
job of the advocate's own, kept for a while after it ends, that says how many pages are read, how it ended and why if it failed. A
failure it is known to end in is told in plain words; any other is logged with its traceback and told plainly, never hidden. The
permission to share with the AI is checked before the job begins. The pages here are synthetic.
"""
import logging
import threading
import time

import pytest
from fastapi.testclient import TestClient

from nm.app import api
from nm.app.documents import ReadingJobs
from nm.core_engine import page_reading
from nm.core_engine.documents import DocumentRefused
from nm.shared.external_ai_contracts import ModelPermissionRefused
from nm.shared.model_port import USAGE_LIMIT_MESSAGE, ModelError, ModelResult, Usage, UsageLimitReached
from tests.test_core_document_routes import desk, upload  # noqa: F401 - pytest fixtures and helper
from tests.test_core_documents import pdf
from tests.test_core_served import OTHER, OWNER, served  # noqa: F401 - pytest fixture
from tests.test_pages_are_read_many_at_once_within_one_shared_limit import Counting, images

pytestmark = pytest.mark.class_a


def test_the_pages_read_are_counted_as_each_is_read_one_at_a_time():
    seen = []
    read, _ = page_reading.read_pages(Counting(hold=0.01), "scan.pdf", images(5), progress=lambda done, total: seen.append((done, total)))
    assert seen == [(1, 5), (2, 5), (3, 5), (4, 5), (5, 5)] and sorted(read) == [1, 2, 3, 4, 5]
    assert sorted(page_reading.read_pages(Counting(hold=0.0), "scan.pdf", images(3))[0]) == [1, 2, 3], "progress is optional"


def explain(exc):
    return {"status": 503, "why": "The pages could not be read just now. Try again.", "code": "document_reading_unavailable"} \
        if isinstance(exc, ConnectionError) else None


def wait_until(jobs, advocate, ref, wanted, seconds=5):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        shown = jobs.status(advocate, ref)
        if shown is not None and wanted(shown):
            return shown
        time.sleep(0.01)
    raise AssertionError(f"the job did not reach what was wanted: {jobs.status(advocate, ref)}")


def test_a_job_says_where_it_stands_and_how_it_ended_and_asking_again_does_not_start_another():
    jobs, gate, calls = ReadingJobs(), threading.Event(), []

    def work(progress):
        calls.append(1)
        progress(1, 3)
        assert gate.wait(5)
        progress(3, 3)
        return {"name": "memo.pdf", "pages_read": 3}
    first = jobs.start("a", "doc_1", 3, work, explain)
    assert first["state"] == "reading" and first["total"] == 3
    assert wait_until(jobs, "a", "doc_1", lambda s: s["done"] == 1)["state"] == "reading"
    assert jobs.start("a", "doc_1", 3, work, explain)["state"] == "reading" and calls == [1], "one job, however often it is started"
    gate.set()
    ended = wait_until(jobs, "a", "doc_1", lambda s: s["state"] == "done")
    assert (ended["done"], ended["total"], ended["document"]) == (3, 3, {"name": "memo.pdf", "pages_read": 3})
    ended["document"]["name"] = "changed"
    assert jobs.status("a", "doc_1")["document"]["name"] == "memo.pdf", "what is told is a copy"
    assert jobs.status("b", "doc_1") is None and jobs.status("a", "doc_2") is None, "a job is its advocate's and its document's"


def test_a_failure_the_reading_is_known_to_end_in_is_told_in_plain_words_and_any_other_is_logged_not_hidden(caplog):
    jobs = ReadingJobs()

    def known(progress):
        raise ConnectionError("provider down")

    def unknown(progress):
        raise KeyError("a defect")
    jobs.start("a", "doc_1", 2, known, explain)
    assert wait_until(jobs, "a", "doc_1", lambda s: s["state"] == "failed")["error"]["code"] == "document_reading_unavailable"
    with caplog.at_level(logging.ERROR):
        jobs.start("a", "doc_2", 2, unknown, explain)
        failed = wait_until(jobs, "a", "doc_2", lambda s: s["state"] == "failed")
    assert failed["error"] == {"status": 500, "why": "The pages could not be read just now. Try again.",
                               "code": "document_reading_failed"}
    assert any("nobody expected" in record.getMessage() and record.exc_info for record in caplog.records)


def test_a_job_is_kept_for_a_while_after_it_ends_then_forgotten_and_a_new_one_may_begin():
    now = [0.0]
    jobs = ReadingJobs(clock=lambda: now[0])
    jobs.start("a", "doc_1", 1, lambda progress: {"n": 1}, explain)
    wait_until(jobs, "a", "doc_1", lambda s: s["state"] == "done")
    now[0] = ReadingJobs.KEPT - 1
    assert jobs.status("a", "doc_1") is not None
    jobs.start("a", "doc_1", 1, lambda progress: {"n": 2}, explain)
    assert wait_until(jobs, "a", "doc_1", lambda s: s["document"] == {"n": 2})["state"] == "done", "reading again begins again"
    now[0] += ReadingJobs.KEPT + 1
    assert jobs.status("a", "doc_1") is None
    gate = threading.Event()
    jobs.start("a", "doc_3", 1, lambda progress: gate.wait(5) and {"n": 3}, explain)
    now[0] += 10 * ReadingJobs.KEPT
    assert jobs.status("a", "doc_3")["state"] == "reading", "a job still running is never forgotten"
    gate.set()


class Pages:
    """Reads each page as 'Page N words.'; the page named in `hold` waits until released, and `refuse` raises the permission refusal."""

    def __init__(self, hold=None, refuse=None):
        self.hold, self.refuse, self.release = hold, refuse, threading.Event()

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        number = int(prompt.user.split()[1])
        if number == self.refuse:
            raise ModelPermissionRefused("Read the current AI data-sharing notice before continuing.")
        if number == self.hold:
            assert self.release.wait(10)
        return ModelResult(text=None, data={"text": f"Page {number} words.", "readable": "all", "note": ""}, tier=tier,
                           provider="scripted", model="page-model-1", usage=Usage(1, 1, 0.0), latency_ms=1)


def scan(served, pages=3):
    return upload(served.client, data=pdf([""] * pages), name="scan.pdf").json()


def ask(served, ref, until, seconds=8):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        reply = served.client.get(f"/api/documents/{ref}/reading")
        assert reply.status_code == 200, reply.text
        if until(reply.json()):
            return reply
        time.sleep(0.02)
    raise AssertionError(f"not reached: {reply.json()}")


def test_the_advocate_starts_a_reading_and_asks_after_it_page_by_page_until_it_is_done(served, desk, monkeypatch):
    shown, model = scan(served), Pages(hold=3)
    assert shown["waiting_for_ai"] == 3
    monkeypatch.setattr(served.app, "document_reader", lambda advocate_id, *, session_current: model)
    url = f"/api/documents/{shown['document_ref']}/reading"
    started = served.client.post(url)
    assert started.status_code == 202 and started.json()["state"] in ("reading", "done") and started.json()["total"] == 3
    middle = ask(served, shown["document_ref"], lambda s: s["done"] == 2 and s["state"] == "reading")
    assert middle.headers["cache-control"] == "no-store" and "document" not in middle.json()
    model.release.set()
    ended = ask(served, shown["document_ref"], lambda s: s["state"] == "done").json()
    assert (ended["done"], ended["total"]) == (3, 3)
    assert ended["document"]["pages_read_by_ai"] == 3 and ended["document"]["document_ref"] != shown["document_ref"]
    assert "words" not in str(ended), "the summary carries no page text"


def test_the_reading_is_the_advocates_own_and_needs_this_pages_csrf_value(served, desk, monkeypatch):
    shown = scan(served)
    monkeypatch.setattr(served.app, "document_reader", lambda advocate_id, *, session_current: Pages())
    url = f"/api/documents/{shown['document_ref']}/reading"
    assert served.client.post(url, headers={"x-nm-csrf": "wrong"}).status_code == 403
    assert served.login(OTHER).post(url).status_code == 404
    assert served.client.post(url).status_code == 202
    assert served.login(OTHER).get(url).status_code == 404, "nobody else can ask after it"
    ask(served, shown["document_ref"], lambda s: s["state"] == "done")


def test_without_ai_permission_the_reading_is_refused_before_a_job_begins(served, desk, monkeypatch):
    shown = scan(served)

    def document_reader(advocate_id, *, session_current):
        raise ModelPermissionRefused("Read the current AI data-sharing notice before continuing.")
    monkeypatch.setattr(served.app, "document_reader", document_reader)
    refused = served.client.post(f"/api/documents/{shown['document_ref']}/reading")
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "model_permission_required"
    assert served.client.get(f"/api/documents/{shown['document_ref']}/reading").status_code == 404


def test_a_refusal_during_the_reading_ends_the_job_failed_with_why(served, desk, monkeypatch):
    shown = scan(served)
    monkeypatch.setattr(served.app, "document_reader", lambda advocate_id, *, session_current: Pages(refuse=2))
    served.client.post(f"/api/documents/{shown['document_ref']}/reading")
    failed = ask(served, shown["document_ref"], lambda s: s["state"] == "failed").json()
    assert failed["error"]["code"] == "model_permission_required" and failed["error"]["status"] == 403
    assert "document" not in failed


@pytest.mark.parametrize("failure, status, code", [
    (ModelPermissionRefused("Read the current AI data-sharing notice before continuing."), 403, "model_permission_required"),
    (UsageLimitReached("the provider has no quota left"), 402, "usage_limit"),
    (ModelError("the provider could not be reached"), 503, "document_reading_unavailable"),
    (DocumentRefused("This document's original is not available."), 404, "document_unavailable"),
    (OSError("the disk is full"), 503, "document_storage"),
    (KeyError("a defect nobody expected"), 500, "document_reading_failed"),
])
def test_each_way_a_reading_can_end_is_told_in_its_own_words(served, desk, monkeypatch, failure, status, code):
    shown = scan(served)

    def read_waiting(advocate_id, ref, model, progress=None):
        raise failure
    monkeypatch.setattr(desk, "read_waiting", read_waiting)
    monkeypatch.setattr(served.app, "document_reader", lambda advocate_id, *, session_current: object())
    served.client.post(f"/api/documents/{shown['document_ref']}/reading")
    told = ask(served, shown["document_ref"], lambda s: s["state"] == "failed").json()["error"]
    assert (told["status"], told["code"]) == (status, code)
    assert "defect nobody" not in told["why"] and "provider" not in told["why"], "a failure's own words are not told, only the plain ones"
    if status == 402:
        assert told["why"] == USAGE_LIMIT_MESSAGE


def test_a_used_up_allowance_is_told_in_the_owners_words_before_a_job_begins(served, desk, monkeypatch):
    shown = scan(served)

    def document_reader(advocate_id, *, session_current):
        raise UsageLimitReached("the provider has no quota left")
    monkeypatch.setattr(served.app, "document_reader", document_reader)
    refused = served.client.post(f"/api/documents/{shown['document_ref']}/reading")
    assert refused.status_code == 402 and refused.json()["detail"] == {"why": USAGE_LIMIT_MESSAGE, "code": "usage_limit"}
    assert served.client.get(f"/api/documents/{shown['document_ref']}/reading").status_code == 404


def test_a_document_with_nothing_waiting_is_done_at_once_and_no_one_is_asked_to_read(served, desk, monkeypatch):
    def document_reader(advocate_id, *, session_current):
        raise AssertionError("no reader is needed")
    monkeypatch.setattr(served.app, "document_reader", document_reader)
    shown = upload(served.client).json()
    url = f"/api/documents/{shown['document_ref']}/reading"
    reply = served.client.post(url)
    assert reply.status_code == 202 and reply.json()["state"] == "done" and reply.json()["document"] == shown
    assert served.client.get(url).status_code == 404, "no job was begun for it"


def test_a_permission_refusal_once_the_session_has_ended_sends_the_advocate_back_to_sign_in(served, desk, monkeypatch):
    shown = scan(served)

    def document_reader(advocate_id, *, session_current):
        raise ModelPermissionRefused("This session has ended.")
    monkeypatch.setattr(served.app, "document_reader", document_reader)
    real, asked = api._session_current, []

    def current(request, advocate_id):
        asked.append(1)
        return len(asked) == 1 and real(request, advocate_id)
    monkeypatch.setattr(api, "_session_current", current)
    assert served.client.post(f"/api/documents/{shown['document_ref']}/reading").status_code == 401


def test_asking_after_a_reading_that_never_began_or_is_gone_is_not_found(served, desk):
    shown = scan(served)
    gone = served.client.get(f"/api/documents/{shown['document_ref']}/reading")
    assert gone.status_code == 404 and gone.json()["detail"]["code"] == "reading_not_found"
    with TestClient(api.app) as anonymous:
        assert anonymous.get(f"/api/documents/{shown['document_ref']}/reading").status_code == 401
