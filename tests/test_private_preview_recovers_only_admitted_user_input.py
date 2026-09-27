"""Served history distinguishes real user instructions from checked model words."""
from dataclasses import replace

import pytest
from nm.core.original_instruction import OriginalInstruction
from nm.core.reviewed_preview import ReviewedPreview
from nm.domain.loop import digest

from tests.test_private_brain_transport_cannot_approve_or_release_itself import (
    PRIVATE,
    path,
    request,
)
from tests.test_scoped_preview_uses_the_actual_application_boundary import approved, preview

pytestmark = pytest.mark.class_a


def test_actual_owned_get_recovers_original_input_separately_without_another_dispatch(client):
    app, matter, author, judges = approved(client)
    submitted = request(matter)
    assert client.post(path(matter), json=submitted).status_code == 200
    before = app.store.load(matter.id)
    shown = client.get(preview(matter))
    assert shown.status_code == 200, shown.text
    original = shown.json()["original_instruction"]
    assert original["state"] == "recorded" and original["text"] == submitted["message"]
    assert original["text_identity"] == digest(submitted["message"])
    assert original["material_kind"] == "advocate_original_instruction"
    assert original["trust"] == "user_instruction_not_established_fact_or_legal_authority"
    assert PRIVATE not in str(original)
    assert shown.json()["paragraphs"] == [{"text": PRIVATE, "references": []}]
    assert shown.json()["released"] is shown.json()["client_ready"] is False
    assert client.get(preview(matter)).json() == shown.json()
    assert app.store.load(matter.id) == before
    assert author.tool_call.call_count == 1 and sum(len(j.prompts) for j in judges) == 1


def test_wording_owner_absence_does_not_erase_saved_user_input_or_expose_model_words(client):
    app, matter, author, _ = approved(client)
    app.controlled_evaluations = (replace(app.controlled_evaluations[0],
                                         review_interactions=False),)
    submitted = request(matter)
    assert client.post(path(matter), json=submitted).status_code == 200
    shown = client.get(preview(matter))
    assert shown.status_code == 200 and shown.json()["result_state"] == "wording_review_pending"
    assert shown.json()["original_instruction"]["text"] == submitted["message"]
    assert not shown.json()["paragraphs"] and PRIVATE not in shown.text
    assert author.tool_call.call_count == 1


def test_unknown_turn_has_an_explicit_absent_input_not_a_reconstruction(client):
    app, matter, author, judges = approved(client)
    before = app.store.load(matter.id)
    shown = client.get(preview(matter))
    assert shown.status_code == 200
    assert shown.json()["original_instruction"] == OriginalInstruction("not_recorded").as_dict()
    assert not shown.json()["paragraphs"]
    assert app.store.load(matter.id) == before
    assert author.tool_call.call_count == 0 and not judges[0].prompts


def test_original_input_is_not_a_checked_paragraph_or_display_subject():
    original = OriginalInstruction("recorded", "Exact supplied words",
                                   digest("Exact supplied words"),
                                   "sealed_first_dispatch")
    body = ReviewedPreview("matter", "turn", 1, original_instruction=original).as_dict()
    assert not body["paragraphs"] and body["original_instruction"]["text"] == original.text
    assert body["result_state"] == "not_available"
    assert body["released"] is body["client_ready"] is False
