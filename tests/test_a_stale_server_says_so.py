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

import nm.app.api as api

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

def test_health_no_longer_carries_the_state_to_a_visitor(client):
    """CHANGED BY PLAN AN.52 (52a3, D207), 13 Nov 2026. This test held that the build state, with both fingerprints, reaches
    the page from `/api/health` BEFORE the session resolves, so the banner could show on the sign-in screen. D207 takes the
    code's fingerprints out of what anyone not signed in is told: the public answer is up or down only, and the state (without
    fingerprints) is at /api/health/detail for a signed-in advocate - tested in
    tests/test_the_public_health_answer_says_up_or_down_only.py. The banner therefore no longer shows on the sign-in screen;
    since AN.48 the server restarts itself when its code changes on disk, which is what the banner asked a person to do."""
    body = client.get("/api/health").json()
    assert body == {"status": "up"}
    assert api.SERVING not in str(body)


def test_health_needs_no_session(client):
    """It still answers a visitor: that the server is up."""
    assert client.get("/api/health").status_code == 200


def test_the_page_shows_the_build_once_signed_in_and_not_before():
    """CHANGED BY PLAN AN.52 (52a4, D207), 13 Nov 2026. This test held that the page checks the build in boot(), before the
    session call, so that the banner showed on the sign-in screen - where, on 6 Sept 2026, a registration was refused by a rule
    three commits old. D207 tells a visitor nothing of the code (the public answer is up or down only), so the page cannot
    know it before sign-in: it reads the state once signed in, from the same answer as the library's line, and takes the banner
    down when the sign-in screen is shown. What that costs is said here, not hidden: a stale server is no longer named on the
    sign-in screen; since AN.48 the server restarts itself when its code changes on disk. The page's behaviour is tested in
    tests/test_the_page_reads_the_servers_state_once_signed_in.py."""
    import pathlib

    script = (pathlib.Path(__file__).resolve().parents[1]
              / "nm/app/app.js").read_text(encoding="utf-8")
    boot = script[script.index("async function boot()"):]
    boot = boot[:boot.index("\n}")]
    assert "/api/health" not in boot and "showBuild" not in boot, (
        "boot() asks about the build before anyone has signed in; the address that answers a visitor says up or down only, "
        "so the banner would read 'could not be identified' for everyone")
    signed_in = script[script.index("async function loadHealth() {"):]
    signed_in = signed_in[:signed_in.index("\n}")]
    assert "/api/health/detail" in signed_in and "showBuild(h)" in signed_in and "showBuild(null, e)" in signed_in, (
        "the state of the build is shown from the signed-in answer, and a failed asking is not an all-clear")
