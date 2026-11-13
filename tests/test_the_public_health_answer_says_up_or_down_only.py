"""The public health answer says up or down only; the detail is behind sign-in (plan AN.52, 52a3, D207; the review's
F-11).

/api/health answered anyone - signed in or not - with the provider's name, the model's name, the fingerprints of the
running code and of the code on disk, where the steps are worked and how many wait, and 'runtime: ready' whatever was
true. It now answers a visitor with one word, up or down, from what readiness last measured (52a1). What the page
needs is at /api/health/detail for a signed-in advocate: whether the library can be read (from the measured
readiness, no longer 'configured_unverified' for ever), how the steps stand, whether the running code is the code on
disk, and each capability's state - and no provider, model, fingerprint, or reason that could hold a path.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nm.app import api
from nm.app.composition import NOT_CHECKED, NOT_READY, READY
from tests.test_core_served import served  # noqa: F401 - served is a fixture
from tests.test_steps_in_a_worker_of_their_own import split, until  # noqa: F401 - split is a fixture

pytestmark = pytest.mark.class_a

NEVER_PUBLIC = ("provider", "model", "serving", "tree", "steps", "brain", "corpus", "readiness", "why", "code_state")
NEVER_IN_DETAIL = ("provider", "model", "serving", "tree", "brain")
LAW = ("the held law: provision", "the held law: judgment")


def _measured(served, monkeypatch, **states):
    """Readiness as last measured, given by state; everything not named is ready."""
    names = ("the store", *LAW, "the malware scanner", "account mail", "the AI service")
    measured = {name: {"state": states.get(name, READY), "why": "a reason naming /srv/nm/library/index.faiss"} for name in names}
    monkeypatch.setattr(served.app, "readiness", lambda measure=True: measured)


def test_a_visitor_is_told_up_and_nothing_else(served):
    with TestClient(api.app) as visitor:
        answer = visitor.get("/api/health")
    assert answer.status_code == 200 and answer.json() == {"status": "up"}
    assert not any(name in answer.text for name in NEVER_PUBLIC)
    assert "scripted" not in answer.text and api.SERVING not in answer.text


def test_a_capability_measured_not_ready_is_down_for_a_visitor_and_which_is_not_said(served, monkeypatch):
    _measured(served, monkeypatch, **{"the malware scanner": NOT_READY})
    with TestClient(api.app) as visitor:
        answer = visitor.get("/api/health")
    assert answer.status_code == 503 and answer.json() == {"status": "down"}
    assert "scanner" not in answer.text and "/srv/nm" not in answer.text


def test_what_is_only_not_checked_is_not_down(served, monkeypatch):
    _measured(served, monkeypatch, **{"account mail": NOT_CHECKED, "the AI service": NOT_CHECKED})
    with TestClient(api.app) as visitor:
        assert visitor.get("/api/health").json() == {"status": "up"}


def test_an_application_that_cannot_be_asked_is_down_not_a_server_error(monkeypatch):
    def refused():
        raise RuntimeError("configuration refused")
    monkeypatch.setattr(api, "application", refused)
    with TestClient(api.app) as visitor:
        answer = visitor.get("/api/health")
    assert answer.status_code == 503 and answer.json() == {"status": "down"} and "refused" not in answer.text


def test_the_detail_is_refused_to_a_visitor(served):
    with TestClient(api.app) as visitor:
        assert visitor.get("/api/health/detail").status_code == 401


def test_a_signed_in_advocate_is_told_what_the_page_needs_and_no_provider_model_or_fingerprint(served, monkeypatch):
    _measured(served, monkeypatch)
    answer = served.client.get("/api/health/detail")
    assert answer.status_code == 200
    detail = answer.json()
    assert set(detail) == {"runtime", "corpus", "steps", "rehearsal", "code_state", "readiness"}
    assert detail["steps"] == {"mode": "inside", "waiting": 0, "working": 0}, "how the steps stand (D167), now behind sign-in"
    assert detail["rehearsal"] is True, "a stand-in model is said as a rehearsal, not by the provider's name"
    assert detail["code_state"] == "current"
    assert set(detail["readiness"].values()) == {READY} and "the store" in detail["readiness"], "each state, and no reason"
    assert not any(name in detail for name in NEVER_IN_DETAIL)
    assert "/srv/nm" not in answer.text and api.SERVING not in answer.text and "scripted" not in answer.text


@pytest.mark.parametrize("states, said", [
    ({}, "readable"),
    ({LAW[0]: NOT_READY}, "NOT READABLE"),
    ({LAW[1]: NOT_READY}, "NOT READABLE"),
    ({LAW[0]: NOT_CHECKED}, "configured_unverified"),
    ({LAW[0]: NOT_CHECKED, LAW[1]: NOT_READY}, "NOT READABLE"),
], ids=["both ready", "provisions not ready", "judgments not ready", "one not checked", "not checked and not ready"])
def test_whether_the_library_can_be_read_is_what_readiness_measured(served, monkeypatch, states, said):
    _measured(served, monkeypatch, **states)
    assert served.client.get("/api/health/detail").json()["corpus"] == said


def test_before_anything_is_measured_the_library_is_not_said_to_be_readable(served):
    assert served.client.get("/api/health/detail").json()["corpus"] == "configured_unverified"


def test_no_search_connected_is_said_as_not_connected(served, monkeypatch):
    monkeypatch.setattr(served.app, "legal_search", None)
    assert served.client.get("/api/health/detail").json()["corpus"] == "not_connected"


def test_a_server_running_code_that_is_no_longer_on_disk_says_so_without_a_fingerprint(served, monkeypatch):
    monkeypatch.setattr(api, "source_fingerprint", lambda: "another-tree-fingerprint")
    answer = served.client.get("/api/health/detail")
    detail = answer.json()
    assert detail["code_state"] == "stale" and "Restart" in detail["why"]
    assert "another-tree-fingerprint" not in answer.text and api.SERVING not in answer.text
    with TestClient(api.app) as visitor:
        assert visitor.get("/api/health").json() == {"status": "up"}, "a visitor is told nothing of the code"


def test_a_web_server_whose_step_worker_is_not_heard_from_is_down_and_up_once_it_is(split):
    """What an outside monitor read from the steps line (D167), in the one word it is now given."""
    with TestClient(api.app) as visitor:
        answer = visitor.get("/api/health")
        assert answer.status_code == 503 and answer.json() == {"status": "down"}
        split.start_worker()
        assert until(lambda: visitor.get("/api/health").json() == {"status": "up"})
