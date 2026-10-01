"""Actual encrypted document/tool/review/publication path, never fact promotion."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from unittest.mock import Mock

import pytest

from nm.Archives.legal_brain.verify import grounding
from nm.Archives.legal_brain.verify.brain_assessment import AssessmentRefused, AssessmentService
from nm.Archives.legal_brain.verify.brain_finalization import FinalizationService, SavedCheckReader
from nm.Archives.legal_brain.verify.brain_publication import PrivatePublicationService
from nm.Archives.legal_brain.verify.brain_release import ReviewRefused, ReviewService, prepare_claims
from nm.Archives.legal_brain.orchestrate.controlled_brain import ControlledBrain, EvaluationScope
from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopLimits, LoopMode
from nm.Archives.legal_brain.reason.matter_support import REFERENCE_KEYS, captured_documents
from nm.Archives.legal_brain.common.principles_file_adapter import FilePrinciples
from nm.Archives.legal_brain.orchestrate.tool_catalogue import catalogue_tools
from nm.Archives.legal_brain.orchestrate.tools import Boundary, foundation_tools
from nm.Archives.legal_brain.verify.verifier import IndependentVerifier
from nm.open_matter.matter_documents_port import DocumentRefused
from nm.shared.budget_contracts import Budget
from nm.shared.model_port import ToolCall
from nm.shared.store_loop_log import MatterLoopLog
from nm.work_the_file import dependency
from tests.test_admitted_documents_are_owned_exact_and_sealed import (
    WORDS,
    analyse,
    fixture,
    quote_args,
)
from tests.test_independent_claim_verifier import Judge, response
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a


def _case(tmp_path, *, text=None, judged=None):
    documents, store, _, _, _, original = fixture(tmp_path)
    reading = analyse(documents, original)
    args = {**quote_args(reading), "end": len(WORDS)}
    quoted = documents.quote("mat_one", "adv_one", store.load("mat_one").version, **args)
    registry = foundation_tools(store, Mock(), manifest=Mock(), source_version="controlled-docs",
        before=lambda *_: Boundary(True, "Controlled document evaluation"),
        after=lambda *_: Boundary(True, "Controlled result check"))
    registry = registry.extend(catalogue_tools(store, Mock(), source_version="controlled-docs",
                                               matter_documents=documents))
    author = Mock()
    author.provider = "scripted"
    author.resolved_model.return_value = "scripted:document-author"
    author.context_budget.return_value = 100000
    author.tool_call.side_effect = [replace(_response(call), model="scripted:document-author")
        for call in (ToolCall("doc1", "quote_matter", args), ToolCall("answer1", "submit_answer", {
            "claims": [{"id": "docclaim", "text": text or
                f'The extracted document records: "{WORDS}". This does not establish its truth.',
                "sources": [{"locator": quoted.locator, "quote": quoted.text}],
                "premise_ids": [], "contrary": [], "depends_on": []}]}))]
    log = MatterLoopLog(store, advocate_id="adv_one")
    judge = Judge(answer=judged or response(words="The recorded date is 4 March 2026"))

    def current(matter, span):
        try:
            latest = documents.quote(matter.id, matter.advocate_id, matter.version,
                                    **{key: span.source[key] for key in REFERENCE_KEYS})
        except DocumentRefused:
            return False
        return latest == span.captured_quote

    reviewer = ReviewService(store=store, log=log, verifier=IndependentVerifier(judge),
        session_current=lambda: True, cost_ceiling=lambda *_: 0.03, document_current=current)
    brain = ControlledBrain(store=store, model=author, principles=FilePrinciples(), log=log,
        registry=registry, scope=EvaluationScope("OWNER-DOCS", "adv_one",
            frozenset({"mat_one"}), LoopMode.SYNTHETIC), cost_ceiling=lambda *_: 0.03,
        session_current=lambda: True, reviewer=reviewer)
    outcome = brain.run(matter_id="mat_one", turn_id="document-assessment",
        message="Explain what the held document says without treating it as true.",
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 10, 500))
    return store, brain, outcome, judge, documents, original, current


def _finalizer(store, brain, outcome, current):
    reader = SavedCheckReader(store=store, log=brain.log, model=brain.model,
        session_current=lambda: True, cost_ceiling=lambda *_: 0.03,
        current_tools_version=lambda: outcome.record.identity.tools_version,
        current_principles_version=lambda: outcome.record.identity.principles_version,
        document_current=current)
    finalizer = FinalizationService(reader=reader, today=lambda: date(2026, 9, 27),
                                    jurisdiction="Not established")
    assessor = AssessmentService(store=store, log=brain.log, session_current=lambda: True,
        supplement=finalizer.subjects, boundaries=finalizer.boundaries,
        current_tools_version=lambda: outcome.record.identity.tools_version,
        current_principles_version=lambda: outcome.record.identity.principles_version,
        document_current=current)
    return finalizer, assessor


def test_actual_document_is_separately_bound_and_conditionally_reviewed(tmp_path):
    store, brain, outcome, judge, _, _, current = _case(tmp_path)
    quotes = captured_documents(outcome.record)
    assert len(quotes) == 1
    package = prepare_claims(outcome, store.load("mat_one"))[0]
    assert not package.spans and not package.premises and len(package.documents) == 1
    review = brain.review(outcome)
    assert review.result.released and not review.client_ready
    payload = json.loads(judge.prompts[0].user)
    assert not payload["sources"] and not payload["premises"]
    assert payload["case_documents"][0]["source"]["facts_established"] is False
    assert "not authenticated" in payload["case_documents"][0]["limits"]
    assert store.load("mat_one").facts == ()
    finalizer, assessor = _finalizer(store, brain, outcome, current)
    assessment = assessor.assess(outcome, review, expected_version=store.load("mat_one").version)
    receipts = {row.gate_id: row for row in assessment.outputs}
    assert receipts["G-QUOTE"].assessed is True
    assert receipts["G-GROUND"].assessed is True
    assert receipts["G-DATE"].assessed is None
    assert not assessment.client_ready and not assessment.checks_complete
    ledger = finalizer.subjects(store.load("mat_one"), outcome, review).ledger
    node = ledger.node("claim:docclaim")
    assert {rest.kind for rest in node.rests_on} == {dependency.InputKind.DOCUMENT}
    assert dependency.presentable(ledger, node.name)[0]
    assert grounding.verify(assessment.candidate, (), retrieved_documents=quotes,
        independent_packages=review.result.released, independent_records=review.records).clear


@pytest.mark.parametrize("reader", [None, lambda *_: False])
def test_missing_or_negative_actual_document_owner_refuses_before_dispatch(tmp_path, reader):
    _, brain, outcome, judge, _, _, _ = _case(tmp_path)
    brain.reviewer.document_current = reader
    with pytest.raises(ReviewRefused, match="document"):
        brain.review(outcome)
    assert not judge.prompts


def test_revoked_document_refuses_both_review_and_final_publication_subjects(tmp_path):
    store, brain, outcome, judge, documents, original, current = _case(tmp_path)
    reviewed = brain.review(outcome)
    finalizer, assessor = _finalizer(store, brain, outcome, current)
    documents.revoke("mat_one", "adv_one", store.load("mat_one").version, original)
    for callback in (lambda: brain.review(outcome), lambda: finalizer.reader.current(outcome),
                     lambda: assessor.assess(outcome, reviewed)):
        with pytest.raises((ReviewRefused, AssessmentRefused)):
            callback()
    assert len(judge.prompts) == 1 and not store.load("mat_one").turn_receipts


def test_client_document_cannot_supply_legal_authority(tmp_path):
    _, brain, outcome, judge, _, _, _ = _case(tmp_path,
        text="Section 999 permits the requested relief.")
    reviewed = brain.review(outcome)
    assert not reviewed.result.released and not judge.prompts


def test_textual_label_cannot_skip_document_inference_and_opposition(tmp_path):
    _, brain, outcome, _, _, _, _ = _case(tmp_path,
        judged=response(textual=True, inference=None, opposition=None,
                        words="The recorded date is 4 March 2026"))
    reviewed = brain.review(outcome)
    assert reviewed.records[0].textual_eligible is False
    assert not reviewed.result.released


def test_independent_review_cannot_accept_invented_document_quote(tmp_path):
    _, brain, outcome, _, _, _, _ = _case(tmp_path,
        text='The document says "There was a signed and witnessed transfer".')
    reviewed = brain.review(outcome)
    assert not reviewed.result.released


def test_captured_document_dictionary_tampering_is_detected(tmp_path):
    store, _, outcome, _, _, _, _ = _case(tmp_path)
    package = prepare_claims(outcome, store.load("mat_one"))[0]
    package.documents[0].captured_quote.source["derivative_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="changed"):
        _ = package.identity


def test_actual_private_publication_saves_document_graph_and_never_admits_a_fact(tmp_path):
    store, brain, outcome, _, _, _, current = _case(tmp_path)
    review = brain.review(outcome)
    finalizer, assessor = _finalizer(store, brain, outcome, current)
    assessment = assessor.assess(outcome, review, expected_version=store.load("mat_one").version)
    publisher = PrivatePublicationService(assessment=assessor, finalizer=finalizer)
    result = publisher.record(outcome, review, assessment, original_message=
        "Explain what the held document says without treating it as true.")
    saved = store.load("mat_one")
    assert saved.facts == () and not saved.turn_receipts
    assert not result.client_ready
    assert result.record.events[-1].payload["released"] is False
    ledger = dependency.Ledger.from_stored(
        result.record.events[-1].payload["dependency_ledger"])
    assert ledger.tracked[0].kind is dependency.InputKind.DOCUMENT


def test_document_identity_changes_only_its_actual_dependency_closure(tmp_path):
    store, brain, outcome, _, _, _, current = _case(tmp_path)
    review = brain.review(outcome)
    finalizer, _ = _finalizer(store, brain, outcome, current)
    ledger = finalizer.subjects(store.load("mat_one"), outcome, review).ledger
    document = ledger.tracked[0]
    unrelated = dependency.Node("independent", "Unrelated account", rests_on=(
        dependency.Rest(dependency.InputKind.FACT, "unrelated_fact"),))
    ledger = dependency.record(ledger, unrelated)
    changed, did = dependency.observe(ledger, document.kind, document.id, "changed-extract")
    assert did
    invalidated, affected = dependency.invalidate(changed, (dependency.Rest(
        document.kind, document.id),), reason="The admitted extract changed")
    assert affected == ("claim:docclaim",)
    assert invalidated.node("claim:docclaim").currency is dependency.Currency.STALE
    assert invalidated.node("independent") == ledger.node("independent")


@pytest.mark.parametrize("mutation", ["missing_dispatch", "changed_snapshot", "wrong_actor_source",
                                      "established_fact", "repeated_return"])
def test_document_capture_refuses_incomplete_or_changed_receipts(tmp_path, mutation):
    from nm.Archives.legal_brain.orchestrate.loop_contracts import StepKind

    _, _, outcome, _, _, _, _ = _case(tmp_path)
    events = list(outcome.record.events)
    returned = next(i for i, event in enumerate(events) if event.kind is StepKind.TOOL_RETURNED)
    payload = json.loads(json.dumps(events[returned].payload))
    if mutation == "missing_dispatch":
        events = [event for event in events if event.kind is not StepKind.TOOL_STARTED]
    elif mutation == "repeated_return":
        events.insert(returned + 1, events[returned])
    else:
        receipt = payload["receipt"]
        if mutation == "changed_snapshot":
            receipt["receipt"]["snapshot"] = "unknown"
        elif mutation == "wrong_actor_source":
            receipt["data"]["source"]["original_id"] = "another-original"
        else:
            receipt["data"]["source"]["facts_established"] = True
        events[returned] = Mock(kind=events[returned].kind,
                                sequence=events[returned].sequence, payload=payload)
    # A deliberately corrupted decoder input, not a fake sealed record.
    with pytest.raises(ValueError):
        captured_documents(Mock(events=tuple(events), identity=outcome.record.identity))
