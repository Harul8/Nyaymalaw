"""The new read transport cannot expose unchecked work or authorize its own preview."""
from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from nm.core.brain_release import ReviewRefused
from nm.core.reviewed_preview import MARKER, ReviewedPreviewService
from nm.edge.reviewed_preview import router

from tests.test_reviewed_private_preview_checks_saved_words import ready

pytestmark = pytest.mark.class_a
PATH = "/api/matters/mat_loop/brain/reviewed-preview/private-turn"


def configured(tmp_path, **kwargs):
    store, brain, _, _, _, _, _ = ready(tmp_path, **kwargs)
    state = {"active": True, "grant": True}

    def signed_in(request: Request):
        if request.headers.get("x-test-session") != "active" or not state["active"]:
            raise HTTPException(401, "Sign in again.")
        return "adv_loop"

    def owned(ident, actor):
        matter = store.load(ident)
        if matter is None or matter.advocate_id != actor:
            raise HTTPException(404, "Matter unavailable.")
        return matter

    def read(*, session_current, **arguments):
        if state.get("read_failure"):
            raise state["read_failure"]
        result = ReviewedPreviewService(brain=brain,
            current=lambda: state["grant"] and session_current()).read(**arguments)
        after = state.get("after_read")
        if after:
            after()
        return result

    app = FastAPI()
    app.include_router(router(owned=owned, signed_in=signed_in,
        session_current=lambda _request, _actor: state["active"], read=read))
    return TestClient(app, headers={"x-test-session": "active"}), store, brain, state, app


def test_served_exact_saved_preview_is_private_uncacheable_and_no_normal_history(tmp_path):
    client, store, brain, _, _ = configured(tmp_path)
    before = store.load("mat_loop")
    brain.model.tool_call.side_effect = lambda *_args, **_kwargs: pytest.fail("No author spend")
    brain.finalizer.reader.model.structured = lambda *_args, **_kwargs: pytest.fail(
        "No check spend")
    brain.reviewer.verifier.model.structured = lambda *_args, **_kwargs: pytest.fail(
        "No judge spend")
    served = client.get(PATH)
    assert served.status_code == 200, served.text
    assert served.json()["marker"] == MARKER
    assert served.json()["paragraphs"][0]["text"] == "The benefit depends on notice."
    assert served.headers["cache-control"] == "no-store"
    assert served.headers["x-content-type-options"] == "nosniff"
    assert served.json()["released"] is False and served.json()["client_ready"] is False
    assert store.load("mat_loop") == before and not before.turn_receipts
    assert not store.transcripts_for("mat_loop")


def test_http_scope_or_pass_parameters_cannot_enable_preview_and_logout_closes_read(tmp_path):
    client, _, _, state, _ = configured(tmp_path)
    state["grant"] = False
    result = client.get(PATH, params={"scope": "self-approved", "checks_complete": "true",
                                     "consent": "true", "advocate_id": "adv_loop"})
    assert result.status_code == 403 and "depends on notice" not in result.text
    assert result.headers["cache-control"] == "no-store"
    state["grant"] = True
    state["active"] = False
    assert client.get(PATH).status_code == 401


@pytest.mark.parametrize("kind", ["unassessed", "question", "unknown_turn"])
def test_transport_never_leaks_a_present_candidate_or_unreviewed_question(tmp_path, kind):
    client, _, _, _, _ = configured(tmp_path, incomplete=kind == "unassessed",
        terminal="ask_advocate" if kind == "question" else "submit_answer")
    served = client.get(PATH.replace("private-turn", "absent") if kind == "unknown_turn" else PATH)
    assert served.status_code == 200
    assert not served.json()["paragraphs"] and "PRIVATE UNREVIEWED" not in served.text
    assert "The benefit depends on notice." not in served.text


def test_before_and_after_owned_file_and_session_are_rechecked(tmp_path):
    client, store, _, state, _ = configured(tmp_path)
    # The actual read result is checked against a file changed by another writer.
    def changed():
        matter = store.load("mat_loop")
        store.commit(replace(matter, version=matter.version + 1), expected_version=matter.version)

    state["after_read"] = changed
    assert client.get(PATH).status_code == 409
    state["after_read"] = lambda: state.__setitem__("active", False)
    assert client.get(PATH).status_code == 401


def test_error_details_never_echo_withheld_model_text(tmp_path):
    client, _, _, state, _ = configured(tmp_path)
    state["read_failure"] = ReviewRefused("PRIVATE WITHHELD MODEL WORDS")
    served = client.get(PATH)
    assert served.status_code == 409 and "PRIVATE WITHHELD" not in served.text
    assert served.headers["cache-control"] == "no-store"
