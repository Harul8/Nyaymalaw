"""A running process that is behind its own tree reports it.

WHAT HAPPENED THREE TIMES ON 6 SEPTEMBER 2026, IN ONE SESSION
---------------------------------------------------------------
Each looked like a product defect, and each cost a round trip:

    the browser held a cached `app.js`, so Register did nothing;
    :8071 had no `/api/register` at all, three commits behind;
    :8078 served the 12-character password rule after it became 8.

The last was reported with a screenshot of the OLD refusal message, against a
fix that was already committed and green on a full gate. The code was right,
the running thing was old, and NOTHING ANYWHERE SAID SO.

WHY THE SERVER AND NOT A TOOL
-------------------------------
The comparison needs both numbers and the server is the only party holding
them: the fingerprint it froze at import — what it is RUNNING — and the
fingerprint of the tree now. The browser cannot see the tree; the tree cannot
see the process.

A tool would have caught all three and nobody would have run it. That is R-6
in the risk register, in its own words: apparatus that runs when someone has
time is decoration.

THE THIRD STATE IS A VALUE, NOT A NULL
----------------------------------------
`code_state` is `current` / `stale` / `not_assessed`, never a bool. A
fingerprint that could not be computed must not read as "nothing has changed"
— that is defect shape S1 arriving on the check built to catch S1, which this
project has already paid for once (B-110).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import nm.edge.api as api

pytestmark = pytest.mark.class_a


class _App:
    """Only what `/api/health` reaches.

    A whole `Application` needs a corpus, a model and an authority index. The
    build state is deliberately NOT one of its dependencies -- a server can be
    misconfigured in every other way and still has to be able to say what code
    it is running, because that is often the reason it is misconfigured.
    """

    def health(self) -> dict:
        return {"corpus": "readable"}


@pytest.fixture()
def client():
    was = api._application
    api.set_application(_App())
    try:
        with TestClient(api.app) as c:
            yield c
    finally:
        api.set_application(was)


# ================================= the states ===============================

def test_a_current_server_says_current():
    """The tree has not moved since import, which is the case in every test
    run — so this is also the assertion that the check is not simply always
    firing."""
    state = api.serving_state()
    assert state["code_state"] == "current", state
    assert state["serving"] == state["tree"]
    assert "why" not in state, (
        "a server running current code explained itself, which means the "
        "banner has something to show on every ordinary boot")


def test_a_stale_server_says_stale_and_names_both_numbers(monkeypatch):
    """THE DEFECT, AS A RULE — and the POSITIVE CONTROL for the whole
    mechanism. The tree cannot be moved from inside a test, so what is moved
    is the frozen import-time number, which is the same comparison seen from
    the other end."""
    monkeypatch.setattr(api, "SERVING", "0000feedface0000")
    state = api.serving_state()

    assert state["code_state"] == "stale"
    assert state["serving"] == "0000feedface0000"
    assert state["tree"] != "0000feedface0000"
    # BOTH NUMBERS, because "stale" alone does not tell anyone which of the
    # two things they are holding is the old one.
    assert "0000feedface0000" in state["why"]
    assert state["tree"] in state["why"]
    assert "Restart" in state["why"]


def test_an_unknown_fingerprint_is_not_an_all_clear(monkeypatch):
    """S1, on the check built to catch S1. `SERVING` records the failure in
    words at import; a comparison that read that string as an ordinary digest
    would announce a mismatch it did not measure, and one that fell back to
    `current` would announce agreement it did not measure either."""
    monkeypatch.setattr(api, "SERVING", "unknown: PermissionError")
    state = api.serving_state()

    assert state["code_state"] == "not_assessed"
    assert state["tree"] == "not assessed"
    assert state["why"]


def test_a_tree_that_cannot_be_read_is_not_an_all_clear(monkeypatch):
    """The other half. The frozen number is fine and the tree cannot be
    fingerprinted — a permission change, a file removed mid-walk."""
    def boom():
        raise OSError("no")

    monkeypatch.setattr(api, "source_fingerprint", boom)
    state = api.serving_state()
    assert state["code_state"] == "not_assessed"
    assert state["tree"].startswith("unknown:")


# ============================== on the wire =================================

def test_health_carries_the_state(client):
    """It has to reach the page, and `/api/health` is what the page asks —
    BEFORE the session resolves, because the thing this catches happens on the
    gate."""
    body = client.get("/api/health").json()
    assert body["code_state"] in ("current", "stale", "not_assessed")
    assert body["serving"] and body["tree"]


def test_health_needs_no_session(client):
    """Or the banner cannot appear on the sign-in screen, which is exactly
    where the stale password rule was refusing registrations."""
    assert client.get("/api/health").status_code == 200


def test_the_page_checks_before_the_session_resolves():
    """A check wired after sign-in would have missed all three incidents."""
    import pathlib

    script = (pathlib.Path(__file__).resolve().parents[1]
              / "web" / "app.js").read_text(encoding="utf-8")
    boot = script[script.index("async function boot()"):]
    boot = boot[:boot.index("\n}")]
    assert "checkBuild()" in boot, (
        "boot() does not check the build, so the banner appears only after a "
        "successful sign-in -- and the registration screen is where the stale "
        "rule was refusing people")
    assert boot.index("checkBuild()") < boot.index("/api/session"), (
        "the build check runs after the session call, so a server too old to "
        "answer /api/session reports a connection problem instead of its age")
