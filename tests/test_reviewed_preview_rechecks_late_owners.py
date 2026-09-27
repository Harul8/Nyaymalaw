"""The saved wording review cannot outlive a late permission or source loss.

Real sealed parents and independent scripted checks; no paid provider calls.
The planted changes occur after recorded() has returned a positive review,
so early admission cannot accidentally satisfy the final-boundary controls.
"""
from dataclasses import replace

import pytest

from nm.arrive.advocate_contracts import utcnow
from nm.legal_brain.verify.brain_finalization import SavedCheckReader
from nm.legal_brain.verify.brain_release import ReviewRefused
from nm.legal_brain.evaluate.controlled_evaluations_composition import (
    EvaluationUnavailable,
    _current_admission,
)
from nm.legal_brain.verify.interaction_review import InteractionReviewService
from nm.legal_brain.verify.interaction_subject import InteractionSubjectOwner
from nm.legal_brain.orchestrate.loop_contracts import LoopLimits
from nm.legal_brain.reason.matter_support import REFERENCE_KEYS, captured_documents
from nm.legal_brain.communicate.reviewed_preview import ReviewedPreviewService
from nm.shared.budget_contracts import Budget
from nm.shared.model_port import ToolCall
from tests.test_document_words_reach_review_without_becoming_facts_or_law import (
    _case as document_case,
)
from tests.test_document_words_reach_review_without_becoming_facts_or_law import (
    _finalizer as document_finalizer,
)
from tests.test_interaction_words_require_an_independent_exact_review import InteractionJudge
from tests.test_openai_text_permission import bound, choice
from tests.test_private_brain_transport_cannot_approve_or_release_itself import PRIVATE, request
from tests.test_reviewed_private_preview_checks_saved_words import ready
from tests.test_scoped_preview_uses_the_actual_application_boundary import approved, preview
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a


def checked_interaction(tmp_path, *, document=False):
    if document:
        store, brain, first, _, _, _, document_current = document_case(tmp_path)
        captured = captured_documents(first.record)[0]
        brain.model.tool_call.side_effect = [
            replace(_response(call), model="scripted:document-author") for call in (
                ToolCall("quote", "quote_matter", {
                    key: captured.source[key] for key in REFERENCE_KEYS}),
                ToolCall("ask", "ask_advocate", {"question": "Is the recorded date disputed?"}))]
        outcome = brain.run(matter_id="mat_one", turn_id="document-question",
            message="The extracted date may be wrong; ask what would resolve this uncertainty.",
            limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 20, 500))
        brain.finalizer, brain.assessment = document_finalizer(
            store, brain, outcome, document_current)
        assert len(captured_documents(outcome.record)) == 1
    else:
        store, brain, outcome, _, _, _, _ = ready(tmp_path, terminal="ask_advocate")
        document_current = None
    judge = InteractionJudge()
    owner = InteractionSubjectOwner(principles=brain.principles, source_current=lambda *_: True)
    reader = SavedCheckReader(store=store, log=brain.log, model=judge,
        session_current=lambda: True, cost_ceiling=lambda *_: 0.03,
        current_tools_version=lambda: outcome.record.identity.tools_version,
        current_principles_version=lambda: brain.principles.load().version,
        subject_packages=owner.packages, document_current=document_current, max_tokens=2048)
    interaction = InteractionReviewService(reader=reader, owner=owner)
    reviewed = interaction.review(outcome)
    assert reviewed.checked and reviewed.candidate_text
    brain.interaction_review = interaction
    service = ReviewedPreviewService(brain=brain, current=lambda: True)
    arguments = {"actor": outcome.record.identity.advocate_id,
                 "matter_id": outcome.record.identity.matter_id,
                 "turn_id": outcome.record.identity.turn_id}
    assert service.read(**arguments).paragraphs[0].text == reviewed.candidate_text
    return store, service, interaction, judge, arguments


@pytest.mark.parametrize("owner", ["source_generation", "law_current", "principles", "document"])
def test_positive_saved_words_are_refused_when_an_owner_moves_after_recorded_check(
        tmp_path, owner):
    store, service, interaction, judge, arguments = checked_interaction(
        tmp_path, document=owner == "document")
    before = store.load(arguments["matter_id"])
    original = interaction.recorded
    planted = []

    def changed(outcome):
        checked = original(outcome)
        assert checked is not None and checked.checked
        if owner == "source_generation":
            interaction.reader.current_tools_version = lambda: "changed-source-generation"
        elif owner == "law_current":
            interaction.owner.source_current = lambda *_: False
        elif owner == "principles":
            interaction.reader.current_principles_version = lambda: "changed-principles"
        else:
            assert captured_documents(outcome.record)
            interaction.reader.document_current = lambda *_: False
        planted.append(owner)
        return checked

    interaction.recorded = changed
    with pytest.raises(ReviewRefused):
        service.read(**arguments)
    assert planted == [owner]
    assert store.load(arguments["matter_id"]) == before
    assert not before.turn_receipts and len(judge.prompts) == 1


def test_actual_account_consent_revocation_during_a_checked_get_hides_the_words(
        client, monkeypatch):
    app, matter, author, judges = approved(client)
    posted = client.post(f"/api/matters/{matter.id}/brain/preview", json=request(matter))
    assert posted.status_code == 200 and PRIVATE not in posted.text
    assert len(judges[0].prompts) == 1
    _, transport = bound(client)
    assert choice(client).status_code == 200
    original = InteractionReviewService.recorded
    planted = []

    def withdrawn(service, outcome):
        checked = original(service, outcome)
        assert checked is not None and checked.checked
        result = choice(client, accepted=False, version=1)
        assert result.status_code == 200 and result.json()["accepted"] is False
        planted.append("consent")
        return checked

    monkeypatch.setattr(InteractionReviewService, "recorded", withdrawn)
    response = client.get(preview(matter))
    assert planted == ["consent"], response.text
    assert response.status_code in {403, 409} and PRIVATE not in response.text
    assert not transport.calls
    assert author.tool_call.call_count == 1
    assert sum(len(judge.prompts) for judge in judges) == 1
    assert not app.store.load(matter.id).turn_receipts


def test_an_author_factory_requires_its_current_trusted_permission_owner(client):
    app, matter, _, _ = approved(client)
    grant = app.controlled_evaluations[0]
    with pytest.raises(ValueError):
        replace(grant, author_factory=lambda *_: app.model)
    calls, permitted = [], [True]

    def permission(application, scope):
        assert application is app and scope is grant.scope
        calls.append(permitted[0])
        return permitted[0]

    current_grant = replace(grant, author_factory=lambda *_: app.model,
                            permission_current=permission)
    app.controlled_evaluations = (current_grant,)
    selected, current = _current_admission(app, actor="adv_demo", matter_id=matter.id,
        session_current=lambda: True, now=utcnow)
    assert selected is current_grant and current() is True
    permitted[0] = False
    assert current() is False
    assert calls == [True, True, False]
    with pytest.raises(EvaluationUnavailable):
        _current_admission(app, actor="adv_demo", matter_id=matter.id,
            session_current=lambda: True, now=utcnow)


@pytest.mark.parametrize("unproved", [None, 1, "true", {}])
def test_factory_permission_requires_true_not_a_truthy_or_unknown_value(client, unproved):
    app, matter, author, judges = approved(client)
    grant = app.controlled_evaluations[0]
    app.controlled_evaluations = (replace(grant,
        author_factory=lambda *_: app.model, permission_current=lambda *_: unproved),)
    response = client.get(preview(matter))
    assert response.status_code == 403 and PRIVATE not in response.text
    assert author.tool_call.call_count == 0 and not judges
    assert not app.store.load(matter.id).loop_records
