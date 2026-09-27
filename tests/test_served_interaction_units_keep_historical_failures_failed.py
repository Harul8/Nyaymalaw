"""Real ASGI/private display path: code owns coverage, reviewers judge meaning."""
import json
from dataclasses import replace

import pytest

from nm.legal_brain.brain_release import ReviewService
from nm.legal_brain.interaction_review import COMMUNICATION_UNIT_REVIEW_SCHEMA, CRITERIA
from nm.legal_brain.preview_display import displayed_questions
from nm.legal_brain.verifier import IndependentVerifier
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Tier, Usage
from nm.shared.store_loop_log import MatterLoopLog
from tests.test_interaction_words_require_an_independent_exact_review import InteractionJudge
from tests.test_private_brain_transport_cannot_approve_or_release_itself import (
    PRIVATE,
    path,
    request,
)
from tests.test_scoped_preview_uses_the_actual_application_boundary import approved, preview

pytestmark = pytest.mark.class_a


class UnitJudge(InteractionJudge):
    def structured(self, prompt, schema, tier, **_kwargs):
        assert schema == COMMUNICATION_UNIT_REVIEW_SCHEMA and tier is Tier.JUDGE
        self.prompts.append(prompt)
        packet = json.loads(prompt.user)
        unit = packet["review_units"][0]
        subject = packet["subject"]
        words = [{"source_id": "proposed_text", "quote": unit["text"]},
                 {"source_id": "original_instruction", "quote": subject["original_instruction"]}]
        data = {"subject_identity": packet["subject_identity"],
            "units": [{"unit_id": unit["unit_id"], "kind": "question",
                       "reason": "The whole supplied unit is a controlled information request",
                       "supporting_words": [words[0]]}],
            **{name: {"assessed": True, "reason": "Controlled distinct-model assessment",
                      "supporting_words": words} for name in CRITERIA}}
        return ModelResult(None, data, tier, self.provider, self.resolved_model(tier),
                           Usage(80, 80, 0.02), 1, completion=Completion.COMPLETE)


def unit_approved(client):
    app, matter, author, _ = approved(client)
    judges = []

    def reviewer(application, scope, current):
        judge = UnitJudge()
        judges.append(judge)
        return ReviewService(store=application.store,
            log=MatterLoopLog(application.store, advocate_id=scope.advocate_id),
            verifier=IndependentVerifier(judge), session_current=current,
            cost_ceiling=app.controlled_evaluations[0].cost_ceiling)

    app.controlled_evaluations = (replace(app.controlled_evaluations[0],
        reviewer_factory=reviewer, interaction_protocol_version=2),)
    return app, matter, author, judges


def test_actual_version_two_get_display_and_historical_question_replay_are_one_owned_path(client):
    app, matter, author, judges = unit_approved(client)
    response = client.post(path(matter), json=request(matter))
    assert response.status_code == 200, response.text
    shown = client.get(preview(matter))
    assert shown.status_code == 200, shown.text
    assert shown.json()["paragraphs"] == [{"text": PRIVATE, "references": []}]
    assert shown.json()["original_instruction"]["text"] == request(matter)["message"]
    before = app.store.load(matter.id)
    assert any(row.identity.turn_id.endswith(":check:communication_units")
               for row in before.loop_records)
    seen = client.post(f"{preview(matter)}/seen", json={})
    assert seen.status_code == 200, seen.text
    saved = app.store.load(matter.id)
    history = displayed_questions(saved, before_version=saved.version, selected_issue_ids=())
    assert len(history) == 1 and history[0]["text"] == PRIVATE
    assert history[0]["state"] == "historical_private_preview_display_not_current_legal_validity"
    assert client.get(preview(matter)).json()["paragraphs"] == shown.json()["paragraphs"]
    assert not saved.facts and not saved.turn_receipts and not saved.asked
    assert author.tool_call.call_count == 1 and sum(len(j.prompts) for j in judges) == 1


def test_malformed_historic_numeric_review_remains_failed_even_after_version_two_configuration(
        client):
    def miscount(raw):
        raw["clauses"][0]["end"] -= 1
        return raw

    app, matter, author, judges = approved(client, miscount)
    posted = client.post(path(matter), json=request(matter))
    assert posted.status_code == 200
    assert posted.json()["result_state"] == "not_released" and PRIVATE not in posted.text
    app.controlled_evaluations = (replace(app.controlled_evaluations[0],
                                         interaction_protocol_version=2),)
    before = app.store.load(matter.id)
    shown = client.get(preview(matter))
    assert shown.status_code == 200, shown.text
    assert shown.json()["result_state"] == "wording_review_failed"
    assert not shown.json()["paragraphs"] and PRIVATE not in shown.text
    assert shown.json()["original_instruction"]["text"] == request(matter)["message"]
    assert client.post(f"{preview(matter)}/seen", json={}).status_code == 409
    assert app.store.load(matter.id) == before
    assert author.tool_call.call_count == 1 and sum(len(j.prompts) for j in judges) == 1


@pytest.mark.parametrize("version", [True, False, 0, 8, "2", None])
def test_trusted_grant_cannot_select_an_unknown_or_false_like_review_protocol(client, version):
    app, _, _, _ = approved(client)
    with pytest.raises(ValueError):
        replace(app.controlled_evaluations[0], interaction_protocol_version=version)


def test_http_body_cannot_select_its_review_protocol_or_approve_a_missing_review(client):
    app, matter, author, judges = unit_approved(client)
    before = app.store.load(matter.id)
    response = client.post(path(matter), json={**request(matter),
                                              "interaction_protocol_version": 2})
    assert response.status_code == 422
    assert app.store.load(matter.id) == before and author.tool_call.call_count == 0 and not judges


@pytest.mark.parametrize("criterion", CRITERIA)
@pytest.mark.parametrize("verdict", [False, None], ids=["rejected", "not_assessed"])
def test_saved_negative_and_unassessed_judgments_never_share_a_ui_verdict(
        client, criterion, verdict):
    def mutate(raw):
        raw[criterion]["assessed"] = verdict
        return raw

    app, matter, author, judges = approved(client, mutate)
    posted = client.post(path(matter), json=request(matter))
    assert posted.status_code == 200 and PRIVATE not in posted.text
    before = app.store.load(matter.id)
    shown = client.get(preview(matter))
    assert shown.status_code == 200 and not shown.json()["paragraphs"]
    expected = "wording_review_failed" if verdict is False else "wording_review_pending"
    assert shown.json()["result_state"] == expected
    if verdict is False:
        assert "did not approve" in shown.json()["message"]
        assert "still needs" not in shown.json()["message"]
    assert shown.json()["original_instruction"]["text"] == request(matter)["message"]
    assert PRIVATE not in shown.text and client.post(
        f"{preview(matter)}/seen", json={}).status_code == 409
    assert app.store.load(matter.id) == before
    assert author.tool_call.call_count == 1 and sum(len(j.prompts) for j in judges) == 1
