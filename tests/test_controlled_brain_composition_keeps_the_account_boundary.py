"""The actual application composes the loop without waiving account authority."""
from dataclasses import replace
from unittest.mock import Mock

import pytest

from nm.app import api
from nm.legal_brain.verify.brain_release import ReviewService
from nm.legal_brain.orchestrate.controlled_brain import EvaluationScope
from nm.legal_brain.orchestrate.loop_contracts import LoopMode, StopReason
from nm.legal_brain.verify.verifier import IndependentVerifier
from nm.shared.external_ai_contracts import ModelPermissionRefused
from nm.shared.model_port import Prompt, Tier, ToolCall
from nm.shared.store_loop_log import MatterLoopLog
from nm.work_the_file.matter_contracts import Matter
from tests.test_independent_claim_verifier import Judge, finding, premise
from tests.test_openai_text_permission import bound, choice
from tests.test_the_loop_records_work_before_using_it import _limits, _response

pytestmark = pytest.mark.class_a


def _scope(client):
    app = api.application()
    matter = replace(Matter.create("adv_demo", "Controlled file"), version=1)
    app.store.commit(matter, expected_version=0)
    return app, matter, EvaluationScope("OWNER-20260927-USD5", "adv_demo",
                                      frozenset({matter.id}), LoopMode.SYNTHETIC)


def _compose(app, scope, session=lambda: True):
    return app.controlled_brain_for(scope, session_current=session,
                                   cost_ceiling=lambda *_: 0.03,
                                   source_version="measured-test-generation",
                                   table_version="checked-test-table-generation")


def test_composed_registry_reads_the_current_sealed_version_not_the_starting_one(client):
    app, matter, scope = _scope(client)
    model = Mock()
    model.provider = "scripted"
    model.resolved_model.return_value = "recorded-v1"
    model.context_budget.return_value = 100000
    model.tool_call.side_effect = [
        _response(ToolCall("inspect-r1", "inspect_tool", {"name": "read_facts"})),
        _response(ToolCall("r1", "read_facts", {})),
        _response(ToolCall("q1", "ask_advocate", {"question": "What needs reviewing?"}))]
    app.model.inner.inner = model
    brain = _compose(app, scope)
    assert brain.checklist_review is None
    output = brain.run(matter_id=matter.id, turn_id="composed-read",
                       message="Read my recorded file.", limits=_limits())
    assert output.reason is StopReason.QUESTION
    read = next(event.payload["receipt"] for event in output.record.events
                if event.kind.value == "tool_returned"
                and event.payload["receipt"]["tool"] == "read_facts")
    assert read["receipt"]["matter_version"] > output.record.identity.matter_version
    assert read["receipt"]["matter_id"] == matter.id
    assert len(app.store.load(matter.id).loop_records) == 1
    assert not app.store.load(matter.id).turn_receipts


def test_controlled_scope_cannot_replace_a_current_account_text_permission(client):
    app, _, scope = _scope(client)
    bound(client)
    with pytest.raises(ModelPermissionRefused, match="AI data sharing"):
        _compose(app, scope)
    assert choice(client).status_code == 200
    brain = _compose(app, scope)
    assert brain.model.provider == "openai"
    assert choice(client, accepted=False, version=1).status_code == 200
    with pytest.raises(ModelPermissionRefused, match="AI data sharing"):
        brain.model.tool_call(Prompt("Review"), brain.registry.definitions, Tier.ROUTINE)


def test_scope_is_finite_and_an_ended_session_cannot_compose_the_loop(client):
    app, _, scope = _scope(client)
    with pytest.raises(PermissionError):
        _compose(app, scope, lambda: False)
    with pytest.raises(PermissionError):
        _compose(app, {"approval_reference": "self-approved"})
    brain = _compose(app, scope)
    with pytest.raises(PermissionError):
        brain.run(matter_id="other-matter", turn_id="foreign", message="Read", limits=_limits())
    brain.scope = replace(scope, advocate_id="other-advocate")
    with pytest.raises(PermissionError):
        brain.run(matter_id=next(iter(scope.matter_ids)), turn_id="foreign-actor",
                  message="Read", limits=_limits())


def test_actual_application_assembles_checks_without_forging_missing_owner_subjects(client):
    from nm.legal_brain.retrieve.evidence_port import Coverage, EvidenceResult, SourceDocument

    app, matter, scope = _scope(client)
    held = finding()
    current = replace(matter, facts=(premise(),), version=matter.version + 1)
    app.store.commit(current, expected_version=matter.version)
    app.evidence.read_provision = Mock(return_value=EvidenceResult(
        Coverage.ANSWERED, (held,), searched_stores=("held",)))
    # New working-record checks reopen the exact source; the fixture supplies
    # that real typed read rather than asking an untyped Mock to certify it.
    app.evidence.document = Mock(return_value=SourceDocument(
        "read", label=held.ref, store="held", segments=(("1", held.span),),
        target=0, locator=held.locator, kind=held.source_kind.value))
    author = Mock()
    author.provider = "scripted"
    author.resolved_model.return_value = "recorded-v1"
    author.context_budget.return_value = 100000
    # Composition now dispatches real final-check reads. This fixture must
    # explicitly model their unavailability, not return an untyped Mock.
    from nm.shared.model_port import ProviderUnavailable

    author.structured.side_effect = ProviderUnavailable("Controlled final-check read unavailable")
    author.tool_call.side_effect = [
        _response(ToolCall("inspect-source", "inspect_tool", {"name": "read_provision"})),
        _response(ToolCall("source", "read_provision", {
            "act": "Recorded primary rule", "section": "1", "as_of": "2026-01-01"})),
        _response(ToolCall("proposal", "submit_answer", {"claims": [{
            "id": "p1", "text": "The benefit depends on notice.",
            "sources": [{"locator": held.locator, "quote": held.span}],
            "premise_ids": ["fact_1"], "contrary": [], "depends_on": []}]}))]
    app.model.inner.inner = author
    judge = Judge()
    reviewer = ReviewService(store=app.store,
        log=MatterLoopLog(app.store, advocate_id=scope.advocate_id),
        verifier=IndependentVerifier(judge), session_current=lambda: True,
        cost_ceiling=lambda *_: 0.03)
    brain = app.controlled_brain_for(scope, session_current=lambda: True,
        cost_ceiling=lambda *_: 0.03, source_version=app.source_generation_guard().version,
        table_version="checked-table-generation", reviewer=reviewer)
    assert brain.checklist_review.reviewer is reviewer
    result = brain.evaluate(matter_id=matter.id, turn_id="application-assessment",
        message="Assess the notice requirement.", limits=_limits(), max_repairs=0)
    assert len(result.attempts) == 1 and len(result.assessments) == 1
    assessed = result.assessments[0]
    checked = {row.gate_id: row for row in (*assessed.outputs, *assessed.boundaries)}
    assert checked["G-GROUND"].assessed is True
    assert checked["G-DUTY"].assessed is None
    assert checked["G-CONSISTENT"].assessed is None
    # The new finalizer supplies the exact captured claim/file dependency
    # ledger. This does not certify the legacy corpus or missing model reads.
    assert checked["G-CURRENCY"].assessed is True
    assert "dependency" in checked["G-CURRENCY"].reason.lower()
    assert len(checked) == 24
    assert not assessed.checks_complete and not result.client_ready
    assert not app.store.load(matter.id).turn_receipts
    assert len(result.publications) == 1
    assert result.publications[0].client_ready is False
    assert result.publications[0].record.events[-1].payload["released"] is False
    starts = [event.payload for event in result.attempts[0].record.events
              if event.kind.value == "model_started"]
    assert len(starts) == 3
    assert "read_provision" not in {row["name"] for row in starts[0]["tools"]}
    assert "read_provision" in {row["name"] for row in starts[1]["tools"]}
    assert max(row["reserved_tokens"] for row in starts) <= _limits().budget.max_tokens
    names = {row.name for row in brain.registry.definitions}
    assert {"compute_limitation", "compute_interest"} <= names
    assert {"research", "oppose", "discover_tools", "inspect_tool", "read_owner_guide"} <= names
    assert {"oppose_early", "oppose_full", "oppose_matter", "read_opposition_status"} <= names
